#!/usr/bin/env python3
"""Collect and monitor system schedule + OpenClaw schedule snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
CRITICAL_TIMER_UNITS = {
    "certbot.timer",
    "sysstat-collect.timer",
    "fstrim.timer",
    "e2scrub_all.timer",
}
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "ops-agent/system-schedule-audit"


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def run_command(command: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_log_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else "silent"


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


def digest_object(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_openclaw_jobs(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "ok": False, "job_count": 0, "job_ids": [], "error": ""}
    if not path.exists():
        out["error"] = "jobs file not found"
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        if not isinstance(jobs, list):
            jobs = []
        job_ids = [str(item.get("id", "")) for item in jobs if isinstance(item, dict)]
        out.update({"ok": True, "job_count": len(job_ids), "job_ids": sorted(x for x in job_ids if x)})
        return out
    except Exception as exc:
        out["error"] = str(exc)
        return out


def get_user_crontab() -> dict[str, Any]:
    rc, out, err = run_command(["crontab", "-l"], timeout=10)
    if rc != 0:
        return {"ok": False, "lines": [], "raw": "", "error": err or f"exit={rc}"}
    lines = [x.rstrip() for x in out.splitlines()]
    active = [x for x in lines if x.strip() and not x.strip().startswith("#")]
    return {"ok": True, "lines": active, "raw": out, "error": ""}


def get_root_crontab() -> dict[str, Any]:
    rc, out, err = run_command(["sudo", "-n", "crontab", "-l"], timeout=10)
    if rc != 0:
        return {"ok": False, "lines": [], "raw": "", "error": err or f"exit={rc}"}
    lines = [x.rstrip() for x in out.splitlines()]
    active = [x for x in lines if x.strip() and not x.strip().startswith("#")]
    return {"ok": True, "lines": active, "raw": out, "error": ""}


def get_cron_d() -> dict[str, Any]:
    root = Path("/etc/cron.d")
    if not root.exists() or not root.is_dir():
        return {"ok": False, "files": {}, "list": [], "error": "missing /etc/cron.d"}
    files: dict[str, dict[str, Any]] = {}
    names = sorted(x.name for x in root.iterdir() if x.is_file())
    for name in names:
        path = root / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            files[name] = {"ok": True, "line_count": len(text.splitlines()), "sha256": digest_object(text)}
        except Exception as exc:
            files[name] = {"ok": False, "line_count": 0, "sha256": "", "error": str(exc)}
    return {"ok": True, "files": files, "list": names, "error": ""}


def get_systemd_timers() -> dict[str, Any]:
    rc, out, err = run_command(["systemctl", "list-timers", "--all", "--no-pager", "--no-legend"], timeout=20)
    if rc != 0:
        return {"ok": False, "units": [], "raw": "", "error": err or f"exit={rc}"}
    lines = [x.rstrip() for x in out.splitlines() if x.strip()]
    units: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 5:
            units.append(parts[4])
    return {"ok": True, "units": sorted(set(units)), "raw": out, "error": ""}


def collect_snapshot(openclaw_jobs_file: Path) -> dict[str, Any]:
    return {
        "collected_at": now_iso(),
        "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown"),
        "openclaw": get_openclaw_jobs(openclaw_jobs_file),
        "user_crontab": get_user_crontab(),
        "root_crontab": get_root_crontab(),
        "cron_d": get_cron_d(),
        "systemd_timers": get_systemd_timers(),
    }


def to_fingerprints(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        "openclaw_jobs": digest_object(snapshot.get("openclaw", {}).get("job_ids", [])),
        "user_crontab": digest_object(snapshot.get("user_crontab", {}).get("lines", [])),
        "root_crontab": digest_object(snapshot.get("root_crontab", {}).get("lines", [])),
        "cron_d": digest_object(snapshot.get("cron_d", {}).get("files", {})),
        "systemd_timers": digest_object(snapshot.get("systemd_timers", {}).get("units", [])),
    }


def compare_snapshots(snapshot: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    prev_fp = state.get("fingerprints") if isinstance(state.get("fingerprints"), dict) else {}
    curr_fp = to_fingerprints(snapshot)
    changed = [key for key, value in curr_fp.items() if prev_fp.get(key) != value]

    risk_reasons: list[str] = []
    change_reasons: list[str] = []

    if changed:
        change_reasons.append("schedule_changed")
    for key in changed:
        change_reasons.append(f"changed:{key}")

    prev_openclaw_ids = set(state.get("last_openclaw_job_ids", []))
    curr_openclaw_ids = set(snapshot.get("openclaw", {}).get("job_ids", []))
    removed_openclaw = sorted(prev_openclaw_ids - curr_openclaw_ids)
    if removed_openclaw:
        risk_reasons.append(f"openclaw_job_removed:{len(removed_openclaw)}")

    prev_root_lines = set(state.get("last_root_crontab_lines", []))
    curr_root_lines = set(snapshot.get("root_crontab", {}).get("lines", []))
    if prev_root_lines and prev_root_lines != curr_root_lines:
        risk_reasons.append("root_crontab_changed")

    prev_timer_units = set(state.get("last_timer_units", []))
    curr_timer_units = set(snapshot.get("systemd_timers", {}).get("units", []))
    missing_critical = sorted((CRITICAL_TIMER_UNITS & prev_timer_units) - curr_timer_units)
    if missing_critical:
        risk_reasons.append(f"critical_timer_missing:{','.join(missing_critical)}")

    return {
        "changed_keys": changed,
        "change_reasons": change_reasons,
        "risk_reasons": risk_reasons,
        "fingerprints": curr_fp,
        "removed_openclaw_ids": removed_openclaw,
        "missing_critical_timers": missing_critical,
    }


def build_state(snapshot: dict[str, Any], compare: dict[str, Any], snapshot_file: Path) -> dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "last_snapshot_file": str(snapshot_file),
        "fingerprints": compare.get("fingerprints", {}),
        "last_openclaw_job_ids": snapshot.get("openclaw", {}).get("job_ids", []),
        "last_root_crontab_lines": snapshot.get("root_crontab", {}).get("lines", []),
        "last_timer_units": snapshot.get("systemd_timers", {}).get("units", []),
    }


def build_output(
    *,
    snapshot: dict[str, Any],
    compare: dict[str, Any],
    task_id: str,
    sender_identity: str,
    normal_log_mode: str,
    snapshot_file: Path,
) -> tuple[bool, str]:
    risk_reasons = compare.get("risk_reasons", [])
    change_reasons = compare.get("change_reasons", [])

    notify = bool(risk_reasons)
    # Chat mode can announce schedule drift, but stays quiet when there is no change.
    if not notify and change_reasons and normal_log_mode == "chat":
        notify = True
    if not notify:
        return False, "NO_REPLY"

    lines: list[str] = []
    lines.append("# ops-system-schedule-audit")
    lines.append(f"- sender_identity: {sender_identity}")
    lines.append(f"- task: {task_id or '-'}")
    lines.append(f"- time: {now_iso()}")
    lines.append(f"- normal_log_mode: {normal_log_mode}")
    if risk_reasons:
        lines.append(f"- risk_reasons: {', '.join(risk_reasons)}")
    if change_reasons:
        lines.append(f"- change_reasons: {', '.join(change_reasons)}")

    openclaw = snapshot.get("openclaw", {})
    lines.append(f"- openclaw_jobs: ok={openclaw.get('ok')}, count={openclaw.get('job_count', 0)}")
    lines.append(f"- user_crontab_lines: {len(snapshot.get('user_crontab', {}).get('lines', []))}")
    lines.append(f"- root_crontab_lines: {len(snapshot.get('root_crontab', {}).get('lines', []))}")
    lines.append(f"- cron_d_files: {len(snapshot.get('cron_d', {}).get('list', []))}")
    lines.append(f"- systemd_timers: {len(snapshot.get('systemd_timers', {}).get('units', []))}")
    lines.append(f"- evidence: {snapshot_file}")
    return True, "\n".join(lines)


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="System/OpenClaw schedule snapshot monitor")
    parser.add_argument("--openclaw-jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--output-dir", default=str(home / ".openclaw/ops/system-schedule/snapshots"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/system-schedule/state.json"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = Path(args.state_file).expanduser()
    state = load_json(state_file, {})
    if not isinstance(state, dict):
        state = {}

    snapshot = collect_snapshot(Path(args.openclaw_jobs_file).expanduser())
    sender_identity = normalize_sender_identity(args.sender_identity)
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    run_id = uuid.uuid4().hex[:8]
    snapshot_file = output_dir / f"{stamp}_{run_id}.json"
    save_json(snapshot_file, snapshot)

    compare = compare_snapshots(snapshot, state)
    new_state = build_state(snapshot, compare, snapshot_file)
    save_json(state_file, new_state)

    notify, output = build_output(
        snapshot=snapshot,
        compare=compare,
        task_id=str(args.task_id or ""),
        sender_identity=sender_identity,
        normal_log_mode=normalize_log_mode(args.normal_log_mode),
        snapshot_file=snapshot_file,
    )

    result = {
        "notify": notify,
        "sender_identity": sender_identity,
        "output": output,
        "snapshot_file": str(snapshot_file),
        "state_file": str(state_file),
        "risk_reasons": compare.get("risk_reasons", []),
        "change_reasons": compare.get("change_reasons", []),
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

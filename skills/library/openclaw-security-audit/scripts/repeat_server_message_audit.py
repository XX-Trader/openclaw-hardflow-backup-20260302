#!/usr/bin/env python3
"""Inspect recent cron messages on multiple servers and remediate noisy runtime drift."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc
DEFAULT_SERVERS = [
    "pm-website",
    "大白pm",
    "nofx",
    "coingod",
    "tokyo-claw",
]
DEFAULT_TOTAL_ROUNDS = 4
DEFAULT_INTERVAL_SECONDS = 3 * 60 * 60
DEFAULT_RECENT_LIMIT = 50
DEFAULT_LATEST_LIMIT = 20

ENGLISH_CHATTER_RE = re.compile(
    r"^(Let's|Okay,|Now let's|I'll|I will|Running |Starting |Let me )",
    re.IGNORECASE,
)
NORMAL_INFO_PREFIXES = (
    "# local-git-backup",
    "# web-intel-collect",
    "# web-intel-review",
    "# todo-patrol",
    "# reviewer-cron",
    "local-git-backup",
    "web-intel-collect",
    "web-intel-review",
    "web-intel-review (optimization)",
    "web-intel-review (project-doc)",
)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now_utc().isoformat()


def classify_summary(summary: str) -> str | None:
    text = str(summary or "").strip()
    if not text:
        return None
    if text.startswith("{") and '"ok"' in text:
        return "json_误发"
    if ENGLISH_CHATTER_RE.match(text):
        return "英文废话误发"
    if text.startswith("```"):
        return "正常信息误发"
    if any(text.startswith(prefix) for prefix in NORMAL_INFO_PREFIXES):
        return "正常信息误发"
    if "task:" in text and "time:" in text and ("repo:" in text or "sender_identity:" in text):
        return "正常信息误发"
    return None


def summarize_entries(
    entries: list[dict[str, Any]],
    *,
    recent_limit: int = DEFAULT_RECENT_LIMIT,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
) -> dict[str, Any]:
    normalized = sorted(entries, key=lambda item: int(item.get("ts_sort") or 0), reverse=True)
    recent_delivered = [
        item for item in normalized if bool(item.get("delivered")) and str(item.get("summary") or "").strip()
    ][: max(1, int(recent_limit))]
    latest_items = normalized[: max(1, int(latest_limit))]

    unsuitable_count = 0
    samples: list[dict[str, Any]] = []
    for item in recent_delivered:
        kind = classify_summary(str(item.get("summary") or ""))
        if not kind:
            continue
        unsuitable_count += 1
        if len(samples) < 8:
            preview = str(item.get("summary") or "").splitlines()[0][:160]
            samples.append(
                {
                    "ts": item.get("ts"),
                    "job": item.get("job_name") or item.get("job_id") or "",
                    "kind": kind,
                    "preview": preview,
                }
            )

    latest20_quiet_ok = sum(
        1 for item in latest_items if (item.get("delivered") is False and not str(item.get("summary") or "").strip())
    )
    latest20_unsuitable_count = sum(
        1
        for item in latest_items
        if bool(item.get("delivered")) and classify_summary(str(item.get("summary") or ""))
    )
    current_samples: list[dict[str, Any]] = []
    for item in latest_items:
        if not bool(item.get("delivered")):
            continue
        kind = classify_summary(str(item.get("summary") or ""))
        if not kind:
            continue
        if len(current_samples) >= 8:
            break
        current_samples.append(
            {
                "ts": item.get("ts"),
                "job": item.get("job_name") or item.get("job_id") or "",
                "kind": kind,
                "preview": str(item.get("summary") or "").splitlines()[0][:160],
            }
        )

    return {
        "recent_delivered_checked": len(recent_delivered),
        "unsuitable_count": unsuitable_count,
        "latest20_total": len(latest_items),
        "latest20_quiet_ok": latest20_quiet_ok,
        "latest20_unsuitable_count": latest20_unsuitable_count,
        "samples": samples,
        "current_samples": current_samples,
        "historical_only": unsuitable_count > 0 and latest20_unsuitable_count == 0,
    }


def compute_round_schedule(
    start_at: datetime,
    *,
    total_rounds: int,
    interval_seconds: int,
) -> list[datetime]:
    rounds = max(1, int(total_rounds))
    interval = max(1, int(interval_seconds))
    return [start_at + timedelta(seconds=interval * idx) for idx in range(rounds)]


def tail_text(text: str, *, max_lines: int = 20, max_chars: int = 2400) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    lines = value.splitlines()
    clipped = "\n".join(lines[-max_lines:])
    return clipped[-max_chars:]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_ssh(server: str, ssh_config: str, remote_command: str, *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh",
            "-F",
            ssh_config,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            server,
            remote_command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, int(timeout_seconds)),
    )


def run_remote_python(server: str, ssh_config: str, script: str, *, timeout_seconds: int) -> dict[str, Any]:
    remote_command = "python3 - <<'PY'\n" + script + "\nPY"
    proc = run_ssh(server, ssh_config, remote_command, timeout_seconds=timeout_seconds)
    stdout = str(proc.stdout or "").strip()
    stderr = str(proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"server={server} rc={proc.returncode} stdout={tail_text(stdout)!r} stderr={tail_text(stderr)!r}"
        )
    if not stdout:
        raise RuntimeError(f"server={server} remote python returned empty stdout")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"server={server} remote json decode failed stdout={tail_text(stdout)!r} stderr={tail_text(stderr)!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"server={server} remote payload is not a json object")
    return payload


def build_remote_probe_script(server: str) -> str:
    return f"""
from pathlib import Path
import datetime
import json
import glob

server = {json.dumps(server, ensure_ascii=False)}
home = Path.home()
openclaw_home = home / ".openclaw"
repo_path = ""
for pattern in ("openclaw-hardflow-backup-*", "openclaw-*"):
    candidates = sorted((p for p in home.glob(pattern) if p.is_dir()), key=lambda item: item.name, reverse=True)
    for candidate in candidates:
        if (candidate / "scripts/openclaw-ops/install_workflow_profile.py").exists():
            repo_path = str(candidate)
            break
    if repo_path:
        break

jobs_file = openclaw_home / "cron" / "jobs.json"
jobs_map = {{}}
if jobs_file.exists():
    try:
        raw_jobs = json.loads(jobs_file.read_text(encoding="utf-8-sig"))
        if isinstance(raw_jobs, list):
            items = raw_jobs
        elif isinstance(raw_jobs, dict):
            candidate_items = raw_jobs.get("jobs") or raw_jobs.get("items") or []
            items = list(candidate_items.values()) if isinstance(candidate_items, dict) else candidate_items
        else:
            items = []
        for job in items:
            if not isinstance(job, dict):
                continue
            job_id = job.get("id") or job.get("job_id") or job.get("jobId") or ""
            jobs_map[job_id] = job.get("name") or job_id
    except Exception:
        jobs_map = {{}}

entries = []
runs_dir = openclaw_home / "cron" / "runs"
if runs_dir.exists():
    for path in glob.glob(str(runs_dir / "*.jsonl")):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    action = item.get("event") or item.get("action")
                    if action != "finished":
                        continue
                    ts_raw = item.get("ts") or item.get("time") or 0
                    try:
                        ts_sort = int(ts_raw)
                    except Exception:
                        ts_sort = 0
                    ts_text = str(ts_raw)
                    if ts_sort > 0:
                        ts_text = datetime.datetime.fromtimestamp(ts_sort / 1000, datetime.UTC).isoformat()
                    summary = str(item.get("summary") or "").strip()
                    if len(summary) > 4000:
                        summary = summary[:4000]
                    job_id = item.get("job_id") or item.get("jobId") or ""
                    entries.append(
                        {{
                            "ts_sort": ts_sort,
                            "ts": ts_text,
                            "delivered": item.get("delivered"),
                            "summary": summary,
                            "job_id": job_id,
                            "job_name": jobs_map.get(job_id, job_id),
                        }}
                    )
        except Exception:
            continue

entries.sort(key=lambda item: int(item.get("ts_sort") or 0), reverse=True)
payload = {{
    "ok": True,
    "server": server,
    "home": str(home),
    "openclaw_home": str(openclaw_home),
    "openclaw_exists": openclaw_home.exists(),
    "repo_path": repo_path,
    "jobs_file": str(jobs_file),
    "jobs_file_exists": jobs_file.exists(),
    "runs_dir": str(runs_dir),
    "runs_dir_exists": runs_dir.exists(),
    "entries": entries[:120],
}}
print(json.dumps(payload, ensure_ascii=False))
""".strip()


def build_remote_remediation_script(server: str, repo_path: str, openclaw_home: str) -> str:
    return f"""
from pathlib import Path
import json
import subprocess

server = {json.dumps(server, ensure_ascii=False)}
repo_path = Path({json.dumps(repo_path, ensure_ascii=False)})
openclaw_home = Path({json.dumps(openclaw_home, ensure_ascii=False)})
ops_target = openclaw_home / "ops"

def clip(text: str, max_lines: int = 20, max_chars: int = 2400) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    lines = value.splitlines()
    clipped = "\\n".join(lines[-max_lines:])
    return clipped[-max_chars:]

steps = []
commands = []
if (repo_path / ".git").exists():
    commands.append(("git_pull", ["git", "-C", str(repo_path), "pull", "--ff-only", "origin", "main"], 300))
commands.append(
    (
        "sync_ops",
        [
            "python3",
            str(repo_path / "scripts/openclaw-ops/sync_openclaw_ops_files.py"),
            "--source-dir",
            str(repo_path / "scripts/openclaw-ops"),
            "--target-ops-dir",
            str(ops_target),
            "--emit-json",
        ],
        1800,
    )
)
commands.append(
    (
        "install_profile",
        [
            "python3",
            str(repo_path / "scripts/openclaw-ops/install_workflow_profile.py"),
            "--profile",
            "core",
            "--install-web-intel-jobs",
            "--openclaw-home",
            str(openclaw_home),
            "--workflow-repo-path",
            str(repo_path),
            "--emit-json",
        ],
        3600,
    )
)

overall_ok = True
for name, cmd, timeout_seconds in commands:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    step_payload = {{
        "step": name,
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode),
        "stdout_tail": clip(stdout),
        "stderr_tail": clip(stderr),
    }}
    steps.append(step_payload)
    if proc.returncode != 0 and name != "git_pull":
        overall_ok = False

payload = {{
    "ok": overall_ok,
    "server": server,
    "repo_path": str(repo_path),
    "openclaw_home": str(openclaw_home),
    "steps": steps,
}}
print(json.dumps(payload, ensure_ascii=False))
""".strip()


def inspect_server(server: str, ssh_config: str, *, timeout_seconds: int) -> dict[str, Any]:
    payload = run_remote_python(server, ssh_config, build_remote_probe_script(server), timeout_seconds=timeout_seconds)
    payload["inspection"] = summarize_entries(list(payload.get("entries") or []))
    return payload


def remediate_server(
    server: str,
    ssh_config: str,
    inspection_payload: dict[str, Any],
    *,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    repo_path = str(inspection_payload.get("repo_path") or "").strip()
    openclaw_home = str(inspection_payload.get("openclaw_home") or "").strip()
    if dry_run:
        return {
            "ok": True,
            "server": server,
            "skipped": True,
            "reason": "dry-run",
            "repo_path": repo_path,
            "openclaw_home": openclaw_home,
        }
    if not repo_path or not openclaw_home:
        return {
            "ok": False,
            "server": server,
            "skipped": True,
            "reason": "missing_repo_or_openclaw_home",
            "repo_path": repo_path,
            "openclaw_home": openclaw_home,
        }
    return run_remote_python(
        server,
        ssh_config,
        build_remote_remediation_script(server, repo_path, openclaw_home),
        timeout_seconds=timeout_seconds,
    )


def build_round_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    current_issue_servers = 0
    historical_only_servers = 0
    fully_quiet_servers = 0
    for result in results:
        after = (result.get("after") or {}).get("inspection") or {}
        latest_bad = int(after.get("latest20_unsuitable_count") or 0)
        historical_only = bool(after.get("historical_only"))
        if latest_bad > 0:
            current_issue_servers += 1
        elif historical_only:
            historical_only_servers += 1
        else:
            fully_quiet_servers += 1
    return {
        "servers_total": len(results),
        "current_issue_servers": current_issue_servers,
        "historical_only_servers": historical_only_servers,
        "fully_quiet_servers": fully_quiet_servers,
    }


def execute_round(
    *,
    round_index: int,
    servers: list[str],
    ssh_config: str,
    inspect_timeout_seconds: int,
    remediate_timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    round_started_at = now_iso()
    results: list[dict[str, Any]] = []
    for server in servers:
        item: dict[str, Any] = {
            "server": server,
            "started_at": now_iso(),
        }
        try:
            before = inspect_server(server, ssh_config, timeout_seconds=inspect_timeout_seconds)
            remediation = remediate_server(
                server,
                ssh_config,
                before,
                timeout_seconds=remediate_timeout_seconds,
                dry_run=dry_run,
            )
            after = inspect_server(server, ssh_config, timeout_seconds=inspect_timeout_seconds)
            item.update(
                {
                    "ok": bool(remediation.get("ok", False)),
                    "before": {
                        key: value for key, value in before.items() if key != "entries"
                    },
                    "remediation": remediation,
                    "after": {
                        key: value for key, value in after.items() if key != "entries"
                    },
                }
            )
        except Exception as exc:
            item.update(
                {
                    "ok": False,
                    "error": str(exc),
                }
            )
        item["finished_at"] = now_iso()
        results.append(item)
    return {
        "round_index": round_index,
        "started_at": round_started_at,
        "finished_at": now_iso(),
        "results": results,
        "summary": build_round_summary(results),
    }


def render_round_line(round_payload: dict[str, Any]) -> str:
    summary = round_payload.get("summary") or {}
    return (
        f"round={round_payload.get('round_index')} "
        f"servers={summary.get('servers_total', 0)} "
        f"current={summary.get('current_issue_servers', 0)} "
        f"historical_only={summary.get('historical_only_servers', 0)} "
        f"quiet={summary.get('fully_quiet_servers', 0)}"
    )


def aggregate_rounds(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    final_summary = rounds[-1]["summary"] if rounds else {}
    return {
        "rounds_completed": len(rounds),
        "final_summary": final_summary,
        "generated_at": now_iso(),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repeat multi-server cron message inspection and remediation")
    parser.add_argument("--ssh-config", default="D:/ssh_keys/ssh_config")
    parser.add_argument("--servers", nargs="*", default=list(DEFAULT_SERVERS))
    parser.add_argument("--total-rounds", type=int, default=DEFAULT_TOTAL_ROUNDS)
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--inspect-timeout-seconds", type=int, default=300)
    parser.add_argument("--remediate-timeout-seconds", type=int, default=4800)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ssh_config = str(Path(args.ssh_config))
    if not Path(ssh_config).exists():
        raise SystemExit(f"ssh_config not found: {ssh_config}")

    run_dir = Path(args.run_dir) if str(args.run_dir).strip() else (
        Path("tmp/server-message-audit-runs") / now_utc().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at = now_utc()
    schedule = compute_round_schedule(
        started_at,
        total_rounds=max(1, int(args.total_rounds)),
        interval_seconds=max(1, int(args.interval_seconds)),
    )
    plan_payload = {
        "started_at": started_at.isoformat(),
        "servers": list(args.servers),
        "ssh_config": ssh_config,
        "total_rounds": len(schedule),
        "interval_seconds": max(1, int(args.interval_seconds)),
        "dry_run": bool(args.dry_run),
        "schedule": [item.isoformat() for item in schedule],
    }
    write_json(run_dir / "plan.json", plan_payload)

    rounds: list[dict[str, Any]] = []
    state_path = run_dir / "state.json"
    for index, scheduled_at in enumerate(schedule, start=1):
        wait_seconds = max(0.0, (scheduled_at - now_utc()).total_seconds())
        if wait_seconds > 0:
            state_payload = {
                "status": "sleeping",
                "next_round_index": index,
                "next_run_at": scheduled_at.isoformat(),
                "completed_rounds": len(rounds),
                "run_dir": str(run_dir.resolve()),
                "updated_at": now_iso(),
            }
            write_json(state_path, state_payload)
            time.sleep(wait_seconds)

        state_payload = {
            "status": "running",
            "current_round_index": index,
            "completed_rounds": len(rounds),
            "run_dir": str(run_dir.resolve()),
            "updated_at": now_iso(),
        }
        write_json(state_path, state_payload)

        round_payload = execute_round(
            round_index=index,
            servers=list(args.servers),
            ssh_config=ssh_config,
            inspect_timeout_seconds=max(30, int(args.inspect_timeout_seconds)),
            remediate_timeout_seconds=max(60, int(args.remediate_timeout_seconds)),
            dry_run=bool(args.dry_run),
        )
        rounds.append(round_payload)
        write_json(run_dir / f"round_{index:02d}.json", round_payload)
        print(render_round_line(round_payload), flush=True)

    summary_payload = aggregate_rounds(rounds)
    write_json(run_dir / "summary.json", summary_payload)
    write_json(
        state_path,
        {
            "status": "completed",
            "completed_rounds": len(rounds),
            "run_dir": str(run_dir.resolve()),
            "updated_at": now_iso(),
            "summary": summary_payload,
        },
    )
    print(json.dumps(summary_payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

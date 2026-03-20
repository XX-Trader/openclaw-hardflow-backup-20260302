#!/usr/bin/env python3
"""Collect and monitor system schedule + OpenClaw schedule snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from utf8_runtime import configure_process_utf8_stdio
from io_write_gateway import FileWriteError, write_json_atomic
from chat_output import build_trace_id, render_chat_notice

configure_process_utf8_stdio()

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
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def normalize_log_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else "silent"


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def policy_enforcer_path() -> Path:
    custom = str(os.environ.get("POLICY_ENFORCER_PY", "")).strip()
    if custom:
        return Path(custom).expanduser()
    return Path(__file__).resolve().parent / "policy" / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized_id = str(task_id or "").strip()
    if not normalized_id or (not db_path.exists()):
        return False
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized_id,)).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def invoke_policy_enforcer(db_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, dict[str, Any], str]:
    script = policy_enforcer_path()
    if not script.exists():
        return False, {}, f"policy_enforcer_missing:{script}"
    cmd = [sys.executable, str(script), "--db", str(db_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return False, {}, f"policy_enforcer_exec_failed:{exc}"

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    if not isinstance(payload, dict):
        return False, {}, "policy_enforcer_invalid_json_output"
    if not bool(payload.get("ok", False)):
        return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
    return True, payload, ""


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "ops-agent").strip() or "ops-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "ops-agent"
    source_name = str(source_module or "ops-agent/system-schedule-audit").strip() or "ops-agent/system-schedule-audit"
    create_args = [
        "create-task",
        "--task-id",
        normalized,
        "--task-type",
        "ops_runtime_cron",
        "--reason",
        f"[CRON_RUNTIME] bind {normalized}",
        "--source",
        source_name,
        "--request-source",
        "ai",
        "--priority",
        "low",
        "--risk-level",
        "low",
        "--pool",
        "jobs",
        "--assignee",
        assignee,
        "--need-human-confirm",
        "false",
        "--human-confirmed",
        "true",
        "--requirement",
        f"Auto register runtime task for {normalized} to bind observability records.",
        "--result-output",
        "Runtime task exists and accepts module/communication/report records.",
        "--acceptance",
        "Task can be used for cron observability binding without manual action.",
        "--observable-outputs",
        "module_logs,module_communications,agent_task_reports,planner_summary",
        "--acceptance-thresholds",
        "At least one runtime observability record is bound to this task.",
        "--scheduled-at",
        now_iso(),
        "--actor",
        actor_name,
    ]
    ok, _payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
    if ok and task_exists_in_db(db_path, normalized):
        return normalized, ""
    return "", (err or f"auto_register_task_failed:{normalized}")


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

    openclaw = snapshot.get("openclaw", {})
    output = render_chat_notice(
        "系统定时巡检提醒",
        status="需关注",
        task_id=task_id,
        sender_identity=sender_identity,
        run_time=now_iso(),
        trace_id=build_trace_id(report_file=snapshot_file),
        summary=(
            f"检测到 {len(risk_reasons)} 个高风险项"
            if risk_reasons
            else f"检测到 {len(change_reasons)} 个配置变更"
        ),
        extra_lines=[
            f"通知模式：{normal_log_mode}",
            f"OpenClaw 定时任务：{int(openclaw.get('job_count', 0) or 0)} 个",
            f"用户 crontab 条目：{len(snapshot.get('user_crontab', {}).get('lines', []))}",
            f"root crontab 条目：{len(snapshot.get('root_crontab', {}).get('lines', []))}",
            f"/etc/cron.d 文件：{len(snapshot.get('cron_d', {}).get('list', []))}",
            f"systemd 定时器：{len(snapshot.get('systemd_timers', {}).get('units', []))}",
        ],
        next_step="如需排查，请按留痕编号查看系统定时快照和差异记录。",
    )
    return True, output


def main() -> int:
    run_started_at = datetime.now(TZ)
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="System/OpenClaw schedule snapshot monitor")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
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
    run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
    result["run_duration_ms"] = run_duration_ms

    policy_db_path = Path(args.db).expanduser()
    policy_observability: dict[str, Any] = {"enabled": False, "db": str(policy_db_path), "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    if policy_db_path.exists():
        policy_observability["enabled"] = True
        raw_task_id = str(args.task_id or "").strip()
        bound_task_id = ""
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                policy_db_path,
                raw_task_id,
                "ops-agent",
                "ops-agent/system-schedule-audit",
            )
            policy_observability["task_bound"] = bool(bound_task_id)
            if (not bound_task_id) and bind_err:
                policy_observability["errors"].append(bind_err)

        risk_reasons = [str(x).strip() for x in compare.get("risk_reasons", []) if str(x).strip()]
        change_reasons = [str(x).strip() for x in compare.get("change_reasons", []) if str(x).strip()]
        module_args = [
            "log-module",
            "--module-name",
            "ops-agent/system-schedule-audit",
            "--phase",
            "snapshot",
            "--level",
            ("error" if risk_reasons else "info"),
            "--status",
            ("failed" if risk_reasons else "passed"),
            "--message",
            (
                "system schedule snapshot collected: "
                + f"risk={len(risk_reasons)} change={len(change_reasons)} notify={bool(result.get('notify'))}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "snapshot_file": str(snapshot_file),
                    "state_file": str(state_file),
                    "risk_reasons": risk_reasons,
                    "change_reasons": change_reasons,
                    "notify": bool(result.get("notify")),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(policy_db_path, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if (not ok_module) and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "ops-agent/system-schedule-audit",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "system_schedule_snapshot",
            "--status",
            ("failed" if risk_reasons else "acked"),
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(snapshot_file.stem),
            "--payload-ref",
            str(snapshot_file),
            "--details-json",
            json.dumps({"state_file": str(state_file), "notify": bool(result.get("notify"))}, ensure_ascii=False),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(policy_db_path, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if (not ok_comm) and err_comm:
            policy_observability["errors"].append(err_comm)

        if bound_task_id:
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "ops-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("failed" if risk_reasons else "passed"),
                "--solved",
                ("false" if risk_reasons else "true"),
                "--resolved-issues",
                "system_schedule_snapshot",
                "--resolution-summary",
                (
                    "system schedule snapshot completed"
                    if not risk_reasons
                    else "system schedule snapshot detected risk items"
                ),
                "--resolution-steps",
                "collect_snapshot,compare,save_state,build_output",
                "--failed-items",
                ",".join(risk_reasons[:20]),
                "--failure-count",
                str(len(risk_reasons)),
                "--duration-ms",
                str(run_duration_ms),
                "--input-tokens",
                "0",
                "--output-tokens",
                "0",
                "--cost-estimate",
                "0",
                "--quality-score",
                str(75.0 if risk_reasons else 92.0),
                "--quality-grade",
                ("c" if risk_reasons else "a"),
                "--notify-chat",
                ("true" if risk_reasons else "false"),
                "--details-json",
                json.dumps(
                    {
                        "snapshot_file": str(snapshot_file),
                        "state_file": str(state_file),
                        "risk_reasons": risk_reasons,
                        "change_reasons": change_reasons,
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "ops-agent",
            ]
            ok_report, payload_report, err_report = invoke_policy_enforcer(policy_db_path, report_args, timeout=35)
            policy_observability["report_agent_result_ok"] = ok_report
            if ok_report and isinstance(payload_report, dict):
                result_payload = payload_report.get("result")
                if isinstance(result_payload, dict):
                    planner_payload = result_payload.get("planner_payload")
                    if isinstance(planner_payload, dict):
                        policy_observability["agent_report"] = {
                            "report_status": planner_payload.get("report_status"),
                            "notify_chat": planner_payload.get("notify_chat"),
                            "failure_count": planner_payload.get("failure_count"),
                        }
            if (not ok_report) and err_report:
                policy_observability["errors"].append(err_report)

        since_24h = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            policy_db_path,
            ["planner-summary", "--planner-id", "coordinator", "--since", since_24h, "--limit", "80"],
            timeout=30,
        )
        policy_observability["planner_summary_ok"] = ok_summary
        if ok_summary and isinstance(payload_summary, dict):
            summary = payload_summary.get("summary")
            if isinstance(summary, dict):
                planner_summary_snapshot = {
                    "planner_id": summary.get("planner_id"),
                    "report_count": summary.get("report_count", 0),
                    "task_count": summary.get("task_count", 0),
                    "resolved_task_count": summary.get("resolved_task_count", 0),
                    "failed_task_count": summary.get("failed_task_count", 0),
                    "solved_ratio_pct": summary.get("solved_ratio_pct", 0.0),
                    "total_tokens": summary.get("total_tokens", 0),
                    "total_cost_estimate": summary.get("total_cost_estimate", 0.0),
                }
        if (not ok_summary) and err_summary:
            policy_observability["errors"].append(err_summary)

    exception_reasons = [str(x).strip() for x in policy_observability.get("errors", []) if str(x).strip()]
    notify = bool(result.get("notify") or exception_reasons)
    output = str(result.get("output", "NO_REPLY"))
    if planner_summary_snapshot and notify:
        summary_line = (
            "近24小时处理："
            f"报告 {int(planner_summary_snapshot.get('report_count', 0) or 0)} 条，"
            f"已解决 {int(planner_summary_snapshot.get('resolved_task_count', 0) or 0)} 项，"
            f"失败 {int(planner_summary_snapshot.get('failed_task_count', 0) or 0)} 项。"
        )
        if output == "NO_REPLY":
            output = render_chat_notice(
                "系统定时巡检提醒",
                status="需关注",
                task_id=str(args.task_id or ""),
                sender_identity=sender_identity,
                run_time=now_iso(),
                summary="系统定时巡检发现需要关注的变化。",
                extra_lines=[summary_line],
                next_step="如需排查，请按留痕编号查看系统定时快照。",
            )
        else:
            output = f"{output}\n- {summary_line}"
    if exception_reasons:
        if output == "NO_REPLY":
            output = render_chat_notice(
                "系统定时巡检异常",
                status="需处理",
                task_id=str(args.task_id or ""),
                sender_identity=sender_identity,
                run_time=now_iso(),
                summary=f"系统定时巡检运行时发现 {len(exception_reasons)} 个异常。",
                next_step="请按留痕编号查看内部错误记录。",
            )
        else:
            output = f"{output}\n- 运行异常：{len(exception_reasons)} 项。"
    if not notify:
        output = "NO_REPLY"

    result["notify"] = notify
    result["output"] = output
    result["policy_observability"] = policy_observability
    result["planner_summary"] = planner_summary_snapshot
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

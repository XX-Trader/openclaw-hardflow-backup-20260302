#!/usr/bin/env python3
"""Stable experience maintenance runner for daily/weekly/monthly cron jobs."""

from __future__ import annotations

import argparse
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

from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
MODES = {"daily", "weekly", "monthly"}
DEFAULT_SENDER_IDENTITY = "optimization-agent/experience-maintain"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


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

    actor_name = str(actor or "optimization-agent").strip() or "optimization-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "optimization-agent"
    source_name = (
        str(source_module or "optimization-agent/experience-maintain").strip()
        or "optimization-agent/experience-maintain"
    )
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


def ensure_memory_files(workspace: Path) -> list[str]:
    actions: list[str] = []
    workspace_new = not workspace.exists()
    workspace.mkdir(parents=True, exist_ok=True)
    if workspace_new:
        actions.append(f"create_dir:{workspace}")
    memory_dir = workspace / "memory"
    memory_dir_new = not memory_dir.exists()
    memory_dir.mkdir(parents=True, exist_ok=True)
    if memory_dir_new:
        actions.append(f"create_dir:{memory_dir}")

    memory_md = workspace / "MEMORY.md"
    if not memory_md.exists():
        atomic_write_text(
            memory_md,
            "# MEMORY.md\n\n"
            "## Purpose\n"
            "- Keep durable context for recurring tasks and operational decisions.\n\n"
            "## Policy\n"
            "- Prefer concise records in memory/YYYY-MM-DD.md.\n"
            "- Keep only actionable conclusions and verified outcomes.\n",
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
        actions.append(f"create_file:{memory_md}")

    today_md = memory_dir / f"{now().strftime('%Y-%m-%d')}.md"
    if not today_md.exists():
        atomic_write_text(
            today_md,
            f"# {now().strftime('%Y-%m-%d')} 缁存姢璁板綍\n\n",
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
        actions.append(f"create_file:{today_md}")
    return actions


def default_state() -> dict[str, Any]:
    return {
        "updated_at": "",
        "last_run_by_mode": {},
        "last_report_file": "",
    }


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Experience maintenance runner")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--mode", default="daily", choices=sorted(MODES))
    parser.add_argument("--workspace", default=str(home / ".openclaw/workspace"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/experience-maintain/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/experience-maintain/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    mode = str(args.mode).strip().lower()
    if mode not in MODES:
        raise SystemExit(f"invalid mode: {mode}")

    workspace = Path(args.workspace).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    actions: list[str] = []
    run_errors: list[str] = []
    ok = True
    try:
        actions = ensure_memory_files(workspace)
    except Exception as exc:
        ok = False
        run_errors.append(f"ensure_memory_files_failed:{exc}")
    run_id = uuid.uuid4().hex[:12]
    report = {
        "run_id": run_id,
        "time": now_iso(),
        "mode": mode,
        "sender_identity": str(args.sender_identity or DEFAULT_SENDER_IDENTITY).strip() or DEFAULT_SENDER_IDENTITY,
        "task_id": str(args.task_id or ""),
        "workspace": str(workspace),
        "actions": actions,
        "ok": ok,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "cost_estimate": 0.0,
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{mode}_{run_id}.json"
    save_json(report_file, report)

    last_runs = state.get("last_run_by_mode")
    if not isinstance(last_runs, dict):
        last_runs = {}
    last_runs[mode] = {
        "time": now_iso(),
        "run_id": run_id,
        "report_file": str(report_file),
    }
    state["last_run_by_mode"] = last_runs
    state["updated_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    # Only announce when there are concrete maintenance actions.
    notify = bool(actions)
    output = "NO_REPLY"
    if notify:
        output = (
            f"# experience-maintain {mode}\n"
            f"- sender_identity: {report['sender_identity']}\n"
            f"- task: {args.task_id or '-'}\n"
            f"- time: {report['time']}\n"
            f"- normal_log_mode: {normal_log_mode}\n"
            f"- actions: {len(actions)}\n"
            f"- evidence: {report_file}"
        )

    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms
    report["normal_log_mode"] = normal_log_mode
    report["notify"] = notify

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
                "optimization-agent",
                "optimization-agent/experience-maintain",
            )
            policy_observability["task_bound"] = bool(bound_task_id)
            if (not bound_task_id) and bind_err:
                policy_observability["errors"].append(bind_err)

        module_args = [
            "log-module",
            "--module-name",
            "optimization-agent/experience-maintain",
            "--phase",
            mode,
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            f"experience maintain {mode} finished: actions={len(actions)}",
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "run_id": run_id,
                    "actions_count": len(actions),
                    "run_error_count": len(run_errors),
                    "report_file": str(report_file),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "optimization-agent",
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
            "optimization-agent/experience-maintain",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "experience_maintain",
            "--status",
            ("failed" if run_errors else "acked"),
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(run_id),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps({"mode": mode, "notify": bool(notify), "actions_count": len(actions)}, ensure_ascii=False),
            "--actor",
            "optimization-agent",
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
                "optimization-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("failed" if run_errors else "passed"),
                "--solved",
                ("false" if run_errors else "true"),
                "--resolved-issues",
                "experience_maintenance_completed",
                "--resolution-summary",
                (
                    f"experience maintain {mode} finished"
                    if not run_errors
                    else f"experience maintain {mode} finished with runtime errors"
                ),
                "--resolution-steps",
                "ensure_workspace,ensure_memory_files,update_state",
                "--failed-items",
                ",".join(str(x) for x in run_errors[:20]),
                "--failure-count",
                str(len(run_errors)),
                "--duration-ms",
                str(run_duration_ms),
                "--input-tokens",
                "0",
                "--output-tokens",
                "0",
                "--cost-estimate",
                "0",
                "--quality-score",
                str(72.0 if run_errors else 90.0),
                "--quality-grade",
                ("c" if run_errors else "a"),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps({"mode": mode, "actions_count": len(actions), "report_file": str(report_file)}, ensure_ascii=False),
                "--actor",
                "optimization-agent",
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

        since_24h = (now().astimezone(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
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

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    exception_reasons.extend(str(x).strip() for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(actions or exception_reasons)
    if planner_summary_snapshot and notify:
        summary_line = (
            f"- planner_summary: reports={planner_summary_snapshot.get('report_count', 0)}, "
            f"resolved={planner_summary_snapshot.get('resolved_task_count', 0)}, "
            f"failed={planner_summary_snapshot.get('failed_task_count', 0)}, "
            f"tokens={planner_summary_snapshot.get('total_tokens', 0)}"
        )
        if output == "NO_REPLY":
            output = "\n".join(
                [
                    f"# experience-maintain {mode}",
                    f"- sender_identity: {report['sender_identity']}",
                    f"- task: {args.task_id or '-'}",
                    f"- time: {report['time']}",
                    summary_line,
                ]
            )
        else:
            output = f"{output}\n{summary_line}"
    if exception_reasons:
        if output == "NO_REPLY":
            output = "\n".join(
                [
                    f"# experience-maintain {mode} exception",
                    f"- sender_identity: {report['sender_identity']}",
                    f"- task: {args.task_id or '-'}",
                    f"- time: {report['time']}",
                    f"- exception_count: {len(exception_reasons)}",
                ]
            )
        else:
            output = f"{output}\n- exception_count: {len(exception_reasons)}"
        for reason in exception_reasons[:12]:
            output = f"{output}\n- exception: {reason}"
    if not notify:
        output = "NO_REPLY"

    report["notify"] = notify
    report["run_errors"] = run_errors
    report["policy_observability"] = policy_observability
    report["planner_summary"] = planner_summary_snapshot
    save_json(report_file, report)

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(f"{output}\n- evidence: {report_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


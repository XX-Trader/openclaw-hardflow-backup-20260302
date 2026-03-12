#!/usr/bin/env python3
"""Daily TODO/DONE digest (no external push, only chat output)."""

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

from io_write_gateway import FileWriteError, write_json_atomic
from chat_output import build_trace_id, render_chat_notice, strip_list_marker

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "ops-agent/daily-todo-digest"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


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
    source_name = str(source_module or "ops-agent/daily-todo-digest").strip() or "ops-agent/daily-todo-digest"
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


def default_state() -> dict[str, Any]:
    return {
        "updated_at": "",
        "sent_todo_ids": [],
        "sent_done_ids": [],
        "last_report_file": "",
    }


def is_today_local(iso_text: str) -> bool:
    text = str(iso_text or "").strip()
    if not text:
        return False
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        dt = dt.astimezone(TZ)
        return dt.date() == now().date()
    except Exception:
        return False


def load_tasks(db_path: Path, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = conn.execute(
            """
            SELECT task_id, task_type, reason, priority, risk_level, assignee, status, scheduled_at, created_at, updated_at
            FROM tasks
            ORDER BY
              CASE
                WHEN LOWER(status) IN ('pending', 'running', 'failed', 'escalated') THEN
                  CASE
                    WHEN scheduled_at IS NULL OR TRIM(scheduled_at) = '' OR scheduled_at <= ? THEN 0
                    ELSE 1
                  END
                ELSE 2
              END ASC,
              COALESCE(NULLIF(TRIM(scheduled_at), ''), created_at) ASC,
              updated_at DESC
            LIMIT ?
            """,
            (now_utc_iso, max(1, int(limit))),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def is_runtime_binding_task(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if str(item.get("task_type", "")).strip().lower() == "ops_runtime_cron":
        return True
    return str(item.get("reason", "")).strip().startswith("[CRON_RUNTIME] bind ")


def summarize_items(items: list[dict[str, Any]], limit: int) -> list[str]:
    lines: list[str] = []
    for row in items[: max(1, int(limit))]:
        lines.append(
            "- "
            + f"[{row.get('task_id')}] "
            + f"{str(row.get('reason') or '')[:70]} "
            + f"(priority={row.get('priority')}, risk={row.get('risk_level')}, assignee={row.get('assignee')})"
        )
    return lines


def build_chat_output(
    *,
    sender_identity: str,
    task_id: str,
    run_time: str,
    run_id: str,
    new_todo: list[dict[str, Any]],
    new_done: list[dict[str, Any]],
    planner_summary: dict[str, Any] | None,
    exception_reasons: list[str],
    max_notify_items: int,
) -> str:
    has_updates = bool(new_todo or new_done)
    has_exceptions = bool(exception_reasons)
    if (not has_updates) and (not has_exceptions):
        return "NO_REPLY"

    title = "每日任务摘要" if has_updates else "每日任务摘要异常"
    status = "有更新" if has_updates and (not has_exceptions) else "需关注"
    summary_parts: list[str] = []
    if has_updates:
        summary_parts.append(f"新增待办 {len(new_todo)} 项")
        summary_parts.append(f"新增完成 {len(new_done)} 项")
    if has_exceptions:
        summary_parts.append(f"发现 {len(exception_reasons)} 个运行异常")

    extra_lines: list[str] = []
    if has_updates:
        extra_lines.append(f"新增待办：{len(new_todo)} 项")
        extra_lines.append(f"新增完成：{len(new_done)} 项")
    if isinstance(planner_summary, dict) and planner_summary:
        extra_lines.append(
            "近24小时处理："
            f"任务 {int(planner_summary.get('task_count', 0) or 0)} 项，"
            f"已解决 {int(planner_summary.get('resolved_task_count', 0) or 0)} 项，"
            f"失败 {int(planner_summary.get('failed_task_count', 0) or 0)} 项。"
        )

    detail_lines: list[str] = []
    for idx, text in enumerate(summarize_items(new_todo, int(max_notify_items)), start=1):
        detail_lines.append(f"待办{idx}：{strip_list_marker(text)}")
    for idx, text in enumerate(summarize_items(new_done, int(max_notify_items)), start=1):
        detail_lines.append(f"完成{idx}：{strip_list_marker(text)}")
    if has_exceptions:
        detail_lines.append("运行详情已写入内部留痕，不再在群聊中展示底层文件路径。")

    return render_chat_notice(
        title,
        status=status,
        task_id=str(task_id or "").strip(),
        sender_identity=str(sender_identity or DEFAULT_SENDER_IDENTITY).strip(),
        run_time=str(run_time or now_iso()).strip(),
        trace_id=build_trace_id(run_id=run_id),
        summary="；".join(summary_parts),
        details=detail_lines,
        extra_lines=extra_lines,
        next_step=(
            "如需排查，请按留痕编号查看内部报告。"
            if has_exceptions
            else "如需跟进，请按任务编号进入任务中心处理。"
        ),
    )


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Daily TODO digest")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/daily-todo-digest/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/daily-todo-digest/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--max-db-tasks", type=int, default=2000)
    parser.add_argument("--max-notify-items", type=int, default=15)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    tasks = load_tasks(db_path, limit=int(args.max_db_tasks))
    sent_todo_ids = {str(x) for x in state.get("sent_todo_ids", [])}
    sent_done_ids = {str(x) for x in state.get("sent_done_ids", [])}

    unresolved_statuses = {"pending", "running", "failed", "escalated"}
    todo_candidates = [
        x
        for x in tasks
        if str(x.get("status", "")).lower() in unresolved_statuses and not is_runtime_binding_task(x)
    ]
    done_candidates = [
        x
        for x in tasks
        if str(x.get("status", "")).lower() == "passed"
        and is_today_local(x.get("updated_at", ""))
        and not is_runtime_binding_task(x)
    ]

    new_todo = [x for x in todo_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_todo_ids]
    new_done = [x for x in done_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_done_ids]

    sender_identity = normalize_sender_identity(args.sender_identity)
    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    run_errors: list[str] = []
    notify = bool(new_todo or new_done)
    output = "NO_REPLY"

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "normal_log_mode": normal_log_mode,
        "notify": notify,
        "db": str(db_path),
        "new_todo_count": len(new_todo),
        "new_done_count": len(new_done),
        "new_todo_ids": [str(x.get("task_id", "")) for x in new_todo if x.get("task_id")],
        "new_done_ids": [str(x.get("task_id", "")) for x in new_done if x.get("task_id")],
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "cost_estimate": 0.0,
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
    report["run_duration_ms"] = run_duration_ms
    report["observability_window_since"] = since_24h

    planner_summary_snapshot: dict[str, Any] = {}
    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    if db_path.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_path)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_path,
                raw_task_id,
                "ops-agent",
                "ops-agent/daily-todo-digest",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            db_path,
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

        module_args = [
            "log-module",
            "--module-name",
            "ops-agent/daily-todo-digest",
            "--phase",
            "daily_digest",
            "--level",
            "info",
            "--status",
            "passed",
            "--message",
            f"daily todo digest generated: new_todo={len(new_todo)} new_done={len(new_done)}",
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "notify": bool(notify),
                    "new_todo_count": len(new_todo),
                    "new_done_count": len(new_done),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(db_path, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "ops-agent/daily-todo-digest",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "daily_todo_digest",
            "--status",
            "acked",
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(report.get("run_id", "")),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps(
                {
                    "new_todo_count": len(new_todo),
                    "new_done_count": len(new_done),
                    "scheduled_priority_order_enabled": True,
                },
                ensure_ascii=False,
            ),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_path, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        if bound_task_id:
            report_status = "failed" if run_errors else "passed"
            quality_score = 70.0 if run_errors else 90.0
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "ops-agent",
                "--planner-id",
                "coordinator",
                "--status",
                report_status,
                "--solved",
                ("false" if run_errors else "true"),
                "--resolved-issues",
                "daily_todo_digest",
                "--resolution-summary",
                (
                    "daily todo digest generated"
                    if not run_errors
                    else "daily todo digest generated with runtime exceptions"
                ),
                "--resolution-steps",
                "load_tasks,order_by_schedule,build_digest,record_state",
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
                str(round(float(quality_score), 2)),
                "--quality-grade",
                ("c" if run_errors else "a"),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "report_file": str(report_file),
                        "new_todo_count": len(new_todo),
                        "new_done_count": len(new_done),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "ops-agent",
            ]
            ok_report, payload_report, err_report = invoke_policy_enforcer(db_path, report_args, timeout=35)
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

    report["planner_summary"] = planner_summary_snapshot
    report["policy_observability"] = policy_observability
    save_json(report_file, report)

    state["updated_at"] = now_iso()
    if notify:
        state["sent_todo_ids"] = sorted(set(sent_todo_ids).union(report["new_todo_ids"]))
        state["sent_done_ids"] = sorted(set(sent_done_ids).union(report["new_done_ids"]))
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(new_todo or new_done or exception_reasons)
    report["notify"] = notify
    report["run_errors"] = run_errors
    save_json(report_file, report)

    output = build_chat_output(
        sender_identity=sender_identity,
        task_id=str(args.task_id or ""),
        run_time=now_iso(),
        run_id=str(report.get("run_id", "")),
        new_todo=new_todo,
        new_done=new_done,
        planner_summary=planner_summary_snapshot,
        exception_reasons=exception_reasons[:12],
        max_notify_items=int(args.max_notify_items),
    )

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(output)
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

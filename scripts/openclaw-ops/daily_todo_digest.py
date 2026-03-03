#!/usr/bin/env python3
"""Daily TODO/DONE digest (no external push, only chat output)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
        rows = conn.execute(
            """
            SELECT task_id, reason, priority, risk_level, assignee, status, created_at, updated_at
            FROM tasks
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


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


def main() -> int:
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
    todo_candidates = [x for x in tasks if str(x.get("status", "")).lower() in unresolved_statuses]
    done_candidates = [
        x for x in tasks if str(x.get("status", "")).lower() == "passed" and is_today_local(x.get("updated_at", ""))
    ]

    new_todo = [x for x in todo_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_todo_ids]
    new_done = [x for x in done_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_done_ids]

    sender_identity = normalize_sender_identity(args.sender_identity)
    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    notify = bool(new_todo or new_done)
    output = "NO_REPLY"
    if notify:
        lines = [
            f"# Daily TODO Digest {now().strftime('%Y-%m-%d')}",
            f"- sender_identity: {sender_identity}",
            f"- task: {args.task_id or '-'}",
            f"- time: {now_iso()}",
            f"- new_todo: {len(new_todo)}",
            f"- new_done: {len(new_done)}",
            "",
            "## TODO (new)",
            *(summarize_items(new_todo, int(args.max_notify_items)) or ["- (none)"]),
            "",
            "## DONE (new)",
            *(summarize_items(new_done, int(args.max_notify_items)) or ["- (none)"]),
        ]
        output = "\n".join(lines)
    elif normal_log_mode == "chat":
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
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    save_json(report_file, report)

    state["updated_at"] = now_iso()
    if notify:
        state["sent_todo_ids"] = sorted(set(sent_todo_ids).union(report["new_todo_ids"]))
        state["sent_done_ids"] = sorted(set(sent_done_ids).union(report["new_done_ids"]))
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

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


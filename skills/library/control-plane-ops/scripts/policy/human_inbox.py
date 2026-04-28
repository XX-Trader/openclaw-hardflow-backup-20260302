#!/usr/bin/env python3
"""Human action inbox for Task Center confirmation, clarification, and escalations."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


POLICY_DIR = Path(__file__).resolve().parent
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from task_center import TaskCenter, TaskCenterError, parse_json  # noqa: E402
from policy_route_selection import (  # noqa: E402
    NON_PIPELINE_ROUTE_ACTIONS,
    PIPELINE_ROUTE_CHOICES,
    VALID_ROUTE_CHOICES,
    route_choice_action,
)


VALID_CONFIRM_CHOICES = set(VALID_ROUTE_CHOICES) | {"recommended"}


def default_task_db() -> Path:
    runtime_home = (
        os.environ.get("HARDFLOW_RUNTIME_HOME")
        or os.environ.get("OPENCLAW_HOME")
        or os.environ.get("HERMES_HOME")
        or str(Path.home() / ".hardflow-runtime")
    )
    return Path(runtime_home).expanduser() / "ops" / "task-center" / "task_center.db"


def _decode_task(center: TaskCenter, row: Any) -> dict[str, Any]:
    return center._deserialize_task_row(row)  # Existing TaskCenter row deserializer keeps field formats consistent.


def task_reasons(task: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if bool(task.get("need_human_confirm")) and not bool(task.get("human_confirmed")):
        reasons.append("waiting_confirm")
    if bool(task.get("needs_clarification")):
        reasons.append("needs_clarification")
    if str(task.get("status") or "").lower() == "escalated":
        reasons.append("escalated")
    if str(task.get("action") or "").lower() == "escalate_human":
        reasons.append("escalate_human")
    context = task.get("context_payload")
    if isinstance(context, str):
        context = parse_json(context)
    if isinstance(context, dict) and bool(context.get("requires_human_assistance")):
        reasons.append("requires_human_assistance")
    return sorted(set(reasons))


def list_inbox(task_db: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    center = TaskCenter(task_db)
    try:
        center.init_schema()
        rows = center.conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE
                (need_human_confirm = 1 AND human_confirmed = 0)
                OR needs_clarification = 1
                OR status = 'escalated'
                OR action = 'escalate_human'
            ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 50), 500)),),
        ).fetchall()
        tasks = [_decode_task(center, row) for row in rows]
    finally:
        center.close()
    return [{**task, "human_inbox_reasons": task_reasons(task)} for task in tasks]


def format_inbox(tasks: list[dict[str, Any]], *, task_db: Path) -> str:
    if not tasks:
        return "NO_REPLY"
    lines = [f"HUMAN_INBOX items={len(tasks)}"]
    command = "python3 ${HARDFLOW_RUNTIME_HOME:-$HOME/.hardflow-runtime}/ops/policy/human_inbox.py"
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        reasons = ",".join(task.get("human_inbox_reasons") or [])
        lines.append(
            f"- [{reasons}] {task_id} priority={task.get('priority')} status={task.get('status')} "
            f"assignee={task.get('assignee') or ''}"
        )
        lines.append(f"  reason: {str(task.get('reason') or '')[:180]}")
        if "waiting_confirm" in task.get("human_inbox_reasons", []):
            lines.append(f"  confirm: {command} confirm --task-db {task_db} --task-id {task_id}")
            lines.append(f"  decline: {command} decline --task-db {task_db} --task-id {task_id}")
        if "needs_clarification" in task.get("human_inbox_reasons", []):
            lines.append(f"  clarify: {command} clarify --task-db {task_db} --task-id {task_id} --note '<answer>'")
    return "\n".join(lines)


def _task_context(task: dict[str, Any]) -> dict[str, Any]:
    context = task.get("context_payload")
    if isinstance(context, str):
        context = parse_json(context)
    return context if isinstance(context, dict) else {}


def _resolve_route_choice(task: dict[str, Any], route_choice: str) -> tuple[str, str]:
    context = _task_context(task)
    route_selection = context.get("route_selection")
    if not isinstance(route_selection, dict):
        route_selection = {}
    raw_choice = str(route_choice or "").strip().lower() or "recommended"
    if raw_choice not in VALID_CONFIRM_CHOICES:
        raise TaskCenterError(
            "route_choice must be one of: " + ", ".join(sorted(VALID_CONFIRM_CHOICES))
        )
    recommended = str(route_selection.get("recommended_route") or "coding_workflow").strip().lower()
    selected = recommended if raw_choice == "recommended" else raw_choice
    if selected not in VALID_ROUTE_CHOICES:
        selected = "coding_workflow"
    return selected, route_choice_action(selected)


def confirm_task(
    task_db: Path,
    task_id: str,
    *,
    actor: str,
    assignee: str = "",
    route_choice: str = "recommended",
) -> dict[str, Any]:
    center = TaskCenter(task_db)
    try:
        center.init_schema()
        task = center.get_task(task_id, display_safe=False)
        selected_route, action = _resolve_route_choice(task, route_choice)
        context = _task_context(task)
        route_selection = context.get("route_selection")
        if not isinstance(route_selection, dict):
            route_selection = {}
        route_selection.update(
            {
                "selected_route": selected_route,
                "selection_actor": actor,
                "selection_source": "human_inbox",
            }
        )
        context["route_selection"] = route_selection
        normalized_assignee = str(assignee or "").strip()
        if selected_route == "specified_agent" and not normalized_assignee:
            raise TaskCenterError("specified_agent route requires --assignee <agent-id>")
        if not normalized_assignee:
            if selected_route == "requirement_discussion":
                normalized_assignee = "project-agent"
            elif selected_route in PIPELINE_ROUTE_CHOICES:
                normalized_assignee = "coordinator"
        center.confirm_human(task_id=task_id, actor=actor, confirmed=True)
        updates: dict[str, Any] = {
            "action": action,
            "context_payload": context,
        }
        if normalized_assignee:
            updates["assignee"] = normalized_assignee
        updated = center.update_task(task_id, actor=actor, fields=updates)
        center.record_task_output(
            task_id=task_id,
            output_type="human_decision",
            audience="machine",
            channel="human_inbox",
            status="prepared",
            summary=f"Human selected route: {selected_route}.",
            payload={"decision": "confirm", "route_choice": route_choice, "selected_route": selected_route, "assignee": normalized_assignee},
            actor=actor,
        )
        return updated
    finally:
        center.close()


def decline_task(task_db: Path, task_id: str, *, actor: str, note: str = "") -> dict[str, Any]:
    center = TaskCenter(task_db)
    try:
        center.init_schema()
        center.confirm_human(task_id=task_id, actor=actor, confirmed=False)
        center.update_task(task_id, actor=actor, fields={"action": "declined_by_human"})
        center.record_task_output(
            task_id=task_id,
            output_type="human_decision",
            audience="machine",
            channel="human_inbox",
            status="prepared",
            summary="Human declined task execution.",
            payload={"decision": "decline", "note": note},
            actor=actor,
        )
        return center.transition_status(
            task_id=task_id,
            new_status="cancelled",
            actor=actor,
            stage="human_inbox",
            details={"decision": "decline", "note": note},
        )
    finally:
        center.close()


def clarify_task(task_db: Path, task_id: str, *, actor: str, note: str) -> dict[str, Any]:
    center = TaskCenter(task_db)
    try:
        center.init_schema()
        task = center.get_task(task_id, display_safe=False)
        context = task.get("context_payload")
        if not isinstance(context, dict):
            context = {}
        notes = list(context.get("human_clarification_notes") or [])
        notes.append({"actor": actor, "note": note})
        context["human_clarification_notes"] = notes
        updated = center.update_task(
            task_id,
            actor=actor,
            fields={
                "needs_clarification": False,
                "clarification_reason": "",
                "context_payload": context,
                "action": "clarified_for_execution",
            },
        )
        center.record_task_output(
            task_id=task_id,
            output_type="human_clarification",
            audience="machine",
            channel="human_inbox",
            status="prepared",
            summary="Human clarification added.",
            payload={"note": note},
            actor=actor,
        )
        return updated
    finally:
        center.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task Center human inbox.")
    parser.add_argument("--task-db", default=str(default_task_db()))
    parser.add_argument("--actor", default="human")
    parser.add_argument("--emit-json", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--task-db", default=str(default_task_db()))
    list_parser.add_argument("--actor", default="human")
    list_parser.add_argument("--emit-json", action="store_true")
    list_parser.add_argument("--limit", type=int, default=50)

    confirm_parser = subparsers.add_parser("confirm")
    confirm_parser.add_argument("--task-db", default=str(default_task_db()))
    confirm_parser.add_argument("--actor", default="human")
    confirm_parser.add_argument("--emit-json", action="store_true")
    confirm_parser.add_argument("--task-id", required=True)
    confirm_parser.add_argument("--assignee", default="")
    confirm_parser.add_argument(
        "--route-choice",
        default="recommended",
        choices=sorted(VALID_CONFIRM_CHOICES),
        help="manual execution route selected by the human",
    )

    decline_parser = subparsers.add_parser("decline")
    decline_parser.add_argument("--task-db", default=str(default_task_db()))
    decline_parser.add_argument("--actor", default="human")
    decline_parser.add_argument("--emit-json", action="store_true")
    decline_parser.add_argument("--task-id", required=True)
    decline_parser.add_argument("--note", default="")

    clarify_parser = subparsers.add_parser("clarify")
    clarify_parser.add_argument("--task-db", default=str(default_task_db()))
    clarify_parser.add_argument("--actor", default="human")
    clarify_parser.add_argument("--emit-json", action="store_true")
    clarify_parser.add_argument("--task-id", required=True)
    clarify_parser.add_argument("--note", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = args.command or "list"
    task_db = Path(args.task_db).expanduser().resolve()
    try:
        if command == "list":
            result: Any = list_inbox(task_db, limit=int(getattr(args, "limit", 50)))
            if args.emit_json:
                print(json.dumps({"items": result}, ensure_ascii=False, indent=2, default=str))
            else:
                print(format_inbox(result, task_db=task_db))
            return 0
        if command == "confirm":
            result = confirm_task(
                task_db,
                str(args.task_id),
                actor=str(args.actor),
                assignee=str(args.assignee or ""),
                route_choice=str(getattr(args, "route_choice", "recommended") or "recommended"),
            )
        elif command == "decline":
            result = decline_task(task_db, str(args.task_id), actor=str(args.actor), note=str(args.note or ""))
        elif command == "clarify":
            result = clarify_task(task_db, str(args.task_id), actor=str(args.actor), note=str(args.note or ""))
        else:
            raise TaskCenterError(f"unknown command: {command}")
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"FAILED human_inbox: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{command}_ok task_id={result.get('task_id')} status={result.get('status')} action={result.get('action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

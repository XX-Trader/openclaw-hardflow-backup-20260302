#!/usr/bin/env python3
"""Create Task Center candidates for due TODO lines with risk-aware routing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_RUNTIME_HOME = (
    os.environ.get("HARDFLOW_RUNTIME_HOME")
    or os.environ.get("OPENCLAW_HOME")
    or os.environ.get("HERMES_HOME")
    or str(Path.home() / ".hardflow-runtime")
)
RUNTIME_HOME = Path(DEFAULT_RUNTIME_HOME).expanduser()
POLICY_DIR_CANDIDATES = [
    SCRIPT_PATH.parent / "policy",
    RUNTIME_HOME / "ops" / "policy",
    Path.home() / ".openclaw" / "ops" / "policy",
    SCRIPT_PATH.parents[2] / "control-plane-ops" / "scripts" / "policy",
]
for candidate in POLICY_DIR_CANDIDATES:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from policy_route_selection import (  # noqa: E402
    AWAIT_ROUTE_SELECTION_ACTION,
    build_route_selection as build_policy_route_selection,
    route_selection_options,
)
from task_center import TaskCenter, TaskCenterError  # noqa: E402


DEADLINE_PATTERN = re.compile(
    r"\[(?:\u622a\u6b62|deadline|due)\s*[:\uff1a]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})\]",
    re.IGNORECASE,
)
UNCHECKED_PATTERN = re.compile(r"^\s*-\s*\[\s*[ /]\s*\]\s*(?P<text>.+?)\s*$")
PRIORITY_PATTERN = re.compile(r"\[(?P<tag>P[0-3]|🔴|🟡|🟢)\]", re.IGNORECASE)
HIGH_RISK_PATTERN = re.compile(
    r"(生产|线上|部署|重启|迁移|删除|drop|truncate|rm\s+-rf|force\s+push|"
    r"凭证|密钥|token|api[_ -]?key|cookie|资金|提现|划转|下单|撤单|实盘|交易|权限|sudo|root)",
    re.IGNORECASE,
)
LOW_RISK_PATTERN = re.compile(
    r"(文档|docs?|readme|索引|说明|注释|格式|错别字|typo|只读|查询|整理|报告|csv|excel)",
    re.IGNORECASE,
)
@dataclass(frozen=True)
class DueTodoItem:
    line_no: int
    raw_line: str
    text: str
    deadline: datetime
    days_until: int
    state: str


def default_task_db() -> Path:
    return RUNTIME_HOME / "ops" / "task-center" / "task_center.db"


def parse_deadline(text: str) -> datetime | None:
    match = DEADLINE_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1).replace("/", "-")
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def scan_due_todos(todo_file: Path, *, now: datetime | None = None, include_upcoming_days: int = 0) -> list[DueTodoItem]:
    if not todo_file.exists():
        raise FileNotFoundError(f"todo file not found: {todo_file}")
    current = now or datetime.now(tz=timezone.utc)
    lines = todo_file.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[DueTodoItem] = []
    for index, line in enumerate(lines, start=1):
        unchecked = UNCHECKED_PATTERN.match(line)
        if not unchecked:
            continue
        deadline = parse_deadline(line)
        if deadline is None:
            continue
        days_until = (deadline.date() - current.date()).days
        if days_until < 0:
            state = "overdue"
        elif days_until == 0:
            state = "due_today"
        elif days_until <= include_upcoming_days:
            state = "upcoming"
        else:
            continue
        out.append(
            DueTodoItem(
                line_no=index,
                raw_line=line,
                text=unchecked.group("text").strip(),
                deadline=deadline,
                days_until=days_until,
                state=state,
            )
        )
    return out


def build_task_id(todo_file: Path, item: DueTodoItem) -> str:
    fingerprint = hashlib.sha256(
        f"{todo_file.resolve()}|{item.line_no}|{item.deadline.date().isoformat()}|{item.raw_line.strip()}".encode(
            "utf-8", errors="replace"
        )
    ).hexdigest()
    return f"todo-deadline-{fingerprint[:16]}"


def infer_priority_and_risk(item: DueTodoItem) -> tuple[str, str, list[str]]:
    text = item.raw_line + "\n" + item.text
    priority_match = PRIORITY_PATTERN.search(text)
    priority_tag = (priority_match.group("tag").upper() if priority_match else "").strip()
    reasons: list[str] = []

    if priority_tag in {"P0", "P1", "🔴"}:
        priority = "high"
        risk_level = "high"
        reasons.append(f"priority_tag:{priority_tag}")
    elif priority_tag in {"P2", "🟡"}:
        priority = "medium"
        risk_level = "low"
        reasons.append(f"priority_tag:{priority_tag}")
    elif priority_tag in {"P3", "🟢"}:
        priority = "low"
        risk_level = "low"
        reasons.append(f"priority_tag:{priority_tag}")
    else:
        priority = "high" if item.days_until < 0 else "medium"
        risk_level = "low"
        reasons.append("deadline_due")

    if HIGH_RISK_PATTERN.search(text):
        risk_level = "high"
        priority = "high"
        reasons.append("high_risk_keyword")
    elif LOW_RISK_PATTERN.search(text):
        risk_level = "low"
        reasons.append("low_risk_keyword")

    return priority, risk_level, reasons


def build_todo_route_selection(*, priority: str, risk_level: str, risk_reasons: list[str]) -> dict[str, Any]:
    route_selection = build_policy_route_selection(
        risk_level=risk_level,
        task_type="todo_deadline_candidate",
        require_manual=True,
    )
    route_selection.update(
        {
            "priority": priority,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        }
    )
    return route_selection


def build_candidate_task(todo_file: Path, item: DueTodoItem, *, assignee: str) -> dict[str, Any]:
    overdue_text = "overdue" if item.days_until < 0 else item.state
    priority, risk_level, risk_reasons = infer_priority_and_risk(item)
    route_selection = build_todo_route_selection(priority=priority, risk_level=risk_level, risk_reasons=risk_reasons)
    need_human_confirm = True
    effective_assignee = "human-inbox"
    action = AWAIT_ROUTE_SELECTION_ACTION
    requirement = (
        "Ask the user to choose the execution route before any workflow, agent, or backlog runner starts work. "
        f"Recommended route: {route_selection['recommended_route']}. TODO: {item.text}"
    )
    result_output = "A selected execution route, a clarified task, or a cancelled candidate."
    acceptance = "The user explicitly chooses direct run, requirement discussion, specified agent, coding workflow, or TODO auto candidate."
    observable_outputs = "human_inbox entry; task_center task row; human route-selection output"
    acceptance_thresholds = "Candidate remains blocked while need_human_confirm=true and human_confirmed=false."
    return {
        "task_id": build_task_id(todo_file, item),
        "pool": "todo",
        "task_type": "todo_deadline_candidate",
        "reason": f"TODO deadline {overdue_text}: line {item.line_no}",
        "source": "todo-deadline-bridge",
        "request_source": "ai",
        "priority": priority,
        "risk_level": risk_level,
        "assignee": effective_assignee,
        "status": "pending",
        "need_human_confirm": need_human_confirm,
        "human_confirmed": False,
        "action": action,
        "requirement": requirement,
        "result_output": result_output,
        "acceptance": acceptance,
        "observable_outputs": observable_outputs,
        "acceptance_thresholds": acceptance_thresholds,
        "context_payload": {
            "bridge": "deadline_to_task_bridge",
            "question": (
                "Should this due TODO be added to the executable Task Center queue?"
                if need_human_confirm
                else ""
            ),
            "source_file": str(todo_file),
            "line_no": item.line_no,
            "deadline": item.deadline.date().isoformat(),
            "days_until": item.days_until,
            "state": item.state,
            "raw_todo": item.raw_line,
            "risk_reasons": risk_reasons,
            "route_selection": route_selection,
        },
        "allowed_agents": ["human-inbox", "coordinator", "project-agent", "researcher", "tester", "doc-writer"],
        "required_capabilities": ["human_confirmation", "task_routing"],
        "required_skills": ["todo-patrol"],
    }


def create_due_candidates(
    *,
    todo_file: Path,
    task_db: Path,
    actor: str,
    assignee: str,
    include_upcoming_days: int = 0,
    max_items: int = 20,
    dry_run: bool = False,
) -> dict[str, Any]:
    items = scan_due_todos(todo_file, include_upcoming_days=max(0, include_upcoming_days))
    selected = items[: max(1, max_items)]
    summary: dict[str, Any] = {
        "todo_file": str(todo_file),
        "task_db": str(task_db),
        "found": len(items),
        "selected": len(selected),
        "created": [],
        "existing": [],
        "planned": [],
    }
    if dry_run:
        summary["planned"] = [build_candidate_task(todo_file, item, assignee=assignee) for item in selected]
        return summary

    center = TaskCenter(task_db)
    try:
        center.init_schema()
        for item in selected:
            task = build_candidate_task(todo_file, item, assignee=assignee)
            task_id = str(task["task_id"])
            try:
                existing = center.get_task(task_id, display_safe=False)
            except TaskCenterError:
                existing = None
            if existing:
                summary["existing"].append(task_id)
                continue
            created = center.create_task(task, actor=actor)
            command_base = "python3 ${HARDFLOW_RUNTIME_HOME:-$HOME/.hardflow-runtime}/ops/policy/human_inbox.py"
            route_selection = task.get("context_payload", {}).get("route_selection", {})
            recommended_route = str(route_selection.get("recommended_route") or "coding_workflow")
            center.record_task_output(
                task_id=task_id,
                output_type="human_question",
                audience="human",
                channel="human_inbox",
                status="prepared",
                summary=f"Select execution route for due TODO candidate {task_id}",
                payload={
                    "question": "请选择这个到期 TODO 的执行链路。",
                    "todo": item.raw_line,
                    "deadline": item.deadline.date().isoformat(),
                    "recommended_route": recommended_route,
                    "recommendation_reason": route_selection.get("recommendation_reason", ""),
                    "choices": route_selection.get("options", route_selection_options()),
                    "commands": {
                        "recommended": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice {recommended_route}",
                        "direct_run": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice direct_run",
                        "requirement_discussion": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice requirement_discussion --assignee project-agent",
                        "specified_agent": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice specified_agent --assignee <agent-id>",
                        "coding_workflow": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice coding_workflow",
                        "todo_auto_candidate": f"{command_base} confirm --task-db {task_db} --task-id {task_id} --route-choice todo_auto_candidate",
                        "decline": f"{command_base} decline --task-db {task_db} --task-id {task_id}",
                    },
                },
                actor=actor,
            )
            center.add_event(
                task_id=task_id,
                actor=actor,
                event_type="deadline_candidate_created",
                stage="intake",
                details={"source_file": str(todo_file), "line_no": item.line_no, "state": item.state},
            )
            summary["created"].append(created["task_id"])
    finally:
        center.close()
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge due TODO lines into risk-aware Task Center candidates.")
    parser.add_argument("--todo-file", required=True)
    parser.add_argument("--task-db", default=str(default_task_db()))
    parser.add_argument("--task-id", default="cron:deadline-to-task-bridge")
    parser.add_argument("--actor", default="todo-deadline-bridge")
    parser.add_argument("--assignee", default="coordinator")
    parser.add_argument("--include-upcoming-days", type=int, default=0)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        summary = create_due_candidates(
            todo_file=Path(args.todo_file).expanduser().resolve(),
            task_db=Path(args.task_db).expanduser().resolve(),
            actor=str(args.actor or args.task_id or "todo-deadline-bridge"),
            assignee=str(args.assignee or "coordinator"),
            include_upcoming_days=int(args.include_upcoming_days),
            max_items=int(args.max_items),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"FAILED deadline_to_task_bridge: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if not summary["created"] and not summary["planned"]:
        print("NO_REPLY")
        return 0
    print(
        "deadline_to_task_bridge "
        f"created={len(summary['created'])} existing={len(summary['existing'])} planned={len(summary['planned'])}"
    )
    for task_id in summary["created"]:
        print(f"deadline_candidate_created task_id={task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TODO patrol with source-aware routing and context gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))

DEFAULT_AI_SOURCE_KEYWORDS = [
    "[ai]",
    "ai:",
    "自动巡检",
    "自动审计",
    "巡检发现",
    "审计发现",
    "监控发现",
    "ops汇总",
    "bot",
]

DEFAULT_HUMAN_SOURCE_KEYWORDS = [
    "[human]",
    "human:",
    "[manual]",
    "manual:",
]

DEFAULT_PROJECT_KEYWORDS = [
    "项目",
    "项目索引",
    "项目规划",
    "项目说明",
    "模块",
    "架构",
    "workflow",
    "readme",
    "api文档",
    "接口文档",
    "产品经理",
    "项目经理",
]

AI_REQUIRED_CONTEXT_FIELDS = [
    "problem",
    "location",
    "first_seen_at",
    "duration",
    "impact",
    "evidence",
    "target_state",
    "scope",
]


def now_tz() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now_tz().isoformat(timespec="seconds")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


@dataclass(slots=True)
class TodoItem:
    item_id: str
    text: str
    section: str
    priority_tag: str
    line_num: int
    raw_line: str


def parse_todo_items(content: str) -> list[TodoItem]:
    items: list[TodoItem] = []
    current_section = ""
    lines = content.splitlines()
    checkbox_re = re.compile(r"^\s*-\s*\[\s\]\s*(.+?)\s*$")

    for idx, line in enumerate(lines, start=1):
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue

        m = checkbox_re.match(line)
        if not m:
            continue

        text = m.group(1).strip()
        if not text:
            continue

        pm = re.search(r"\b(P0|P1|P2)\b", text, flags=re.IGNORECASE)
        priority_tag = (pm.group(1).upper() if pm else "")
        item_id = sha256(f"{current_section}|{norm_text(text)}")
        items.append(
            TodoItem(
                item_id=item_id,
                text=text,
                section=current_section,
                priority_tag=priority_tag,
                line_num=idx,
                raw_line=line,
            )
        )
    return items


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


def load_routing(path: Path) -> dict[str, Any]:
    default = {
        "high_risk_keywords": [],
        "priority_keywords": {"high": [], "low": []},
        "assignee_rules": [],
        "default_assignee": "coordinator",
        "clarification_assignee": "project-agent",
        "project_keywords": DEFAULT_PROJECT_KEYWORDS,
        "ai_source_keywords": DEFAULT_AI_SOURCE_KEYWORDS,
        "human_source_keywords": DEFAULT_HUMAN_SOURCE_KEYWORDS,
    }
    data = load_json(path, default)
    if not isinstance(data, dict):
        return default
    out = dict(default)
    out.update(data)
    return out


def calc_due_hours(priority: str) -> int:
    if priority == "high":
        return 4
    if priority == "medium":
        return 24
    return 72


def normalize_keywords(values: list[Any] | None, fallback: list[str]) -> list[str]:
    if not isinstance(values, list):
        values = []
    out = [str(x).strip().lower() for x in values if str(x).strip()]
    return out or [x.lower() for x in fallback]


def infer_request_source(item: TodoItem, routing: dict[str, Any], default_source: str) -> str:
    text = norm_text(item.text)
    ai_keywords = normalize_keywords(routing.get("ai_source_keywords"), DEFAULT_AI_SOURCE_KEYWORDS)
    human_keywords = normalize_keywords(routing.get("human_source_keywords"), DEFAULT_HUMAN_SOURCE_KEYWORDS)

    for keyword in human_keywords:
        if keyword in text:
            return "human"
    for keyword in ai_keywords:
        if keyword in text:
            return "ai"

    source = str(default_source or "").strip().lower()
    if source in {"human", "ai"}:
        return source
    return "human"


def detect_project_hits(text: str, routing: dict[str, Any]) -> list[str]:
    keywords = normalize_keywords(routing.get("project_keywords"), DEFAULT_PROJECT_KEYWORDS)
    text_norm = norm_text(text)
    return [k for k in keywords if k in text_norm]


def route_item(item: TodoItem, routing: dict[str, Any], request_source: str) -> dict[str, Any]:
    text_norm = norm_text(item.text)
    high_risk_keywords = [str(x).strip().lower() for x in routing.get("high_risk_keywords", []) if str(x).strip()]
    high_priority_keywords = [
        str(x).strip().lower()
        for x in (routing.get("priority_keywords", {}) or {}).get("high", [])
        if str(x).strip()
    ]
    low_priority_keywords = [
        str(x).strip().lower()
        for x in (routing.get("priority_keywords", {}) or {}).get("low", [])
        if str(x).strip()
    ]

    high_risk_hits = [k for k in high_risk_keywords if k in text_norm]
    high_priority_hits = [k for k in high_priority_keywords if k in text_norm]
    low_priority_hits = [k for k in low_priority_keywords if k in text_norm]

    if item.priority_tag == "P0" or high_priority_hits:
        priority = "high"
    elif item.priority_tag == "P1":
        priority = "high"
    elif item.priority_tag == "P2":
        priority = "medium"
    elif low_priority_hits:
        priority = "low"
    else:
        priority = "medium"

    risk_level = "high" if (item.priority_tag in {"P0", "P1"} or high_risk_hits) else "low"

    assignee = str(routing.get("default_assignee", "coordinator")).strip() or "coordinator"
    assignee_hit = ""
    for rule in routing.get("assignee_rules", []):
        if not isinstance(rule, dict):
            continue
        candidate = str(rule.get("assignee", "")).strip()
        keywords = [str(x).strip().lower() for x in rule.get("keywords", []) if str(x).strip()]
        if not candidate or not keywords:
            continue
        for keyword in keywords:
            if keyword and keyword in text_norm:
                assignee = candidate
                assignee_hit = keyword
                break
        if assignee_hit:
            break

    project_hits = detect_project_hits(item.text, routing)
    if request_source == "human" and project_hits:
        assignee = "project-agent"
        if priority == "low":
            priority = "medium"

    pool = "jobs" if priority == "high" else "todo"
    due_hours = calc_due_hours(priority)
    due_at = (now_tz() + timedelta(hours=due_hours)).isoformat(timespec="seconds")

    return {
        "priority": priority,
        "risk_level": risk_level,
        "assignee": assignee,
        "assignee_hit": assignee_hit,
        "pool": pool,
        "due_hours": due_hours,
        "due_at": due_at,
        "high_risk_hits": high_risk_hits,
        "high_priority_hits": high_priority_hits,
        "low_priority_hits": low_priority_hits,
        "project_hits": project_hits,
    }


def extract_context(item: TodoItem) -> dict[str, str]:
    text = str(item.text or "").strip()
    location = ""
    first_seen = ""
    duration = ""
    impact = ""
    evidence = ""
    target_state = ""

    location_match = re.search(
        r"(https?://\S+|/[A-Za-z0-9._/\-]+(?:\?[^\s]+)?|[A-Za-z]:\\[^\s]+|[\w./-]+\.(?:py|js|ts|tsx|json|ya?ml|md|sql|sh|log))",
        text,
    )
    if location_match:
        location = location_match.group(1)

    first_seen_match = re.search(r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", text)
    if first_seen_match:
        first_seen = first_seen_match.group(0)

    duration_match = re.search(r"(持续[^，。；;\s]{1,24}|[0-9]+(?:分钟|小时|天|周))", text)
    if duration_match:
        duration = duration_match.group(1)

    impact_keywords = ["影响", "阻塞", "不可用", "失败", "报错", "错误", "超时", "404", "500", "延迟"]
    for keyword in impact_keywords:
        if keyword in text:
            impact = f"contains:{keyword}"
            break

    evidence_match = re.search(
        r"(证据路径[:：]?\s*[^\s，。；;]+|/home/[^\s，。；;]+|[A-Za-z]:\\[^\s，。；;]+|[\w./-]+\.(?:json|log|txt))",
        text,
    )
    if evidence_match:
        evidence = evidence_match.group(1)

    target_match = re.search(r"(修复[^，。；;\n]{1,40}|恢复[^，。；;\n]{1,40}|目标[^，。；;\n]{1,40}|需要[^，。；;\n]{1,40})", text)
    if target_match:
        target_state = target_match.group(1)

    return {
        "problem": text,
        "location": location,
        "first_seen_at": first_seen,
        "duration": duration,
        "impact": impact,
        "evidence": evidence,
        "target_state": target_state,
        "scope": f"todo_section={item.section or '-'};line={item.line_num}",
    }


def evaluate_ai_context(context_payload: dict[str, Any], min_pct: float) -> dict[str, Any]:
    missing = [field for field in AI_REQUIRED_CONTEXT_FIELDS if not str(context_payload.get(field, "")).strip()]
    completeness = round(((len(AI_REQUIRED_CONTEXT_FIELDS) - len(missing)) / len(AI_REQUIRED_CONTEXT_FIELDS)) * 100.0, 2)
    needs_clarification = completeness < min_pct or bool(missing)
    reason = ""
    if needs_clarification:
        reason = f"ai_context_incomplete: completeness={completeness:.2f}, missing={','.join(missing)}"
    return {
        "needs_clarification": needs_clarification,
        "clarification_reason": reason,
        "context_completeness": completeness,
        "context_fields_missing": missing,
    }


def build_task_payload(
    item: TodoItem,
    route: dict[str, Any],
    request_source: str,
    context_eval: dict[str, Any],
    context_payload: dict[str, Any],
    clarification_assignee: str,
) -> dict[str, Any]:
    task_id = f"todo-{item.item_id}"
    needs_clarification = bool(context_eval.get("needs_clarification"))

    assignee = route["assignee"]
    priority = route["priority"]
    pool = route["pool"]
    task_type = "todo_dispatch"
    requirement = f"处理 TODO 项并给出可复现修复方案: {item.text}"
    result_output = "输出变更文件、验证命令、验证结果、影响范围。"
    acceptance = "关键检查通过，相关接口/流程可用，无新增高风险回归。"
    observable_outputs = "TaskCenter 状态、代码/配置变更、测试或运行日志。"
    acceptance_thresholds = "失败重试次数 < 3；关键验收项全部通过。"

    if request_source == "ai" and needs_clarification:
        assignee = clarification_assignee
        pool = "todo"
        task_type = "clarification_required"
        if priority == "low":
            priority = "medium"
        requirement = (
            "当前任务来源为 AI 且上下文不完整，先补全任务上下文再进入执行。"
            f"\n原始问题: {item.text}"
            "\n请补齐: problem/location/first_seen_at/duration/impact/evidence/target_state/scope"
        )
        result_output = "输出补全后的任务包（需求、目标、验收、证据）并关闭 clarification 标记。"
        acceptance = "上下文字段完整，能直接分配执行，且可观测证据路径明确。"
        observable_outputs = "补全后的 context_payload、证据路径、任务分配建议。"
        acceptance_thresholds = "AI 上下文完整度达到 100%，缺失字段为 0。"

    return {
        "task_id": task_id,
        "pool": pool,
        "task_type": task_type,
        "reason": item.text,
        "source": "todo_patrol",
        "request_source": request_source,
        "priority": priority,
        "risk_level": route["risk_level"],
        "assignee": assignee,
        "status": "pending",
        "needs_clarification": needs_clarification,
        "clarification_reason": str(context_eval.get("clarification_reason", "")).strip(),
        "need_human_confirm": route["risk_level"] == "high" and not needs_clarification,
        "human_confirmed": False,
        "context_completeness": float(context_eval.get("context_completeness", 100.0) or 100.0),
        "context_fields_missing": list(context_eval.get("context_fields_missing", [])),
        "context_payload": context_payload,
        "requirement": requirement,
        "result_output": result_output,
        "acceptance": acceptance,
        "observable_outputs": observable_outputs,
        "acceptance_thresholds": acceptance_thresholds,
        "scheduled_at": now_iso(),
        "action": "dispatch",
    }


def mark_item_processed(line: str, task_id: str, payload: dict[str, Any], route: dict[str, Any]) -> str:
    cleaned = re.sub(r"^\s*-\s*\[\s\]\s*", "", line).strip()
    status_tag = "AUTO_CLARIFY_REQUIRED" if payload.get("needs_clarification") else "AUTO_DISPATCHED"
    return (
        f"- [x] [{status_tag}] task_id={task_id} assignee={payload.get('assignee')} "
        f"priority={payload.get('priority')} risk={payload.get('risk_level')} "
        f"source={payload.get('request_source')} "
        f"context={payload.get('context_completeness')}% eta={route['due_hours']}h | {cleaned}"
    )


def format_dispatch_message(
    task: str,
    todo_file: Path,
    dispatched: list[dict[str, Any]],
    skipped_count: int,
    db_path: Path,
    state_file: Path,
) -> str:
    if not dispatched and skipped_count == 0:
        return "NO_REPLY"

    lines: list[str] = []
    lines.append("sender_identity: ops-agent/todo-patrol")
    lines.append(f"task: {task}")
    lines.append(f"time: {now_tz().strftime('%Y-%m-%d %H:%M:%S')} UTC+8")
    lines.append(f"todo_file: {todo_file}")
    lines.append(f"task_center_db: {db_path}")
    lines.append(f"state_file: {state_file}")
    lines.append("")
    lines.append(f"dispatch_result: new={len(dispatched)} skipped={skipped_count}")
    lines.append("")

    if dispatched:
        lines.append("new_tasks:")
        for idx, item in enumerate(dispatched, start=1):
            task_row = item["task"]
            route = item["route"]
            lines.append(
                f"{idx}. task_id={task_row.get('task_id')} assignee={task_row.get('assignee') or 'unassigned'} "
                f"priority={task_row.get('priority')} risk={task_row.get('risk_level')} "
                f"source={task_row.get('request_source')} "
                f"clarification={task_row.get('needs_clarification')} "
                f"context={task_row.get('context_completeness')}% "
                f"status={task_row.get('status')} retry={task_row.get('retry_count')} failure={task_row.get('failure_count')}"
            )
            lines.append(f"   reason: {task_row.get('reason')}")
            lines.append(f"   requirement: {task_row.get('requirement')}")
            lines.append(f"   target_result: {task_row.get('result_output')}")
            lines.append(f"   acceptance: {task_row.get('acceptance')}")
            lines.append(f"   observable_outputs: {task_row.get('observable_outputs')}")
            lines.append(f"   acceptance_thresholds: {task_row.get('acceptance_thresholds')}")
            lines.append(f"   context_missing: {task_row.get('context_fields_missing')}")
            lines.append(f"   eta_hours: {route.get('due_hours')} (due_at={route.get('due_at')})")
            lines.append("")

    if skipped_count > 0:
        lines.append(f"skipped_reason: max-dispatch reached, remaining={skipped_count}")

    return "\n".join(lines).strip()


def main() -> int:
    home = Path(os.path.expanduser("~"))
    default_openclaw_home = Path(os.environ.get("OPENCLAW_HOME", str(home / ".openclaw"))).expanduser()
    default_ops_dir = Path(os.environ.get("OPENCLAW_OPS_DIR", str(default_openclaw_home / "ops"))).expanduser()
    default_coordinator_ws = Path(
        os.environ.get("COORDINATOR_WORKSPACE", str(default_openclaw_home / "workspace-coordinator"))
    ).expanduser()

    parser = argparse.ArgumentParser(description="TODO patrol with source-aware auto dispatch")
    parser.add_argument("--task", default="cron:todo-patrol")
    parser.add_argument("--ops-dir", default=str(default_ops_dir))
    parser.add_argument("--todo-file", default=str(default_coordinator_ws / "TODO.md"))
    parser.add_argument("--state-file", default=str(default_ops_dir / "todo-patrol-state.json"))
    parser.add_argument("--task-db", default=str(default_ops_dir / "task-center/task_center.db"))
    parser.add_argument("--routing-file", default=str(default_ops_dir / "policy/routing-rules.json"))
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--max-dispatch", type=int, default=5)
    parser.add_argument("--default-request-source", default="human", choices=["human", "ai"])
    parser.add_argument("--ai-context-min-pct", type=float, default=100.0)
    parser.add_argument("--clarification-assignee", default="")
    parser.add_argument("--no-auto-assign", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    policy_dir = script_dir / "policy"
    if str(policy_dir) not in sys.path:
        sys.path.insert(0, str(policy_dir))
    try:
        from task_center import TaskCenter, TaskCenterError
    except Exception as exc:  # pragma: no cover - runtime bootstrapping
        print(f"NO_REPLY\n# todo-patrol error: cannot import task_center: {exc}")
        return 0

    ops_dir = Path(args.ops_dir).expanduser()
    todo_file = Path(args.todo_file).expanduser()
    state_file = Path(args.state_file).expanduser()
    task_db = Path(args.task_db).expanduser()
    routing_file = Path(args.routing_file).expanduser()
    max_dispatch = max(1, int(args.max_dispatch or 1))

    if not todo_file.exists():
        print("NO_REPLY")
        return 0

    routing = load_routing(routing_file)
    state = load_json(state_file, {"updated_at": "", "items": {}})
    if not isinstance(state, dict):
        state = {"updated_at": "", "items": {}}
    if not isinstance(state.get("items"), dict):
        state["items"] = {}

    clarification_assignee = (
        str(args.clarification_assignee or "").strip()
        or str(routing.get("clarification_assignee", "project-agent")).strip()
        or "project-agent"
    )

    todo_content = todo_file.read_text(encoding="utf-8-sig")
    todo_items = parse_todo_items(todo_content)
    if not todo_items:
        print("NO_REPLY")
        return 0

    dispatch_candidates = todo_items[:max_dispatch]
    skipped_count = max(0, len(todo_items) - len(dispatch_candidates))

    if args.no_auto_assign:
        msg = format_dispatch_message(
            task=args.task,
            todo_file=todo_file,
            dispatched=[],
            skipped_count=len(todo_items),
            db_path=task_db,
            state_file=state_file,
        )
        print(msg)
        return 0

    lines = todo_content.splitlines()
    dispatched: list[dict[str, Any]] = []

    def make_task_row(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": payload["task_id"],
            "assignee": payload["assignee"],
            "priority": payload["priority"],
            "risk_level": payload["risk_level"],
            "status": "pending",
            "retry_count": 0,
            "failure_count": 0,
            "request_source": payload.get("request_source", "human"),
            "needs_clarification": bool(payload.get("needs_clarification")),
            "clarification_reason": payload.get("clarification_reason", ""),
            "context_completeness": payload.get("context_completeness", 100.0),
            "context_fields_missing": payload.get("context_fields_missing", []),
            "reason": payload["reason"],
            "requirement": payload["requirement"],
            "result_output": payload["result_output"],
            "acceptance": payload["acceptance"],
            "observable_outputs": payload["observable_outputs"],
            "acceptance_thresholds": payload["acceptance_thresholds"],
        }

    if args.dry_run:
        for item in dispatch_candidates:
            request_source = infer_request_source(item, routing, args.default_request_source)
            route = route_item(item, routing, request_source)
            context_payload = extract_context(item)
            if request_source == "ai":
                context_eval = evaluate_ai_context(context_payload, float(args.ai_context_min_pct))
            else:
                context_eval = {
                    "needs_clarification": False,
                    "clarification_reason": "",
                    "context_completeness": 100.0,
                    "context_fields_missing": [],
                }
            payload = build_task_payload(
                item=item,
                route=route,
                request_source=request_source,
                context_eval=context_eval,
                context_payload=context_payload,
                clarification_assignee=clarification_assignee,
            )
            dispatched.append({"item": item, "task": make_task_row(payload), "route": route, "payload": payload})
    else:
        task_db.parent.mkdir(parents=True, exist_ok=True)
        tc = TaskCenter(task_db)
        tc.init_schema()
        try:
            for item in dispatch_candidates:
                request_source = infer_request_source(item, routing, args.default_request_source)
                route = route_item(item, routing, request_source)
                context_payload = extract_context(item)
                if request_source == "ai":
                    context_eval = evaluate_ai_context(context_payload, float(args.ai_context_min_pct))
                else:
                    context_eval = {
                        "needs_clarification": False,
                        "clarification_reason": "",
                        "context_completeness": 100.0,
                        "context_fields_missing": [],
                    }
                payload = build_task_payload(
                    item=item,
                    route=route,
                    request_source=request_source,
                    context_eval=context_eval,
                    context_payload=context_payload,
                    clarification_assignee=clarification_assignee,
                )
                task_id = payload["task_id"]
                created_new = False
                try:
                    task_row = tc.create_task(payload, actor=args.actor)
                    created_new = True
                except TaskCenterError as exc:
                    if "task_id already exists" not in str(exc):
                        raise
                    task_row = tc.get_task(task_id)

                if (task_row.get("assignee") or "").strip() != payload["assignee"]:
                    task_row = tc.assign_task(task_id=task_id, assignee=payload["assignee"], actor=args.actor)

                tc.add_event(
                    task_id=task_id,
                    actor=args.actor,
                    event_type="todo_auto_dispatched",
                    stage="dispatch",
                    details={
                        "todo_item_id": item.item_id,
                        "todo_section": item.section,
                        "todo_file": str(todo_file),
                        "line_num": item.line_num,
                        "created_new": created_new,
                        "request_source": request_source,
                        "route": route,
                        "context_eval": context_eval,
                    },
                )

                item_state = state["items"].setdefault(item.item_id, {})
                item_state.update(
                    {
                        "task_id": task_id,
                        "last_text": item.text,
                        "last_dispatched_at": now_iso(),
                        "dispatch_count": int(item_state.get("dispatch_count", 0) or 0) + 1,
                        "request_source": request_source,
                        "priority": payload["priority"],
                        "risk_level": payload["risk_level"],
                        "assignee": payload["assignee"],
                        "needs_clarification": bool(payload["needs_clarification"]),
                        "context_completeness": payload["context_completeness"],
                        "context_fields_missing": payload["context_fields_missing"],
                    }
                )

                if 0 < item.line_num <= len(lines):
                    lines[item.line_num - 1] = mark_item_processed(lines[item.line_num - 1], task_id, payload, route)

                dispatched.append({"item": item, "task": task_row, "route": route, "payload": payload})
        finally:
            tc.close()

    if dispatched and not args.dry_run:
        todo_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if not args.dry_run:
        state["updated_at"] = now_iso()
        save_json(state_file, state)

    msg = format_dispatch_message(
        task=args.task,
        todo_file=todo_file,
        dispatched=dispatched,
        skipped_count=skipped_count,
        db_path=task_db,
        state_file=state_file,
    )
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

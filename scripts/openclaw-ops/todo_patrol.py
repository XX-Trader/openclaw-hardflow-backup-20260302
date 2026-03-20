#!/usr/bin/env python3
"""TODO patrol with source-aware routing and policy-enforced dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclass_compat import compat_dataclass as dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from utf8_runtime import configure_process_utf8_stdio
from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic
from chat_output import build_trace_id, render_chat_notice

configure_process_utf8_stdio()

TZ = timezone(timedelta(hours=8))

DEFAULT_AI_SOURCE_KEYWORDS = [
    "[ai]",
    "ai:",
    "自动巡检",
    "自动审计",
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

DEFAULT_CODE_TASK_KEYWORDS = [
    "write code",
    "coding",
    "implement",
    "bugfix",
    "fix bug",
    "refactor",
    "开发",
    "写代码",
    "修复",
    "实现",
    "代码",
]

DEFAULT_FRONTEND_CODE_KEYWORDS = [
    "frontend",
    "ui",
    "页面",
    "前端",
    "样式",
    "交互",
]

DEFAULT_BACKEND_CODE_KEYWORDS = [
    "backend",
    "api",
    "服务端",
    "后端",
    "数据库",
    "接口",
]

DEFAULT_TEST_CODE_KEYWORDS = [
    "test",
    "qa",
    "测试",
    "回归",
    "验收",
    "playwright",
]

AI_REQUIRED_CONTEXT_FIELDS = [
    "problem",
    "location",
    "first_seen_at",
    "impact",
    "evidence",
    "current_state",
    "expected_state",
    "operation_path",
    "reproduction_steps",
    "scope",
    "constraints",
    "acceptance_criteria",
    "full_background",
]

AI_RECOMMENDED_CONTEXT_FIELDS = [
    "duration",
    "trigger_conditions",
    "dependencies",
    "history_changes",
    "deliverables",
]

def now_tz() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now_tz().isoformat(timespec="seconds")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def to_text(value: Any) -> str:
    return str(value or "").strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = to_text(value)
        if text:
            return text
    return ""


def split_items(raw: str) -> list[str]:
    text = to_text(raw)
    if not text:
        return []
    parts = re.split(r"[|,，、;；]+", text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = to_text(part)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def extract_labeled_value(text: str, labels: list[str]) -> str:
    raw = str(text or "")
    for label in labels:
        key = re.escape(to_text(label))
        if not key:
            continue
        patterns = [
            rf"(?:^|[\s|,，、;；]){key}\s*[:：]\s*([^\n|,，、;；]+)",
            rf"(?:^|[\s|,，、;；]){key}\s+([^\n|,，、;；]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                return to_text(match.group(1))
    return ""


def infer_default_impact(text: str) -> str:
    lowered = norm_text(text)
    keywords = ["error", "exception", "failed", "timeout", "500", "404", "异常", "失败", "超时"]
    hits = [token for token in keywords if token in lowered]
    return ",".join(hits[:3])


def humanize_dispatch_error(raw: str) -> tuple[str, str]:
    text = to_text(raw)
    if not text:
        return "任务巡检执行失败", "未提供错误详情"

    prefix_mapping = {
        "planner_summary_failed:": "规划器摘要读取失败",
        "log_module_start_failed:": "模块日志启动失败",
        "log_module_finish_failed:": "模块日志收尾失败",
    }
    for prefix, title in prefix_mapping.items():
        if text.startswith(prefix):
            return title, to_text(text[len(prefix) :]) or text

    task_id = extract_labeled_value(text, ["task"])
    if "assign_failed=" in text:
        detail = to_text(text.split("assign_failed=", 1)[1]) or text
        return "任务派发失败", f"task={task_id} | {detail}" if task_id else detail
    if "log_communication_failed=" in text:
        detail = to_text(text.split("log_communication_failed=", 1)[1]) or text
        return "沟通记录写入失败", f"task={task_id} | {detail}" if task_id else detail
    if "report_agent_result_failed=" in text:
        detail = to_text(text.split("report_agent_result_failed=", 1)[1]) or text
        return "Agent 结果回写失败", f"task={task_id} | {detail}" if task_id else detail
    return "任务巡检执行失败", text


def compact_task_text(value: Any, max_len: int = 88) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_dispatch_subject(task_row: dict[str, Any], context_payload: dict[str, Any]) -> str:
    human_summary = compact_task_text(context_payload.get("human_summary", ""), 80)
    if human_summary:
        return human_summary
    requirement = compact_task_text(task_row.get("requirement", ""), 80)
    if requirement:
        return requirement
    reason = compact_task_text(task_row.get("reason", ""), 72)
    if reason:
        return reason
    task_id = to_text(task_row.get("task_id"))
    return task_id or "未命名任务"


def build_dispatch_requirement(task_row: dict[str, Any]) -> str:
    requirement = compact_task_text(task_row.get("requirement", ""), 88)
    acceptance = compact_task_text(task_row.get("acceptance", ""), 64)
    if requirement and acceptance:
        return f"{requirement} 验收：{acceptance}"
    if requirement:
        return requirement
    if acceptance:
        return f"验收：{acceptance}"
    result_output = compact_task_text(task_row.get("result_output", ""), 72)
    if result_output:
        return f"期望输出：{result_output}"
    return "当前只完成派发，尚未补充更具体的执行要求。"


def build_dispatch_status(task_row: dict[str, Any]) -> str:
    assignee = to_text(task_row.get("assignee")) or "unassigned"
    priority = to_text(task_row.get("priority")) or "-"
    risk_level = to_text(task_row.get("risk_level")) or "-"
    context_completeness = to_text(task_row.get("context_completeness")) or "0"
    if bool(task_row.get("needs_clarification")):
        status_label = "已派发待补充信息"
    else:
        status_label = f"已派发给 {assignee}"
    return (
        f"{status_label}（优先级={priority}，风险={risk_level}，"
        f"上下文完整度={context_completeness}%）"
    )


def explain_dispatch_value(task_row: dict[str, Any]) -> str:
    priority = to_text(task_row.get("priority")).lower()
    risk_level = to_text(task_row.get("risk_level")).lower()
    if bool(task_row.get("needs_clarification")):
        return "这项还缺上下文，先补清楚能避免派发后重复返工。"
    if priority == "high" or risk_level == "high":
        return "这项优先级或风险偏高，越早接手越能避免积压。"
    return "这项已经进入任务中心，尽快跟进能把待办真正推进起来。"


def build_dispatch_judgement(dispatched: list[dict[str, Any]], dispatch_errors: list[str]) -> str:
    if dispatch_errors and dispatched:
        return "巡检有异常，先看异常，再确认已派发任务是否需要人工兜底。"
    if dispatch_errors:
        return "本轮巡检异常优先，先恢复巡检链路。"
    if dispatched:
        high_priority_count = 0
        for row in dispatched:
            task_row = row.get("task", {}) if isinstance(row, dict) else {}
            if not isinstance(task_row, dict):
                continue
            if to_text(task_row.get("priority")).lower() == "high" or to_text(task_row.get("risk_level")).lower() == "high":
                high_priority_count += 1
        if high_priority_count > 0:
            return f"本轮已派发 {high_priority_count} 项高优先级任务，建议先盯前排事项。"
        return "本轮派发正常，重点确认新任务是否被及时接手。"
    return ""


def has_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(has_value(v) for v in value)
    text = to_text(value)
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"none", "n/a", "na", "unknown", "-", "未提供", "待补充"}:
        return False
    return True

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

        match = checkbox_re.match(line)
        if not match:
            continue

        text = to_text(match.group(1))
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


def is_ops_incident_item(item: TodoItem) -> bool:
    text = norm_text(item.text)
    if "[ops]" in text:
        return True
    return any(token in text for token in ("key=issue:", "key=workflow_job:", "source=ops-cron-runner"))


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
        "force_dispatch_code_tasks": True,
        "code_task_keywords": DEFAULT_CODE_TASK_KEYWORDS,
        "frontend_code_keywords": DEFAULT_FRONTEND_CODE_KEYWORDS,
        "backend_code_keywords": DEFAULT_BACKEND_CODE_KEYWORDS,
        "test_code_keywords": DEFAULT_TEST_CODE_KEYWORDS,
        "default_code_assignee": "backend-dev",
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
    out = [to_text(x).lower() for x in values if to_text(x)]
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

    source = to_text(default_source).lower()
    if source in {"human", "ai"}:
        return source
    return "human"


def detect_project_hits(text: str, routing: dict[str, Any]) -> list[str]:
    keywords = normalize_keywords(routing.get("project_keywords"), DEFAULT_PROJECT_KEYWORDS)
    text_norm = norm_text(text)
    return [k for k in keywords if k in text_norm]


def route_item(item: TodoItem, routing: dict[str, Any], request_source: str) -> dict[str, Any]:
    text_norm = norm_text(item.text)
    high_risk_keywords = [to_text(x).lower() for x in routing.get("high_risk_keywords", []) if to_text(x)]
    high_priority_keywords = [to_text(x).lower() for x in (routing.get("priority_keywords", {}) or {}).get("high", []) if to_text(x)]
    low_priority_keywords = [to_text(x).lower() for x in (routing.get("priority_keywords", {}) or {}).get("low", []) if to_text(x)]

    high_risk_hits = [k for k in high_risk_keywords if k in text_norm]
    high_priority_hits = [k for k in high_priority_keywords if k in text_norm]
    low_priority_hits = [k for k in low_priority_keywords if k in text_norm]

    if item.priority_tag in {"P0", "P1"} or high_priority_hits:
        priority = "high"
    elif item.priority_tag == "P2":
        priority = "medium"
    elif low_priority_hits:
        priority = "low"
    else:
        priority = "medium"

    risk_level = "high" if (item.priority_tag in {"P0", "P1"} or high_risk_hits) else "low"

    assignee = to_text(routing.get("default_assignee", "coordinator")) or "coordinator"
    assignee_hit = ""
    for rule in routing.get("assignee_rules", []):
        if not isinstance(rule, dict):
            continue
        candidate = to_text(rule.get("assignee"))
        keywords = [to_text(x).lower() for x in rule.get("keywords", []) if to_text(x)]
        if not candidate or not keywords:
            continue
        for keyword in keywords:
            if keyword in text_norm:
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

    code_task_hits = [
        k for k in normalize_keywords(routing.get("code_task_keywords"), DEFAULT_CODE_TASK_KEYWORDS) if k in text_norm
    ]
    code_dispatch_forced = False
    code_dispatch_target = ""
    if (
        assignee == "project-agent"
        and bool(routing.get("force_dispatch_code_tasks", True))
        and code_task_hits
    ):
        frontend_hits = [
            k
            for k in normalize_keywords(
                routing.get("frontend_code_keywords"),
                DEFAULT_FRONTEND_CODE_KEYWORDS,
            )
            if k in text_norm
        ]
        backend_hits = [
            k
            for k in normalize_keywords(
                routing.get("backend_code_keywords"),
                DEFAULT_BACKEND_CODE_KEYWORDS,
            )
            if k in text_norm
        ]
        test_hits = [
            k
            for k in normalize_keywords(
                routing.get("test_code_keywords"),
                DEFAULT_TEST_CODE_KEYWORDS,
            )
            if k in text_norm
        ]
        target = to_text(routing.get("default_code_assignee", "backend-dev")) or "backend-dev"
        if backend_hits:
            target = "backend-dev"
        elif frontend_hits and not backend_hits:
            target = "frontend-dev"
        elif test_hits:
            target = "tester"
        elif frontend_hits:
            target = "frontend-dev"
        assignee = target
        code_dispatch_forced = True
        code_dispatch_target = target
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
        "code_task_hits": code_task_hits,
        "code_dispatch_forced": code_dispatch_forced,
        "code_dispatch_target": code_dispatch_target,
    }


def extract_context(item: TodoItem) -> dict[str, Any]:
    text = to_text(item.text)
    location = ""
    first_seen = ""
    duration = ""
    evidence = ""

    location_match = re.search(
        r"(https?://\S+|/[A-Za-z0-9._/\-]+(?:\?[^\s]+)?|[A-Za-z]:\\[^\s]+|[\w./-]+\.(?:py|js|ts|tsx|json|ya?ml|md|sql|sh|log))",
        text,
    )
    if location_match:
        location = location_match.group(1)

    first_seen_match = re.search(r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", text)
    if first_seen_match:
        first_seen = first_seen_match.group(0)

    duration_match = re.search(r"(\d+\s*(?:m|min|minute|h|hour|d|day|分钟|小时|天))", text, flags=re.IGNORECASE)
    if duration_match:
        duration = duration_match.group(1)

    evidence_match = re.search(
        r"(evidence[:：]\s*[^\s|,，、;；]+|/home/[^\s|,，、;；]+|[A-Za-z]:\\[^\s|,，、;；]+|[\w./-]+\.(?:json|log|txt))",
        text,
        flags=re.IGNORECASE,
    )
    if evidence_match:
        evidence = evidence_match.group(1)

    current_state = extract_labeled_value(text, ["现状", "当前", "current", "current_state", "问题现象"])
    expected_state = extract_labeled_value(text, ["预期", "目标", "expected", "target", "target_state"])
    operation_path = extract_labeled_value(text, ["操作路径", "path", "route"])
    trigger_conditions = extract_labeled_value(text, ["触发条件", "trigger", "when"])
    reproduction_steps = extract_labeled_value(text, ["复现步骤", "repro", "steps"])
    scope = extract_labeled_value(text, ["范围", "scope", "功能范围", "模块"])
    constraints = extract_labeled_value(text, ["约束", "constraints", "限制", "不可做"])
    acceptance_criteria = extract_labeled_value(text, ["验收", "acceptance", "通过线", "标准"])
    dependencies = split_items(extract_labeled_value(text, ["依赖", "dependencies", "depends", "blocked_by"]))
    history_changes = split_items(extract_labeled_value(text, ["历史变更", "历史", "changes", "changelog", "变更记录"]))
    deliverables = split_items(extract_labeled_value(text, ["交付物", "deliverables", "outputs", "产出"]))
    owner_match = re.search(r"(?:owner|负责人|责任人|执行人)\s*[:：]\s*([^\s|,，、;；]+)", text, flags=re.IGNORECASE)
    owner = owner_match.group(1).strip() if owner_match else ""
    change_match = re.search(r"(?:change_id|变更单|变更号|工单号|ticket)\s*[:：]\s*([^\s|,，、;；]+)", text, flags=re.IGNORECASE)
    change_id = change_match.group(1).strip() if change_match else ""
    if owner:
        owner = re.split(r"[\s:：|,，、;；]+", owner, maxsplit=1)[0].strip()
    if not deliverables:
        deliverables = ["代码/配置变更", "验证命令与结果", "风险与回归说明"]

    target_state = first_non_empty(expected_state, "任务完成且通过验收")
    impact = first_non_empty(extract_labeled_value(text, ["影响", "impact"]), infer_default_impact(text))
    full_background = first_non_empty(extract_labeled_value(text, ["背景", "background", "context"]), text)
    scope_text = first_non_empty(scope, f"todo_section={item.section or '-'};line={item.line_num}")

    return {
        "problem": text,
        "location": location,
        "first_seen_at": first_seen,
        "duration": duration,
        "impact": impact,
        "evidence": evidence,
        "target_state": target_state,
        "scope": scope_text,
        "current_state": first_non_empty(current_state, text),
        "expected_state": target_state,
        "operation_path": first_non_empty(operation_path, location),
        "trigger_conditions": trigger_conditions,
        "reproduction_steps": reproduction_steps,
        "constraints": constraints,
        "acceptance_criteria": acceptance_criteria,
        "dependencies": dependencies,
        "history_changes": history_changes,
        "deliverables": deliverables,
        "owner": owner,
        "change_id": change_id,
        "full_background": full_background,
    }


def evaluate_ai_context(context_payload: dict[str, Any], min_pct: float) -> dict[str, Any]:
    missing_required = [field for field in AI_REQUIRED_CONTEXT_FIELDS if not has_value(context_payload.get(field))]
    required_total = max(1, len(AI_REQUIRED_CONTEXT_FIELDS))
    completeness = round(((required_total - len(missing_required)) / required_total) * 100.0, 2)

    missing_recommended = [field for field in AI_RECOMMENDED_CONTEXT_FIELDS if not has_value(context_payload.get(field))]
    needs_clarification = completeness < min_pct or bool(missing_required)

    reason = ""
    if needs_clarification:
        reason = (
            f"ai_context_incomplete: completeness={completeness:.2f}, "
            f"missing_required={','.join(missing_required)}"
        )

    return {
        "needs_clarification": needs_clarification,
        "clarification_reason": reason,
        "context_completeness": completeness,
        "context_fields_missing": missing_required,
        "context_fields_recommended_missing": missing_recommended,
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
    owner = first_non_empty(context_payload.get("owner"), assignee)
    change_id = to_text(context_payload.get("change_id"))    requirement = f"处理 TODO 任务并完成修复交付：{item.text}"
    result_output = "输出变更文件、验证命令、验证结果、影响范围和回归结论。"
    acceptance = "关键检查通过，相关接口/流程可用，无新增高风险回归。"
    observable_outputs = "TaskCenter 状态、代码/配置变更、测试或运行日志。"
    acceptance_thresholds = "失败重试次数 < 3；关键验收项全部通过。"
    info_packet = {
        "task_definition": {
            "current_state": first_non_empty(context_payload.get("current_state"), item.text),
            "expected_target": first_non_empty(context_payload.get("expected_state"), context_payload.get("target_state")),
        },
        "bug_scenario": {
            "operation_path": first_non_empty(context_payload.get("operation_path"), context_payload.get("location")),
            "trigger_conditions": to_text(context_payload.get("trigger_conditions")),
            "reproduction_steps": to_text(context_payload.get("reproduction_steps")),
        },
        "requirement_boundary": {
            "functional_scope": to_text(context_payload.get("scope")),
            "constraints": to_text(context_payload.get("constraints")),
            "acceptance_criteria": first_non_empty(context_payload.get("acceptance_criteria"), acceptance),
        },
        "assignment_packet": {
            "status_snapshot": {
                "priority": priority,
                "risk_level": route["risk_level"],
                "pool": pool,
                "assignee": assignee,
                "owner": owner,
                "change_id": change_id,
                "request_source": request_source,
                "todo_section": item.section or "-",
                "todo_line": item.line_num,
            },
            "full_background": to_text(context_payload.get("full_background")) or item.text,
            "deliverables": list(context_payload.get("deliverables", [])) or ["浠ｇ爜鍙樻洿", "楠岃瘉缁撴灉", "椋庨櫓璇存槑"],
            "dependencies": list(context_payload.get("dependencies", [])),
            "history_changes": list(context_payload.get("history_changes", [])),
        },
    }

    context_payload = dict(context_payload)
    context_payload["information_flow"] = info_packet
    context_payload["human_summary"] = first_non_empty(context_payload.get("problem"), item.text)[:160]
    context_payload["owner"] = owner
    context_payload["change_id"] = change_id
    context_payload["context_contract"] = {
        "required_fields": AI_REQUIRED_CONTEXT_FIELDS,
        "recommended_fields": AI_RECOMMENDED_CONTEXT_FIELDS,
    }
    context_payload["output_language_policy"] = {
        "default_language": "zh-CN",
        "require_chinese_output": True,
        "allow_override_by_user": True,
    }

    risk_points: list[str] = []
    if route["risk_level"] == "high":
        risk_points.append("high_risk_task")
    if context_payload.get("impact"):
        risk_points.append(f"impact={context_payload.get('impact')}")
    if context_payload.get("dependencies"):
        risk_points.append(f"dependencies={len(context_payload.get('dependencies', []))}")
    if context_eval.get("context_fields_missing"):
        risk_points.append(f"context_missing={len(context_eval.get('context_fields_missing', []))}")
    context_payload["risk_points"] = risk_points
    if request_source == "ai" and needs_clarification:
        assignee = clarification_assignee
        pool = "todo"
        task_type = "clarification_required"
        if priority == "low":
            priority = "medium"
        requirement = (
            "当前任务来源为 AI 且上下文不完整，请先补全上下文后再执行。"
            f"\n原始问题: {item.text}"
            "\n请补齐：任务定义/bug场景/需求边界/任务分配包（含优先级、依赖、历史变更）。"
        )
        result_output = "输出补全后的任务包（需求、目标、验收、证据）并关闭 clarification 标记。"
        acceptance = "上下文字段完整，可直接分配执行，且证据路径明确。"
        observable_outputs = "补全后的 context_payload、证据路径、任务分配建议。"
        acceptance_thresholds = "AI 上下文完整度达到 100%，缺失必填字段为 0。"

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
        "owner": owner,
        "change_id": change_id,
        "status": "pending",
        "needs_clarification": needs_clarification,
        "clarification_reason": to_text(context_eval.get("clarification_reason")),
        "need_human_confirm": route["risk_level"] == "high" and not needs_clarification,
        "human_confirmed": False,
        "context_completeness": float(context_eval.get("context_completeness", 100.0) or 100.0),
        "context_fields_missing": list(context_eval.get("context_fields_missing", [])),
        "context_fields_recommended_missing": list(context_eval.get("context_fields_recommended_missing", [])),
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
    ops_incident_skipped_count: int,
    skip_ops_incidents: bool,
    db_path: Path,
    state_file: Path,
    dispatch_errors: list[str],
    planner_summary: dict[str, Any] | None = None,
    output_mode: str = "summary",
) -> str:
    mode = to_text(output_mode).lower() or "summary"
    if mode not in {"summary", "verbose", "silent"}:
        mode = "summary"

    if mode == "silent" and not dispatch_errors:
        return "NO_REPLY"

    if not dispatched and skipped_count == 0 and not dispatch_errors:
        return "NO_REPLY"

    detail_lines: list[str] = []
    if dispatched:
        for idx, row in enumerate(dispatched[:8], start=1):
            task_row = row["task"]
            payload = row.get("payload", {}) if isinstance(row, dict) else {}
            context_payload = payload.get("context_payload", {}) if isinstance(payload, dict) else {}
            if not isinstance(context_payload, dict):
                context_payload = {}
            detail_lines.append(f"任务{idx}：{build_dispatch_subject(task_row, context_payload)}")
            detail_lines.append(f"要求{idx}：{build_dispatch_requirement(task_row)}")
            detail_lines.append(f"状态{idx}：{build_dispatch_status(task_row)}")
            detail_lines.append(f"值得做{idx}：{explain_dispatch_value(task_row)}")
            if bool(task_row.get("needs_clarification")):
                clar_reason = to_text(task_row.get("clarification_reason")) or "上下文仍需补充"
                detail_lines.append(f"澄清要求{idx}：{clar_reason}")

    judgement = build_dispatch_judgement(dispatched, dispatch_errors)
    if dispatch_errors:
        for idx, err in enumerate(dispatch_errors[:10], start=1):
            title, detail = humanize_dispatch_error(err)
            detail_lines.append(f"异常{idx}：{title}")
            detail_lines.append(f"详情{idx}：{detail}")

    extra_lines = [
        f"输出模式：{mode}",
        f"新增派发：{len(dispatched)} 项",
        f"跳过数量：{skipped_count} 项",
        f"跳过运维事件：{ops_incident_skipped_count} 项",
        f"运行异常：{len(dispatch_errors)} 项",
        f"运维事件过滤：{'开启' if skip_ops_incidents else '关闭'}",
    ]
    if judgement:
        extra_lines.insert(0, f"人工判断：{judgement}")
    summary = planner_summary if isinstance(planner_summary, dict) else {}
    if summary:
        extra_lines.append(
            "近24小时规划："
            f"任务 {summary.get('task_count', 0)} 项，"
            f"已解决 {summary.get('resolved_task_count', 0)} 项，"
            f"失败 {summary.get('failed_task_count', 0)} 项，"
            f"解决率 {summary.get('solved_ratio_pct', 0.0)}。"
        )

    if mode == "summary":
        if not dispatch_errors:
            return "NO_REPLY"
        return render_chat_notice(
            "任务巡检异常",
            status="需处理",
            task_id=task,
            sender_identity="coordinator/todo-patrol",
            run_time=now_iso(),
            trace_id=build_trace_id(report_file=state_file),
            summary=(
                f"任务巡检发现 {len(dispatch_errors)} 个异常，"
                f"本轮新增派发 {len(dispatched)} 项。"
            ),
            extra_lines=extra_lines,
            details=detail_lines,
            next_step="请按留痕编号查看内部记录，并优先处理巡检异常。",
        )

    return render_chat_notice(
        "任务巡检摘要" if not dispatch_errors else "任务巡检异常",
        status=("需处理" if dispatch_errors else "有更新"),
        task_id=task,
        sender_identity="coordinator/todo-patrol",
        run_time=now_iso(),
        trace_id=build_trace_id(report_file=state_file),
        summary=(
            f"任务巡检已新增派发 {len(dispatched)} 项，"
            f"跳过 {skipped_count} 项，异常 {len(dispatch_errors)} 项。"
        ),
        extra_lines=extra_lines,
        details=detail_lines,
        next_step=(
            "请按留痕编号查看内部记录，并优先处理巡检异常。"
            if dispatch_errors
            else "如需跟进，请按任务编号进入任务中心查看已派发任务。"
        ),
    )


def build_policy_create_args(payload: dict[str, Any], actor: str, entry_agent: str) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=to_text(payload.get("task_id")),
        task_type=to_text(payload.get("task_type")),
        reason=to_text(payload.get("reason")),
        source=to_text(payload.get("source")),
        request_source=to_text(payload.get("request_source")),
        priority=to_text(payload.get("priority")),
        risk_level=to_text(payload.get("risk_level")),
        pool=to_text(payload.get("pool")),
        assignee=to_text(payload.get("assignee")),
        owner=to_text(payload.get("owner")),
        change_id=to_text(payload.get("change_id")),
        entry_agent=to_text(entry_agent),
        need_human_confirm=str(bool(payload.get("need_human_confirm"))).lower(),
        human_confirmed=str(bool(payload.get("human_confirmed"))).lower(),
        requirement=to_text(payload.get("requirement")),
        result_output=to_text(payload.get("result_output")),
        acceptance=to_text(payload.get("acceptance")),
        observable_outputs=to_text(payload.get("observable_outputs")),
        acceptance_thresholds=to_text(payload.get("acceptance_thresholds")),
        context_json=json.dumps(payload.get("context_payload", {}), ensure_ascii=False),
        context_file="",
        force_needs_clarification=str(bool(payload.get("needs_clarification"))).lower(),
        clarification_reason=to_text(payload.get("clarification_reason")),
        scheduled_at=to_text(payload.get("scheduled_at")),
        actor=to_text(actor) or "coordinator",
    )


def build_policy_assign_args(task_id: str, assignee: str, actor: str) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=to_text(task_id),
        assignee=to_text(assignee),
        reason="todo_patrol_route",
        actor=to_text(actor) or "coordinator",
    )


def build_policy_log_module_args(
    *,
    task_id: str,
    actor: str,
    phase: str,
    level: str,
    status: str,
    message: str,
    duration_ms: int,
    details: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=to_text(task_id),
        module_name="coordinator/todo-patrol",
        phase=to_text(phase) or "dispatch",
        level=to_text(level) or "info",
        status=to_text(status) or "running",
        message=to_text(message),
        duration_ms=max(0, int(duration_ms or 0)),
        details_json=json.dumps(details or {}, ensure_ascii=False),
        actor=to_text(actor) or "coordinator",
    )


def build_policy_log_communication_args(
    *,
    task_id: str,
    actor: str,
    to_module: str,
    status: str,
    correlation_id: str,
    payload_ref: str,
    details: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=to_text(task_id),
        from_module="coordinator/todo-patrol",
        to_module=to_text(to_module) or "coordinator",
        protocol="policy-enforcer",
        message_type="task_dispatch",
        status=to_text(status) or "sent",
        latency_ms=0,
        correlation_id=to_text(correlation_id),
        payload_ref=to_text(payload_ref),
        details_json=json.dumps(details or {}, ensure_ascii=False),
        actor=to_text(actor) or "coordinator",
    )


def build_policy_report_result_args(
    *,
    task_id: str,
    actor: str,
    assignee: str,
    context_completeness: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=to_text(task_id),
        agent_id="coordinator",
        planner_id="coordinator",
        status="partial",
        solved="false",
        resolved_issues="task_dispatched",
        resolution_summary=f"task dispatched to {to_text(assignee) or 'unassigned'}",
        resolution_steps="route,create_task,assign_task",
        failed_items="",
        failure_count="0",
        duration_ms="0",
        model="",
        input_tokens="0",
        output_tokens="0",
        cost_estimate="0",
        quality_score=str(round(float(context_completeness or 0.0), 2)),
        quality_grade="b",
        notify_chat="false",
        details_json=json.dumps({"dispatch_stage": True}, ensure_ascii=False),
        actor=to_text(actor) or "coordinator",
    )


def build_policy_planner_summary_args(actor: str) -> SimpleNamespace:
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
    return SimpleNamespace(
        planner_id=to_text(actor) or "coordinator",
        since=since,
        limit="60",
    )


def main() -> int:
    home = Path(os.path.expanduser("~"))
    default_openclaw_home = Path(os.environ.get("OPENCLAW_HOME", str(home / ".openclaw"))).expanduser()
    default_ops_dir = Path(os.environ.get("OPENCLAW_OPS_DIR", str(default_openclaw_home / "ops"))).expanduser()
    default_policy_dir = Path(os.environ.get("OPENCLAW_POLICY_ROOT", str(default_ops_dir / "policy"))).expanduser()
    default_coordinator_ws = Path(
        os.environ.get("COORDINATOR_WORKSPACE", str(default_openclaw_home / "workspace-coordinator"))
    ).expanduser()

    parser = argparse.ArgumentParser(description="TODO patrol with source-aware dispatch")
    parser.add_argument("--task", default="cron:todo-patrol")
    parser.add_argument("--ops-dir", default=str(default_ops_dir))
    parser.add_argument("--todo-file", default=str(default_coordinator_ws / "TODO.md"))
    parser.add_argument("--state-file", default=str(default_ops_dir / "todo-patrol-state.json"))
    parser.add_argument("--task-db", default=str(default_ops_dir / "task-center/task_center.db"))
    parser.add_argument("--routing-file", default=str(default_policy_dir / "routing-rules.json"))
    parser.add_argument("--policy-file", default=str(default_policy_dir / "policy-config.json"))
    parser.add_argument("--pricing-file", default=str(default_policy_dir / "token-pricing.json"))
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--entry-agent", default="coordinator")
    parser.add_argument("--max-dispatch", type=int, default=5)
    parser.add_argument("--default-request-source", default="human", choices=["human", "ai"])
    parser.add_argument("--ai-context-min-pct", type=float, default=100.0)
    parser.add_argument("--clarification-assignee", default="")
    parser.add_argument("--no-auto-assign", action="store_true")
    parser.add_argument("--skip-ops-incidents", dest="skip_ops_incidents", action="store_true", default=True)
    parser.add_argument("--allow-ops-incidents", dest="skip_ops_incidents", action="store_false")
    parser.add_argument("--output-mode", default="summary", choices=["summary", "verbose", "silent"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    todo_file = Path(args.todo_file).expanduser()
    state_file = Path(args.state_file).expanduser()
    task_db = Path(args.task_db).expanduser()
    routing_file = Path(args.routing_file).expanduser()
    policy_file = Path(args.policy_file).expanduser()
    pricing_file = Path(args.pricing_file).expanduser()
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
        to_text(args.clarification_assignee)
        or to_text(routing.get("clarification_assignee"))
        or "project-agent"
    )

    todo_content = todo_file.read_text(encoding="utf-8-sig")
    todo_items = parse_todo_items(todo_content)
    if not todo_items:
        print("NO_REPLY")
        return 0

    if args.skip_ops_incidents:
        eligible_items = [item for item in todo_items if not is_ops_incident_item(item)]
        ops_incident_skipped_count = len(todo_items) - len(eligible_items)
    else:
        eligible_items = list(todo_items)
        ops_incident_skipped_count = 0

    dispatch_candidates = eligible_items[:max_dispatch]
    skipped_count = max(0, len(eligible_items) - len(dispatch_candidates))

    if args.no_auto_assign:
        msg = format_dispatch_message(
            task=args.task,
            todo_file=todo_file,
            dispatched=[],
            skipped_count=len(eligible_items),
            ops_incident_skipped_count=ops_incident_skipped_count,
            skip_ops_incidents=bool(args.skip_ops_incidents),
            db_path=task_db,
            state_file=state_file,
            dispatch_errors=[],
            output_mode=args.output_mode,
        )
        print(msg)
        return 0

    lines = todo_content.splitlines()
    dispatched: list[dict[str, Any]] = []
    dispatch_errors: list[str] = []
    planner_summary_snapshot: dict[str, Any] = {}
    run_started_at = now_tz()

    def make_task_row(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": payload["task_id"],
            "assignee": payload["assignee"],
            "owner": payload.get("owner", ""),
            "change_id": payload.get("change_id", ""),
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
            "context_fields_recommended_missing": payload.get("context_fields_recommended_missing", []),
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
                    "context_fields_recommended_missing": [],
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
        enforcer = None
        try:
            script_dir = Path(__file__).resolve().parent
            policy_dir = script_dir / "policy"
            if str(policy_dir) not in sys.path:
                sys.path.insert(0, str(policy_dir))
            try:
                from policy_enforcer import PolicyEnforcer, PolicyError, RuntimePaths, TaskCenterError, cmd_init
            except Exception as exc:  # pragma: no cover
                print(
                    render_chat_notice(
                        "任务巡检异常",
                        status="需处理",
                        task_id=str(args.task),
                        sender_identity="coordinator/todo-patrol",
                        run_time=now_iso(),
                        trace_id=build_trace_id(report_file=state_file),
                        summary="任务巡检无法启动，策略执行器导入失败。",
                        details=[f"详情：{exc}"],
                        next_step="请先检查策略模块路径和运行环境，再重新执行任务巡检。",
                    )
                )
                return 0

            task_db.parent.mkdir(parents=True, exist_ok=True)
            runtime_paths = RuntimePaths(
                db=task_db,
                policy_file=policy_file,
                routing_file=routing_file,
                pricing_file=pricing_file,
            )
            cmd_init(paths=runtime_paths, force=False)
            enforcer = PolicyEnforcer(runtime_paths)
            try:
                enforcer.log_module(
                    build_policy_log_module_args(
                        task_id="",
                        actor=str(args.actor),
                        phase="dispatch",
                        level="info",
                        status="started",
                        message=f"todo patrol started candidates={len(dispatch_candidates)}",
                        duration_ms=0,
                        details={
                            "task": str(args.task),
                            "todo_file": str(todo_file),
                            "max_dispatch": int(max_dispatch),
                        },
                    )
                )
            except Exception as exc:
                dispatch_errors.append(f"log_module_start_failed:{exc}")

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
                        "context_fields_recommended_missing": [],
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
                    task_row = enforcer.create_task(
                        build_policy_create_args(payload=payload, actor=args.actor, entry_agent=args.entry_agent)
                    )
                    created_new = True
                except TaskCenterError as exc:
                    if "task_id already exists" not in str(exc):
                        raise
                    task_row = enforcer.db.get_task(task_id)

                if to_text(task_row.get("assignee")) != to_text(payload.get("assignee")):
                    try:
                        task_row = enforcer.assign_task(
                            build_policy_assign_args(
                                task_id=task_id,
                                assignee=to_text(payload.get("assignee")),
                                actor=args.actor,
                            )
                        )
                    except PolicyError as exc:
                        dispatch_errors.append(f"task={task_id} assign_failed={exc}")

                enforcer.db.add_event(
                    task_id=task_id,
                    actor=to_text(args.actor) or "coordinator",
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
                        "information_flow": payload.get("context_payload", {}).get("information_flow", {}),
                    },
                )
                try:
                    enforcer.log_communication(
                        build_policy_log_communication_args(
                            task_id=task_id,
                            actor=str(args.actor),
                            to_module=to_text(task_row.get("assignee")) or "coordinator",
                            status="sent",
                            correlation_id=item.item_id,
                            payload_ref=str(todo_file),
                            details={
                                "route_assignee": to_text(task_row.get("assignee")) or payload.get("assignee"),
                                "priority": payload.get("priority"),
                                "risk_level": payload.get("risk_level"),
                                "request_source": request_source,
                            },
                        )
                    )
                except Exception as exc:
                    dispatch_errors.append(f"task={task_id} log_communication_failed={exc}")
                try:
                    enforcer.report_agent_result(
                        build_policy_report_result_args(
                            task_id=task_id,
                            actor=str(args.actor),
                            assignee=to_text(task_row.get("assignee")) or payload.get("assignee", ""),
                            context_completeness=float(task_row.get("context_completeness", 0.0) or 0.0),
                        )
                    )
                except Exception as exc:
                    dispatch_errors.append(f"task={task_id} report_agent_result_failed={exc}")

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
                        "assignee": to_text(task_row.get("assignee")) or payload["assignee"],
                        "owner": to_text(task_row.get("owner")) or payload.get("owner", ""),
                        "change_id": to_text(task_row.get("change_id")) or payload.get("change_id", ""),
                        "needs_clarification": bool(task_row.get("needs_clarification", payload["needs_clarification"])),
                        "context_completeness": task_row.get("context_completeness", payload["context_completeness"]),
                        "context_fields_missing": task_row.get("context_fields_missing", payload["context_fields_missing"]),
                        "context_fields_recommended_missing": task_row.get(
                            "context_fields_recommended_missing",
                            payload["context_fields_recommended_missing"],
                        ),
                    }
                )

                if 0 < item.line_num <= len(lines):
                    lines[item.line_num - 1] = mark_item_processed(lines[item.line_num - 1], task_id, payload, route)

                dispatched.append({"item": item, "task": task_row, "route": route, "payload": payload})
        except Exception as exc:
            dispatch_errors.append(str(exc))
        finally:
            if enforcer is not None:
                run_duration_ms = max(0, int((now_tz() - run_started_at).total_seconds() * 1000))
                try:
                    summary_raw = enforcer.planner_summary(build_policy_planner_summary_args(str(args.actor)))
                    if isinstance(summary_raw, dict):
                        planner_summary_snapshot = {
                            "planner_id": summary_raw.get("planner_id"),
                            "report_count": summary_raw.get("report_count", 0),
                            "task_count": summary_raw.get("task_count", 0),
                            "resolved_task_count": summary_raw.get("resolved_task_count", 0),
                            "failed_task_count": summary_raw.get("failed_task_count", 0),
                            "solved_ratio_pct": summary_raw.get("solved_ratio_pct", 0.0),
                            "total_tokens": summary_raw.get("total_tokens", 0),
                            "total_cost_estimate": summary_raw.get("total_cost_estimate", 0.0),
                        }
                except Exception as exc:
                    dispatch_errors.append(f"planner_summary_failed:{exc}")
                try:
                    enforcer.log_module(
                        build_policy_log_module_args(
                            task_id="",
                            actor=str(args.actor),
                            phase="dispatch",
                            level=("error" if dispatch_errors else "info"),
                            status=("failed" if dispatch_errors else "passed"),
                            message=(
                                "todo patrol finished: "
                                + f"dispatched={len(dispatched)} skipped={skipped_count} errors={len(dispatch_errors)}"
                            ),
                            duration_ms=run_duration_ms,
                            details={
                                "task": str(args.task),
                                "dispatched_count": len(dispatched),
                                "skipped_count": skipped_count,
                                "ops_incident_skipped_count": ops_incident_skipped_count,
                            },
                        )
                    )
                except Exception as exc:
                    dispatch_errors.append(f"log_module_finish_failed:{exc}")
                enforcer.close()

    if dispatched and not args.dry_run:
        atomic_write_text(
            todo_file,
            "\n".join(lines).rstrip() + "\n",
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
    if not args.dry_run:
        state["updated_at"] = now_iso()
        save_json(state_file, state)

    msg = format_dispatch_message(
        task=args.task,
        todo_file=todo_file,
        dispatched=dispatched,
        skipped_count=skipped_count,
        ops_incident_skipped_count=ops_incident_skipped_count,
        skip_ops_incidents=bool(args.skip_ops_incidents),
        db_path=task_db,
        state_file=state_file,
        dispatch_errors=dispatch_errors,
        planner_summary=planner_summary_snapshot,
        output_mode=args.output_mode,
    )
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

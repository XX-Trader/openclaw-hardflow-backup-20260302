"""Shared manual route-selection policy for Task Center entries."""

from __future__ import annotations

from typing import Any


PIPELINE_ROUTE_CHOICES = frozenset({"coding_workflow", "todo_auto_candidate"})
NON_PIPELINE_ROUTE_ACTIONS = {
    "direct_run": "manual_direct_run_requested",
    "requirement_discussion": "requirement_discussion_requested",
    "specified_agent": "specified_agent_requested",
}
VALID_ROUTE_CHOICES = PIPELINE_ROUTE_CHOICES | frozenset(NON_PIPELINE_ROUTE_ACTIONS)
PIPELINE_ROUTE_ACTION = "confirmed_for_execution"
AWAIT_ROUTE_SELECTION_ACTION = "await_route_selection"
ROUTE_SELECTION_OPTIONS = (
    {
        "id": "direct_run",
        "label": "直接运行",
        "description": "当前主 agent 直接处理，不进入工作流或子代理。",
    },
    {
        "id": "requirement_discussion",
        "label": "需求探讨",
        "description": "先澄清目标、范围、风险和验收，不改代码。",
    },
    {
        "id": "specified_agent",
        "label": "指定 agent",
        "description": "由人工指定 project-agent、researcher、tester 等 agent。",
    },
    {
        "id": "coding_workflow",
        "label": "指定编码工作流",
        "description": "进入完整交付链路，包含测试、审查和写回门禁。",
    },
    {
        "id": "todo_auto_candidate",
        "label": "TODO 自动候选",
        "description": "确认后才允许 backlog runner 作为低风险候选推进。",
    },
)


def route_selection_options() -> list[dict[str, str]]:
    return [dict(item) for item in ROUTE_SELECTION_OPTIONS]


def route_choice_action(selected_route: str) -> str:
    route = str(selected_route or "").strip().lower()
    if route in PIPELINE_ROUTE_CHOICES:
        return PIPELINE_ROUTE_ACTION
    if route in NON_PIPELINE_ROUTE_ACTIONS:
        return NON_PIPELINE_ROUTE_ACTIONS[route]
    raise ValueError("selected_route must be one of: " + ", ".join(sorted(VALID_ROUTE_CHOICES)))


def build_route_selection(
    *,
    risk_level: str,
    needs_clarification: bool = False,
    workflow_profile_id: str = "",
    task_type: str = "",
    require_manual: bool = True,
) -> dict[str, Any]:
    profile = str(workflow_profile_id or "").strip()
    kind = str(task_type or "").strip().lower()
    risk = str(risk_level or "").strip().lower()
    recommended_route = "direct_run"
    recommendation_reason = "范围和风险较低，推荐由当前主 agent 直接处理。"

    if needs_clarification:
        recommended_route = "requirement_discussion"
        recommendation_reason = "上下文或需求包不完整，推荐先做需求探讨。"
    elif risk == "high":
        recommended_route = "coding_workflow"
        recommendation_reason = "命中高风险，需要完整工作流和人工门禁。"
    elif kind in {"todo_deadline_candidate", "todo_dispatch"}:
        recommended_route = "todo_auto_candidate"
        recommendation_reason = "到期 TODO 可交给受控待办推进，但仍需人工选择确认。"
    elif profile in {"coding-default", "ops-default"}:
        recommended_route = "coding_workflow"
        recommendation_reason = f"选择器命中 {profile}，推荐走完整工作流。"
    elif profile == "research-default":
        recommended_route = "specified_agent"
        recommendation_reason = "选择器命中外部资料核对，推荐指定 researcher 类 agent。"
    elif profile == "docs-default":
        recommended_route = "direct_run"
        recommendation_reason = "文档类低风险任务，推荐当前主 agent 直接处理并同步记忆。"

    return {
        "mode": "manual_selection" if require_manual else "auto_recommendation",
        "required": bool(require_manual),
        "recommended_route": recommended_route,
        "recommendation_reason": recommendation_reason,
        "options": route_selection_options(),
    }

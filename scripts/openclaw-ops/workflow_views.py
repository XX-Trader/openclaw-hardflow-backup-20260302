#!/usr/bin/env python3
"""Unified workflow event + human view rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chat_output import format_beijing_time

SUCCESS_STATUSES = {"passed", "resolved", "solved", "ok", "success"}
PARTIAL_STATUSES = {"partial", "escalated"}
FAILED_STATUSES = {"failed", "error", "timeout"}
IGNORED_STATUSES = {"skipped", "needs_clarification", "waiting_human_confirm"}
NOTIFY_ON_MODES = {"error", "activity", "always"}


@dataclass(frozen=True)
class WorkflowDisplayMeta:
    title: str
    cadence: str = ""

    def render(self, include_cadence: bool = True) -> str:
        if include_cadence and self.cadence:
            return f"{self.title}（{self.cadence}）"
        return self.title


WORKFLOW_DISPLAY_META: dict[str, WorkflowDisplayMeta] = {
    "ops_git_sync_push": WorkflowDisplayMeta("Git 同步推送", "6小时"),
    "ops_local_openclaw_git_backup": WorkflowDisplayMeta("OpenClaw 本地备份", "1小时"),
    "web_intel_collect_hourly": WorkflowDisplayMeta("Web 情报采集", "1小时"),
    "web_intel_review_optimization_4h": WorkflowDisplayMeta("Web 情报优化复核", "4小时"),
    "web_intel_review_project_docs_6h": WorkflowDisplayMeta("项目文档情报复核", "6小时"),
    "project_index_maintainer_30m": WorkflowDisplayMeta("项目索引维护", "按 Git 更新 / 4小时兜底"),
    "reviewer_incremental_daily_4am": WorkflowDisplayMeta("每日增量审查", "每日 04:00"),
    "reviewer_git_update_hourly": WorkflowDisplayMeta("每小时代码审查", "每小时"),
    "reviewer_recurring_bi_daily": WorkflowDisplayMeta("双日复发问题审查"),
    "reviewer_weekly_structure_review": WorkflowDisplayMeta("每周结构审查", "每周一"),
    "ops_incremental_monitor": WorkflowDisplayMeta("运维增量巡检", "15分钟"),
    "ops_full_calibration": WorkflowDisplayMeta("运维全量巡检", "6小时"),
    "ops_daily_summary": WorkflowDisplayMeta("运维每日汇总", "每日"),
    "ops_system_schedule_audit": WorkflowDisplayMeta("系统调度审计"),
    "ops_api_test": WorkflowDisplayMeta("API 巡检"),
    "ops_daily_work_report_dingtalk": WorkflowDisplayMeta("工作日报汇总", "每日"),
    "ops_self_evolution_weekly_todo": WorkflowDisplayMeta("每周自进化复盘", "每周"),
    "ops_conversation_evolution": WorkflowDisplayMeta("对话进化扫描"),
    "ops_governance_evolution_incremental": WorkflowDisplayMeta("治理进化扫描"),
    "ops_github_web_evolution_incremental": WorkflowDisplayMeta("GitHub 生态扫描"),
    "ops_auto_update_install_hourly": WorkflowDisplayMeta("自动更新安装", "每小时"),
    "todo_patrol_15m": WorkflowDisplayMeta("待办巡检分发", "15分钟"),
    "task_executor_10m": WorkflowDisplayMeta("任务执行器", "10分钟"),
}

WORKFLOW_NAME_ALIASES: dict[str, str] = {
    "cron:ops-incremental-monitor": "ops_incremental_monitor",
    "cron:ops-full-calibration": "ops_full_calibration",
    "cron:ops-daily-summary": "ops_daily_summary",
    "cron:ops-system-schedule-audit": "ops_system_schedule_audit",
    "cron:ops-api-test": "ops_api_test",
    "cron:ops-daily-work-report": "ops_daily_work_report_dingtalk",
    "cron:ops-self-evolution": "ops_self_evolution_weekly_todo",
    "cron:ops-conversation-evolution": "ops_conversation_evolution",
    "cron:ops-governance-evolution": "ops_governance_evolution_incremental",
    "cron:ops-github-web-evolution": "ops_github_web_evolution_incremental",
    "cron:ops-git-sync-push": "ops_git_sync_push",
    "cron:ops-auto-update-install": "ops_auto_update_install_hourly",
    "cron:ops-local-openclaw-git-backup": "ops_local_openclaw_git_backup",
    "cron:task-executor": "task_executor_10m",
    "cron:todo-patrol": "todo_patrol_15m",
}

OPS_SCAN_MODE_KEYS = {
    "incremental": "ops_incremental_monitor",
    "full": "ops_full_calibration",
    "daily": "ops_daily_summary",
}


def normalize_notify_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in NOTIFY_ON_MODES else "error"


def normalize_result_status(item: dict[str, Any]) -> str:
    for key in ("report_status", "task_status_after", "status"):
        value = str(item.get(key, "")).strip().lower()
        if value:
            return value
    return ""


def classify_result(item: dict[str, Any]) -> str:
    status = normalize_result_status(item)
    if status in IGNORED_STATUSES:
        return "ignored"
    if status in SUCCESS_STATUSES:
        return "passed"
    if status in PARTIAL_STATUSES:
        return "partial"
    if status in FAILED_STATUSES:
        return "failed"
    reason = str(item.get("reason", "")).strip().lower()
    if reason in IGNORED_STATUSES:
        return "ignored"
    if reason in PARTIAL_STATUSES:
        return "partial"
    if reason in FAILED_STATUSES:
        return "failed"
    return "failed"


def humanize_executor_detail(detail: str) -> str:
    text = " ".join(str(detail or "").split())
    lower = text.lower()
    if lower in {"timeout", "timed out"}:
        return "超时"
    if lower == "waiting_human_confirm":
        return "等待人工确认"
    if lower == "needs_clarification":
        return "任务信息不足，需要补充上下文"
    return text or "未提供详细信息"


def humanize_executor_reason(item: dict[str, Any]) -> tuple[str, str]:
    status = classify_result(item)
    raw = (
        str(item.get("reason", "")).strip()
        or str(item.get("report_status", "")).strip()
        or str(item.get("task_status_after", "")).strip()
        or str(item.get("status", "")).strip()
        or "-"
    )
    lower = raw.lower()
    if lower == "preflight_strict_blocked":
        reassign = item.get("preflight_reassign", {})
        if not isinstance(reassign, dict):
            reassign = {}
        recommended_agents = reassign.get("recommended_agents", [])
        if not isinstance(recommended_agents, list):
            recommended_agents = []
        agent_text = ",".join(str(x).strip() for x in recommended_agents if str(x).strip())
        detail = "高风险任务未满足执行前能力约束，已阻止执行"
        if agent_text:
            detail += f"，建议改派：{agent_text}"
        return "派单能力不匹配", detail
    if lower.startswith("pre_stage_failed:model blocked by policy:"):
        model = raw.split(":", 2)[-1].strip() or "-"
        return "模型被策略拦截", f"执行前检查失败：模型 {model} 被策略禁止"
    if lower.startswith("pre_stage_failed:"):
        detail = raw.split(":", 1)[1].strip()
        return "执行前检查失败", humanize_executor_detail(detail)
    if lower.startswith("report_failed:"):
        detail = raw.split(":", 1)[1].strip()
        return "执行结果回写失败", humanize_executor_detail(detail)
    if lower.startswith("call_agent_exception:"):
        detail = raw.split(":", 1)[1].strip()
        return "调用执行代理失败", humanize_executor_detail(detail)
    if lower == "waiting_human_confirm":
        return "等待人工确认", "任务要求人工确认，当前尚未确认"
    if lower == "needs_clarification":
        return "上下文不足", "任务上下文不足，需要补充说明后再执行"
    if status == "partial":
        return "任务仅部分完成", humanize_executor_detail(raw or "仅部分完成")
    if status == "passed":
        return "任务已完成", humanize_executor_detail(raw)
    return "任务执行失败", humanize_executor_detail(raw)


def _make_event(kind: str, facts: dict[str, Any], human_view: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "facts": facts,
        "views": {
            "human": human_view,
            "agent": {
                "kind": kind,
                "facts": facts,
            },
            "external": {
                "kind": kind,
                "enabled": bool(human_view.get("visible", False)),
            },
            "storage": facts,
        },
    }


def render_human_view(view: dict[str, Any]) -> str:
    if not isinstance(view, dict) or not bool(view.get("visible", False)):
        return "NO_REPLY"
    title = str(view.get("title", "")).strip() or "系统通知"
    summary = str(view.get("summary", "")).strip()
    headline = f"{format_beijing_time(str(view.get('run_time', '')).strip())} {title}"
    if summary:
        headline = f"{headline}：{summary}"
    lines = [headline]
    for line in view.get("lines", []):
        text = str(line or "").rstrip()
        if text:
            lines.append(text)
    trace_id = str(view.get("trace_id", "")).strip()
    if trace_id:
        lines.append(f"- 留痕编号：{trace_id}")
    return "\n".join(lines)


def build_follow_up_progress_lines(summary: dict[str, Any]) -> list[str]:
    created_count = int(summary.get("created_count", 0) or 0)
    existing_count = int(summary.get("existing_count", 0) or 0)
    pending_count = int(summary.get("pending_count", existing_count) or 0)
    tasks = summary.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    errors = summary.get("errors", [])
    if not isinstance(errors, list):
        errors = []
    if created_count <= 0 and pending_count <= 0 and not errors:
        return []

    lines = [
        (
            f"- 修复进展: 新建修复任务 {created_count} 条，"
            f"已有待处理修复任务 {pending_count} 条。"
        )
    ]
    if tasks:
        lines.append("- 已派生修复任务:")
        for idx, item in enumerate(tasks[:3], start=1):
            if not isinstance(item, dict):
                continue
            workflow_name = str(item.get("workflow_job_name", "")).strip()
            task_id = str(item.get("task_id", "")).strip() or "-"
            assignee = str(item.get("assignee", "")).strip() or "-"
            status = str(item.get("status", "")).strip() or "created"
            label = humanize_workflow_job_name(workflow_name) if workflow_name else task_id
            lines.append(f"  {idx}. {label} -> {assignee} ({status})")
    if errors:
        lines.append("- 修复建单异常:")
        for idx, err in enumerate(errors[:3], start=1):
            lines.append(f"  {idx}. {str(err)[:180]}")
    return lines


def compact_task_text(value: Any, max_len: int = 72) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def format_duration_ms_human(value: Any) -> str:
    duration_ms = max(0, int(value or 0))
    if duration_ms <= 0:
        return "未记录"
    if duration_ms < 1000:
        return f"{duration_ms}毫秒"
    duration_sec = duration_ms / 1000.0
    if duration_sec < 60:
        if abs(duration_sec - round(duration_sec)) < 0.05:
            return f"{int(round(duration_sec))}秒"
        return f"{duration_sec:.1f}秒"
    minutes = int(duration_sec // 60)
    remain_sec = duration_sec - (minutes * 60)
    if abs(remain_sec - round(remain_sec)) < 0.05:
        remain_text = f"{int(round(remain_sec))}秒"
    else:
        remain_text = f"{remain_sec:.1f}秒"
    if remain_sec <= 0.05:
        return f"{minutes}分"
    return f"{minutes}分{remain_text}"


def format_cost_estimate(value: Any) -> str:
    try:
        cost_value = float(value or 0.0)
    except Exception:
        cost_value = 0.0
    if cost_value <= 0:
        return "未记录"
    return f"${cost_value:.6f}"


def humanize_task_stage(stage: str) -> str:
    normalized = str(stage or "").strip().lower()
    if normalized == "plan":
        return "规划"
    if normalized in {"implement", "implementation"}:
        return "实现"
    if normalized in {"test-loop", "test"}:
        return "验证"
    if normalized == "review":
        return "审查"
    if normalized == "document":
        return "文档"
    if normalized == "deploy":
        return "部署"
    return ""


def describe_task_subject(item: dict[str, Any]) -> str:
    requirement = compact_task_text(item.get("task_requirement", ""), 88)
    if requirement:
        return requirement
    task_reason = compact_task_text(item.get("task_reason", ""), 72)
    if task_reason and task_reason.lower() not in IGNORED_STATUSES:
        return task_reason
    task_type = compact_task_text(item.get("task_type", ""), 40)
    if task_type:
        return f"{task_type} 任务"
    return "未命名任务"


def humanize_selected_task_status(item: dict[str, Any]) -> str:
    raw_reason = str(item.get("reason", "")).strip().lower()
    category = classify_result(item)
    if raw_reason == "waiting_human_confirm":
        return "等待人工确认"
    if raw_reason == "needs_clarification":
        return "待补充上下文"
    if category == "passed":
        return "已完成"
    if category == "partial":
        return "部分完成"
    if category == "failed":
        issue, _detail = humanize_executor_reason(item)
        return issue
    return "已跳过"


def describe_selected_task(item: dict[str, Any]) -> str:
    assignee = str(item.get("assignee", "")).strip()
    stage_label = humanize_task_stage(str(item.get("stage", "")).strip())
    subject = describe_task_subject(item)
    status_label = humanize_selected_task_status(item)
    owner = assignee or "未分配"
    if stage_label:
        owner = f"{owner} / {stage_label}"
    return f"{owner}：{subject}（{status_label}）"


def build_executor_task_requirement(item: dict[str, Any]) -> str:
    requirement = compact_task_text(item.get("task_requirement", ""), 96)
    task_reason = compact_task_text(item.get("task_reason", ""), 88)
    if requirement and task_reason and requirement != task_reason:
        return f"{requirement} 背景：{task_reason}"
    if requirement:
        return requirement
    if task_reason:
        return task_reason
    task_type = compact_task_text(item.get("task_type", ""), 64)
    if task_type:
        return f"补齐 {task_type} 的执行上下文，再决定下一步动作。"
    return "当前只记录了执行结果，缺少明确任务要求。"


def build_executor_task_status(item: dict[str, Any]) -> str:
    assignee = str(item.get("assignee", "")).strip() or "未分配"
    stage_label = humanize_task_stage(str(item.get("stage", "")).strip())
    raw_reason = str(item.get("reason", "")).strip().lower()
    category = classify_result(item)
    if raw_reason == "waiting_human_confirm":
        status_label = "等待人工确认"
    elif raw_reason == "needs_clarification":
        status_label = "待补充上下文"
    elif raw_reason == "preflight_strict_blocked":
        status_label = "任务被门禁拦截"
    elif category == "passed":
        status_label = "已完成"
    elif category == "partial":
        status_label = "部分完成"
    elif category == "failed":
        status_label = "任务执行失败"
    else:
        status_label = "状态待确认"
    detail_parts = [f"负责人={assignee}"]
    if stage_label:
        detail_parts.append(f"阶段={stage_label}")
    return f"{status_label}（{'，'.join(detail_parts)}）"


def build_executor_failure_reason_text(item: dict[str, Any]) -> str:
    failed_items = item.get("failed_items", [])
    if isinstance(failed_items, list):
        normalized = [compact_task_text(part, 96) for part in failed_items if compact_task_text(part, 96)]
        if normalized:
            return normalized[0]
    resolution_summary = compact_task_text(item.get("resolution_summary", ""), 96)
    if resolution_summary:
        return resolution_summary
    issue, detail = humanize_executor_reason(item)
    if detail and detail != issue:
        return compact_task_text(f"{issue}：{detail}", 96)
    return compact_task_text(detail or issue, 96)


def build_executor_failure_line(index: int, item: dict[str, Any]) -> str:
    category = classify_result(item)
    if category not in {"partial", "failed"}:
        return ""
    failure_count = max(0, int(item.get("failure_count", 0) or 0))
    if failure_count <= 0:
        failure_count = 1
    duration_text = format_duration_ms_human(item.get("duration_ms", 0))
    return (
        f"失败信息{index}：原因={build_executor_failure_reason_text(item) or '未记录'}；"
        f"失败次数={failure_count}次；最近耗时={duration_text}"
    )


def build_executor_execution_line(index: int, item: dict[str, Any]) -> str:
    model_name = compact_task_text(item.get("model", ""), 48) or "未记录"
    input_tokens = max(0, int(item.get("input_tokens", 0) or 0))
    output_tokens = max(0, int(item.get("output_tokens", 0) or 0))
    total_tokens = max(0, int(item.get("total_tokens", 0) or 0))
    if total_tokens <= 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    cost_text = format_cost_estimate(item.get("cost_estimate", 0))
    if model_name == "未记录" and total_tokens <= 0 and cost_text == "未记录":
        return ""
    token_text = f"总={total_tokens}（输入={input_tokens}，输出={output_tokens}）" if total_tokens > 0 else "未记录"
    return f"执行概况{index}：模型={model_name}；tokens={token_text}；成本≈{cost_text}"


def explain_executor_task_value(item: dict[str, Any]) -> str:
    raw_reason = str(item.get("reason", "")).strip().lower()
    category = classify_result(item)
    if raw_reason == "waiting_human_confirm":
        return "这项正在等人工拍板，不先确认会一直停在队列里。"
    if raw_reason == "needs_clarification":
        return "这项信息还不够，先补上下文才能避免重复返工。"
    if raw_reason == "preflight_strict_blocked":
        return "这项被能力门禁拦住了，先改派才能恢复执行。"
    if category == "partial":
        return "这项只完成了一部分，继续追进能更快收口。"
    if category == "failed":
        return "这项已经失败，不优先处理会继续阻塞后续动作。"
    return "这项是本轮的焦点任务，先看它最能判断当前执行质量。"


def select_focus_task_items(results: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for idx, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        raw_reason = str(item.get("reason", "")).strip().lower()
        category = classify_result(item)
        if raw_reason == "preflight_strict_blocked":
            bucket = 0
        elif category == "failed":
            bucket = 1
        elif category == "partial":
            bucket = 2
        elif raw_reason == "waiting_human_confirm":
            bucket = 3
        elif raw_reason == "needs_clarification":
            bucket = 4
        else:
            bucket = 5
        ranked.append((bucket, idx, item))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [item for _bucket, _idx, item in ranked[: max(1, int(limit))]]


def resolve_workflow_display_meta(name: Any) -> WorkflowDisplayMeta | None:
    normalized = str(name or "").strip()
    if not normalized:
        return None
    canonical = WORKFLOW_NAME_ALIASES.get(normalized, normalized)
    if canonical in WORKFLOW_DISPLAY_META:
        return WORKFLOW_DISPLAY_META[canonical]
    normalized_key = normalized.replace("-", "_")
    if normalized_key in WORKFLOW_DISPLAY_META:
        return WORKFLOW_DISPLAY_META[normalized_key]
    if normalized.startswith("cron:"):
        cron_key = normalized.removeprefix("cron:").replace("-", "_")
        return WORKFLOW_DISPLAY_META.get(cron_key)
    return None


def humanize_workflow_job_name(name: Any, include_cadence: bool = True) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        return "未命名工作流"
    meta = resolve_workflow_display_meta(normalized)
    if meta is not None:
        return meta.render(include_cadence=include_cadence)
    return compact_task_text(normalized.removeprefix("cron:"), 48)


def humanize_workflow_failure_reason(item: dict[str, Any]) -> str:
    last_error = str(item.get("last_error", "")).strip()
    signal = _classify_failure_signal(last_error)
    if signal == "timeout":
        return "执行超时"
    if signal == "network_error":
        return "网络错误"
    if signal == "missing_detail":
        return "缺少明确错误详情"
    return compact_task_text(last_error, 88) or "未提供失败原因"


def build_task_executor_event(summary: dict[str, Any], report_path: Path, notify_on: str) -> dict[str, Any]:
    mode = normalize_notify_mode(notify_on)
    dedupe = summary.get("alert_dedupe", {})
    results = summary.get("results", [])
    if not isinstance(results, list):
        results = []
    trigger_task_label = humanize_workflow_job_name(
        str(summary.get("trigger_task", "")).strip() or "task_executor_10m"
    )

    passed_items: list[dict[str, Any]] = []
    partial_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    ignored_items: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        bucket = classify_result(item)
        if bucket == "passed":
            passed_items.append(item)
        elif bucket == "partial":
            partial_items.append(item)
        elif bucket == "ignored":
            ignored_items.append(item)
        else:
            failed_items.append(item)

    selected = max(0, int(summary.get("tasks_selected", 0) or 0))
    executed = max(0, int(summary.get("tasks_executed", 0) or 0))
    skipped = max(0, int(summary.get("tasks_skipped", 0) or 0))
    unresolved = len(partial_items) + len(failed_items)
    waiting_confirm_items = [
        item
        for item in ignored_items
        if str(item.get("reason", "")).strip().lower() == "waiting_human_confirm"
        or str(item.get("status", "")).strip().lower() == "waiting_human_confirm"
        or str(item.get("report_status", "")).strip().lower() == "waiting_human_confirm"
        or str(item.get("task_status_after", "")).strip().lower() == "waiting_human_confirm"
    ]
    clarification_items = [
        item
        for item in ignored_items
        if str(item.get("reason", "")).strip().lower() == "needs_clarification"
        or str(item.get("status", "")).strip().lower() == "needs_clarification"
        or str(item.get("report_status", "")).strip().lower() == "needs_clarification"
        or str(item.get("task_status_after", "")).strip().lower() == "needs_clarification"
    ]
    visible = True
    if isinstance(dedupe, dict) and bool(dedupe.get("suppressed", False)):
        visible = False
    elif mode == "error" and unresolved <= 0:
        visible = False
    elif mode == "activity" and unresolved <= 0 and executed <= 0:
        visible = False

    waiting_confirm_count = max(len(waiting_confirm_items), skipped if waiting_confirm_items else 0)
    clarification_count = max(len(clarification_items), skipped if clarification_items else 0)

    if unresolved > 0:
        summary_text = f"选中 {selected} 个任务，未闭环 {unresolved} 个。"
    elif executed > 0:
        summary_text = f"已执行 {executed} 个任务，全部闭环。"
    elif waiting_confirm_items and skipped > 0:
        summary_text = f"{waiting_confirm_count} 个任务等待人工确认，本轮未执行。"
    elif clarification_items and skipped > 0:
        summary_text = f"{clarification_count} 个任务因上下文不足而跳过。"
    elif skipped > 0:
        summary_text = f"{skipped} 个任务已跳过，本轮未执行。"
    elif selected > 0:
        summary_text = f"选中 {selected} 个任务，本轮无需执行。"
    else:
        summary_text = "当前没有待处理任务。"

    reason_parts: list[str] = []
    if waiting_confirm_items:
        reason_parts.append(f"等待人工确认 {waiting_confirm_count} 个")
    if clarification_items:
        reason_parts.append(f"待补充上下文 {clarification_count} 个")
    if partial_items:
        reason_parts.append(f"任务仅部分完成 {len(partial_items)} 个")
    if failed_items:
        reason_parts.append(f"任务执行失败 {len(failed_items)} 个")

    lines = [
        f"- 触发任务：{trigger_task_label}",
        f"- 运行编号：{str(summary.get('run_id', '')).strip() or '-'}",
        f"- 执行模型：{str(summary.get('executor_model', '')).strip() or '-'}",
        (
            f"- 结果：选中 {selected} 个，已执行 {executed} 个，"
            f"跳过 {skipped} 个，未闭环 {unresolved} 个。"
        ),
    ]
    if reason_parts:
        lines.append(f"- 原因解析：{'；'.join(reason_parts)}。")
    lines.append(
        f"- 修复进展：已执行 {executed}/{selected or max(executed, 1)}，"
        f"部分推进 {len(partial_items)}，失败 {len(failed_items)}。"
    )
    preflight_warning_tasks = max(0, int(summary.get("preflight_warning_tasks", 0) or 0))
    preflight_blocked_tasks = max(0, int(summary.get("preflight_blocked_tasks", 0) or 0))
    if preflight_warning_tasks > 0:
        line = f"- Preflight 告警 {preflight_warning_tasks} 个"
        if preflight_blocked_tasks > 0:
            line += f"，强拦截 {preflight_blocked_tasks} 个高风险任务。"
        else:
            line += "。"
        lines.append(line)
    focus_items = select_focus_task_items(results, limit=3)
    if focus_items:
        for idx, item in enumerate(focus_items, start=1):
            lines.append(f"- 任务{idx}：{describe_task_subject(item)}")
            lines.append(f"- 要求{idx}：{build_executor_task_requirement(item)}")
            lines.append(f"- 状态{idx}：{build_executor_task_status(item)}")
            failure_line = build_executor_failure_line(idx, item)
            if failure_line:
                lines.append(f"- {failure_line}")
            execution_line = build_executor_execution_line(idx, item)
            if execution_line:
                lines.append(f"- {execution_line}")
            lines.append(f"- 值得做{idx}：{explain_executor_task_value(item)}")
        if len(results) > len(focus_items):
            lines.append(f"- 其余 {len(results) - len(focus_items)} 个任务请按留痕编号查看。")
    if passed_items:
        lines.append(f"- 已闭环：{len(passed_items)} 个")
    if waiting_confirm_items:
        lines.append(f"- 待人工确认：{waiting_confirm_count} 个")
    if clarification_items:
        lines.append(f"- 待补充上下文：{clarification_count} 个")
    unresolved_items = [*partial_items, *failed_items]

    human_view = {
        "visible": visible,
        "title": trigger_task_label,
        "summary": summary_text,
        "run_time": str(summary.get("finished_at", "")).strip() or str(summary.get("started_at", "")).strip(),
        "lines": lines,
        "trace_id": report_path.stem,
    }
    facts = {
        "trigger_task": str(summary.get("trigger_task", "")).strip(),
        "run_id": str(summary.get("run_id", "")).strip(),
        "started_at": str(summary.get("started_at", "")).strip(),
        "executor_model": str(summary.get("executor_model", "")).strip(),
        "tasks_selected": selected,
        "tasks_executed": executed,
        "tasks_skipped": skipped,
        "passed_count": len(passed_items),
        "partial_count": len(partial_items),
        "failed_count": len(failed_items),
        "report_file": str(report_path),
        "results": unresolved_items,
    }
    return _make_event("task_executor", facts, human_view)


def _extract_count(risk_reasons: list[str], prefix: str) -> int:
    for reason in risk_reasons:
        raw = str(reason or "").strip()
        if not raw.startswith(prefix):
            continue
        _, _, value = raw.partition("=")
        try:
            return max(0, int(value))
        except Exception:
            return 0
    return 0


def _classify_failure_signal(text: str) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return "missing_detail"
    if "timed out" in raw or "timeout" in raw:
        return "timeout"
    if "network_error" in raw or "network error" in raw:
        return "network_error"
    return "other"


def build_ops_scan_event(record: dict[str, Any]) -> dict[str, Any]:
    risk_reasons = [str(x).strip() for x in (record.get("risk_reasons") or []) if str(x).strip()]
    workflow_health = record.get("workflow_health", {})
    if not isinstance(workflow_health, dict):
        workflow_health = {}
    failed_jobs = workflow_health.get("failed_jobs", [])
    if not isinstance(failed_jobs, list):
        failed_jobs = []
    follow_up = record.get("workflow_follow_up_summary", {})
    if not isinstance(follow_up, dict):
        follow_up = {}
    runtime_health = record.get("runtime_health", {})
    if not isinstance(runtime_health, dict):
        runtime_health = {}
    runtime_missing = runtime_health.get("missing_required", [])
    if not isinstance(runtime_missing, list):
        runtime_missing = []
    scan_errors = record.get("scan_errors", [])
    if not isinstance(scan_errors, list):
        scan_errors = []
    handoff_summary = record.get("handoff_summary", {})
    if not isinstance(handoff_summary, dict):
        handoff_summary = {}

    failed_count = _extract_count(risk_reasons, "workflow_job_error")
    stale_failed_count = _extract_count(risk_reasons, "workflow_job_error_stale")
    if failed_count <= 0:
        failed_count = len(failed_jobs)

    counters = {"timeout": 0, "network_error": 0, "missing_detail": 0, "other": 0}
    for item in failed_jobs:
        if not isinstance(item, dict):
            continue
        counters[_classify_failure_signal(str(item.get("last_error", "")))] += 1

    reason_parts: list[str] = []
    if counters["timeout"] > 0:
        reason_parts.append(f"超时 {counters['timeout']} 项")
    if counters["network_error"] > 0:
        reason_parts.append(f"网络错误 {counters['network_error']} 项")
    if counters["missing_detail"] > 0:
        reason_parts.append(f"缺少明确错误详情 {counters['missing_detail']} 项")
    if counters["other"] > 0:
        reason_parts.append(f"其他失败 {counters['other']} 项")
    if not reason_parts and risk_reasons:
        reason_parts.append("存在风险信号，待进一步分诊")

    mode = str(record.get("mode", "")).strip().lower()
    raw_task_name = str(record.get("task_id", "")).strip()
    mode_task_name = OPS_SCAN_MODE_KEYS.get(mode, "")
    task_name = raw_task_name or mode_task_name
    title_meta = resolve_workflow_display_meta(task_name) or resolve_workflow_display_meta(mode_task_name)
    if title_meta is not None:
        title = title_meta.render()
    elif task_name:
        title = humanize_workflow_job_name(task_name)
    else:
        title = "运维巡检"
    summary_text = (
        f"发现 {failed_count} 个工作流失败，{stale_failed_count} 个持续失败。"
        if failed_count > 0
        else f"发现 {len(risk_reasons)} 个需关注信号。"
    )
    todo_new = int(handoff_summary.get("todo_new", 0) or 0)

    lines = [
        f"- 任务：{title}",
        f"- 运行编号：{str(record.get('run_id', '')).strip() or '-'}",
        (
            f"- 结果：风险信号 {len(risk_reasons)} 项，扫描异常 {len(scan_errors)} 项，"
            f"新增待办 {todo_new} 条。"
        ),
        f"- 原因解析：{'；'.join(reason_parts)}。",
    ]
    lines.extend(build_follow_up_progress_lines(follow_up))
    if runtime_missing:
        lines.append("- 缺失常驻进程/服务：")
        for idx, item in enumerate(runtime_missing[:5], start=1):
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  {idx}. {str(item.get('project_name', '-'))} / "
                f"{str(item.get('item_name', '-'))} "
                f"({str(item.get('type', '-'))}) -> {str(item.get('status', '-'))}"
            )
    if failed_jobs:
        lines.append("- 失败工作流：")
        for idx, item in enumerate(failed_jobs[:3], start=1):
            if not isinstance(item, dict):
                continue
            detail_parts: list[str] = []
            consecutive_errors = int(item.get("consecutive_errors", 0) or 0)
            if consecutive_errors > 0:
                detail_parts.append(f"连续失败 {consecutive_errors} 次")
            last_status = str(item.get("last_status", "")).strip()
            if last_status:
                detail_parts.append(f"状态 {last_status}")
            detail_text = f"（{'，'.join(detail_parts)}）" if detail_parts else ""
            lines.append(
                f"  {idx}. {humanize_workflow_job_name(item.get('name', ''))}："
                f"{humanize_workflow_failure_reason(item)}{detail_text}"
            )
    if scan_errors:
        lines.append("- 扫描错误：")
        for idx, err in enumerate(scan_errors[:3], start=1):
            lines.append(f"  {idx}. {str(err)[:180]}")
    if todo_new > 0:
        lines.append(f"- 已写入待办：{todo_new} 条")
    risk_notify_suppressed_reason = str(record.get("risk_notify_suppressed_reason", "")).strip()
    if risk_notify_suppressed_reason:
        lines.append(f"- 告警抑制：{risk_notify_suppressed_reason}")

    human_view = {
        "visible": failed_count > 0 or bool(risk_reasons),
        "title": title,
        "summary": summary_text,
        "run_time": str(record.get("time", "")).strip(),
        "lines": lines,
        "trace_id": str(record.get("run_id", "")).strip(),
    }
    facts = {
        "task_id": str(record.get("task_id", "")).strip(),
        "mode": str(record.get("mode", "")).strip(),
        "time": str(record.get("time", "")).strip(),
        "run_id": str(record.get("run_id", "")).strip(),
        "risk_reasons": risk_reasons,
        "workflow_health": workflow_health,
        "workflow_follow_up_summary": follow_up,
    }
    return _make_event("ops_scan", facts, human_view)

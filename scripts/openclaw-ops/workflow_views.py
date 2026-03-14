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
    "project_index_maintainer_30m": WorkflowDisplayMeta("项目索引维护", "30分钟"),
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

    lines = [
        f"- 触发任务：{trigger_task_label}",
        f"- 运行编号：{str(summary.get('run_id', '')).strip() or '-'}",
        f"- 执行模型：{str(summary.get('executor_model', '')).strip() or '-'}",
        (
            f"- 结果：选中 {selected} 个，已执行 {executed} 个，"
            f"跳过 {skipped} 个，未闭环 {unresolved} 个。"
        ),
    ]
    preflight_warning_tasks = max(0, int(summary.get("preflight_warning_tasks", 0) or 0))
    preflight_blocked_tasks = max(0, int(summary.get("preflight_blocked_tasks", 0) or 0))
    if preflight_warning_tasks > 0:
        line = f"- Preflight 告警 {preflight_warning_tasks} 个"
        if preflight_blocked_tasks > 0:
            line += f"，强拦截 {preflight_blocked_tasks} 个高风险任务。"
        else:
            line += "。"
        lines.append(line)
    if results:
        lines.append("- 本轮任务：")
        for idx, item in enumerate(results[:5], start=1):
            if not isinstance(item, dict):
                continue
            lines.append(f"  {idx}. {describe_selected_task(item)}")
        if len(results) > 5:
            lines.append(f"  - 其余 {len(results) - 5} 个任务请按留痕编号查看。")
    if passed_items:
        lines.append(f"- 已闭环：{len(passed_items)} 个")
    if waiting_confirm_items:
        lines.append(f"- 待人工确认：{waiting_confirm_count} 个")
    if clarification_items:
        lines.append(f"- 待补充上下文：{clarification_count} 个")
    unresolved_items = [*partial_items, *failed_items]
    if unresolved_items:
        lines.append("- 未闭环任务：")
        for item in unresolved_items[:8]:
            issue, detail = humanize_executor_reason(item)
            lines.append(f"  - {describe_selected_task(item)}：{issue}；{detail}")

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

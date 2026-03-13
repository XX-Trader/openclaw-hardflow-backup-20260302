#!/usr/bin/env python3
"""Unified workflow event + human view rendering helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUCCESS_STATUSES = {"passed", "resolved", "solved", "ok", "success"}
PARTIAL_STATUSES = {"partial", "escalated"}
FAILED_STATUSES = {"failed", "error", "timeout"}
IGNORED_STATUSES = {"skipped", "needs_clarification", "waiting_human_confirm"}
NOTIFY_ON_MODES = {"error", "activity", "always"}


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
    lines = [title]
    for line in view.get("lines", []):
        text = str(line or "").rstrip()
        if text:
            lines.append(text)
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
            label = workflow_name or task_id
            lines.append(f"  {idx}. {label} -> {assignee} ({status})")
    if errors:
        lines.append("- 修复建单异常:")
        for idx, err in enumerate(errors[:3], start=1):
            lines.append(f"  {idx}. {str(err)[:180]}")
    return lines


def build_task_executor_event(summary: dict[str, Any], report_path: Path, notify_on: str) -> dict[str, Any]:
    mode = normalize_notify_mode(notify_on)
    dedupe = summary.get("alert_dedupe", {})
    results = summary.get("results", [])
    if not isinstance(results, list):
        results = []

    passed_items: list[dict[str, Any]] = []
    partial_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        bucket = classify_result(item)
        if bucket == "passed":
            passed_items.append(item)
        elif bucket == "partial":
            partial_items.append(item)
        elif bucket == "ignored":
            continue
        else:
            failed_items.append(item)

    selected = max(0, int(summary.get("tasks_selected", 0) or 0))
    executed = max(0, int(summary.get("tasks_executed", 0) or 0))
    skipped = max(0, int(summary.get("tasks_skipped", 0) or 0))
    unresolved = len(partial_items) + len(failed_items)
    visible = True
    if isinstance(dedupe, dict) and bool(dedupe.get("suppressed", False)):
        visible = False
    elif mode == "error" and unresolved <= 0:
        visible = False
    elif mode == "activity" and unresolved <= 0 and executed <= 0:
        visible = False

    if unresolved <= 0:
        conclusion = f"本轮选中的 {selected} 个任务已闭环。"
    elif selected > 0 and unresolved >= selected:
        conclusion = f"本轮选中的 {selected} 个任务均未闭环。"
    else:
        conclusion = f"本轮选中的 {selected} 个任务里，仍有 {unresolved} 个未闭环。"

    reason_parts: list[str] = []
    if partial_items:
        reason_parts.append(f"任务仅部分完成 {len(partial_items)} 个")
    if failed_items:
        reason_parts.append(f"任务执行失败 {len(failed_items)} 个")
    if not reason_parts:
        reason_parts.append("未发现失败或部分完成项")

    lines = [
        f"- 触发任务: {str(summary.get('trigger_task', '')).strip() or '-'}",
        f"- 时间: {str(summary.get('started_at', '')).strip() or '-'}",
        f"- 运行 ID: {str(summary.get('run_id', '')).strip() or '-'}",
        f"- 执行模型: {str(summary.get('executor_model', '')).strip() or '-'}",
        f"- 选中任务: {selected}",
        f"- 已执行: {executed}",
        f"- 已跳过: {skipped}",
        f"- 失败任务: {unresolved}",
        f"- 报告文件: {report_path}",
        f"- 结论: {conclusion}",
        f"- 原因解析: {'；'.join(reason_parts)}。",
        (
            f"- 修复进展: 已执行 {executed}/{selected}，"
            f"已闭环 {len(passed_items)}，部分推进 {len(partial_items)}，失败 {len(failed_items)}。"
        ),
    ]
    unresolved_items = [*partial_items, *failed_items]
    if unresolved_items:
        lines.append("- 失败明细:")
        for item in unresolved_items[:8]:
            task_id = str(item.get("task_id", "")).strip() or "-"
            assignee = str(item.get("assignee", "")).strip() or "-"
            issue, detail = humanize_executor_reason(item)
            lines.append(f"  - 任务: {task_id}")
            lines.append(f"    执行人: {assignee}")
            lines.append(f"    问题: {issue}")
            lines.append(f"    详情: {detail}")

    human_view = {
        "visible": visible,
        "title": "任务执行异常" if unresolved > 0 else "任务执行摘要",
        "lines": lines,
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

    lines = [
        f"- 模式: {str(record.get('mode', '')).strip() or '-'}",
        f"- 时间: {str(record.get('time', '')).strip() or '-'}",
        f"- 任务: {str(record.get('task_id', '')).strip() or '-'}",
        f"- 运行编号: {str(record.get('run_id', '')).strip() or '-'}",
        f"- 结论: 当前有 {failed_count} 个工作流失败，其中 {stale_failed_count} 个持续失败仍未恢复。",
        f"- 原因解析: {'；'.join(reason_parts)}。",
    ]
    lines.extend(build_follow_up_progress_lines(follow_up))
    if runtime_missing:
        lines.append("- 常驻进程/服务缺失:")
        for idx, item in enumerate(runtime_missing[:5], start=1):
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  {idx}. {str(item.get('project_name', '-'))} / "
                f"{str(item.get('item_name', '-'))} "
                f"({str(item.get('type', '-'))}) -> {str(item.get('status', '-'))}"
            )
    if failed_jobs:
        lines.append("- 失败工作流:")
        for idx, item in enumerate(failed_jobs[:3], start=1):
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  {idx}. {str(item.get('id', '')).strip() or '-'} / "
                f"{str(item.get('name', '')).strip() or '-'} "
                f"(连续失败: {int(item.get('consecutive_errors', 0) or 0)}, "
                f"状态: {str(item.get('last_status', '')).strip() or '-'})"
            )
            if str(item.get("last_error", "")).strip():
                lines.append(f"     错误: {str(item.get('last_error', ''))[:160]}")
    if scan_errors:
        lines.append("- 扫描错误:")
        for idx, err in enumerate(scan_errors[:3], start=1):
            lines.append(f"  {idx}. {str(err)[:180]}")
    todo_new = int(handoff_summary.get("todo_new", 0) or 0)
    if todo_new > 0:
        lines.append(f"- 已写入待办: {todo_new} 条")
    risk_notify_suppressed_reason = str(record.get("risk_notify_suppressed_reason", "")).strip()
    if risk_notify_suppressed_reason:
        lines.append(f"- 告警抑制: {risk_notify_suppressed_reason}")

    human_view = {
        "visible": failed_count > 0 or bool(risk_reasons),
        "title": "运维巡检异常",
        "lines": lines,
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

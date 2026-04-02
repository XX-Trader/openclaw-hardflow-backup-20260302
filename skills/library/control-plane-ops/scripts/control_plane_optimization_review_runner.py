#!/usr/bin/env python3
"""Review dispatched control-plane optimization tasks and summarize execution readiness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import TaskCenter, parse_utc_iso, utc_now_iso  # type: ignore
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()

DISPATCH_SOURCE = "control-plane-optimization-dispatcher"
PENDING_STATUSES = {"pending", "running"}
COMPLETED_STATUSES = {"passed", "failed", "escalated", "cancelled"}


def _normalize_since(lookback_hours: int) -> str:
    """Build the UTC lower bound used for optimization-review queries."""

    return (
        datetime.now(tz=timezone.utc) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()


def _load_candidate_tasks(
    *,
    task_center: TaskCenter,
    since: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Load recent optimization tasks ordered by latest update time descending."""

    rows = task_center.conn.execute(
        """
        SELECT
            task_id,
            status,
            assignee,
            updated_at,
            workflow_profile_id,
            workflow_channel,
            stage_id,
            change_id,
            selection_inputs,
            context_payload
        FROM tasks
        WHERE source = ?
          AND updated_at >= ?
        ORDER BY updated_at DESC, task_id DESC
        LIMIT ?
        """,
        (DISPATCH_SOURCE, since, max(1, int(limit or 20))),
    ).fetchall()
    return [dict(row) for row in rows]


def _extract_recommendation_type(task: dict[str, Any]) -> str:
    """Extract optimization recommendation type from task metadata."""

    selection_inputs = task.get("selection_inputs", {})
    if isinstance(selection_inputs, dict):
        recommendation_type = str(selection_inputs.get("recommendation_type", "")).strip()
        if recommendation_type:
            return recommendation_type
    context_payload = task.get("context_payload", {})
    if isinstance(context_payload, dict):
        recommendation = context_payload.get("recommendation", {})
        if isinstance(recommendation, dict):
            recommendation_type = str(recommendation.get("type", "")).strip()
            if recommendation_type:
                return recommendation_type
    return ""


def _extract_target(task: dict[str, Any]) -> tuple[str, str, str]:
    """Extract target workflow/stage metadata from task payload."""

    context_payload = task.get("context_payload", {})
    if not isinstance(context_payload, dict):
        context_payload = {}
    target_workflow_profile_id = str(context_payload.get("target_workflow_profile_id", "")).strip()
    target_stage_id = str(context_payload.get("target_stage_id", "")).strip()
    target_stage_label = str(context_payload.get("target_stage_label", "")).strip()
    return (
        target_workflow_profile_id or "unknown-workflow",
        target_stage_id or "unknown-stage",
        target_stage_label or target_stage_id or "unknown-stage",
    )


def _extract_recommendation_payload(task: dict[str, Any]) -> dict[str, Any]:
    """Extract the normalized recommendation payload from task context."""

    context_payload = task.get("context_payload", {})
    if not isinstance(context_payload, dict):
        return {}
    recommendation = context_payload.get("recommendation", {})
    if isinstance(recommendation, dict):
        return recommendation
    return {}


def _build_blocking_reasons(report: dict[str, Any]) -> list[str]:
    """Build blocking reasons for one optimization task report."""

    task = report.get("task", {}) if isinstance(report.get("task", {}), dict) else {}
    control_plane = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
    status = str(task.get("status", "")).strip().lower()
    blocking_reasons: list[str] = []

    if status in PENDING_STATUSES:
        blocking_reasons.append("pending_execution")
    elif status != "passed":
        blocking_reasons.append(f"task_not_passed:{status or 'unknown'}")

    if int(control_plane.get("open_incident_count", 0) or 0) > 0:
        blocking_reasons.append("open_incidents")
    if int(control_plane.get("critical_open_incident_count", 0) or 0) > 0:
        blocking_reasons.append("critical_incidents")
    if bool(control_plane.get("requires_human_assistance", False)):
        blocking_reasons.append("requires_human_assistance")
    if bool(control_plane.get("waiting_human_confirm", False)):
        blocking_reasons.append("waiting_human_confirm")
    if bool(control_plane.get("needs_clarification", False)):
        blocking_reasons.append("needs_clarification")
    return blocking_reasons


def _build_profile_update_guard(
    *,
    task: dict[str, Any],
    recommendation_type: str,
    recommendation_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the review guard used before profile-update dispatch."""

    if recommendation_type != "stage_simplification_candidate":
        return (
            {
                "policy": "workflow_evolution.profile_update.default",
                "ready": True,
                "reasons": [],
            },
            {},
        )

    evidence = recommendation_payload.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    guard_reasons: list[str] = []
    if not evidence:
        guard_reasons.append("missing_simplification_evidence")
    if int(evidence.get("task_count", 0) or 0) < 3:
        guard_reasons.append("insufficient_simplification_task_count")
    if int(evidence.get("benchmark_promoted_count", 0) or 0) < 2:
        guard_reasons.append("insufficient_simplification_benchmark_promotions")
    if int(evidence.get("open_incident_task_count", 0) or 0) > 0:
        guard_reasons.append("simplification_open_incidents_present")
    if int(evidence.get("critical_incident_task_count", 0) or 0) > 0:
        guard_reasons.append("simplification_critical_incidents_present")
    if int(evidence.get("human_assistance_task_count", 0) or 0) > 0:
        guard_reasons.append("simplification_human_assistance_present")
    if int(evidence.get("waiting_human_confirm_task_count", 0) or 0) > 0:
        guard_reasons.append("simplification_waiting_human_confirm_present")
    if int(evidence.get("needs_clarification_task_count", 0) or 0) > 0:
        guard_reasons.append("simplification_needs_clarification_present")
    if int(evidence.get("benchmark_blocked_count", 0) or 0) > 0:
        guard_reasons.append("simplification_benchmark_blocked_present")
    return (
        {
            "policy": str(evidence.get("policy", "")).strip() or "workflow_evolution.stage_simplification.v1",
            "ready": len(guard_reasons) == 0,
            "reasons": guard_reasons,
        },
        evidence,
    )


def _build_review_item(report: dict[str, Any]) -> dict[str, Any]:
    """Convert one task report into optimization-review summary item."""

    task = report.get("task", {}) if isinstance(report.get("task", {}), dict) else {}
    target_workflow_profile_id, target_stage_id, target_stage_label = _extract_target(task)
    recommendation_type = _extract_recommendation_type(task)
    recommendation_payload = _extract_recommendation_payload(task)
    blocking_reasons = _build_blocking_reasons(report)
    status = str(task.get("status", "")).strip().lower()
    profile_update_guard, evidence_snapshot = _build_profile_update_guard(
        task=task,
        recommendation_type=recommendation_type,
        recommendation_payload=recommendation_payload,
    )
    for reason in profile_update_guard.get("reasons", []):
        if reason not in blocking_reasons:
            blocking_reasons.append(str(reason))
    latest_agent_report = {}
    agent_reports = report.get("agent_reports", [])
    if isinstance(agent_reports, list) and agent_reports:
        if isinstance(agent_reports[0], dict):
            latest_agent_report = agent_reports[0]
    return {
        "task_id": str(task.get("task_id", "")).strip(),
        "change_id": str(task.get("change_id", "")).strip(),
        "status": status,
        "assignee": str(task.get("assignee", "")).strip(),
        "updated_at": str(task.get("updated_at", "")).strip(),
        "execution_workflow_profile_id": str(task.get("workflow_profile_id", "")).strip(),
        "execution_workflow_channel": str(task.get("workflow_channel", "")).strip(),
        "execution_stage_id": str(task.get("stage_id", "")).strip(),
        "target_workflow_profile_id": target_workflow_profile_id,
        "target_stage_id": target_stage_id,
        "target_stage_label": target_stage_label,
        "recommendation_type": recommendation_type,
        "open_incident_count": int(report.get("control_plane", {}).get("open_incident_count", 0) or 0),
        "critical_open_incident_count": int(report.get("control_plane", {}).get("critical_open_incident_count", 0) or 0),
        "requires_human_assistance": bool(report.get("control_plane", {}).get("requires_human_assistance", False)),
        "waiting_human_confirm": bool(report.get("control_plane", {}).get("waiting_human_confirm", False)),
        "needs_clarification": bool(report.get("control_plane", {}).get("needs_clarification", False)),
        "blocking_reasons": blocking_reasons,
        "evidence_snapshot": evidence_snapshot,
        "profile_update_guard": profile_update_guard,
        "ready_for_profile_update": status == "passed" and not blocking_reasons and bool(profile_update_guard.get("ready", False)),
        "latest_agent_report_status": str(latest_agent_report.get("status", "")).strip(),
        "latest_agent_report_summary": str(latest_agent_report.get("resolution_summary", "")).strip(),
    }


def _merge_counts(counter: dict[str, int], key: str) -> None:
    """Increment one flat counter map."""

    counter[key] = counter.get(key, 0) + 1


def render_control_plane_optimization_review_markdown(report: dict[str, Any]) -> str:
    """Render one Markdown review report for dispatched optimization tasks."""

    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    items = report.get("items", []) if isinstance(report.get("items", []), list) else []
    lines = [
        "# OpenClaw Control Plane Optimization Review",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- 时间窗口：最近 {report.get('lookback_hours', 72)} 小时",
        f"- 扫描优化任务：{summary.get('task_count', 0)}",
        f"- 已完成：{summary.get('completed_count', 0)}，待执行：{summary.get('pending_count', 0)}，阻塞：{summary.get('blocked_count', 0)}",
        f"- 可进入 profile 更新评审：{summary.get('ready_for_profile_update_count', 0)}",
        "",
        "## 重点结果",
    ]
    if not items:
        lines.append("- 当前窗口内暂无 optimization task")
        return "\n".join(lines).rstrip() + "\n"

    for item in items:
        if not isinstance(item, dict):
            continue
        target_label = f"{item.get('target_workflow_profile_id', '')} / {item.get('target_stage_id', '')}"
        headline = (
            f"- {item.get('task_id', '')}: {item.get('recommendation_type', '')} -> {target_label}"
            f" / status={item.get('status', '')}"
        )
        if bool(item.get("ready_for_profile_update", False)):
            headline += " / ready_for_profile_update"
        lines.append(headline)
        if item.get("blocking_reasons"):
            lines.append(f"  - 阻塞原因：{', '.join(str(reason) for reason in item['blocking_reasons'])}")
        if str(item.get("latest_agent_report_summary", "")).strip():
            lines.append(f"  - 执行摘要：{item.get('latest_agent_report_summary', '')}")
    return "\n".join(lines).rstrip() + "\n"


def build_control_plane_optimization_review_report(
    *,
    task_db: str | Path,
    lookback_hours: int = 72,
    limit: int = 20,
) -> dict[str, Any]:
    """Build one structured optimization execution review report.

    Args:
        task_db: Task-center SQLite path.
        lookback_hours: Only review optimization tasks updated within this window.
        limit: Maximum number of optimization tasks to inspect.

    Returns:
        dict[str, Any]: Review report including summary counts, per-task items and Markdown.

    Raises:
        ValueError: Raised when `lookback_hours` or `limit` is invalid after normalization.
    """

    normalized_lookback = max(1, int(lookback_hours or 72))
    normalized_limit = max(1, int(limit or 20))
    since = _normalize_since(normalized_lookback)

    task_center = TaskCenter(Path(task_db).expanduser())
    try:
        candidates = _load_candidate_tasks(
            task_center=task_center,
            since=since,
            limit=normalized_limit,
        )
        items: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        recommendation_type_counts: dict[str, int] = {}
        target_workflow_counts: dict[str, int] = {}

        for candidate in candidates:
            task_id = str(candidate.get("task_id", "")).strip()
            if not task_id:
                continue
            report = task_center.task_report(task_id, event_limit=200, display_safe=False)
            item = _build_review_item(report)
            items.append(item)
            _merge_counts(status_counts, str(item["status"]))
            if str(item["recommendation_type"]).strip():
                _merge_counts(recommendation_type_counts, str(item["recommendation_type"]))
            if str(item["target_workflow_profile_id"]).strip():
                _merge_counts(target_workflow_counts, str(item["target_workflow_profile_id"]))
    finally:
        task_center.close()

    ready_count = sum(1 for item in items if bool(item.get("ready_for_profile_update", False)))
    pending_count = sum(1 for item in items if str(item.get("status", "")).strip().lower() in PENDING_STATUSES)
    completed_count = sum(1 for item in items if str(item.get("status", "")).strip().lower() in COMPLETED_STATUSES)
    blocked_count = sum(
        1
        for item in items
        if str(item.get("status", "")).strip().lower() not in PENDING_STATUSES
        and item.get("blocking_reasons")
        and not bool(item.get("ready_for_profile_update", False))
    )
    report = {
        "generated_at": utc_now_iso(),
        "task_db": str(Path(task_db).expanduser()),
        "lookback_hours": normalized_lookback,
        "summary": {
            "task_count": len(items),
            "completed_count": completed_count,
            "pending_count": pending_count,
            "blocked_count": blocked_count,
            "ready_for_profile_update_count": ready_count,
            "status_counts": status_counts,
            "recommendation_type_counts": recommendation_type_counts,
            "target_workflow_counts": target_workflow_counts,
        },
        "items": items,
    }
    report["markdown"] = render_control_plane_optimization_review_markdown(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Review dispatched control-plane optimization tasks.")
    parser.add_argument("--task-db", required=True)
    parser.add_argument("--lookback-hours", default="72")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the optimization review payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_control_plane_optimization_review_report(
        task_db=str(args.task_db).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 72)),
        limit=max(1, int(args.limit or 20)),
    )
    payload = {"report": report}
    if str(args.json_output or "").strip():
        write_json_atomic(
            Path(str(args.json_output).strip()).expanduser(),
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            report["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(report["markdown"])
    return payload


if __name__ == "__main__":
    main()

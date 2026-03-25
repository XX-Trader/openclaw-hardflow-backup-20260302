#!/usr/bin/env python3
"""Apply passed workflow profile update tasks into the workflow profile registry."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import TaskCenter, parse_json, utc_now_iso  # type: ignore
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


TASK_SOURCE = "control-plane-profile-update-dispatcher"
TASK_TYPE = "workflow_profile_update"
APPLY_STATUSES = {"passed"}
PENDING_TASK_STATUSES = {"pending", "running"}
DEFAULT_CLARIFICATION_FIELDS = ["objective", "constraints", "acceptance"]
STAGE_GUARD_BY_STAGE: dict[str, tuple[str, str]] = {
    "clarify": ("clarified_requirement", "context_complete_or_escalated"),
    "implement": ("verification_result", "tests_or_validation_recorded"),
    "investigate": ("verification_result", "tests_or_validation_recorded"),
    "stabilize": ("verification_result", "tests_or_validation_recorded"),
    "verify": ("verification_result", "tests_or_validation_recorded"),
    "draft": ("acceptance_summary", "review_completed"),
    "review": ("acceptance_summary", "review_completed"),
}


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON object using UTF-8 without BOM."""

    write_json_atomic(
        path,
        payload,
        ensure_ascii=False,
        indent=2,
        file_mode=0o644,
        dir_mode=0o755,
    )


def _normalize_since(lookback_hours: int) -> str:
    """Build the UTC lower bound used for apply queries."""

    return (
        datetime.now(tz=timezone.utc) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()


def _load_candidate_tasks(
    *,
    task_center: TaskCenter,
    since: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Load recent workflow profile update tasks ordered by latest update time."""

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
          AND task_type = ?
          AND updated_at >= ?
        ORDER BY updated_at DESC, task_id DESC
        LIMIT ?
        """,
        (TASK_SOURCE, TASK_TYPE, since, max(1, int(limit or 20))),
    ).fetchall()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["selection_inputs"] = parse_json(str(item.get("selection_inputs") or ""))
        item["context_payload"] = parse_json(str(item.get("context_payload") or ""))
        normalized_rows.append(item)
    return normalized_rows


def _find_profile_entry_index(registry: dict[str, Any], *, profile_id: str, channel: str) -> int:
    """Find one workflow profile entry index by profile id and channel."""

    profiles = registry.get("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError("workflow profile registry profiles must be a list")
    normalized_profile_id = str(profile_id or "").strip().lower()
    normalized_channel = str(channel or "").strip().lower()
    for index, entry in enumerate(profiles):
        if not isinstance(entry, dict):
            continue
        if (
            str(entry.get("profile_id", "")).strip().lower() == normalized_profile_id
            and str(entry.get("channel", "")).strip().lower() == normalized_channel
        ):
            return index
    raise ValueError(f"workflow profile entry not found: {profile_id}@{channel}")


def _find_stage_entry(stage_entries: list[dict[str, Any]], stage_id: str) -> dict[str, Any] | None:
    """Return one stage entry by stage id."""

    normalized_stage_id = str(stage_id or "").strip().lower()
    for entry in stage_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("stage_id", "")).strip().lower() == normalized_stage_id:
            return entry
    return None


def _ensure_list_strings(values: Any) -> list[str]:
    """Normalize one list-like payload into stripped string items."""

    if values is None:
        return []
    if isinstance(values, list):
        items = values
    else:
        items = [values]
    normalized: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _extract_recommendation_type(task: dict[str, Any]) -> str:
    """Extract recommendation type from task metadata."""

    selection_inputs = task.get("selection_inputs", {})
    if isinstance(selection_inputs, dict):
        recommendation_type = str(selection_inputs.get("recommendation_type", "")).strip()
        if recommendation_type:
            return recommendation_type
    context_payload = task.get("context_payload", {})
    if isinstance(context_payload, dict):
        review_item = context_payload.get("review_item", {})
        if isinstance(review_item, dict):
            recommendation_type = str(review_item.get("recommendation_type", "")).strip()
            if recommendation_type:
                return recommendation_type
    return ""


def _extract_target(task: dict[str, Any]) -> tuple[str, str, str]:
    """Extract target workflow and stage metadata from task payload."""

    selection_inputs = task.get("selection_inputs", {})
    context_payload = task.get("context_payload", {})
    target_workflow_profile_id = ""
    target_stage_id = ""
    target_stage_label = ""
    if isinstance(selection_inputs, dict):
        target_workflow_profile_id = str(selection_inputs.get("target_workflow_profile_id", "")).strip()
        target_stage_id = str(selection_inputs.get("target_stage_id", "")).strip()
    if isinstance(context_payload, dict):
        target_workflow_profile_id = target_workflow_profile_id or str(context_payload.get("target_workflow_profile_id", "")).strip()
        target_stage_id = target_stage_id or str(context_payload.get("target_stage_id", "")).strip()
        target_stage_label = str(context_payload.get("target_stage_label", "")).strip()
    return (
        target_workflow_profile_id or "unknown-workflow",
        target_stage_id or "unknown-stage",
        target_stage_label or target_stage_id or "unknown-stage",
    )


def _extract_review_item(task: dict[str, Any]) -> dict[str, Any]:
    """Extract the normalized review item carried by the profile-update task."""

    context_payload = task.get("context_payload", {})
    if not isinstance(context_payload, dict):
        return {}
    review_item = context_payload.get("review_item", {})
    if isinstance(review_item, dict):
        return review_item
    return {}


def _history_change_ids(registry: dict[str, Any]) -> set[str]:
    """Collect already-applied change ids from registry history."""

    history = registry.get("profile_update_history", [])
    if not isinstance(history, list):
        return set()
    change_ids: set[str] = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        change_id = str(item.get("change_id", "")).strip()
        if change_id:
            change_ids.add(change_id)
    return change_ids


def _control_plane_gate_clear(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return whether the task report is safe to apply into the registry."""

    control_plane = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
    reasons: list[str] = []
    if int(control_plane.get("open_incident_count", 0) or 0) > 0:
        reasons.append("open_incidents")
    if int(control_plane.get("critical_open_incident_count", 0) or 0) > 0:
        reasons.append("critical_incidents")
    if bool(control_plane.get("requires_human_assistance", False)):
        reasons.append("requires_human_assistance")
    if bool(control_plane.get("waiting_human_confirm", False)):
        reasons.append("waiting_human_confirm")
    if bool(control_plane.get("needs_clarification", False)):
        reasons.append("needs_clarification")
    return len(reasons) == 0, reasons


def _ensure_stage_dict_list(profile_entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the profile stage list."""

    stages = profile_entry.get("stages", [])
    if not isinstance(stages, list):
        raise ValueError("workflow profile stages must be a list")
    normalized: list[dict[str, Any]] = []
    for item in stages:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _ensure_optimization_hints(stage_entry: dict[str, Any]) -> dict[str, Any]:
    """Return the mutable optimization hint object on one stage entry."""

    hints = stage_entry.get("optimization_hints", {})
    if not isinstance(hints, dict):
        hints = {}
    stage_entry["optimization_hints"] = hints
    return hints


def _append_unique_list(target: list[str], value: str) -> None:
    """Append one string into the list when it is non-empty and not duplicated."""

    text = str(value or "").strip()
    if text and text not in target:
        target.append(text)


def _apply_strengthen_stage_gate(
    *,
    stage_entry: dict[str, Any],
    task: dict[str, Any],
    recommendation_type: str,
) -> dict[str, Any]:
    """Apply one stage-gate strengthening patch."""

    before_count = int(stage_entry.get("min_evidence_count", 0) or 0)
    stage_entry["min_evidence_count"] = max(3, before_count + 1)

    output_contract = stage_entry.get("output_contract", {})
    if not isinstance(output_contract, dict):
        output_contract = {}
    deliverables = _ensure_list_strings(output_contract.get("deliverables", []))
    verification_contract = stage_entry.get("verification_contract", {})
    if not isinstance(verification_contract, dict):
        verification_contract = {}
    checks = _ensure_list_strings(verification_contract.get("checks", []))

    deliverable_hint, check_hint = STAGE_GUARD_BY_STAGE.get(
        str(stage_entry.get("stage_id", "")).strip().lower(),
        ("acceptance_summary", "review_completed"),
    )
    _append_unique_list(deliverables, deliverable_hint)
    _append_unique_list(checks, check_hint)
    output_contract["deliverables"] = deliverables
    verification_contract["checks"] = checks
    stage_entry["output_contract"] = output_contract
    stage_entry["verification_contract"] = verification_contract

    hints = _ensure_optimization_hints(stage_entry)
    hints[recommendation_type] = {
        "enabled": True,
        "source_task_id": str(task.get("task_id", "")).strip(),
        "source_change_id": str(task.get("change_id", "")).strip(),
        "applied_at": utc_now_iso(),
    }
    return {
        "min_evidence_count_before": before_count,
        "min_evidence_count_after": int(stage_entry["min_evidence_count"]),
        "deliverables": deliverables,
        "checks": checks,
    }


def _apply_clarification_upgrade(
    *,
    stage_entry: dict[str, Any],
    task: dict[str, Any],
    recommendation_type: str,
) -> dict[str, Any]:
    """Apply one clarification-upgrade patch."""

    before_count = int(stage_entry.get("min_evidence_count", 0) or 0)
    stage_entry["min_evidence_count"] = max(3, before_count)
    stage_entry["clarification_required_fields"] = list(DEFAULT_CLARIFICATION_FIELDS)

    output_contract = stage_entry.get("output_contract", {})
    if not isinstance(output_contract, dict):
        output_contract = {}
    deliverables = _ensure_list_strings(output_contract.get("deliverables", []))
    for deliverable in ("clarified_requirement", "context_payload"):
        _append_unique_list(deliverables, deliverable)
    output_contract["deliverables"] = deliverables
    stage_entry["output_contract"] = output_contract

    verification_contract = stage_entry.get("verification_contract", {})
    if not isinstance(verification_contract, dict):
        verification_contract = {}
    checks = _ensure_list_strings(verification_contract.get("checks", []))
    _append_unique_list(checks, "context_complete_or_escalated")
    verification_contract["checks"] = checks
    stage_entry["verification_contract"] = verification_contract

    hints = _ensure_optimization_hints(stage_entry)
    hints[recommendation_type] = {
        "enabled": True,
        "source_task_id": str(task.get("task_id", "")).strip(),
        "source_change_id": str(task.get("change_id", "")).strip(),
        "applied_at": utc_now_iso(),
    }
    return {
        "min_evidence_count_before": before_count,
        "min_evidence_count_after": int(stage_entry["min_evidence_count"]),
        "clarification_required_fields": list(DEFAULT_CLARIFICATION_FIELDS),
        "deliverables": deliverables,
        "checks": checks,
    }


def _apply_parallelize_candidate(
    *,
    stage_entry: dict[str, Any],
    task: dict[str, Any],
    recommendation_type: str,
) -> dict[str, Any]:
    """Apply one parallelization candidate patch."""

    parallel_config = stage_entry.get("parallel_execution", {})
    if not isinstance(parallel_config, dict):
        parallel_config = {}
    parallel_config.update(
        {
            "enabled": True,
            "mode": "candidate",
            "suggested_batch_size": max(2, int(parallel_config.get("suggested_batch_size", 2) or 2)),
            "source_task_id": str(task.get("task_id", "")).strip(),
            "source_change_id": str(task.get("change_id", "")).strip(),
            "applied_at": utc_now_iso(),
        }
    )
    stage_entry["parallel_execution"] = parallel_config
    hints = _ensure_optimization_hints(stage_entry)
    hints[recommendation_type] = deepcopy(parallel_config)
    return {"parallel_execution": deepcopy(parallel_config)}


def _apply_simplification_candidate(
    *,
    stage_entry: dict[str, Any],
    task: dict[str, Any],
    recommendation_type: str,
) -> dict[str, Any]:
    """Apply one stage simplification candidate patch."""

    review_item = _extract_review_item(task)
    evidence_snapshot = review_item.get("evidence_snapshot", {})
    if not isinstance(evidence_snapshot, dict):
        evidence_snapshot = {}
    profile_update_guard = review_item.get("profile_update_guard", {})
    if not isinstance(profile_update_guard, dict):
        profile_update_guard = {}
    simplification_config = stage_entry.get("simplification_hint", {})
    if not isinstance(simplification_config, dict):
        simplification_config = {}
    simplification_config.update(
        {
            "enabled": True,
            "mode": "candidate",
            "strategy": "sample_or_merge",
            "deletion_mode": "suggest_only",
            "policy": str(profile_update_guard.get("policy", "")).strip() or "workflow_evolution.stage_simplification.v1",
            "evidence_snapshot": deepcopy(evidence_snapshot),
            "profile_update_guard": deepcopy(profile_update_guard),
            "source_task_id": str(task.get("task_id", "")).strip(),
            "source_change_id": str(task.get("change_id", "")).strip(),
            "applied_at": utc_now_iso(),
        }
    )
    stage_entry["simplification_hint"] = simplification_config
    hints = _ensure_optimization_hints(stage_entry)
    hints[recommendation_type] = deepcopy(simplification_config)
    return {"simplification_hint": deepcopy(simplification_config)}


def _evaluate_profile_update_guard(
    *,
    task: dict[str, Any],
    recommendation_type: str,
) -> tuple[bool, list[str]]:
    """Return whether the task is safe to apply into the candidate registry."""

    if recommendation_type != "stage_simplification_candidate":
        return True, []
    review_item = _extract_review_item(task)
    profile_update_guard = review_item.get("profile_update_guard", {})
    if not isinstance(profile_update_guard, dict):
        return False, ["missing_profile_update_guard"]
    if bool(profile_update_guard.get("ready", False)):
        return True, []
    reasons = profile_update_guard.get("reasons", [])
    if isinstance(reasons, list):
        normalized_reasons = [str(reason).strip() for reason in reasons if str(reason).strip()]
    else:
        normalized_reasons = []
    if not normalized_reasons:
        normalized_reasons = ["profile_update_guard_not_ready"]
    return False, normalized_reasons


def _apply_stage_patch(
    *,
    stage_entry: dict[str, Any],
    task: dict[str, Any],
    recommendation_type: str,
) -> dict[str, Any]:
    """Apply one deterministic patch to the target stage."""

    if recommendation_type == "strengthen_stage_gate":
        return _apply_strengthen_stage_gate(
            stage_entry=stage_entry,
            task=task,
            recommendation_type=recommendation_type,
        )
    if recommendation_type == "clarification_upgrade_needed":
        return _apply_clarification_upgrade(
            stage_entry=stage_entry,
            task=task,
            recommendation_type=recommendation_type,
        )
    if recommendation_type == "parallelize_stage_candidate":
        return _apply_parallelize_candidate(
            stage_entry=stage_entry,
            task=task,
            recommendation_type=recommendation_type,
        )
    if recommendation_type == "stage_simplification_candidate":
        return _apply_simplification_candidate(
            stage_entry=stage_entry,
            task=task,
            recommendation_type=recommendation_type,
        )
    raise ValueError(f"unsupported recommendation_type: {recommendation_type}")


def _build_history_record(
    *,
    task: dict[str, Any],
    target_profile_id: str,
    target_stage_id: str,
    target_stage_label: str,
    target_channel: str,
    recommendation_type: str,
    stage_before: dict[str, Any],
    stage_after: dict[str, Any],
    latest_agent_report_summary: str,
) -> dict[str, Any]:
    """Build one registry history record for an applied profile update."""

    return {
        "profile_update_id": f"profile-update-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "applied_at": utc_now_iso(),
        "task_id": str(task.get("task_id", "")).strip(),
        "change_id": str(task.get("change_id", "")).strip(),
        "target_profile_id": target_profile_id,
        "target_stage_id": target_stage_id,
        "target_stage_label": target_stage_label,
        "target_channel": target_channel,
        "recommendation_type": recommendation_type,
        "latest_agent_report_summary": latest_agent_report_summary,
        "stage_snapshot_before": stage_before,
        "stage_snapshot_after": stage_after,
    }


def render_control_plane_profile_update_apply_markdown(result: dict[str, Any]) -> str:
    """Render one Markdown summary for applied profile updates."""

    lines = [
        "# OpenClaw Control Plane Profile Update Apply",
        "",
        f"- 生成时间：{result.get('generated_at', '')}",
        f"- 目标 registry：{result.get('registry_file', '')}",
        f"- 目标 channel：{result.get('target_channel', '')}",
        f"- 已应用：{result.get('applied_count', 0)}",
        f"- 已跳过：{result.get('skipped_count', 0)}",
        "",
        "## 已应用任务",
    ]
    applied = result.get("applied", [])
    if isinstance(applied, list) and applied:
        for item in applied:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('task_id', '')}: {item.get('recommendation_type', '')} -> "
                f"{item.get('target_profile_id', '')}/{item.get('target_stage_id', '')}@{item.get('target_channel', '')}"
            )
    else:
        lines.append("- 当前窗口内没有可应用的 profile update 任务")

    lines.extend(["", "## 已跳过任务"])
    skipped = result.get("skipped", [])
    if isinstance(skipped, list) and skipped:
        for item in skipped:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('task_id', '')}: {item.get('target_profile_id', '')}/"
                f"{item.get('target_stage_id', '')} / {item.get('reason', '')}"
            )
    else:
        lines.append("- 当前窗口内没有跳过项")
    return "\n".join(lines).rstrip() + "\n"


def render_control_plane_profile_update_apply_markdown_clean(result: dict[str, Any]) -> str:
    """Render one clean Chinese Markdown summary for applied profile updates."""

    lines = [
        "# OpenClaw Control Plane Profile Update Apply",
        "",
        f"- 生成时间：{result.get('generated_at', '')}",
        f"- 目标 registry：{result.get('registry_file', '')}",
        f"- 目标 channel：{result.get('target_channel', '')}",
        f"- 已应用：{result.get('applied_count', 0)}",
        f"- 已跳过：{result.get('skipped_count', 0)}",
        "",
        "## 已应用任务",
    ]
    applied = result.get("applied", [])
    if isinstance(applied, list) and applied:
        for item in applied:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('task_id', '')}: {item.get('recommendation_type', '')} -> "
                f"{item.get('target_profile_id', '')}/{item.get('target_stage_id', '')}@{item.get('target_channel', '')}"
            )
    else:
        lines.append("- 当前窗口内没有可应用的 profile update 任务")

    lines.extend(["", "## 已跳过任务"])
    skipped = result.get("skipped", [])
    if isinstance(skipped, list) and skipped:
        for item in skipped:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('task_id', '')}: {item.get('target_profile_id', '')}/"
                f"{item.get('target_stage_id', '')} / {item.get('reason', '')}"
            )
    else:
        lines.append("- 当前窗口内没有跳过项")
    return "\n".join(lines).rstrip() + "\n"


def apply_control_plane_profile_updates(
    *,
    task_db: str | Path,
    registry_file: str | Path,
    lookback_hours: int = 72,
    limit: int = 20,
    target_channel: str = "candidate",
) -> dict[str, Any]:
    """Apply passed workflow profile update tasks into the workflow profile registry.

    Args:
        task_db: Task-center SQLite path.
        registry_file: Workflow profile registry JSON file.
        lookback_hours: Only inspect tasks updated within this window.
        limit: Maximum number of tasks to inspect.
        target_channel: Registry channel to mutate. Defaults to `candidate`.

    Returns:
        dict[str, Any]: Structured apply summary including applied and skipped items.
    """

    registry_path = Path(registry_file).expanduser()
    registry = _load_json_object(registry_path)
    applied_change_ids = _history_change_ids(registry)
    profiles = registry.get("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError("workflow profile registry profiles must be a list")

    normalized_target_channel = str(target_channel or "candidate").strip().lower() or "candidate"
    normalized_lookback = max(1, int(lookback_hours or 72))
    normalized_limit = max(1, int(limit or 20))
    since = _normalize_since(normalized_lookback)

    task_center = TaskCenter(Path(task_db).expanduser())
    task_center.init_schema()
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        candidates = _load_candidate_tasks(
            task_center=task_center,
            since=since,
            limit=normalized_limit,
        )
        for task in candidates:
            task_id = str(task.get("task_id", "")).strip()
            status = str(task.get("status", "")).strip().lower()
            change_id = str(task.get("change_id", "")).strip()
            recommendation_type = _extract_recommendation_type(task)
            target_profile_id, target_stage_id, target_stage_label = _extract_target(task)

            if status not in APPLY_STATUSES:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "task_not_passed",
                    }
                )
                continue
            if change_id in applied_change_ids:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "duplicate_applied_change_id",
                    }
                )
                continue
            if not recommendation_type:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "missing_recommendation_type",
                    }
                )
                continue
            if recommendation_type == "load_balance_stage_candidate":
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "deprecated_recommendation_type",
                    }
                )
                continue
            profile_update_guard_ready, profile_update_guard_reasons = _evaluate_profile_update_guard(
                task=task,
                recommendation_type=recommendation_type,
            )
            if not profile_update_guard_ready:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "profile_update_guard_not_ready",
                        "blocking_reasons": profile_update_guard_reasons,
                    }
                )
                continue

            report = task_center.task_report(task_id, event_limit=200, display_safe=False)
            control_plane_clear, blocking_reasons = _control_plane_gate_clear(report)
            if not control_plane_clear:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "control_plane_gate_blocked",
                        "blocking_reasons": blocking_reasons,
                    }
                )
                continue

            try:
                profile_index = _find_profile_entry_index(
                    registry,
                    profile_id=target_profile_id,
                    channel=normalized_target_channel,
                )
            except ValueError:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "target_profile_channel_missing",
                    }
                )
                continue

            profile_entry = profiles[profile_index]
            if not isinstance(profile_entry, dict):
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "invalid_profile_entry",
                    }
                )
                continue
            stage_entries = _ensure_stage_dict_list(profile_entry)
            stage_entry = _find_stage_entry(stage_entries, target_stage_id)
            if stage_entry is None:
                skipped.append(
                    {
                        "task_id": task_id,
                        "change_id": change_id,
                        "target_profile_id": target_profile_id,
                        "target_stage_id": target_stage_id,
                        "reason": "target_stage_missing",
                    }
                )
                continue

            stage_before = deepcopy(stage_entry)
            latest_agent_report_summary = ""
            agent_reports = report.get("agent_reports", [])
            if isinstance(agent_reports, list) and agent_reports and isinstance(agent_reports[0], dict):
                latest_agent_report_summary = str(agent_reports[0].get("resolution_summary", "")).strip()
            patch_summary = _apply_stage_patch(
                stage_entry=stage_entry,
                task=task,
                recommendation_type=recommendation_type,
            )
            stage_after = deepcopy(stage_entry)
            history = registry.get("profile_update_history", [])
            if not isinstance(history, list):
                history = []
            history.append(
                _build_history_record(
                    task=task,
                    target_profile_id=target_profile_id,
                    target_stage_id=target_stage_id,
                    target_stage_label=target_stage_label,
                    target_channel=normalized_target_channel,
                    recommendation_type=recommendation_type,
                    stage_before=stage_before,
                    stage_after=stage_after,
                    latest_agent_report_summary=latest_agent_report_summary,
                )
            )
            registry["profile_update_history"] = history
            registry["last_profile_update"] = {
                "task_id": task_id,
                "change_id": change_id,
                "target_profile_id": target_profile_id,
                "target_stage_id": target_stage_id,
                "target_channel": normalized_target_channel,
                "recommendation_type": recommendation_type,
                "applied_at": utc_now_iso(),
            }
            applied_change_ids.add(change_id)
            applied.append(
                {
                    "task_id": task_id,
                    "change_id": change_id,
                    "target_profile_id": target_profile_id,
                    "target_stage_id": target_stage_id,
                    "target_stage_label": target_stage_label,
                    "target_channel": normalized_target_channel,
                    "recommendation_type": recommendation_type,
                    "patch_summary": patch_summary,
                }
            )
    finally:
        task_center.close()

    _write_json(registry_path, registry)
    result = {
        "generated_at": utc_now_iso(),
        "task_db": str(Path(task_db).expanduser()),
        "registry_file": str(registry_path),
        "lookback_hours": normalized_lookback,
        "target_channel": normalized_target_channel,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }
    result["markdown"] = render_control_plane_profile_update_apply_markdown_clean(result)
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Apply passed workflow profile update tasks into the runtime registry.")
    parser.add_argument("--task-db", required=True)
    parser.add_argument("--registry-file", required=True)
    parser.add_argument("--target-channel", default="candidate")
    parser.add_argument("--lookback-hours", default="72")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the apply payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    result = apply_control_plane_profile_updates(
        task_db=str(args.task_db).strip(),
        registry_file=str(args.registry_file).strip(),
        target_channel=str(args.target_channel).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 72)),
        limit=max(1, int(args.limit or 20)),
    )
    payload = {"result": result}
    if str(args.json_output or "").strip():
        _write_json(Path(str(args.json_output).strip()).expanduser(), payload)
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            result["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(result["markdown"])
    return payload


if __name__ == "__main__":
    main()

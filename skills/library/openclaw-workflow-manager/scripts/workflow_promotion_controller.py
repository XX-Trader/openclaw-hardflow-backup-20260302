#!/usr/bin/env python3
"""Apply or rollback workflow profile promotions against the runtime registry."""

from __future__ import annotations

import argparse
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JSONDict = dict[str, Any]


class WorkflowPromotionError(RuntimeError):
    """Raised when workflow promotion or rollback validation fails."""


def _now_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json_object(path: Path) -> JSONDict:
    """Load a JSON object from disk.

    Args:
        path: JSON file path.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        WorkflowPromotionError: Raised when the file is missing or not a JSON object.
    """

    if not path.exists():
        raise WorkflowPromotionError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise WorkflowPromotionError(f"JSON payload must be an object: {path}")
    return payload


def _write_json(path: Path, payload: JSONDict) -> None:
    """Write a JSON object using UTF-8 without BOM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_profile_entry_index(registry: JSONDict, *, profile_id: str, channel: str) -> int:
    """Find a workflow profile entry index by profile id and channel."""

    profiles = registry.get("profiles", [])
    if not isinstance(profiles, list):
        raise WorkflowPromotionError("workflow profile registry profiles must be a list")
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
    raise WorkflowPromotionError(f"workflow profile entry not found: {profile_id}@{channel}")


def _summary_workflow_decision(summary: JSONDict) -> tuple[bool, JSONDict]:
    """Extract workflow promotion decision data from an upgrade summary."""

    workflow_scorecard = summary.get("workflow_scorecard", {})
    if not isinstance(workflow_scorecard, dict):
        raise WorkflowPromotionError("summary.workflow_scorecard must be an object")
    decision = workflow_scorecard.get("decision", {})
    if not isinstance(decision, dict):
        raise WorkflowPromotionError("summary.workflow_scorecard.decision must be an object")
    promoted = bool(decision.get("promote_to_new_baseline", summary.get("workflow_promoted", False)))
    return promoted, workflow_scorecard


def _derive_promoted_version(
    *,
    stable_entry: JSONDict,
    candidate_entry: JSONDict,
    summary: JSONDict,
) -> str:
    """Derive the new stable version for a promotion."""

    candidate_version = str(candidate_entry.get("version", "") or "").strip()
    stable_version = str(stable_entry.get("version", "") or "").strip()
    if candidate_version and candidate_version != stable_version:
        return candidate_version
    generated_at = str(summary.get("generated_at", "") or "").strip()
    if generated_at:
        stamp = (
            generated_at.replace("-", "")
            .replace(":", "")
            .replace("+00:00", "Z")
            .replace("T", "-")
        )
        return f"promoted-{stamp}"
    candidate_run_ids = summary.get("candidate_run_ids", [])
    if isinstance(candidate_run_ids, list) and candidate_run_ids:
        tail = str(candidate_run_ids[-1]).strip()
        if tail:
            return f"promoted-{tail}"
    return f"promoted-{uuid.uuid4().hex[:12]}"


def apply_workflow_promotion(
    *,
    registry_file: str | Path,
    summary_file: str | Path,
    profile_id: str = "coding-default",
    stable_channel: str = "stable",
    candidate_channel: str = "candidate",
    operator: str = "upgrade-feedback-runner",
) -> JSONDict:
    """Promote one workflow candidate entry into the stable channel.

    Args:
        registry_file: Workflow profile registry JSON file.
        summary_file: Upgrade feedback summary JSON file.
        profile_id: Workflow profile id to promote.
        stable_channel: Stable channel name.
        candidate_channel: Candidate channel name.
        operator: Operator name recorded in promotion history.

    Returns:
        dict[str, Any]: Promotion result payload.

    Raises:
        WorkflowPromotionError: Raised when validation fails or summary does not permit promotion.
    """

    registry_path = Path(registry_file).expanduser()
    summary_path = Path(summary_file).expanduser()
    registry = _load_json_object(registry_path)
    summary = _load_json_object(summary_path)
    promoted, workflow_scorecard = _summary_workflow_decision(summary)
    if not promoted:
        raise WorkflowPromotionError("workflow promotion decision is false; promotion aborted")

    profiles = registry.get("profiles", [])
    if not isinstance(profiles, list):
        raise WorkflowPromotionError("workflow profile registry profiles must be a list")

    stable_index = _find_profile_entry_index(
        registry,
        profile_id=profile_id,
        channel=stable_channel,
    )
    candidate_index = _find_profile_entry_index(
        registry,
        profile_id=profile_id,
        channel=candidate_channel,
    )

    stable_before = deepcopy(profiles[stable_index])
    candidate_entry = deepcopy(profiles[candidate_index])
    if not bool(candidate_entry.get("enabled", True)):
        raise WorkflowPromotionError(f"candidate workflow is disabled: {profile_id}@{candidate_channel}")

    new_version = _derive_promoted_version(
        stable_entry=stable_before,
        candidate_entry=candidate_entry,
        summary=summary,
    )
    promoted_at = _now_iso()
    promotion_id = f"promotion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    stable_after = deepcopy(candidate_entry)
    stable_after["channel"] = str(stable_channel).strip().lower()
    stable_after["promotion_target_channel"] = (
        str(stable_before.get("promotion_target_channel", candidate_channel) or candidate_channel).strip().lower()
        or str(candidate_channel).strip().lower()
    )
    stable_after["display_name"] = str(stable_before.get("display_name", "") or candidate_entry.get("display_name", "")).strip()
    stable_after["description"] = str(stable_before.get("description", "") or candidate_entry.get("description", "")).strip()
    stable_after["version"] = new_version
    stable_after["last_promoted_at"] = promoted_at
    stable_after["last_promoted_from_channel"] = str(candidate_channel).strip().lower()
    stable_after["last_promotion_summary_file"] = str(summary_path)
    stable_after["last_candidate_run_ids"] = list(summary.get("candidate_run_ids", []))
    stable_after["last_baseline_run_ids"] = list(summary.get("baseline_run_ids", []))
    stable_after["last_promotion_decision"] = deepcopy(workflow_scorecard.get("decision", {}))
    stable_after["last_promotion_operator"] = str(operator or "").strip()
    profiles[stable_index] = stable_after

    candidate_after = deepcopy(candidate_entry)
    candidate_after["last_evaluated_at"] = promoted_at
    candidate_after["last_promotion_summary_file"] = str(summary_path)
    candidate_after["last_promotion_candidate_run_ids"] = list(summary.get("candidate_run_ids", []))
    candidate_after["last_promotion_decision"] = deepcopy(workflow_scorecard.get("decision", {}))
    profiles[candidate_index] = candidate_after

    history = registry.get("promotion_history", [])
    if not isinstance(history, list):
        history = []
    workflow_decision = workflow_scorecard.get("decision", {})
    history.append(
        {
            "promotion_id": promotion_id,
            "profile_id": str(profile_id).strip(),
            "stable_channel": str(stable_channel).strip().lower(),
            "candidate_channel": str(candidate_channel).strip().lower(),
            "operator": str(operator or "").strip(),
            "promoted_at": promoted_at,
            "summary_file": str(summary_path),
            "baseline_run_ids": list(summary.get("baseline_run_ids", [])),
            "candidate_run_ids": list(summary.get("candidate_run_ids", [])),
            "baseline_average": workflow_decision.get("baseline_average"),
            "candidate_average": workflow_decision.get("candidate_average"),
            "stable_snapshot_before": stable_before,
            "stable_snapshot_after": deepcopy(stable_after),
            "candidate_snapshot": candidate_entry,
        }
    )
    registry["promotion_history"] = history
    registry["profiles"] = profiles
    registry["last_promotion"] = {
        "promotion_id": promotion_id,
        "profile_id": str(profile_id).strip(),
        "stable_channel": str(stable_channel).strip().lower(),
        "candidate_channel": str(candidate_channel).strip().lower(),
        "summary_file": str(summary_path),
        "promoted_at": promoted_at,
        "operator": str(operator or "").strip(),
    }
    _write_json(registry_path, registry)
    return {
        "status": "promoted",
        "promotion_id": promotion_id,
        "registry_file": str(registry_path),
        "summary_file": str(summary_path),
        "profile_id": str(profile_id).strip(),
        "stable_channel": str(stable_channel).strip().lower(),
        "candidate_channel": str(candidate_channel).strip().lower(),
        "new_version": new_version,
        "candidate_run_ids": list(summary.get("candidate_run_ids", [])),
    }


def rollback_workflow_promotion(
    *,
    registry_file: str | Path,
    profile_id: str = "coding-default",
    stable_channel: str = "stable",
    promotion_id: str = "",
    operator: str = "human",
) -> JSONDict:
    """Rollback the stable workflow entry to the previous snapshot.

    Args:
        registry_file: Workflow profile registry JSON file.
        profile_id: Workflow profile id to roll back.
        stable_channel: Stable channel name to restore.
        promotion_id: Optional promotion id to roll back to. Defaults to latest matching promotion.
        operator: Operator recorded in rollback history.

    Returns:
        dict[str, Any]: Rollback result payload.

    Raises:
        WorkflowPromotionError: Raised when no matching promotion snapshot is available.
    """

    registry_path = Path(registry_file).expanduser()
    registry = _load_json_object(registry_path)
    history = registry.get("promotion_history", [])
    if not isinstance(history, list) or not history:
        raise WorkflowPromotionError("no promotion history available for rollback")

    normalized_profile_id = str(profile_id or "").strip().lower()
    normalized_stable_channel = str(stable_channel or "").strip().lower()
    wanted_promotion_id = str(promotion_id or "").strip()
    selected_record: JSONDict | None = None
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("profile_id", "")).strip().lower() != normalized_profile_id:
            continue
        if str(item.get("stable_channel", "")).strip().lower() != normalized_stable_channel:
            continue
        if wanted_promotion_id and str(item.get("promotion_id", "")).strip() != wanted_promotion_id:
            continue
        selected_record = item
        break
    if selected_record is None:
        raise WorkflowPromotionError(
            f"promotion history not found for rollback: {profile_id}@{stable_channel}"
            + (f" promotion_id={wanted_promotion_id}" if wanted_promotion_id else "")
        )

    stable_snapshot_before = selected_record.get("stable_snapshot_before")
    if not isinstance(stable_snapshot_before, dict):
        raise WorkflowPromotionError("rollback snapshot is missing stable_snapshot_before")

    stable_index = _find_profile_entry_index(
        registry,
        profile_id=profile_id,
        channel=stable_channel,
    )
    rollback_at = _now_iso()
    restored_entry = deepcopy(stable_snapshot_before)
    restored_entry["channel"] = normalized_stable_channel
    restored_entry["last_rolled_back_at"] = rollback_at
    restored_entry["last_rollback_operator"] = str(operator or "").strip()
    restored_entry["last_rollback_promotion_id"] = str(selected_record.get("promotion_id", "")).strip()
    registry["profiles"][stable_index] = restored_entry

    rollback_history = registry.get("rollback_history", [])
    if not isinstance(rollback_history, list):
        rollback_history = []
    rollback_id = f"rollback-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    rollback_history.append(
        {
            "rollback_id": rollback_id,
            "promotion_id": str(selected_record.get("promotion_id", "")).strip(),
            "profile_id": str(profile_id).strip(),
            "stable_channel": normalized_stable_channel,
            "rolled_back_at": rollback_at,
            "operator": str(operator or "").strip(),
        }
    )
    registry["rollback_history"] = rollback_history
    registry["last_rollback"] = {
        "rollback_id": rollback_id,
        "promotion_id": str(selected_record.get("promotion_id", "")).strip(),
        "profile_id": str(profile_id).strip(),
        "stable_channel": normalized_stable_channel,
        "rolled_back_at": rollback_at,
        "operator": str(operator or "").strip(),
    }
    _write_json(registry_path, registry)
    return {
        "status": "rolled_back",
        "rollback_id": rollback_id,
        "promotion_id": str(selected_record.get("promotion_id", "")).strip(),
        "registry_file": str(registry_path),
        "profile_id": str(profile_id).strip(),
        "stable_channel": normalized_stable_channel,
    }


def main() -> int:
    """Run the workflow promotion controller as a CLI."""

    home = Path.home()
    parser = argparse.ArgumentParser(description="Promote or rollback workflow profiles in the runtime registry.")
    parser.add_argument(
        "--registry-file",
        default=str(home / ".openclaw/ops/policy/workflow-profile-registry.json"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser("promote", help="promote a workflow candidate to stable")
    promote.add_argument("--summary-file", required=True)
    promote.add_argument("--profile-id", default="coding-default")
    promote.add_argument("--stable-channel", default="stable")
    promote.add_argument("--candidate-channel", default="candidate")
    promote.add_argument("--operator", default="upgrade-feedback-runner")

    rollback = sub.add_parser("rollback", help="rollback a workflow stable channel to the previous snapshot")
    rollback.add_argument("--profile-id", default="coding-default")
    rollback.add_argument("--stable-channel", default="stable")
    rollback.add_argument("--promotion-id", default="")
    rollback.add_argument("--operator", default="human")

    args = parser.parse_args()
    if args.command == "promote":
        result = apply_workflow_promotion(
            registry_file=args.registry_file,
            summary_file=args.summary_file,
            profile_id=args.profile_id,
            stable_channel=args.stable_channel,
            candidate_channel=args.candidate_channel,
            operator=args.operator,
        )
    else:
        result = rollback_workflow_promotion(
            registry_file=args.registry_file,
            profile_id=args.profile_id,
            stable_channel=args.stable_channel,
            promotion_id=args.promotion_id,
            operator=args.operator,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Policy Enforcer — WorkflowMixin."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _discover_repo_root(start: Path) -> Path:
    """Find the repository root from a skillized policy module path."""
    for env_name in ("HARDFLOW_WORKFLOW_REPO", "OPENCLAW_WORKFLOW_REPO"):
        env_value = str(os.environ.get(env_name, "") or "").strip()
        if not env_value:
            continue
        candidate = Path(env_value).expanduser().resolve()
        if (candidate / ".git").exists():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return ROOT.parent.parent


REPO_ROOT = _discover_repo_root(ROOT)
LEGACY_REPO_REF_ALIASES = {
    "scripts/hardflow/score-policy.json": "skills/openclaw-hardflow-automation/scripts/score-policy.json",
}

UTC = timezone.utc

from policy_defaults import (
    DEFAULT_POLICY,
    DEFAULT_WORKFLOW_PROFILE_REGISTRY,
)
from policy_utils import (
    PolicyError,
    parse_bool,
    merge_missing_keys,
    read_json,
    has_context_value,
)
from task_capability_binding import (
    DEFAULT_CAPABILITY_REGISTRY,
    normalize_capability_registry,
    validate_task_capability_constraints,
)

class WorkflowMixin:
    """Mixin providing Workflow methods for PolicyEnforcer."""

    def workflow_selection_policy(self) -> dict[str, Any]:
        cfg = self.policy.get("workflow_selection_policy", {})
        if not isinstance(cfg, dict):
            raise PolicyError("policy.workflow_selection_policy must be a JSON object")
        return cfg


    def workflow_selector_policy(self) -> dict[str, Any]:
        """Return the workflow selector policy with defaults backfilled.

        Returns:
            dict[str, Any]: Selector policy used to classify tasks before workflow entry.

        Raises:
            PolicyError: Raised when policy.workflow_selector_policy is not a JSON object.
        """
        cfg = self.policy.get("workflow_selector_policy", {})
        if not isinstance(cfg, dict):
            raise PolicyError("policy.workflow_selector_policy must be a JSON object")
        defaults = DEFAULT_POLICY.get("workflow_selector_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(cfg, defaults)


    @staticmethod
    def _selector_excerpt(text: str, limit: int = 160) -> str:
        collapsed = re.sub(r"\s+", " ", str(text or "").strip())
        if len(collapsed) <= limit:
            return collapsed
        return collapsed[: max(0, limit - 3)].rstrip() + "..."


    def capability_registry_file(self) -> Path:
        """Return the runtime capability registry path."""
        return self.paths.policy_file.parent / "capability-registry.json"


    @staticmethod
    def _normalize_json_contract(value: Any, *, field_name: str) -> dict[str, Any]:
        """Normalize a contract field and require a JSON object."""
        if isinstance(value, dict):
            return json.loads(json.dumps(value))
        raise PolicyError(f"{field_name} must be a JSON object")


    @staticmethod
    def _resolve_repo_ref_path(path_text: str) -> Path:
        """Resolve a repo-relative or absolute file path."""
        raw = str(path_text or "").strip()
        if not raw:
            return Path()
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            return candidate
        resolved = (REPO_ROOT / candidate).resolve()
        if resolved.exists():
            return resolved
        alias = LEGACY_REPO_REF_ALIASES.get(raw.replace("\\", "/"))
        if alias:
            alias_resolved = (REPO_ROOT / alias).resolve()
            if alias_resolved.exists():
                return alias_resolved
        return resolved


    def load_score_policy_gates(self, score_policy_ref: str) -> dict[str, Any]:
        """Load gates from a score policy JSON file."""
        normalized_ref = str(score_policy_ref or "").strip()
        if not normalized_ref:
            raise PolicyError("score_policy_ref must not be empty")
        if normalized_ref in self._score_policy_cache:
            return self._score_policy_cache[normalized_ref]
        score_policy_path = self._resolve_repo_ref_path(normalized_ref)
        if not score_policy_path.exists():
            raise PolicyError(f"score policy file not found: {score_policy_path}")
        try:
            payload = json.loads(score_policy_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise PolicyError(f"score policy file is not valid JSON: {score_policy_path}: {exc}") from exc
        gates = payload.get("gates", {}) if isinstance(payload, dict) else {}
        if not isinstance(gates, dict) or not gates:
            raise PolicyError(f"score policy gates missing or invalid: {score_policy_path}")
        self._score_policy_cache[normalized_ref] = gates
        return gates


    def load_capability_registry(self) -> dict[str, Any]:
        """Load, backfill defaults, and validate the runtime capability registry.

        Returns:
            dict[str, Any]: Normalized capability registry payload.

        Raises:
            PolicyError: Raised when the registry shape is invalid.
        """
        registry_path = self.capability_registry_file()
        registry_raw = read_json(
            registry_path,
            DEFAULT_CAPABILITY_REGISTRY,
            write_if_missing=True,
        )
        try:
            return normalize_capability_registry(registry_raw)
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc


    def workflow_profile_registry_file(self) -> Path:
        """Return the runtime workflow profile registry path.

        Returns:
            Path: Runtime directory file path for workflow profile registry JSON.
        """
        return self.paths.policy_file.parent / "workflow-profile-registry.json"


    def _normalize_workflow_profile_entry(self, entry_raw: Any, *, index: int) -> dict[str, Any]:
        """Validate and normalize one workflow profile registry entry."""
        if not isinstance(entry_raw, dict):
            raise PolicyError(f"workflow profile registry entry #{index} must be a JSON object")

        merged_entry = dict(entry_raw)
        profile_id = str(merged_entry.get("profile_id", "") or "").strip()
        channel = str(merged_entry.get("channel", "") or "").strip().lower()
        for item in DEFAULT_WORKFLOW_PROFILE_REGISTRY.get("profiles", []):
            if (
                str(item.get("profile_id", "")).strip().lower() == profile_id.lower()
                and str(item.get("channel", "")).strip().lower() == channel
            ):
                merged_entry = merge_missing_keys(merged_entry, item)
                break

        profile_id = str(merged_entry.get("profile_id", "") or "").strip()
        if not profile_id:
            raise PolicyError(f"workflow profile registry entry #{index} missing profile_id")

        channel = str(merged_entry.get("channel", "") or "").strip().lower()
        if not channel:
            raise PolicyError(f"workflow profile registry entry #{index} missing channel")

        entry_task_types_raw = merged_entry.get("entry_task_types", [])
        if not isinstance(entry_task_types_raw, list):
            raise PolicyError(f"workflow profile registry entry #{index} entry_task_types must be a list")
        entry_task_types: list[str] = []
        seen_task_types: set[str] = set()
        for item in entry_task_types_raw:
            task_type = str(item or "").strip().lower()
            if not task_type or task_type in seen_task_types:
                continue
            seen_task_types.add(task_type)
            entry_task_types.append(task_type)

        score_policy_ref = str(merged_entry.get("score_policy_ref", "") or "").strip()
        if not score_policy_ref:
            raise PolicyError(f"workflow profile registry entry #{index} missing score_policy_ref")
        score_policy_gates = self.load_score_policy_gates(score_policy_ref)

        runtime_entry = str(merged_entry.get("runtime_entry", "") or "").strip()
        if not runtime_entry:
            raise PolicyError(f"workflow profile registry entry #{index} missing runtime_entry")

        stages_raw = merged_entry.get("stages", [])
        if not isinstance(stages_raw, list) or not stages_raw:
            raise PolicyError(f"workflow profile registry entry #{index} stages must be a non-empty list")
        stages: list[dict[str, Any]] = []
        seen_stage_ids: set[str] = set()
        for stage_index, stage_raw in enumerate(stages_raw):
            if not isinstance(stage_raw, dict):
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage #{stage_index} must be a JSON object"
                )
            stage_id = str(stage_raw.get("stage_id", "") or "").strip()
            if not stage_id:
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage #{stage_index} missing stage_id"
                )
            lowered_stage_id = stage_id.lower()
            if lowered_stage_id in seen_stage_ids:
                raise PolicyError(
                    f"workflow profile registry entry #{index} duplicate stage_id: {stage_id}"
                )
            seen_stage_ids.add(lowered_stage_id)
            try:
                normalized_constraints = validate_task_capability_constraints(
                    stage_raw.get("required_capabilities", []),
                    stage_raw.get("required_skills", []),
                    [],
                    registry=self.capability_registry,
                )
            except ValueError as exc:
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage '{stage_id}' invalid: {exc}"
                ) from exc
            stages.append(
                {
                    "stage_id": stage_id,
                    "display_name": str(stage_raw.get("display_name", stage_id) or stage_id).strip() or stage_id,
                    "score_gate": "",
                    "min_evidence_count": 0,
                    "output_contract": {},
                    "verification_contract": {},
                    "clarification_required_fields": [],
                    "parallel_execution": {},
                    "simplification_hint": {},
                    "optimization_hints": {},
                    "required_capabilities": normalized_constraints["required_capabilities"],
                    "required_skills": normalized_constraints["required_skills"],
                }
            )
            score_gate = str(stage_raw.get("score_gate", "") or "").strip().lower()
            if not score_gate:
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage '{stage_id}' missing score_gate"
                )
            if score_gate not in score_policy_gates:
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage '{stage_id}' references unknown score_gate: "
                    f"{score_gate}"
                )
            gate_defaults = score_policy_gates.get(score_gate, {})
            gate_min_evidence = int(gate_defaults.get("minEvidenceCount", 0) or 0)
            try:
                min_evidence_count = int(stage_raw.get("min_evidence_count", gate_min_evidence) or gate_min_evidence)
            except (TypeError, ValueError) as exc:
                raise PolicyError(
                    f"workflow profile registry entry #{index} stage '{stage_id}' invalid min_evidence_count"
                ) from exc
            min_evidence_count = max(0, min_evidence_count)
            output_contract = self._normalize_json_contract(
                stage_raw.get("output_contract", {}),
                field_name=f"workflow profile registry entry #{index} stage '{stage_id}' output_contract",
            )
            verification_contract = self._normalize_json_contract(
                stage_raw.get("verification_contract", {}),
                field_name=(
                    f"workflow profile registry entry #{index} stage '{stage_id}' verification_contract"
                ),
            )
            stages[-1]["score_gate"] = score_gate
            stages[-1]["min_evidence_count"] = max(gate_min_evidence, min_evidence_count)
            stages[-1]["output_contract"] = output_contract
            stages[-1]["verification_contract"] = verification_contract
            stages[-1]["clarification_required_fields"] = self._merge_text_lists(
                stage_raw.get("clarification_required_fields", [])
            )
            parallel_execution = stage_raw.get("parallel_execution", {})
            if parallel_execution:
                stages[-1]["parallel_execution"] = self._normalize_json_contract(
                    parallel_execution,
                    field_name=(
                        f"workflow profile registry entry #{index} stage '{stage_id}' parallel_execution"
                    ),
                )
            simplification_hint = stage_raw.get("simplification_hint", {})
            if simplification_hint:
                stages[-1]["simplification_hint"] = self._normalize_json_contract(
                    simplification_hint,
                    field_name=(
                        f"workflow profile registry entry #{index} stage '{stage_id}' simplification_hint"
                    ),
                )
            optimization_hints = stage_raw.get("optimization_hints", {})
            if optimization_hints:
                stages[-1]["optimization_hints"] = self._normalize_json_contract(
                    optimization_hints,
                    field_name=(
                        f"workflow profile registry entry #{index} stage '{stage_id}' optimization_hints"
                    ),
                )

        default_stage_id = str(merged_entry.get("default_stage_id", "") or "").strip()
        if not default_stage_id:
            raise PolicyError(f"workflow profile registry entry #{index} missing default_stage_id")
        if default_stage_id.lower() not in seen_stage_ids:
            raise PolicyError(
                f"workflow profile registry entry #{index} default_stage_id not found in stages: {default_stage_id}"
            )

        task_type_stage_map_raw = merged_entry.get("task_type_stage_map", {})
        if not isinstance(task_type_stage_map_raw, dict):
            raise PolicyError(f"workflow profile registry entry #{index} task_type_stage_map must be an object")
        task_type_stage_map: dict[str, str] = {}
        for raw_task_type, raw_stage_id in task_type_stage_map_raw.items():
            task_type = str(raw_task_type or "").strip().lower()
            stage_id = str(raw_stage_id or "").strip()
            if not task_type or not stage_id:
                continue
            if stage_id.lower() not in seen_stage_ids:
                raise PolicyError(
                    f"workflow profile registry entry #{index} task_type_stage_map references unknown stage_id: {stage_id}"
                )
            task_type_stage_map[task_type] = stage_id

        return {
            "profile_id": profile_id,
            "channel": channel,
            "enabled": parse_bool(merged_entry.get("enabled", True), True),
            "display_name": str(merged_entry.get("display_name", profile_id) or profile_id).strip() or profile_id,
            "description": str(merged_entry.get("description", "") or "").strip(),
            "entry_task_types": entry_task_types,
            "promotion_target_channel": str(merged_entry.get("promotion_target_channel", "") or "").strip().lower(),
            "score_policy_ref": score_policy_ref,
            "runtime_entry": runtime_entry,
            "default_stage_id": default_stage_id,
            "task_type_stage_map": task_type_stage_map,
            "stages": stages,
        }


    def load_workflow_profile_registry(self) -> dict[str, Any]:
        """Load, backfill defaults, and validate the runtime workflow profile registry.

        Returns:
            dict[str, Any]: Normalized workflow registry payload with validated profile entries.

        Raises:
            PolicyError: Raised when registry format is invalid or default entry is missing.
        """
        registry_path = self.workflow_profile_registry_file()
        registry_raw = read_json(
            registry_path,
            DEFAULT_WORKFLOW_PROFILE_REGISTRY,
            write_if_missing=True,
        )
        if not isinstance(registry_raw, dict):
            raise PolicyError("workflow profile registry must be a JSON object")

        registry = merge_missing_keys(registry_raw, DEFAULT_WORKFLOW_PROFILE_REGISTRY)
        default_profile_id = str(
            registry.get("default_profile_id", DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_profile_id"]) or ""
        ).strip()
        if not default_profile_id:
            raise PolicyError("workflow profile registry default_profile_id must not be empty")

        default_channel = str(
            registry.get("default_channel", DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_channel"]) or ""
        ).strip().lower()
        if not default_channel:
            raise PolicyError("workflow profile registry default_channel must not be empty")

        profiles_raw = registry.get("profiles", [])
        if not isinstance(profiles_raw, list) or not profiles_raw:
            raise PolicyError("workflow profile registry profiles must be a non-empty list")

        profiles: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for index, item in enumerate(profiles_raw):
            profile = self._normalize_workflow_profile_entry(item, index=index)
            key = (profile["profile_id"].lower(), profile["channel"])
            if key in seen_keys:
                raise PolicyError(
                    "duplicate workflow profile registry entry: "
                    f"{profile['profile_id']}@{profile['channel']}"
                )
            seen_keys.add(key)
            profiles.append(profile)

        if (default_profile_id.lower(), default_channel) not in seen_keys:
            raise PolicyError(
                "workflow profile registry default entry missing: "
                f"{default_profile_id}@{default_channel}"
            )

        return {
            "schema_version": str(registry.get("schema_version", DEFAULT_WORKFLOW_PROFILE_REGISTRY["schema_version"])),
            "default_profile_id": default_profile_id,
            "default_channel": default_channel,
            "profiles": profiles,
        }


    def resolve_workflow_profile_entry(self, profile_id: str, channel: str) -> dict[str, Any]:
        """Resolve a workflow profile entry by profile id and channel.

        Args:
            profile_id: Workflow profile id, must not be empty.
            channel: Workflow channel, must not be empty.

        Returns:
            dict[str, Any]: Normalized workflow profile registry entry.

        Raises:
            PolicyError: Raised when profile id or channel is empty, unknown, or mismatched.
        """
        normalized_profile_id = str(profile_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_profile_id:
            raise PolicyError("workflow profile id must not be empty")
        if not normalized_channel:
            raise PolicyError("workflow profile channel must not be empty")

        profiles = self.workflow_profile_registry.get("profiles", [])
        for entry in profiles:
            if (
                str(entry.get("profile_id", "")).strip().lower() == normalized_profile_id.lower()
                and str(entry.get("channel", "")).strip().lower() == normalized_channel
            ):
                return entry

        available_channels = sorted(
            {
                str(entry.get("channel", "")).strip().lower()
                for entry in profiles
                if str(entry.get("profile_id", "")).strip().lower() == normalized_profile_id.lower()
            }
        )
        if available_channels:
            raise PolicyError(
                f"workflow profile '{normalized_profile_id}' has no channel '{normalized_channel}', "
                f"available channels: {', '.join(available_channels)}"
            )
        raise PolicyError(f"unknown workflow profile: {normalized_profile_id}")


    def resolve_workflow_stage_entry(
        self,
        *,
        profile_id: str,
        channel: str,
        task_type: str,
        stage_id: str = "",
    ) -> dict[str, Any]:
        """Resolve a workflow stage entry for a profile and task type."""
        profile_entry = self.resolve_workflow_profile_entry(profile_id, channel)
        stages = profile_entry.get("stages", [])
        if not isinstance(stages, list) or not stages:
            raise PolicyError(f"workflow profile '{profile_id}@{channel}' has no stages configured")

        normalized_stage_id = str(stage_id or "").strip()
        normalized_task_type = str(task_type or "").strip().lower()
        if normalized_stage_id:
            target_stage_id = normalized_stage_id
        else:
            task_type_stage_map = profile_entry.get("task_type_stage_map", {})
            target_stage_id = str(task_type_stage_map.get(normalized_task_type, "") or "").strip()
            if not target_stage_id:
                target_stage_id = str(profile_entry.get("default_stage_id", "") or "").strip()

        for entry in stages:
            if str(entry.get("stage_id", "")).strip().lower() == target_stage_id.lower():
                return entry

        raise PolicyError(
            f"workflow profile '{profile_id}@{channel}' has no stage '{target_stage_id}'"
        )


    def parse_workflow_selection_inputs(self, selection_json: str = "", selection_file: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {}
        path_text = str(selection_file or "").strip()
        if path_text:
            path = Path(path_text).expanduser()
            if not path.exists():
                raise PolicyError(f"workflow-selection-inputs-file not found: {path}")
            try:
                file_data = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise PolicyError(f"workflow-selection-inputs-file is not valid JSON: {exc}") from exc
            if not isinstance(file_data, dict):
                raise PolicyError("workflow-selection-inputs-file must be a JSON object")
            payload.update(file_data)
        payload.update(self.parse_optional_json_arg(selection_json, "workflow-selection-inputs-json"))
        return payload


    def resolve_keyword_group_workflow_override(
        self,
        matched_keyword_groups: list[str],
        *,
        selection_policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve workflow override metadata from selector keyword groups."""
        matched_group_set = {
            str(item or "").strip()
            for item in matched_keyword_groups
            if str(item or "").strip()
        }
        priority: list[str] = []
        for item in selection_policy.get("keyword_group_priority", []):
            group = str(item or "").strip()
            if group and group in matched_group_set and group not in priority:
                priority.append(group)
        for item in matched_keyword_groups:
            group = str(item or "").strip()
            if group and group not in priority:
                priority.append(group)

        mapping_raw = selection_policy.get("keyword_group_profile_map", {})
        if not isinstance(mapping_raw, dict) or not priority:
            return {
                "workflow_profile_id": "",
                "workflow_channel": "",
                "selection_reason": "",
                "matched_group": "",
                "fallback_profile_ids": [],
            }

        default_channel = (
            str(selection_policy.get("default_channel", DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_channel"]) or "")
            .strip()
            .lower()
            or DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_channel"]
        )
        fallback_profile_ids: list[str] = []
        for group in priority:
            mapping_entry = mapping_raw.get(group)
            if not mapping_entry:
                continue
            if isinstance(mapping_entry, str):
                profile_id = str(mapping_entry or "").strip()
                channel = default_channel
                selection_reason = ""
            elif isinstance(mapping_entry, dict):
                profile_id = str(mapping_entry.get("profile_id", "") or "").strip()
                channel = str(mapping_entry.get("channel", "") or "").strip().lower() or default_channel
                selection_reason = str(mapping_entry.get("selection_reason", "") or "").strip()
            else:
                continue
            if not profile_id:
                continue
            try:
                profile_entry = self.resolve_workflow_profile_entry(profile_id, channel)
            except PolicyError:
                fallback_profile_ids.append(profile_id)
                continue
            if not parse_bool(profile_entry.get("enabled", True), True):
                fallback_profile_ids.append(profile_id)
                continue
            return {
                "workflow_profile_id": profile_entry["profile_id"],
                "workflow_channel": profile_entry["channel"],
                "selection_reason": selection_reason or f"keyword_group_workflow_selection:{group}",
                "matched_group": group,
                "fallback_profile_ids": fallback_profile_ids,
            }
        return {
            "workflow_profile_id": "",
            "workflow_channel": "",
            "selection_reason": "",
            "matched_group": "",
            "fallback_profile_ids": fallback_profile_ids,
        }


    def select_workflow_for_request(
        self,
        *,
        description: str,
        task_type: str,
        request_source: str,
        source: str,
        assignee: str,
        needs_clarification: bool,
        context_payload: dict[str, Any] | None = None,
        workflow_profile_id: str = "",
        workflow_channel: str = "",
        selection_reason: str = "",
        selection_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Select a workflow profile for a request using the current selector policy.

        Args:
            description: Human-readable task description or requirement summary.
            task_type: Current task type, such as workflow or clarification_required.
            request_source: Original request source, such as human or ai.
            source: Source system hint.
            assignee: Current assignee chosen by routing.
            needs_clarification: Whether the task is waiting for clarification.
            context_payload: Optional structured context already extracted for the request.
            workflow_profile_id: Explicit workflow profile override when provided.
            workflow_channel: Explicit workflow channel override when provided.
            selection_reason: Explicit selection reason override when provided.
            selection_inputs: Additional selector inputs supplied by caller.

        Returns:
            dict[str, Any]: Normalized workflow selection result.
        """
        context_payload = context_payload if isinstance(context_payload, dict) else {}
        explicit_inputs = selection_inputs if isinstance(selection_inputs, dict) else {}
        normalized_task_type = str(task_type or "").strip().lower()
        selector_policy = self.workflow_selector_policy()
        selection_policy = self.workflow_selection_policy()
        default_reason = str(
            selection_policy.get("default_selection_reason", "default_coding_workflow_for_execution") or ""
        ).strip() or "default_coding_workflow_for_execution"

        if normalized_task_type in {
            str(item).strip().lower()
            for item in (selection_policy.get("skip_task_types", []) or [])
            if str(item).strip()
        }:
            return {
                "workflow_profile_id": "",
                "workflow_channel": "",
                "selection_reason": "",
                "selection_inputs": {},
            }

        description_text = str(description or "").strip()
        description_norm = description_text.lower()
        coding_hits = self._keyword_hits(description_norm, selector_policy.get("coding_task_keywords", []))
        research_hits = self._keyword_hits(description_norm, selector_policy.get("research_task_keywords", []))
        ops_hits = self._keyword_hits(description_norm, selector_policy.get("ops_task_keywords", []))
        docs_hits = self._keyword_hits(description_norm, selector_policy.get("docs_task_keywords", []))

        matched_keyword_groups: list[str] = []
        if normalized_task_type in {
            str(item).strip().lower()
            for item in (selector_policy.get("coding_task_types", []) or [])
            if str(item).strip()
        }:
            matched_keyword_groups.append("coding_task")
        if coding_hits and "coding_task" not in matched_keyword_groups:
            matched_keyword_groups.append("coding_task")
        if research_hits:
            matched_keyword_groups.append("research_task")
        if ops_hits:
            matched_keyword_groups.append("ops_task")
        if docs_hits:
            matched_keyword_groups.append("docs_task")
        if needs_clarification and "clarification_required" not in matched_keyword_groups:
            matched_keyword_groups.append("clarification_required")

        selector_inputs = {
            "selector_version": str(selector_policy.get("selector_version", "2026-03-22") or "2026-03-22"),
            "selector_state": "selected",
            "description_excerpt": self._selector_excerpt(description_text),
            "matched_keyword_groups": matched_keyword_groups or ["default_fallback"],
            "matched_keywords": {
                "coding_task": coding_hits,
                "research_task": research_hits,
                "ops_task": ops_hits,
                "docs_task": docs_hits,
            },
            "fallback_profile_ids": [],
            "context_fields": sorted(
                key for key, value in context_payload.items() if has_context_value(value)
            ),
        }
        selector_inputs.update(explicit_inputs)

        reason = str(selection_reason or "").strip() or default_reason
        selected_profile_id = str(workflow_profile_id or "").strip()
        selected_channel = str(workflow_channel or "").strip().lower()
        if not selected_profile_id:
            keyword_group_override = self.resolve_keyword_group_workflow_override(
                matched_keyword_groups,
                selection_policy=selection_policy,
            )
            fallback_profile_ids = keyword_group_override.get("fallback_profile_ids", [])
            if fallback_profile_ids:
                selector_inputs["fallback_profile_ids"] = fallback_profile_ids
            matched_group = str(keyword_group_override.get("matched_group", "") or "").strip()
            if matched_group:
                selector_inputs["selector_state"] = "keyword_group_override"
                selector_inputs["selected_keyword_group"] = matched_group
                selected_profile_id = str(keyword_group_override.get("workflow_profile_id", "") or "").strip()
                selected_channel = str(keyword_group_override.get("workflow_channel", "") or "").strip().lower()
                reason = str(keyword_group_override.get("selection_reason", "") or "").strip() or reason
        if not coding_hits and not matched_keyword_groups and parse_bool(
            selector_policy.get("prefer_default_on_unknown", True), True
        ):
            selector_inputs["matched_keyword_groups"] = ["default_fallback"]

        return self.resolve_workflow_selection(
            task_type=normalized_task_type,
            request_source=request_source,
            source=source,
            assignee=assignee,
            needs_clarification=needs_clarification,
            workflow_profile_id=selected_profile_id,
            workflow_channel=selected_channel,
            selection_reason=reason,
            selection_inputs=selector_inputs,
        )


    def select_workflow(self, args: argparse.Namespace) -> dict[str, Any]:
        """Select a workflow profile from CLI-style arguments.

        Args:
            args: Parsed CLI arguments or a namespace carrying selector inputs.

        Returns:
            dict[str, Any]: Normalized workflow selection result.
        """
        context_payload = self.parse_context_payload(
            getattr(args, "context_json", ""),
            getattr(args, "context_file", ""),
        )
        selection_inputs = self.parse_workflow_selection_inputs(
            getattr(args, "workflow_selection_inputs_json", ""),
            getattr(args, "workflow_selection_inputs_file", ""),
        )
        request_source = self.normalize_request_source(
            getattr(args, "request_source", ""),
            getattr(args, "source", ""),
        )
        return self.select_workflow_for_request(
            description=str(getattr(args, "description", "") or "").strip(),
            task_type=str(getattr(args, "task_type", "workflow") or "workflow").strip() or "workflow",
            request_source=request_source,
            source=str(getattr(args, "source", "") or "").strip(),
            assignee=str(getattr(args, "assignee", "") or "").strip(),
            needs_clarification=parse_bool(getattr(args, "needs_clarification", ""), False),
            context_payload=context_payload,
            workflow_profile_id=str(getattr(args, "workflow_profile_id", "") or "").strip(),
            workflow_channel=str(getattr(args, "workflow_channel", "") or "").strip(),
            selection_reason=str(getattr(args, "workflow_selection_reason", "") or "").strip(),
            selection_inputs=selection_inputs,
        )


    def resolve_workflow_selection(
        self,
        *,
        task_type: str,
        request_source: str,
        source: str,
        assignee: str,
        needs_clarification: bool,
        workflow_profile_id: str = "",
        workflow_channel: str = "",
        selection_reason: str = "",
        selection_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = self.workflow_selection_policy()
        registry_default_profile = str(
            self.workflow_profile_registry.get("default_profile_id", DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_profile_id"])
            or ""
        ).strip()
        registry_default_channel = str(
            self.workflow_profile_registry.get("default_channel", DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_channel"])
            or ""
        ).strip().lower() or DEFAULT_WORKFLOW_PROFILE_REGISTRY["default_channel"]
        normalized_task_type = str(task_type or "").strip().lower()
        explicit_profile = str(workflow_profile_id or "").strip()
        explicit_channel = str(workflow_channel or "").strip().lower()
        explicit_reason = str(selection_reason or "").strip()
        explicit_inputs = selection_inputs if isinstance(selection_inputs, dict) else {}
        default_profile = str(policy.get("default_profile_id", registry_default_profile) or "").strip() or registry_default_profile
        default_channel = (
            str(policy.get("default_channel", registry_default_channel) or registry_default_channel).strip().lower()
            or registry_default_channel
        )
        default_reason = str(
            policy.get("default_selection_reason", "default_coding_workflow_for_execution") or ""
        ).strip() or "default_coding_workflow_for_execution"
        apply_task_types = {
            str(item).strip().lower()
            for item in (policy.get("apply_task_types", ["workflow", "clarification_required"]) or [])
            if str(item).strip()
        }
        skip_task_types = {
            str(item).strip().lower()
            for item in (policy.get("skip_task_types", ["ops_runtime_cron"]) or [])
            if str(item).strip()
        }

        if explicit_profile:
            profile_id = explicit_profile
            channel = explicit_channel or default_channel
            reason = explicit_reason or "explicit_workflow_selection"
        elif normalized_task_type in skip_task_types:
            return {
                "workflow_profile_id": "",
                "workflow_channel": "",
                "selection_reason": "",
                "selection_inputs": {},
            }
        elif (not apply_task_types) or normalized_task_type in apply_task_types:
            profile_id = default_profile
            channel = explicit_channel or default_channel
            reason = explicit_reason or default_reason
        else:
            return {
                "workflow_profile_id": "",
                "workflow_channel": "",
                "selection_reason": "",
                "selection_inputs": {},
            }

        profile_entry = self.resolve_workflow_profile_entry(profile_id, channel)
        if not parse_bool(profile_entry.get("enabled", True), True):
            raise PolicyError(f"workflow profile is disabled: {profile_id}@{channel}")

        entry_task_types = {
            str(item).strip().lower()
            for item in (profile_entry.get("entry_task_types", []) or [])
            if str(item).strip()
        }
        if entry_task_types and normalized_task_type not in entry_task_types:
            raise PolicyError(
                f"workflow profile '{profile_entry['profile_id']}@{profile_entry['channel']}' "
                f"does not accept task_type '{normalized_task_type}'"
            )

        merged_inputs = {
            "task_type": normalized_task_type,
            "request_source": str(request_source or "").strip(),
            "source": str(source or "").strip(),
            "assignee": str(assignee or "").strip(),
            "needs_clarification": bool(needs_clarification),
            "workflow_profile_id": profile_entry["profile_id"],
            "workflow_channel": profile_entry["channel"],
        }
        merged_inputs.update(explicit_inputs)
        return {
            "workflow_profile_id": profile_entry["profile_id"],
            "workflow_channel": profile_entry["channel"],
            "selection_reason": reason,
            "selection_inputs": merged_inputs,
        }

"""Policy Enforcer — ContextMixin."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

from policy_defaults import DEFAULT_POLICY
from policy_utils import PolicyError, parse_bool, merge_missing_keys, has_context_value, get_context_field_value

class ContextMixin:
    """Mixin providing Context methods for PolicyEnforcer."""

    def context_policy(self) -> dict[str, Any]:
        raw = self.policy.get("context_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("context_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)


    def requirement_package_policy(self) -> dict[str, Any]:
        raw = self.policy.get("requirement_package_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("requirement_package_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)


    def parse_context_json_arg(self, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"context-json is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyError("context-json must be a JSON object")
        return data


    def parse_context_payload(self, context_json: str, context_file: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {}
        path_text = str(context_file or "").strip()
        if path_text:
            path = Path(path_text).expanduser()
            if not path.exists():
                raise PolicyError(f"context-file not found: {path}")
            try:
                file_data = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise PolicyError(f"context-file is not valid JSON: {exc}") from exc
            if not isinstance(file_data, dict):
                raise PolicyError("context-file must be a JSON object")
            payload.update(file_data)
        payload.update(self.parse_context_json_arg(context_json))
        return payload


    def parse_optional_json_arg(self, raw: str, field_name: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"{field_name} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyError(f"{field_name} must be a JSON object")
        return data


    def parse_text_list_arg(self, raw: str) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in text.split(","):
            value = item.strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(value)
        return out


    @staticmethod
    def _merge_text_lists(*groups: Any) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            if isinstance(group, (list, tuple, set)):
                values = group
            else:
                values = [group]
            for item in values:
                text = str(item or "").strip()
                if not text:
                    continue
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                merged.append(text)
        return merged


    def extract_context_from_text(self, text: str) -> dict[str, str]:
        raw = str(text or "").strip()
        location = ""
        first_seen = ""
        duration = ""
        impact = ""
        evidence = ""
        target_state = ""

        location_match = re.search(
            r"(https?://\S+|/[A-Za-z0-9._/\-]+(?:\?[^\s]+)?|[A-Za-z]:\\[^\s]+|[\w./-]+\.(?:py|js|ts|tsx|json|ya?ml|md|sql|sh|log))",
            raw,
        )
        if location_match:
            location = location_match.group(1)

        first_seen_match = re.search(r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", raw)
        if first_seen_match:
            first_seen = first_seen_match.group(0)

        duration_match = re.search(r"(持续[^，。；;\s]{1,24}|[0-9]+(?:分钟|小时|天|day|hour|min))", raw, flags=re.IGNORECASE)
        if duration_match:
            duration = duration_match.group(1)

        impact_keywords = ["影响", "阻塞", "不可用", "失败", "报错", "错误", "超时", "404", "500", "延迟", "回退"]
        for kw in impact_keywords:
            if kw in raw:
                impact = f"contains:{kw}"
                break

        evidence_match = re.search(
            r"(evidence[:：]?\s*[^\s，。；;]+|证据路径[:：]?\s*[^\s，。；;]+|/home/[^\s，。；;]+|[A-Za-z]:\\[^\s，。；;]+|[\w./-]+\.(?:json|log|txt))",
            raw,
        )
        if evidence_match:
            evidence = evidence_match.group(1)

        target_match = re.search(r"(修复[^，。；;\n]{1,40}|恢复[^，。；;\n]{1,40}|目标[^，。；;\n]{1,40}|需要[^，。；;\n]{1,40})", raw)
        if target_match:
            target_state = target_match.group(1)

        return {
            "problem": raw,
            "location": location,
            "first_seen_at": first_seen,
            "duration": duration,
            "impact": impact,
            "evidence": evidence,
            "target_state": target_state,
            "current_state": raw,
            "expected_state": target_state,
            "operation_path": location,
            "reproduction_steps": raw,
            "scope": "task_description",
            "constraints": "",
            "acceptance_criteria": "",
            "full_background": raw,
            "owner": "",
            "change_id": "",
        }


    def evaluate_context_gate(
        self,
        request_source: str,
        context_payload: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self.context_policy()
        if not parse_bool(cfg.get("enabled", True), True):
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": [],
            }

        if request_source != "ai":
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": [],
            }

        required_raw = cfg.get("ai_required_fields", [])
        if not isinstance(required_raw, list):
            raise PolicyError("context_policy.ai_required_fields must be a list")
        required_fields = [str(x).strip() for x in required_raw if str(x).strip()]

        recommended_raw = cfg.get("ai_recommended_fields", [])
        if not isinstance(recommended_raw, list):
            raise PolicyError("context_policy.ai_recommended_fields must be a list")
        recommended_fields = [str(x).strip() for x in recommended_raw if str(x).strip()]

        if not required_fields:
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": recommended_fields,
            }

        missing_fields = [field for field in required_fields if not has_context_value(context_payload.get(field))]
        missing_recommended_fields = [field for field in recommended_fields if not has_context_value(context_payload.get(field))]
        completeness = round(((len(required_fields) - len(missing_fields)) / len(required_fields)) * 100.0, 2)
        min_pct = float(cfg.get("ai_min_completeness_pct", 100.0) or 100.0)
        needs_clarification = completeness < min_pct or bool(missing_fields)
        reason = ""
        if needs_clarification:
            reason = (
                f"ai_context_incomplete: completeness={completeness:.2f}, "
                f"required={len(required_fields)}, missing={','.join(missing_fields)}"
            )
        return {
            "needs_clarification": needs_clarification,
            "clarification_reason": reason,
            "context_completeness": completeness,
            "missing_fields": missing_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "required_fields": required_fields,
            "recommended_fields": recommended_fields,
        }


    def evaluate_requirement_package_gate(
        self,
        *,
        request_source: str,
        task_type: str,
        context_payload: dict[str, Any],
        project_requirement: bool = False,
    ) -> dict[str, Any]:
        cfg = self.requirement_package_policy()
        if not parse_bool(cfg.get("enabled", True), True):
            return {
                "required": False,
                "package_ready": True,
                "needs_clarification": False,
                "clarification_reason": "",
                "required_fields": [],
                "recommended_fields": [],
                "missing_fields": [],
                "missing_recommended_fields": [],
                "triggered_by": "",
            }

        request_sources_raw = cfg.get("request_sources", [])
        request_sources = [str(item).strip().lower() for item in request_sources_raw if str(item).strip()]
        if request_sources and str(request_source or "").strip().lower() not in request_sources:
            return {
                "required": False,
                "package_ready": True,
                "needs_clarification": False,
                "clarification_reason": "",
                "required_fields": [],
                "recommended_fields": [],
                "missing_fields": [],
                "missing_recommended_fields": [],
                "triggered_by": "",
            }

        task_types_raw = cfg.get("task_types", [])
        task_types = [str(item).strip().lower() for item in task_types_raw if str(item).strip()]
        if task_types and str(task_type or "").strip().lower() not in task_types:
            return {
                "required": False,
                "package_ready": True,
                "needs_clarification": False,
                "clarification_reason": "",
                "required_fields": [],
                "recommended_fields": [],
                "missing_fields": [],
                "missing_recommended_fields": [],
                "triggered_by": "",
            }

        explicit_required = parse_bool(
            context_payload.get("requirement_package_required")
            or get_context_field_value(context_payload, "requirement_package.required"),
            False,
        )
        project_requirement_only = parse_bool(cfg.get("project_requirement_only", True), True)
        triggered_by = ""
        requirement_required = False
        if explicit_required:
            requirement_required = True
            triggered_by = "explicit_flag"
        elif project_requirement:
            requirement_required = True
            triggered_by = "project_requirement"
        elif not project_requirement_only:
            requirement_required = True
            triggered_by = "policy_default"

        required_fields = [str(item).strip() for item in cfg.get("required_fields", []) if str(item).strip()]
        recommended_fields = [str(item).strip() for item in cfg.get("recommended_fields", []) if str(item).strip()]
        if not requirement_required:
            return {
                "required": False,
                "package_ready": True,
                "needs_clarification": False,
                "clarification_reason": "",
                "required_fields": required_fields,
                "recommended_fields": recommended_fields,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "triggered_by": "",
            }

        missing_fields = [
            field_path
            for field_path in required_fields
            if not has_context_value(get_context_field_value(context_payload, field_path))
        ]
        missing_recommended_fields = [
            field_path
            for field_path in recommended_fields
            if not has_context_value(get_context_field_value(context_payload, field_path))
        ]
        package_ready = not missing_fields
        clarification_reason = ""
        if missing_fields:
            clarification_reason = (
                f"requirement_package_incomplete: triggered_by={triggered_by or 'unknown'}, "
                f"missing={','.join(missing_fields)}"
            )
        return {
            "required": True,
            "package_ready": package_ready,
            "needs_clarification": not package_ready,
            "clarification_reason": clarification_reason,
            "required_fields": required_fields,
            "recommended_fields": recommended_fields,
            "missing_fields": missing_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "triggered_by": triggered_by,
        }


    def evaluate_stage_context_gate(
        self,
        context_payload: dict[str, Any],
        workflow_stage_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Evaluate one workflow stage for extra clarification and execution hints."""

        stage_entry = workflow_stage_entry if isinstance(workflow_stage_entry, dict) else {}
        stage_id = str(stage_entry.get("stage_id", "")).strip()
        required_fields = self._merge_text_lists(stage_entry.get("clarification_required_fields", []))
        missing_fields = [field for field in required_fields if not has_context_value(context_payload.get(field))]
        clarification_reason = ""
        if missing_fields:
            clarification_reason = (
                f"stage_context_incomplete: stage={stage_id or 'unknown'}, "
                f"missing={','.join(missing_fields)}"
            )
        parallel_execution = stage_entry.get("parallel_execution", {})
        if not isinstance(parallel_execution, dict):
            parallel_execution = {}
        simplification_hint = stage_entry.get("simplification_hint", {})
        if not isinstance(simplification_hint, dict):
            simplification_hint = {}
        optimization_hints = stage_entry.get("optimization_hints", {})
        if not isinstance(optimization_hints, dict):
            optimization_hints = {}
        return {
            "evaluated_stage_id": stage_id,
            "required_fields": required_fields,
            "missing_fields": missing_fields,
            "needs_clarification": bool(missing_fields),
            "clarification_reason": clarification_reason,
            "parallel_execution": dict(parallel_execution),
            "simplification_hint": dict(simplification_hint),
            "optimization_hints": dict(optimization_hints),
        }


    def apply_stage_selection_inputs(
        self,
        selection_inputs_payload: dict[str, Any],
        workflow_stage_entry: dict[str, Any] | None,
        stage_context_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach resolved stage metadata and optimization hints into selector payload."""

        payload = dict(selection_inputs_payload or {})
        stage_entry = workflow_stage_entry if isinstance(workflow_stage_entry, dict) else {}
        context_gate = stage_context_gate if isinstance(stage_context_gate, dict) else {}
        if stage_entry:
            payload["stage_id"] = str(stage_entry.get("stage_id", "")).strip()
            payload["stage_display_name"] = str(stage_entry.get("display_name", "")).strip()
            payload["stage_score_gate"] = str(stage_entry.get("score_gate", "")).strip().lower()
            payload["stage_min_evidence_count"] = int(stage_entry.get("min_evidence_count", 0) or 0)
            output_contract = stage_entry.get("output_contract", {})
            payload["stage_output_contract"] = dict(output_contract) if isinstance(output_contract, dict) else {}
            verification_contract = stage_entry.get("verification_contract", {})
            payload["stage_verification_contract"] = (
                dict(verification_contract) if isinstance(verification_contract, dict) else {}
            )
            parallel_execution = stage_entry.get("parallel_execution", {})
            payload["stage_parallel_execution"] = (
                dict(parallel_execution) if isinstance(parallel_execution, dict) else {}
            )
            simplification_hint = stage_entry.get("simplification_hint", {})
            payload["stage_simplification_hint"] = (
                dict(simplification_hint) if isinstance(simplification_hint, dict) else {}
            )
            optimization_hints = stage_entry.get("optimization_hints", {})
            payload["stage_optimization_hints"] = (
                dict(optimization_hints) if isinstance(optimization_hints, dict) else {}
            )
            payload["stage_execution_strategy"] = {
                "parallel_execution": dict(payload["stage_parallel_execution"]),
                "simplification_hint": dict(payload["stage_simplification_hint"]),
                "optimization_hints": dict(payload["stage_optimization_hints"]),
            }
        if context_gate:
            payload["stage_context_gate"] = {
                "evaluated_stage_id": str(context_gate.get("evaluated_stage_id", "")).strip(),
                "required_fields": list(context_gate.get("required_fields", []))
                if isinstance(context_gate.get("required_fields", []), list)
                else [],
                "missing_fields": list(context_gate.get("missing_fields", []))
                if isinstance(context_gate.get("missing_fields", []), list)
                else [],
                "needs_clarification": bool(context_gate.get("needs_clarification", False)),
                "clarification_reason": str(context_gate.get("clarification_reason", "")).strip(),
                "rerouted_task_type": str(context_gate.get("rerouted_task_type", "")).strip(),
            }
            payload["stage_clarification_required_fields"] = list(
                payload["stage_context_gate"].get("required_fields", [])
            )
            payload["stage_missing_context_fields"] = list(payload["stage_context_gate"].get("missing_fields", []))
        return payload


    def is_human_project_requirement(self, text: str) -> tuple[bool, list[str]]:
        cfg = self.context_policy()
        keywords_raw = cfg.get("human_project_keywords", [])
        if not isinstance(keywords_raw, list):
            keywords_raw = []
        norm = re.sub(r"\s+", " ", str(text or "").strip().lower())
        hits = [str(x) for x in keywords_raw if str(x).strip() and str(x).lower() in norm]

        # Treat generic nouns like "workflow" or "readme" as weak signals so
        # ordinary docs/research/ops tasks are not misclassified as full project
        # requirement intake. Automatic requirement-package gating should only
        # trigger on stronger planning-oriented language.
        strong_markers = [
            "project requirement",
            "product requirement",
            "requirement package",
            "requirements package",
            "requirements doc",
            "requirements document",
            "prd",
            "scope definition",
            "project planning",
            "roadmap",
            "milestone",
            "需求包",
            "需求文档",
            "项目需求",
            "项目规划",
            "产品需求",
            "产品经理",
            "项目经理",
        ]
        weak_markers = {
            "workflow",
            "readme",
            "module",
            "architecture",
            "api docs",
            "api document",
        }
        strong_hits = [marker for marker in strong_markers if marker in norm]
        meaningful_hits = [hit for hit in hits if str(hit).strip().lower() not in weak_markers]
        if strong_hits:
            return True, self._merge_text_lists(strong_hits, hits)
        return len(meaningful_hits) >= 2, hits


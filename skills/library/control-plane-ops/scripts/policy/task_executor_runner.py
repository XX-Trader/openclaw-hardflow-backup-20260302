#!/usr/bin/env python3
"""Execute pending task-center items by invoking OpenClaw agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))
ROOT = POLICY_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_SHARED_DIR = Path(__file__).resolve().parents[5] / "scripts" / "openclaw-ops" / "shared"
if SOURCE_SHARED_DIR.exists() and str(SOURCE_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_SHARED_DIR))
SOURCE_WORKFLOW_MANAGER_DIR = (
    Path(__file__).resolve().parents[5]
    / "skills"
    / "library"
    / "openclaw-workflow-manager"
    / "scripts"
)
if SOURCE_WORKFLOW_MANAGER_DIR.exists() and str(SOURCE_WORKFLOW_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_WORKFLOW_MANAGER_DIR))

from utf8_runtime import configure_process_utf8_stdio
from chat_output import format_beijing_time
from workflow_views import build_task_executor_event, render_human_view
from policy_enforcer import PolicyEnforcer, RuntimePaths  # type: ignore
from policy_cli import cmd_init  # type: ignore
from policy_utils import runtime_defaults  # type: ignore
from alert_dedupe import (
    WORKFLOW_FAILURE_BUCKET,
    build_workflow_failure_signature,
    check_and_record_signature,
    extract_workflow_failure_tokens_from_task,
    load_dedupe_state,
    resolve_shared_alert_state_path,
    save_dedupe_state,
    workflow_tokens_from_job_ids,
)

configure_process_utf8_stdio()

UTC = timezone.utc
GOVERNANCE_BRIDGE_EPILOG = (
    "Bridge contract: this Python executor is usually triggered from official "
    "OpenClaw cron/hooks/webhook surfaces, uses structured JSON for machine output, "
    "and does not mutate vendor private runtime files directly."
)
AUTO_MODEL_SENTINELS = {"", "auto", "default"}
LEGACY_DEFAULT_MODEL = "volcengine/kimi-k2.5"
DEFAULT_THINKING_LEVEL = "high"
NOTIFY_ON_MODES = {"error", "activity", "always"}
ERROR_TASK_STATUSES = {"failed", "partial", "escalated"}
SUCCESS_TASK_STATUSES = {"passed", "resolved", "solved", "ok", "success"}
TASK_EXECUTOR_NOTIFY_STATE_KEY = "task_executor_notify"
TASK_EXECUTOR_NOTIFY_KEEP_DAYS = 14
VALIDATION_EVIDENCE_KEYWORDS = (
    "test",
    "tests",
    "pytest",
    "validation",
    "validate",
    "validated",
    "verify",
    "verified",
    "check",
    "checked",
    "验收",
    "验证",
    "测试",
    "复跑",
    "校验",
)
RETRYABLE_AGENT_ERROR_PATTERNS = (
    "api rate limit reached",
    "too many requests",
    "http_error:429",
    "status code: 429",
    "status=429",
    "failovererror: ⚠️ api rate limit reached",
)
DEFAULT_STRICT_PREFLIGHT_TASK_TYPES = (

    "github_web_evolution",
    "governance_evolution_context_preflight",
    "governance_evolution_optimize",
    "governance_evolution_review",
    "reviewer_technical_debt",
)


BENIGN_STDERR_PATTERNS = (
    "loaded without install/load-path provenance",
    "treat as untracked local code and pin trust via plugins.allow or install records",
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HERMES_SESSION_ID_RE = re.compile(r"(?im)^\s*(?:session_id|session id|SESSION_ID)\s*[:=]\s*([A-Za-z0-9_.:-]+)\s*$")
GATEWAY_ACK_TIMEOUT_MS = 30_000
GATEWAY_HISTORY_LIMIT = 200


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", str(text or ""))


def extract_hermes_session_id(text: str) -> str:
    match = HERMES_SESSION_ID_RE.search(strip_ansi(text))
    return str(match.group(1) or "").strip() if match else ""


def strip_hermes_session_lines(text: str) -> str:
    lines = []
    for line in strip_ansi(text).splitlines():
        if HERMES_SESSION_ID_RE.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    direct = parse_json_output(raw)
    if isinstance(direct, dict):
        return direct
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    for block in fenced:
        parsed = parse_json_output(block)
        if isinstance(parsed, dict):
            return parsed
    m = re.search(r"(\{[\s\S]*\})", raw)
    if m:
        parsed = parse_json_output(m.group(1))
        if isinstance(parsed, dict):
            return parsed
    return None


def split_list(value: Any) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
    else:
        text = str(value or "").strip()
        if not text:
            return []
        out = [x.strip() for x in re.split(r"[,\n;|，；、]+", text) if x.strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def load_agent_capability_index(manifest_file: Path) -> dict[str, dict[str, Any]]:
    if not manifest_file.exists():
        return {}
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    agents = payload.get("agents", []) if isinstance(payload, dict) else []
    if not isinstance(agents, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in agents:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agent_id", "")).strip()
        if not agent_id:
            continue
        index[agent_id] = item
    return index


def build_task_preflight(
    task: dict[str, Any],
    capability_index: dict[str, dict[str, Any]],
    planner_id: str = "",
) -> dict[str, Any]:
    assignee = str(task.get("assignee", "")).strip() or "backend-dev"
    required_skills = split_list(task.get("required_skills"))
    required_capabilities = split_list(task.get("required_capabilities"))
    allowed_agents = split_list(task.get("allowed_agents"))
    agent_profile = capability_index.get(assignee, {})
    declared_skills = split_list(agent_profile.get("declared_skills", []))
    capability_tokens = set(declared_skills)
    capability_mode = str(agent_profile.get("capability_mode", "")).strip()
    if capability_mode:
        capability_tokens.add(capability_mode)
    normalized_planner_id = str(planner_id or "").strip()
    planner_profile = capability_index.get(normalized_planner_id, {}) if normalized_planner_id else {}
    planner_allow_agents = split_list(planner_profile.get("allow_agents", []))

    warnings: list[str] = []
    if not agent_profile:
        warnings.append("assignee_not_registered")
    if allowed_agents and assignee not in allowed_agents:
        warnings.append("assignee_not_allowed")
    if normalized_planner_id and planner_allow_agents and assignee not in planner_allow_agents:
        warnings.append("assignee_not_in_planner_allowlist")

    declared_skill_set = set(declared_skills)
    missing_skills = [item for item in required_skills if item not in declared_skill_set]
    missing_capabilities = [item for item in required_capabilities if item not in capability_tokens]
    if missing_skills:
        warnings.append("required_skills_unmet")
    if missing_capabilities:
        warnings.append("required_capabilities_unmet")
    recommended_agents = list(allowed_agents)
    if planner_allow_agents:
        if recommended_agents:
            planner_intersection = [item for item in recommended_agents if item in planner_allow_agents]
            recommended_agents = planner_intersection or list(planner_allow_agents)
        else:
            recommended_agents = list(planner_allow_agents)
    workflow_profile_id = str(task.get("workflow_profile_id", "")).strip()
    workflow_channel = str(task.get("workflow_channel", "")).strip().lower()
    stage_id = str(task.get("stage_id", "")).strip()
    stage_score_gate = str(task.get("stage_score_gate", "")).strip().lower()
    try:
        stage_min_evidence_count = max(0, int(task.get("stage_min_evidence_count", 0) or 0))
    except (TypeError, ValueError):
        stage_min_evidence_count = 0
    stage_output_contract_raw = task.get("stage_output_contract", {})
    if isinstance(stage_output_contract_raw, str):
        try:
            stage_output_contract = json.loads(stage_output_contract_raw) if stage_output_contract_raw.strip() else {}
        except json.JSONDecodeError:
            stage_output_contract = {}
    elif isinstance(stage_output_contract_raw, dict):
        stage_output_contract = stage_output_contract_raw
    else:
        stage_output_contract = {}
    stage_verification_contract_raw = task.get("stage_verification_contract", {})
    if isinstance(stage_verification_contract_raw, str):
        try:
            stage_verification_contract = (
                json.loads(stage_verification_contract_raw) if stage_verification_contract_raw.strip() else {}
            )
        except json.JSONDecodeError:
            stage_verification_contract = {}
    elif isinstance(stage_verification_contract_raw, dict):
        stage_verification_contract = stage_verification_contract_raw
    else:
        stage_verification_contract = {}
    selection_reason = str(task.get("selection_reason", "")).strip()
    selection_inputs_raw = task.get("selection_inputs", {})
    if isinstance(selection_inputs_raw, str):
        try:
            parsed_selection_inputs = json.loads(selection_inputs_raw) if selection_inputs_raw.strip() else {}
        except json.JSONDecodeError:
            parsed_selection_inputs = {}
    elif isinstance(selection_inputs_raw, dict):
        parsed_selection_inputs = selection_inputs_raw
    else:
        parsed_selection_inputs = {}
    capability_binding = (
        parsed_selection_inputs.get("capability_binding", {})
        if isinstance(parsed_selection_inputs.get("capability_binding", {}), dict)
        else {}
    )
    capability_declarations = (
        capability_binding.get("capability_declarations", [])
        if isinstance(capability_binding.get("capability_declarations", []), list)
        else []
    )
    capability_declarations = [item for item in capability_declarations if isinstance(item, dict)]
    capability_contracts = (
        capability_binding.get("capability_contracts", {})
        if isinstance(capability_binding.get("capability_contracts", {}), dict)
        else {}
    )
    resolved_agent_profile = (
        capability_binding.get("resolved_agent_profile", {})
        if isinstance(capability_binding.get("resolved_agent_profile", {}), dict)
        else {}
    )
    resolved_assignee = str(capability_binding.get("resolved_assignee", "")).strip() or assignee
    stage_context_gate = (
        parsed_selection_inputs.get("stage_context_gate", {})
        if isinstance(parsed_selection_inputs.get("stage_context_gate", {}), dict)
        else {}
    )
    stage_parallel_execution = (
        parsed_selection_inputs.get("stage_parallel_execution", {})
        if isinstance(parsed_selection_inputs.get("stage_parallel_execution", {}), dict)
        else {}
    )
    stage_simplification_hint = (
        parsed_selection_inputs.get("stage_simplification_hint", {})
        if isinstance(parsed_selection_inputs.get("stage_simplification_hint", {}), dict)
        else {}
    )
    stage_optimization_hints = (
        parsed_selection_inputs.get("stage_optimization_hints", {})
        if isinstance(parsed_selection_inputs.get("stage_optimization_hints", {}), dict)
        else {}
    )
    requirement_package_gate = (
        parsed_selection_inputs.get("requirement_package_gate", {})
        if isinstance(parsed_selection_inputs.get("requirement_package_gate", {}), dict)
        else {}
    )
    task_id = str(task.get("task_id", "")).strip()
    trace_id = str(task.get("trace_id", "")).strip() or str(parsed_selection_inputs.get("trace_id", "")).strip()
    if not trace_id and task_id:
        trace_id = f"trace-{task_id}"
    attempt_id = (
        str(task.get("attempt_id", "")).strip()
        or str(parsed_selection_inputs.get("attempt_id", "")).strip()
        or "attempt-001"
    )
    required_runtime = split_list(capability_binding.get("required_runtime", []))
    tool_requirements = split_list(capability_binding.get("tool_requirements", []))
    execution_envelope = (
        parsed_selection_inputs.get("execution_envelope", {})
        if isinstance(parsed_selection_inputs.get("execution_envelope", {}), dict)
        else {}
    )
    execution_envelope = dict(execution_envelope)
    envelope_workflow = execution_envelope.get("workflow", {})
    if not isinstance(envelope_workflow, dict):
        envelope_workflow = {}
    envelope_workflow.update(
        {
            "profile_id": workflow_profile_id,
            "channel": workflow_channel,
            "stage_id": stage_id,
            "selection_reason": selection_reason,
        }
    )
    envelope_routing = execution_envelope.get("routing", {})
    if not isinstance(envelope_routing, dict):
        envelope_routing = {}
    envelope_routing.update(
        {
            "assignee": assignee,
            "allowed_agents": list(allowed_agents),
        }
    )
    envelope_capability_binding = execution_envelope.get("capability_binding", {})
    if not isinstance(envelope_capability_binding, dict):
        envelope_capability_binding = {}
    envelope_capability_binding.update(
        {
            "resolved_assignee": resolved_assignee,
            "capability_declarations": capability_declarations,
            "capability_contracts": capability_contracts,
            "resolved_agent_profile": resolved_agent_profile,
        }
    )
    envelope_capability_binding.update(
        {
            "required_capabilities": list(required_capabilities),
            "required_skills": list(required_skills),
            "required_runtime": list(required_runtime),
            "tool_requirements": list(tool_requirements),
        }
    )
    envelope_contracts = execution_envelope.get("contracts", {})
    if not isinstance(envelope_contracts, dict):
        envelope_contracts = {}
    envelope_contracts.update(
        {
            "output_contract": dict(stage_output_contract),
            "verification_contract": dict(stage_verification_contract),
            "stage_context_gate": dict(stage_context_gate),
        }
    )
    execution_envelope.update(
        {
            "schema_version": str(execution_envelope.get("schema_version", "2026-03-23")).strip() or "2026-03-23",
            "trace_id": trace_id,
            "attempt_id": attempt_id,
            "task_id": task_id,
            "workflow": envelope_workflow,
            "routing": envelope_routing,
            "capability_binding": envelope_capability_binding,
            "contracts": envelope_contracts,
        }
    )
    parsed_selection_inputs["trace_id"] = trace_id
    parsed_selection_inputs["attempt_id"] = attempt_id
    parsed_selection_inputs["execution_envelope"] = execution_envelope
    agent_declared_runtime = split_list(agent_profile.get("declared_runtime", []))
    agent_available_tools = split_list(agent_profile.get("available_tools", []))
    runtime_inventory_declared = "declared_runtime" in agent_profile
    tool_inventory_declared = "available_tools" in agent_profile
    missing_runtime_requirements = []
    missing_tool_requirements = []
    if runtime_inventory_declared:
        declared_runtime_set = set(agent_declared_runtime)
        missing_runtime_requirements = [item for item in required_runtime if item not in declared_runtime_set]
        if missing_runtime_requirements:
            warnings.append("required_runtime_unmet")
    if tool_inventory_declared:
        available_tool_set = set(agent_available_tools)
        missing_tool_requirements = [item for item in tool_requirements if item not in available_tool_set]
        if missing_tool_requirements:
            warnings.append("tool_requirements_unmet")

    return {
        "ok": not warnings,
        "assignee": assignee,
        "planner_id": normalized_planner_id,
        "warnings": warnings,
        "allowed_agents": allowed_agents,
        "planner_allow_agents": planner_allow_agents,
        "recommended_agents": recommended_agents,
        "required_skills": required_skills,
        "required_capabilities": required_capabilities,
        "resolved_assignee": resolved_assignee,
        "resolved_agent_profile": resolved_agent_profile,
        "capability_declarations": capability_declarations,
        "capability_contracts": capability_contracts,
        "required_runtime": required_runtime,
        "tool_requirements": tool_requirements,
        "stage_id": stage_id,
        "stage_score_gate": stage_score_gate,
        "stage_min_evidence_count": stage_min_evidence_count,
        "stage_output_contract": stage_output_contract,
        "stage_verification_contract": stage_verification_contract,
        "stage_context_gate": stage_context_gate,
        "stage_parallel_execution": stage_parallel_execution,
        "stage_simplification_hint": stage_simplification_hint,
        "stage_execution_strategy": {
            "parallel_execution": dict(stage_parallel_execution),
            "simplification_hint": dict(stage_simplification_hint),
            "optimization_hints": dict(stage_optimization_hints),
        },
        "stage_optimization_hints": stage_optimization_hints,
        "missing_skills": missing_skills,
        "missing_capabilities": missing_capabilities,
        "missing_runtime_requirements": missing_runtime_requirements,
        "missing_tool_requirements": missing_tool_requirements,
        "workflow_profile_id": workflow_profile_id,
        "workflow_channel": workflow_channel,
        "selection_reason": selection_reason,
        "requirement_package_gate": requirement_package_gate,
        "trace_id": trace_id,
        "attempt_id": attempt_id,
        "execution_envelope": execution_envelope,
        "selection_inputs": parsed_selection_inputs,
    }


def parse_strict_preflight_task_types(raw: Any) -> set[str]:
    return {item.lower() for item in split_list(raw) if item}


def _counter_key(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _increment_counter(bucket: dict[str, int], key: str) -> None:
    bucket[key] = int(bucket.get(key, 0) or 0) + 1


def record_preflight_observation(
    summary: dict[str, Any],
    *,
    task_type: str,
    assignee: str,
    preflight: dict[str, Any],
    strict_task_types: set[str],
) -> dict[str, bool]:
    warnings = split_list(preflight.get("warnings"))
    normalized_task_type = _counter_key(task_type, "(unknown)")
    normalized_assignee = _counter_key(assignee, "(unassigned)")
    has_warnings = bool(warnings)
    strict_blocked = has_warnings and normalized_task_type.lower() in strict_task_types
    if not has_warnings:
        return {"has_warnings": False, "strict_blocked": False}

    summary["preflight_warning_tasks"] = int(summary.get("preflight_warning_tasks", 0) or 0) + 1
    warning_by_type = summary.setdefault("preflight_warning_by_task_type", {})
    warning_by_assignee = summary.setdefault("preflight_warning_by_assignee", {})
    warning_codes = summary.setdefault("preflight_warning_codes", {})
    if isinstance(warning_by_type, dict):
        _increment_counter(warning_by_type, normalized_task_type)
    if isinstance(warning_by_assignee, dict):
        _increment_counter(warning_by_assignee, normalized_assignee)
    if isinstance(warning_codes, dict):
        for code in warnings:
            _increment_counter(warning_codes, code)

    if strict_blocked:
        summary["preflight_blocked_tasks"] = int(summary.get("preflight_blocked_tasks", 0) or 0) + 1
        blocked_by_type = summary.setdefault("preflight_blocked_by_task_type", {})
        blocked_by_assignee = summary.setdefault("preflight_blocked_by_assignee", {})
        if isinstance(blocked_by_type, dict):
            _increment_counter(blocked_by_type, normalized_task_type)
        if isinstance(blocked_by_assignee, dict):
            _increment_counter(blocked_by_assignee, normalized_assignee)

    return {"has_warnings": True, "strict_blocked": strict_blocked}


def build_preflight_reassign_payload(task: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id", "")).strip()
    task_type = str(task.get("task_type", "")).strip()
    assignee = str(task.get("assignee", "")).strip() or "backend-dev"
    warnings = split_list(preflight.get("warnings"))
    recommended_agents = split_list(preflight.get("recommended_agents")) or split_list(preflight.get("allowed_agents"))
    missing_skills = split_list(preflight.get("missing_skills"))
    missing_capabilities = split_list(preflight.get("missing_capabilities"))
    summary_parts = [
        f"high-risk task {task_id or '-'} was blocked before execution",
        f"assignee={assignee}",
    ]
    if task_type:
        summary_parts.append(f"task_type={task_type}")
    if missing_skills:
        summary_parts.append(f"missing_skills={','.join(missing_skills)}")
    if missing_capabilities:
        summary_parts.append(f"missing_capabilities={','.join(missing_capabilities)}")
    if recommended_agents:
        summary_parts.append(f"recommended_agents={','.join(recommended_agents)}")
    return {
        "need_reassign": True,
        "reason_code": "preflight_strict_blocked",
        "summary": "; ".join(summary_parts),
        "task_id": task_id,
        "task_type": task_type,
        "current_assignee": assignee,
        "recommended_agents": recommended_agents,
        "warnings": warnings,
        "missing_skills": missing_skills,
        "missing_capabilities": missing_capabilities,
    }


def load_policy(policy_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(policy_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_codex_model(model_name: str) -> bool:
    return str(model_name or "").strip().startswith("openai-codex/")


def normalize_thinking(value: Any, default: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"off", "minimal", "low", "medium", "high", "xhigh", "adaptive"}:
        return normalized
    return str(default or "").strip().lower()


def resolve_executor_selection(requested_model: str, assignee: str, policy_file: Path) -> tuple[str, str, str]:
    normalized = str(requested_model or "").strip()
    if normalized and normalized.lower() not in AUTO_MODEL_SENTINELS:
        policy = load_policy(policy_file)
        thinking_map = policy.get("model_thinking_overrides", {})
        thinking = ""
        if isinstance(thinking_map, dict):
            thinking = normalize_thinking(thinking_map.get(normalized), DEFAULT_THINKING_LEVEL)
        if not thinking:
            thinking = DEFAULT_THINKING_LEVEL
        return normalized, "cli", thinking

    policy = load_policy(policy_file)
    if not policy:
        return LEGACY_DEFAULT_MODEL, "legacy-default", DEFAULT_THINKING_LEVEL

    agent_overrides = policy.get("agent_model_overrides", {})
    if isinstance(agent_overrides, dict):
        assignee_key = str(assignee or "").strip()
        target = str(agent_overrides.get(assignee_key, "")).strip()
        if target:
            thinking_map = policy.get("model_thinking_overrides", {})
            thinking = ""
            if isinstance(thinking_map, dict):
                thinking = normalize_thinking(thinking_map.get(target), DEFAULT_THINKING_LEVEL)
            if not thinking:
                thinking = DEFAULT_THINKING_LEVEL
            return target, f"policy-agent:{assignee_key}", thinking

    thinking_map = policy.get("model_thinking_overrides", {})
    primary = str(policy.get("primary_model", "")).strip()
    allowed_raw = policy.get("allowed_models", [])
    allowed = [str(item).strip() for item in allowed_raw if str(item).strip()] if isinstance(allowed_raw, list) else []
    if primary and primary in allowed:
        thinking = normalize_thinking(thinking_map.get(primary), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return primary, "policy-primary", (thinking or DEFAULT_THINKING_LEVEL)
    if allowed:
        thinking = normalize_thinking(thinking_map.get(allowed[0]), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return allowed[0], "policy-allowed[0]", (thinking or DEFAULT_THINKING_LEVEL)
    if primary:
        thinking = normalize_thinking(thinking_map.get(primary), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return primary, "policy-primary", (thinking or DEFAULT_THINKING_LEVEL)
    return LEGACY_DEFAULT_MODEL, "legacy-default", DEFAULT_THINKING_LEVEL


def normalize_contract(reply_text: str) -> dict[str, Any]:
    parsed = extract_json_object(reply_text) or {}
    status = str(parsed.get("status", "")).strip().lower()
    solved = bool(parsed.get("solved", False))
    if status not in {"passed", "failed", "partial", "escalated"}:
        status = "passed" if solved else "partial"
    if status == "passed":
        solved = True

    try:
        quality_score = float(parsed.get("quality_score", 70.0))
    except Exception:
        quality_score = 70.0
    quality_score = max(0.0, min(100.0, quality_score))

    quality_grade = str(parsed.get("quality_grade", "")).strip().lower()
    if quality_grade not in {"a", "b", "c", "d"}:
        quality_grade = "a" if quality_score >= 90 else ("b" if quality_score >= 80 else ("c" if quality_score >= 70 else "d"))

    failed_items = split_list(parsed.get("failed_items"))
    failure_count = int(parsed.get("failure_count", len(failed_items) or (1 if status in {"failed", "partial"} else 0)) or 0)
    failure_count = max(0, failure_count)

    summary = str(parsed.get("resolution_summary", "")).strip() or str(reply_text or "").strip()[:400]
    steps = split_list(parsed.get("resolution_steps"))
    resolved = split_list(parsed.get("resolved_issues"))
    missing = split_list(parsed.get("context_fields_missing"))

    try:
        cost_estimate = float(parsed.get("cost_estimate", 0.0))
    except Exception:
        cost_estimate = 0.0
    cost_estimate = max(0.0, cost_estimate)

    return {
        "status": status,
        "solved": solved,
        "resolution_summary": summary,
        "resolution_steps": steps,
        "resolved_issues": resolved,
        "failed_items": failed_items,
        "failure_count": failure_count,
        "quality_score": quality_score,
        "quality_grade": quality_grade,
        "need_clarification": bool(parsed.get("need_clarification", False)),
        "clarification_reason": str(parsed.get("clarification_reason", "")).strip(),
        "context_fields_missing": missing,
        "cost_estimate": cost_estimate,
        "raw_text": str(reply_text or "").strip(),
    }


def parse_stage_contract_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = str(value or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def collect_stage_contract_evidence(contract: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    candidates: list[str] = []
    summary = str(contract.get("resolution_summary", "")).strip()
    if summary:
        candidates.append(summary)
    candidates.extend(split_list(contract.get("resolution_steps")))
    candidates.extend(split_list(contract.get("resolved_issues")))
    candidates.extend(f"failed:{item}" for item in split_list(contract.get("failed_items")))
    candidates.extend(f"context_missing:{item}" for item in split_list(contract.get("context_fields_missing")))
    clarification_reason = str(contract.get("clarification_reason", "")).strip()
    if clarification_reason:
        candidates.append(f"clarification:{clarification_reason}")

    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        evidence.append(text)
    return evidence


def has_validation_evidence(contract: dict[str, Any]) -> bool:
    text_blob = " ".join(
        [
            str(contract.get("resolution_summary", "")).strip(),
            str(contract.get("raw_text", "")).strip(),
            " ".join(split_list(contract.get("resolution_steps"))),
            " ".join(split_list(contract.get("resolved_issues"))),
            " ".join(split_list(contract.get("failed_items"))),
        ]
    ).lower()
    return any(keyword in text_blob for keyword in VALIDATION_EVIDENCE_KEYWORDS if keyword)


def deliverable_present(deliverable: str, contract: dict[str, Any]) -> bool:
    name = str(deliverable or "").strip().lower()
    summary = str(contract.get("resolution_summary", "")).strip()
    has_summary = bool(summary)
    has_steps = bool(split_list(contract.get("resolution_steps")))
    has_resolved = bool(split_list(contract.get("resolved_issues")))
    status = str(contract.get("status", "")).strip().lower()
    missing_context = split_list(contract.get("context_fields_missing"))
    need_clarification = bool(contract.get("need_clarification", False))

    if name == "clarified_requirement":
        return has_summary or has_steps or has_resolved
    if name == "context_payload":
        return (not missing_context) or need_clarification or status == "escalated"
    if name == "code_changes":
        return has_summary or has_steps or has_resolved
    if name == "verification_result":
        return has_validation_evidence(contract)
    if name == "review_decision":
        return status in {"passed", "failed", "partial", "escalated"} and (has_summary or has_resolved)
    if name == "acceptance_summary":
        return has_summary or has_steps
    return has_summary or has_steps or has_resolved


def verification_check_passed(check_name: str, contract: dict[str, Any]) -> bool:
    name = str(check_name or "").strip().lower()
    summary = str(contract.get("resolution_summary", "")).strip()
    status = str(contract.get("status", "")).strip().lower()
    missing_context = split_list(contract.get("context_fields_missing"))
    need_clarification = bool(contract.get("need_clarification", False))

    if name == "context_complete_or_escalated":
        return (not missing_context) or need_clarification or status == "escalated"
    if name == "tests_or_validation_recorded":
        return has_validation_evidence(contract)
    if name == "review_completed":
        return status in {"passed", "failed", "partial", "escalated"} and bool(summary)
    return bool(summary or split_list(contract.get("resolution_steps")) or split_list(contract.get("resolved_issues")))


def evaluate_stage_contract(task: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    stage_id = str(task.get("stage_id", "")).strip()
    score_gate = str(task.get("stage_score_gate", "")).strip().lower()
    try:
        min_evidence_count = max(0, int(task.get("stage_min_evidence_count", 0) or 0))
    except (TypeError, ValueError):
        min_evidence_count = 0
    output_contract = parse_stage_contract_object(task.get("stage_output_contract", {}))
    verification_contract = parse_stage_contract_object(task.get("stage_verification_contract", {}))
    deliverables = split_list(output_contract.get("deliverables", []))
    checks = split_list(verification_contract.get("checks", []))
    evidence = collect_stage_contract_evidence(contract)
    evidence_count = len(evidence)

    deliverable_results = [
        {"deliverable": deliverable, "present": deliverable_present(deliverable, contract)}
        for deliverable in deliverables
    ]
    verification_results = [
        {"check": check_name, "passed": verification_check_passed(check_name, contract)}
        for check_name in checks
    ]
    missing_deliverables = [item["deliverable"] for item in deliverable_results if not bool(item.get("present", False))]
    failed_checks = [item["check"] for item in verification_results if not bool(item.get("passed", False))]
    deliverables_passed = not missing_deliverables
    verification_passed = not failed_checks
    evidence_passed = evidence_count >= min_evidence_count

    return {
        "stage_id": stage_id,
        "score_gate": score_gate,
        "min_evidence_count": min_evidence_count,
        "evidence": evidence,
        "evidence_count": evidence_count,
        "evidence_passed": evidence_passed,
        "output_contract": output_contract,
        "verification_contract": verification_contract,
        "deliverables": deliverables,
        "checks": checks,
        "deliverable_results": deliverable_results,
        "verification_results": verification_results,
        "missing_deliverables": missing_deliverables,
        "failed_checks": failed_checks,
        "deliverables_passed": deliverables_passed,
        "verification_passed": verification_passed,
        "contract_passed": evidence_passed and deliverables_passed and verification_passed,
        "contract_status": str(contract.get("status", "")).strip().lower(),
    }


def sanitize_agent_stderr(stderr_text: str) -> str:
    lines = [line.strip() for line in str(stderr_text or "").splitlines() if line.strip()]
    kept: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(pattern in lowered for pattern in BENIGN_STDERR_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def contract_from_agent_result(exit_code: int, stdout_text: str, stderr_text: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    agent_json = parse_json_output(stdout_text) or {}
    payloads = agent_json.get("payloads", [])
    reply_text = ""
    if isinstance(payloads, list):
        reply_text = "\n".join(str(x.get("text", "")).strip() for x in payloads if isinstance(x, dict) and str(x.get("text", "")).strip())
    if not reply_text:
        reply_text = str(stdout_text or "").strip()

    sanitized_stderr = sanitize_agent_stderr(stderr_text)
    if int(exit_code or 0) != 0 and (not reply_text):
        reply_text = sanitized_stderr or str(stderr_text or "").strip()

    contract = normalize_contract(reply_text)
    if int(exit_code or 0) != 0:
        contract["status"] = "failed"
        contract["solved"] = False
        contract["failure_count"] = max(1, int(contract.get("failure_count", 0)))
    elif not reply_text:
        contract["status"] = "failed"
        contract["solved"] = False
        contract["failure_count"] = max(1, int(contract.get("failure_count", 0)))
        contract["resolution_summary"] = "agent_returned_no_structured_output"
        contract["raw_text"] = sanitized_stderr

    return contract, agent_json, reply_text, sanitized_stderr


def default_stage(assignee: str) -> str:
    agent = str(assignee or "").strip().lower()
    if agent in {"coordinator", "project-agent"}:
        return "plan"
    if agent == "tester":
        return "test-loop"
    if agent == "reviewer":
        return "review"
    if agent == "doc-writer":
        return "document"
    if agent == "deployer":
        return "deploy"
    return "implement"


def normalize_notify_on(value: str) -> str:
    mode = str(value or "error").strip().lower()
    return mode if mode in NOTIFY_ON_MODES else "error"


def compact_text(value: Any, max_len: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_task_session_id(task_id: str, max_len: int = 48) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(task_id or "").strip()).strip("-._")
    if not normalized:
        normalized = "task"
    candidate = f"task-{normalized}"
    if len(candidate) <= max_len:
        return candidate
    digest = hashlib.sha1(str(task_id or "").encode("utf-8")).hexdigest()[:10]
    head_budget = max(8, max_len - len("task--") - len(digest))
    head = normalized[:head_budget].rstrip("-._") or "task"
    session_id = f"task-{head}-{digest}"
    return session_id[:max_len]


def normalize_agent_session_token(value: str, fallback: str = "main") -> str:
    token = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-_")
    return token[:64] or fallback


def build_gateway_agent_session_key(assignee: str, session_id: str) -> str:
    agent_id = normalize_agent_session_token(assignee, fallback="main")
    run_token = normalize_agent_session_token(session_id, fallback="task")
    return f"agent:{agent_id}:cron:task-executor:run:{run_token}"


def extract_latest_assistant_text(history_payload: dict[str, Any]) -> str:
    messages = history_payload.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for candidate in reversed(messages):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("role", "")).strip().lower() != "assistant":
            continue
        content = candidate.get("content", [])
        if not isinstance(content, list):
            continue
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).strip().lower() != "text":
                continue
            text = str(item.get("text", "")).strip()
            if text:
                texts.append(text)
        if texts:
            return "\n".join(texts).strip()
    return ""


def humanize_executor_detail(detail: str) -> str:
    text = compact_text(detail, 220)
    lower = text.lower()
    if lower in {"timeout", "timed out"}:
        return "超时"
    if lower == "waiting_human_confirm":
        return "等待人工确认"
    if lower == "needs_clarification":
        return "任务信息不足，需要补充上下文"
    return text or "未提供详细信息"


def humanize_executor_reason(reason: str, status: str) -> tuple[str, str]:
    raw = str(reason or "").strip()
    normalized_status = str(status or "").strip().lower()
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
    if normalized_status == "partial":
        return "任务仅部分完成", humanize_executor_detail(raw or "仅部分完成")
    if normalized_status == "escalated":
        return "任务已升级处理", humanize_executor_detail(raw or "已升级给更高优先级处理")
    if normalized_status == "failed":
        return "任务执行失败", humanize_executor_detail(raw)
    return "任务状态异常", humanize_executor_detail(raw or normalized_status or "unknown")


def result_is_error(item: dict[str, Any]) -> bool:
    status = str(item.get("status", "")).strip().lower()
    report_status = str(item.get("report_status", "")).strip().lower()
    task_status_after = str(item.get("task_status_after", "")).strip().lower()
    if status == "failed":
        return True
    if report_status in ERROR_TASK_STATUSES:
        return True
    if task_status_after in ERROR_TASK_STATUSES:
        return True
    return False


def humanize_task_stage_label(stage: Any) -> str:
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


def is_task_result_open(item: dict[str, Any]) -> bool:
    """Return whether the task result still needs human follow-up."""
    normalized_status = str(
        item.get("task_status_after", "") or item.get("report_status", "") or item.get("status", "")
    ).strip().lower()
    reason = str(item.get("reason", "")).strip().lower()
    if normalized_status in SUCCESS_TASK_STATUSES:
        return False
    if reason in {"waiting_human_confirm", "needs_clarification", "preflight_strict_blocked"}:
        return True
    if normalized_status in ERROR_TASK_STATUSES:
        return True
    if normalized_status in {"waiting_human_confirm", "needs_clarification"}:
        return True
    return result_is_error(item)


def build_task_notify_key(item: dict[str, Any]) -> str:
    task_id = str(item.get("task_id", "")).strip()
    if task_id:
        return task_id
    for field in ("task_requirement", "task_reason", "task_type"):
        value = compact_text(item.get(field, ""), 120)
        if value:
            digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
            return f"anonymous-{digest}"
    return ""


def build_task_notify_subject(item: dict[str, Any]) -> str:
    requirement = compact_text(item.get("task_requirement", ""), 96)
    if requirement:
        return requirement
    task_reason = compact_text(item.get("task_reason", ""), 96)
    if task_reason:
        return task_reason
    task_type = compact_text(item.get("task_type", ""), 64)
    if task_type:
        return f"{task_type} 任务"
    return "未命名任务"


def build_task_notify_progress(item: dict[str, Any]) -> str:
    reason = str(item.get("reason", "")).strip().lower()
    normalized_status = str(
        item.get("task_status_after", "") or item.get("report_status", "") or item.get("status", "")
    ).strip().lower()
    if reason == "preflight_strict_blocked":
        return "未执行"
    if reason == "waiting_human_confirm":
        return "等待人工确认"
    if reason == "needs_clarification":
        return "待补充上下文"
    if normalized_status in SUCCESS_TASK_STATUSES:
        return "已闭环"
    if normalized_status == "partial" or reason == "partial":
        return "部分完成"
    if normalized_status == "escalated" or reason == "escalated":
        return "已升级处理"
    if normalized_status in {"failed", "error", "timeout"} or reason:
        return "执行失败"
    return "状态待确认"


def build_task_notify_blocker(item: dict[str, Any]) -> str:
    reason = str(item.get("reason", "")).strip().lower()
    normalized_status = str(
        item.get("task_status_after", "") or item.get("report_status", "") or item.get("status", "")
    ).strip().lower()
    if reason == "preflight_strict_blocked":
        return "派单能力不匹配"
    if reason == "waiting_human_confirm":
        return "等待人工确认"
    if reason == "needs_clarification":
        return "上下文不足"
    if normalized_status in SUCCESS_TASK_STATUSES:
        return "无"
    issue, _detail = humanize_executor_reason(str(item.get("reason", "")), normalized_status)
    return compact_text(issue, 48) or "任务执行失败"


def build_task_notify_gap(item: dict[str, Any]) -> str:
    reason = str(item.get("reason", "")).strip().lower()
    normalized_status = str(
        item.get("task_status_after", "") or item.get("report_status", "") or item.get("status", "")
    ).strip().lower()
    if reason == "preflight_strict_blocked":
        reassign = item.get("preflight_reassign", {})
        if not isinstance(reassign, dict):
            reassign = {}
        recommended_agents = [str(x).strip() for x in reassign.get("recommended_agents", []) if str(x).strip()]
        if recommended_agents:
            return f"改派给 {','.join(recommended_agents)}"
        return "改派给满足能力约束的执行人"
    if reason == "waiting_human_confirm":
        return "人工确认后才能继续执行"
    if reason == "needs_clarification":
        return "补充任务背景或上下文后再执行"
    if normalized_status in SUCCESS_TASK_STATUSES:
        return "无"
    _issue, detail = humanize_executor_reason(str(item.get("reason", "")), normalized_status)
    detail_text = compact_text(detail, 96)
    if detail_text:
        return detail_text
    if normalized_status == "partial" or reason == "partial":
        return "继续补齐剩余项后再收口"
    return "补齐失败原因后再执行"


def build_task_executor_notify_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    key = build_task_notify_key(item)
    if not key:
        return {}
    stage = str(item.get("stage", "")).strip().lower()
    snapshot = {
        "task_id": str(item.get("task_id", "")).strip() or key,
        "key": key,
        "subject": build_task_notify_subject(item),
        "assignee": str(item.get("assignee", "")).strip() or "未分配",
        "stage": stage,
        "stage_label": humanize_task_stage_label(stage),
        "progress": build_task_notify_progress(item),
        "blocker": build_task_notify_blocker(item),
        "gap": build_task_notify_gap(item),
        "is_open": is_task_result_open(item),
    }
    raw = json.dumps(
        {
            "subject": snapshot["subject"],
            "assignee": snapshot["assignee"],
            "stage": snapshot["stage"],
            "progress": snapshot["progress"],
            "blocker": snapshot["blocker"],
            "gap": snapshot["gap"],
            "is_open": snapshot["is_open"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    snapshot["signature"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return snapshot


def _task_executor_notify_section(state: dict[str, Any]) -> dict[str, Any]:
    section = state.get(TASK_EXECUTOR_NOTIFY_STATE_KEY, {})
    if not isinstance(section, dict):
        section = {}
    entries = section.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    section["entries"] = entries
    return section


def _dedupe_task_ids(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def apply_task_executor_incremental_notify(
    summary: dict[str, Any],
    state_path: Path,
    *,
    now_text: str = "",
) -> dict[str, Any]:
    """Build incremental task-notify diff so unchanged executor runs stay quiet."""
    notify = {
        "suppressed": False,
        "mode": "initial",
        "new_count": 0,
        "changed_count": 0,
        "resolved_count": 0,
        "open_count": 0,
        "focus_task_ids": [],
        "resolved_items": [],
    }
    results = summary.get("results", [])
    if not isinstance(results, list):
        summary["task_change_notify"] = notify
        return notify

    state = load_dedupe_state(state_path)
    section = _task_executor_notify_section(state)
    entries = section.get("entries", {})
    current_at = datetime.fromisoformat((now_text or now_iso()).replace("Z", "+00:00")).astimezone(UTC)
    keep_after = current_at.timestamp() - (TASK_EXECUTOR_NOTIFY_KEEP_DAYS * 86400)
    for key, item in list(entries.items()):
        if not isinstance(item, dict):
            entries.pop(key, None)
            continue
        updated_at = item.get("updated_at", "")
        try:
            updated_ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00")).astimezone(UTC).timestamp()
        except Exception:
            updated_ts = 0.0
        if updated_ts >= keep_after:
            continue
        entries.pop(key, None)

    had_entries = bool(entries)
    focus_task_ids: list[str] = []
    resolved_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        snapshot = build_task_executor_notify_snapshot(item)
        if not snapshot:
            continue
        key = str(snapshot.get("key", "")).strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        previous = entries.get(key, {}) if isinstance(entries.get(key, {}), dict) else {}
        previous_open = bool(previous.get("is_open", False))
        previous_signature = str(previous.get("signature", "")).strip()
        current_open = bool(snapshot.get("is_open", False))
        if current_open:
            notify["open_count"] += 1
            if not previous or not previous_open:
                notify["new_count"] += 1
                focus_task_ids.append(str(snapshot.get("task_id", "")).strip() or key)
            elif previous_signature != str(snapshot.get("signature", "")).strip():
                notify["changed_count"] += 1
                focus_task_ids.append(str(snapshot.get("task_id", "")).strip() or key)
        elif previous_open:
            notify["resolved_count"] += 1
            resolved_items.append(
                {
                    "task_id": str(snapshot.get("task_id", "")).strip() or key,
                    "subject": str(snapshot.get("subject", "")).strip(),
                    "assignee": str(snapshot.get("assignee", "")).strip(),
                    "stage": str(snapshot.get("stage", "")).strip(),
                }
            )

        entries[key] = {
            "task_id": str(snapshot.get("task_id", "")).strip() or key,
            "subject": str(snapshot.get("subject", "")).strip(),
            "assignee": str(snapshot.get("assignee", "")).strip(),
            "stage": str(snapshot.get("stage", "")).strip(),
            "progress": str(snapshot.get("progress", "")).strip(),
            "blocker": str(snapshot.get("blocker", "")).strip(),
            "gap": str(snapshot.get("gap", "")).strip(),
            "is_open": current_open,
            "signature": str(snapshot.get("signature", "")).strip(),
            "updated_at": current_at.replace(microsecond=0).isoformat(),
        }

    notify["focus_task_ids"] = _dedupe_task_ids(focus_task_ids)
    notify["resolved_items"] = resolved_items[:3]
    if notify["new_count"] <= 0 and notify["changed_count"] <= 0 and notify["resolved_count"] <= 0:
        notify["suppressed"] = True
        notify["mode"] = "no_change"
    elif not had_entries:
        notify["mode"] = "initial"
    else:
        notify["mode"] = "delta"

    section["schema_version"] = "2026-03-17"
    section["updated_at"] = current_at.replace(microsecond=0).isoformat()
    section["entries"] = entries
    state[TASK_EXECUTOR_NOTIFY_STATE_KEY] = section
    save_dedupe_state(state_path, state)
    summary["task_change_notify"] = notify
    return notify


def build_chat_output(summary: dict[str, Any], report_path: Path, notify_on: str) -> str:
    event = build_task_executor_event(summary, report_path, normalize_notify_on(notify_on))
    return render_human_view(event["views"]["human"])


def apply_shared_alert_dedupe(
    summary: dict[str, Any],
    state_path: Path,
    *,
    cooldown_minutes: int,
    now_text: str = "",
) -> dict[str, Any]:
    dedupe = {
        "suppressed": False,
        "reason": "",
        "bucket": WORKFLOW_FAILURE_BUCKET,
        "signature": "",
        "tokens": [],
    }
    results = summary.get("results", [])
    if not isinstance(results, list):
        return dedupe
    error_items = [item for item in results if isinstance(item, dict) and result_is_error(item)]
    if not error_items:
        return dedupe

    tokens: list[str] = []
    for item in error_items:
        item_tokens = item.get("workflow_alert_tokens", [])
        if not isinstance(item_tokens, list) or not item_tokens:
            item_tokens = extract_workflow_failure_tokens_from_task(
                item.get("task_id", ""),
                task_type=item.get("task_type", ""),
                requirement=item.get("requirement", ""),
                context_payload=item.get("context_payload"),
            )
        if not item_tokens:
            return dedupe
        tokens.extend(item_tokens)

    normalized_tokens = workflow_tokens_from_job_ids(tokens)
    signature = build_workflow_failure_signature(normalized_tokens)
    if not signature:
        return dedupe

    state = load_dedupe_state(state_path)
    suppressed, reason = check_and_record_signature(
        state,
        bucket=WORKFLOW_FAILURE_BUCKET,
        signature=signature,
        now_text=now_text or str(summary.get("started_at", "")),
        cooldown_minutes=max(1, int(cooldown_minutes or 60)),
        meta={
            "source": "task_executor_runner",
            "trigger_task": str(summary.get("trigger_task", "")).strip(),
            "run_id": str(summary.get("run_id", "")).strip(),
            "tokens": list(normalized_tokens),
        },
    )
    save_dedupe_state(state_path, state)
    dedupe["suppressed"] = suppressed
    dedupe["reason"] = reason
    dedupe["signature"] = signature
    dedupe["tokens"] = normalized_tokens
    return dedupe


def cli_flag_enabled(flag: str) -> bool:
    return str(flag or "").strip() in {str(part).strip() for part in sys.argv[1:]}


def cli_flag_value(flag: str, default: str = "") -> str:
    parts = sys.argv[1:]
    for idx, part in enumerate(parts):
        if part == flag and idx + 1 < len(parts):
            return str(parts[idx + 1]).strip()
        if part.startswith(flag + "="):
            return str(part.split("=", 1)[1]).strip()
    return default


def build_fatal_output(exc: Exception) -> str:
    task_name = cli_flag_value("--task", "cron:task-executor") or "cron:task-executor"
    issue, detail = humanize_executor_reason(str(exc), "failed")
    lines = [
        f"{format_beijing_time(now_iso())} 任务执行器：执行入口异常。",
        f"- 触发任务：{task_name}",
        f"- 异常类型：{exc.__class__.__name__}",
        f"- 详情：{issue}；{detail}",
    ]
    return "\n".join(lines)


def is_runtime_binding_task(task: dict[str, Any] | None) -> bool:
    if not isinstance(task, dict):
        return False
    if str(task.get("task_type", "")).strip().lower() == "ops_runtime_cron":
        return True
    return str(task.get("reason", "")).strip().startswith("[CRON_RUNTIME] bind ")


def select_tasks(enforcer: PolicyEnforcer, only_task_id: str, max_tasks: int) -> list[dict[str, Any]]:
    if str(only_task_id or "").strip():
        task = enforcer.db.get_task(str(only_task_id).strip())
        return [] if is_runtime_binding_task(task) else [task]
    rows = enforcer.db.conn.execute(
        """
        SELECT task_id FROM tasks
        WHERE status = 'pending'
        ORDER BY
          CASE pool WHEN 'jobs' THEN 0 ELSE 1 END ASC,
          CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC,
          created_at ASC
        LIMIT ?
        """,
        (max(1, int(max_tasks)) * 4,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        task = enforcer.db.get_task(str(row["task_id"]))
        if is_runtime_binding_task(task):
            continue
        out.append(task)
        if len(out) >= max_tasks:
            break
    return out


def local_context(repo_root: Path, task: dict[str, Any]) -> list[str]:
    query = str(task.get("reason", "")).strip() or str(task.get("requirement", "")).strip()
    if not query:
        return []
    token = split_list(re.sub(r"[^\w\u4e00-\u9fff]+", " ", query))
    if not token:
        return []
    key = token[0]
    try:
        proc = subprocess.run(
            ["rg", "-n", "--max-count", "8", key, "scripts", "docs", "agents", "openclaw"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()][:8]


def web_context(sources_file: Path, keyword: str, max_chars: int) -> list[dict[str, str]]:
    if not sources_file.exists() or not keyword:
        return []
    try:
        data = json.loads(sources_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    sources = data.get("sources", []) if isinstance(data, dict) else []
    if not isinstance(sources, list):
        return []
    out: list[dict[str, str]] = []
    for item in sources:
        if len(out) >= 2:
            break
        if not isinstance(item, dict) or not bool(item.get("enabled", True)):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "openclaw-task-executor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read(max(2048, int(max_chars))).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError):
            continue
        hit = body.lower().find(keyword.lower())
        if hit < 0:
            continue
        start = max(0, hit - 160)
        end = min(len(body), hit + 240)
        out.append({"id": str(item.get("id", "")).strip(), "url": url, "snippet": body[start:end].replace("\n", " ").strip()})
    return out


def prompt_for_task(task: dict[str, Any], local_hits: list[str], web_hits: list[dict[str, str]]) -> str:
    local_text = "\n".join(f"- {x}" for x in local_hits) or "- (none)"
    web_text = "\n".join(f"- [{x['id']}] {x['url']} | {x['snippet']}" for x in web_hits) or "- (none)"
    workflow_selection_inputs = task.get("selection_inputs", {})
    if not isinstance(workflow_selection_inputs, dict):
        workflow_selection_inputs = {}
    return f"""你是执行代理，请完成任务并只输出 JSON 对象，不要解释。

任务:
- task_id: {task.get('task_id')}
- reason: {task.get('reason')}
- requirement: {task.get('requirement')}
- result_output: {task.get('result_output')}
- acceptance: {task.get('acceptance')}
- observable_outputs: {task.get('observable_outputs')}
- acceptance_thresholds: {task.get('acceptance_thresholds')}
- stage_id: {task.get('stage_id', '')}
- stage_score_gate: {task.get('stage_score_gate', '')}
- stage_min_evidence_count: {task.get('stage_min_evidence_count', 0)}
- stage_output_contract: {json.dumps(task.get('stage_output_contract', {}), ensure_ascii=False, sort_keys=True)}
- stage_verification_contract: {json.dumps(task.get('stage_verification_contract', {}), ensure_ascii=False, sort_keys=True)}
- stage_context_gate: {json.dumps(workflow_selection_inputs.get('stage_context_gate', {}), ensure_ascii=False, sort_keys=True)}
- stage_parallel_execution: {json.dumps(workflow_selection_inputs.get('stage_parallel_execution', {}), ensure_ascii=False, sort_keys=True)}
- stage_simplification_hint: {json.dumps(workflow_selection_inputs.get('stage_simplification_hint', {}), ensure_ascii=False, sort_keys=True)}
- stage_execution_strategy: {json.dumps(workflow_selection_inputs.get('stage_execution_strategy', {}), ensure_ascii=False, sort_keys=True)}
- stage_optimization_hints: {json.dumps(workflow_selection_inputs.get('stage_optimization_hints', {}), ensure_ascii=False, sort_keys=True)}
- required_capabilities: {task.get('required_capabilities')}
- required_skills: {task.get('required_skills')}
- allowed_agents: {task.get('allowed_agents')}
- workflow_profile_id: {task.get('workflow_profile_id', '')}
- workflow_channel: {task.get('workflow_channel', '')}
- selection_reason: {task.get('selection_reason', '')}
- selection_inputs: {json.dumps(workflow_selection_inputs, ensure_ascii=False, sort_keys=True)}

本地检索:
{local_text}

网络检索:
{web_text}

输出模板:
{{"status":"passed|failed|partial|escalated","solved":true,"resolution_summary":"","resolution_steps":[],"resolved_issues":[],"failed_items":[],"failure_count":0,"quality_score":0,"quality_grade":"a|b|c|d","need_clarification":false,"clarification_reason":"","context_fields_missing":[],"cost_estimate":0}}"""


def call_agent(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    local_mode: bool,
    thinking: str = "",
) -> tuple[int, str, str]:
    openclaw_cmd = str(openclaw_bin or "openclaw").strip() or "openclaw"
    timeout_value = max(30, int(timeout_sec))
    cmd = [
        openclaw_cmd,
        "agent",
        "--agent",
        str(assignee or "").strip(),
        "--message",
        str(message or ""),
        "--session-id",
        str(session_id or "").strip(),
        "--json",
        "--timeout",
        str(timeout_value),
    ]
    normalized_thinking = normalize_thinking(thinking)
    if normalized_thinking:
        cmd.extend(["--thinking", normalized_thinking])
    if local_mode:
        cmd.append("--local")
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max(60, int(timeout_sec) + 30),
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def is_hermes_agent_bin(openclaw_bin: str) -> bool:
    name = Path(str(openclaw_bin or "")).name.lower()
    return name == "hermes" or name == "hermes.exe"


def call_hermes_agent(
    hermes_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    local_mode: bool,
) -> tuple[int, str, str]:
    hermes_cmd = str(hermes_bin or "hermes").strip() or "hermes"
    timeout_value = max(30, int(timeout_sec))
    session_key = build_gateway_agent_session_key(assignee, session_id)
    prompt = (
        f"你是 Task Center 指定 agent `{str(assignee or '').strip()}`。\n"
        "本次调用已经由上游人工选择 specified_agent 路线并分配给你，不是新的 Discord 入口消息；"
        "不要再次要求选择执行链路。请只根据下面任务执行，并按输出模板返回结构化 JSON。\n\n"
        f"{message}"
    )
    cmd = [
        hermes_cmd,
        "--pass-session-id",
        "chat",
        "-q",
        prompt,
        "-Q",
        "--max-turns",
        "3",
        "--source",
        f"task-executor:{str(assignee or '').strip() or 'agent'}",
        "--accept-hooks",
        "--checkpoints",
        "--ignore-rules",
    ]
    if local_mode:
        cmd.append("--yolo")
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max(60, int(timeout_value) + 30),
        check=False,
    )
    stdout = strip_ansi(proc.stdout or "")
    stderr = strip_ansi(proc.stderr or "")
    if int(proc.returncode or 0) != 0:
        return int(proc.returncode), stdout, stderr
    session_ref = extract_hermes_session_id(f"{stdout}\n{stderr}")
    reply_text = strip_hermes_session_lines(stdout) or stdout.strip()
    wrapped = {
        "payloads": [{"text": reply_text}],
        "meta": {
            "agentMeta": {
                "runId": session_ref or session_id,
                "waitStatus": "ok",
                "sessionKey": session_key,
                "sessionId": session_ref,
                "runtime": "hermes-chat",
            }
        },
    }
    return 0, json.dumps(wrapped, ensure_ascii=False), stderr


def call_gateway_method(
    openclaw_bin: str,
    method: str,
    params: dict[str, Any],
    timeout_ms: int,
) -> tuple[int, str, str]:
    openclaw_cmd = str(openclaw_bin or "openclaw").strip() or "openclaw"
    cmd = [
        openclaw_cmd,
        "gateway",
        "call",
        str(method or "").strip(),
        "--json",
        "--timeout",
        str(max(1, int(timeout_ms))),
        "--params",
        json.dumps(params, ensure_ascii=False),
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max(30, int(timeout_ms / 1000) + 30),
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def call_agent_via_gateway_step(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    thinking: str = "",
) -> tuple[int, str, str]:
    timeout_value = max(30, int(timeout_sec))
    normalized_thinking = normalize_thinking(thinking)
    session_key = build_gateway_agent_session_key(assignee, session_id)
    idempotency_key = (
        f"task-exec-{normalize_agent_session_token(session_id, fallback='task')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    agent_params: dict[str, Any] = {
        "message": str(message or ""),
        "agentId": str(assignee or "").strip(),
        "sessionKey": session_key,
        "idempotencyKey": idempotency_key,
        "timeout": timeout_value,
    }
    if normalized_thinking:
        agent_params["thinking"] = normalized_thinking

    rc, out, err = call_gateway_method(
        openclaw_bin,
        "agent",
        agent_params,
        GATEWAY_ACK_TIMEOUT_MS,
    )
    if rc != 0:
        return rc, out, err

    accepted = parse_json_output(out) or {}
    run_id = str(accepted.get("runId", "")).strip() or idempotency_key
    wait_timeout_ms = max(GATEWAY_ACK_TIMEOUT_MS, timeout_value * 1000)
    rc_wait, out_wait, err_wait = call_gateway_method(
        openclaw_bin,
        "agent.wait",
        {"runId": run_id, "timeoutMs": wait_timeout_ms},
        wait_timeout_ms + 2_000,
    )
    if rc_wait != 0:
        return rc_wait, out_wait, err_wait

    wait_payload = parse_json_output(out_wait) or {}
    wait_status = str(wait_payload.get("status", "")).strip().lower()
    if wait_status != "ok":
        wait_error = str(wait_payload.get("error", "")).strip()
        return 1, "", wait_error or f"agent.wait status={wait_status or 'unknown'}"

    rc_history, out_history, err_history = call_gateway_method(
        openclaw_bin,
        "chat.history",
        {"sessionKey": session_key, "limit": GATEWAY_HISTORY_LIMIT},
        GATEWAY_ACK_TIMEOUT_MS,
    )
    if rc_history != 0:
        return rc_history, out_history, err_history

    history_payload = parse_json_output(out_history) or {}
    reply_text = extract_latest_assistant_text(history_payload)
    if not reply_text:
        return 1, "", "chat.history returned no assistant text"

    wrapped = {
        "payloads": [{"text": reply_text}],
        "meta": {
            "agentMeta": {
                "runId": run_id,
                "waitStatus": wait_status,
                "sessionKey": session_key,
                "sessionId": str(history_payload.get("sessionId", "")).strip(),
            }
        },
    }
    return 0, json.dumps(wrapped, ensure_ascii=False), ""


def is_retryable_agent_failure(exit_code: int, out: str, err: str) -> bool:
    if int(exit_code or 0) == 0:
        return False
    combined = "\n".join([str(out or ""), str(err or "")]).lower()
    return any(pattern in combined for pattern in RETRYABLE_AGENT_ERROR_PATTERNS)


def call_agent_with_retries(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    local_mode: bool,
    thinking: str,
    *,
    max_retries: int,
    retry_delay_sec: int,
    prefer_gateway: bool = False,
) -> tuple[int, str, str, int, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    total_attempts = max(1, int(max_retries or 0) + 1)
    delay_base = max(1, int(retry_delay_sec or 1))
    for attempt_idx in range(total_attempts):
        if is_hermes_agent_bin(openclaw_bin):
            rc, out, err = call_hermes_agent(
                openclaw_bin,
                assignee,
                message,
                session_id,
                timeout_sec,
                local_mode,
            )
        elif prefer_gateway:
            rc, out, err = call_agent_via_gateway_step(
                openclaw_bin,
                assignee,
                message,
                session_id,
                timeout_sec,
                thinking,
            )
        else:
            rc, out, err = call_agent(
                openclaw_bin,
                assignee,
                message,
                session_id,
                timeout_sec,
                local_mode,
                thinking,
            )
        retryable = is_retryable_agent_failure(rc, out, err)
        attempts.append(
            {
                "attempt": attempt_idx + 1,
                "exit_code": int(rc or 0),
                "retryable": retryable,
                "stderr_excerpt": str(err or "")[:300],
            }
        )
        if rc == 0 or (not retryable) or attempt_idx >= total_attempts - 1:
            return rc, out, err, attempt_idx + 1, attempts
        time.sleep(delay_base * (attempt_idx + 1))
    return rc, out, err, total_attempts, attempts


def extract_usage(agent_json: dict[str, Any]) -> tuple[int, int, int]:
    meta = agent_json.get("meta", {})
    duration_ms = int(meta.get("durationMs", 0) or 0) if isinstance(meta, dict) else 0
    usage = ((meta.get("agentMeta", {}) if isinstance(meta, dict) else {}).get("usage", {}))
    if not isinstance(usage, dict):
        return 0, 0, max(0, duration_ms)
    return max(0, int(usage.get("input", 0) or 0)), max(0, int(usage.get("output", 0) or 0)), max(0, duration_ms)


def ns(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def main() -> int:
    defaults = runtime_defaults()
    repo_root = Path(__file__).resolve().parents[3]

    parser = argparse.ArgumentParser(
        description="Execute pending tasks by calling assigned agents",
        epilog=GOVERNANCE_BRIDGE_EPILOG,
    )
    parser.add_argument("--db", default=defaults["db"])
    parser.add_argument("--policy-file", default=defaults["policy_file"])
    parser.add_argument("--routing-file", default=defaults["routing_file"])
    parser.add_argument("--pricing-file", default=defaults["pricing_file"])
    parser.add_argument("--task", default="")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--planner-id", default="coordinator")
    parser.add_argument("--max-tasks", type=int, default=3)
    parser.add_argument("--only-task-id", default="")
    parser.add_argument("--timeout-sec", type=int, default=1200)
    parser.add_argument("--local-agent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--web-sources-file", default=str(repo_root / "scripts/openclaw-ops/web/project_docs_sources.json"))
    parser.add_argument("--agent-capability-manifest", default=str(repo_root / "agents/agent_capability_manifest.json"))
    parser.add_argument("--web-max-chars", type=int, default=12000)
    parser.add_argument("--report-dir", default=str(repo_root / ".workflow/executor-runs"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notify-on", default="error", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--shared-alert-state-file", default=str(resolve_shared_alert_state_path()))
    parser.add_argument("--shared-alert-cooldown-minutes", type=int, default=60)
    parser.add_argument("--agent-max-retries", type=int, default=2)
    parser.add_argument("--agent-retry-delay-sec", type=int, default=20)
    parser.add_argument(
        "--strict-preflight-task-types",
        default=",".join(DEFAULT_STRICT_PREFLIGHT_TASK_TYPES),
        help="Comma-separated task types that should be blocked when preflight warnings exist.",
    )
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    paths = RuntimePaths(
        db=Path(args.db).expanduser(),
        policy_file=Path(args.policy_file).expanduser(),
        routing_file=Path(args.routing_file).expanduser(),
        pricing_file=Path(args.pricing_file).expanduser(),
    )
    requested_model = str(args.model or "").strip()
    has_fixed_model = bool(requested_model and requested_model.lower() not in AUTO_MODEL_SENTINELS)
    cmd_init(paths, force=False)
    enforcer = PolicyEnforcer(paths)

    run_id = f"exec-{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:8]}"
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "started_at": now_iso(),
        "tasks_selected": 0,
        "tasks_executed": 0,
        "tasks_skipped": 0,
        "tasks_failed": 0,
        "bridge": {
            "trigger_surfaces": ["cron", "hooks", "webhook"],
            "machine_output": "json",
            "vendor_state_policy": "no-direct-vendor-private-state-writes",
        },
        "trigger_task": str(args.task).strip(),
        "executor_model": (requested_model if has_fixed_model else "auto(per-assignee)"),
        "executor_model_source": ("cli" if has_fixed_model else "policy-agent-overrides"),
        "executor_thinking": "auto(by-model)",
        "preflight_manifest": str(Path(args.agent_capability_manifest).expanduser()),
        "preflight_warning_tasks": 0,
        "preflight_warning_by_task_type": {},
        "preflight_warning_by_assignee": {},
        "preflight_warning_codes": {},
        "preflight_blocked_tasks": 0,
        "preflight_blocked_by_task_type": {},
        "preflight_blocked_by_assignee": {},
        "preflight_strict_task_types": sorted(parse_strict_preflight_task_types(args.strict_preflight_task_types)),
        "results": [],
    }

    try:
        capability_index = load_agent_capability_index(Path(args.agent_capability_manifest).expanduser())
        strict_task_types = parse_strict_preflight_task_types(args.strict_preflight_task_types)
        tasks = select_tasks(enforcer, str(args.only_task_id), max(1, int(args.max_tasks)))
        summary["tasks_selected"] = len(tasks)

        for task in tasks:
            task_id = str(task.get("task_id", "")).strip()
            assignee = str(task.get("assignee", "")).strip() or "backend-dev"
            preflight = build_task_preflight(task, capability_index, planner_id=str(args.planner_id))
            stage = default_stage(assignee)
            task_type = str(task.get("task_type", "")).strip()
            workflow_alert_tokens = extract_workflow_failure_tokens_from_task(
                task_id,
                task_type=task_type,
                requirement=task.get("requirement", ""),
                context_payload=task.get("context_payload"),
            )
            task_model_name, task_model_source, task_thinking = resolve_executor_selection(
                requested_model,
                assignee,
                paths.policy_file,
            )
            task_cli_thinking = task_thinking if is_codex_model(task_model_name) else ""
            result: dict[str, Any] = {
                "task_id": task_id,
                "assignee": assignee,
                "stage": stage,
                "status": "skipped",
                "reason": "",
                "model": task_model_name,
                "model_source": task_model_source,
                "thinking": task_thinking,
                "task_type": task_type,
                "task_reason": compact_text(task.get("reason", ""), 96),
                "task_requirement": compact_text(task.get("requirement", ""), 120),
                "task_acceptance": compact_text(task.get("acceptance", ""), 120),
                "task_result_output": compact_text(task.get("result_output", ""), 120),
                "workflow_alert_tokens": workflow_alert_tokens,
                "preflight": preflight,
            }

            preflight_observation = record_preflight_observation(
                summary,
                task_type=task_type,
                assignee=assignee,
                preflight=preflight,
                strict_task_types=strict_task_types,
            )
            if preflight_observation["has_warnings"]:
                try:
                    enforcer.db.add_event(
                        task_id=task_id,
                        actor=str(args.actor),
                        event_type="task_preflight_warning",
                        stage="dispatch",
                        details=preflight,
                    )
                except Exception:
                    pass
            if preflight_observation["strict_blocked"]:
                preflight_reassign = build_preflight_reassign_payload(task, preflight)
                result.update(
                    {
                        "status": "failed",
                        "reason": "preflight_strict_blocked",
                        "preflight_enforced": True,
                        "need_reassign": True,
                        "preflight_reassign": preflight_reassign,
                    }
                )
                summary["tasks_skipped"] += 1
                summary["results"].append(result)
                try:
                    enforcer.db.add_event(
                        task_id=task_id,
                        actor=str(args.actor),
                        event_type="task_preflight_blocked",
                        stage="dispatch",
                        details={"preflight": preflight, "reassign": preflight_reassign},
                    )
                except Exception:
                    pass
                continue

            if bool(task.get("needs_clarification")):
                result["reason"] = "needs_clarification"
                summary["tasks_skipped"] += 1
                summary["results"].append(result)
                continue
            if bool(task.get("need_human_confirm")) and (not bool(task.get("human_confirmed"))):
                result["reason"] = "waiting_human_confirm"
                summary["tasks_skipped"] += 1
                summary["results"].append(result)
                continue

            local_hits = local_context(repo_root, task)
            keyword = split_list(str(task.get("reason", "")))
            web_hits = web_context(Path(args.web_sources_file).expanduser(), keyword[0] if keyword else "", int(args.web_max_chars))
            prompt = prompt_for_task(task, local_hits, web_hits)
            session_id = build_task_session_id(task_id)

            try:
                enforcer.db.add_event(task_id=task_id, actor=str(args.actor), event_type="task_decomposed", stage="dispatch", details={"steps": [
                    {"id": "s1", "owner": "project-agent", "title": "澄清范围"},
                    {"id": "s2", "owner": assignee, "title": "实现改动"},
                    {"id": "s3", "owner": "tester", "title": "执行验证"},
                    {"id": "s4", "owner": "doc-writer", "title": "输出验收文档"},
                ]})
            except Exception:
                pass

            try:
                enforcer.pre_stage(
                    ns(
                        task_id=task_id,
                        stage=stage,
                        agent_id=assignee,
                        model=task_model_name,
                        input_ref=str(report_dir),
                        actor=str(args.actor),
                    )
                )
            except Exception as exc:
                result["status"] = "failed"
                result["reason"] = f"pre_stage_failed:{exc}"
                summary["tasks_failed"] += 1
                summary["results"].append(result)
                continue

            if args.dry_run:
                result["status"] = "dry_run"
                result["reason"] = "execution_skipped"
                summary["tasks_executed"] += 1
                summary["results"].append(result)
                continue

            started = datetime.now(tz=UTC)
            try:
                rc, out, err, agent_attempts, agent_attempt_details = call_agent_with_retries(
                    str(args.openclaw_bin),
                    assignee,
                    prompt,
                    session_id,
                    int(args.timeout_sec),
                    bool(args.local_agent),
                    task_cli_thinking,
                    max_retries=int(args.agent_max_retries),
                    retry_delay_sec=int(args.agent_retry_delay_sec),
                    prefer_gateway=bool(args.local_agent),
                )
            except Exception as exc:
                rc, out, err, agent_attempts, agent_attempt_details = 1, "", f"call_agent_exception:{exc}", 1, []
            agent_log_path = report_dir / f"{run_id}-{task_id}.agent.log"
            try:
                agent_log_path.write_text(
                    "\n".join(
                        [
                            f"task_id={task_id}",
                            f"assignee={assignee}",
                            f"model={task_model_name}",
                            f"model_source={task_model_source}",
                            f"thinking={task_thinking}",
                            f"session_id={session_id}",
                            f"exit_code={rc}",
                            f"attempts={agent_attempts}",
                            "=== STDOUT ===",
                            str(out or ""),
                            "=== STDERR ===",
                            str(err or ""),
                            "=== ATTEMPTS ===",
                            json.dumps(agent_attempt_details, ensure_ascii=False),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            contract, agent_json, reply_text, sanitized_stderr = contract_from_agent_result(rc, out, err)
            meta = agent_json.get("meta", {}) if isinstance(agent_json, dict) else {}
            agent_meta = meta.get("agentMeta", {}) if isinstance(meta, dict) else {}
            agent_runtime_run_id = str(agent_meta.get("runId", "")).strip() if isinstance(agent_meta, dict) else ""
            agent_session_key = str(agent_meta.get("sessionKey", "")).strip() if isinstance(agent_meta, dict) else ""
            agent_runtime_session_id = str(agent_meta.get("sessionId", "")).strip() if isinstance(agent_meta, dict) else ""
            in_tokens, out_tokens, duration_ms = extract_usage(agent_json)
            if duration_ms <= 0:
                duration_ms = max(0, int((datetime.now(tz=UTC) - started).total_seconds() * 1000))

            if bool(contract.get("need_clarification")):
                try:
                    enforcer.db.update_clarification(
                        task_id=task_id,
                        actor=assignee,
                        needs_clarification=True,
                        clarification_reason=str(contract.get("clarification_reason", "")).strip() or "agent_need_clarification",
                        context_payload=task.get("context_payload", {}),
                        context_completeness=float(task.get("context_completeness", 0.0) or 0.0),
                        context_fields_missing=list(contract.get("context_fields_missing", [])),
                        context_fields_recommended_missing=list(task.get("context_fields_recommended_missing", [])),
                    )
                except Exception:
                    pass

            try:
                if (in_tokens + out_tokens) > 0:
                    enforcer.record_token(
                        ns(
                            task_id=task_id,
                            agent_id=assignee,
                            model=task_model_name,
                            input_tokens=str(in_tokens),
                            output_tokens=str(out_tokens),
                        )
                    )
            except Exception:
                pass

            details = {
                "run_id": run_id,
                "session_id": session_id,
                "agent_run_id": agent_runtime_run_id,
                "agent_session_key": agent_session_key,
                "agent_runtime_session_id": agent_runtime_session_id,
                "model": task_model_name,
                "model_source": task_model_source,
                "thinking": task_thinking,
                "command_exit_code": rc,
                "agent_attempts": agent_attempts,
                "agent_attempt_details": agent_attempt_details,
                "stderr_excerpt": str(err or "")[:1200],
                "stderr_sanitized_excerpt": str(sanitized_stderr or "")[:1200],
                "local_context_hits": len(local_hits),
                "web_context_hits": len(web_hits),
                "raw_reply_excerpt": str(contract.get("raw_text", ""))[:1200],
            }
            stage_contract = evaluate_stage_contract(task, contract)
            details["stage_contract"] = stage_contract
            post_reason = "ok" if rc == 0 else f"agent_exit_{rc}"
            try:
                enforcer.post_stage(
                    ns(
                        task_id=task_id,
                        stage=stage,
                        exit_code=str(rc),
                        reason=post_reason,
                        output_ref=str(agent_log_path),
                        details_json=json.dumps({"stage_contract": stage_contract}, ensure_ascii=False),
                        actor=str(args.actor),
                    )
                )
            except Exception:
                pass
            try:
                report = enforcer.report_agent_result(
                    ns(
                        task_id=task_id,
                        agent_id=assignee,
                        planner_id=str(args.planner_id),
                        status=str(contract.get("status", "partial")),
                        solved="true" if bool(contract.get("solved", False)) else "false",
                        resolved_issues=",".join(contract.get("resolved_issues", [])),
                        resolution_summary=str(contract.get("resolution_summary", "")),
                        resolution_steps=",".join(contract.get("resolution_steps", [])),
                        failed_items=",".join(contract.get("failed_items", [])),
                        failure_count=str(max(0, int(contract.get("failure_count", 0) or 0))),
                        duration_ms=str(max(0, int(duration_ms))),
                        model=task_model_name,
                        input_tokens=str(max(0, int(in_tokens))),
                        output_tokens=str(max(0, int(out_tokens))),
                        cost_estimate=str(max(0.0, float(contract.get("cost_estimate", 0.0) or 0.0))),
                        quality_score=str(max(0.0, min(float(contract.get("quality_score", 0.0) or 0.0), 100.0))),
                        quality_grade=str(contract.get("quality_grade", "c")),
                        notify_chat="false",
                        details_json=json.dumps(details, ensure_ascii=False),
                        actor=assignee,
                    )
                )
            except Exception as exc:
                result["status"] = "failed"
                result["reason"] = f"report_failed:{exc}"
                summary["tasks_failed"] += 1
                summary["results"].append(result)
                continue

            end_status = str(report.get("task_status_sync", {}).get("task_status_after", "")).strip() or str(contract.get("status", "partial"))
            result.update(
                {
                    "status": "executed",
                    "reason": ("stage_contract_failed" if not bool(stage_contract.get("contract_passed", True)) else ""),
                    "task_status_after": end_status,
                    "executor_run_id": run_id,
                    "session_id": session_id,
                    "agent_run_id": agent_runtime_run_id,
                    "agent_session_key": agent_session_key,
                    "agent_runtime_session_id": agent_runtime_session_id,
                    "report_status": str(contract.get("status", "partial")),
                    "solved": bool(contract.get("solved", False)),
                    "quality_score": float(contract.get("quality_score", 0.0) or 0.0),
                    "resolution_summary": str(contract.get("resolution_summary", "")),
                    "failed_items": list(contract.get("failed_items", [])),
                    "stage_contract": stage_contract,
                    "failure_count": max(0, int(contract.get("failure_count", 0) or 0)),
                    "duration_ms": duration_ms,
                    "model": task_model_name,
                    "stage_contract": stage_contract,
                    "standard_output": dict(report.get("standard_output", {})) if isinstance(report.get("standard_output", {}), dict) else {},
                    "human_gate": dict(report.get("planner_payload", {}).get("human_gate", {}))
                    if isinstance(report.get("planner_payload", {}), dict)
                    and isinstance(report.get("planner_payload", {}).get("human_gate", {}), dict)
                    else {},
                    "incident": dict(report.get("incident", {})) if isinstance(report.get("incident", {}), dict) else {},
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "total_tokens": max(0, int(in_tokens)) + max(0, int(out_tokens)),
                    "cost_estimate": max(0.0, float(contract.get("cost_estimate", 0.0) or 0.0)),
                }
            )
            summary["tasks_executed"] += 1
            summary["results"].append(result)
    finally:
        enforcer.close()

    summary["finished_at"] = now_iso()
    summary["alert_dedupe"] = apply_shared_alert_dedupe(
        summary,
        Path(args.shared_alert_state_file).expanduser(),
        cooldown_minutes=max(1, int(args.shared_alert_cooldown_minutes)),
        now_text=str(summary.get("started_at", "")),
    )
    summary["task_change_notify"] = apply_task_executor_incremental_notify(
        summary,
        Path(args.shared_alert_state_file).expanduser(),
        now_text=str(summary.get("started_at", "")),
    )
    report_path = report_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["report_file"] = str(report_path)

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(build_chat_output(summary, report_path, str(args.notify_on)))
    return 0


def run_cli() -> int:
    try:
        return main()
    except Exception as exc:
        output = build_fatal_output(exc)
        payload = {
            "ok": False,
            "notify": True,
            "output": output,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if cli_flag_enabled("--emit-json"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(output)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

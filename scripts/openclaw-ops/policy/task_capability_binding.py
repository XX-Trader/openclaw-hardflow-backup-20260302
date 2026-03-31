#!/usr/bin/env python3
"""Capability registry helpers for task constraints."""

from __future__ import annotations

from typing import Any


DEFAULT_CAPABILITY_REGISTRY: dict[str, Any] = {
    "schema_version": "2026-03-22",
    "capabilities": [
        {
            "capability_id": "role_only",
            "display_name": "Role Only",
            "owner_domain": "policy",
            "default_agent": "project-agent",
            "allowed_agents": [
                "agent-factory",
                "ops-agent",
                "optimization-agent",
                "project-agent",
                "self-evolution-agent",
                "web-agent",
            ],
            "required_skills": [],
            "required_runtime": ["task-center"],
            "tool_requirements": [],
            "input_contract": "任务必须指定 assignee，并且 assignee 必须属于 allowed_agents。",
            "output_contract": "任务约束保持为单角色、单 agent 执行。",
            "verification_contract": "校验 assignee 是否在 allowed_agents 内。",
            "failure_modes": ["assignee_not_allowed"],
        },
        {
            "capability_id": "skill_backed",
            "display_name": "Skill Backed",
            "owner_domain": "workflow",
            "default_agent": "coordinator",
            "allowed_agents": [
                "main",
                "coordinator",
                "backend-dev",
                "frontend-dev",
                "reviewer",
                "tester",
                "deployer",
                "doc-writer",
            ],
            "required_skills": [],
            "required_runtime": ["task-center", "skills"],
            "tool_requirements": [],
            "input_contract": "任务必须声明 skill，或由 agent 默认技能补齐。",
            "output_contract": "执行前需要完成 skill 和 assignee 约束检查。",
            "verification_contract": "校验 required_skills 是否被 agent manifest 满足。",
            "failure_modes": ["required_skills_unmet", "required_capabilities_unmet"],
        },
        {
            "capability_id": "project_context",
            "display_name": "Project Context",
            "owner_domain": "project",
            "default_agent": "project-agent",
            "allowed_agents": ["project-agent", "coordinator"],
            "required_skills": [],
            "required_runtime": ["task-center"],
            "tool_requirements": ["filesystem"],
            "input_contract": "输入必须包含项目上下文、范围与位置。",
            "output_contract": "输出补全项目背景、结构与范围判断。",
            "verification_contract": "校验 context gate 所需字段是否齐全。",
            "failure_modes": ["context_fields_missing"],
        },
        {
            "capability_id": "routing",
            "display_name": "Routing",
            "owner_domain": "workflow",
            "default_agent": "coordinator",
            "allowed_agents": ["coordinator", "main"],
            "required_skills": [],
            "required_runtime": ["task-center"],
            "tool_requirements": [],
            "input_contract": "输入必须包含任务类别、优先级与来源。",
            "output_contract": "输出 assignee、pool、priority 等路由结果。",
            "verification_contract": "校验 assignee 与 allowed_agents 是否一致。",
            "failure_modes": ["assignee_not_allowed"],
        },
        {
            "capability_id": "task_execution",
            "display_name": "Task Execution",
            "owner_domain": "execution",
            "default_agent": "backend-dev",
            "allowed_agents": [
                "backend-dev",
                "frontend-dev",
                "reviewer",
                "tester",
                "deployer",
                "ops-agent",
                "optimization-agent",
            ],
            "required_skills": [],
            "required_runtime": ["task-center"],
            "tool_requirements": ["filesystem", "shell"],
            "input_contract": "输入必须包含 requirement、acceptance 与 observable outputs。",
            "output_contract": "输出结构化执行结果、质量分与验证信息。",
            "verification_contract": "校验执行结果满足 acceptance thresholds。",
            "failure_modes": ["required_capabilities_unmet", "quality_score_low"],
        },
    ],
    "agent_defaults": [
        {
            "agent_id": "agent-factory",
            "required_capabilities": ["role_only"],
            "required_skills": [],
            "allowed_agents": ["agent-factory"],
        },
        {
            "agent_id": "ops-agent",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": [],
            "allowed_agents": ["ops-agent"],
        },
        {
            "agent_id": "optimization-agent",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": [],
            "allowed_agents": ["optimization-agent"],
        },
        {
            "agent_id": "project-agent",
            "required_capabilities": ["role_only"],
            "required_skills": [],
            "allowed_agents": ["project-agent"],
        },
        {
            "agent_id": "self-evolution-agent",
            "required_capabilities": ["role_only"],
            "required_skills": [],
            "allowed_agents": ["self-evolution-agent"],
        },
        {
            "agent_id": "web-agent",
            "required_capabilities": ["role_only"],
            "required_skills": [],
            "allowed_agents": ["web-agent"],
        },
        {
            "agent_id": "main",
            "required_capabilities": ["skill_backed"],
            "required_skills": ["requirements-clarity", "task-decomposer"],
            "allowed_agents": ["main"],
        },
        {
            "agent_id": "coordinator",
            "required_capabilities": ["skill_backed"],
            "required_skills": ["requirements-clarity", "task-decomposer"],
            "allowed_agents": ["coordinator"],
        },
        {
            "agent_id": "backend-dev",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": ["feature-development"],
            "allowed_agents": ["backend-dev"],
        },
        {
            "agent_id": "frontend-dev",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": ["frontend-design", "feature-development"],
            "allowed_agents": ["frontend-dev"],
        },
        {
            "agent_id": "reviewer",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": ["requesting-code-review"],
            "allowed_agents": ["reviewer"],
        },
        {
            "agent_id": "tester",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": ["webapp-testing"],
            "allowed_agents": ["tester"],
        },
        {
            "agent_id": "deployer",
            "required_capabilities": ["skill_backed", "task_execution"],
            "required_skills": ["deployment-test"],
            "allowed_agents": ["deployer"],
        },
        {
            "agent_id": "doc-writer",
            "required_capabilities": ["skill_backed"],
            "required_skills": ["writing-plans"],
            "allowed_agents": ["doc-writer"],
        },
    ],
}


def _normalize_text_list(raw: Any) -> list[str]:
    """Normalize string or list inputs into deduplicated string lists."""

    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = str(raw).split(",")
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(text)
    return output


def capability_ids_from_registry(registry: dict[str, Any]) -> set[str]:
    """Return known capability ids from a normalized registry."""

    return {
        str(item.get("capability_id", "")).strip().lower()
        for item in registry.get("capabilities", [])
        if str(item.get("capability_id", "")).strip()
    }


def agent_defaults_index_from_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build an index of agent default constraints from a normalized registry."""

    return {
        str(item.get("agent_id", "")).strip().lower(): item
        for item in registry.get("agent_defaults", [])
        if str(item.get("agent_id", "")).strip()
    }


def capability_index_from_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build an index of capability entries from a normalized registry."""

    return {
        str(item.get("capability_id", "")).strip().lower(): item
        for item in registry.get("capabilities", [])
        if str(item.get("capability_id", "")).strip()
    }


def _merge_capability_requirements(
    capability_ids: list[str],
    capability_index: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Collect merged runtime and tool requirements from capability ids."""

    required_runtime: list[str] = []
    tool_requirements: list[str] = []
    for capability_id in capability_ids:
        entry = capability_index.get(str(capability_id or "").strip().lower())
        if not entry:
            continue
        required_runtime = _normalize_text_list(required_runtime + list(entry.get("required_runtime", [])))
        tool_requirements = _normalize_text_list(tool_requirements + list(entry.get("tool_requirements", [])))
    return {
        "required_runtime": required_runtime,
        "tool_requirements": tool_requirements,
    }


def _build_capability_declarations(
    capability_ids: list[str],
    capability_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return normalized per-capability declarations for declarative assembly."""

    declarations: list[dict[str, Any]] = []
    for capability_id in capability_ids:
        entry = capability_index.get(str(capability_id or "").strip().lower())
        if not entry:
            continue
        declarations.append(
            {
                "capability_id": str(entry.get("capability_id", "")).strip(),
                "display_name": str(entry.get("display_name", "")).strip(),
                "owner_domain": str(entry.get("owner_domain", "")).strip(),
                "default_agent": str(entry.get("default_agent", "")).strip(),
                "allowed_agents": _normalize_text_list(entry.get("allowed_agents", [])),
                "required_skills": _normalize_text_list(entry.get("required_skills", [])),
                "required_runtime": _normalize_text_list(entry.get("required_runtime", [])),
                "tool_requirements": _normalize_text_list(entry.get("tool_requirements", [])),
                "input_contract": str(entry.get("input_contract", "")).strip(),
                "output_contract": str(entry.get("output_contract", "")).strip(),
                "verification_contract": str(entry.get("verification_contract", "")).strip(),
                "failure_modes": _normalize_text_list(entry.get("failure_modes", [])),
            }
        )
    return declarations


def _build_capability_contracts(declarations: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Aggregate contracts and failure modes across capability declarations."""

    input_contracts: list[str] = []
    output_contracts: list[str] = []
    verification_contracts: list[str] = []
    failure_modes: list[str] = []
    owner_domains: list[str] = []
    for item in declarations:
        if not isinstance(item, dict):
            continue
        input_contracts = _normalize_text_list(input_contracts + [item.get("input_contract", "")])
        output_contracts = _normalize_text_list(output_contracts + [item.get("output_contract", "")])
        verification_contracts = _normalize_text_list(
            verification_contracts + [item.get("verification_contract", "")]
        )
        failure_modes = _normalize_text_list(failure_modes + list(item.get("failure_modes", [])))
        owner_domains = _normalize_text_list(owner_domains + [item.get("owner_domain", "")])
    return {
        "input_contracts": input_contracts,
        "output_contracts": output_contracts,
        "verification_contracts": verification_contracts,
        "failure_modes": failure_modes,
        "owner_domains": owner_domains,
    }


def _build_agent_profile_snapshot(
    agent_id: str,
    agent_defaults_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return the normalized agent-default snapshot used by declarative assembly."""

    normalized_agent_id = str(agent_id or "").strip().lower()
    if not normalized_agent_id:
        return {}
    matched = agent_defaults_index.get(normalized_agent_id)
    if not isinstance(matched, dict):
        return {}
    return {
        "agent_id": str(matched.get("agent_id", "")).strip(),
        "required_capabilities": _normalize_text_list(matched.get("required_capabilities", [])),
        "required_skills": _normalize_text_list(matched.get("required_skills", [])),
        "allowed_agents": _normalize_text_list(matched.get("allowed_agents", [])),
    }


def normalize_capability_registry(registry_raw: Any) -> dict[str, Any]:
    """Validate and normalize a capability registry payload.

    Args:
        registry_raw: Raw registry payload loaded from JSON.

    Returns:
        dict[str, Any]: Normalized capability registry with validated capabilities and agent defaults.

    Raises:
        ValueError: Raised when the registry shape is invalid or references unknown capabilities.
    """

    if not isinstance(registry_raw, dict):
        raise ValueError("capability registry must be a JSON object")

    schema_version = str(
        registry_raw.get("schema_version", DEFAULT_CAPABILITY_REGISTRY["schema_version"]) or ""
    ).strip() or DEFAULT_CAPABILITY_REGISTRY["schema_version"]

    capabilities_raw = registry_raw.get("capabilities", DEFAULT_CAPABILITY_REGISTRY["capabilities"])
    if not isinstance(capabilities_raw, list) or not capabilities_raw:
        raise ValueError("capability registry capabilities must be a non-empty list")

    capabilities: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    for index, item in enumerate(capabilities_raw):
        if not isinstance(item, dict):
            raise ValueError(f"capability registry entry #{index} must be a JSON object")
        capability_id = str(item.get("capability_id", "") or "").strip()
        if not capability_id:
            raise ValueError(f"capability registry entry #{index} missing capability_id")
        lowered_capability_id = capability_id.lower()
        if lowered_capability_id in seen_capabilities:
            raise ValueError(f"duplicate capability registry entry: {capability_id}")
        seen_capabilities.add(lowered_capability_id)
        capabilities.append(
            {
                "capability_id": capability_id,
                "display_name": str(item.get("display_name", capability_id) or capability_id).strip()
                or capability_id,
                "owner_domain": str(item.get("owner_domain", "") or "").strip() or "workflow",
                "default_agent": str(item.get("default_agent", "") or "").strip(),
                "allowed_agents": _normalize_text_list(item.get("allowed_agents", [])),
                "required_skills": _normalize_text_list(item.get("required_skills", [])),
                "required_runtime": _normalize_text_list(item.get("required_runtime", [])),
                "tool_requirements": _normalize_text_list(item.get("tool_requirements", [])),
                "input_contract": str(item.get("input_contract", "") or "").strip(),
                "output_contract": str(item.get("output_contract", "") or "").strip(),
                "verification_contract": str(item.get("verification_contract", "") or "").strip(),
                "failure_modes": _normalize_text_list(item.get("failure_modes", [])),
            }
        )

    agent_defaults_raw = registry_raw.get("agent_defaults", DEFAULT_CAPABILITY_REGISTRY["agent_defaults"])
    if not isinstance(agent_defaults_raw, list):
        raise ValueError("capability registry agent_defaults must be a list")

    agent_defaults: list[dict[str, Any]] = []
    seen_agents: set[str] = set()
    known_capability_ids = capability_ids_from_registry({"capabilities": capabilities})
    for index, item in enumerate(agent_defaults_raw):
        if not isinstance(item, dict):
            raise ValueError(f"capability agent default #{index} must be a JSON object")
        agent_id = str(item.get("agent_id", "") or "").strip()
        if not agent_id:
            raise ValueError(f"capability agent default #{index} missing agent_id")
        lowered_agent_id = agent_id.lower()
        if lowered_agent_id in seen_agents:
            raise ValueError(f"duplicate capability agent default: {agent_id}")
        seen_agents.add(lowered_agent_id)
        required_capabilities = _normalize_text_list(item.get("required_capabilities", []))
        unknown_capabilities = [
            capability_id
            for capability_id in required_capabilities
            if capability_id.lower() not in known_capability_ids
        ]
        if unknown_capabilities:
            raise ValueError(
                f"capability agent default '{agent_id}' references unknown capabilities: "
                + ", ".join(unknown_capabilities)
            )
        agent_defaults.append(
            {
                "agent_id": agent_id,
                "required_capabilities": required_capabilities,
                "required_skills": _normalize_text_list(item.get("required_skills", [])),
                "allowed_agents": _normalize_text_list(item.get("allowed_agents", [agent_id])),
            }
        )

    return {
        "schema_version": schema_version,
        "capabilities": capabilities,
        "agent_defaults": agent_defaults,
    }


def validate_task_capability_constraints(
    required_capabilities: Any,
    required_skills: Any,
    allowed_agents: Any,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Normalize and validate task constraint fields against a capability registry."""

    normalized_registry = normalize_capability_registry(registry or DEFAULT_CAPABILITY_REGISTRY)
    normalized_constraints = {
        "required_capabilities": _normalize_text_list(required_capabilities),
        "required_skills": _normalize_text_list(required_skills),
        "allowed_agents": _normalize_text_list(allowed_agents),
    }
    known_capabilities = capability_ids_from_registry(normalized_registry)
    unknown_capabilities = [
        capability_id
        for capability_id in normalized_constraints["required_capabilities"]
        if capability_id.lower() not in known_capabilities
    ]
    if unknown_capabilities:
        raise ValueError("unknown required capabilities: " + ", ".join(unknown_capabilities))
    return normalized_constraints


def infer_task_capability_constraints(
    assignee: str,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Infer default task constraints for an assignee from the capability registry."""

    normalized_assignee = str(assignee or "").strip()
    if not normalized_assignee:
        return {
            "required_capabilities": [],
            "required_skills": [],
            "allowed_agents": [],
            "required_runtime": [],
            "tool_requirements": [],
        }

    normalized_registry = normalize_capability_registry(registry or DEFAULT_CAPABILITY_REGISTRY)
    default_index = agent_defaults_index_from_registry(normalized_registry)
    matched = default_index.get(normalized_assignee.lower())
    if not matched:
        return {
            "required_capabilities": [],
            "required_skills": [],
            "allowed_agents": [],
            "required_runtime": [],
            "tool_requirements": [],
        }

    capability_index = capability_index_from_registry(normalized_registry)
    requirement_bundle = _merge_capability_requirements(
        list(matched.get("required_capabilities", [])),
        capability_index,
    )
    return {
        "required_capabilities": list(matched.get("required_capabilities", [])),
        "required_skills": list(matched.get("required_skills", [])),
        "allowed_agents": list(matched.get("allowed_agents", [])),
        "required_runtime": requirement_bundle["required_runtime"],
        "tool_requirements": requirement_bundle["tool_requirements"],
    }


def resolve_task_capability_binding(
    assignee: str,
    *,
    required_capabilities: Any,
    required_skills: Any,
    allowed_agents: Any,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one assignee and merged task constraints from capability declarations."""

    normalized_registry = normalize_capability_registry(registry or DEFAULT_CAPABILITY_REGISTRY)
    capability_index = capability_index_from_registry(normalized_registry)
    agent_defaults_index = agent_defaults_index_from_registry(normalized_registry)
    normalized_required_capabilities = _normalize_text_list(required_capabilities)
    normalized_required_skills = _normalize_text_list(required_skills)
    explicit_allowed_agents = _normalize_text_list(allowed_agents)

    capability_allowed_agents: list[str] = []
    capability_default_agents: list[str] = []
    for capability_id in normalized_required_capabilities:
        entry = capability_index.get(capability_id.lower())
        if not entry:
            continue
        capability_allowed_agents = _normalize_text_list(
            capability_allowed_agents + list(entry.get("allowed_agents", []))
        )
        default_agent = str(entry.get("default_agent", "") or "").strip()
        if default_agent:
            capability_default_agents = _normalize_text_list(capability_default_agents + [default_agent])

    allowed_filter = explicit_allowed_agents or capability_allowed_agents
    allowed_filter_set = {item.lower() for item in allowed_filter}
    skill_matched_agents: list[str] = []
    if normalized_required_skills:
        required_skill_set = {item.lower() for item in normalized_required_skills}
        for item in normalized_registry.get("agent_defaults", []):
            agent_id = str(item.get("agent_id", "") or "").strip()
            if not agent_id:
                continue
            agent_skill_set = {
                str(skill or "").strip().lower()
                for skill in item.get("required_skills", [])
                if str(skill or "").strip()
            }
            if not required_skill_set.issubset(agent_skill_set):
                continue
            if allowed_filter_set and agent_id.lower() not in allowed_filter_set:
                continue
            skill_matched_agents = _normalize_text_list(skill_matched_agents + [agent_id])

    resolved_assignee = str(assignee or "").strip()
    resolution_reason = "explicit_assignee" if resolved_assignee else ""
    if not resolved_assignee and skill_matched_agents:
        resolved_assignee = skill_matched_agents[0]
        resolution_reason = "required_skills_binding"
    if not resolved_assignee:
        filtered_default_agents = [
            agent_id
            for agent_id in capability_default_agents
            if not allowed_filter_set or agent_id.lower() in allowed_filter_set
        ]
        if filtered_default_agents:
            resolved_assignee = filtered_default_agents[0]
            resolution_reason = "capability_default_agent"
    if not resolved_assignee and explicit_allowed_agents:
        resolved_assignee = explicit_allowed_agents[0]
        resolution_reason = "explicit_allowed_agents_fallback"
    if not resolved_assignee and capability_allowed_agents:
        resolved_assignee = capability_allowed_agents[0]
        resolution_reason = "capability_allowed_agents_fallback"

    inferred_constraints = infer_task_capability_constraints(
        resolved_assignee,
        registry=normalized_registry,
    )
    derived_allowed_agents = explicit_allowed_agents
    if not derived_allowed_agents and skill_matched_agents:
        derived_allowed_agents = skill_matched_agents
    if not derived_allowed_agents and capability_allowed_agents:
        derived_allowed_agents = capability_allowed_agents
    if not derived_allowed_agents:
        derived_allowed_agents = list(inferred_constraints.get("allowed_agents", []))
    if resolved_assignee and resolved_assignee.lower() not in {item.lower() for item in derived_allowed_agents}:
        derived_allowed_agents = _normalize_text_list([resolved_assignee] + derived_allowed_agents)

    declared_requirement_bundle = _merge_capability_requirements(
        normalized_required_capabilities,
        capability_index,
    )
    capability_declarations = _build_capability_declarations(
        _normalize_text_list(
            list(inferred_constraints.get("required_capabilities", [])) + normalized_required_capabilities
        ),
        capability_index,
    )
    capability_contracts = _build_capability_contracts(capability_declarations)
    resolved_agent_profile = _build_agent_profile_snapshot(resolved_assignee, agent_defaults_index)
    return {
        "assignee": resolved_assignee,
        "required_capabilities": _normalize_text_list(
            list(inferred_constraints.get("required_capabilities", [])) + normalized_required_capabilities
        ),
        "required_skills": _normalize_text_list(
            list(inferred_constraints.get("required_skills", [])) + normalized_required_skills
        ),
        "allowed_agents": _normalize_text_list(derived_allowed_agents),
        "required_runtime": _normalize_text_list(
            list(inferred_constraints.get("required_runtime", [])) + declared_requirement_bundle["required_runtime"]
        ),
        "tool_requirements": _normalize_text_list(
            list(inferred_constraints.get("tool_requirements", []))
            + declared_requirement_bundle["tool_requirements"]
        ),
        "capability_allowed_agents": capability_allowed_agents,
        "skill_matched_agents": skill_matched_agents,
        "capability_default_agents": capability_default_agents,
        "capability_declarations": capability_declarations,
        "capability_contracts": capability_contracts,
        "resolved_agent_profile": resolved_agent_profile,
        "resolution_reason": resolution_reason or "unresolved",
        "agent_default_present": resolved_assignee.lower() in agent_defaults_index if resolved_assignee else False,
    }


def extend_create_task_args_with_constraints(
    create_args: list[str],
    assignee: str,
    *,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Append inferred capability constraint flags to a create-task command."""

    constraints = infer_task_capability_constraints(assignee, registry=registry)
    if constraints["required_capabilities"]:
        create_args.extend(["--required-capabilities", ",".join(constraints["required_capabilities"])])
    if constraints["required_skills"]:
        create_args.extend(["--required-skills", ",".join(constraints["required_skills"])])
    if constraints["allowed_agents"]:
        create_args.extend(["--allowed-agents", ",".join(constraints["allowed_agents"])])
    return create_args


def build_task_constraint_fields(
    assignee: str,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return inferred constraint fields for direct task payload construction."""

    return infer_task_capability_constraints(assignee, registry=registry)

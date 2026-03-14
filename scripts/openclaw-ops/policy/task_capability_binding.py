#!/usr/bin/env python3
"""Helpers for attaching capability constraints to generated tasks."""

from __future__ import annotations

from typing import Any


ROLE_ONLY_AGENTS = {
    "agent-factory",
    "ops-agent",
    "optimization-agent",
    "project-agent",
    "web-agent",
}

SKILL_REQUIREMENTS_BY_AGENT: dict[str, list[str]] = {
    "main": ["requirements-clarity", "task-decomposer"],
    "coordinator": ["requirements-clarity", "task-decomposer"],
    "backend-dev": ["feature-development"],
    "frontend-dev": ["frontend-design", "feature-development"],
    "reviewer": ["requesting-code-review"],
    "tester": ["webapp-testing"],
    "deployer": ["deployment-test"],
    "doc-writer": ["writing-plans"],
}


def infer_task_capability_constraints(assignee: str) -> dict[str, list[str]]:
    normalized = str(assignee or "").strip()
    if not normalized:
        return {
            "required_capabilities": [],
            "required_skills": [],
            "allowed_agents": [],
        }

    if normalized in ROLE_ONLY_AGENTS:
        return {
            "required_capabilities": ["role_only"],
            "required_skills": [],
            "allowed_agents": [normalized],
        }

    required_skills = list(SKILL_REQUIREMENTS_BY_AGENT.get(normalized, []))
    required_capabilities = ["skill_backed"] if required_skills else []
    return {
        "required_capabilities": required_capabilities,
        "required_skills": required_skills,
        "allowed_agents": [normalized],
    }


def extend_create_task_args_with_constraints(create_args: list[str], assignee: str) -> list[str]:
    constraints = infer_task_capability_constraints(assignee)
    if constraints["required_capabilities"]:
        create_args.extend(["--required-capabilities", ",".join(constraints["required_capabilities"])])
    if constraints["required_skills"]:
        create_args.extend(["--required-skills", ",".join(constraints["required_skills"])])
    if constraints["allowed_agents"]:
        create_args.extend(["--allowed-agents", ",".join(constraints["allowed_agents"])])
    return create_args


def build_task_constraint_fields(assignee: str) -> dict[str, Any]:
    return infer_task_capability_constraints(assignee)

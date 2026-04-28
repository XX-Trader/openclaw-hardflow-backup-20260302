#!/usr/bin/env python3
"""Project delivery pipeline state machine.

This runner owns deterministic orchestration artifacts and gates. It does not
pretend to be the coding agent runtime. In dry-run mode it simulates every
stage so the workflow can be tested without mutating product code. In live mode
it requires external agent artifacts for implementation, verification, and
review stages.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable


SCHEMA_VERSION = "1.0"
DEFAULT_RUNTIME_HOME = {
    "generic": "~/.hardflow-runtime",
    "hermes": "~/.hermes",
    "openclaw": "~/.openclaw",
}
EXPECTED_VERDICTS = {
    "requirements_review": "ready_for_solution",
    "solution_review": "ready_for_implement",
    "code_review": "pass",
}
PROJECT_MEMORY_FILES = {
    "PROJECT_PROFILE.md": "project profile and module boundary",
    "DECISIONS.md": "durable project decisions",
    "DELIVERY_RULES.md": "coding and acceptance rules",
    "API_REGISTRY.json": "third-party API ownership and docs",
    "SOURCE_REGISTRY.json": "official docs, changelog, and repo sources",
    "IMPACT_MAP.json": "module/file impact map for change localization",
    "RETRIEVAL_MANIFEST.json": "hybrid retrieval policy and optional RAG backend",
}
STAGE_AGENT_MAP = {
    "intake": "coordinator",
    "context_snapshot": "project-agent",
    "project_memory_context": "project-agent",
    "external_research": "web-agent",
    "requirements_package": "project-agent",
    "requirements_discussion": "project-agent,reviewer",
    "requirements_review": "reviewer",
    "solution_package": "project-agent",
    "solution_review": "reviewer",
    "code_execution": "backend-dev",
    "verification": "tester",
    "code_review": "reviewer",
    "deployment": "deployer",
    "acceptance": "tester",
    "writeback": "doc-writer",
    "git_publish": "coordinator",
}
SIMULATED_FAILURES = {
    "requirements",
    "solution",
    "verification",
    "code_review",
    "acceptance_requirement",
    "acceptance_implementation",
    "git_publish",
}
VERDICT_RE = re.compile(
    r"(?im)^\s*(?:Final verdict|final_verdict|verdict)\s*:\s*([a-z_]+)"
)
DUAL_REVIEW_STAGES = {"requirements_review", "solution_review", "code_review"}
REVIEWER_ROLE_ARG_RE = re.compile(
    r"(?:^|\s)--reviewer-role(?:=|\s+)(?:\"([A-Za-z0-9_.-]+)\"|'([A-Za-z0-9_.-]+)'|([A-Za-z0-9_.-]+))"
)
REVIEWER_ROLE_OUTPUT_RE = re.compile(
    r"(?im)^\s*(?:Reviewer role|reviewer_role|reviewer-role)\s*:\s*([A-Za-z0-9_.-]+)\s*$"
)
PATH_TOKEN_RE = re.compile(
    r"(?:`([^`\r\n]+)`)|(?:\b([A-Za-z0-9_.\-/\\]+(?:\.(?:py|md|json|yaml|yml|toml|js|jsx|ts|tsx|sh|ps1|sql)))\b)"
)
PLAN_PATH_RE = re.compile(r"(?:/|\\|\.(?:py|md|json|yaml|yml|toml|js|jsx|ts|tsx|sh|ps1|sql)$)", re.IGNORECASE)
PIPELINE_ARTIFACT_FILES = {
    "context_snapshot.md",
    "delivery_evidence.md",
    "delivery_plan.json",
    "git_publish_report.md",
    "patch_summary.md",
    "pipeline_state.json",
    "project_memory_context.md",
    "requirements.md",
    "requirements_discussion.md",
    "requirements_review.md",
    "research_report.md",
    "resolved_requirement.md",
    "solution.md",
    "solution_review.md",
    "verification_report.md",
    "writeback_report.md",
}


class PipelineError(RuntimeError):
    """Raised for invalid runner input."""


@dataclass(frozen=True)
class PipelineConfig:
    project_key: str
    requirement: str | None = None
    requirement_file: Path | None = None
    runtime_host: str = "generic"
    runtime_home: str | None = None
    workspace_root: Path = Path(".workflow/pipeline-runs")
    run_id: str | None = None
    source_urls: tuple[str, ...] = ()
    dry_run: bool = False
    simulate_failure_stage: str | None = None
    max_repair_loops: int = 2
    research_report_file: Path | None = None
    research_commands: tuple[str, ...] = ()
    requirements_discussion_commands: tuple[str, ...] = ()
    requirements_review_commands: tuple[str, ...] = ()
    solution_review_commands: tuple[str, ...] = ()
    code_agent: str = "backend-dev"
    code_command: str | None = None
    patch_summary_file: Path | None = None
    verification_commands: tuple[str, ...] = ()
    verification_report_file: Path | None = None
    code_review_command: str | None = None
    code_review_commands: tuple[str, ...] = ()
    code_review_file: Path | None = None
    deployment_command: str | None = None
    memory_write_command: str | None = None
    git_publish_command: str | None = None
    write_project_memory: bool = False
    command_cwd: Path = Path(".")
    agent_workspace_root: Path | None = None
    command_timeout_seconds: int = 600
    project_memory_root: Path = Path(".workflow/project-memory")
    record_task_center: bool = False
    task_center_db: Path | None = None
    task_center_task_id: str | None = None
    force: bool = False


@dataclass
class StageRecord:
    name: str
    status: str
    artifact: str | None = None
    verdict: str | None = None
    score: int | None = None
    next_action: str = "continue"
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "artifact": self.artifact,
            "verdict": self.verdict,
            "score": self.score,
            "next_action": self.next_action,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AgentWorkspace:
    stage: str
    agent_id: str
    workspace_dir: Path
    repo_dir: Path
    mode: str
    isolated: bool
    primary: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "agent_id": self.agent_id,
            "workspace_dir": str(self.workspace_dir),
            "repo_dir": str(self.repo_dir),
            "mode": self.mode,
            "isolated": self.isolated,
            "primary": self.primary,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug[:64] or "pipeline-run"


def default_run_id(project_key: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{slugify(project_key)}"


def load_requirement(config: PipelineConfig) -> str:
    parts: list[str] = []
    if config.requirement:
        parts.append(config.requirement.strip())
    if config.requirement_file:
        if not config.requirement_file.exists():
            raise PipelineError(f"requirement file not found: {config.requirement_file}")
        parts.append(config.requirement_file.read_text(encoding="utf-8").strip())
    requirement = "\n\n".join(part for part in parts if part)
    if not requirement:
        raise PipelineError("provide --requirement or --requirement-file")
    return requirement


def resolve_runtime_context(config: PipelineConfig) -> dict[str, Any]:
    runtime_home = config.runtime_home or DEFAULT_RUNTIME_HOME.get(config.runtime_host) or f"~/.{slugify(config.runtime_host)}"
    return {
        "host": config.runtime_host,
        "runtime_home": runtime_home,
        "state_dir": f"{runtime_home}/.workflow/pipeline-runs",
        "skill_entry": "skills/library/project-delivery-pipeline/SKILL.md",
        "adapter_contract": "references/runtime-adapter.md",
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    write_text(path, content)


def write_json_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        return
    write_json(path, payload)


def read_optional_file(path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    if not path.exists():
        raise PipelineError(f"artifact file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def parse_verdict(content: str) -> str | None:
    match = VERDICT_RE.search(content)
    return match.group(1).strip() if match else None


def gate_result(stage_name: str, artifact_path: Path) -> tuple[bool, str | None]:
    expected = EXPECTED_VERDICTS[stage_name]
    verdict = parse_verdict(artifact_path.read_text(encoding="utf-8"))
    return verdict == expected, verdict


def command_report_verdict(report: dict[str, Any]) -> str | None:
    text = "\n".join([str(report.get("stdout") or ""), str(report.get("stderr") or "")])
    return parse_verdict(text)


def normalize_reviewer_role(value: str | None) -> str:
    role = str(value or "").strip().lower()
    return role if re.fullmatch(r"[a-z0-9_.-]+", role) else ""


def reviewer_role_from_command(command_text: str) -> str:
    match = REVIEWER_ROLE_ARG_RE.search(str(command_text or ""))
    if not match:
        return ""
    return normalize_reviewer_role(next((part for part in match.groups() if part), ""))


def reviewer_role_from_output(stdout: str, stderr: str) -> str:
    text = "\n".join([str(stdout or ""), str(stderr or "")])
    match = REVIEWER_ROLE_OUTPUT_RE.search(text)
    return normalize_reviewer_role(match.group(1) if match else "")


def reviewer_role_for_report(report: dict[str, Any]) -> str:
    explicit = normalize_reviewer_role(str(report.get("reviewer_role") or ""))
    if explicit:
        return explicit
    command_role = reviewer_role_from_command(str(report.get("command") or ""))
    if command_role:
        return command_role
    return reviewer_role_from_output(str(report.get("stdout") or ""), str(report.get("stderr") or ""))


def dual_review_pass(stage_name: str, reports: list[dict[str, Any]]) -> bool:
    expected = EXPECTED_VERDICTS[stage_name]
    if len(reports) < 2:
        return False
    if not all(bool(item.get("ok")) and command_report_verdict(item) == expected for item in reports):
        return False
    commands = [str(item.get("command") or "").strip() for item in reports]
    if len({command for command in commands if command}) != len(commands):
        return False
    roles = [reviewer_role_for_report(item) for item in reports]
    if any(not role for role in roles):
        return False
    return len(set(roles)) >= 2


def render_dual_ai_review(stage_name: str, reports: list[dict[str, Any]], verdict: str) -> str:
    expected = EXPECTED_VERDICTS[stage_name]
    roles = [reviewer_role_for_report(item) or "missing" for item in reports]
    commands = [str(item.get("command") or "").strip() for item in reports]
    distinct_commands = len({command for command in commands if command}) == len(commands) if commands else False
    return dedent(
        f"""
        # {stage_name.replace('_', ' ').title()}

        Final verdict: {verdict}
        Confidence: {"high" if verdict == expected else "medium"}

        ## Dual AI Contract
        - Expected verdict: {expected}
        - Reviewer-A evidence: {"present" if "reviewer-a" in roles else "missing"}
        - Reviewer-B evidence: {"present" if "reviewer-b" in roles else "missing"}
        - Reviewer roles: {", ".join(roles) if roles else "missing"}
        - Distinct commands: {str(distinct_commands).lower()}
        - Independent command reports: {len(reports)}

        {command_markdown("Dual AI Review Commands", reports)}
        """
    )


def consensus_review(review_type: str, verdict: str, requirement: str) -> str:
    return dedent(
        f"""
        # {review_type.replace('_', ' ').title()}

        ## Reviewer-A independent opinion
        - Conclusion: {verdict}
        - Key finding: The package is testable and has explicit acceptance gates.

        ## Reviewer-B challenge
        - Conclusion: {verdict}
        - Challenge: Prefer existing runtime skills and deterministic gates before adding new services.

        ## Consensus discussion
        - Round 1: Reviewer-A checks scope and artifact completeness.
        - Round 2: Reviewer-B checks reuse, failure routing, and missing external research.
        - Round 3: Both reviewers agree on the final gate signal.

        ## Joint conclusion
        Final verdict: {verdict}
        Confidence: high
        Dissent: false
        Rewrite targets:
        - requirement package

        ## Requirement excerpt
        {requirement[:800]}
        """
    )


def render_run_meta(config: PipelineConfig, run_id: str, requirement: str, runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "created_at": utc_now(),
        "dry_run": config.dry_run,
        "runtime_context": runtime,
        "source_urls": list(config.source_urls),
        "max_repair_loops": config.max_repair_loops,
        "agent_workspace_strategy": "git-worktree",
        "agent_workspace_root": str(config.agent_workspace_root) if config.agent_workspace_root else "",
        "code_workspace_diff_policy": "always-apply",
        "code_agent": normalize_code_agent(config.code_agent),
        "requirement_preview": requirement[:240],
    }


def render_context_snapshot(requirement: str, runtime: dict[str, Any]) -> str:
    return dedent(
        f"""
        # Context Snapshot

        ## User Requirement
        {requirement}

        ## Runtime
        - Host: {runtime["host"]}
        - Runtime home: {runtime["runtime_home"]}
        - State dir: {runtime["state_dir"]}

        ## Repository Boundary
        - The runner records orchestration artifacts only.
        - Product code changes must be performed by coding agents or by the coordinator.
        - Host-specific details stay inside the runtime adapter.
        """
    )


def project_memory_dir(config: PipelineConfig) -> Path:
    memory_root = config.project_memory_root
    if (
        memory_root == Path(".workflow/project-memory")
        and config.workspace_root != Path(".workflow/pipeline-runs")
    ):
        memory_root = (
            config.workspace_root.parent / "project-memory"
            if config.workspace_root.name in {"pipeline-runs", "runs"}
            else config.workspace_root / "project-memory"
        )
    return memory_root / slugify(config.project_key)


def bootstrap_project_memory_module(config: PipelineConfig, requirement: str, runtime: dict[str, Any]) -> Path:
    memory_dir = project_memory_dir(config)
    memory_dir.mkdir(parents=True, exist_ok=True)

    write_text_if_missing(
        memory_dir / "PROJECT_PROFILE.md",
        dedent(
            f"""
            # Project Profile

            ## Project Key
            {config.project_key}

            ## Purpose
            TODO: describe the product goal, core modules, runtime entrypoints, and deployment boundary.

            ## Runtime Hosts
            - preferred: {runtime["host"]}
            - runtime_home: {runtime["runtime_home"]}

            ## Current Requirement Seed
            {requirement[:800]}
            """
        ),
    )
    write_text_if_missing(
        memory_dir / "DECISIONS.md",
        dedent(
            """
            # Decisions

            Add durable project decisions here. Each entry should include date,
            decision, rejected alternatives, and verification evidence.
            """
        ),
    )
    write_text_if_missing(
        memory_dir / "DELIVERY_RULES.md",
        dedent(
            """
            # Delivery Rules

            - Read project memory before solution design or code execution.
            - Prefer existing module boundaries before introducing new paths.
            - Record the intended change location before editing.
            - If the best location is unclear, stop at requirements or solution revision.
            """
        ),
    )
    write_json_if_missing(
        memory_dir / "API_REGISTRY.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "providers": [],
        },
    )
    write_json_if_missing(
        memory_dir / "SOURCE_REGISTRY.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "sources": [],
        },
    )
    write_json_if_missing(
        memory_dir / "IMPACT_MAP.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "modules": [],
            "last_indexed_at": "",
            "note": "Populate module, owner, entrypoint, tests, docs, and related files before live coding.",
        },
    )
    write_json_if_missing(
        memory_dir / "RETRIEVAL_MANIFEST.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "default_strategy": "hybrid_local_first",
            "required_indexes": [
                "PROJECT_PROFILE.md",
                "DECISIONS.md",
                "DELIVERY_RULES.md",
                "API_REGISTRY.json",
                "SOURCE_REGISTRY.json",
                "IMPACT_MAP.json",
            ],
            "retrieval_order": [
                "structured project memory",
                "keyword and symbol search",
                "semantic/vector search when configured",
                "GraphRAG only for cross-module or multi-hop architecture questions",
            ],
            "optional_backends": {
                "vector_store": "OpenAI vector stores / file_search or compatible local vector DB",
                "graph_rag": "Microsoft GraphRAG or graph-backed retrieval for global architecture questions",
                "mcp": "MCP resources/tools for external systems and runtime state",
            },
        },
    )
    return memory_dir


def render_project_memory_context(config: PipelineConfig, requirement: str, runtime: dict[str, Any]) -> str:
    memory_dir = bootstrap_project_memory_module(config, requirement, runtime)
    file_lines = "\n".join(
        f"- `{name}`: {purpose}" for name, purpose in sorted(PROJECT_MEMORY_FILES.items())
    )
    return dedent(
        f"""
        # Project Memory Context

        ## Memory Module
        - Project key: {config.project_key}
        - Memory dir: {memory_dir}
        - Runtime host: {runtime["host"]}

        ## Required Files
        {file_lines}

        ## Retrieval Gate
        Before solution design and before coding, project-agent must identify:
        - existing module or file most likely to own the change
        - related tests and docs that must move with the change
        - prior decisions that constrain the implementation
        - source/API registry entries that require current external checks

        ## Retrieval Strategy
        - Default: hybrid local-first retrieval using structured memory, keyword search, and symbol/file mapping.
        - Optional vector RAG: use when project docs exceed the prompt budget or semantic recall is needed.
        - Optional GraphRAG: use only for cross-module, multi-hop, or architecture-level questions where file-level search is not enough.
        - MCP resources/tools may expose external systems, but must respect project/workspace boundaries.

        ## Anti Local-Optimum Rule
        Coding is blocked until `IMPACT_MAP.json` or this run's context snapshot names the likely change location.
        If no reliable location exists, route back to `requirements_package` or `solution_package` instead of guessing.
        """
    )


def render_research_report(
    config: PipelineConfig,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if config.research_report_file:
        return read_optional_file(config.research_report_file, "")

    source_lines = "\n".join(f"- {url}" for url in config.source_urls) or "- No live source URLs supplied to runner."
    mode = "dry-run simulated research" if config.dry_run else "live research evidence required"
    command_section = command_markdown("Research Commands", command_reports) if command_reports else ""
    return dedent(
        f"""
        # External Research Report

        ## Status
        - Mode: {mode}
        - Gate rule: implementation cannot rely only on memory when external SDKs, APIs, or existing solutions may exist.

        ## Sources Checked Or Required
        {source_lines}

        ## Reuse Decision
        - Prefer official SDKs, existing runtime skills, and mature open-source implementations before writing new code.
        - If a source changes the requirement or solution, route back to the requirements or solution package before coding.

        ## Existing Code Candidates
        - dual-ai-review templates and review gate artifacts
        - failure tracker CLI contract
        - project memory writer/injector contract

        {command_section}
        """
    )


def render_requirements(requirement: str) -> str:
    return dedent(
        f"""
        # Requirement Package

        ## Original Requirement
        {requirement}

        ## Normalized Requirement
        Deliver the user request above exactly as written, preserving its target
        files, non-goals, safety boundaries, deployment expectations, and publish
        requirements. If later discussion narrows or corrects the scope, the
        refined requirement must stay tied to this original request instead of
        falling back to a generic pipeline template.

        ## Scope Guard
        - Keep implementation scoped to the original request and the accepted
          requirements discussion.
        - Do not continue unrelated feature slices when the request is about
          workflow repair, deployment, cleanup, documentation, or diagnosis.
        - If the request names files, services, run ids, artifacts, dirty
          worktree entries, or safety constraints, treat them as acceptance inputs.

        ## Acceptance Criteria
        - Requirements review must return ready_for_solution.
        - The requirement package and discussion must preserve the user-specific
          objective, explicit non-goals, and safety constraints.
        - Project memory context must name likely change locations or force revision.
        - Solution review must return ready_for_implement.
        - Verification must pass before acceptance.
        - Code review must return pass.
        - Acceptance failures must be routed to the correct upstream stage.
        """
    )


def render_requirements_discussion(requirement: str) -> str:
    return dedent(
        f"""
        # Dual-Agent Requirement Discussion

        ## Goal
        Two AI roles must actively discuss the requirement before the final requirement review:
        - `project-agent`: product/project analyst, owns user intent, scope, acceptance criteria, and delivery constraints.
        - `reviewer`: independent challenger, owns ambiguity, hidden risks, missing evidence, and testability.

        ## Original Requirement
        {requirement}

        ## Discussion Transcript Template

        ### Round 1 - project-agent: intent and first draft
        - Restate the user goal in concrete, testable language.
        - Identify target users, entry points, outputs, constraints, and non-goals.
        - Draft acceptance criteria and required evidence.

        ### Round 2 - reviewer: challenge and gap finding
        - Challenge unclear terms, missing data contracts, unsafe assumptions, and unsupported external facts.
        - Ask whether internet or official documentation research is required before implementation.
        - Identify risks that would make the requirement incomplete or unsafe.

        ### Round 3 - project-agent: revised requirement
        - Answer reviewer challenges.
        - Add missing scope boundaries, explicit non-goals, validation steps, and rollback/verification expectations.
        - Convert the discussion into a coherent requirement document outline.

        ### Round 4 - reviewer: final tightening
        - Confirm the requirement is specific, testable, bounded, and implementable.
        - List any remaining open questions that must block coding.
        - If no blocking questions remain, mark the requirement ready for formal review.

        ## Final Requirement Document Contract
        The final `requirements.md` / requirement package must include:
        - Problem statement
        - Users and entry points
        - In-scope behavior
        - Out-of-scope behavior
        - Data/API/config contracts
        - External research evidence needed or supplied
        - Acceptance criteria
        - Test and verification plan
        - Security/credential/production boundaries
        - Open questions, with coding blocked if any are material
        """
    )


def render_resolved_requirement(requirement: str, artifacts: dict[str, str]) -> str:
    discussion = read_optional_file(Path(artifacts.get("requirements_discussion", "")), "")
    review = read_optional_file(Path(artifacts.get("requirements_review", "")), "")
    return dedent(
        f"""
        # Resolved Requirement

        ## Original Requirement
        {requirement}

        ## Accepted Requirement Source
        The accepted implementation scope is the original requirement plus the
        completed requirements discussion and requirements review below. Downstream
        stages must use this artifact as the handoff contract and must not fall
        back to a generic pipeline template.

        ## Requirements Discussion
        {discussion}

        ## Requirements Review
        {review}
        """
    )


def clean_plan_path(value: str) -> str:
    path = str(value or "").strip().strip(".,;:()[]{}<>\"'")
    if not path:
        return ""
    path = path.replace("\\", "/")
    name = Path(path).name
    if name in PIPELINE_ARTIFACT_FILES:
        return ""
    if not PLAN_PATH_RE.search(path):
        return ""
    if path.startswith(("/tmp/", "/home/", "C:/", "c:/")):
        return ""
    return path


def extract_plan_paths(*texts: str, limit: int = 24) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in PATH_TOKEN_RE.finditer(str(text or "")):
            candidate = clean_plan_path(match.group(1) or match.group(2) or "")
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            paths.append(candidate)
            if len(paths) >= limit:
                return paths
    return paths


def infer_task_type(text: str) -> str:
    value = str(text or "")
    lowered = value.lower()
    if any(token in lowered for token in ("docs-only", "doc-only", "memory/docs-only", "memory-only")):
        return "docs"
    if any(token in lowered for token in ("bug", "fix", "failed", "requires_revision", "修复", "失败", "阻塞")):
        return "bugfix"
    if any(token in lowered for token in ("deploy", "restart", "install", "runtime", "部署", "重启", "安装")):
        return "deploy"
    if any(token in lowered for token in ("research", "官方", "调研", "资料")):
        return "research"
    if (
        re.search(r"\b(?:only|just)\s+(?:update|edit|write|sync)\b.{0,60}\b(?:docs?|documentation|memory|readme)\b", lowered)
        or re.search(r"(?:只|仅|只需|仅需|只要).{0,30}(?:更新|修改|补充|同步|整理|撰写|写).{0,60}(?:文档|记忆|README)", value, re.IGNORECASE)
    ):
        return "docs"
    return "feature"


def infer_code_agent(text: str, config: PipelineConfig) -> str:
    lowered = str(text or "").lower()
    if config.code_agent == "frontend-dev":
        return "frontend-dev"
    if any(token in lowered for token in ("frontend", "dashboard", "页面", "前端", "交互")) or re.search(r"\bui\b", lowered):
        return "frontend-dev"
    if infer_task_type(text) == "docs":
        return "doc-writer"
    return normalize_code_agent(config.code_agent)


def original_requirement_excerpt(requirement: str) -> str:
    match = re.search(r"(?ims)^## Original Requirement\s*(.+?)(?=^## |\Z)", str(requirement or ""))
    source = match.group(1) if match else requirement
    lines = [line.strip(" -\t") for line in str(source or "").splitlines() if line.strip(" -\t")]
    return next((line for line in lines if not line.startswith("#")), "")


def plan_scope_slice(requirement: str, review: str, repair_context: str) -> dict[str, Any]:
    original = original_requirement_excerpt(requirement)
    source = repair_context or original or review or requirement
    lines = [line.strip(" -\t") for line in str(source or "").splitlines() if line.strip(" -\t")]
    summary = next((line for line in lines if not line.startswith("#")), "Deliver the accepted requirement.")
    return {
        "id": "primary",
        "description": clip_text(summary, 280),
        "source": "repair_context" if repair_context else ("original_requirement" if original else "requirements_review"),
    }


def configured_verification_commands(config: PipelineConfig, task_type: str) -> list[dict[str, Any]]:
    commands = [
        {"command": command, "required": True, "source": "runner_config"}
        for command in config.verification_commands
    ]
    if commands:
        return commands
    fallback = [{"command": "git diff --check", "required": True, "source": "default"}]
    if task_type != "docs":
        fallback.append(
            {
                "command": "Run the focused tests or compile checks that cover changed files.",
                "required": True,
                "source": "agent_selected",
            }
        )
    return fallback


def render_markdown_items(items: list[str]) -> str:
    cleaned = [clip_text(str(item).strip(), 240) for item in items if str(item).strip()]
    if not cleaned:
        return "- not_applicable"
    return "\n".join(f"- {item}" for item in cleaned)


def artifact_text(artifacts: dict[str, str], key: str) -> str:
    path = artifacts.get(key)
    if not path:
        return ""
    return read_optional_file(Path(path), "")


def compile_delivery_plan(
    config: PipelineConfig,
    runtime: dict[str, Any],
    requirement: str,
    artifacts: dict[str, str],
) -> dict[str, Any]:
    research = artifact_text(artifacts, "external_research")
    memory = artifact_text(artifacts, "project_memory_context")
    requirements_review = artifact_text(artifacts, "requirements_review")
    repair_context = os.environ.get("PIPELINE_REPAIR_CONTEXT", "").strip()
    original_requirement = original_requirement_excerpt(requirement) or requirement
    decision_text = "\n".join([requirement, requirements_review, repair_context])
    classification_text = "\n".join(
        part for part in (original_requirement, repair_context) if str(part or "").strip()
    ) or requirements_review
    task_type = infer_task_type(classification_text)
    target_paths = extract_plan_paths(requirement, requirements_review, repair_context)
    if not target_paths:
        target_paths = extract_plan_paths(research, memory)
    target_files = [
        {
            "path": path,
            "reason": "Referenced by accepted requirement, review, repair context, or project evidence.",
            "confidence": "explicit",
        }
        for path in target_paths
    ]
    discovery_required = not target_files
    implementation_steps = [
        {
            "id": "locate",
            "description": (
                "Use repository search and project memory to confirm the exact files and entry points before editing."
                if discovery_required
                else "Open the listed target files and confirm the current behavior before editing."
            ),
            "required": True,
        },
        {
            "id": "change",
            "description": "Apply the smallest scoped change that satisfies the accepted requirement and repair findings.",
            "required": True,
        },
        {
            "id": "verify",
            "description": "Run every required verification command and record concrete outcomes.",
            "required": True,
        },
        {
            "id": "review",
            "description": "Do not proceed to acceptance or publish until code review gates pass.",
            "required": True,
        },
    ]
    return {
        "schema_version": "delivery-plan/v1",
        "task_type": task_type,
        "owner": infer_code_agent(classification_text, config),
        "source_artifacts": {
            key: artifacts[key]
            for key in (
                "resolved_requirement",
                "requirements_review",
                "requirements_discussion",
                "external_research",
                "project_memory_context",
            )
            if key in artifacts
        },
        "runtime": {
            "host": runtime.get("host", ""),
            "runtime_home": runtime.get("runtime_home", ""),
        },
        "scope_slices": [plan_scope_slice(requirement, requirements_review, repair_context)],
        "target_files": target_files,
        "entry_points": [
            {"path": path["path"], "reason": path["reason"]}
            for path in target_files[:8]
        ],
        "out_of_scope": [
            "Do not broaden the task beyond the accepted requirement.",
            "Do not use secrets, credentials, private keys, cookies, or auth state files.",
            "Do not start real trading, place orders, transfer funds, or change production trading controls.",
        ],
        "implementation_steps": implementation_steps,
        "verification_commands": configured_verification_commands(config, task_type),
        "release_gates": [
            "All required verification commands pass.",
            "Dual review gates pass with the expected final verdicts.",
            "Deployment or git publish only runs when explicitly configured by the runner.",
        ],
        "rollback_plan": [
            "If verification or code review fails after a workspace patch is applied, revert the applied patch and preserve rollback evidence.",
            "If rollback fails, stop with manual_cleanup_required.",
        ],
        "human_blockers": [
            "Requires credentials, secret values, private keys, cookies, or auth state access.",
            "Requires real trading authorization, order placement, fund movement, withdrawals, destructive data operations, or force push.",
            "Target files cannot be located from repository evidence and implementation would require guessing.",
        ],
        "risk_boundaries": [
            {"name": "credentials", "allowed": False, "description": "No credential or secret access."},
            {"name": "real_trading", "allowed": False, "description": "Production trading remains disabled."},
            {"name": "fund_movement", "allowed": False, "description": "No orders, transfers, withdrawals, or fund movement."},
        ],
        "plan_findings": {
            "discovery_required": discovery_required,
            "repair_context_present": bool(repair_context),
        },
    }


def render_solution(delivery_plan: dict[str, Any]) -> str:
    target_files = delivery_plan.get("target_files") if isinstance(delivery_plan.get("target_files"), list) else []
    verification_commands = delivery_plan.get("verification_commands") if isinstance(delivery_plan.get("verification_commands"), list) else []
    implementation_steps = delivery_plan.get("implementation_steps") if isinstance(delivery_plan.get("implementation_steps"), list) else []
    human_blockers = delivery_plan.get("human_blockers") if isinstance(delivery_plan.get("human_blockers"), list) else []
    out_of_scope = delivery_plan.get("out_of_scope") if isinstance(delivery_plan.get("out_of_scope"), list) else []
    return "\n".join(
        [
            "# Solution Package",
            "",
            "## Delivery Plan Contract",
            "- Source of truth: `delivery_plan.json`",
            f"- Schema: {delivery_plan.get('schema_version', 'delivery-plan/v1')}",
            f"- Task type: {delivery_plan.get('task_type', 'feature')}",
            f"- Owner: {delivery_plan.get('owner', 'backend-dev')}",
            "",
            "## Scope Slices",
            render_markdown_items([item.get("description", "") for item in delivery_plan.get("scope_slices", []) if isinstance(item, dict)]),
            "",
            "## Target Files",
            render_markdown_items([item.get("path", "") for item in target_files if isinstance(item, dict)] or ["Discovery required before editing; do not guess."]),
            "",
            "## Implementation Steps",
            render_markdown_items([item.get("description", "") for item in implementation_steps if isinstance(item, dict)]),
            "",
            "## Verification Commands",
            render_markdown_items([item.get("command", "") for item in verification_commands if isinstance(item, dict)]),
            "",
            "## Out Of Scope",
            render_markdown_items([str(item) for item in out_of_scope]),
            "",
            "## Human Blockers",
            render_markdown_items([str(item) for item in human_blockers]),
            "",
            "## Review Contract",
            "Reviewers must validate `delivery_plan.json`, not prose shape alone. The plan is not ready for implementation if it lacks scope, target discovery, verification commands, release gates, rollback behavior, or human blockers.",
        ]
    )


def clip_text(value: str, limit: int = 12000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... truncated {len(text) - limit} chars ..."


def normalize_code_agent(value: str | None) -> str:
    agent = str(value or "").strip()
    return agent if agent in {"backend-dev", "frontend-dev"} else "backend-dev"


def stage_agent_ids(stage_name: str, config: PipelineConfig | None = None) -> list[str]:
    raw = normalize_code_agent(config.code_agent) if stage_name == "code_execution" and config else STAGE_AGENT_MAP.get(stage_name, "coordinator")
    agents = [part.strip() for part in str(raw).split(",") if part.strip()]
    return agents or ["coordinator"]


def agent_workspace_base(config: PipelineConfig, run_dir: Path) -> Path:
    if config.agent_workspace_root is not None:
        root = config.agent_workspace_root.expanduser()
        return root / run_dir.name if root.name != run_dir.name else root
    return run_dir / "agent-workspaces"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def ensure_agent_repo(base_cwd: Path, workspace_dir: Path) -> tuple[Path, str, bool]:
    repo_dir = workspace_dir / "repo"
    if repo_dir.exists():
        return repo_dir, "worktree", True

    workspace_dir.mkdir(parents=True, exist_ok=True)
    try:
        nested_under_base = repo_dir.resolve().is_relative_to(base_cwd.resolve())
    except OSError:
        nested_under_base = False
    if nested_under_base:
        raise PipelineError(
            f"agent workspace root must be outside command cwd for git worktree mode: "
            f"repo={repo_dir} command_cwd={base_cwd}"
        )
    inside = run_git(["rev-parse", "--is-inside-work-tree"], base_cwd)
    head = run_git(["rev-parse", "HEAD"], base_cwd)
    if inside.returncode != 0 or head.returncode != 0:
        raise PipelineError(f"agent workspaces require a git repository with HEAD: {base_cwd}")
    proc = run_git(["worktree", "add", "--detach", str(repo_dir), "HEAD"], base_cwd)
    if proc.returncode != 0:
        raise PipelineError(f"failed to create git worktree at {repo_dir}: {proc.stderr.strip()}")
    return repo_dir, "worktree", True


def apply_patch_file(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    if not patch_file.exists() or patch_file.stat().st_size == 0:
        return {"ok": True, "applied": False, "returncode": 0, "stderr": ""}
    proc = run_git(["apply", "--whitespace=nowarn", str(patch_file)], repo_dir)
    return {
        "ok": proc.returncode == 0,
        "applied": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": clip_text(proc.stdout),
        "stderr": clip_text(proc.stderr),
    }


def git_status_porcelain(repo_dir: Path) -> dict[str, Any]:
    proc = run_git(["status", "--porcelain"], repo_dir)
    status = proc.stdout or ""
    return {
        "ok": proc.returncode == 0 and not status.strip(),
        "returncode": proc.returncode,
        "dirty": bool(status.strip()),
        "stdout": clip_text(status),
        "stderr": clip_text(proc.stderr),
    }


def status_paths(porcelain: str) -> set[str]:
    paths: set[str] = set()
    for line in str(porcelain or "").splitlines():
        if not line.strip() or len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.rsplit(" -> ", 1)[-1].strip()
        paths.add(raw.strip('"'))
    return paths


def patch_paths(patch_file: Path) -> set[str]:
    paths: set[str] = set()
    try:
        content = patch_file.read_text(encoding="utf-8")
    except OSError:
        return paths
    for line in content.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) >= 4:
            path = parts[3]
            if path.startswith("b/"):
                path = path[2:]
            paths.add(path.strip('"'))
    return paths


def command_cwd_patch_preflight(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    status = git_status_porcelain(repo_dir)
    dirty_paths = status_paths(str(status.get("stdout") or ""))
    changed_paths = patch_paths(patch_file)
    overlapping = sorted(dirty_paths & changed_paths)
    return {
        "ok": status.get("returncode") == 0 and not overlapping,
        "returncode": status.get("returncode", 0),
        "dirty": bool(dirty_paths),
        "dirty_paths": sorted(dirty_paths),
        "patch_paths": sorted(changed_paths),
        "overlapping_dirty_paths": overlapping,
        "stdout": status.get("stdout", ""),
        "stderr": status.get("stderr", ""),
    }


def reverse_patch_file(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    if not patch_file.exists() or patch_file.stat().st_size == 0:
        return {"ok": True, "reverted": False, "returncode": 0, "stderr": ""}
    proc = run_git(["apply", "-R", "--whitespace=nowarn", str(patch_file)], repo_dir)
    return {
        "ok": proc.returncode == 0,
        "reverted": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": clip_text(proc.stdout),
        "stderr": clip_text(proc.stderr),
    }


def rollback_applied_code_patch(
    config: PipelineConfig,
    run_dir: Path,
    artifacts: dict[str, str],
    patch_file: Path | None,
    reason: str,
) -> dict[str, Any]:
    if patch_file is None:
        return {"ok": True, "reverted": False, "reason": reason, "patch_file": ""}
    report = reverse_patch_file(config.command_cwd.expanduser().resolve(), patch_file)
    report["reason"] = reason
    report["patch_file"] = str(patch_file)
    report_file = run_dir / "command-runs" / f"rollback-{slugify(reason)}.json"
    report["report_file"] = str(report_file)
    write_json(report_file, report)
    artifacts[f"rollback_{slugify(reason)}"] = str(report_file)
    return report


def rollback_failed(report: dict[str, Any]) -> bool:
    return bool(report.get("patch_file")) and not bool(report.get("ok"))


def rollback_failure_detail(report: dict[str, Any]) -> str:
    stderr = str(report.get("stderr") or "").strip()
    return (
        "failed to rollback an unaccepted code workspace patch from command cwd; "
        "manual cleanup is required before continuing"
        + (f": {clip_text(stderr, 600)}" if stderr else "")
    )


def export_workspace_patch(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    inside = run_git(["rev-parse", "--is-inside-work-tree"], repo_dir)
    if inside.returncode != 0:
        return {
            "ok": False,
            "patch_file": str(patch_file),
            "stderr": "workspace repo is not a git repository; cannot export workspace diff",
        }
    run_git(["add", "-N", "."], repo_dir)
    proc = run_git(["diff", "--binary"], repo_dir)
    if proc.returncode != 0:
        return {
            "ok": False,
            "patch_file": str(patch_file),
            "stdout": clip_text(proc.stdout),
            "stderr": clip_text(proc.stderr),
        }
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(proc.stdout or "", encoding="utf-8")
    return {
        "ok": True,
        "patch_file": str(patch_file),
        "has_changes": bool((proc.stdout or "").strip()),
        "stdout": "",
        "stderr": "",
    }


def update_agent_workspace_manifest(run_dir: Path, stage_name: str, index: int, workspaces: list[AgentWorkspace]) -> Path:
    manifest_file = run_dir / "agent-workspaces" / "manifest.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    manifest.setdefault("stages", {})
    manifest["updated_at"] = utc_now()
    manifest["stages"].setdefault(stage_name, {})
    manifest["stages"][stage_name][str(index)] = [workspace.as_dict() for workspace in workspaces]
    write_json(manifest_file, manifest)
    return manifest_file


def prepare_agent_workspaces(
    config: PipelineConfig,
    run_dir: Path,
    stage_name: str,
    index: int,
    base_cwd: Path,
    input_patch_file: Path | None = None,
) -> list[AgentWorkspace]:
    workspaces: list[AgentWorkspace] = []
    root = agent_workspace_base(config, run_dir)
    for agent_index, agent_id in enumerate(stage_agent_ids(stage_name, config)):
        workspace_dir = root / slugify(stage_name) / slugify(agent_id)
        repo_preexisted = (workspace_dir / "repo").exists()
        repo_dir, effective_mode, isolated = ensure_agent_repo(base_cwd, workspace_dir)
        workspace = AgentWorkspace(
            stage=stage_name,
            agent_id=agent_id,
            workspace_dir=workspace_dir,
            repo_dir=repo_dir,
            mode=effective_mode,
            isolated=isolated,
            primary=agent_index == 0,
        )
        if agent_index == 0 and input_patch_file and isolated and not repo_preexisted:
            result = apply_patch_file(repo_dir, input_patch_file)
            if not result.get("ok"):
                raise PipelineError(
                    f"failed to apply prior code workspace diff to {agent_id} workspace: "
                    f"{result.get('stderr', '')}"
                )
        workspaces.append(workspace)
    update_agent_workspace_manifest(run_dir, stage_name, index, workspaces)
    return workspaces


def command_env(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    requirement: str,
    stage_name: str = "",
    primary_workspace: AgentWorkspace | None = None,
    workspaces: list[AgentWorkspace] | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    requirement_file = run_dir / "requirement.txt"
    if not requirement_file.exists():
        write_text(requirement_file, requirement)
    memory_dir = project_memory_dir(config)
    env.update(
        {
            "PIPELINE_RUN_DIR": str(run_dir),
            "PIPELINE_REQUIREMENT_FILE": str(requirement_file),
            "PIPELINE_PROJECT_KEY": config.project_key,
            "PIPELINE_RUNTIME_HOST": str(runtime.get("host", "")),
            "PIPELINE_RUNTIME_HOME": str(runtime.get("runtime_home", "")),
            "PIPELINE_PROJECT_MEMORY_DIR": str(memory_dir),
            "PIPELINE_RESEARCH_REPORT_FILE": str(run_dir / "research_report.md"),
            "PIPELINE_REQUIREMENTS_FILE": str(run_dir / "requirements.md"),
            "PIPELINE_REQUIREMENTS_DISCUSSION_FILE": str(run_dir / "requirements_discussion.md"),
            "PIPELINE_REQUIREMENTS_REVIEW_FILE": str(run_dir / "requirements_review.md"),
            "PIPELINE_DELIVERY_PLAN_FILE": str(run_dir / "delivery_plan.json"),
            "PIPELINE_SOLUTION_FILE": str(run_dir / "solution.md"),
            "PIPELINE_SOLUTION_REVIEW_FILE": str(run_dir / "solution_review.md"),
            "PIPELINE_PATCH_SUMMARY_FILE": str(run_dir / "patch_summary.md"),
            "PIPELINE_VERIFICATION_REPORT_FILE": str(run_dir / "verification_report.md"),
            "PIPELINE_CODE_REVIEW_FILE": str(run_dir / "code_review.md"),
            "PIPELINE_DEPLOYMENT_REPORT_FILE": str(run_dir / "deployment_report.md"),
            "PIPELINE_WRITEBACK_REPORT_FILE": str(run_dir / "writeback_report.md"),
            "PIPELINE_GIT_PUBLISH_REPORT_FILE": str(run_dir / "git_publish_report.md"),
        }
    )
    if stage_name:
        env["PIPELINE_STAGE_NAME"] = stage_name
    if primary_workspace is not None:
        env.update(
            {
                "PIPELINE_AGENT_ID": primary_workspace.agent_id,
                "PIPELINE_AGENT_WORKSPACE": str(primary_workspace.workspace_dir),
                "PIPELINE_AGENT_REPO_DIR": str(primary_workspace.repo_dir),
                "PIPELINE_AGENT_WORKSPACE_MODE": primary_workspace.mode,
                "PIPELINE_AGENT_WORKSPACE_ISOLATED": "1" if primary_workspace.isolated else "0",
            }
        )
    if workspaces is not None:
        env["PIPELINE_AGENT_WORKSPACES_JSON"] = json.dumps(
            [workspace.as_dict() for workspace in workspaces],
            ensure_ascii=False,
        )
    return env


def run_stage_command(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    artifacts: dict[str, str],
    requirement: str,
    stage_name: str,
    command: str,
    index: int = 1,
    input_patch_file: Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    command_text = str(command or "").strip()
    if not command_text:
        raise PipelineError(f"{stage_name} command must not be empty")
    base_cwd = config.command_cwd.expanduser().resolve()
    if not base_cwd.exists() or not base_cwd.is_dir():
        raise PipelineError(f"command cwd not found: {base_cwd}")
    workspaces = prepare_agent_workspaces(config, run_dir, stage_name, index, base_cwd, input_patch_file)
    primary_workspace = workspaces[0]
    cwd = primary_workspace.repo_dir
    if progress_callback is not None:
        progress_callback(stage_name, f"running command {index} in {primary_workspace.agent_id}")

    started_at = utc_now()
    stdout = ""
    stderr = ""
    returncode = 124
    timed_out = False
    error = ""
    workspace_patch: dict[str, Any] = {}
    try:
        proc = subprocess.run(
            command_text,
            shell=True,
            cwd=str(cwd),
            env=command_env(config, run_dir, runtime, requirement, stage_name, primary_workspace, workspaces),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(config.command_timeout_seconds or 600)),
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        error = f"timeout after {config.command_timeout_seconds}s"

    if (
        stage_name in {"code_execution", "memory_writeback"}
        and returncode == 0
        and not timed_out
        and primary_workspace.isolated
    ):
        patch_file = run_dir / "command-runs" / f"{stage_name}-{index}.patch"
        workspace_patch = export_workspace_patch(primary_workspace.repo_dir, patch_file)
        if (
            stage_name == "code_execution"
            and workspace_patch.get("ok")
            and workspace_patch.get("has_changes")
        ):
            preflight = command_cwd_patch_preflight(base_cwd, patch_file)
            workspace_patch["command_cwd_preflight"] = preflight
            if not preflight.get("ok"):
                returncode = 1
                error = (
                    "command cwd has uncommitted changes overlapping the code workspace diff; "
                    "refusing to apply patch before verification and code review"
                )
                workspace_patch["applied_to_command_cwd"] = {
                    "ok": False,
                    "applied": False,
                    "returncode": int(preflight.get("returncode") or 1),
                    "stderr": preflight.get("stderr", ""),
                }
            else:
                apply_result = apply_patch_file(base_cwd, patch_file)
                workspace_patch["applied_to_command_cwd"] = apply_result
                if not apply_result.get("ok"):
                    returncode = int(apply_result.get("returncode") or 1)
                    error = f"failed to apply code workspace diff to command cwd: {apply_result.get('stderr', '')}"
        elif not workspace_patch.get("ok"):
            returncode = 1
            error = f"failed to export code workspace diff: {workspace_patch.get('stderr', '')}"

    report = {
        "stage": stage_name,
        "index": index,
        "command": command_text,
        "cwd": str(cwd),
        "command_cwd": str(base_cwd),
        "agent_id": primary_workspace.agent_id,
        "agent_workspace": primary_workspace.as_dict(),
        "agent_workspaces": [workspace.as_dict() for workspace in workspaces],
        "dispatch_mode": "isolated-agent-workspace",
        "started_at": started_at,
        "ended_at": utc_now(),
        "returncode": returncode,
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "stdout": clip_text(stdout),
        "stderr": clip_text(stderr),
    }
    if workspace_patch:
        report["workspace_patch"] = workspace_patch
        if workspace_patch.get("patch_file"):
            report["workspace_patch_file"] = workspace_patch["patch_file"]
    if stage_name in DUAL_REVIEW_STAGES:
        report["reviewer_role"] = reviewer_role_from_command(command_text) or reviewer_role_from_output(stdout, stderr)
    report_dir = run_dir / "command-runs"
    report_file = report_dir / f"{stage_name}-{index}.json"
    write_json(report_file, report)
    artifacts[f"command_{stage_name}_{index}"] = str(report_file)
    artifacts["agent_workspace_manifest"] = str(run_dir / "agent-workspaces" / "manifest.json")
    return report


def run_stage_commands(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    artifacts: dict[str, str],
    requirement: str,
    stage_name: str,
    commands: tuple[str, ...],
    input_patch_file: Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    return [
        run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            stage_name,
            command,
            index,
            input_patch_file,
            progress_callback,
        )
        for index, command in enumerate(commands, start=1)
    ]


def commands_ok(reports: list[dict[str, Any]]) -> bool:
    return bool(reports) and all(bool(item.get("ok")) for item in reports)


def command_markdown(title: str, reports: list[dict[str, Any]]) -> str:
    lines = [f"## {title}"]
    for item in reports:
        lines.extend(
            [
                f"### Command {item.get('index')}",
                f"- cwd: `{item.get('cwd', '')}`",
                f"- agent: `{item.get('agent_id', '')}`",
                f"- dispatch: `{item.get('dispatch_mode', '')}`",
                f"- returncode: {item.get('returncode')}",
                f"- ok: {str(item.get('ok')).lower()}",
                "",
                "```text",
                str(item.get("command", "")),
                "```",
            ]
        )
        stdout = str(item.get("stdout", "")).strip()
        stderr = str(item.get("stderr", "")).strip()
        if stdout:
            lines.extend(["", "#### stdout", "```text", stdout, "```"])
        if stderr:
            lines.extend(["", "#### stderr", "```text", stderr, "```"])
    return "\n".join(lines)


def render_patch_summary(config: PipelineConfig, command_report: dict[str, Any] | None = None) -> str:
    if command_report is not None:
        return dedent(
            f"""
            # Patch Summary

            ## Mode
            Live command adapter.

            ## Result
            - Status: {"pass" if command_report.get("ok") else "fail"}
            - Return code: {command_report.get("returncode")}
            - Command evidence: `command-runs/code_execution-1.json`
            - Agent: `{command_report.get("agent_id", "")}`
            - Agent repo: `{command_report.get("cwd", "")}`
            - Workspace diff: `{command_report.get("workspace_patch_file", "") or "not_applicable"}`

            {command_markdown("Coding Command", [command_report])}

            ## Handoff
            Runtime agent output above is treated as the implementation handoff. When the
            command ran in an isolated workspace, the exported workspace diff is applied
            back to the configured command cwd before verification.
            """
        )

    fallback = dedent(
        """
        # Patch Summary

        ## Mode
        Dry-run simulation.

        ## Code Changes
        - No product code was modified by this runner.
        - In a live Hermes run, this artifact is produced by the coding agent after implementation.

        ## Handoff
        - Coding agent must list changed files, behavior changes, tests, and known risks.
        """
    )
    return read_optional_file(config.patch_summary_file, fallback)


def render_verification_report(
    config: PipelineConfig,
    failed: bool,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if command_reports:
        passed = commands_ok(command_reports)
        return dedent(
            f"""
            # Verification Report

            ## Result
            - Status: {"pass" if passed else "fail"}
            - Score: {100 if passed else 55}

            ## Evidence
            - Verification commands executed: {len(command_reports)}
            - Command evidence dir: `command-runs/`

            {command_markdown("Verification Commands", command_reports)}

            ## Failure Class
            - {"none" if passed else "implementation"}
            """
        )

    fallback = dedent(
        f"""
        # Verification Report

        ## Result
        - Status: {"fail" if failed else "pass"}
        - Score: {55 if failed else 100}

        ## Evidence
        - Runner dry-run generated all required orchestration artifacts.
        - Live implementation tests must be attached by the coding agent or verifier.

        ## Failure Class
        - {"implementation" if failed else "none"}
        """
    )
    if config.verification_report_file and not failed:
        return read_optional_file(config.verification_report_file, fallback)
    return fallback


def render_code_review(
    config: PipelineConfig,
    failed: bool,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if command_reports is not None and command_reports:
        return render_dual_ai_review("code_review", command_reports, "requires_revision" if failed else "pass")
    if config.code_review_file and not failed:
        return read_optional_file(config.code_review_file, "")
    verdict = "requires_revision" if failed else "pass"
    return consensus_review("code_review", verdict, "Implementation evidence is attached in patch_summary.md.")


def render_deployment_report(command_report: dict[str, Any] | None) -> str:
    if command_report is not None:
        passed = bool(command_report.get("ok"))
        return dedent(
            f"""
            # Deployment Report

            ## Result
            - Status: {"pass" if passed else "fail"}
            - Return code: {command_report.get("returncode")}
            - Command evidence: `command-runs/deployment-1.json`

            {command_markdown("Deployment Command", [command_report])}
            """
        )
    return dedent(
        """
        # Deployment Report

        ## Result
        - Status: skipped

        ## Evidence
        - No deployment command was supplied for this run.
        """
    )


def render_git_publish_report(command_report: dict[str, Any]) -> str:
    passed = bool(command_report.get("ok"))
    input_patch = command_report.get("input_patch") or {}
    input_patch_file = input_patch.get("patch_file") or "none"
    input_patch_source = input_patch.get("source") or "unknown"
    return dedent(
        f"""
        # Git Publish Report

        ## Result
        - Status: {"pass" if passed else "fail"}
        - Return code: {command_report.get("returncode")}
        - Command evidence: `command-runs/git_publish-1.json`
        - Input patch: `{input_patch_file}` ({input_patch_source})

        ## Contract
        - Git publish runs only after verification, code review, deployment if supplied, acceptance, and memory writeback.
        - Commit message and publish notes must be written in Chinese.
        - Force push and secret-bearing diffs are not allowed.

        {command_markdown("Git Publish Command", [command_report])}
        """
    )


def render_delivery_evidence(score: int, status: str, next_action: str) -> str:
    return dedent(
        f"""
        # Delivery Evidence

        ## Acceptance
        - Status: {status}
        - Score: {score}
        - Next action: {next_action}

        ## Required Evidence
        - Requirement package
        - Solution package
        - Patch summary
        - Verification report
        - Code review
        - Deployment report when a deployment command is supplied
        - Git publish report when a git publish command is supplied
        - Pipeline state
        """
    )


def render_writeback_report(project_key: str, status: str, next_action: str) -> str:
    return dedent(
        f"""
        # Writeback Report

        ## Project
        - Project key: {project_key}
        - Pipeline status: {status}
        - Next action: {next_action}

        ## Memory Contract
        The runner can execute project memory writeback when `--write-project-memory`
        or `--memory-write-command` is supplied. Otherwise this report is a
        recommendation and live completion remains blocked.

        ## Suggested Command
        python scripts/openclaw-ops/project_memory_writer.py --project-key {project_key} --artifact-type changelog --content-file <writeback_report.md> --source project-delivery-pipeline
        """
    )


def repo_root_from_runner() -> Path:
    return Path(__file__).resolve().parents[4]


def find_project_memory_writer(runtime: dict[str, Any]) -> Path | None:
    runtime_home = str(runtime.get("runtime_home", "") or "").strip()
    candidates = [
        repo_root_from_runner() / "scripts" / "openclaw-ops" / "project_memory_writer.py",
    ]
    if runtime_home:
        candidates.append(Path(runtime_home).expanduser() / "ops" / "project_memory_writer.py")
    candidates.append(Path("scripts/openclaw-ops/project_memory_writer.py").resolve())
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def run_builtin_project_memory_writeback(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    writeback_file: Path,
) -> dict[str, Any]:
    writer = find_project_memory_writer(runtime)
    if writer is None:
        return {
            "ok": False,
            "returncode": 2,
            "stage": "memory_writeback",
            "command": "project_memory_writer.py",
            "stdout": "",
            "stderr": "project_memory_writer.py not found in repo or runtime ops",
        }
    cmd = [
        sys.executable,
        str(writer),
        "--data-dir",
        str(config.project_memory_root),
        "--project-key",
        config.project_key,
        "--artifact-type",
        "changelog",
        "--content-file",
        str(writeback_file),
        "--source",
        f"project-delivery:{run_dir.name}",
    ]
    started_at = utc_now()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(config.command_cwd.expanduser().resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(config.command_timeout_seconds or 600)),
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = int(proc.returncode)
        timed_out = False
        error = ""
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        returncode = 124
        timed_out = True
        error = f"timeout after {config.command_timeout_seconds}s"
    return {
        "stage": "memory_writeback",
        "index": 1,
        "command": " ".join(cmd),
        "cwd": str(config.command_cwd.expanduser().resolve()),
        "started_at": started_at,
        "ended_at": utc_now(),
        "returncode": returncode,
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "stdout": clip_text(stdout),
        "stderr": clip_text(stderr),
    }


def write_memory_command_report(
    run_dir: Path,
    artifacts: dict[str, str],
    report: dict[str, Any],
) -> Path:
    report_file = run_dir / "command-runs" / "memory_writeback-1.json"
    write_json(report_file, report)
    artifacts["command_memory_writeback_1"] = str(report_file)
    return report_file


def render_memory_writeback_report(reports: list[dict[str, Any]]) -> str:
    return dedent(
        f"""
        # Memory Writeback Evidence

        ## Result
        - Status: {"pass" if commands_ok(reports) else "fail"}
        - Commands: {len(reports)}

        {command_markdown("Memory Writeback Commands", reports)}
        """
    )


def failure_learning_payload(
    config: PipelineConfig,
    run_id: str,
    status: str,
    failed_stage: str | None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "triggered": status != "completed",
        "failed_stage": failed_stage,
        "next_action": next_action,
        "failure_tracker_contract": {
            "command": (
                "python scripts/openclaw-ops/failure_tracker.py record "
                f"--task-id {run_id} --task-type project_delivery_pipeline "
                "--model coordinator "
                f"--project-key {config.project_key} "
                "--failure-reason <reason>"
            )
        },
        "timestamp": utc_now(),
    }


def pipeline_state(
    config: PipelineConfig,
    run_id: str,
    run_dir: Path,
    runtime: dict[str, Any],
    stages: list[StageRecord],
    artifacts: dict[str, str],
    status: str,
    next_action: str,
    failed_stage: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "status": status,
        "next_action": next_action,
        "failed_stage": failed_stage,
        "dry_run": config.dry_run,
        "runtime_context": runtime,
        "run_dir": str(run_dir),
        "artifacts": artifacts,
        "stage_agents": {
            stage.name: stage_agent_ids(stage.name, config)
            for stage in stages
        },
        "stages": [stage.as_dict() for stage in stages],
        "updated_at": utc_now(),
    }


def policy_dir_candidates() -> list[Path]:
    current = Path(__file__).resolve()
    return [
        current.parent / "policy",
        current.parents[2] / "control-plane-ops" / "scripts" / "policy",
    ]


def policy_dir() -> Path:
    candidates = policy_dir_candidates()
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def load_task_center_classes() -> tuple[Any, Any]:
    path = policy_dir()
    if not path.exists():
        candidates = ", ".join(str(candidate) for candidate in policy_dir_candidates())
        raise PipelineError(f"task-center policy dir not found: {path}; checked: {candidates}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        from task_center import TaskCenter, TaskCenterError  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive import boundary
        raise PipelineError(f"failed to load task-center integration: {exc}") from exc
    return TaskCenter, TaskCenterError


def task_center_db_path(config: PipelineConfig) -> Path:
    if config.task_center_db is not None:
        return config.task_center_db.expanduser()
    return config.workspace_root.parent / "task-center" / "task_center.db"


def task_center_task_id(config: PipelineConfig, run_id: str) -> str:
    return config.task_center_task_id or f"project-delivery:{run_id}"


TASK_CENTER_UPDATE_FIELDS = {
    "task_type",
    "reason",
    "source",
    "request_source",
    "trace_id",
    "attempt_id",
    "priority",
    "risk_level",
    "assignee",
    "status",
    "retry_count",
    "failure_count",
    "need_human_confirm",
    "human_confirmed",
    "needs_clarification",
    "clarification_reason",
    "context_completeness",
    "context_fields_missing",
    "context_fields_recommended_missing",
    "context_payload",
    "review_status",
    "review_mode",
    "review_head",
    "reviewed_at",
    "owner",
    "change_id",
    "requirement",
    "result_output",
    "acceptance",
    "observable_outputs",
    "acceptance_thresholds",
    "stage_id",
    "stage_score_gate",
    "stage_min_evidence_count",
    "stage_output_contract",
    "stage_verification_contract",
    "required_capabilities",
    "required_skills",
    "allowed_agents",
    "workflow_profile_id",
    "workflow_channel",
    "selection_reason",
    "selection_inputs",
    "score_raw",
    "score_normalized",
    "score_payload",
    "token_usage_summary",
    "cost_estimate_total",
    "action",
    "scheduled_at",
    "started_at",
    "completed_at",
}


def stage_output_ref(run_dir: Path, stage: dict[str, Any]) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    path = Path(artifact)
    if path.is_absolute():
        return str(path)
    return str(run_dir / artifact)


def stage_command_execution_details(state: dict[str, Any], stage_name: str) -> dict[str, Any]:
    artifacts = state.get("artifacts", {})
    command_refs = {
        key: value
        for key, value in artifacts.items()
        if str(key).startswith(f"command_{stage_name}_")
    }
    reports: list[dict[str, Any]] = []
    for ref in command_refs.values():
        path = Path(str(ref))
        if not path.exists():
            continue
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    agent_workspaces: list[dict[str, Any]] = []
    for report in reports:
        for workspace in report.get("agent_workspaces", []) or []:
            if isinstance(workspace, dict):
                agent_workspaces.append(workspace)
    return {
        "command_run_refs": command_refs,
        "dispatch_mode": reports[0].get("dispatch_mode") if reports else "state-machine",
        "agent_id": reports[0].get("agent_id") if reports else STAGE_AGENT_MAP.get(stage_name, "coordinator"),
        "agent_workspaces": agent_workspaces,
        "workspace_patch_files": [
            report.get("workspace_patch_file")
            for report in reports
            if report.get("workspace_patch_file")
        ],
    }


def mirror_state_to_task_center(config: PipelineConfig, state: dict[str, Any], requirement: str) -> dict[str, Any] | None:
    if not config.record_task_center:
        return None

    TaskCenter, TaskCenterError = load_task_center_classes()
    db_path = task_center_db_path(config)
    task_id = task_center_task_id(config, str(state["run_id"]))
    status = "passed" if state["status"] == "completed" else "failed"
    action = "complete" if status == "passed" else str(state.get("next_action", ""))
    run_dir = Path(str(state["run_dir"]))
    memory_dir = project_memory_dir(config)
    stage_names = [str(item.get("name", "")) for item in state.get("stages", []) if item.get("name")]
    context_payload = {
        "pipeline_state": state,
        "run_dir": str(run_dir),
        "project_memory_dir": str(memory_dir),
        "stage_names": stage_names,
    }

    task_payload = {
        "task_id": task_id,
        "pool": "jobs",
        "task_type": "project_delivery_pipeline",
        "reason": f"{config.project_key}: {requirement[:180]}",
        "source": str(state.get("runtime_context", {}).get("host", "project-delivery-pipeline")),
        "request_source": "human",
        "priority": "medium",
        "risk_level": "low",
        "assignee": "coordinator",
        "status": status,
        "requirement": requirement,
        "result_output": f"Pipeline {state['status']} at {state['run_dir']}",
        "acceptance": "delivery_evidence.md and pipeline_state.json must show pass",
        "observable_outputs": ",".join(sorted(str(key) for key in state.get("artifacts", {}).keys())),
        "requirements_discussion_agents": "project-agent,reviewer",
        "acceptance_thresholds": (
            "requirements_review=ready_for_solution,"
            "solution_review=ready_for_implement,verification=pass,code_review=pass,"
            "acceptance=pass,git_publish=pass_when_supplied"
        ),
        "required_capabilities": "project_memory_retrieval,external_research,coding,verification,code_review,git_publish",
        "required_skills": "project-delivery-pipeline",
        "allowed_agents": "coordinator,project-agent,web-agent,reviewer,backend-dev,frontend-dev,tester,deployer,doc-writer",
        "workflow_profile_id": "project-delivery-pipeline@stable",
        "workflow_channel": "stable",
        "selection_reason": "single controlled coding delivery pipeline",
        "selection_inputs": {
            "run_id": state["run_id"],
            "runtime_context": state.get("runtime_context", {}),
            "project_memory_dir": str(memory_dir),
        },
        "context_payload": context_payload,
        "score_raw": 100 if status == "passed" else 0,
        "score_normalized": 100 if status == "passed" else 0,
        "score_payload": {
            "status": state["status"],
            "next_action": state.get("next_action", ""),
            "failed_stage": state.get("failed_stage"),
        },
        "action": action,
        "started_at": state.get("updated_at", utc_now()),
        "completed_at": utc_now(),
    }

    task_center = TaskCenter(db_path)
    try:
        task_center.init_schema()
        try:
            task_center.get_task(task_id, display_safe=False)
        except TaskCenterError:
            task_center.create_task(task_payload, actor="project-delivery-pipeline")
        else:
            update_fields = {key: value for key, value in task_payload.items() if key in TASK_CENTER_UPDATE_FIELDS}
            task_center.update_task(task_id, actor="project-delivery-pipeline", fields=update_fields)

        for stage in state.get("stages", []):
            stage_name = str(stage.get("name", "")).strip()
            if not stage_name:
                continue
            agent_id = STAGE_AGENT_MAP.get(stage_name, "coordinator")
            output_ref = stage_output_ref(run_dir, stage)
            execution_details = stage_command_execution_details(state, stage_name)
            model_id = (
                "runtime-agent-workspace"
                if execution_details.get("command_run_refs")
                else "state-machine"
            )
            task_center.start_stage_run(
                task_id=task_id,
                stage=stage_name,
                agent_id=agent_id,
                model_id=model_id,
                input_ref=str(run_dir / "run_meta.json"),
                details={"pipeline_stage": stage, "agent_execution": execution_details},
            )
            stage_status = "passed" if str(stage.get("status")) == "completed" else "failed"
            task_center.finish_stage_run(
                task_id=task_id,
                stage=stage_name,
                status=stage_status,
                exit_code=0 if stage_status == "passed" else 1,
                error_reason=str(stage.get("detail", "")),
                output_ref=output_ref,
                details={
                    "verdict": stage.get("verdict"),
                    "score": stage.get("score"),
                    "next_action": stage.get("next_action"),
                    "agent_execution": execution_details,
                },
            )
            handoff_agents = [part.strip() for part in str(agent_id).split(",") if part.strip()] or ["coordinator"]
            for handoff_agent in handoff_agents:
                task_center.record_module_communication(
                    task_id=task_id,
                    from_module="coordinator",
                    to_module=handoff_agent,
                    protocol="project-delivery-pipeline",
                    message_type="stage_handoff",
                    status="acked" if stage_status == "passed" else "failed",
                    payload_ref=output_ref,
                    details={
                        "stage": stage_name,
                        "run_id": state["run_id"],
                        "agent_execution": execution_details,
                    },
                    actor="project-delivery-pipeline",
                )

        task_center.record_task_output(
            task_id=task_id,
            output_type="pipeline_state",
            audience="human",
            channel="task-center",
            status="prepared",
            summary=f"Project delivery pipeline {state['status']}; next_action={state.get('next_action', '')}",
            payload={
                "run_id": state["run_id"],
                "run_dir": state["run_dir"],
                "status": state["status"],
                "next_action": state.get("next_action", ""),
                "failed_stage": state.get("failed_stage"),
                "project_memory_dir": str(memory_dir),
                "artifacts": state.get("artifacts", {}),
            },
            actor="project-delivery-pipeline",
        )
        if state["status"] != "completed":
            task_center.record_task_incident(
                task_id=task_id,
                incident_type="pipeline_blocked",
                severity="warning",
                status="open",
                reason=str(state.get("failed_stage", "")),
                summary=f"Pipeline blocked; next_action={state.get('next_action', '')}",
                owner="coordinator",
                details={
                    "run_id": state["run_id"],
                    "failed_stage": state.get("failed_stage"),
                    "next_action": state.get("next_action"),
                },
                actor="project-delivery-pipeline",
            )
    except TaskCenterError as exc:
        raise PipelineError(f"failed to mirror pipeline run to task center: {exc}") from exc
    finally:
        task_center.close()

    return {
        "db": str(db_path),
        "task_id": task_id,
        "status": status,
    }


def finalize_pipeline_state(config: PipelineConfig, state: dict[str, Any], requirement: str) -> dict[str, Any]:
    task_center_ref = mirror_state_to_task_center(config, state, requirement)
    if task_center_ref:
        state["task_center"] = task_center_ref
        write_json(Path(str(state["run_dir"])) / "pipeline_state.json", state)
    return state


def block_pipeline(
    config: PipelineConfig,
    run_id: str,
    run_dir: Path,
    runtime: dict[str, Any],
    stages: list[StageRecord],
    artifacts: dict[str, str],
    stage_name: str,
    next_action: str,
    detail: str,
    artifact: str | None = None,
    verdict: str | None = None,
    score: int | None = None,
) -> dict[str, Any]:
    stages.append(
        StageRecord(
            name=stage_name,
            status="blocked",
            artifact=artifact,
            verdict=verdict,
            score=score,
            next_action=next_action,
            detail=detail,
        )
    )
    failure_path = run_dir / "failure_learning_check.json"
    write_json(failure_path, failure_learning_payload(config, run_id, "blocked", stage_name, next_action))
    artifacts["failure_learning_check"] = str(failure_path)
    state = pipeline_state(config, run_id, run_dir, runtime, stages, artifacts, "blocked", next_action, stage_name)
    write_json(run_dir / "pipeline_state.json", state)
    return state


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    if config.simulate_failure_stage and config.simulate_failure_stage not in SIMULATED_FAILURES:
        raise PipelineError(f"unsupported simulated failure: {config.simulate_failure_stage}")

    requirement = load_requirement(config)
    run_id = config.run_id or default_run_id(config.project_key)
    run_dir = config.workspace_root / run_id
    if run_dir.exists() and any(run_dir.iterdir()) and not config.force:
        raise PipelineError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    runtime = resolve_runtime_context(config)
    stages: list[StageRecord] = []
    artifacts: dict[str, str] = {}

    def write_progress_state(stage_name: str | None = None, detail: str = "") -> None:
        snapshot_stages = list(stages)
        if stage_name:
            snapshot_stages.append(
                StageRecord(
                    name=stage_name,
                    status="running",
                    next_action="continue",
                    detail=detail,
                )
            )
        state = pipeline_state(config, run_id, run_dir, runtime, snapshot_stages, artifacts, "running", "continue")
        write_json(run_dir / "pipeline_state.json", state)

    def record(name: str, file_name: str, content: str, **extra: Any) -> Path:
        path = run_dir / file_name
        write_text(path, content)
        artifacts[name] = str(path)
        stages.append(StageRecord(name=name, status="completed", artifact=file_name, **extra))
        write_progress_state()
        return path

    def record_payload(name: str, file_name: str, payload: dict[str, Any]) -> Path:
        path = run_dir / file_name
        write_json(path, payload)
        artifacts[name] = str(path)
        write_progress_state()
        return path

    meta_path = run_dir / "run_meta.json"
    write_json(meta_path, render_run_meta(config, run_id, requirement, runtime))
    artifacts["run_meta"] = str(meta_path)
    stages.append(StageRecord(name="intake", status="completed", artifact="run_meta.json"))
    write_progress_state()

    record("context_snapshot", "context_snapshot.md", render_context_snapshot(requirement, runtime))
    record("project_memory_context", "project_memory_context.md", render_project_memory_context(config, requirement, runtime))
    research_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "external_research",
        config.research_commands,
        progress_callback=write_progress_state,
    ) if config.research_commands else []
    research_evidence_supplied = bool(
        config.dry_run
        or config.source_urls
        or config.research_report_file
        or research_command_reports
    )
    record(
        "external_research",
        "research_report.md",
        render_research_report(config, research_command_reports),
        verdict="pass" if research_evidence_supplied and (not research_command_reports or commands_ok(research_command_reports)) else "missing",
    )
    if not config.dry_run and (not research_evidence_supplied or (research_command_reports and not commands_ok(research_command_reports))):
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "external_research",
                "run_external_research",
                "live mode requires external research evidence before requirements review",
                "research_report.md",
                "fail",
            ),
            requirement,
        )
    record("requirements_package", "requirements.md", render_requirements(requirement))
    discussion_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "requirements_discussion",
        config.requirements_discussion_commands,
        progress_callback=write_progress_state,
    ) if config.requirements_discussion_commands else []
    discussion_evidence_supplied = bool(config.dry_run or discussion_command_reports)
    discussion_body = render_requirements_discussion(requirement)
    if discussion_command_reports:
        discussion_body = discussion_body.rstrip() + "\n\n" + command_markdown("Requirements Discussion Commands", discussion_command_reports)
    record(
        "requirements_discussion",
        "requirements_discussion.md",
        discussion_body,
        verdict="pass" if discussion_evidence_supplied and (not discussion_command_reports or commands_ok(discussion_command_reports)) else "missing",
    )
    if not config.dry_run and (not discussion_evidence_supplied or (discussion_command_reports and not commands_ok(discussion_command_reports))):
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "requirements_discussion",
                "run_dual_agent_requirements_discussion",
                "live mode requires successful project-agent/reviewer requirement discussion evidence before requirements review",
                "requirements_discussion.md",
                "fail",
            ),
            requirement,
        )

    req_review_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "requirements_review",
        config.requirements_review_commands,
        progress_callback=write_progress_state,
    ) if config.requirements_review_commands else []
    req_verdict = "requires_revision" if config.simulate_failure_stage == "requirements" else "ready_for_solution"
    if req_review_reports:
        req_verdict = "ready_for_solution" if dual_review_pass("requirements_review", req_review_reports) else "requires_revision"
    elif not config.dry_run:
        req_verdict = "requires_revision"
    req_review = record(
        "requirements_review",
        "requirements_review.md",
        render_dual_ai_review("requirements_review", req_review_reports, req_verdict)
        if req_review_reports or not config.dry_run
        else consensus_review("requirements_review", req_verdict, requirement),
        verdict=req_verdict,
    )
    gate_ok, parsed_verdict = gate_result("requirements_review", req_review)
    if not gate_ok:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "requirements_review",
                "revise_requirements",
                "requirements review did not allow solution design",
                "requirements_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    resolved_requirement = record(
        "resolved_requirement",
        "resolved_requirement.md",
        render_resolved_requirement(requirement, artifacts),
        verdict="pass",
    )

    delivery_plan = compile_delivery_plan(
        config,
        runtime,
        resolved_requirement.read_text(encoding="utf-8"),
        artifacts,
    )
    record_payload("delivery_plan", "delivery_plan.json", delivery_plan)
    record("solution_package", "solution.md", render_solution(delivery_plan))
    sol_review_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "solution_review",
        config.solution_review_commands,
        progress_callback=write_progress_state,
    ) if config.solution_review_commands else []
    sol_verdict = "requires_revision" if config.simulate_failure_stage == "solution" else "ready_for_implement"
    if sol_review_reports:
        sol_verdict = "ready_for_implement" if dual_review_pass("solution_review", sol_review_reports) else "requires_revision"
    elif not config.dry_run:
        sol_verdict = "requires_revision"
    sol_review = record(
        "solution_review",
        "solution_review.md",
        render_dual_ai_review("solution_review", sol_review_reports, sol_verdict)
        if sol_review_reports or not config.dry_run
        else consensus_review("solution_review", sol_verdict, requirement),
        verdict=sol_verdict,
    )
    gate_ok, parsed_verdict = gate_result("solution_review", sol_review)
    if not gate_ok:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "solution_review",
                "revise_solution",
                "solution review did not allow implementation",
                "solution_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    code_command_report = None
    code_workspace_patch_file: Path | None = None
    if config.code_command:
        code_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "code_execution",
            config.code_command,
            progress_callback=write_progress_state,
        )
        if code_command_report.get("workspace_patch_file"):
            candidate = Path(str(code_command_report["workspace_patch_file"]))
            if candidate.exists() and candidate.stat().st_size > 0:
                code_workspace_patch_file = candidate
    if code_command_report and not code_command_report.get("ok"):
        record("code_execution", "patch_summary.md", render_patch_summary(config, code_command_report), verdict="fail")
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_execution",
                "return_to_code_execution",
                "coding command failed and must be repaired by implementation agent",
                "patch_summary.md",
                "fail",
            ),
            requirement,
        )

    if not config.dry_run and config.patch_summary_file is None and code_command_report is None:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_execution",
                "dispatch_code_agent",
                "live mode requires a coding agent patch summary artifact",
            ),
            requirement,
        )
    record("code_execution", "patch_summary.md", render_patch_summary(config, code_command_report))

    verification_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "verification",
        config.verification_commands,
        code_workspace_patch_file,
        progress_callback=write_progress_state,
    ) if config.verification_commands else []
    missing_live_verification = (
        not config.dry_run
        and not config.verification_report_file
        and not verification_command_reports
    )
    verification_failed = (
        config.simulate_failure_stage == "verification"
        or missing_live_verification
        or (bool(verification_command_reports) and not commands_ok(verification_command_reports))
    )
    verification_content = render_verification_report(config, verification_failed, verification_command_reports)
    verification_score = 55 if verification_failed else 100
    record(
        "verification",
        "verification_report.md",
        verification_content,
        score=verification_score,
        verdict="fail" if verification_failed else "pass",
    )
    if verification_failed:
        rollback_report = rollback_applied_code_patch(
            config,
            run_dir,
            artifacts,
            code_workspace_patch_file,
            "verification_failed",
        )
        if rollback_failed(rollback_report):
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "rollback_cleanup",
                    "manual_cleanup_required",
                    rollback_failure_detail(rollback_report),
                    Path(str(rollback_report.get("report_file") or "")).name or None,
                    "fail",
                    20,
                ),
                requirement,
            )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "verification",
                "return_to_code_execution",
                "verification failed or live verification evidence is missing",
                "verification_report.md",
                "fail",
                verification_score,
            ),
            requirement,
        )

    code_review_commands = config.code_review_commands or (
        (config.code_review_command,) if config.code_review_command else ()
    )
    code_review_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "code_review",
        code_review_commands,
        input_patch_file=code_workspace_patch_file,
        progress_callback=write_progress_state,
    ) if code_review_commands else []
    missing_live_code_review = (
        not config.dry_run
        and not config.code_review_file
        and not code_review_command_reports
    )
    code_review_failed = (
        config.simulate_failure_stage == "code_review"
        or missing_live_code_review
        or (bool(code_review_command_reports) and not dual_review_pass("code_review", code_review_command_reports))
    )
    code_review = record(
        "code_review",
        "code_review.md",
        render_code_review(config, code_review_failed, code_review_command_reports),
        verdict="requires_revision" if code_review_failed else "pass",
    )
    gate_ok, parsed_verdict = gate_result("code_review", code_review)
    if not gate_ok:
        rollback_report = rollback_applied_code_patch(
            config,
            run_dir,
            artifacts,
            code_workspace_patch_file,
            "code_review_failed",
        )
        if rollback_failed(rollback_report):
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "rollback_cleanup",
                    "manual_cleanup_required",
                    rollback_failure_detail(rollback_report),
                    Path(str(rollback_report.get("report_file") or "")).name or None,
                    "fail",
                    20,
                ),
                requirement,
            )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_review",
                "return_to_code_execution",
                "code review failed and must be fixed by implementation agent",
                "code_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    deployment_command_report = None
    if config.deployment_command:
        deployment_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "deployment",
            config.deployment_command,
            input_patch_file=code_workspace_patch_file,
            progress_callback=write_progress_state,
        )
        deployment_failed = not deployment_command_report.get("ok")
        record(
            "deployment",
            "deployment_report.md",
            render_deployment_report(deployment_command_report),
            verdict="fail" if deployment_failed else "pass",
        )
        if deployment_failed:
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "deployment",
                    "return_to_deployment",
                    "deployment command failed and must be repaired by deployer",
                    "deployment_report.md",
                    "fail",
                ),
                requirement,
            )

    if config.simulate_failure_stage == "acceptance_requirement":
        acceptance_path = record(
            "acceptance",
            "delivery_evidence.md",
            render_delivery_evidence(60, "fail", "revise_requirements"),
            score=60,
            verdict="fail",
        )
        artifacts["delivery_evidence"] = str(acceptance_path)
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "acceptance",
                "revise_requirements",
                "acceptance failed because the requirement package is wrong",
                "delivery_evidence.md",
                "fail",
                60,
            ),
            requirement,
        )

    if config.simulate_failure_stage == "acceptance_implementation":
        acceptance_path = record(
            "acceptance",
            "delivery_evidence.md",
            render_delivery_evidence(65, "fail", "return_to_code_execution"),
            score=65,
            verdict="fail",
        )
        artifacts["delivery_evidence"] = str(acceptance_path)
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "acceptance",
                "return_to_code_execution",
                "acceptance failed because implementation evidence is insufficient",
                "delivery_evidence.md",
                "fail",
                65,
            ),
            requirement,
        )

    acceptance_path = record(
        "acceptance",
        "delivery_evidence.md",
        render_delivery_evidence(100, "pass", "writeback"),
        score=100,
        verdict="pass",
    )
    artifacts["delivery_evidence"] = str(acceptance_path)
    writeback_path = record("writeback", "writeback_report.md", render_writeback_report(config.project_key, "completed", "none"))
    memory_reports: list[dict[str, Any]] = []
    if config.memory_write_command:
        memory_reports.append(
            run_stage_command(
                config,
                run_dir,
                runtime,
                artifacts,
                requirement,
                "memory_writeback",
                config.memory_write_command,
                input_patch_file=code_workspace_patch_file,
                progress_callback=write_progress_state,
            )
        )
    elif config.write_project_memory:
        builtin_report = run_builtin_project_memory_writeback(config, run_dir, runtime, writeback_path)
        write_memory_command_report(run_dir, artifacts, builtin_report)
        memory_reports.append(builtin_report)

    missing_live_memory_writeback = (
        not config.dry_run
        and not config.write_project_memory
        and not config.memory_write_command
    )
    if memory_reports:
        memory_report_path = run_dir / "memory_writeback_report.md"
        write_text(memory_report_path, render_memory_writeback_report(memory_reports))
        artifacts["memory_writeback"] = str(memory_report_path)
    if missing_live_memory_writeback or (memory_reports and not commands_ok(memory_reports)):
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "writeback",
                "fix_memory_writeback",
                "live mode requires successful project memory writeback",
                "writeback_report.md",
                "fail",
                70,
            ),
            requirement,
        )

    if config.git_publish_command:
        git_publish_input_patch_file: Path | None = None
        git_publish_input_patch_report: dict[str, Any] = {
            "ok": True,
            "source": "none",
            "patch_file": "",
            "has_changes": False,
        }
        for memory_report in reversed(memory_reports):
            candidate_text = str(memory_report.get("workspace_patch_file") or "")
            candidate = Path(candidate_text) if candidate_text else None
            if candidate is not None and candidate.exists() and candidate.stat().st_size > 0:
                git_publish_input_patch_file = candidate
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "memory_writeback_workspace_patch",
                    "patch_file": str(candidate),
                    "has_changes": True,
                }
                break
        if git_publish_input_patch_file is None:
            if code_workspace_patch_file is not None and code_workspace_patch_file.exists():
                git_publish_input_patch_file = code_workspace_patch_file
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "code_execution_workspace_patch",
                    "patch_file": str(code_workspace_patch_file),
                    "has_changes": code_workspace_patch_file.stat().st_size > 0,
                }
            else:
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "no_accepted_patch",
                    "patch_file": "",
                    "has_changes": False,
                }
        git_publish_input_patch_report_path = run_dir / "command-runs" / "git_publish-input-patch.json"
        write_json(git_publish_input_patch_report_path, git_publish_input_patch_report)
        artifacts["git_publish_input_patch_report"] = str(git_publish_input_patch_report_path)
        if git_publish_input_patch_file:
            artifacts["git_publish_input_patch"] = str(git_publish_input_patch_file)
        git_publish_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "git_publish",
            config.git_publish_command,
            input_patch_file=git_publish_input_patch_file,
            progress_callback=write_progress_state,
        )
        git_publish_report["input_patch"] = git_publish_input_patch_report
        git_publish_command_report_path = artifacts.get("command_git_publish_1")
        if git_publish_command_report_path:
            write_json(Path(git_publish_command_report_path), git_publish_report)
        git_publish_failed = not git_publish_report.get("ok")
        record(
            "git_publish",
            "git_publish_report.md",
            render_git_publish_report(git_publish_report),
            verdict="fail" if git_publish_failed else "pass",
        )
        if git_publish_failed:
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "git_publish",
                    "fix_git_publish",
                    "git publish command failed and requires human-safe repair",
                    "git_publish_report.md",
                    "fail",
                    70,
                ),
                requirement,
            )
    elif config.simulate_failure_stage == "git_publish":
        record(
            "git_publish",
            "git_publish_report.md",
            "# Git Publish Report\n\nFinal verdict: fail\n\nNo git publish command was supplied.",
            verdict="fail",
        )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "git_publish",
                "fix_git_publish",
                "simulated git publish failure",
                "git_publish_report.md",
                "fail",
                70,
            ),
            requirement,
        )

    failure_path = run_dir / "failure_learning_check.json"
    write_json(failure_path, failure_learning_payload(config, run_id, "completed", None, "none"))
    artifacts["failure_learning_check"] = str(failure_path)

    state = pipeline_state(config, run_id, run_dir, runtime, stages, artifacts, "completed", "none")
    write_json(run_dir / "pipeline_state.json", state)
    return finalize_pipeline_state(config, state, requirement)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the project delivery pipeline state machine")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--requirement")
    parser.add_argument("--requirement-file", type=Path)
    parser.add_argument("--runtime-host", default="generic")
    parser.add_argument("--runtime-home")
    parser.add_argument("--workspace-root", type=Path, default=Path(".workflow/pipeline-runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--simulate-failure-stage", choices=sorted(SIMULATED_FAILURES))
    parser.add_argument("--max-repair-loops", type=int, default=2)
    parser.add_argument("--research-report-file", type=Path)
    parser.add_argument("--research-command", action="append", default=[], help="trusted command that produces research evidence")
    parser.add_argument("--requirements-discussion-command", action="append", default=[], help="trusted command that makes project-agent and reviewer discuss/refine requirements")
    parser.add_argument("--requirements-review-command", action="append", default=[], help="trusted independent reviewer command for requirements gate; supply at least two")
    parser.add_argument("--solution-review-command", action="append", default=[], help="trusted independent reviewer command for solution gate; supply at least two")
    parser.add_argument("--code-agent", choices=["backend-dev", "frontend-dev"], default="backend-dev", help="workflow owner for code_execution")
    parser.add_argument("--code-command", help="trusted runtime/agent command that performs or dispatches implementation")
    parser.add_argument("--patch-summary-file", type=Path)
    parser.add_argument("--verification-command", action="append", default=[], help="trusted command used as verification evidence")
    parser.add_argument("--verification-report-file", type=Path)
    parser.add_argument("--code-review-command", action="append", default=[], help="trusted independent reviewer command that produces code review output; supply at least two")
    parser.add_argument("--code-review-file", type=Path)
    parser.add_argument("--deployment-command", help="trusted command that deploys an accepted implementation")
    parser.add_argument("--memory-write-command", help="trusted command that writes project memory after acceptance")
    parser.add_argument("--git-publish-command", help="trusted command that commits and pushes accepted changes after writeback")
    parser.add_argument("--write-project-memory", action="store_true", help="call project_memory_writer.py for accepted runs")
    parser.add_argument("--command-cwd", type=Path, default=Path("."))
    parser.add_argument("--agent-workspace-root", type=Path, help="root for per-run agent workspaces")
    parser.add_argument("--command-timeout-seconds", type=int, default=600)
    parser.add_argument("--project-memory-root", type=Path, default=Path(".workflow/project-memory"))
    parser.add_argument("--record-task-center", action="store_true")
    parser.add_argument("--task-center-db", type=Path)
    parser.add_argument("--task-center-task-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        project_key=args.project_key,
        requirement=args.requirement,
        requirement_file=args.requirement_file,
        runtime_host=args.runtime_host,
        runtime_home=args.runtime_home,
        workspace_root=args.workspace_root,
        run_id=args.run_id,
        source_urls=tuple(args.source_url or ()),
        dry_run=args.dry_run,
        simulate_failure_stage=args.simulate_failure_stage,
        max_repair_loops=args.max_repair_loops,
        research_report_file=args.research_report_file,
        research_commands=tuple(args.research_command or ()),
        requirements_discussion_commands=tuple(args.requirements_discussion_command or ()),
        requirements_review_commands=tuple(args.requirements_review_command or ()),
        solution_review_commands=tuple(args.solution_review_command or ()),
        code_agent=normalize_code_agent(args.code_agent),
        code_command=args.code_command,
        patch_summary_file=args.patch_summary_file,
        verification_commands=tuple(args.verification_command or ()),
        verification_report_file=args.verification_report_file,
        code_review_commands=tuple(args.code_review_command or ()),
        code_review_file=args.code_review_file,
        deployment_command=args.deployment_command,
        memory_write_command=args.memory_write_command,
        git_publish_command=args.git_publish_command,
        write_project_memory=bool(args.write_project_memory),
        command_cwd=args.command_cwd,
        agent_workspace_root=args.agent_workspace_root,
        command_timeout_seconds=args.command_timeout_seconds,
        project_memory_root=args.project_memory_root,
        record_task_center=args.record_task_center,
        task_center_db=args.task_center_db,
        task_center_task_id=args.task_center_task_id,
        force=args.force,
    )


def build_view_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View a project delivery pipeline run")
    parser.add_argument("--workspace-root", type=Path, default=Path(".workflow/pipeline-runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--task-center-db", type=Path)
    parser.add_argument("--task-id")
    parser.add_argument("--event-limit", type=int, default=100)
    parser.add_argument("--emit-json", action="store_true")
    return parser


def load_pipeline_state(workspace_root: Path, run_id: str | None) -> dict[str, Any]:
    if run_id:
        state_file = workspace_root / run_id / "pipeline_state.json"
    else:
        candidates = sorted(workspace_root.glob("*/pipeline_state.json"), key=lambda item: item.stat().st_mtime)
        if not candidates:
            raise PipelineError(f"no pipeline_state.json found under {workspace_root}")
        state_file = candidates[-1]
    if not state_file.exists():
        raise PipelineError(f"pipeline state not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8"))


def load_task_center_report(db_path: Path | None, task_id: str | None, event_limit: int) -> dict[str, Any] | None:
    if db_path is None or not task_id:
        return None
    TaskCenter, TaskCenterError = load_task_center_classes()
    task_center = TaskCenter(db_path.expanduser())
    try:
        task_center.init_schema()
        return task_center.task_report(task_id, event_limit=max(20, int(event_limit or 100)), display_safe=False)
    except TaskCenterError as exc:
        raise PipelineError(f"failed to load task-center report: {exc}") from exc
    finally:
        task_center.close()


def build_view_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_id or args.workspace_root.exists():
        state = load_pipeline_state(args.workspace_root, args.run_id)
    elif args.task_center_db and args.task_id:
        state = {}
    else:
        raise PipelineError(f"workspace root not found: {args.workspace_root}")
    task_id = str(args.task_id or state.get("task_center", {}).get("task_id", "")).strip()
    db_raw = args.task_center_db or state.get("task_center", {}).get("db")
    db_path = Path(db_raw).expanduser() if db_raw else None
    task_report = load_task_center_report(db_path, task_id, args.event_limit) if task_id and db_path else None
    return {
        "state": state,
        "task_center_report": task_report,
        "summary": {
            "run_id": state.get("run_id", ""),
            "project_key": state.get("project_key", ""),
            "status": state.get("status", ""),
            "next_action": state.get("next_action", ""),
            "failed_stage": state.get("failed_stage", ""),
            "run_dir": state.get("run_dir", ""),
            "task_center_db": str(db_path) if db_path else "",
            "task_id": task_id,
            "stage_count": len(state.get("stages", [])),
            "artifact_count": len(state.get("artifacts", {})),
            "open_incident_count": (
                task_report.get("control_plane", {}).get("open_incident_count", 0) if task_report else 0
            ),
        },
    }


def render_view_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    state = payload.get("state", {})
    lines = [
        f"Pipeline {summary.get('status', '-')}: {summary.get('run_id', '-')}",
        f"- project: {summary.get('project_key', '-')}",
        f"- next_action: {summary.get('next_action', '-')}",
        f"- failed_stage: {summary.get('failed_stage') or 'none'}",
        f"- run_dir: {summary.get('run_dir', '-')}",
        f"- task_center: {summary.get('task_id') or 'not recorded'}",
        f"- open_incidents: {summary.get('open_incident_count', 0)}",
    ]
    artifacts = state.get("artifacts", {})
    if artifacts:
        lines.append("- key artifacts:")
        for key in (
            "project_memory_context",
            "requirements_package",
            "requirements_discussion",
            "delivery_plan",
            "solution_package",
            "verification",
            "code_review",
            "acceptance",
            "git_publish",
        ):
            if key in artifacts:
                lines.append(f"  {key}: {artifacts[key]}")
    return "\n".join(lines)


def run_view(argv: list[str]) -> int:
    parser = build_view_arg_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_view_payload(args)
    except PipelineError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_view_text(payload))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["view"]:
        return run_view(argv[1:])
    if argv[:1] == ["run"]:
        argv = argv[1:]
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        state = run_pipeline(config_from_args(args))
    except PipelineError as exc:
        payload = {"status": "error", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(f"pipeline {state['status']}: {state['run_dir']}")
    return 0 if state["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

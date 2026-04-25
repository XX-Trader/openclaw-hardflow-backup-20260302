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
from typing import Any


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
    "acceptance": "tester",
    "writeback": "doc-writer",
}
SIMULATED_FAILURES = {
    "requirements",
    "solution",
    "verification",
    "code_review",
    "acceptance_requirement",
    "acceptance_implementation",
}
VERDICT_RE = re.compile(
    r"(?im)^\s*(?:Final verdict|final_verdict|verdict)\s*:\s*([a-z_]+)"
)


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
    code_command: str | None = None
    patch_summary_file: Path | None = None
    verification_commands: tuple[str, ...] = ()
    verification_report_file: Path | None = None
    code_review_command: str | None = None
    code_review_file: Path | None = None
    memory_write_command: str | None = None
    write_project_memory: bool = False
    command_cwd: Path = Path(".")
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug[:64] or "pipeline-run"


def default_run_id(project_key: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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
        Build an end-to-end coding delivery pipeline that can:
        - explore and refine requirements with multiple AI reviewers
        - retrieve project memory before selecting a change location
        - research external implementation options before coding
        - route coding work to implementation agents
        - run verification and code review gates
        - return implementation failures to coding agents
        - return requirement-caused failures to the requirement package
        - write final delivery evidence and memory updates

        ## Acceptance Criteria
        - Requirements review must return ready_for_solution.
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


def render_solution(runtime: dict[str, Any]) -> str:
    return dedent(
        f"""
        # Solution Package

        ## Architecture
        The pipeline is a deterministic state machine with runtime adapters.
        OpenClaw and Hermes are hosts, not separate workflow definitions.

        ## Runtime Adapter
        - Host: {runtime["host"]}
        - Runtime home: {runtime["runtime_home"]}
        - State dir: {runtime["state_dir"]}

        ## Stage Order
        1. intake
        2. context_snapshot
        3. project_memory_context
        4. external_research
        5. requirements_package
        6. requirements_discussion
        7. requirements_review
        8. solution_package
        9. solution_review
        10. code_execution
        11. verification
        12. code_review
        13. acceptance
        14. writeback

        ## Failure Routing
        - Requirement defects route to revise_requirements.
        - Solution defects route to revise_solution.
        - Implementation, verification, and code review defects route to return_to_code_execution.
        """
    )


def clip_text(value: str, limit: int = 12000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... truncated {len(text) - limit} chars ..."


def command_env(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    requirement: str,
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
            "PIPELINE_REQUIREMENTS_DISCUSSION_FILE": str(run_dir / "requirements_discussion.md"),
            "PIPELINE_PATCH_SUMMARY_FILE": str(run_dir / "patch_summary.md"),
            "PIPELINE_VERIFICATION_REPORT_FILE": str(run_dir / "verification_report.md"),
            "PIPELINE_CODE_REVIEW_FILE": str(run_dir / "code_review.md"),
            "PIPELINE_WRITEBACK_REPORT_FILE": str(run_dir / "writeback_report.md"),
        }
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
) -> dict[str, Any]:
    command_text = str(command or "").strip()
    if not command_text:
        raise PipelineError(f"{stage_name} command must not be empty")
    cwd = config.command_cwd.expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise PipelineError(f"command cwd not found: {cwd}")

    started_at = utc_now()
    stdout = ""
    stderr = ""
    returncode = 124
    timed_out = False
    error = ""
    try:
        proc = subprocess.run(
            command_text,
            shell=True,
            cwd=str(cwd),
            env=command_env(config, run_dir, runtime, requirement),
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

    report = {
        "stage": stage_name,
        "index": index,
        "command": command_text,
        "cwd": str(cwd),
        "started_at": started_at,
        "ended_at": utc_now(),
        "returncode": returncode,
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "stdout": clip_text(stdout),
        "stderr": clip_text(stderr),
    }
    report_dir = run_dir / "command-runs"
    report_file = report_dir / f"{stage_name}-{index}.json"
    write_json(report_file, report)
    artifacts[f"command_{stage_name}_{index}"] = str(report_file)
    return report


def run_stage_commands(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    artifacts: dict[str, str],
    requirement: str,
    stage_name: str,
    commands: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        run_stage_command(config, run_dir, runtime, artifacts, requirement, stage_name, command, index)
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

            {command_markdown("Coding Command", [command_report])}

            ## Handoff
            Runtime agent output above is treated as the implementation handoff.
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
    command_report: dict[str, Any] | None = None,
) -> str:
    if command_report is not None:
        stdout = str(command_report.get("stdout", "")).strip()
        if stdout:
            return stdout
        return dedent(
            f"""
            # Code Review

            Final verdict: {"pass" if command_report.get("ok") else "requires_revision"}
            Confidence: medium

            {command_markdown("Code Review Command", [command_report])}
            """
        )
    if config.code_review_file and not failed:
        return read_optional_file(config.code_review_file, "")
    verdict = "requires_revision" if failed else "pass"
    return consensus_review("code_review", verdict, "Implementation evidence is attached in patch_summary.md.")


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


def stage_output_ref(run_dir: Path, stage: dict[str, Any]) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    path = Path(artifact)
    if path.is_absolute():
        return str(path)
    return str(run_dir / artifact)


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
            "solution_review=ready_for_implement,verification=pass,code_review=pass,acceptance=pass"
        ),
        "required_capabilities": "project_memory_retrieval,external_research,coding,verification,code_review",
        "required_skills": "project-delivery-pipeline",
        "allowed_agents": "coordinator,project-agent,web-agent,backend-dev,frontend-dev,reviewer,tester,ops-agent,deployer,doc-writer",
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
            update_fields = {key: value for key, value in task_payload.items() if key != "task_id"}
            task_center.update_task(task_id, actor="project-delivery-pipeline", fields=update_fields)

        for stage in state.get("stages", []):
            stage_name = str(stage.get("name", "")).strip()
            if not stage_name:
                continue
            agent_id = STAGE_AGENT_MAP.get(stage_name, "coordinator")
            output_ref = stage_output_ref(run_dir, stage)
            task_center.start_stage_run(
                task_id=task_id,
                stage=stage_name,
                agent_id=agent_id,
                model_id="state-machine",
                input_ref=str(run_dir / "run_meta.json"),
                details={"pipeline_stage": stage},
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
                    details={"stage": stage_name, "run_id": state["run_id"]},
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

    def record(name: str, file_name: str, content: str, **extra: Any) -> Path:
        path = run_dir / file_name
        write_text(path, content)
        artifacts[name] = str(path)
        stages.append(StageRecord(name=name, status="completed", artifact=file_name, **extra))
        return path

    meta_path = run_dir / "run_meta.json"
    write_json(meta_path, render_run_meta(config, run_id, requirement, runtime))
    artifacts["run_meta"] = str(meta_path)
    stages.append(StageRecord(name="intake", status="completed", artifact="run_meta.json"))

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

    req_verdict = "requires_revision" if config.simulate_failure_stage == "requirements" else "ready_for_solution"
    req_review = record(
        "requirements_review",
        "requirements_review.md",
        consensus_review("requirements_review", req_verdict, requirement),
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

    record("solution_package", "solution.md", render_solution(runtime))
    sol_verdict = "requires_revision" if config.simulate_failure_stage == "solution" else "ready_for_implement"
    sol_review = record(
        "solution_review",
        "solution_review.md",
        consensus_review("solution_review", sol_verdict, requirement),
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
    if config.code_command:
        code_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "code_execution",
            config.code_command,
        )
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

    code_review_command_report = None
    if config.code_review_command:
        code_review_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "code_review",
            config.code_review_command,
        )
    missing_live_code_review = (
        not config.dry_run
        and not config.code_review_file
        and code_review_command_report is None
    )
    code_review_failed = (
        config.simulate_failure_stage == "code_review"
        or missing_live_code_review
        or (code_review_command_report is not None and not code_review_command_report.get("ok"))
    )
    code_review = record(
        "code_review",
        "code_review.md",
        render_code_review(config, code_review_failed, code_review_command_report),
        verdict="requires_revision" if code_review_failed else "pass",
    )
    gate_ok, parsed_verdict = gate_result("code_review", code_review)
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
                "code_review",
                "return_to_code_execution",
                "code review failed and must be fixed by implementation agent",
                "code_review.md",
                parsed_verdict,
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
    parser.add_argument("--code-command", help="trusted runtime/agent command that performs or dispatches implementation")
    parser.add_argument("--patch-summary-file", type=Path)
    parser.add_argument("--verification-command", action="append", default=[], help="trusted command used as verification evidence")
    parser.add_argument("--verification-report-file", type=Path)
    parser.add_argument("--code-review-command", help="trusted runtime/agent command that produces code review output")
    parser.add_argument("--code-review-file", type=Path)
    parser.add_argument("--memory-write-command", help="trusted command that writes project memory after acceptance")
    parser.add_argument("--write-project-memory", action="store_true", help="call project_memory_writer.py for accepted runs")
    parser.add_argument("--command-cwd", type=Path, default=Path("."))
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
        code_command=args.code_command,
        patch_summary_file=args.patch_summary_file,
        verification_commands=tuple(args.verification_command or ()),
        verification_report_file=args.verification_report_file,
        code_review_command=args.code_review_command,
        code_review_file=args.code_review_file,
        memory_write_command=args.memory_write_command,
        write_project_memory=bool(args.write_project_memory),
        command_cwd=args.command_cwd,
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
        for key in ("project_memory_context", "requirements_package", "requirements_discussion", "solution_package", "verification", "code_review", "acceptance"):
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

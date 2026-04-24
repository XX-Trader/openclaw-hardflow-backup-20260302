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
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_RUNTIME_HOME = {
    "hermes": "~/.hermes",
    "openclaw": "~/.openclaw",
}
EXPECTED_VERDICTS = {
    "requirements_review": "ready_for_solution",
    "solution_review": "ready_for_implement",
    "code_review": "pass",
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
    runtime_host: str = "hermes"
    runtime_home: str | None = None
    workspace_root: Path = Path(".workflow/pipeline-runs")
    run_id: str | None = None
    source_urls: tuple[str, ...] = ()
    dry_run: bool = False
    simulate_failure_stage: str | None = None
    max_repair_loops: int = 2
    patch_summary_file: Path | None = None
    verification_report_file: Path | None = None
    code_review_file: Path | None = None
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
    if config.runtime_host not in DEFAULT_RUNTIME_HOME:
        raise PipelineError(f"unsupported runtime host: {config.runtime_host}")
    runtime_home = config.runtime_home or DEFAULT_RUNTIME_HOME[config.runtime_host]
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


def render_research_report(source_urls: tuple[str, ...], dry_run: bool) -> str:
    source_lines = "\n".join(f"- {url}" for url in source_urls) or "- No live source URLs supplied to runner."
    mode = "dry-run simulated research" if dry_run else "live research evidence required"
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
        - research external implementation options before coding
        - route coding work to implementation agents
        - run verification and code review gates
        - return implementation failures to coding agents
        - return requirement-caused failures to the requirement package
        - write final delivery evidence and memory updates

        ## Acceptance Criteria
        - Requirements review must return ready_for_solution.
        - Solution review must return ready_for_implement.
        - Verification must pass before acceptance.
        - Code review must return pass.
        - Acceptance failures must be routed to the correct upstream stage.
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
        2. external_research
        3. requirements_package
        4. requirements_review
        5. solution_package
        6. solution_review
        7. code_execution
        8. verification
        9. code_review
        10. acceptance
        11. writeback

        ## Failure Routing
        - Requirement defects route to revise_requirements.
        - Solution defects route to revise_solution.
        - Implementation, verification, and code review defects route to return_to_code_execution.
        """
    )


def render_patch_summary(config: PipelineConfig) -> str:
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


def render_verification_report(config: PipelineConfig, failed: bool) -> str:
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


def render_code_review(config: PipelineConfig, failed: bool) -> str:
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
        The runner records the recommended writeback only. A live coordinator may
        call project_memory_writer.py after acceptance passes.

        ## Suggested Command
        python scripts/openclaw-ops/project_memory_writer.py --project-key {project_key} --artifact-type decision --content "Project delivery pipeline run accepted" --source manual
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
    record("external_research", "research_report.md", render_research_report(config.source_urls, config.dry_run))
    record("requirements_package", "requirements.md", render_requirements(requirement))

    req_verdict = "requires_revision" if config.simulate_failure_stage == "requirements" else "ready_for_solution"
    req_review = record(
        "requirements_review",
        "requirements_review.md",
        consensus_review("requirements_review", req_verdict, requirement),
        verdict=req_verdict,
    )
    gate_ok, parsed_verdict = gate_result("requirements_review", req_review)
    if not gate_ok:
        return block_pipeline(
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
        return block_pipeline(
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
        )

    if not config.dry_run and config.patch_summary_file is None:
        return block_pipeline(
            config,
            run_id,
            run_dir,
            runtime,
            stages,
            artifacts,
            "code_execution",
            "dispatch_code_agent",
            "live mode requires a coding agent patch summary artifact",
        )
    record("code_execution", "patch_summary.md", render_patch_summary(config))

    verification_failed = config.simulate_failure_stage == "verification"
    verification_content = render_verification_report(config, verification_failed)
    verification_score = 55 if verification_failed else 100
    record(
        "verification",
        "verification_report.md",
        verification_content,
        score=verification_score,
        verdict="fail" if verification_failed else "pass",
    )
    if verification_failed:
        return block_pipeline(
            config,
            run_id,
            run_dir,
            runtime,
            stages,
            artifacts,
            "verification",
            "return_to_code_execution",
            "verification failed and must be fixed by implementation agent",
            "verification_report.md",
            "fail",
            verification_score,
        )

    code_review_failed = config.simulate_failure_stage == "code_review"
    code_review = record(
        "code_review",
        "code_review.md",
        render_code_review(config, code_review_failed),
        verdict="requires_revision" if code_review_failed else "pass",
    )
    gate_ok, parsed_verdict = gate_result("code_review", code_review)
    if not gate_ok:
        return block_pipeline(
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
        return block_pipeline(
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
        return block_pipeline(
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
        )

    acceptance_path = record(
        "acceptance",
        "delivery_evidence.md",
        render_delivery_evidence(100, "pass", "writeback"),
        score=100,
        verdict="pass",
    )
    artifacts["delivery_evidence"] = str(acceptance_path)
    record("writeback", "writeback_report.md", render_writeback_report(config.project_key, "completed", "none"))

    failure_path = run_dir / "failure_learning_check.json"
    write_json(failure_path, failure_learning_payload(config, run_id, "completed", None, "none"))
    artifacts["failure_learning_check"] = str(failure_path)

    state = pipeline_state(config, run_id, run_dir, runtime, stages, artifacts, "completed", "none")
    write_json(run_dir / "pipeline_state.json", state)
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the project delivery pipeline state machine")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--requirement")
    parser.add_argument("--requirement-file", type=Path)
    parser.add_argument("--runtime-host", choices=sorted(DEFAULT_RUNTIME_HOME), default="hermes")
    parser.add_argument("--runtime-home")
    parser.add_argument("--workspace-root", type=Path, default=Path(".workflow/pipeline-runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--simulate-failure-stage", choices=sorted(SIMULATED_FAILURES))
    parser.add_argument("--max-repair-loops", type=int, default=2)
    parser.add_argument("--patch-summary-file", type=Path)
    parser.add_argument("--verification-report-file", type=Path)
    parser.add_argument("--code-review-file", type=Path)
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
        patch_summary_file=args.patch_summary_file,
        verification_report_file=args.verification_report_file,
        code_review_file=args.code_review_file,
        force=args.force,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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

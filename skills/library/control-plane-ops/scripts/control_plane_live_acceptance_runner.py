#!/usr/bin/env python3
"""Run one isolated live acceptance flow for the control-plane runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from benchmark_output_consumer import build_benchmark_output_consumer_payload
from control_plane_acceptance_runner import build_control_plane_acceptance_report
from control_plane_dashboard import build_control_plane_dashboard_snapshot
from control_plane_optimization_advisor import build_control_plane_optimization_report
from control_plane_optimization_dispatcher import dispatch_control_plane_optimization_tasks
from control_plane_profile_update_applier import apply_control_plane_profile_updates
from control_plane_profile_update_dispatcher import dispatch_control_plane_profile_update_tasks
from control_plane_profile_update_validation_runner import run_control_plane_profile_update_validation
from control_plane_optimization_review_runner import build_control_plane_optimization_review_report
from control_plane_summary_runner import build_control_plane_summary_payload
from cron_setup import (
    build_benchmark_output_job,
    build_benchmark_sweep_job,
    build_control_plane_dashboard_job,
    build_control_plane_optimization_dispatch_job,
    build_control_plane_profile_update_dispatch_job,
    build_control_plane_profile_update_apply_job,
    build_control_plane_profile_update_validation_job,
    build_control_plane_optimization_review_job,
    build_control_plane_optimization_job,
    build_control_plane_summary_job,
    build_task_output_broadcast_job,
)
from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from install_workflow_profile import build_cron_setup_cmd
from task_center import TaskCenter, utc_now_iso  # type: ignore
from task_output_consumer import build_task_output_consumer_payload
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


JSONDict = dict[str, Any]
REPLAY_JOB_NAMES = (
    "ops_control_plane_summary_6h",
    "ops_control_plane_dashboard_6h",
    "ops_control_plane_optimization_12h",
    "ops_control_plane_optimization_dispatch_12h",
    "ops_control_plane_optimization_review_12h",
    "ops_control_plane_profile_update_dispatch_12h",
    "ops_control_plane_profile_update_apply_12h",
    "ops_control_plane_profile_update_validation_12h",
    "ops_control_plane_acceptance_12h",
)


def _write_json(path: Path, payload: JSONDict) -> None:
    """Write one JSON payload using UTF-8 without BOM."""

    write_json_atomic(
        path,
        payload,
        ensure_ascii=False,
        indent=2,
        file_mode=0o644,
        dir_mode=0o755,
    )


def _write_markdown(path: Path, text: str) -> None:
    """Write one Markdown payload using UTF-8 without BOM."""

    atomic_write_text(
        path,
        text,
        encoding="utf-8",
        newline="\n",
        file_mode=0o644,
        dir_mode=0o755,
    )


def _load_jobs(jobs_file: Path) -> list[JSONDict]:
    """Load installed jobs from one jobs.json file."""

    payload = json.loads(jobs_file.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"jobs file must contain a JSON object: {jobs_file}")
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError(f"jobs file jobs must be a list: {jobs_file}")
    return [item for item in jobs if isinstance(item, dict)]


def _extract_job_command(job: JSONDict) -> str:
    """Extract the raw scheduled runner command from one installed job payload."""

    payload = job.get("payload", {}) if isinstance(job.get("payload", {}), dict) else {}
    message = str(payload.get("message", "")).strip()
    if message:
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line.endswith("Run command only:") and index + 1 < len(lines):
                return str(lines[index + 1]).strip()
        if len(lines) >= 2 and lines[0].startswith("You are "):
            return str(lines[1]).strip()
    return str(job.get("command", "")).strip()


def _normalize_replay_command(command: str) -> str:
    """Normalize one replay command so it can run inside the current Python host."""

    normalized = str(command or "").strip()
    if not normalized:
        return ""
    if normalized == "python3":
        return f'"{sys.executable}"'
    if normalized.startswith("python3 "):
        return f'"{sys.executable}"{normalized[len("python3"):]}'
    return normalized


def _run_installed_job_replay_step(*, jobs_file: Path) -> JSONDict:
    """Replay a curated subset of installed jobs against the isolated workspace."""

    installed_jobs = _load_jobs(jobs_file)
    job_by_name = {
        str(item.get("name", "")).strip(): item
        for item in installed_jobs
        if str(item.get("name", "")).strip()
    }
    repo_root = Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    replayed: list[dict[str, Any]] = []
    skipped_job_names: list[str] = []
    for job_name in REPLAY_JOB_NAMES:
        job = job_by_name.get(job_name)
        if not isinstance(job, dict):
            skipped_job_names.append(job_name)
            continue
        command = _normalize_replay_command(_extract_job_command(job))
        if not command:
            skipped_job_names.append(job_name)
            continue
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            shell=True,
            timeout=180,
        )
        result = {
            "job_name": job_name,
            "returncode": int(completed.returncode),
            "stdout_tail": str(completed.stdout or "")[-2000:],
            "stderr_tail": str(completed.stderr or "")[-2000:],
            "command": command,
        }
        if completed.returncode != 0:
            raise RuntimeError(
                f"installed job replay failed: {job_name}: "
                + (result["stderr_tail"] or result["stdout_tail"] or f"exit={completed.returncode}")
            )
        replayed.append(result)
    return {
        "jobs_file": str(jobs_file),
        "executed_job_count": len(replayed),
        "executed_job_names": [item["job_name"] for item in replayed],
        "skipped_job_names": skipped_job_names,
        "replayed": replayed,
    }


def _seed_sample_control_plane_data(task_db: Path) -> JSONDict:
    """Seed one isolated task-center DB with representative control-plane samples.

    Args:
        task_db: Isolated SQLite database path used only for acceptance.

    Returns:
        dict[str, Any]: Seed summary including created sample task ids.
    """

    task_center = TaskCenter(task_db)
    task_center.init_schema()
    unique_suffix = uuid.uuid4().hex[:8]
    risky_task_id = f"live-accept-risk-{unique_suffix}"
    stable_task_id = f"live-accept-stable-{unique_suffix}"
    try:
        task_center.create_task(
            {
                "task_id": risky_task_id,
                "pool": "todo",
                "task_type": "workflow",
                "reason": "live acceptance risky review",
                "source": "control-plane-live-acceptance-runner",
                "priority": "high",
                "risk_level": "high",
                "status": "running",
                "workflow_profile_id": "coding-default",
                "workflow_channel": "candidate",
                "stage_id": "review",
                "requirement": "Need stronger review gate",
                "result_output": "review blocked",
                "acceptance": "gate recommendation",
                "observable_outputs": "acceptance runner",
                "acceptance_thresholds": "ok",
            },
            actor="live-acceptance",
        )
        task_center.record_task_output(
            task_id=risky_task_id,
            output_type="agent_report",
            audience="human",
            channel="none",
            status="prepared",
            summary="需要人工协助",
            payload={"human_gate": {"requires_human_assistance": True}},
            actor="reviewer",
        )
        task_center.record_task_incident(
            task_id=risky_task_id,
            incident_type="stage_contract_failed",
            severity="critical",
            status="open",
            reason="contract_failed",
            summary="仍需人工复核",
            owner="reviewer",
            details={"source": "control-plane-live-acceptance-runner"},
            actor="reviewer",
        )
        task_center.record_benchmark_run(
            task_id=risky_task_id,
            benchmark_suite_id="coding-default-core",
            benchmark_run_id=f"{risky_task_id}-bench",
            workflow_profile_id="coding-default",
            workflow_channel="candidate",
            target_kind="workflow",
            target_id="coding-default",
            baseline_run_ids=["baseline-1"],
            candidate_run_ids=["candidate-1"],
            summary_file="reports/latest-summary.json",
            scorecard_file="reports/latest-scorecard.json",
            decision={"promote_to_new_baseline": False, "veto_reasons": ["critical_incidents_present"]},
            actor="upgrade-feedback-runner",
        )

        task_center.create_task(
            {
                "task_id": stable_task_id,
                "pool": "todo",
                "task_type": "workflow",
                "reason": "live acceptance stable draft",
                "source": "control-plane-live-acceptance-runner",
                "priority": "medium",
                "risk_level": "low",
                "status": "passed",
                "workflow_profile_id": "docs-default",
                "workflow_channel": "stable",
                "stage_id": "draft",
                "requirement": "Draft stage looks stable",
                "result_output": "Can consider simplification",
                "acceptance": "stability recommendation",
                "observable_outputs": "acceptance runner",
                "acceptance_thresholds": "ok",
            },
            actor="live-acceptance",
        )
        task_center.record_benchmark_run(
            task_id=stable_task_id,
            benchmark_suite_id="docs-default-core",
            benchmark_run_id=f"{stable_task_id}-bench",
            workflow_profile_id="docs-default",
            workflow_channel="stable",
            target_kind="workflow",
            target_id="docs-default",
            baseline_run_ids=["baseline-1"],
            candidate_run_ids=["candidate-1"],
            summary_file="reports/latest-summary.json",
            scorecard_file="reports/latest-scorecard.json",
            decision={"promote_to_new_baseline": True, "veto_reasons": []},
            actor="upgrade-feedback-runner",
        )
    finally:
        task_center.close()

    return {
        "seeded_task_ids": [risky_task_id, stable_task_id],
        "seeded_task_count": 2,
        "primary_task_id": risky_task_id,
    }


def _build_sample_benchmark_summary() -> JSONDict:
    """Build one synthetic benchmark sweep summary for consumer/dashboard validation."""

    return {
        "status": "partial_failure",
        "generated_at": utc_now_iso(),
        "requested_suite_ids": ["coding-default-core", "docs-default-core"],
        "success_count": 1,
        "failure_count": 1,
        "results": [
            {
                "suite_id": "docs-default-core",
                "summary": {
                    "workflow_scorecard": {
                        "decision": {
                            "promote_to_new_baseline": True,
                            "veto_reasons": [],
                        }
                    }
                },
            }
        ],
        "failures": [
            {
                "suite_id": "coding-default-core",
                "error_type": "RuntimeError",
                "error": "synthetic blocked candidate",
            }
        ],
    }


def _seed_workspace_workflow_registry(workspace_root: Path) -> Path:
    """Copy one mutable workflow registry into the isolated live-acceptance workspace."""

    source_registry = Path(__file__).resolve().parent / "policy" / "workflow-profile-registry.json"
    target_registry = workspace_root / "policy/workflow-profile-registry.json"
    target_registry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_registry, target_registry)
    return target_registry


def _write_install_surface_project_registry(project_registry: Path) -> None:
    """Create one minimal project-registry file for isolated install-surface generation."""

    project_registry.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        project_registry,
        {
            "version": 1,
            "projects": [],
        },
    )


def _build_install_surface(
    *,
    workspace_root: Path,
    task_db: Path,
    jobs_file: str | Path | None,
) -> dict[str, Any]:
    """Generate one jobs file by executing the real cron_setup install surface."""

    if jobs_file:
        requested = Path(str(jobs_file).strip()).expanduser()
        if requested.exists():
            return {
                "jobs_file": str(requested),
                "jobs_file_generated": False,
                "install_command": "",
            }

    ops_home = Path(__file__).resolve().parent
    repo_root = ops_home.parent.parent
    openclaw_home = workspace_root / "openclaw-home"
    workflow_repo_path = workspace_root / "workflow-repo"
    workflow_repo_path.mkdir(parents=True, exist_ok=True)
    (workflow_repo_path / "todo.md").write_text("# live acceptance\n", encoding="utf-8")
    (workflow_repo_path / "TODO.md").write_text("# live acceptance\n", encoding="utf-8")
    if not (workflow_repo_path / ".git").exists():
        init_completed = subprocess.run(
            ["git", "init"],
            cwd=str(workflow_repo_path),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        if init_completed.returncode != 0:
            raise RuntimeError(
                "install surface failed to initialize workflow repo: "
                + (init_completed.stderr.strip() or init_completed.stdout.strip() or f"exit={init_completed.returncode}")
            )
    project_registry = workspace_root / "projects/registry.json"
    _write_install_surface_project_registry(project_registry)
    generated_jobs_file = workspace_root / "cron/jobs.json"
    generated_jobs_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_cron_setup_cmd(
        python_bin=sys.executable,
        script_path=str(ops_home / "cron_setup.py"),
        jobs_file=str(generated_jobs_file),
        ops_home=str(ops_home),
        openclaw_home=str(openclaw_home),
        workflow_repo_path=str(workflow_repo_path),
        workflow_repo_id="openclaw-live-acceptance",
        project_registry=str(project_registry),
        task_db=str(task_db),
        incremental_every_ms=600000,
        full_expr="0 * * * *",
        daily_summary_expr="0 9 * * *",
        daily_work_expr="0 8 * * *",
        self_evolution_expr="0 3 * * 1",
        self_evolution_low_score_guarantee_enabled=True,
        self_evolution_low_score_guarantee_min_agents=2,
        self_evolution_low_score_guarantee_max_agents=6,
        self_evolution_low_score_guarantee_threshold=70.0,
        conversation_every_ms=600000,
        governance_every_ms=21600000,
        governance_auto_pr=False,
        governance_reviewer_gh_user="",
        governance_push_before_pr=False,
        git_sync_every_ms=21600000,
        auto_update_install_every_ms=86400000,
        github_web_every_ms=21600000,
        include_github_web=False,
        channel="announce",
        target="control-plane-live-acceptance",
    )
    completed = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "install surface failed to generate jobs.json: "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}")
        )
    if not generated_jobs_file.exists():
        raise RuntimeError("install surface finished without jobs.json output")
    return {
        "jobs_file": str(generated_jobs_file),
        "jobs_file_generated": True,
        "install_command": subprocess.list2cmdline(cmd),
    }


def _build_synthetic_jobs_payload(*, workspace_root: Path, jobs_file: Path) -> JSONDict:
    """Build one synthetic control-plane jobs payload for acceptance validation."""

    ops_dir = Path(__file__).resolve().parent
    policy_dir = ops_dir / "policy"
    task_db = workspace_root / "task-center/task_center.db"
    workspace_registry = workspace_root / "policy/workflow-profile-registry.json"
    return {
        "jobs": [
            build_benchmark_sweep_job(
                script_py=str(ops_dir / "benchmark_orchestrator.py"),
                executor_run_dir=str(workspace_root / "task-center/executor-runs"),
                output_root=str(workspace_root / "benchmark-sweeps"),
                state_root=str(workspace_root / "benchmark-sweeps/state"),
                benchmark_suite_file=str(policy_dir / "benchmark-suite-registry.json"),
                workflow_profile_registry=str(policy_dir / "workflow-profile-registry.json"),
                task_db=str(task_db),
                output_consumer_py=str(ops_dir / "benchmark_output_consumer.py"),
                summary_file=str(workspace_root / "benchmark-sweeps/sweeps/latest-summary.json"),
                consumer_output_file=str(workspace_root / "benchmark-sweeps/output/latest-event.json"),
                consumer_notify_on="error",
                every_ms=86400000,
                log_mode="silent",
                auto_create_tasks=False,
                auto_apply_workflow_promotion=False,
                promotion_operator="live-acceptance",
                task_score_threshold=80.0,
                task_schedule_gap_minutes=120,
                suite_ids=["coding-default-core", "docs-default-core"],
            ),
            build_benchmark_output_job(
                script_py=str(ops_dir / "benchmark_output_consumer.py"),
                summary_file=str(workspace_root / "benchmark-sweeps/sweeps/latest-summary.json"),
                output_file=str(workspace_root / "benchmark-sweeps/output/latest-event.json"),
                notify_on="error",
                every_ms=86400000,
                delay_ms=300000,
                log_mode="silent",
            ),
            build_task_output_broadcast_job(
                script_py=str(ops_dir / "task_output_broadcast_runner.py"),
                db_file=str(task_db),
                state_file=str(workspace_root / "task-output/state.json"),
                output_file=str(workspace_root / "task-output/latest-event.json"),
                lookback_hours=24,
                limit=12,
                event_limit=200,
                notify_on="error",
                every_ms=900000,
                delay_ms=120000,
                log_mode="silent",
            ),
            build_control_plane_summary_job(
                script_py=str(ops_dir / "control_plane_summary_runner.py"),
                db_file=str(task_db),
                state_file=str(workspace_root / "control-plane-summary/state.json"),
                output_file=str(workspace_root / "control-plane-summary/latest-event.json"),
                lookback_hours=24,
                limit=20,
                notify_on="activity",
                every_ms=21600000,
                delay_ms=180000,
                log_mode="silent",
            ),
            build_control_plane_dashboard_job(
                script_py=str(ops_dir / "control_plane_dashboard.py"),
                db_file=str(task_db),
                benchmark_summary_file=str(workspace_root / "benchmark-sweeps/sweeps/latest-summary.json"),
                json_output=str(workspace_root / "control-plane-dashboard/latest-dashboard.json"),
                markdown_output=str(workspace_root / "control-plane-dashboard/latest-dashboard.md"),
                html_output=str(workspace_root / "control-plane-dashboard/latest-dashboard.html"),
                lookback_hours=24,
                limit=20,
                every_ms=21600000,
                delay_ms=240000,
                log_mode="silent",
            ),
            build_control_plane_optimization_job(
                script_py=str(ops_dir / "control_plane_optimization_advisor.py"),
                db_file=str(task_db),
                json_output=str(workspace_root / "control-plane-optimization/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-optimization/latest-report.md"),
                lookback_hours=24,
                limit=20,
                every_ms=43200000,
                delay_ms=360000,
                log_mode="silent",
            ),
            build_control_plane_optimization_dispatch_job(
                script_py=str(ops_dir / "control_plane_optimization_dispatcher.py"),
                report_file=str(workspace_root / "control-plane-optimization/latest-report.json"),
                task_db=str(task_db),
                json_output=str(workspace_root / "control-plane-optimization-dispatch/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-optimization-dispatch/latest-report.md"),
                execution_workflow_profile="coding-default",
                execution_workflow_channel="stable",
                schedule_gap_minutes=30,
                every_ms=43200000,
                delay_ms=480000,
                log_mode="silent",
            ),
            build_control_plane_optimization_review_job(
                script_py=str(ops_dir / "control_plane_optimization_review_runner.py"),
                task_db=str(task_db),
                json_output=str(workspace_root / "control-plane-optimization-review/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-optimization-review/latest-report.md"),
                lookback_hours=72,
                limit=20,
                every_ms=43200000,
                delay_ms=540000,
                log_mode="silent",
            ),
            build_control_plane_profile_update_dispatch_job(
                script_py=str(ops_dir / "control_plane_profile_update_dispatcher.py"),
                review_file=str(workspace_root / "control-plane-optimization-review/latest-report.json"),
                task_db=str(task_db),
                json_output=str(workspace_root / "control-plane-profile-update-dispatch/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-profile-update-dispatch/latest-report.md"),
                execution_workflow_profile="coding-default",
                execution_workflow_channel="stable",
                schedule_gap_minutes=60,
                every_ms=43200000,
                delay_ms=600000,
                log_mode="silent",
            ),
            build_control_plane_profile_update_apply_job(
                script_py=str(ops_dir / "control_plane_profile_update_applier.py"),
                task_db=str(task_db),
                registry_file=str(workspace_registry),
                json_output=str(workspace_root / "control-plane-profile-update-apply/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-profile-update-apply/latest-report.md"),
                target_channel="candidate",
                lookback_hours=72,
                limit=20,
                every_ms=43200000,
                delay_ms=660000,
                log_mode="silent",
            ),
            build_control_plane_profile_update_validation_job(
                script_py=str(ops_dir / "control_plane_profile_update_validation_runner.py"),
                apply_file=str(workspace_root / "control-plane-profile-update-apply/latest-report.json"),
                benchmark_suite_file=str(policy_dir / "benchmark-suite-registry.json"),
                executor_run_dir=str(workspace_root / "task-center/executor-runs"),
                output_root=str(workspace_root / "control-plane-profile-update-validation"),
                state_file=str(workspace_root / "control-plane-profile-update-validation/state.json"),
                task_db=str(task_db),
                workflow_profile_registry=str(workspace_registry),
                json_output=str(workspace_root / "control-plane-profile-update-validation/latest-report.json"),
                markdown_output=str(workspace_root / "control-plane-profile-update-validation/latest-report.md"),
                every_ms=43200000,
                delay_ms=720000,
                log_mode="silent",
                auto_create_tasks=False,
                auto_apply_workflow_promotion=False,
                promotion_operator="control-plane-validation",
            ),
        ]
    }


def _ensure_jobs_file(*, workspace_root: Path, jobs_file: str | Path | None) -> tuple[Path, bool]:
    """Resolve or synthesize one jobs file for static acceptance validation."""

    if jobs_file:
        requested = Path(str(jobs_file).strip()).expanduser()
        if requested.exists():
            return requested, False
    synthetic_jobs_file = workspace_root / "cron/jobs.json"
    _write_json(synthetic_jobs_file, _build_synthetic_jobs_payload(workspace_root=workspace_root, jobs_file=synthetic_jobs_file))
    return synthetic_jobs_file, True


def _execute_step(
    *,
    steps: dict[str, Any],
    step_name: str,
    action: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run one step and capture structured pass/fail metadata."""

    try:
        result = action()
        steps[step_name] = {"status": "passed", **result}
        return result
    except Exception as exc:
        steps[step_name] = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        raise


def render_control_plane_live_acceptance_markdown(report: JSONDict) -> str:
    """Render one Markdown summary for the isolated live acceptance run."""

    lines = [
        "# OpenClaw Control Plane Live Acceptance",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- 工作区：{report.get('workspace_root', '')}",
        f"- 任务库：{report.get('task_db', '')}",
        f"- 通过状态：{'PASS' if bool(report.get('passed', False)) else 'FAIL'}",
        f"- 播种任务数：{report.get('seeded_task_count', 0)}",
        f"- 派发任务数：{report.get('dispatch_created_count', 0)}",
        "",
        "## Steps",
    ]
    steps = report.get("steps", {})
    if isinstance(steps, dict):
        for step_name, item in steps.items():
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "unknown")).upper()
            line = f"- [{status}] {step_name}"
            if str(item.get("error", "")).strip():
                line += f" -> {item.get('error_type', 'Error')}: {item.get('error', '')}"
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def run_control_plane_live_acceptance(
    *,
    workspace_root: str | Path,
    jobs_file: str | Path | None = None,
    lookback_hours: int = 24,
    limit: int = 20,
) -> JSONDict:
    """Run one isolated live acceptance flow for the control-plane runtime.

    Args:
        workspace_root: Isolated output root used for sample DB, reports, and derived artifacts.
        jobs_file: Optional installed jobs.json path. If missing, a synthetic jobs file is generated.
        lookback_hours: Summary/advisor/dashboard lookback window in hours.
        limit: Max task/sample count used by summary/advisor/dashboard.

    Returns:
        dict[str, Any]: Structured live acceptance report with per-step status and artifacts.
    """

    workspace = Path(workspace_root).expanduser()
    task_db = workspace / "task-center/task_center.db"
    optimization_json = workspace / "control-plane-optimization/latest-report.json"
    optimization_md = workspace / "control-plane-optimization/latest-report.md"
    dispatch_json = workspace / "control-plane-optimization-dispatch/latest-report.json"
    dispatch_md = workspace / "control-plane-optimization-dispatch/latest-report.md"
    optimization_review_json = workspace / "control-plane-optimization-review/latest-report.json"
    optimization_review_md = workspace / "control-plane-optimization-review/latest-report.md"
    profile_update_dispatch_json = workspace / "control-plane-profile-update-dispatch/latest-report.json"
    profile_update_dispatch_md = workspace / "control-plane-profile-update-dispatch/latest-report.md"
    profile_update_apply_json = workspace / "control-plane-profile-update-apply/latest-report.json"
    profile_update_apply_md = workspace / "control-plane-profile-update-apply/latest-report.md"
    profile_update_validation_json = workspace / "control-plane-profile-update-validation/latest-report.json"
    profile_update_validation_md = workspace / "control-plane-profile-update-validation/latest-report.md"
    summary_output = workspace / "control-plane-summary/latest-event.json"
    summary_state = workspace / "control-plane-summary/state.json"
    dashboard_json = workspace / "control-plane-dashboard/latest-dashboard.json"
    dashboard_md = workspace / "control-plane-dashboard/latest-dashboard.md"
    dashboard_html = workspace / "control-plane-dashboard/latest-dashboard.html"
    task_output_json = workspace / "task-output/latest-event.json"
    benchmark_summary_file = workspace / "benchmark-sweeps/sweeps/latest-summary.json"
    benchmark_output_json = workspace / "benchmark-sweeps/output/latest-event.json"
    acceptance_json = workspace / "control-plane-acceptance/latest-report.json"
    acceptance_md = workspace / "control-plane-acceptance/latest-report.md"

    seed_info = _seed_sample_control_plane_data(task_db)
    workspace_registry = _seed_workspace_workflow_registry(workspace)
    _write_json(benchmark_summary_file, _build_sample_benchmark_summary())

    steps: dict[str, Any] = {}
    dispatch_payload: dict[str, Any] = {}
    profile_update_dispatch_payload: dict[str, Any] = {}
    profile_update_apply_payload: dict[str, Any] = {}
    profile_update_validation_payload: dict[str, Any] = {}
    install_surface_info: dict[str, Any] = {}
    resolved_jobs_file = Path(jobs_file).expanduser() if jobs_file else workspace / "cron/jobs.json"
    generated_jobs_file = False
    jobs_file_generation_mode = "existing_jobs_file"
    try:
        install_surface_info = _execute_step(
            steps=steps,
            step_name="install_surface",
            action=lambda: _build_install_surface(
                workspace_root=workspace,
                task_db=task_db,
                jobs_file=jobs_file,
            ),
        )
        resolved_jobs_file = Path(str(install_surface_info["jobs_file"])).expanduser()
        generated_jobs_file = bool(install_surface_info.get("jobs_file_generated", False))
        jobs_file_generation_mode = "install_surface" if generated_jobs_file else "existing_jobs_file"
        report = _execute_step(
            steps=steps,
            step_name="optimization_advisor",
            action=lambda: _run_optimization_advisor_step(
                task_db=task_db,
                lookback_hours=lookback_hours,
                limit=limit,
                json_output=optimization_json,
                markdown_output=optimization_md,
            ),
        )
        dispatch_payload = _execute_step(
            steps=steps,
            step_name="optimization_dispatch",
            action=lambda: _run_optimization_dispatch_step(
                task_db=task_db,
                report=report["report"],
                report_file=optimization_json,
                json_output=dispatch_json,
                markdown_output=dispatch_md,
            ),
        )
        _simulate_optimization_task_outcomes(
            task_db=task_db,
            dispatch_payload=dispatch_payload,
        )
        _execute_step(
            steps=steps,
            step_name="optimization_review",
            action=lambda: _run_optimization_review_step(
                task_db=task_db,
                json_output=optimization_review_json,
                markdown_output=optimization_review_md,
            ),
        )
        profile_update_dispatch_payload = _execute_step(
            steps=steps,
            step_name="profile_update_dispatch",
            action=lambda: _run_profile_update_dispatch_step(
                task_db=task_db,
                review_file=optimization_review_json,
                json_output=profile_update_dispatch_json,
                markdown_output=profile_update_dispatch_md,
            ),
        )
        _simulate_profile_update_task_outcomes(
            task_db=task_db,
            dispatch_payload=profile_update_dispatch_payload,
        )
        profile_update_apply_payload = _execute_step(
            steps=steps,
            step_name="profile_update_apply",
            action=lambda: _run_profile_update_apply_step(
                task_db=task_db,
                registry_file=workspace_registry,
                json_output=profile_update_apply_json,
                markdown_output=profile_update_apply_md,
            ),
        )
        profile_update_validation_payload = _execute_step(
            steps=steps,
            step_name="profile_update_validation",
            action=lambda: _run_profile_update_validation_step(
                apply_file=profile_update_apply_json,
                benchmark_suite_file=Path(__file__).resolve().parent / "policy/benchmark-suite-registry.json",
                executor_run_dir=workspace / "task-center/executor-runs",
                output_root=workspace / "control-plane-profile-update-validation",
                state_file=workspace / "control-plane-profile-update-validation/state.json",
                task_db=task_db,
                workflow_profile_registry=workspace_registry,
                json_output=profile_update_validation_json,
                markdown_output=profile_update_validation_md,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="control_plane_summary",
            action=lambda: _run_control_plane_summary_step(
                task_db=task_db,
                lookback_hours=lookback_hours,
                limit=limit,
                state_file=summary_state,
                output_file=summary_output,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="task_output_consumer",
            action=lambda: _run_task_output_consumer_step(
                task_db=task_db,
                task_id=str(seed_info["primary_task_id"]),
                output_file=task_output_json,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="benchmark_output_consumer",
            action=lambda: _run_benchmark_output_consumer_step(
                summary_file=benchmark_summary_file,
                output_file=benchmark_output_json,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="control_plane_dashboard",
            action=lambda: _run_control_plane_dashboard_step(
                task_db=task_db,
                benchmark_summary_file=benchmark_summary_file,
                lookback_hours=lookback_hours,
                limit=limit,
                json_output=dashboard_json,
                markdown_output=dashboard_md,
                html_output=dashboard_html,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="control_plane_acceptance",
            action=lambda: _run_control_plane_acceptance_step(
                jobs_file=resolved_jobs_file,
                json_output=acceptance_json,
                markdown_output=acceptance_md,
            ),
        )
        _execute_step(
            steps=steps,
            step_name="installed_job_replay",
            action=lambda: _run_installed_job_replay_step(jobs_file=resolved_jobs_file),
        )
        passed = True
        error_type = ""
        error_text = ""
    except Exception as exc:
        passed = False
        error_type = type(exc).__name__
        error_text = str(exc)

    acceptance_step = steps.get("control_plane_acceptance", {})
    report_payload = {
        "generated_at": utc_now_iso(),
        "workspace_root": str(workspace),
        "task_db": str(task_db),
        "jobs_file": str(resolved_jobs_file),
        "jobs_file_generated": generated_jobs_file,
        "jobs_file_generation_mode": jobs_file_generation_mode,
        "seeded_task_count": int(seed_info["seeded_task_count"]),
        "seeded_task_ids": list(seed_info["seeded_task_ids"]),
        "dispatch_created_count": int(dispatch_payload.get("created_count", 0) or 0),
        "profile_update_dispatch_created_count": int(profile_update_dispatch_payload.get("created_count", 0) or 0),
        "profile_update_apply_applied_count": int(profile_update_apply_payload.get("applied_count", 0) or 0),
        "profile_update_validation_executed_suite_count": int(profile_update_validation_payload.get("executed_suite_count", 0) or 0),
        "installed_job_replay_executed_count": int(steps.get("installed_job_replay", {}).get("executed_job_count", 0) or 0),
        "passed": bool(passed and acceptance_step.get("status") == "passed"),
        "error_type": error_type,
        "error": error_text,
        "steps": steps,
    }
    report_payload["markdown"] = render_control_plane_live_acceptance_markdown(report_payload)
    return report_payload


def _run_optimization_advisor_step(
    *,
    task_db: Path,
    lookback_hours: int,
    limit: int,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    report = build_control_plane_optimization_report(
        db_file=task_db,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    payload = {"report": report}
    _write_json(json_output, payload)
    _write_markdown(markdown_output, report["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "recommendation_count": len(report.get("recommendations", [])),
        "report": report,
    }


def _run_optimization_dispatch_step(
    *,
    task_db: Path,
    report: JSONDict,
    report_file: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    dispatch = dispatch_control_plane_optimization_tasks(
        task_db=task_db,
        report=report,
        execution_workflow_profile="coding-default",
        execution_workflow_channel="stable",
        schedule_gap_minutes=30,
        report_file=report_file,
    )
    payload = {"dispatch": dispatch}
    _write_json(json_output, payload)
    _write_markdown(markdown_output, dispatch["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "created_count": int(dispatch.get("created_count", 0) or 0),
        "skipped_count": int(dispatch.get("skipped_count", 0) or 0),
        "dispatch": dispatch,
    }


def _simulate_optimization_task_outcomes(
    *,
    task_db: Path,
    dispatch_payload: JSONDict,
) -> JSONDict:
    """Simulate minimal optimization execution outcomes for isolated live acceptance."""

    dispatch = dispatch_payload.get("dispatch", {})
    created = dispatch.get("created", []) if isinstance(dispatch, dict) else []
    if not isinstance(created, list) or not created:
        return {"simulated_task_count": 0}

    task_center = TaskCenter(task_db)
    try:
        first_item = created[0] if isinstance(created[0], dict) else {}
        first_task_id = str(first_item.get("task_id", "")).strip()
        if first_task_id:
            task_center.transition_status(
                first_task_id,
                "passed",
                actor="control-plane-live-acceptance-runner",
                stage="optimization-review",
                details={"simulated": True, "outcome": "ready_for_profile_update"},
            )
        if len(created) >= 2 and isinstance(created[1], dict):
            second_task_id = str(created[1].get("task_id", "")).strip()
            if second_task_id:
                task_center.transition_status(
                    second_task_id,
                    "failed",
                    actor="control-plane-live-acceptance-runner",
                    stage="optimization-review",
                    details={"simulated": True, "outcome": "blocked_for_review"},
                )
                task_center.record_task_incident(
                    task_id=second_task_id,
                    incident_type="optimization_follow_up_blocked",
                    severity="critical",
                    status="open",
                    reason="live_acceptance_blocked_candidate",
                    summary="live acceptance 模拟阻塞样本",
                    owner="reviewer",
                    details={"simulated": True},
                    actor="control-plane-live-acceptance-runner",
                )
        return {"simulated_task_count": min(2, len(created))}
    finally:
        task_center.close()


def _run_optimization_review_step(
    *,
    task_db: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    """Review dispatched optimization tasks and persist one report."""

    report = build_control_plane_optimization_review_report(
        task_db=task_db,
        lookback_hours=72,
        limit=20,
    )
    _write_json(json_output, {"report": report})
    _write_markdown(markdown_output, report["markdown"])
    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "ready_for_profile_update_count": int(summary.get("ready_for_profile_update_count", 0) or 0),
        "blocked_count": int(summary.get("blocked_count", 0) or 0),
        "pending_count": int(summary.get("pending_count", 0) or 0),
    }


def _run_profile_update_dispatch_step(
    *,
    task_db: Path,
    review_file: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    """Dispatch ready optimization review items into workflow profile update tasks."""

    dispatch = dispatch_control_plane_profile_update_tasks(
        review_file=review_file,
        task_db=task_db,
        execution_workflow_profile="coding-default",
        execution_workflow_channel="stable",
        schedule_gap_minutes=60,
    )
    _write_json(json_output, {"dispatch": dispatch})
    _write_markdown(markdown_output, dispatch["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "created_count": int(dispatch.get("created_count", 0) or 0),
        "skipped_count": int(dispatch.get("skipped_count", 0) or 0),
        "dispatch": dispatch,
    }


def _simulate_profile_update_task_outcomes(
    *,
    task_db: Path,
    dispatch_payload: JSONDict,
) -> JSONDict:
    """Simulate minimal workflow-profile-update execution outcomes for live acceptance."""

    dispatch = dispatch_payload.get("dispatch", {})
    created = dispatch.get("created", []) if isinstance(dispatch, dict) else []
    if not isinstance(created, list) or not created:
        return {"simulated_task_count": 0}

    task_center = TaskCenter(task_db)
    try:
        first_item = created[0] if isinstance(created[0], dict) else {}
        first_task_id = str(first_item.get("task_id", "")).strip()
        if first_task_id:
            task_center.transition_status(
                first_task_id,
                "passed",
                actor="control-plane-live-acceptance-runner",
                stage="profile-update-apply",
                details={"simulated": True, "outcome": "ready_for_registry_apply"},
            )
            return {"simulated_task_count": 1}
        return {"simulated_task_count": 0}
    finally:
        task_center.close()


def _run_profile_update_apply_step(
    *,
    task_db: Path,
    registry_file: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    """Apply passed workflow-profile-update tasks into the isolated registry copy."""

    result = apply_control_plane_profile_updates(
        task_db=task_db,
        registry_file=registry_file,
        lookback_hours=72,
        limit=20,
        target_channel="candidate",
    )
    _write_json(json_output, {"result": result})
    _write_markdown(markdown_output, result["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "applied_count": int(result.get("applied_count", 0) or 0),
        "skipped_count": int(result.get("skipped_count", 0) or 0),
    }


def _run_profile_update_validation_step(
    *,
    apply_file: Path,
    benchmark_suite_file: Path,
    executor_run_dir: Path,
    output_root: Path,
    state_file: Path,
    task_db: Path,
    workflow_profile_registry: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    """Run one isolated targeted benchmark validation step after profile updates."""

    def suite_runner(**kwargs: Any) -> JSONDict:
        suite_id = str(kwargs.get("suite_id", "")).strip() or "unknown-suite"
        suite_output_dir = Path(str(kwargs.get("output_root", output_root))).expanduser() / "suites" / suite_id
        suite_output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "workflow_scorecard": {
                "decision": {
                    "promote_to_new_baseline": False,
                    "veto_reasons": [],
                }
            }
        }
        summary_file = suite_output_dir / "latest-summary.json"
        _write_json(summary_file, summary)
        return {
            "status": "ok",
            "suite_id": suite_id,
            "output_dir": str(suite_output_dir),
            "state_file": str(Path(str(kwargs.get("state_root", output_root / 'state'))).expanduser() / f"{suite_id}.json"),
            "summary": summary,
        }

    result = run_control_plane_profile_update_validation(
        apply_file=apply_file,
        benchmark_suite_file=benchmark_suite_file,
        executor_run_dir=executor_run_dir,
        output_root=output_root,
        state_file=state_file,
        task_db=task_db,
        workflow_profile_registry=workflow_profile_registry,
        auto_create_tasks=False,
        auto_apply_workflow_promotion=False,
        promotion_operator="control-plane-live-acceptance",
        suite_runner=suite_runner,
    )
    _write_json(json_output, {"result": result})
    _write_markdown(markdown_output, result["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "executed_suite_count": int(result.get("executed_suite_count", 0) or 0),
        "validated_change_count": int(result.get("validated_change_count", 0) or 0),
        "skipped_count": int(result.get("skipped_count", 0) or 0),
        "failed_count": int(result.get("failed_count", 0) or 0),
    }


def _run_control_plane_summary_step(
    *,
    task_db: Path,
    lookback_hours: int,
    limit: int,
    state_file: Path,
    output_file: Path,
) -> JSONDict:
    payload = build_control_plane_summary_payload(
        db_file=task_db,
        state_file=state_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
        notify_on="activity",
    )
    _write_json(output_file, payload)
    return {
        "output": str(output_file),
        "notify": bool(payload.get("notify", False)),
    }


def _run_task_output_consumer_step(
    *,
    task_db: Path,
    task_id: str,
    output_file: Path,
) -> JSONDict:
    payload = build_task_output_consumer_payload(
        db_file=task_db,
        task_id=task_id,
        event_limit=200,
        notify_on="activity",
    )
    _write_json(output_file, payload)
    return {
        "output": str(output_file),
        "task_id": task_id,
        "notify": bool(payload.get("notify", False)),
    }


def _run_benchmark_output_consumer_step(
    *,
    summary_file: Path,
    output_file: Path,
) -> JSONDict:
    payload = build_benchmark_output_consumer_payload(
        summary_file=summary_file,
        notify_on="activity",
    )
    _write_json(output_file, payload)
    return {
        "output": str(output_file),
        "notify": bool(payload.get("notify", False)),
    }


def _run_control_plane_dashboard_step(
    *,
    task_db: Path,
    benchmark_summary_file: Path,
    lookback_hours: int,
    limit: int,
    json_output: Path,
    markdown_output: Path,
    html_output: Path,
) -> JSONDict:
    snapshot = build_control_plane_dashboard_snapshot(
        db_file=task_db,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
        benchmark_summary_file=benchmark_summary_file,
    )
    payload = {"snapshot": snapshot}
    _write_json(json_output, payload)
    _write_markdown(markdown_output, snapshot["markdown"])
    _write_markdown(html_output, snapshot["html"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "html_output": str(html_output),
    }


def _run_control_plane_acceptance_step(
    *,
    jobs_file: Path,
    json_output: Path,
    markdown_output: Path,
) -> JSONDict:
    report = build_control_plane_acceptance_report(jobs_file=jobs_file)
    payload = {"report": report}
    _write_json(json_output, payload)
    _write_markdown(markdown_output, report["markdown"])
    return {
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "passed": bool(report.get("passed", False)),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the isolated live acceptance runner."""

    parser = argparse.ArgumentParser(description="Run one isolated live acceptance flow for the control-plane runtime.")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--jobs-file", default="")
    parser.add_argument("--lookback-hours", default="24")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> JSONDict:
    """Run the CLI and return the live acceptance payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_control_plane_live_acceptance(
        workspace_root=Path(str(args.workspace_root).strip()).expanduser(),
        jobs_file=(Path(str(args.jobs_file).strip()).expanduser() if str(args.jobs_file).strip() else None),
        lookback_hours=max(1, int(args.lookback_hours or 24)),
        limit=max(1, int(args.limit or 20)),
    )
    payload = {"report": report}
    if str(args.json_output or "").strip():
        _write_json(Path(str(args.json_output).strip()).expanduser(), payload)
    if str(args.markdown_output or "").strip():
        _write_markdown(Path(str(args.markdown_output).strip()).expanduser(), report["markdown"])
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(report["markdown"])
    return payload


if __name__ == "__main__":
    main()

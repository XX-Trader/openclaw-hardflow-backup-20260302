#!/usr/bin/env python3
"""Validate the installed control-plane jobs.json and emit an acceptance report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import utc_now_iso  # type: ignore
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


REQUIRED_CONTROL_PLANE_JOBS: tuple[dict[str, Any], ...] = (
    {
        "name": "ops_benchmark_sweep_daily",
        "delivery_mode": "none",
        "message_contains": (
            "benchmark_orchestrator.py",
            "benchmark_output_consumer.py",
            "--benchmark-suite-file",
            "--workflow-profile-registry",
        ),
    },
    {
        "name": "ops_benchmark_output_daily",
        "delivery_mode": "announce",
        "message_contains": (
            "benchmark_output_consumer.py",
            "--summary-file",
            "--output",
        ),
    },
    {
        "name": "ops_task_output_broadcast_15m",
        "delivery_mode": "announce",
        "message_contains": (
            "task_output_broadcast_runner.py",
            "--db",
            "--state-file",
            "--notify-on",
        ),
    },
    {
        "name": "ops_control_plane_summary_6h",
        "delivery_mode": "announce",
        "message_contains": (
            "control_plane_summary_runner.py",
            "--db",
            "--state-file",
            "--notify-on",
        ),
    },
    {
        "name": "ops_control_plane_dashboard_6h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_dashboard.py",
            "--db",
            "--json-output",
            "--markdown-output",
            "--html-output",
        ),
    },
    {
        "name": "ops_control_plane_optimization_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_optimization_advisor.py",
            "--db",
            "--json-output",
            "--markdown-output",
        ),
    },
    {
        "name": "ops_control_plane_optimization_dispatch_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_optimization_dispatcher.py",
            "--report-file",
            "--task-db",
            "--execution-workflow-profile",
        ),
    },
    {
        "name": "ops_control_plane_optimization_review_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_optimization_review_runner.py",
            "--task-db",
            "--lookback-hours",
            "--json-output",
        ),
    },
    {
        "name": "ops_control_plane_profile_update_dispatch_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_profile_update_dispatcher.py",
            "--review-file",
            "--task-db",
            "--execution-workflow-profile",
        ),
    },
    {
        "name": "ops_control_plane_profile_update_apply_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_profile_update_applier.py",
            "--task-db",
            "--registry-file",
            "--target-channel",
        ),
    },
    {
        "name": "ops_control_plane_profile_update_validation_12h",
        "delivery_mode": "none",
        "message_contains": (
            "control_plane_profile_update_validation_runner.py",
            "--apply-file",
            "--benchmark-suite-file",
            "--workflow-profile-registry",
        ),
    },
)


def _load_jobs_payload(jobs_file: str | Path) -> list[dict[str, Any]]:
    """Load and normalize the cron jobs payload from one jobs file."""

    path = Path(jobs_file).expanduser()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
    elif isinstance(payload, list):
        jobs = payload
    else:
        raise ValueError(f"jobs file must be a JSON object or array: {path}")
    if not isinstance(jobs, list):
        raise ValueError(f"jobs field must be a list: {path}")
    normalized: list[dict[str, Any]] = []
    for item in jobs:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _get_payload_message(job: dict[str, Any]) -> str:
    """Return the agentTurn message from one cron job payload."""

    payload = job.get("payload", {})
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("message", "")).strip()


def _evaluate_required_job(
    *,
    spec: dict[str, Any],
    jobs_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate one required control-plane job against the installed jobs file."""

    job_name = str(spec.get("name", "")).strip()
    expected_delivery_mode = str(spec.get("delivery_mode", "")).strip()
    expected_clauses = [
        str(item).strip()
        for item in spec.get("message_contains", [])
        if str(item).strip()
    ]
    job = jobs_by_name.get(job_name)
    if job is None:
        return {
            "name": job_name,
            "present": False,
            "enabled": False,
            "expected_delivery_mode": expected_delivery_mode,
            "delivery_mode": "",
            "missing_message_clauses": expected_clauses,
            "passed": False,
            "failure_reasons": ["missing_job"],
        }

    delivery = job.get("delivery", {})
    delivery_mode = str(delivery.get("mode", "")).strip() if isinstance(delivery, dict) else ""
    message = _get_payload_message(job)
    missing_message_clauses = [item for item in expected_clauses if item not in message]
    enabled = bool(job.get("enabled", False))
    failure_reasons: list[str] = []
    if not enabled:
        failure_reasons.append("job_disabled")
    if delivery_mode != expected_delivery_mode:
        failure_reasons.append("delivery_mode_mismatch")
    if missing_message_clauses:
        failure_reasons.append("message_clause_missing")
    return {
        "name": job_name,
        "present": True,
        "enabled": enabled,
        "expected_delivery_mode": expected_delivery_mode,
        "delivery_mode": delivery_mode,
        "missing_message_clauses": missing_message_clauses,
        "passed": len(failure_reasons) == 0,
        "failure_reasons": failure_reasons,
    }


def render_control_plane_acceptance_markdown(report: dict[str, Any]) -> str:
    """Render one Markdown acceptance report for the installed control-plane jobs."""

    lines = [
        "# OpenClaw Control Plane Acceptance",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- jobs 文件：{report.get('jobs_file', '')}",
        f"- 检查结果：通过 {report.get('passed_job_count', 0)}/{report.get('checked_job_count', 0)}",
    ]
    missing_jobs = report.get("missing_jobs", [])
    failed_jobs = report.get("failed_jobs", [])
    if isinstance(missing_jobs, list) and missing_jobs:
        lines.append("- 缺失 job：" + ", ".join(str(item) for item in missing_jobs))
    if isinstance(failed_jobs, list) and failed_jobs:
        lines.append("- 校验失败 job：" + ", ".join(str(item) for item in failed_jobs))
    lines.extend(["", "## Job Checks"])
    job_checks = report.get("job_checks", [])
    if isinstance(job_checks, list) and job_checks:
        for item in job_checks:
            if not isinstance(item, dict):
                continue
            status = "PASS" if bool(item.get("passed", False)) else "FAIL"
            line = (
                f"- [{status}] {item.get('name', '')} -> delivery="
                f"{item.get('delivery_mode', '') or 'missing'}"
            )
            missing_message_clauses = item.get("missing_message_clauses", [])
            if isinstance(missing_message_clauses, list) and missing_message_clauses:
                line += "；缺失参数: " + ", ".join(str(part) for part in missing_message_clauses)
            if not bool(item.get("present", False)):
                line += "；缺失"
            elif not bool(item.get("enabled", False)):
                line += "；已禁用"
            lines.append(line)
    else:
        lines.append("- 当前无 job 检查结果")
    return "\n".join(lines).rstrip() + "\n"


def build_control_plane_acceptance_report(*, jobs_file: str | Path) -> dict[str, Any]:
    """Validate the installed control-plane jobs and return one structured report."""

    jobs_path = Path(jobs_file).expanduser()
    jobs = _load_jobs_payload(jobs_path)
    jobs_by_name = {
        str(item.get("name", "")).strip(): item
        for item in jobs
        if str(item.get("name", "")).strip()
    }
    job_checks = [
        _evaluate_required_job(spec=spec, jobs_by_name=jobs_by_name)
        for spec in REQUIRED_CONTROL_PLANE_JOBS
    ]
    missing_jobs = [
        str(item.get("name", "")).strip()
        for item in job_checks
        if not bool(item.get("present", False))
    ]
    failed_jobs = [
        str(item.get("name", "")).strip()
        for item in job_checks
        if bool(item.get("present", False)) and not bool(item.get("passed", False))
    ]
    passed_job_count = sum(1 for item in job_checks if bool(item.get("passed", False)))
    report = {
        "generated_at": utc_now_iso(),
        "jobs_file": str(jobs_path),
        "checked_job_count": len(job_checks),
        "present_job_count": sum(1 for item in job_checks if bool(item.get("present", False))),
        "passed_job_count": passed_job_count,
        "missing_jobs": missing_jobs,
        "failed_jobs": failed_jobs,
        "passed": len(missing_jobs) == 0 and len(failed_jobs) == 0,
        "job_checks": job_checks,
    }
    report["markdown"] = render_control_plane_acceptance_markdown(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the control-plane acceptance runner."""

    parser = argparse.ArgumentParser(description="Validate installed control-plane jobs.json.")
    parser.add_argument("--jobs-file", required=True)
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the generated acceptance payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_control_plane_acceptance_report(jobs_file=str(args.jobs_file).strip())
    payload = {"report": report}
    if str(args.json_output or "").strip():
        write_json_atomic(
            Path(str(args.json_output).strip()).expanduser(),
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            report["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(report["markdown"])
    return payload


if __name__ == "__main__":
    main()

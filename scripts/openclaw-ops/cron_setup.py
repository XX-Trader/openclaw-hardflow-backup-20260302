#!/usr/bin/env python3
"""Install OpenClaw hardflow cron jobs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from scheduled_runner_prompt import build_scheduled_runner_message
from io_write_gateway import write_json_atomic

try:
    from ops_cron_runner import default_config as runner_default_config
except Exception:  # pragma: no cover
    runner_default_config = None

LOG_MODES = {"silent", "chat"}
API_ENGINES = {"http", "playwright", "playwright-real", "selenium", "scrapling", "scrapling-stealth"}
INSTALL_PROFILES = {"legacy", "minimal", "standard", "aggressive"}
LEGACY_OPTIMIZE_JOB_MODES = {"auto", "keep", "disable", "remove"}
DAILY_REPORT_DEDUPE_MODES = {"auto", "keep", "disable-digest", "disable-daily-work"}
DEFAULT_FAILURE_ALERT_AFTER = 1
DEFAULT_FAILURE_ALERT_COOLDOWN_MS = 30 * 60 * 1000
DEFAULT_MAINTENANCE_CRON_MODEL = "glmcode/glm-4.7"
DEFAULT_WORKFLOW_MONITOR_IGNORED_JOB_NAMES = {
    "todo_patrol_15m",
    "project_index_maintainer_4h",
    "project_index_maintainer_30m",
    "ops_conversation_evolution_incremental",
    "ops_governance_evolution_incremental",
    "ops_github_web_evolution_incremental",
    "ops_git_sync_push",
    "ops_auto_update_install_hourly",
    "task_retry_10m",
    "web_intel_collect_hourly",
    "web_intel_review_optimization_4h",
    "web_intel_review_project_docs_6h",
}
LEGACY_OPTIMIZE_JOB_IDS = {
    "948d7307-6941-44ee-a8aa-57da767a31b7",  # optimization-agent 治理巡检 (external optimize_incremental_scan.py)
    "22b1712a-ff4a-4502-bce6-4e39c44cbe9f",  # optimize 自我进化总结 (external optimize_incremental_scan.py)
    "7e12c6d4-adb0-4ad4-83a6-58bffec8eb53",  # optimize 全量校准 (external optimize_full_calibration.py)
    "8f9102f4-d62c-4a01-85ef-1d393e2244de",  # optimize 频率策略管理 (external optimize_frequency_manager.py)
}
LEGACY_OPTIMIZE_COMMAND_HINTS = (
    "optimize_incremental_scan.py",
    "optimize_full_calibration.py",
    "optimize_frequency_manager.py",
)
DAILY_TODO_DIGEST_JOB_IDS = {"2ce5fe63-8316-4503-95e4-48515042b453"}
DAILY_TODO_DIGEST_COMMAND_HINTS = ("daily_todo_digest.py",)
DAILY_WORK_JOB_IDS = {"9873ab34-c4af-4db0-8cd5-40df68f92efd"}
PROFILE_BASELINE: dict[str, dict[str, int | str]] = {
    "legacy": {},
    "minimal": {
        "incremental_every_ms": 1800000,
        "auto_update_install_every_ms": 3600000,
        "full_expr": "23 */12 * * *",
        "conversation_every_ms": 28800000,
        "governance_every_ms": 28800000,
        "github_every_ms": 86400000,
    },
    "standard": {
        "incremental_every_ms": 1200000,
        "auto_update_install_every_ms": 3600000,
        "full_expr": "23 */8 * * *",
        "conversation_every_ms": 21600000,
        "governance_every_ms": 21600000,
        "github_every_ms": 43200000,
    },
    "aggressive": {
        "incremental_every_ms": 900000,
        "auto_update_install_every_ms": 3600000,
        "full_expr": "23 */6 * * *",
        "conversation_every_ms": 14400000,
        "governance_every_ms": 14400000,
        "github_every_ms": 21600000,
    },
}


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_official_cron_surface(job_ids: list[str]) -> dict[str, Any]:
    normalized = [str(job_id).strip() for job_id in job_ids if str(job_id).strip()]
    return {
        "surface": "official-cron",
        "status_cmd": "openclaw cron status --json",
        "run_cmds": {job_id: f"openclaw cron run {job_id} --force" for job_id in normalized},
        "runs_cmds": {job_id: f"openclaw cron runs --id {job_id} --limit 20" for job_id in normalized},
        "notes": [
            "业务 job 定义继续保存在 jobs.json。",
            "安装后的状态查询、启停与触发统一对齐官方 openclaw cron surface。",
        ],
    }


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_api_engine(value: str, default: str = "playwright-real") -> str:
    engine = str(value or "").strip().lower()
    return engine if engine in API_ENGINES else default


def prefer_existing_path(*candidates: Path) -> Path:
    if not candidates:
        raise ValueError("prefer_existing_path requires at least one candidate")
    for path in candidates:
        candidate = Path(path).expanduser()
        if candidate.exists():
            return candidate
    return Path(candidates[0]).expanduser()


def get_payload_message(job: dict[str, Any]) -> str:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("message", ""))


def is_legacy_optimize_job(job: dict[str, Any]) -> bool:
    job_id = str(job.get("id", "")).strip()
    if job_id in LEGACY_OPTIMIZE_JOB_IDS:
        return True
    message = get_payload_message(job).lower()
    return any(hint in message for hint in LEGACY_OPTIMIZE_COMMAND_HINTS)


def is_daily_todo_digest_job(job: dict[str, Any]) -> bool:
    job_id = str(job.get("id", "")).strip()
    if job_id in DAILY_TODO_DIGEST_JOB_IDS:
        return True
    message = get_payload_message(job).lower()
    return any(hint in message for hint in DAILY_TODO_DIGEST_COMMAND_HINTS)


def is_daily_work_report_job(job: dict[str, Any]) -> bool:
    job_id = str(job.get("id", "")).strip()
    if job_id in DAILY_WORK_JOB_IDS:
        return True
    return str(job.get("name", "")).strip() == "ops_daily_work_report_dingtalk"


def resolve_legacy_optimize_job_mode(mode: str, profile: str) -> str:
    normalized = str(mode or "auto").strip().lower()
    if normalized not in LEGACY_OPTIMIZE_JOB_MODES:
        normalized = "auto"
    if normalized == "auto":
        return "keep" if profile == "legacy" else "disable"
    return normalized


def resolve_daily_report_dedupe_mode(mode: str, profile: str, has_daily_work: bool) -> str:
    normalized = str(mode or "auto").strip().lower()
    if normalized not in DAILY_REPORT_DEDUPE_MODES:
        normalized = "auto"
    if normalized == "auto":
        if profile == "legacy":
            return "keep"
        return "disable-digest" if has_daily_work else "keep"
    return normalized


def apply_install_profile(args: argparse.Namespace) -> dict[str, Any]:
    profile = str(getattr(args, "install_profile", "legacy") or "legacy").strip().lower()
    if profile not in INSTALL_PROFILES:
        profile = "legacy"
    setattr(args, "install_profile", profile)

    changes: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []

    def set_arg(name: str, value: Any) -> None:
        old = getattr(args, name)
        if old != value:
            setattr(args, name, value)
            changes[name] = {"from": old, "to": value}

    def ensure_minimum(name: str, minimum: int) -> None:
        current = int(getattr(args, name))
        if current < minimum:
            set_arg(name, minimum)

    def enable_flag(name: str, *, when: bool, reason: str) -> None:
        if bool(getattr(args, name)):
            return
        if when:
            set_arg(name, True)
        else:
            skipped.append(reason)

    def governance_ready_for_install() -> bool:
        script_ok = Path(str(args.governance_evolution_py)).expanduser().is_file()
        registry_ok = Path(str(args.governance_evolution_project_registry)).expanduser().exists()
        repo_raw = str(args.governance_evolution_repo_path).strip()
        repo_ok = False
        if repo_raw:
            repo_path = Path(repo_raw).expanduser()
            repo_ok = repo_path.is_dir() and (repo_path / ".git").exists()
        return script_ok and (registry_ok or repo_ok)

    def git_sync_ready_for_install() -> bool:
        script_ok = Path(str(args.git_sync_py)).expanduser().is_file()
        repo_raw = str(args.git_sync_repo_path or "").strip()
        if not repo_raw:
            fallback = str(args.governance_evolution_repo_path or "").strip()
            if fallback:
                set_arg("git_sync_repo_path", fallback)
                repo_raw = fallback
        if not repo_raw:
            return False
        repo_path = Path(repo_raw).expanduser()
        return script_ok and repo_path.is_dir() and (repo_path / ".git").exists()

    def auto_update_install_ready_for_install() -> bool:
        script_ok = Path(str(args.auto_update_install_py)).expanduser().is_file()
        repo_raw = str(args.auto_update_install_repo_path or "").strip()
        if not repo_raw:
            fallback = str(args.governance_evolution_repo_path or "").strip()
            if fallback:
                set_arg("auto_update_install_repo_path", fallback)
                repo_raw = fallback
        if not repo_raw:
            return False
        repo_path = Path(repo_raw).expanduser()
        install_cmd_ok = bool(str(args.auto_update_install_install_cmd or "").strip())
        return script_ok and repo_path.is_dir() and (repo_path / ".git").exists() and install_cmd_ok

    if profile == "minimal":
        baseline = PROFILE_BASELINE["minimal"]
        ensure_minimum("incremental_every_ms", int(baseline["incremental_every_ms"]))
        set_arg("auto_update_install_every_ms", int(baseline["auto_update_install_every_ms"]))
        set_arg("full_expr", str(baseline["full_expr"]))
        ensure_minimum("governance_evolution_every_ms", int(baseline["governance_every_ms"]))
        ensure_minimum("conversation_evolution_every_ms", int(baseline["conversation_every_ms"]))
        ensure_minimum("github_web_evolution_every_ms", int(baseline["github_every_ms"]))

        governance_ready = governance_ready_for_install()
        enable_flag(
            "install_governance_evolution_job",
            when=governance_ready,
            reason="install_governance_evolution_job skipped: project-registry/repo-path missing",
        )
        enable_flag(
            "install_self_evolution_job",
            when=Path(str(args.self_evolution_py)).expanduser().is_file(),
            reason="install_self_evolution_job skipped: self-evolution script missing",
        )
        enable_flag(
            "install_upgrade_feedback_job",
            when=Path(str(args.upgrade_feedback_py)).expanduser().is_file(),
            reason="install_upgrade_feedback_job skipped: upgrade-feedback script missing",
        )
        enable_flag(
            "install_benchmark_sweep_job",
            when=Path(str(args.benchmark_sweep_py)).expanduser().is_file(),
            reason="install_benchmark_sweep_job skipped: benchmark-orchestrator script missing",
        )
        enable_flag(
            "install_benchmark_output_job",
            when=Path(str(args.benchmark_output_py)).expanduser().is_file(),
            reason="install_benchmark_output_job skipped: benchmark-output script missing",
        )
        enable_flag(
            "install_task_output_broadcast_job",
            when=Path(str(args.task_output_broadcast_py)).expanduser().is_file(),
            reason="install_task_output_broadcast_job skipped: task-output-broadcast script missing",
        )
        enable_flag(
            "install_control_plane_summary_job",
            when=Path(str(args.control_plane_summary_py)).expanduser().is_file(),
            reason="install_control_plane_summary_job skipped: control-plane-summary script missing",
        )
        enable_flag(
            "install_control_plane_dashboard_job",
            when=Path(str(args.control_plane_dashboard_py)).expanduser().is_file(),
            reason="install_control_plane_dashboard_job skipped: control-plane-dashboard script missing",
        )
        enable_flag(
            "install_control_plane_optimization_job",
            when=Path(str(args.control_plane_optimization_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_job skipped: control-plane-optimization script missing",
        )
        enable_flag(
            "install_control_plane_optimization_dispatch_job",
            when=Path(str(args.control_plane_optimization_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_dispatch_job skipped: control-plane-optimization-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_optimization_review_job",
            when=Path(str(args.control_plane_optimization_review_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_review_job skipped: control-plane-optimization-review script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_dispatch_job",
            when=Path(str(args.control_plane_profile_update_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_dispatch_job skipped: control-plane-profile-update-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_apply_job",
            when=Path(str(args.control_plane_profile_update_apply_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_apply_job skipped: control-plane-profile-update-apply script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_validation_job",
            when=Path(str(args.control_plane_profile_update_validation_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_validation_job skipped: control-plane-profile-update-validation script missing",
        )
        enable_flag(
            "install_control_plane_acceptance_job",
            when=Path(str(args.control_plane_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_acceptance_job skipped: control-plane-acceptance script missing",
        )
        enable_flag(
            "install_control_plane_live_acceptance_job",
            when=Path(str(args.control_plane_live_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_live_acceptance_job skipped: control-plane-live-acceptance script missing",
        )
        enable_flag(
            "install_git_sync_job",
            when=git_sync_ready_for_install(),
            reason="install_git_sync_job skipped: git-sync script missing or repo-path not git",
        )
        enable_flag(
            "install_auto_update_install_job",
            when=auto_update_install_ready_for_install(),
            reason="install_auto_update_install_job skipped: updater script/repo/install-cmd missing",
        )
    elif profile == "standard":
        baseline = PROFILE_BASELINE["standard"]
        ensure_minimum("incremental_every_ms", int(baseline["incremental_every_ms"]))
        set_arg("auto_update_install_every_ms", int(baseline["auto_update_install_every_ms"]))
        set_arg("full_expr", str(baseline["full_expr"]))
        ensure_minimum("governance_evolution_every_ms", int(baseline["governance_every_ms"]))
        ensure_minimum("conversation_evolution_every_ms", int(baseline["conversation_every_ms"]))
        ensure_minimum("github_web_evolution_every_ms", int(baseline["github_every_ms"]))

        governance_ready = governance_ready_for_install()
        enable_flag(
            "install_governance_evolution_job",
            when=governance_ready,
            reason="install_governance_evolution_job skipped: project-registry/repo-path missing",
        )
        skipped.append(
            "install_conversation_evolution_job skipped by policy: third-party memory mode keeps conversation evolution off by default"
        )
        enable_flag(
            "install_self_evolution_job",
            when=Path(str(args.self_evolution_py)).expanduser().is_file(),
            reason="install_self_evolution_job skipped: self-evolution script missing",
        )
        enable_flag(
            "install_upgrade_feedback_job",
            when=Path(str(args.upgrade_feedback_py)).expanduser().is_file(),
            reason="install_upgrade_feedback_job skipped: upgrade-feedback script missing",
        )
        enable_flag(
            "install_benchmark_sweep_job",
            when=Path(str(args.benchmark_sweep_py)).expanduser().is_file(),
            reason="install_benchmark_sweep_job skipped: benchmark-orchestrator script missing",
        )
        enable_flag(
            "install_benchmark_output_job",
            when=Path(str(args.benchmark_output_py)).expanduser().is_file(),
            reason="install_benchmark_output_job skipped: benchmark-output script missing",
        )
        enable_flag(
            "install_task_output_broadcast_job",
            when=Path(str(args.task_output_broadcast_py)).expanduser().is_file(),
            reason="install_task_output_broadcast_job skipped: task-output-broadcast script missing",
        )
        enable_flag(
            "install_control_plane_summary_job",
            when=Path(str(args.control_plane_summary_py)).expanduser().is_file(),
            reason="install_control_plane_summary_job skipped: control-plane-summary script missing",
        )
        enable_flag(
            "install_control_plane_dashboard_job",
            when=Path(str(args.control_plane_dashboard_py)).expanduser().is_file(),
            reason="install_control_plane_dashboard_job skipped: control-plane-dashboard script missing",
        )
        enable_flag(
            "install_control_plane_optimization_job",
            when=Path(str(args.control_plane_optimization_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_job skipped: control-plane-optimization script missing",
        )
        enable_flag(
            "install_control_plane_optimization_dispatch_job",
            when=Path(str(args.control_plane_optimization_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_dispatch_job skipped: control-plane-optimization-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_optimization_review_job",
            when=Path(str(args.control_plane_optimization_review_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_review_job skipped: control-plane-optimization-review script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_dispatch_job",
            when=Path(str(args.control_plane_profile_update_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_dispatch_job skipped: control-plane-profile-update-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_apply_job",
            when=Path(str(args.control_plane_profile_update_apply_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_apply_job skipped: control-plane-profile-update-apply script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_validation_job",
            when=Path(str(args.control_plane_profile_update_validation_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_validation_job skipped: control-plane-profile-update-validation script missing",
        )
        enable_flag(
            "install_control_plane_acceptance_job",
            when=Path(str(args.control_plane_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_acceptance_job skipped: control-plane-acceptance script missing",
        )
        enable_flag(
            "install_control_plane_live_acceptance_job",
            when=Path(str(args.control_plane_live_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_live_acceptance_job skipped: control-plane-live-acceptance script missing",
        )
        enable_flag(
            "install_git_sync_job",
            when=git_sync_ready_for_install(),
            reason="install_git_sync_job skipped: git-sync script missing or repo-path not git",
        )
        enable_flag(
            "install_auto_update_install_job",
            when=auto_update_install_ready_for_install(),
            reason="install_auto_update_install_job skipped: updater script/repo/install-cmd missing",
        )
    elif profile == "aggressive":
        baseline = PROFILE_BASELINE["aggressive"]
        ensure_minimum("incremental_every_ms", int(baseline["incremental_every_ms"]))
        set_arg("auto_update_install_every_ms", int(baseline["auto_update_install_every_ms"]))
        set_arg("full_expr", str(baseline["full_expr"]))
        ensure_minimum("governance_evolution_every_ms", int(baseline["governance_every_ms"]))
        ensure_minimum("conversation_evolution_every_ms", int(baseline["conversation_every_ms"]))
        ensure_minimum("github_web_evolution_every_ms", int(baseline["github_every_ms"]))

        governance_ready = governance_ready_for_install()
        enable_flag(
            "install_governance_evolution_job",
            when=governance_ready,
            reason="install_governance_evolution_job skipped: project-registry/repo-path missing",
        )
        skipped.append(
            "install_conversation_evolution_job skipped by policy: third-party memory mode keeps conversation evolution off by default"
        )
        skipped.append(
            "install_github_web_evolution_job not auto-enabled by profile: pass --install-github-web-evolution-job when you explicitly need external knowledge evolution"
        )
        enable_flag(
            "install_self_evolution_job",
            when=Path(str(args.self_evolution_py)).expanduser().is_file(),
            reason="install_self_evolution_job skipped: self-evolution script missing",
        )
        enable_flag(
            "install_upgrade_feedback_job",
            when=Path(str(args.upgrade_feedback_py)).expanduser().is_file(),
            reason="install_upgrade_feedback_job skipped: upgrade-feedback script missing",
        )
        enable_flag(
            "install_benchmark_sweep_job",
            when=Path(str(args.benchmark_sweep_py)).expanduser().is_file(),
            reason="install_benchmark_sweep_job skipped: benchmark-orchestrator script missing",
        )
        enable_flag(
            "install_benchmark_output_job",
            when=Path(str(args.benchmark_output_py)).expanduser().is_file(),
            reason="install_benchmark_output_job skipped: benchmark-output script missing",
        )
        enable_flag(
            "install_task_output_broadcast_job",
            when=Path(str(args.task_output_broadcast_py)).expanduser().is_file(),
            reason="install_task_output_broadcast_job skipped: task-output-broadcast script missing",
        )
        enable_flag(
            "install_control_plane_summary_job",
            when=Path(str(args.control_plane_summary_py)).expanduser().is_file(),
            reason="install_control_plane_summary_job skipped: control-plane-summary script missing",
        )
        enable_flag(
            "install_control_plane_dashboard_job",
            when=Path(str(args.control_plane_dashboard_py)).expanduser().is_file(),
            reason="install_control_plane_dashboard_job skipped: control-plane-dashboard script missing",
        )
        enable_flag(
            "install_control_plane_optimization_job",
            when=Path(str(args.control_plane_optimization_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_job skipped: control-plane-optimization script missing",
        )
        enable_flag(
            "install_control_plane_optimization_dispatch_job",
            when=Path(str(args.control_plane_optimization_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_dispatch_job skipped: control-plane-optimization-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_optimization_review_job",
            when=Path(str(args.control_plane_optimization_review_py)).expanduser().is_file(),
            reason="install_control_plane_optimization_review_job skipped: control-plane-optimization-review script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_dispatch_job",
            when=Path(str(args.control_plane_profile_update_dispatch_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_dispatch_job skipped: control-plane-profile-update-dispatch script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_apply_job",
            when=Path(str(args.control_plane_profile_update_apply_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_apply_job skipped: control-plane-profile-update-apply script missing",
        )
        enable_flag(
            "install_control_plane_profile_update_validation_job",
            when=Path(str(args.control_plane_profile_update_validation_py)).expanduser().is_file(),
            reason="install_control_plane_profile_update_validation_job skipped: control-plane-profile-update-validation script missing",
        )
        enable_flag(
            "install_control_plane_acceptance_job",
            when=Path(str(args.control_plane_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_acceptance_job skipped: control-plane-acceptance script missing",
        )
        enable_flag(
            "install_control_plane_live_acceptance_job",
            when=Path(str(args.control_plane_live_acceptance_py)).expanduser().is_file(),
            reason="install_control_plane_live_acceptance_job skipped: control-plane-live-acceptance script missing",
        )
        enable_flag(
            "install_git_sync_job",
            when=git_sync_ready_for_install(),
            reason="install_git_sync_job skipped: git-sync script missing or repo-path not git",
        )
        enable_flag(
            "install_auto_update_install_job",
            when=auto_update_install_ready_for_install(),
            reason="install_auto_update_install_job skipped: updater script/repo/install-cmd missing",
        )

    return {"profile": profile, "changes": changes, "skipped": skipped}


def apply_legacy_optimize_job_policy(
    jobs: list[dict[str, Any]],
    mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mode = str(mode or "keep").strip().lower()
    if mode not in {"keep", "disable", "remove"}:
        mode = "keep"
    summary = {
        "mode": mode,
        "matched": 0,
        "disabled": 0,
        "removed": 0,
        "jobs": [],
    }
    if mode == "keep":
        return jobs, summary

    ts = now_ms()
    kept: list[dict[str, Any]] = []
    for item in jobs:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if not is_legacy_optimize_job(item):
            kept.append(item)
            continue

        summary["matched"] += 1
        detail = {"id": str(item.get("id", "")), "name": str(item.get("name", ""))}
        if mode == "remove":
            summary["removed"] += 1
            summary["jobs"].append({**detail, "action": "removed"})
            continue

        if bool(item.get("enabled", True)):
            item["enabled"] = False
            item["updatedAtMs"] = ts
            summary["disabled"] += 1
            summary["jobs"].append({**detail, "action": "disabled"})
        else:
            summary["jobs"].append({**detail, "action": "already_disabled"})
        kept.append(item)
    return kept, summary


def apply_daily_report_dedupe_policy(
    jobs: list[dict[str, Any]],
    mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mode = str(mode or "keep").strip().lower()
    if mode not in {"keep", "disable-digest", "disable-daily-work"}:
        mode = "keep"
    summary = {
        "mode": mode,
        "matched": 0,
        "disabled": 0,
        "jobs": [],
    }
    if mode == "keep":
        return jobs, summary

    ts = now_ms()
    target_matcher = is_daily_todo_digest_job if mode == "disable-digest" else is_daily_work_report_job

    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not target_matcher(item):
            continue
        summary["matched"] += 1
        detail = {"id": str(item.get("id", "")), "name": str(item.get("name", ""))}
        if bool(item.get("enabled", True)):
            item["enabled"] = False
            item["updatedAtMs"] = ts
            summary["disabled"] += 1
            summary["jobs"].append({**detail, "action": "disabled"})
        else:
            summary["jobs"].append({**detail, "action": "already_disabled"})
    return jobs, summary


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs file must be a JSON object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def infer_delivery(jobs: list[dict[str, Any]], preferred_agents: list[str]) -> tuple[str, str]:
    for aid in preferred_agents:
        for job in jobs:
            if str(job.get("agentId", "")).strip() != aid:
                continue
            delivery = job.get("delivery") or {}
            channel = str(delivery.get("channel", "")).strip()
            target = str(delivery.get("to", "")).strip()
            if channel and target:
                return channel, target
    return "telegram", ""


def ensure_monitor_config(config_file: Path, overwrite: bool, switches: dict[str, str]) -> dict[str, Any]:
    home = Path(os.path.expanduser("~"))
    if config_file.exists() and not overwrite:
        data = json.loads(config_file.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            data = {}
    else:
        base = runner_default_config() if callable(runner_default_config) else {}
        if isinstance(base, dict):
            data = base
        else:
            data = {
                "schema_version": "2026-03-02",
                "log_roots": [
                    str(home / ".openclaw/workspace-ops-agent/ops"),
                    str(home / ".openclaw/workspace-ops-agent/ops/logs"),
                    str(home / ".openclaw/workflows"),
                ],
                "log_patterns": ["*.log", "**/*.log", "*.out", "**/*.out"],
                "max_log_files": 120,
                "incremental_max_bytes_per_file": 262144,
                "full_scan_tail_bytes_per_file": 1048576,
                "auto_resolve_after_missed_runs": 2,
                "fallback_full_on_incremental_error": True,
                "incremental_full_backstop_runs": 96,
                "daily": {"major_only": True, "window_hours": 24, "top_issue_limit": 8},
            }

    current = data.get("skill_log_switches")
    if not isinstance(current, dict):
        current = {}
    for skill, mode in switches.items():
        node = current.get(skill)
        if not isinstance(node, dict):
            node = {}
        node["normal_log_mode"] = normalize_log_mode(mode, default="silent")
        node["risk_always_notify"] = True
        current[skill] = node
    data["skill_log_switches"] = current

    notify_policy = data.get("notify_policy")
    if not isinstance(notify_policy, dict):
        notify_policy = {}
    quiet_defaults = {
        "silent_notify_on_change": False,
        "chat_notify_on_change": False,
        "chat_notify_on_no_change": False,
        "daily_silent_notify_on_change": False,
        "daily_chat_notify_on_change": False,
        "daily_chat_notify_on_no_change": False,
        "risk_repeat_cooldown_minutes": 60,
    }
    for key, value in quiet_defaults.items():
        notify_policy.setdefault(key, value)
    data["notify_policy"] = notify_policy
    data.setdefault("errors_only_notify", True)

    runtime_monitor = data.get("runtime_monitor")
    if not isinstance(runtime_monitor, dict):
        runtime_monitor = {}
    runtime_defaults = {
        "enabled": True,
        "project_registry": str(home / ".openclaw" / "ops" / "task-center" / "project-registry.json"),
        "max_projects": 24,
        "max_items_per_project": 12,
        "process_timeout_seconds": 15,
        "service_timeout_seconds": 10,
    }
    for key, value in runtime_defaults.items():
        runtime_monitor.setdefault(key, value)
    data["runtime_monitor"] = runtime_monitor

    workflow_monitor = data.get("workflow_monitor")
    if not isinstance(workflow_monitor, dict):
        workflow_monitor = {}
    workflow_defaults = {
        "enabled": True,
        "jobs_file": str(home / ".openclaw" / "cron" / "jobs.json"),
        "max_report_jobs": 8,
        "stale_error_minutes": 30,
        "ignore_job_names": sorted(DEFAULT_WORKFLOW_MONITOR_IGNORED_JOB_NAMES),
    }
    for key, value in workflow_defaults.items():
        workflow_monitor.setdefault(key, value)
    ignore_job_names = workflow_monitor.get("ignore_job_names")
    if not isinstance(ignore_job_names, list):
        ignore_job_names = []
    merged_ignore_names = {
        str(item).strip()
        for item in [*ignore_job_names, *sorted(DEFAULT_WORKFLOW_MONITOR_IGNORED_JOB_NAMES)]
        if str(item).strip()
    }
    workflow_monitor["ignore_job_names"] = sorted(merged_ignore_names)
    data["workflow_monitor"] = workflow_monitor

    incident_handoff = data.get("incident_handoff")
    if not isinstance(incident_handoff, dict):
        incident_handoff = {}
    handoff_defaults = {
        "enabled": True,
        "mode": "todo_only",
        "todo_file": str(home / ".openclaw" / "workspace-coordinator" / "TODO.md"),
        "routing_file": str(home / ".openclaw" / "ops" / "policy" / "routing-rules.json"),
        "source": "ops-cron-runner",
        "default_assignee": "coordinator",
        "max_handoff_per_run": 6,
        "max_issue_items_per_run": 4,
        "max_workflow_jobs_per_run": 2,
        "high_risk_direct_human": True,
        "write_medium_risk_to_todo": False,
    }
    for key, value in handoff_defaults.items():
        incident_handoff.setdefault(key, value)
    data["incident_handoff"] = incident_handoff

    write_json_atomic(
        config_file,
        data,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )
    return data


def build_message(command: str, extra_rules: list[str] | None = None) -> str:
    rules = [
        "Do not run unrelated follow-up diagnostics (for example: ls/cat/read/lsof/rm).",
    ]
    if isinstance(extra_rules, list):
        for item in extra_rules:
            text = str(item or "").strip()
            if text:
                rules.append(text)
    return build_scheduled_runner_message(
        str(command or "").strip(),
        role="scheduled runner",
        extra_rules=rules,
    )


def build_delivery(*, mode: str = "announce") -> dict[str, str]:
    return {"mode": str(mode or "announce").strip() or "announce"}


def build_failure_alert() -> dict[str, Any]:
    return {
        "after": DEFAULT_FAILURE_ALERT_AFTER,
        "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS,
    }


def infer_openclaw_home_from_jobs_file(jobs_file: Path) -> Path:
    jobs_path = jobs_file.expanduser().resolve()
    if jobs_path.parent.name == "cron":
        return jobs_path.parent.parent
    return jobs_path.parent


def harden_known_jobs(jobs: list[dict[str, Any]], openclaw_home: Path) -> dict[str, Any]:
    """Harden legacy jobs that frequently fail due path/tool drift."""
    openclaw_home = openclaw_home.expanduser()
    ops_dir = openclaw_home / "ops"
    workspace_dir = openclaw_home / "workspace"
    log_watcher_job_ids = {"fd8ae471-69f7-4bb5-9d2e-46aa26b092f1"}
    # Include mojibake aliases observed on mixed-encoding terminals.
    log_watcher_name_aliases = {
        "log-watcher agent（双项目）",
        "log-watcher agent锛堝弻椤圭洰锛?",
        "log-watcher agent閿涘牆寮绘い鍦窗閿?",
    }
    known: dict[str, dict[str, Any]] = {
        "log-watcher agent（双项目）": {
            "description": "log-watcher command-runner (stable no-edit mode, single-instance lock)",
            "command": (
                "bash -lc '"
                f"mkdir -p {openclaw_home / 'workspace-ops-agent' / 'ops'} && "
                f"LOCK={openclaw_home / 'workspace-ops-agent' / 'ops' / 'alert-dedupe-state.lock'} && "
                f"flock -xn -E 75 \"$LOCK\" python3 {openclaw_home / 'workspace-ops-agent' / 'ops' / 'log-watcher.py'}; "
                "rc=$?; "
                "if [ \"$rc\" -eq 75 ]; then echo NO_REPLY; exit 0; fi; "
                "exit \"$rc\""
                "'"
            ),
            "timeout": 900,
        },
        "daily_todo_digest_daily": {
            "description": "Daily TODO digest (stable script path, run-only hard mode)",
            "command": (
                f"python3 {ops_dir / 'daily_todo_digest.py'} "
                f"--db {ops_dir / 'task-center' / 'task_center.db'} "
                f"--state-file {ops_dir / 'daily-todo-digest' / 'state.json'} "
                f"--report-dir {ops_dir / 'daily-todo-digest' / 'reports'} "
                "--task-id cron:daily-todo-digest --normal-log-mode silent"
            ),
            "timeout": 1200,
        },
        "project_index_maintainer_4h": {
            "description": "Project index maintainer (stable python runner, compact failure output)",
            "command": (
                f"python3 {ops_dir / 'policy' / 'project_index_maintainer.py'} "
                f"--registry {ops_dir / 'task-center' / 'project-registry.json'} "
                f"--task-db {ops_dir / 'task-center' / 'task_center.db'} "
                "--task-id cron:project-index-maintainer-4h --actor project-agent "
                "--doc-timeout 8 --doc-fetch-max-chars 24000 --disable-memory-index-on-change"
            ),
            "timeout": 1800,
        },
    }
    log_watcher_spec = next(
        (
            spec
            for key, spec in known.items()
            if str(key).startswith("log-watcher agent")
        ),
        None,
    )
    if isinstance(log_watcher_spec, dict):
        for alias in sorted(log_watcher_name_aliases):
            known[alias] = log_watcher_spec
    project_index_spec = known.get("project_index_maintainer_4h")
    if isinstance(project_index_spec, dict):
        known["project_index_maintainer_30m"] = project_index_spec

    status: dict[str, str] = {}
    refs: list[str] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        job_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        spec = known.get(name)
        if spec is None and job_id in log_watcher_job_ids and isinstance(log_watcher_spec, dict):
            spec = log_watcher_spec
        if spec is None:
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        payload["kind"] = "agentTurn"
        extra_rules: list[str] = []
        if job_id in log_watcher_job_ids or name in log_watcher_name_aliases:
            extra_rules = [
                "The flock lock guard is expected. NO_REPLY is a valid successful outcome.",
                "Do not attempt to inspect or remove lock/state files.",
                "Do not retry or rerun the command in this turn.",
            ]
        payload["message"] = build_message(str(spec["command"]), extra_rules=extra_rules)
        payload["timeoutSeconds"] = int(spec["timeout"])
        item["payload"] = payload
        item["description"] = str(spec["description"])
        status[name or job_id] = "hardened"

        try:
            cmd_parts = str(spec["command"]).split()
            if len(cmd_parts) >= 2 and cmd_parts[0].startswith("python"):
                refs.append(cmd_parts[1])
        except Exception:
            pass

    missing_refs: list[str] = []
    for path in sorted(set(refs)):
        p = Path(path).expanduser()
        if not p.exists():
            missing_refs.append(str(p))
    return {"status": status, "missing_refs": missing_refs}


def build_core_jobs(
    *,
    runner_py: str,
    config_file: str,
    state_file: str,
    history_dir: str,
    every_ms: int,
    full_expr: str,
    daily_expr: str,
    tz_name: str,
    daily_major_only: bool,
    incremental_log_mode: str,
    full_log_mode: str,
    daily_log_mode: str,
) -> list[dict[str, Any]]:
    ts = now_ms()
    cmd_base = f"python3 {runner_py} --config {config_file} --state-file {state_file} --history-dir {history_dir}"
    cmd_inc = (
        f"{cmd_base} --mode incremental --task-id cron:ops-incremental-monitor "
        f"--normal-log-mode {normalize_log_mode(incremental_log_mode)}"
    )
    cmd_full = (
        f"{cmd_base} --mode full --task-id cron:ops-full-calibration "
        f"--normal-log-mode {normalize_log_mode(full_log_mode)}"
    )
    cmd_daily = (
        f"{cmd_base} --mode daily --task-id cron:ops-daily-summary "
        f"--normal-log-mode {normalize_log_mode(daily_log_mode)}"
    )
    if daily_major_only:
        cmd_daily += " --daily-major-only"

    return [
        {
            "id": "c9a4f4c4-4f47-4da3-a571-6bc7c3fbd2f8",
            "agentId": "ops-agent",
            "name": "ops_incremental_monitor",
            "description": "增量日志巡检与问题闭环（可配置日志开关）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_inc), "timeoutSeconds": 1800},
        },
        {
            "id": "9bd05850-bca8-4a0a-af67-67e2d5d2af9f",
            "agentId": "ops-agent",
            "name": "ops_full_calibration",
            "description": "全量校准扫描（增量异常自动回退兜底）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": full_expr, "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_full), "timeoutSeconds": 2400},
        },
        {
            "id": "621ee42b-efef-4ac7-88db-4971bb9a7f86",
            "agentId": "ops-agent",
            "name": "ops_daily_summary",
            "description": "每日日报汇总（可配置日志开关）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": daily_expr, "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_daily), "timeoutSeconds": 1800},
            "delivery": build_delivery(mode="none"),
        },
    ]


def build_system_schedule_job(
    *,
    script_py: str,
    output_dir: str,
    state_file: str,
    every_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --output-dir {output_dir} --state-file {state_file} "
        f"--task-id cron:ops-system-schedule-audit --normal-log-mode {normalize_log_mode(log_mode)}"
    )
    return {
        "id": "f603d2ac-2dcf-4f7a-9efe-26f0e0f8d24e",
        "agentId": "ops-agent",
        "name": "ops_system_schedule_audit",
        "description": "系统定时+OpenClaw定时快照审计（高风险强制提醒）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1200},
    }


def build_api_test_job(
    *,
    script_py: str,
    config_file: str,
    state_file: str,
    history_dir: str,
    expr: str,
    tz_name: str,
    engine: str,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --config-file {config_file} --state-file {state_file} --history-dir {history_dir} "
        f"--task-id cron:ops-api-test --engine {normalize_api_engine(engine)} "
        f"--normal-log-mode {normalize_log_mode(log_mode)}"
    )
    return {
        "id": "1a45d6d8-8dde-4fc7-b25e-45c3f57ec31e",
        "agentId": "ops-agent",
        "name": "ops_api_test_audit",
        "description": "接口全量测试（一次执行，无重复重测），空返回/旧数据高风险",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1800},
    }


def build_daily_work_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    report_dir: str,
    expr: str,
    tz_name: str,
    log_mode: str,
    webhook_env: str,
    secret_env: str,
    env_file: str,
    todo_files: list[str] | None = None,
) -> dict[str, Any]:
    ts = now_ms()
    todo_args = " ".join(
        f" --todo-file {str(item).strip()}"
        for item in (todo_files or [])
        if str(item or "").strip()
    )
    cmd = (
        f"python3 {script_py} --db {db_file} --state-file {state_file} --report-dir {report_dir} "
        f"--task-id cron:ops-daily-work-report --normal-log-mode {normalize_log_mode(log_mode)} "
        f"--dingtalk-webhook-env {webhook_env} --dingtalk-secret-env {secret_env} "
        f"--env-file {env_file}{todo_args}"
    )
    return {
        "id": "9873ab34-c4af-4db0-8cd5-40df68f92efd",
        "agentId": "ops-agent",
        "name": "ops_daily_work_report_dingtalk",
        "description": "每日工作报告（todo/done 增量去重，仅新增记录推送钉钉）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 1200,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_self_evolution_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    report_dir: str,
    expr: str,
    tz_name: str,
    log_mode: str,
    lookback_days: int,
    min_review_interval_days: int,
    max_tasks_per_run: int,
    agent_score_threshold: float,
    agent_score_min_reports: int,
    agent_score_top_n: int,
    low_score_guarantee_enabled: bool,
    low_score_guarantee_min_agents: int,
    low_score_guarantee_max_agents: int,
    low_score_guarantee_threshold: float,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --db {db_file} --state-file {state_file} --report-dir {report_dir} "
        f"--task-id cron:ops-self-evolution --normal-log-mode {normalize_log_mode(log_mode)} "
        f"--lookback-days {max(1, int(lookback_days))} "
        f"--min-review-interval-days {max(1, int(min_review_interval_days))} "
        f"--max-tasks-per-run {max(1, int(max_tasks_per_run))} "
        f"--agent-score-threshold {max(1.0, min(float(agent_score_threshold), 100.0))} "
        f"--agent-score-min-reports {max(1, int(agent_score_min_reports))} "
        f"--agent-score-top-n {max(1, int(agent_score_top_n))} "
        f"--{'low-score-guarantee-enabled' if bool(low_score_guarantee_enabled) else 'no-low-score-guarantee-enabled'} "
        f"--low-score-guarantee-min-agents {max(1, int(low_score_guarantee_min_agents))} "
        f"--low-score-guarantee-max-agents {max(1, int(low_score_guarantee_max_agents))} "
        f"--low-score-guarantee-threshold {max(1.0, min(float(low_score_guarantee_threshold), 100.0))}"
    )
    return {
        "id": "9cf2677f-0ea1-4f07-a8cb-7dff4ff7c52b",
        "agentId": "ops-agent",
        "name": "ops_self_evolution_weekly_todo",
        "description": "周度自我进化复盘（只产出建议任务包到TODO，低优先级，人工确认）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1800},
        "delivery": build_delivery(mode="none"),
    }


def build_upgrade_feedback_job(
    *,
    script_py: str,
    executor_run_dir: str,
    output_dir: str,
    state_file: str,
    workflow_profile_registry: str,
    benchmark_suite_file: str,
    benchmark_suite_id: str,
    every_ms: int,
    log_mode: str,
    workflow_target: str,
    skill_name: str,
    skill_assignee: str,
    baseline_count: int,
    candidate_count: int,
    task_db: str,
    auto_create_tasks: bool,
    auto_apply_workflow_promotion: bool,
    promotion_operator: str,
    task_score_threshold: float,
    task_schedule_gap_minutes: int,
) -> dict[str, Any]:
    ts = now_ms()
    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" --executor-run-dir \"{executor_run_dir}\" "
        f"--output-dir \"{output_dir}\" --state-file \"{state_file}\" "
        f"--workflow-target {q(str(workflow_target).strip() or 'task_executor_10m')} "
        f"--skill-name {q(str(skill_name).strip() or 'openclaw-evolution-upgrader')} "
        f"--skill-assignee {q(str(skill_assignee).strip() or 'optimization-agent')} "
        f"--baseline-count {max(1, int(baseline_count))} "
        f"--candidate-count {max(1, int(candidate_count))} "
        f"--task-db {q(str(task_db).strip())} "
        f"{f'--workflow-profile-registry {q(str(workflow_profile_registry).strip())} ' if str(workflow_profile_registry).strip() else ''}"
        f"{f'--benchmark-suite-file {q(str(benchmark_suite_file).strip())} ' if str(benchmark_suite_file).strip() else ''}"
        f"{f'--benchmark-suite-id {q(str(benchmark_suite_id).strip())} ' if str(benchmark_suite_id).strip() else ''}"
        f"{'--auto-create-tasks' if bool(auto_create_tasks) else '--no-auto-create-tasks'} "
        f"{'--auto-apply-workflow-promotion' if bool(auto_apply_workflow_promotion) else '--no-auto-apply-workflow-promotion'} "
        f"--promotion-operator {q(str(promotion_operator).strip() or 'upgrade-feedback-runner')} "
        f"--task-score-threshold {max(0.0, min(float(task_score_threshold), 100.0))} "
        f"--task-schedule-gap-minutes {max(1, int(task_schedule_gap_minutes))}"
    )
    return {
        "id": "0bdb11dd-1594-4c06-a40e-b428c3a4df55",
        "agentId": "ops-agent",
        "name": "ops_upgrade_feedback_daily",
        "description": "升级反馈汇总：从 executor runs 生成 workflow scorecard 与 skill review",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts,
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 1200,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_benchmark_sweep_job(
    *,
    script_py: str,
    executor_run_dir: str,
    output_root: str,
    state_root: str,
    benchmark_suite_file: str,
    workflow_profile_registry: str,
    task_db: str,
    output_consumer_py: str,
    summary_file: str,
    consumer_output_file: str,
    consumer_notify_on: str,
    every_ms: int,
    log_mode: str,
    auto_create_tasks: bool,
    auto_apply_workflow_promotion: bool,
    promotion_operator: str,
    task_score_threshold: float,
    task_schedule_gap_minutes: int,
    suite_ids: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    suite_args = "".join(
        f"--suite-id {q(str(item).strip())} "
        for item in suite_ids
        if str(item).strip()
    )
    benchmark_cmd = (
        f"python3 \"{script_py}\" run-all "
        f"--executor-run-dir \"{executor_run_dir}\" "
        f"--output-root \"{output_root}\" "
        f"--state-root \"{state_root}\" "
        f"{f'--benchmark-suite-file {q(str(benchmark_suite_file).strip())} ' if str(benchmark_suite_file).strip() else ''}"
        f"{f'--workflow-profile-registry {q(str(workflow_profile_registry).strip())} ' if str(workflow_profile_registry).strip() else ''}"
        f"{f'--task-db {q(str(task_db).strip())} ' if str(task_db).strip() else ''}"
        f"{'--auto-create-tasks' if bool(auto_create_tasks) else '--no-auto-create-tasks'} "
        f"{'--auto-apply-workflow-promotion' if bool(auto_apply_workflow_promotion) else '--no-auto-apply-workflow-promotion'} "
        f"--promotion-operator {q(str(promotion_operator).strip() or 'benchmark-orchestrator')} "
        f"--task-score-threshold {max(0.0, min(float(task_score_threshold), 100.0))} "
        f"--task-schedule-gap-minutes {max(1, int(task_schedule_gap_minutes))} "
        f"{suite_args}".rstrip()
    )
    notify_mode = str(consumer_notify_on or "error").strip().lower()
    if notify_mode not in {"error", "activity", "always"}:
        notify_mode = "error"
    consumer_cmd = ""
    if str(output_consumer_py).strip():
        consumer_cmd = (
            " && "
            f"python3 \"{output_consumer_py}\" "
            f"{f'--summary-file {q(str(summary_file).strip())} ' if str(summary_file).strip() else ''}"
            f"--notify-on {q(notify_mode)} "
            f"{f'--output {q(str(consumer_output_file).strip())} ' if str(consumer_output_file).strip() else ''}"
        ).rstrip()
    cmd = f"{benchmark_cmd}{consumer_cmd}"
    return {
        "id": "3c0f8cb2-7793-4d5a-9b4e-223dc0a698ea",
        "agentId": "ops-agent",
        "name": "ops_benchmark_sweep_daily",
        "description": "benchmark sweep：批量执行多工作流基准集并固化控制面摘要",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts,
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 1800,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_benchmark_output_job(
    *,
    script_py: str,
    summary_file: str,
    output_file: str,
    notify_on: str,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    notify_mode = str(notify_on or "error").strip().lower()
    if notify_mode not in {"error", "activity", "always"}:
        notify_mode = "error"

    cmd = (
        f"python3 \"{script_py}\" "
        f"{f'--summary-file {q(str(summary_file).strip())} ' if str(summary_file).strip() else ''}"
        f"--notify-on {q(notify_mode)} "
        f"{f'--output {q(str(output_file).strip())} ' if str(output_file).strip() else ''}"
    ).rstrip()
    return {
        "id": "6e6b677d-f912-47af-b65c-a31a8db82c94",
        "agentId": "ops-agent",
        "name": "ops_benchmark_output_daily",
        "description": "benchmark 输出公告：把最新 benchmark sweep 摘要渲染成统一通知文本",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="announce"),
    }


def build_task_output_broadcast_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    output_file: str,
    lookback_hours: int,
    limit: int,
    event_limit: int,
    notify_on: str,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    notify_mode = str(notify_on or "error").strip().lower()
    if notify_mode not in {"error", "activity", "always"}:
        notify_mode = "error"

    cmd = (
        f"python3 \"{script_py}\" "
        f"--db {q(str(db_file).strip())} "
        f"--state-file {q(str(state_file).strip())} "
        f"--output {q(str(output_file).strip())} "
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))} "
        f"--event-limit {max(20, int(event_limit))} "
        f"--notify-on {q(notify_mode)}"
    ).rstrip()
    return {
        "id": "d69be6a2-8619-4476-9178-cb63f4ab56f8",
        "agentId": "ops-agent",
        "name": "ops_task_output_broadcast_15m",
        "description": "task 控制面广播：批量扫描最近变更任务并公告新的控制面事件",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(300000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="announce"),
    }


def build_control_plane_summary_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    output_file: str,
    lookback_hours: int,
    limit: int,
    notify_on: str,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    notify_mode = str(notify_on or "activity").strip().lower()
    if notify_mode not in {"error", "activity", "always"}:
        notify_mode = "activity"

    cmd = (
        f"python3 \"{script_py}\" "
        f"--db {q(str(db_file).strip())} "
        f"--state-file {q(str(state_file).strip())} "
        f"--output {q(str(output_file).strip())} "
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))} "
        f"--notify-on {q(notify_mode)}"
    ).rstrip()
    return {
        "id": "c7d52a06-6f78-4a58-a75c-e2d9d9018561",
        "agentId": "ops-agent",
        "name": "ops_control_plane_summary_6h",
        "description": "控制面汇总：聚合最近 task/incident/benchmark/promotion 信号并生成运营摘要",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="announce"),
    }


def build_control_plane_dashboard_job(
    *,
    script_py: str,
    db_file: str,
    benchmark_summary_file: str,
    json_output: str,
    markdown_output: str,
    html_output: str,
    lookback_hours: int,
    limit: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--db {q(str(db_file).strip())} "
        f"{f'--benchmark-summary-file {q(str(benchmark_summary_file).strip())} ' if str(benchmark_summary_file).strip() else ''}"
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"{f'--html-output {q(str(html_output).strip())} ' if str(html_output).strip() else ''}"
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))}"
    ).rstrip()
    return {
        "id": "401e118b-0e92-423c-b255-45746997b1e8",
        "agentId": "ops-agent",
        "name": "ops_control_plane_dashboard_6h",
        "description": "控制面看板快照：定期生成 dashboard JSON/Markdown 快照文件",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_optimization_job(
    *,
    script_py: str,
    db_file: str,
    json_output: str,
    markdown_output: str,
    lookback_hours: int,
    limit: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--db {q(str(db_file).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))}"
    ).rstrip()
    return {
        "id": "6ab36dff-3809-465d-befa-9424b6c4088c",
        "agentId": "ops-agent",
        "name": "ops_control_plane_optimization_12h",
        "description": "控制面优化建议：定期生成阶段裁剪、并行和门禁强化建议报告",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_optimization_dispatch_job(
    *,
    script_py: str,
    report_file: str,
    task_db: str,
    json_output: str,
    markdown_output: str,
    execution_workflow_profile: str,
    execution_workflow_channel: str,
    schedule_gap_minutes: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--report-file {q(str(report_file).strip())} "
        f"--task-db {q(str(task_db).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--execution-workflow-profile {q(str(execution_workflow_profile).strip())} "
        f"--execution-workflow-channel {q(str(execution_workflow_channel).strip())} "
        f"--schedule-gap-minutes {max(0, int(schedule_gap_minutes))}"
    ).rstrip()
    return {
        "id": "e85e75c1-41b4-44df-a6ff-4a699e6f949b",
        "agentId": "ops-agent",
        "name": "ops_control_plane_optimization_dispatch_12h",
        "description": "控制面优化建议派发：把 advisor 报告转成 task-center 正式任务",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_optimization_review_job(
    *,
    script_py: str,
    task_db: str,
    json_output: str,
    markdown_output: str,
    lookback_hours: int,
    limit: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--task-db {q(str(task_db).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))}"
    ).rstrip()
    return {
        "id": "471307bc-d7fb-401c-ae7e-c2242986510f",
        "agentId": "ops-agent",
        "name": "ops_control_plane_optimization_review_12h",
        "description": "控制面优化任务复盘：汇总已派发 optimization task 的执行结果与可晋升候选",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_profile_update_dispatch_job(
    *,
    script_py: str,
    review_file: str,
    task_db: str,
    json_output: str,
    markdown_output: str,
    execution_workflow_profile: str,
    execution_workflow_channel: str,
    schedule_gap_minutes: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--review-file {q(str(review_file).strip())} "
        f"--task-db {q(str(task_db).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--execution-workflow-profile {q(str(execution_workflow_profile).strip())} "
        f"--execution-workflow-channel {q(str(execution_workflow_channel).strip())} "
        f"--schedule-gap-minutes {max(0, int(schedule_gap_minutes))}"
    ).rstrip()
    return {
        "id": "7f0ee69c-64c3-4675-8f4c-71b4ba7b1d0b",
        "agentId": "ops-agent",
        "name": "ops_control_plane_profile_update_dispatch_12h",
        "description": "控制面 profile update 派发：把 ready_for_profile_update 项落成正式 workflow_profile_update 任务",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_profile_update_apply_job(
    *,
    script_py: str,
    task_db: str,
    registry_file: str,
    json_output: str,
    markdown_output: str,
    target_channel: str,
    lookback_hours: int,
    limit: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--task-db {q(str(task_db).strip())} "
        f"--registry-file {q(str(registry_file).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--target-channel {q(str(target_channel).strip())} "
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))}"
    ).rstrip()
    return {
        "id": "4c2c2f4b-a1a6-43f6-b2f1-c8ff0b71f632",
        "agentId": "ops-agent",
        "name": "ops_control_plane_profile_update_apply_12h",
        "description": "控制面 profile update 回写：把已完成的 workflow_profile_update 任务安全写回 workflow registry",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_profile_update_validation_job(
    *,
    script_py: str,
    apply_file: str,
    benchmark_suite_file: str,
    executor_run_dir: str,
    output_root: str,
    state_file: str,
    task_db: str,
    workflow_profile_registry: str,
    json_output: str,
    markdown_output: str,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
    auto_create_tasks: bool,
    auto_apply_workflow_promotion: bool,
    promotion_operator: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--apply-file {q(str(apply_file).strip())} "
        f"--benchmark-suite-file {q(str(benchmark_suite_file).strip())} "
        f"--executor-run-dir {q(str(executor_run_dir).strip())} "
        f"--output-root {q(str(output_root).strip())} "
        f"--state-file {q(str(state_file).strip())} "
        f"{f'--task-db {q(str(task_db).strip())} ' if str(task_db).strip() else ''}"
        f"{f'--workflow-profile-registry {q(str(workflow_profile_registry).strip())} ' if str(workflow_profile_registry).strip() else ''}"
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"{'--auto-create-tasks ' if bool(auto_create_tasks) else ''}"
        f"{'--auto-apply-workflow-promotion ' if bool(auto_apply_workflow_promotion) else ''}"
        f"--promotion-operator {q(str(promotion_operator).strip() or 'control-plane-validation')}"
    ).rstrip()
    return {
        "id": "d7c66f8d-1644-4c18-b339-4b495b28458b",
        "agentId": "ops-agent",
        "name": "ops_control_plane_profile_update_validation_12h",
        "description": "控制面 profile update 定向验证：回写后按受影响 workflow 执行 benchmark suite 验证",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 900,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_acceptance_job(
    *,
    script_py: str,
    jobs_file: str,
    json_output: str,
    markdown_output: str,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--jobs-file {q(str(jobs_file).strip())} "
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
    ).rstrip()
    return {
        "id": "df6ea260-d7a6-48f0-ad08-18c43e0f1e1a",
        "agentId": "ops-agent",
        "name": "ops_control_plane_acceptance_12h",
        "description": "控制面长链路验收：校验已安装 jobs.json 是否包含关键控制面 job 与预期命令契约",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 600,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_control_plane_live_acceptance_job(
    *,
    script_py: str,
    workspace_root: str,
    jobs_file: str,
    json_output: str,
    markdown_output: str,
    lookback_hours: int,
    limit: int,
    every_ms: int,
    delay_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()

    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{script_py}\" "
        f"--workspace-root {q(str(workspace_root).strip())} "
        f"{f'--jobs-file {q(str(jobs_file).strip())} ' if str(jobs_file).strip() else ''}"
        f"{f'--json-output {q(str(json_output).strip())} ' if str(json_output).strip() else ''}"
        f"{f'--markdown-output {q(str(markdown_output).strip())} ' if str(markdown_output).strip() else ''}"
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--limit {max(1, int(limit))}"
    ).rstrip()
    return {
        "id": "13b1f8fe-6173-4f98-8ce6-cac203b49166",
        "agentId": "ops-agent",
        "name": "ops_control_plane_live_acceptance_24h",
        "description": "控制面 live 验收：在隔离工作区实跑 advisor、dispatch、summary、dashboard 与 acceptance 链路",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(3600000, int(every_ms)),
            "anchorMs": ts + max(60000, int(delay_ms)),
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(cmd),
            "model": DEFAULT_MAINTENANCE_CRON_MODEL,
            "lightContext": True,
            "timeoutSeconds": 900,
        },
        "delivery": build_delivery(mode="none"),
    }


def build_conversation_evolution_job(
    *,
    script_py: str,
    db_file: str,
    openclaw_home: str,
    state_file: str,
    report_dir: str,
    every_ms: int,
    log_mode: str,
    lookback_hours: int,
    min_interval_minutes: int,
    max_files: int,
    max_evidence_per_candidate: int,
    min_evidence_lines: int,
    min_unique_files: int,
    min_quality_score: int,
    recent_dedupe_days: int,
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
    assignee: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 \"{script_py}\" --db \"{db_file}\" --openclaw-home \"{openclaw_home}\" "
        f"--state-file \"{state_file}\" --report-dir \"{report_dir}\" "
        f"--task-id cron:ops-conversation-evolution "
        f"--normal-log-mode {normalize_log_mode(log_mode)} "
        f"--lookback-hours {max(1, int(lookback_hours))} "
        f"--min-interval-minutes {max(1, int(min_interval_minutes))} "
        f"--max-files {max(10, int(max_files))} "
        f"--max-evidence-per-candidate {max(1, int(max_evidence_per_candidate))} "
        f"--min-evidence-lines {max(1, int(min_evidence_lines))} "
        f"--min-unique-files {max(1, int(min_unique_files))} "
        f"--min-quality-score {max(1, int(min_quality_score))} "
        f"--recent-dedupe-days {max(0, int(recent_dedupe_days))} "
        f"--max-tasks-per-run {max(1, int(max_tasks_per_run))} "
        f"--schedule-gap-minutes {max(1, int(schedule_gap_minutes))} "
        f"--assignee \"{str(assignee or 'optimization-agent').strip() or 'optimization-agent'}\""
    )
    return {
        "id": "2f7a6a53-95d3-4cc6-9d12-a4e2f55379c1",
        "agentId": "ops-agent",
        "name": "ops_conversation_evolution_incremental",
        "description": "近期对话复盘增量扫描：提炼 bug/流程问题/未闭环项，生成TODO任务包",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1800},
        "delivery": build_delivery(mode="none"),
    }


def build_governance_evolution_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    report_dir: str,
    repo_path: str,
    openclaw_config: str,
    project_registry: str,
    repo_id: str,
    repo_name: str,
    auto_git_update: bool,
    git_update_strategy: str,
    git_fetch_timeout: int,
    every_ms: int,
    log_mode: str,
    max_files: int,
    min_interval_minutes: int,
    task_clarity: str,
    project_context_gate: bool,
    project_context_assignee: str,
    create_review_task: bool,
    auto_pr: bool,
    pr_base: str,
    reviewer_gh_user: str,
    push_before_pr: bool,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 \"{script_py}\" --db \"{db_file}\" "
        f"--state-file \"{state_file}\" --report-dir \"{report_dir}\" --mode incremental "
        f"--task-id cron:ops-governance-evolution "
        f"--normal-log-mode {normalize_log_mode(log_mode)} "
        f"--max-files {max(10, int(max_files))} "
        f"--min-interval-minutes {max(1, int(min_interval_minutes))} "
        f"--task-clarity {str(task_clarity).strip() or 'ambiguous'} "
        f"--git-update-strategy {str(git_update_strategy).strip() or 'fetch'} "
        f"--git-fetch-timeout {max(30, int(git_fetch_timeout))}"
    )
    if str(repo_path).strip():
        cmd += f" --repo-path \"{str(repo_path).strip()}\""
    if str(openclaw_config).strip():
        cmd += f" --openclaw-config \"{str(openclaw_config).strip()}\""
    if str(project_registry).strip():
        cmd += f" --project-registry \"{str(project_registry).strip()}\""
    if str(repo_id).strip():
        cmd += f" --repo-id \"{str(repo_id).strip()}\""
    if str(repo_name).strip():
        cmd += f" --repo-name \"{str(repo_name).strip()}\""
    if auto_git_update:
        cmd += " --auto-git-update"
    else:
        cmd += " --no-auto-git-update"
    if project_context_gate:
        cmd += " --project-context-gate"
    else:
        cmd += " --no-project-context-gate"
    if str(project_context_assignee).strip():
        cmd += f" --project-context-assignee \"{str(project_context_assignee).strip()}\""
    if create_review_task:
        cmd += " --create-review-task"
    if auto_pr:
        cmd += (
            " --auto-pr"
            f" --pr-base \"{str(pr_base).strip() or 'main'}\""
        )
        if str(reviewer_gh_user).strip():
            cmd += f" --reviewer-gh-user \"{str(reviewer_gh_user).strip()}\""
        if push_before_pr:
            cmd += " --push-before-pr"
    return {
        "id": "4f53f7b7-2c3e-4bb1-9aab-6a62f34d4b71",
        "agentId": "optimization-agent",
        "name": "ops_governance_evolution_incremental",
        "description": "治理进化增量扫描：产出优化/审查任务，可选自动PR",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 2400},
        "delivery": build_delivery(mode="none"),
    }


def build_github_web_evolution_job(
    *,
    script_py: str,
    db_file: str,
    openclaw_home: str,
    web_root: str,
    state_file: str,
    report_dir: str,
    every_ms: int,
    log_mode: str,
    min_interval_minutes: int,
    max_queries: int,
    max_repos_per_query: int,
    max_total_repos: int,
    min_stars: int,
    min_quality_score: int,
    min_new_or_updated: int,
    recent_dedupe_days: int,
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
    assignee: str,
    github_token_env: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 \"{script_py}\" --db \"{db_file}\" --openclaw-home \"{openclaw_home}\" "
        f"--web-root \"{web_root}\" --state-file \"{state_file}\" --report-dir \"{report_dir}\" "
        f"--task-id cron:ops-github-web-evolution --normal-log-mode {normalize_log_mode(log_mode)} "
        f"--min-interval-minutes {max(1, int(min_interval_minutes))} "
        f"--max-queries {max(1, int(max_queries))} "
        f"--max-repos-per-query {max(1, int(max_repos_per_query))} "
        f"--max-total-repos {max(1, int(max_total_repos))} "
        f"--min-stars {max(0, int(min_stars))} "
        f"--min-quality-score {max(1, int(min_quality_score))} "
        f"--min-new-or-updated {max(1, int(min_new_or_updated))} "
        f"--recent-dedupe-days {max(0, int(recent_dedupe_days))} "
        f"--max-tasks-per-run {max(1, int(max_tasks_per_run))} "
        f"--schedule-gap-minutes {max(1, int(schedule_gap_minutes))} "
        f"--assignee \"{str(assignee or 'optimization-agent').strip() or 'optimization-agent'}\" "
        f"--github-token-env \"{str(github_token_env or 'GITHUB_TOKEN').strip() or 'GITHUB_TOKEN'}\""
    )
    return {
        "id": "8bc8e2ad-9e3f-4f0d-8af5-2f85bbf88831",
        "agentId": "optimization-agent",
        "name": "ops_github_web_evolution_incremental",
        "description": "GitHub web knowledge incremental evolution: search, archive, and package TODO tasks",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 2400},
        "delivery": build_delivery(mode="none"),
    }


def build_git_sync_job(
    *,
    script_py: str,
    repo_path: str,
    every_ms: int,
    log_mode: str,
    remote: str,
    branch: str,
    max_files: int,
    commit_prefix: str,
    auto_pull: bool,
    push: bool,
    include_prefixes: list[str],
    exclude_prefixes: list[str],
    required_remote_urls: list[str],
    notify_on: str,
) -> dict[str, Any]:
    def quote_arg(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    ts = now_ms()
    remote_value = str(remote or "origin").strip() or "origin"
    commit_prefix_value = str(commit_prefix or "chore(self-evolution): sync updates").strip() or "chore(self-evolution): sync updates"
    cmd = (
        f"python3 \"{quote_arg(script_py)}\" "
        f"--repo-path \"{quote_arg(repo_path)}\" "
        "--task-id cron:ops-git-sync-push "
        f"--normal-log-mode {normalize_log_mode(log_mode)} "
        f"--notify-on {str(notify_on or 'error').strip() or 'error'} "
        f"--remote \"{quote_arg(remote_value)}\" "
        f"--max-files {max(1, int(max_files))} "
        f"--commit-prefix \"{quote_arg(commit_prefix_value)}\""
    )
    branch_value = str(branch or "").strip()
    if branch_value:
        cmd += f" --branch \"{quote_arg(branch_value)}\""
    if auto_pull:
        cmd += " --auto-pull"
    else:
        cmd += " --no-auto-pull"
    if push:
        cmd += " --push"
    else:
        cmd += " --no-push"
    for prefix in include_prefixes:
        text = str(prefix).strip()
        if text:
            cmd += f" --include-prefix \"{quote_arg(text)}\""
    for prefix in exclude_prefixes:
        text = str(prefix).strip()
        if text:
            cmd += f" --exclude-prefix \"{quote_arg(text)}\""
    for url in required_remote_urls:
        text = str(url).strip()
        if text:
            cmd += f" --require-remote-url \"{quote_arg(text)}\""
    return {
        "id": "5dd96c0a-5cd2-4b31-b9a6-75f6ef4f3339",
        "agentId": "optimization-agent",
        "name": "ops_git_sync_push",
        "description": "Auto sync local repo and push self-evolution changes to remote git",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 2400},
        "delivery": build_delivery(mode="none"),
    }


def build_auto_update_install_job(
    *,
    script_py: str,
    repo_path: str,
    every_ms: int,
    log_mode: str,
    remote: str,
    branch: str,
    install_cmd: str,
    install_on_no_change: bool,
    git_timeout: int,
    install_timeout: int,
    report_dir: str,
    required_remote_urls: list[str],
    notify_on: str,
) -> dict[str, Any]:
    def quote_arg(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    ts = now_ms()
    remote_value = str(remote or "origin").strip() or "origin"
    install_cmd_value = str(install_cmd or "").strip()
    cmd = (
        f"python3 \"{quote_arg(script_py)}\" "
        f"--repo-path \"{quote_arg(repo_path)}\" "
        "--task-id cron:ops-auto-update-install "
        f"--normal-log-mode {normalize_log_mode(log_mode)} "
        f"--notify-on {str(notify_on or 'error').strip() or 'error'} "
        f"--remote \"{quote_arg(remote_value)}\" "
        f"--git-timeout {max(30, int(git_timeout))} "
        f"--install-timeout {max(30, int(install_timeout))} "
        f"--report-dir \"{quote_arg(report_dir)}\" "
        f"--install-cmd \"{quote_arg(install_cmd_value)}\" "
        "--auto-pull"
    )
    branch_value = str(branch or "").strip()
    if branch_value:
        cmd += f" --branch \"{quote_arg(branch_value)}\""
    if install_on_no_change:
        cmd += " --install-on-no-change"
    else:
        cmd += " --no-install-on-no-change"
    for url in required_remote_urls:
        text = str(url).strip()
        if text:
            cmd += f" --require-remote-url \"{quote_arg(text)}\""
    return {
        "id": "a4d0b6fb-e1a0-40e4-8ae9-f5b5ebf43d09",
        "agentId": "ops-agent",
        "name": "ops_auto_update_install_hourly",
        "description": "Hourly pull workflow repo and run installer (log-only on failure)",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 3000},
        "delivery": build_delivery(mode="none"),
    }


def int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_schedule(schedule: Any) -> dict[str, Any]:
    if not isinstance(schedule, dict):
        return {}
    kind = str(schedule.get("kind", "")).strip()
    if kind == "every":
        return {
            "kind": "every",
            "everyMs": int_or_default(schedule.get("everyMs"), 0),
            "anchorMs": int_or_default(schedule.get("anchorMs"), 0),
        }
    if kind == "cron":
        return {
            "kind": "cron",
            "expr": str(schedule.get("expr", "")).strip(),
            "tz": str(schedule.get("tz", "")).strip(),
        }
    return {"kind": kind}


def normalize_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        "kind": str(payload.get("kind", "")).strip(),
        "message": str(payload.get("message", "")).strip(),
        "timeoutSeconds": int_or_default(payload.get("timeoutSeconds"), 0),
    }


def normalize_delivery(delivery: Any) -> dict[str, str]:
    if not isinstance(delivery, dict):
        return {"mode": "", "channel": "", "to": ""}
    return {
        "mode": str(delivery.get("mode", "")).strip(),
        "channel": str(delivery.get("channel", "")).strip(),
        "to": str(delivery.get("to", "")).strip(),
    }


def find_existing_for_expected(
    jobs: list[dict[str, Any]],
    expected: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    expected_id = str(expected.get("id", "")).strip()
    expected_name = str(expected.get("name", "")).strip()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).strip() == expected_id:
            return item, "id"
    if expected_name:
        for item in jobs:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).strip() == expected_name:
                return item, "name"
    return None, "missing"


def compare_expected_job(
    existing: dict[str, Any],
    expected: dict[str, Any],
    expected_channel: str,
    expected_target: str,
) -> list[str]:
    drifts: list[str] = []
    if str(existing.get("agentId", "")).strip() != str(expected.get("agentId", "")).strip():
        drifts.append("agentId")
    if bool(existing.get("enabled", False)) != bool(expected.get("enabled", False)):
        drifts.append("enabled")
    if str(existing.get("sessionTarget", "")).strip() != str(expected.get("sessionTarget", "")).strip():
        drifts.append("sessionTarget")
    if str(existing.get("wakeMode", "")).strip() != str(expected.get("wakeMode", "")).strip():
        drifts.append("wakeMode")
    if normalize_schedule(existing.get("schedule")) != normalize_schedule(expected.get("schedule")):
        drifts.append("schedule")
    if normalize_payload(existing.get("payload")) != normalize_payload(expected.get("payload")):
        drifts.append("payload")
    expected_mode = normalize_delivery(expected.get("delivery")).get("mode", "").strip() or "announce"
    expected_delivery = {"mode": expected_mode, "channel": expected_channel, "to": expected_target}
    if normalize_delivery(existing.get("delivery")) != expected_delivery:
        drifts.append("delivery")
    return drifts


def audit_jobs(
    jobs: list[dict[str, Any]],
    expected_jobs: list[dict[str, Any]],
    channel: str,
    target: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for expected in expected_jobs:
        expected_id = str(expected.get("id", "")).strip()
        expected_name = str(expected.get("name", "")).strip()
        existing, matched_by = find_existing_for_expected(jobs, expected)
        if not isinstance(existing, dict):
            entries.append(
                {
                    "job_id": expected_id,
                    "job_name": expected_name,
                    "status": "missing",
                    "matched_by": "missing",
                    "existing_job_id": "",
                    "drift_fields": ["missing"],
                    "observed": {},
                    "expected": {
                        "schedule": normalize_schedule(expected.get("schedule")),
                        "payload": normalize_payload(expected.get("payload")),
                        "delivery": {
                            "mode": normalize_delivery(expected.get("delivery")).get("mode", "").strip() or "announce",
                            "channel": channel,
                            "to": target,
                        },
                    },
                }
            )
            continue

        drifts = compare_expected_job(existing, expected, channel, target)
        existing_id = str(existing.get("id", "")).strip()
        if matched_by == "name" and existing_id != expected_id:
            drifts = ["id", *drifts]

        status = "compliant" if not drifts else "drifted"
        entries.append(
            {
                "job_id": expected_id,
                "job_name": expected_name,
                "status": status,
                "matched_by": matched_by,
                "existing_job_id": existing_id,
                "drift_fields": drifts,
                "observed": {
                    "schedule": normalize_schedule(existing.get("schedule")),
                    "payload": normalize_payload(existing.get("payload")),
                    "delivery": normalize_delivery(existing.get("delivery")),
                },
                "expected": {
                    "schedule": normalize_schedule(expected.get("schedule")),
                    "payload": normalize_payload(expected.get("payload")),
                    "delivery": {
                        "mode": normalize_delivery(expected.get("delivery")).get("mode", "").strip() or "announce",
                        "channel": channel,
                        "to": target,
                    },
                },
            }
        )

    counts = {
        "existing_total": sum(1 for x in jobs if isinstance(x, dict)),
        "expected_total": len(expected_jobs),
        "compliant": sum(1 for x in entries if x.get("status") == "compliant"),
        "drifted": sum(1 for x in entries if x.get("status") == "drifted"),
        "missing": sum(1 for x in entries if x.get("status") == "missing"),
    }
    return {
        "counts": counts,
        "jobs": entries,
    }


def remove_name_conflicts(
    jobs: list[dict[str, Any]],
    expected_jobs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    expected_by_name = {
        str(item.get("name", "")).strip(): str(item.get("id", "")).strip()
        for item in expected_jobs
        if isinstance(item, dict) and str(item.get("name", "")).strip() and str(item.get("id", "")).strip()
    }
    if not expected_by_name:
        return jobs, []

    kept: list[dict[str, Any]] = []
    removed: list[dict[str, str]] = []
    for item in jobs:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        name = str(item.get("name", "")).strip()
        jid = str(item.get("id", "")).strip()
        expected_id = expected_by_name.get(name)
        if expected_id and jid and jid != expected_id:
            removed.append({"id": jid, "name": name})
            continue
        kept.append(item)
    return kept, removed


def validate_runtime_paths(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def add_check(label: str, raw_path: str, required: bool = True, expect: str = "file") -> None:
        path = Path(raw_path).expanduser()
        exists = path.exists()
        if expect == "file":
            ok = exists and path.is_file()
        elif expect == "dir":
            ok = exists and path.is_dir()
        else:
            ok = exists
        checks.append(
            {
                "label": label,
                "path": str(path),
                "exists": exists,
                "ok": ok if required else True,
                "required": required,
                "expect": expect,
            }
        )
        if required and not ok:
            errors.append(f"{label}_missing:{path}")

    add_check("runner_py", str(args.runner_py), required=True, expect="file")
    if bool(args.install_system_schedule_job):
        add_check("system_schedule_py", str(args.system_schedule_py), required=True, expect="file")
    if bool(args.install_api_test_job):
        add_check("api_test_py", str(args.api_test_py), required=True, expect="file")
        add_check("api_test_config", str(args.api_test_config), required=True, expect="file")
    if bool(args.install_daily_work_job):
        add_check("daily_work_py", str(args.daily_work_py), required=True, expect="file")
        add_check("daily_work_env_file", str(args.daily_work_env_file), required=False, expect="file")
    if bool(args.install_self_evolution_job):
        add_check("self_evolution_py", str(args.self_evolution_py), required=True, expect="file")
    if bool(args.install_upgrade_feedback_job):
        add_check("upgrade_feedback_py", str(args.upgrade_feedback_py), required=True, expect="file")
        if bool(args.upgrade_feedback_auto_apply_workflow_promotion):
            add_check(
                "upgrade_feedback_workflow_profile_registry",
                str(args.upgrade_feedback_workflow_profile_registry),
                required=True,
                expect="file",
            )
    if bool(args.install_conversation_evolution_job):
        add_check("conversation_evolution_py", str(args.conversation_evolution_py), required=True, expect="file")
        add_check("conversation_evolution_openclaw_home", str(args.conversation_evolution_openclaw_home), required=True, expect="dir")
    if bool(args.install_governance_evolution_job):
        add_check("governance_evolution_py", str(args.governance_evolution_py), required=True, expect="file")
        add_check("governance_evolution_openclaw_config", str(args.governance_evolution_openclaw_config), required=False, expect="file")
        add_check("governance_evolution_project_registry", str(args.governance_evolution_project_registry), required=False, expect="file")
        if str(args.governance_evolution_repo_path).strip():
            add_check(
                "governance_evolution_repo_path",
                str(args.governance_evolution_repo_path),
                required=True,
                expect="dir",
            )
            repo = Path(str(args.governance_evolution_repo_path)).expanduser()
            if not (repo / ".git").exists():
                errors.append(f"governance_evolution_repo_not_git:{repo}")
        else:
            registry = Path(str(args.governance_evolution_project_registry or "")).expanduser()
            if not registry.exists():
                errors.append("governance_evolution_repo_resolve_missing:repo_path_or_project_registry")
    if bool(args.install_git_sync_job):
        add_check("git_sync_py", str(args.git_sync_py), required=True, expect="file")
        repo_raw = str(args.git_sync_repo_path or args.governance_evolution_repo_path or "").strip()
        if repo_raw:
            add_check("git_sync_repo_path", repo_raw, required=True, expect="dir")
            repo = Path(repo_raw).expanduser()
            if not (repo / ".git").exists():
                errors.append(f"git_sync_repo_not_git:{repo}")
        else:
            errors.append("git_sync_repo_missing:--git-sync-repo-path")
    if bool(args.install_auto_update_install_job):
        add_check("auto_update_install_py", str(args.auto_update_install_py), required=True, expect="file")
        repo_raw = str(args.auto_update_install_repo_path or args.governance_evolution_repo_path or "").strip()
        if repo_raw:
            add_check("auto_update_install_repo_path", repo_raw, required=True, expect="dir")
            repo = Path(repo_raw).expanduser()
            if not (repo / ".git").exists():
                errors.append(f"auto_update_install_repo_not_git:{repo}")
        else:
            errors.append("auto_update_install_repo_missing:--auto-update-install-repo-path")
        if not str(args.auto_update_install_install_cmd or "").strip():
            errors.append("auto_update_install_cmd_missing:--auto-update-install-install-cmd")
    if bool(args.install_github_web_evolution_job):
        add_check("github_web_evolution_py", str(args.github_web_evolution_py), required=True, expect="file")
        add_check("github_web_evolution_openclaw_home", str(args.github_web_evolution_openclaw_home), required=True, expect="dir")

    return {"ok": len(errors) == 0, "errors": errors, "checks": checks}


def upsert_jobs(
    jobs: list[dict[str, Any]],
    fresh_jobs: list[dict[str, Any]],
    channel: str,
    target: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ts = now_ms()
    by_id = {str(item.get("id", "")): item for item in jobs if isinstance(item, dict)}
    status: dict[str, str] = {}

    for item in fresh_jobs:
        jid = str(item.get("id", "")).strip()
        old = by_id.get(jid)
        if isinstance(old, dict):
            item["createdAtMs"] = int(old.get("createdAtMs", item.get("createdAtMs", ts)))
            old_state = old.get("state") if isinstance(old.get("state"), dict) else {}
            item["state"] = old_state
            item["updatedAtMs"] = ts
            status[jid] = "updated"
        else:
            item["state"] = {}
            status[jid] = "created"

        delivery_mode = normalize_delivery(item.get("delivery")).get("mode", "").strip() or "announce"
        item["delivery"] = {"mode": delivery_mode, "channel": channel, "to": target}
        failure_alert = item.get("failureAlert")
        if isinstance(failure_alert, dict):
            failure_alert["channel"] = channel
            failure_alert["to"] = target
            item["failureAlert"] = failure_alert
        if item.get("schedule", {}).get("kind") == "every":
            item["state"]["nextRunAtMs"] = ts + int(item["schedule"].get("everyMs", 0))
        by_id[jid] = item

    ordered: list[dict[str, Any]] = []
    replaced = set(status)
    for old in jobs:
        jid = str(old.get("id", ""))
        if jid in replaced:
            ordered.append(by_id[jid])
            replaced.remove(jid)
        else:
            ordered.append(old)
    for jid in status:
        if all(str(x.get("id", "")) != jid for x in ordered):
            ordered.append(by_id[jid])
    return ordered, status


def main() -> int:
    home = Path(os.path.expanduser("~"))
    local_ops_dir = ROOT
    default_self_evolution_py = prefer_existing_path(
        local_ops_dir / "self_evolution_todo.py",
        home / ".openclaw/ops/self_evolution_todo.py",
    )
    default_upgrade_feedback_py = prefer_existing_path(
        local_ops_dir / "upgrade_feedback_runner.py",
        home / ".openclaw/ops/upgrade_feedback_runner.py",
    )
    default_upgrade_feedback_workflow_profile_registry = prefer_existing_path(
        local_ops_dir / "policy/workflow-profile-registry.json",
        home / ".openclaw/ops/policy/workflow-profile-registry.json",
    )
    default_upgrade_feedback_benchmark_suite_file = prefer_existing_path(
        local_ops_dir / "policy/benchmark-suite-registry.json",
        home / ".openclaw/ops/policy/benchmark-suite-registry.json",
    )
    default_benchmark_sweep_py = prefer_existing_path(
        local_ops_dir / "benchmark_orchestrator.py",
        home / ".openclaw/ops/benchmark_orchestrator.py",
    )
    default_benchmark_output_consumer_py = prefer_existing_path(
        local_ops_dir / "benchmark_output_consumer.py",
        home / ".openclaw/ops/benchmark_output_consumer.py",
    )
    default_task_output_broadcast_py = prefer_existing_path(
        local_ops_dir / "task_output_broadcast_runner.py",
        home / ".openclaw/ops/task_output_broadcast_runner.py",
    )
    default_control_plane_summary_py = prefer_existing_path(
        local_ops_dir / "control_plane_summary_runner.py",
        home / ".openclaw/ops/control_plane_summary_runner.py",
    )
    default_control_plane_dashboard_py = prefer_existing_path(
        local_ops_dir / "control_plane_dashboard.py",
        home / ".openclaw/ops/control_plane_dashboard.py",
    )
    default_control_plane_optimization_py = prefer_existing_path(
        local_ops_dir / "control_plane_optimization_advisor.py",
        home / ".openclaw/ops/control_plane_optimization_advisor.py",
    )
    default_control_plane_optimization_dispatch_py = prefer_existing_path(
        local_ops_dir / "control_plane_optimization_dispatcher.py",
        home / ".openclaw/ops/control_plane_optimization_dispatcher.py",
    )
    default_control_plane_optimization_review_py = prefer_existing_path(
        local_ops_dir / "control_plane_optimization_review_runner.py",
        home / ".openclaw/ops/control_plane_optimization_review_runner.py",
    )
    default_control_plane_profile_update_dispatch_py = prefer_existing_path(
        local_ops_dir / "control_plane_profile_update_dispatcher.py",
        home / ".openclaw/ops/control_plane_profile_update_dispatcher.py",
    )
    default_control_plane_profile_update_apply_py = prefer_existing_path(
        local_ops_dir / "control_plane_profile_update_applier.py",
        home / ".openclaw/ops/control_plane_profile_update_applier.py",
    )
    default_control_plane_profile_update_validation_py = prefer_existing_path(
        local_ops_dir / "control_plane_profile_update_validation_runner.py",
        home / ".openclaw/ops/control_plane_profile_update_validation_runner.py",
    )
    default_control_plane_acceptance_py = prefer_existing_path(
        local_ops_dir / "control_plane_acceptance_runner.py",
        home / ".openclaw/ops/control_plane_acceptance_runner.py",
    )
    default_control_plane_live_acceptance_py = prefer_existing_path(
        local_ops_dir / "control_plane_live_acceptance_runner.py",
        home / ".openclaw/ops/control_plane_live_acceptance_runner.py",
    )
    default_conversation_evolution_py = prefer_existing_path(
        local_ops_dir / "conversation_evolution_runner.py",
        home / ".openclaw/ops/conversation_evolution_runner.py",
    )
    default_governance_evolution_py = prefer_existing_path(
        local_ops_dir / "governance_evolution_runner.py",
        home / ".openclaw/ops/governance_evolution_runner.py",
    )
    default_github_web_evolution_py = prefer_existing_path(
        local_ops_dir / "github_web_evolution_runner.py",
        home / ".openclaw/ops/github_web_evolution_runner.py",
    )
    default_git_sync_py = prefer_existing_path(
        local_ops_dir / "git_sync_push_runner.py",
        home / ".openclaw/ops/git_sync_push_runner.py",
    )
    default_auto_update_install_py = prefer_existing_path(
        local_ops_dir / "auto_update_install_runner.py",
        home / ".openclaw/ops/auto_update_install_runner.py",
    )
    default_auto_update_install_cmd = (
        "python3 $HOME/.openclaw/ops/install_workflow_profile.py "
        "--profile core "
        "--openclaw-home $HOME/.openclaw "
        "--workflow-repo-path ${OPENCLAW_WORKFLOW_REPO:-$HOME/openclaw-hardflow-backup-20260302} "
        "--emit-json"
    )
    parser = argparse.ArgumentParser(description="Install OpenClaw hardflow cron jobs")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--install-profile", default="legacy", choices=sorted(INSTALL_PROFILES))
    parser.add_argument(
        "--legacy-optimize-jobs-mode",
        default="auto",
        choices=sorted(LEGACY_OPTIMIZE_JOB_MODES),
    )
    parser.add_argument(
        "--daily-report-dedupe-mode",
        default="auto",
        choices=sorted(DAILY_REPORT_DEDUPE_MODES),
    )

    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/ops_cron_runner.py"))
    parser.add_argument("--config-file", default=str(home / ".openclaw/ops/cron-monitor-config.json"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/cron-monitor-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/cron-runs"))
    parser.add_argument("--incremental-every-ms", type=int, default=900000)
    parser.add_argument("--full-expr", default="23 */6 * * *")
    parser.add_argument("--daily-expr", default="5 0 * * *")
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--daily-major-only", action="store_true")
    parser.add_argument("--incremental-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--full-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--daily-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-system-schedule-job", action="store_true")
    parser.add_argument("--system-schedule-py", default=str(home / ".openclaw/ops/system_schedule_snapshot.py"))
    parser.add_argument("--system-snapshot-dir", default=str(home / ".openclaw/ops/system-schedule/snapshots"))
    parser.add_argument("--system-state-file", default=str(home / ".openclaw/ops/system-schedule/state.json"))
    parser.add_argument("--system-every-ms", type=int, default=1800000)
    parser.add_argument("--system-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-api-test-job", action="store_true")
    parser.add_argument("--api-test-py", default=str(home / ".openclaw/ops/api_test_audit.py"))
    parser.add_argument("--api-test-config", default=str(home / ".openclaw/ops/api-test-config.json"))
    parser.add_argument("--api-test-state", default=str(home / ".openclaw/ops/api-test-state.json"))
    parser.add_argument("--api-test-history-dir", default=str(home / ".openclaw/ops/api-test-runs"))
    parser.add_argument("--api-test-expr", default="*/15 * * * *")
    parser.add_argument("--api-test-engine", default="playwright-real", choices=sorted(API_ENGINES))
    parser.add_argument("--api-test-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-daily-work-job", action="store_true")
    parser.add_argument("--daily-work-py", default=str(home / ".openclaw/ops/daily_work_report.py"))
    parser.add_argument("--daily-work-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--daily-work-state", default=str(home / ".openclaw/ops/daily-work/state.json"))
    parser.add_argument("--daily-work-report-dir", default=str(home / ".openclaw/ops/daily-work/reports"))
    parser.add_argument("--daily-work-expr", default="15 0 * * *")
    parser.add_argument("--daily-work-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--dingtalk-webhook-env", default="DINGTALK_WEBHOOK_URL")
    parser.add_argument("--dingtalk-secret-env", default="DINGTALK_SECRET")
    parser.add_argument("--daily-work-env-file", default=str(home / ".openclaw/ops/runtime.env"))
    parser.add_argument("--daily-work-todo-file", action="append", default=[])

    parser.add_argument("--install-self-evolution-job", action="store_true")
    parser.add_argument("--self-evolution-py", default=str(default_self_evolution_py))
    parser.add_argument("--self-evolution-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--self-evolution-state", default=str(home / ".openclaw/ops/self-evolution/state.json"))
    parser.add_argument("--self-evolution-report-dir", default=str(home / ".openclaw/ops/self-evolution/reports"))
    parser.add_argument("--self-evolution-expr", default="30 3 * * 1")
    parser.add_argument("--self-evolution-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--self-evolution-lookback-days", type=int, default=30)
    parser.add_argument("--self-evolution-min-interval-days", type=int, default=7)
    parser.add_argument("--self-evolution-max-tasks-per-run", type=int, default=3)
    parser.add_argument("--self-evolution-agent-score-threshold", type=float, default=70.0)
    parser.add_argument("--self-evolution-agent-score-min-reports", type=int, default=3)
    parser.add_argument("--self-evolution-agent-score-top-n", type=int, default=12)
    parser.add_argument("--self-evolution-low-score-guarantee-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--self-evolution-low-score-guarantee-min-agents", type=int, default=2)
    parser.add_argument("--self-evolution-low-score-guarantee-max-agents", type=int, default=6)
    parser.add_argument("--self-evolution-low-score-guarantee-threshold", type=float, default=70.0)

    parser.add_argument("--install-upgrade-feedback-job", action="store_true")
    parser.add_argument("--upgrade-feedback-py", default=str(default_upgrade_feedback_py))
    parser.add_argument("--upgrade-feedback-executor-run-dir", default=str(home / ".openclaw/ops/task-center/executor-runs"))
    parser.add_argument("--upgrade-feedback-output-dir", default=str(home / ".openclaw/ops/upgrade-feedback/reports"))
    parser.add_argument("--upgrade-feedback-state", default=str(home / ".openclaw/ops/upgrade-feedback/state.json"))
    parser.add_argument("--upgrade-feedback-every-ms", type=int, default=86400000)
    parser.add_argument("--upgrade-feedback-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--upgrade-feedback-workflow-target", default="task_executor_10m")
    parser.add_argument("--upgrade-feedback-skill-name", default="openclaw-evolution-upgrader")
    parser.add_argument("--upgrade-feedback-skill-assignee", default="optimization-agent")
    parser.add_argument("--upgrade-feedback-baseline-count", type=int, default=3)
    parser.add_argument("--upgrade-feedback-candidate-count", type=int, default=3)
    parser.add_argument("--upgrade-feedback-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--upgrade-feedback-auto-create-tasks", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--upgrade-feedback-workflow-profile-registry",
        default=str(default_upgrade_feedback_workflow_profile_registry),
    )
    parser.add_argument(
        "--upgrade-feedback-benchmark-suite-file",
        default=str(default_upgrade_feedback_benchmark_suite_file),
    )
    parser.add_argument("--upgrade-feedback-benchmark-suite-id", default="coding-default-core")
    parser.add_argument(
        "--upgrade-feedback-auto-apply-workflow-promotion",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--upgrade-feedback-promotion-operator", default="cron-upgrade-feedback")
    parser.add_argument("--upgrade-feedback-task-score-threshold", type=float, default=80.0)
    parser.add_argument("--upgrade-feedback-task-schedule-gap-minutes", type=int, default=120)

    parser.add_argument("--install-benchmark-sweep-job", action="store_true")
    parser.add_argument("--benchmark-sweep-py", default=str(default_benchmark_sweep_py))
    parser.add_argument("--benchmark-sweep-executor-run-dir", default=str(home / ".openclaw/ops/task-center/executor-runs"))
    parser.add_argument("--benchmark-sweep-output-root", default=str(home / ".openclaw/ops/benchmark-sweeps"))
    parser.add_argument("--benchmark-sweep-state-root", default=str(home / ".openclaw/ops/benchmark-sweeps/state"))
    parser.add_argument("--benchmark-sweep-output-py", default=str(default_benchmark_output_consumer_py))
    parser.add_argument("--benchmark-sweep-summary-file", default=str(home / ".openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json"))
    parser.add_argument("--benchmark-sweep-consumer-output-file", default=str(home / ".openclaw/ops/benchmark-sweeps/output/latest-event.json"))
    parser.add_argument("--benchmark-sweep-consumer-notify-on", default="error", choices=["error", "activity", "always"])
    parser.add_argument(
        "--benchmark-sweep-benchmark-suite-file",
        default=str(default_upgrade_feedback_benchmark_suite_file),
    )
    parser.add_argument(
        "--benchmark-sweep-workflow-profile-registry",
        default=str(default_upgrade_feedback_workflow_profile_registry),
    )
    parser.add_argument("--benchmark-sweep-suite-id", action="append", default=[])
    parser.add_argument("--benchmark-sweep-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--benchmark-sweep-every-ms", type=int, default=86400000)
    parser.add_argument("--benchmark-sweep-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--benchmark-sweep-auto-create-tasks", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--benchmark-sweep-auto-apply-workflow-promotion",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--benchmark-sweep-promotion-operator", default="cron-benchmark-sweep")
    parser.add_argument("--benchmark-sweep-task-score-threshold", type=float, default=80.0)
    parser.add_argument("--benchmark-sweep-task-schedule-gap-minutes", type=int, default=120)

    parser.add_argument("--install-benchmark-output-job", action="store_true")
    parser.add_argument("--benchmark-output-py", default=str(default_benchmark_output_consumer_py))
    parser.add_argument("--benchmark-output-summary-file", default=str(home / ".openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json"))
    parser.add_argument("--benchmark-output-output-file", default=str(home / ".openclaw/ops/benchmark-sweeps/output/latest-event.json"))
    parser.add_argument("--benchmark-output-notify-on", default="error", choices=["error", "activity", "always"])
    parser.add_argument("--benchmark-output-every-ms", type=int, default=86400000)
    parser.add_argument("--benchmark-output-delay-ms", type=int, default=300000)
    parser.add_argument("--benchmark-output-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-task-output-broadcast-job", action="store_true")
    parser.add_argument("--task-output-broadcast-py", default=str(default_task_output_broadcast_py))
    parser.add_argument("--task-output-broadcast-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--task-output-broadcast-state", default=str(home / ".openclaw/ops/task-output/state.json"))
    parser.add_argument("--task-output-broadcast-output", default=str(home / ".openclaw/ops/task-output/latest-event.json"))
    parser.add_argument("--task-output-broadcast-lookback-hours", type=int, default=24)
    parser.add_argument("--task-output-broadcast-limit", type=int, default=12)
    parser.add_argument("--task-output-broadcast-event-limit", type=int, default=200)
    parser.add_argument("--task-output-broadcast-notify-on", default="error", choices=["error", "activity", "always"])
    parser.add_argument("--task-output-broadcast-every-ms", type=int, default=900000)
    parser.add_argument("--task-output-broadcast-delay-ms", type=int, default=120000)
    parser.add_argument("--task-output-broadcast-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-summary-job", action="store_true")
    parser.add_argument("--control-plane-summary-py", default=str(default_control_plane_summary_py))
    parser.add_argument("--control-plane-summary-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-summary-state", default=str(home / ".openclaw/ops/control-plane-summary/state.json"))
    parser.add_argument("--control-plane-summary-output", default=str(home / ".openclaw/ops/control-plane-summary/latest-event.json"))
    parser.add_argument("--control-plane-summary-lookback-hours", type=int, default=24)
    parser.add_argument("--control-plane-summary-limit", type=int, default=20)
    parser.add_argument("--control-plane-summary-notify-on", default="activity", choices=["error", "activity", "always"])
    parser.add_argument("--control-plane-summary-every-ms", type=int, default=21600000)
    parser.add_argument("--control-plane-summary-delay-ms", type=int, default=180000)
    parser.add_argument("--control-plane-summary-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-dashboard-job", action="store_true")
    parser.add_argument("--control-plane-dashboard-py", default=str(default_control_plane_dashboard_py))
    parser.add_argument("--control-plane-dashboard-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-dashboard-benchmark-summary-file", default=str(home / ".openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json"))
    parser.add_argument("--control-plane-dashboard-json-output", default=str(home / ".openclaw/ops/control-plane-dashboard/latest-dashboard.json"))
    parser.add_argument("--control-plane-dashboard-markdown-output", default=str(home / ".openclaw/ops/control-plane-dashboard/latest-dashboard.md"))
    parser.add_argument("--control-plane-dashboard-html-output", default=str(home / ".openclaw/ops/control-plane-dashboard/latest-dashboard.html"))
    parser.add_argument("--control-plane-dashboard-lookback-hours", type=int, default=24)
    parser.add_argument("--control-plane-dashboard-limit", type=int, default=20)
    parser.add_argument("--control-plane-dashboard-every-ms", type=int, default=21600000)
    parser.add_argument("--control-plane-dashboard-delay-ms", type=int, default=240000)
    parser.add_argument("--control-plane-dashboard-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-optimization-job", action="store_true")
    parser.add_argument("--control-plane-optimization-py", default=str(default_control_plane_optimization_py))
    parser.add_argument("--control-plane-optimization-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-optimization-json-output", default=str(home / ".openclaw/ops/control-plane-optimization/latest-report.json"))
    parser.add_argument("--control-plane-optimization-markdown-output", default=str(home / ".openclaw/ops/control-plane-optimization/latest-report.md"))
    parser.add_argument("--control-plane-optimization-lookback-hours", type=int, default=24)
    parser.add_argument("--control-plane-optimization-limit", type=int, default=20)
    parser.add_argument("--control-plane-optimization-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-optimization-delay-ms", type=int, default=360000)
    parser.add_argument("--control-plane-optimization-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-optimization-dispatch-job", action="store_true")
    parser.add_argument("--control-plane-optimization-dispatch-py", default=str(default_control_plane_optimization_dispatch_py))
    parser.add_argument("--control-plane-optimization-dispatch-report-file", default=str(home / ".openclaw/ops/control-plane-optimization/latest-report.json"))
    parser.add_argument("--control-plane-optimization-dispatch-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-optimization-dispatch-json-output", default=str(home / ".openclaw/ops/control-plane-optimization-dispatch/latest-report.json"))
    parser.add_argument("--control-plane-optimization-dispatch-markdown-output", default=str(home / ".openclaw/ops/control-plane-optimization-dispatch/latest-report.md"))
    parser.add_argument("--control-plane-optimization-dispatch-execution-workflow-profile", default="coding-default")
    parser.add_argument("--control-plane-optimization-dispatch-execution-workflow-channel", default="stable")
    parser.add_argument("--control-plane-optimization-dispatch-schedule-gap-minutes", type=int, default=30)
    parser.add_argument("--control-plane-optimization-dispatch-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-optimization-dispatch-delay-ms", type=int, default=480000)
    parser.add_argument("--control-plane-optimization-dispatch-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-optimization-review-job", action="store_true")
    parser.add_argument("--control-plane-optimization-review-py", default=str(default_control_plane_optimization_review_py))
    parser.add_argument("--control-plane-optimization-review-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-optimization-review-json-output", default=str(home / ".openclaw/ops/control-plane-optimization-review/latest-report.json"))
    parser.add_argument("--control-plane-optimization-review-markdown-output", default=str(home / ".openclaw/ops/control-plane-optimization-review/latest-report.md"))
    parser.add_argument("--control-plane-optimization-review-lookback-hours", type=int, default=72)
    parser.add_argument("--control-plane-optimization-review-limit", type=int, default=20)
    parser.add_argument("--control-plane-optimization-review-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-optimization-review-delay-ms", type=int, default=540000)
    parser.add_argument("--control-plane-optimization-review-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-profile-update-dispatch-job", action="store_true")
    parser.add_argument("--control-plane-profile-update-dispatch-py", default=str(default_control_plane_profile_update_dispatch_py))
    parser.add_argument("--control-plane-profile-update-dispatch-review-file", default=str(home / ".openclaw/ops/control-plane-optimization-review/latest-report.json"))
    parser.add_argument("--control-plane-profile-update-dispatch-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-profile-update-dispatch-json-output", default=str(home / ".openclaw/ops/control-plane-profile-update-dispatch/latest-report.json"))
    parser.add_argument("--control-plane-profile-update-dispatch-markdown-output", default=str(home / ".openclaw/ops/control-plane-profile-update-dispatch/latest-report.md"))
    parser.add_argument("--control-plane-profile-update-dispatch-execution-workflow-profile", default="coding-default")
    parser.add_argument("--control-plane-profile-update-dispatch-execution-workflow-channel", default="stable")
    parser.add_argument("--control-plane-profile-update-dispatch-schedule-gap-minutes", type=int, default=60)
    parser.add_argument("--control-plane-profile-update-dispatch-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-profile-update-dispatch-delay-ms", type=int, default=600000)
    parser.add_argument("--control-plane-profile-update-dispatch-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-profile-update-apply-job", action="store_true")
    parser.add_argument("--control-plane-profile-update-apply-py", default=str(default_control_plane_profile_update_apply_py))
    parser.add_argument("--control-plane-profile-update-apply-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-profile-update-apply-registry-file", default=str(home / ".openclaw/ops/policy/workflow-profile-registry.json"))
    parser.add_argument("--control-plane-profile-update-apply-json-output", default=str(home / ".openclaw/ops/control-plane-profile-update-apply/latest-report.json"))
    parser.add_argument("--control-plane-profile-update-apply-markdown-output", default=str(home / ".openclaw/ops/control-plane-profile-update-apply/latest-report.md"))
    parser.add_argument("--control-plane-profile-update-apply-target-channel", default="candidate")
    parser.add_argument("--control-plane-profile-update-apply-lookback-hours", type=int, default=72)
    parser.add_argument("--control-plane-profile-update-apply-limit", type=int, default=20)
    parser.add_argument("--control-plane-profile-update-apply-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-profile-update-apply-delay-ms", type=int, default=660000)
    parser.add_argument("--control-plane-profile-update-apply-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-profile-update-validation-job", action="store_true")
    parser.add_argument("--control-plane-profile-update-validation-py", default=str(default_control_plane_profile_update_validation_py))
    parser.add_argument("--control-plane-profile-update-validation-apply-file", default=str(home / ".openclaw/ops/control-plane-profile-update-apply/latest-report.json"))
    parser.add_argument("--control-plane-profile-update-validation-benchmark-suite-file", default=str(home / ".openclaw/ops/policy/benchmark-suite-registry.json"))
    parser.add_argument("--control-plane-profile-update-validation-executor-run-dir", default=str(home / ".openclaw/ops/task-center/executor-runs"))
    parser.add_argument("--control-plane-profile-update-validation-output-root", default=str(home / ".openclaw/ops/control-plane-profile-update-validation"))
    parser.add_argument("--control-plane-profile-update-validation-state-file", default=str(home / ".openclaw/ops/control-plane-profile-update-validation/state.json"))
    parser.add_argument("--control-plane-profile-update-validation-task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--control-plane-profile-update-validation-workflow-profile-registry", default=str(home / ".openclaw/ops/policy/workflow-profile-registry.json"))
    parser.add_argument("--control-plane-profile-update-validation-json-output", default=str(home / ".openclaw/ops/control-plane-profile-update-validation/latest-report.json"))
    parser.add_argument("--control-plane-profile-update-validation-markdown-output", default=str(home / ".openclaw/ops/control-plane-profile-update-validation/latest-report.md"))
    parser.add_argument("--control-plane-profile-update-validation-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-profile-update-validation-delay-ms", type=int, default=720000)
    parser.add_argument("--control-plane-profile-update-validation-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--control-plane-profile-update-validation-auto-create-tasks", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--control-plane-profile-update-validation-auto-apply-workflow-promotion", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--control-plane-profile-update-validation-promotion-operator", default="control-plane-validation")
    parser.add_argument("--install-control-plane-acceptance-job", action="store_true")
    parser.add_argument("--control-plane-acceptance-py", default=str(default_control_plane_acceptance_py))
    parser.add_argument("--control-plane-acceptance-jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--control-plane-acceptance-json-output", default=str(home / ".openclaw/ops/control-plane-acceptance/latest-report.json"))
    parser.add_argument("--control-plane-acceptance-markdown-output", default=str(home / ".openclaw/ops/control-plane-acceptance/latest-report.md"))
    parser.add_argument("--control-plane-acceptance-every-ms", type=int, default=43200000)
    parser.add_argument("--control-plane-acceptance-delay-ms", type=int, default=420000)
    parser.add_argument("--control-plane-acceptance-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--install-control-plane-live-acceptance-job", action="store_true")
    parser.add_argument("--control-plane-live-acceptance-py", default=str(default_control_plane_live_acceptance_py))
    parser.add_argument("--control-plane-live-acceptance-workspace-root", default=str(home / ".openclaw/ops/control-plane-live-acceptance"))
    parser.add_argument("--control-plane-live-acceptance-jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--control-plane-live-acceptance-json-output", default=str(home / ".openclaw/ops/control-plane-live-acceptance/latest-report.json"))
    parser.add_argument("--control-plane-live-acceptance-markdown-output", default=str(home / ".openclaw/ops/control-plane-live-acceptance/latest-report.md"))
    parser.add_argument("--control-plane-live-acceptance-lookback-hours", type=int, default=24)
    parser.add_argument("--control-plane-live-acceptance-limit", type=int, default=20)
    parser.add_argument("--control-plane-live-acceptance-every-ms", type=int, default=86400000)
    parser.add_argument("--control-plane-live-acceptance-delay-ms", type=int, default=540000)
    parser.add_argument("--control-plane-live-acceptance-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-conversation-evolution-job", action="store_true")
    parser.add_argument("--conversation-evolution-py", default=str(default_conversation_evolution_py))
    parser.add_argument("--conversation-evolution-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument(
        "--conversation-evolution-openclaw-home",
        default=str(home / ".openclaw"),
    )
    parser.add_argument(
        "--conversation-evolution-state",
        default=str(home / ".openclaw/ops/conversation-evolution/state.json"),
    )
    parser.add_argument(
        "--conversation-evolution-report-dir",
        default=str(home / ".openclaw/ops/conversation-evolution/reports"),
    )
    parser.add_argument("--conversation-evolution-every-ms", type=int, default=21600000)
    parser.add_argument("--conversation-evolution-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--conversation-evolution-lookback-hours", type=int, default=72)
    parser.add_argument("--conversation-evolution-min-interval-minutes", type=int, default=180)
    parser.add_argument("--conversation-evolution-max-files", type=int, default=120)
    parser.add_argument("--conversation-evolution-max-evidence-per-candidate", type=int, default=24)
    parser.add_argument("--conversation-evolution-min-evidence-lines", type=int, default=3)
    parser.add_argument("--conversation-evolution-min-unique-files", type=int, default=1)
    parser.add_argument("--conversation-evolution-min-quality-score", type=int, default=55)
    parser.add_argument("--conversation-evolution-recent-dedupe-days", type=int, default=14)
    parser.add_argument("--conversation-evolution-max-tasks-per-run", type=int, default=3)
    parser.add_argument("--conversation-evolution-schedule-gap-minutes", type=int, default=90)
    parser.add_argument("--conversation-evolution-assignee", default="optimization-agent")

    parser.add_argument("--install-governance-evolution-job", action="store_true")
    parser.add_argument("--governance-evolution-py", default=str(default_governance_evolution_py))
    parser.add_argument("--governance-evolution-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument(
        "--governance-evolution-state",
        default=str(home / ".openclaw/ops/governance-evolution/state.json"),
    )
    parser.add_argument(
        "--governance-evolution-report-dir",
        default=str(home / ".openclaw/ops/governance-evolution/reports"),
    )
    parser.add_argument("--governance-evolution-repo-path", default="")
    parser.add_argument("--governance-evolution-openclaw-config", default=str(home / ".openclaw/openclaw.json"))
    parser.add_argument("--governance-evolution-project-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--governance-evolution-repo-id", default="")
    parser.add_argument("--governance-evolution-repo-name", default="")
    parser.add_argument("--governance-evolution-auto-git-update", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--governance-evolution-git-update-strategy", default="fetch", choices=["fetch", "pull-ff-only"])
    parser.add_argument("--governance-evolution-git-fetch-timeout", type=int, default=120)
    parser.add_argument("--governance-evolution-every-ms", type=int, default=21600000)
    parser.add_argument("--governance-evolution-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--governance-evolution-max-files", type=int, default=120)
    parser.add_argument("--governance-evolution-min-interval-minutes", type=int, default=180)
    parser.add_argument("--governance-evolution-task-clarity", default="ambiguous", choices=["auto", "clear", "ambiguous"])
    parser.add_argument("--governance-evolution-project-context-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--governance-evolution-project-context-assignee", default="project-agent")
    parser.add_argument("--governance-evolution-create-review-task", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--governance-evolution-auto-pr", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--governance-evolution-pr-base", default="main")
    parser.add_argument("--governance-evolution-reviewer-gh-user", default="")
    parser.add_argument("--governance-evolution-push-before-pr", action=argparse.BooleanOptionalAction, default=False)

    parser.add_argument("--install-git-sync-job", action="store_true")
    parser.add_argument("--git-sync-py", default=str(default_git_sync_py))
    parser.add_argument("--git-sync-repo-path", default="")
    parser.add_argument("--git-sync-every-ms", type=int, default=21600000)
    parser.add_argument("--git-sync-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--git-sync-notify-on", default="error", choices=["error", "all"])
    parser.add_argument("--git-sync-remote", default="origin")
    parser.add_argument("--git-sync-branch", default="")
    parser.add_argument("--git-sync-max-files", type=int, default=200)
    parser.add_argument("--git-sync-commit-prefix", default="chore(self-evolution): sync updates")
    parser.add_argument("--git-sync-auto-pull", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--git-sync-push", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--git-sync-include-prefix", action="append", default=[])
    parser.add_argument("--git-sync-exclude-prefix", action="append", default=[])
    parser.add_argument("--git-sync-require-remote-url", action="append", default=[])

    parser.add_argument("--install-auto-update-install-job", action="store_true")
    parser.add_argument("--auto-update-install-py", default=str(default_auto_update_install_py))
    parser.add_argument("--auto-update-install-repo-path", default="")
    parser.add_argument("--auto-update-install-every-ms", type=int, default=3600000)
    parser.add_argument("--auto-update-install-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--auto-update-install-notify-on", default="error", choices=["error", "all"])
    parser.add_argument("--auto-update-install-remote", default="origin")
    parser.add_argument("--auto-update-install-branch", default="")
    parser.add_argument("--auto-update-install-install-cmd", default=default_auto_update_install_cmd)
    parser.add_argument("--auto-update-install-install-on-no-change", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--auto-update-install-git-timeout", type=int, default=240)
    parser.add_argument("--auto-update-install-install-timeout", type=int, default=2400)
    parser.add_argument(
        "--auto-update-install-report-dir",
        default=str(home / ".openclaw/ops/update-install-runs"),
    )
    parser.add_argument("--auto-update-install-require-remote-url", action="append", default=[])

    parser.add_argument("--install-github-web-evolution-job", action="store_true")
    parser.add_argument("--github-web-evolution-py", default=str(default_github_web_evolution_py))
    parser.add_argument("--github-web-evolution-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--github-web-evolution-openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--github-web-evolution-web-root", default=str(home / ".openclaw/web/github"))
    parser.add_argument("--github-web-evolution-state", default=str(home / ".openclaw/ops/github-web-evolution/state.json"))
    parser.add_argument("--github-web-evolution-report-dir", default=str(home / ".openclaw/ops/github-web-evolution/reports"))
    parser.add_argument("--github-web-evolution-every-ms", type=int, default=43200000)
    parser.add_argument("--github-web-evolution-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--github-web-evolution-min-interval-minutes", type=int, default=360)
    parser.add_argument("--github-web-evolution-max-queries", type=int, default=5)
    parser.add_argument("--github-web-evolution-max-repos-per-query", type=int, default=20)
    parser.add_argument("--github-web-evolution-max-total-repos", type=int, default=40)
    parser.add_argument("--github-web-evolution-min-stars", type=int, default=80)
    parser.add_argument("--github-web-evolution-min-quality-score", type=int, default=45)
    parser.add_argument("--github-web-evolution-min-new-or-updated", type=int, default=2)
    parser.add_argument("--github-web-evolution-recent-dedupe-days", type=int, default=14)
    parser.add_argument("--github-web-evolution-max-tasks-per-run", type=int, default=1)
    parser.add_argument("--github-web-evolution-schedule-gap-minutes", type=int, default=90)
    parser.add_argument("--github-web-evolution-assignee", default="optimization-agent")
    parser.add_argument("--github-web-evolution-github-token-env", default="GITHUB_TOKEN")

    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--keep-name-conflicts", action="store_true")
    parser.add_argument("--skip-script-path-check", action="store_true")
    parser.add_argument("--overwrite-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()
    profile_result = apply_install_profile(args)
    legacy_optimize_mode = resolve_legacy_optimize_job_mode(
        str(args.legacy_optimize_jobs_mode),
        str(profile_result.get("profile", "legacy")),
    )

    jobs_file = Path(args.jobs_file).expanduser()
    config_file = Path(args.config_file).expanduser()
    jobs_file.parent.mkdir(parents=True, exist_ok=True)

    data = load_jobs(jobs_file)
    jobs = data.get("jobs", [])
    existing_daily_work_enabled = any(
        isinstance(item, dict) and is_daily_work_report_job(item) and bool(item.get("enabled", True))
        for item in jobs
    )
    daily_report_dedupe_mode = resolve_daily_report_dedupe_mode(
        str(args.daily_report_dedupe_mode),
        str(profile_result.get("profile", "legacy")),
        bool(args.install_daily_work_job) or existing_daily_work_enabled,
    )

    channel = str(args.channel or "").strip()
    target = str(args.to or "").strip()
    if not channel or not target:
        got_channel, got_target = infer_delivery(jobs, ["ops-agent", "optimization-agent", "coordinator", "project-agent"])
        channel = channel or got_channel
        target = target or got_target
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    path_validation = validate_runtime_paths(args)
    if (not path_validation.get("ok")) and (not bool(args.skip_script_path_check)):
        raise SystemExit(
            "script/path validation failed: "
            + ", ".join(path_validation.get("errors", []))
            + "; fix paths or pass --skip-script-path-check"
        )

    cfg = ensure_monitor_config(
        config_file=config_file,
        overwrite=bool(args.overwrite_config),
        switches={
            "incremental": args.incremental_log_mode,
            "full": args.full_log_mode,
            "daily": args.daily_log_mode,
            "api_test": args.api_test_log_mode,
            "system_schedule": args.system_log_mode,
            "daily_work": args.daily_work_log_mode,
            "self_evolution": args.self_evolution_log_mode,
            "conversation_evolution": args.conversation_evolution_log_mode,
            "governance_evolution": args.governance_evolution_log_mode,
            "git_sync": args.git_sync_log_mode,
            "github_web_evolution": args.github_web_evolution_log_mode,
        },
    )

    fresh_jobs = build_core_jobs(
        runner_py=str(Path(args.runner_py).expanduser()),
        config_file=str(config_file),
        state_file=str(Path(args.state_file).expanduser()),
        history_dir=str(Path(args.history_dir).expanduser()),
        every_ms=int(args.incremental_every_ms),
        full_expr=str(args.full_expr),
        daily_expr=str(args.daily_expr),
        tz_name=str(args.tz),
        daily_major_only=bool(args.daily_major_only),
        incremental_log_mode=args.incremental_log_mode,
        full_log_mode=args.full_log_mode,
        daily_log_mode=args.daily_log_mode,
    )
    if bool(args.install_system_schedule_job):
        fresh_jobs.append(
            build_system_schedule_job(
                script_py=str(Path(args.system_schedule_py).expanduser()),
                output_dir=str(Path(args.system_snapshot_dir).expanduser()),
                state_file=str(Path(args.system_state_file).expanduser()),
                every_ms=int(args.system_every_ms),
                log_mode=args.system_log_mode,
            )
        )
    if bool(args.install_api_test_job):
        fresh_jobs.append(
            build_api_test_job(
                script_py=str(Path(args.api_test_py).expanduser()),
                config_file=str(Path(args.api_test_config).expanduser()),
                state_file=str(Path(args.api_test_state).expanduser()),
                history_dir=str(Path(args.api_test_history_dir).expanduser()),
                expr=str(args.api_test_expr),
                tz_name=str(args.tz),
                engine=str(args.api_test_engine),
                log_mode=args.api_test_log_mode,
            )
        )
    if bool(args.install_daily_work_job):
        fresh_jobs.append(
            build_daily_work_job(
                script_py=str(Path(args.daily_work_py).expanduser()),
                db_file=str(Path(args.daily_work_db).expanduser()),
                state_file=str(Path(args.daily_work_state).expanduser()),
                report_dir=str(Path(args.daily_work_report_dir).expanduser()),
                expr=str(args.daily_work_expr),
                tz_name=str(args.tz),
                log_mode=args.daily_work_log_mode,
                webhook_env=str(args.dingtalk_webhook_env),
                secret_env=str(args.dingtalk_secret_env),
                env_file=str(Path(args.daily_work_env_file).expanduser()),
                todo_files=[str(Path(item).expanduser()) for item in args.daily_work_todo_file if str(item).strip()],
            )
        )
    if bool(args.install_self_evolution_job):
        fresh_jobs.append(
            build_self_evolution_job(
                script_py=str(Path(args.self_evolution_py).expanduser()),
                db_file=str(Path(args.self_evolution_db).expanduser()),
                state_file=str(Path(args.self_evolution_state).expanduser()),
                report_dir=str(Path(args.self_evolution_report_dir).expanduser()),
                expr=str(args.self_evolution_expr),
                tz_name=str(args.tz),
                log_mode=args.self_evolution_log_mode,
                lookback_days=max(1, int(args.self_evolution_lookback_days)),
                min_review_interval_days=int(args.self_evolution_min_interval_days),
                max_tasks_per_run=int(args.self_evolution_max_tasks_per_run),
                agent_score_threshold=float(args.self_evolution_agent_score_threshold),
                agent_score_min_reports=max(1, int(args.self_evolution_agent_score_min_reports)),
                agent_score_top_n=max(1, int(args.self_evolution_agent_score_top_n)),
                low_score_guarantee_enabled=bool(args.self_evolution_low_score_guarantee_enabled),
                low_score_guarantee_min_agents=max(1, int(args.self_evolution_low_score_guarantee_min_agents)),
                low_score_guarantee_max_agents=max(1, int(args.self_evolution_low_score_guarantee_max_agents)),
                low_score_guarantee_threshold=float(args.self_evolution_low_score_guarantee_threshold),
            )
        )
    if bool(args.install_upgrade_feedback_job):
        fresh_jobs.append(
            build_upgrade_feedback_job(
                script_py=str(Path(args.upgrade_feedback_py).expanduser()),
                executor_run_dir=str(Path(args.upgrade_feedback_executor_run_dir).expanduser()),
                output_dir=str(Path(args.upgrade_feedback_output_dir).expanduser()),
                state_file=str(Path(args.upgrade_feedback_state).expanduser()),
                every_ms=max(3600000, int(args.upgrade_feedback_every_ms)),
                log_mode=str(args.upgrade_feedback_log_mode),
                workflow_target=str(args.upgrade_feedback_workflow_target),
                skill_name=str(args.upgrade_feedback_skill_name),
                skill_assignee=str(args.upgrade_feedback_skill_assignee),
                baseline_count=max(1, int(args.upgrade_feedback_baseline_count)),
                candidate_count=max(1, int(args.upgrade_feedback_candidate_count)),
                task_db=str(Path(args.upgrade_feedback_task_db).expanduser()),
                auto_create_tasks=bool(args.upgrade_feedback_auto_create_tasks),
                workflow_profile_registry=str(Path(args.upgrade_feedback_workflow_profile_registry).expanduser()),
                benchmark_suite_file=str(Path(args.upgrade_feedback_benchmark_suite_file).expanduser()),
                benchmark_suite_id=str(args.upgrade_feedback_benchmark_suite_id).strip(),
                auto_apply_workflow_promotion=bool(args.upgrade_feedback_auto_apply_workflow_promotion),
                promotion_operator=str(args.upgrade_feedback_promotion_operator).strip() or "cron-upgrade-feedback",
                task_score_threshold=float(args.upgrade_feedback_task_score_threshold),
                task_schedule_gap_minutes=max(1, int(args.upgrade_feedback_task_schedule_gap_minutes)),
            )
        )
    if bool(args.install_benchmark_sweep_job):
        fresh_jobs.append(
            build_benchmark_sweep_job(
                script_py=str(Path(args.benchmark_sweep_py).expanduser()),
                executor_run_dir=str(Path(args.benchmark_sweep_executor_run_dir).expanduser()),
                output_root=str(Path(args.benchmark_sweep_output_root).expanduser()),
                state_root=str(Path(args.benchmark_sweep_state_root).expanduser()),
                benchmark_suite_file=str(Path(args.benchmark_sweep_benchmark_suite_file).expanduser()),
                workflow_profile_registry=str(Path(args.benchmark_sweep_workflow_profile_registry).expanduser()),
                task_db=str(Path(args.benchmark_sweep_task_db).expanduser()),
                output_consumer_py=str(Path(args.benchmark_sweep_output_py).expanduser()),
                summary_file=str(Path(args.benchmark_sweep_summary_file).expanduser()),
                consumer_output_file=str(Path(args.benchmark_sweep_consumer_output_file).expanduser()),
                consumer_notify_on=str(args.benchmark_sweep_consumer_notify_on).strip() or "error",
                every_ms=max(3600000, int(args.benchmark_sweep_every_ms)),
                log_mode=str(args.benchmark_sweep_log_mode),
                auto_create_tasks=bool(args.benchmark_sweep_auto_create_tasks),
                auto_apply_workflow_promotion=bool(args.benchmark_sweep_auto_apply_workflow_promotion),
                promotion_operator=str(args.benchmark_sweep_promotion_operator).strip() or "cron-benchmark-sweep",
                task_score_threshold=float(args.benchmark_sweep_task_score_threshold),
                task_schedule_gap_minutes=max(1, int(args.benchmark_sweep_task_schedule_gap_minutes)),
                suite_ids=[str(item).strip() for item in (args.benchmark_sweep_suite_id or []) if str(item).strip()],
            )
        )
    if bool(args.install_benchmark_output_job):
        fresh_jobs.append(
            build_benchmark_output_job(
                script_py=str(Path(args.benchmark_output_py).expanduser()),
                summary_file=str(Path(args.benchmark_output_summary_file).expanduser()),
                output_file=str(Path(args.benchmark_output_output_file).expanduser()),
                notify_on=str(args.benchmark_output_notify_on).strip() or "error",
                every_ms=max(3600000, int(args.benchmark_output_every_ms)),
                delay_ms=max(60000, int(args.benchmark_output_delay_ms)),
                log_mode=str(args.benchmark_output_log_mode),
            )
        )
    if bool(args.install_task_output_broadcast_job):
        fresh_jobs.append(
            build_task_output_broadcast_job(
                script_py=str(Path(args.task_output_broadcast_py).expanduser()),
                db_file=str(Path(args.task_output_broadcast_db).expanduser()),
                state_file=str(Path(args.task_output_broadcast_state).expanduser()),
                output_file=str(Path(args.task_output_broadcast_output).expanduser()),
                lookback_hours=max(1, int(args.task_output_broadcast_lookback_hours)),
                limit=max(1, int(args.task_output_broadcast_limit)),
                event_limit=max(20, int(args.task_output_broadcast_event_limit)),
                notify_on=str(args.task_output_broadcast_notify_on).strip() or "error",
                every_ms=max(300000, int(args.task_output_broadcast_every_ms)),
                delay_ms=max(60000, int(args.task_output_broadcast_delay_ms)),
                log_mode=str(args.task_output_broadcast_log_mode),
            )
        )
    if bool(args.install_control_plane_summary_job):
        fresh_jobs.append(
            build_control_plane_summary_job(
                script_py=str(Path(args.control_plane_summary_py).expanduser()),
                db_file=str(Path(args.control_plane_summary_db).expanduser()),
                state_file=str(Path(args.control_plane_summary_state).expanduser()),
                output_file=str(Path(args.control_plane_summary_output).expanduser()),
                lookback_hours=max(1, int(args.control_plane_summary_lookback_hours)),
                limit=max(1, int(args.control_plane_summary_limit)),
                notify_on=str(args.control_plane_summary_notify_on).strip() or "activity",
                every_ms=max(3600000, int(args.control_plane_summary_every_ms)),
                delay_ms=max(60000, int(args.control_plane_summary_delay_ms)),
                log_mode=str(args.control_plane_summary_log_mode),
            )
        )
    if bool(args.install_control_plane_dashboard_job):
        fresh_jobs.append(
            build_control_plane_dashboard_job(
                script_py=str(Path(args.control_plane_dashboard_py).expanduser()),
                db_file=str(Path(args.control_plane_dashboard_db).expanduser()),
                benchmark_summary_file=str(Path(args.control_plane_dashboard_benchmark_summary_file).expanduser()),
                json_output=str(Path(args.control_plane_dashboard_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_dashboard_markdown_output).expanduser()),
                html_output=str(Path(args.control_plane_dashboard_html_output).expanduser()),
                lookback_hours=max(1, int(args.control_plane_dashboard_lookback_hours)),
                limit=max(1, int(args.control_plane_dashboard_limit)),
                every_ms=max(3600000, int(args.control_plane_dashboard_every_ms)),
                delay_ms=max(60000, int(args.control_plane_dashboard_delay_ms)),
                log_mode=str(args.control_plane_dashboard_log_mode),
            )
        )
    if bool(args.install_control_plane_optimization_job):
        fresh_jobs.append(
            build_control_plane_optimization_job(
                script_py=str(Path(args.control_plane_optimization_py).expanduser()),
                db_file=str(Path(args.control_plane_optimization_db).expanduser()),
                json_output=str(Path(args.control_plane_optimization_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_optimization_markdown_output).expanduser()),
                lookback_hours=max(1, int(args.control_plane_optimization_lookback_hours)),
                limit=max(1, int(args.control_plane_optimization_limit)),
                every_ms=max(3600000, int(args.control_plane_optimization_every_ms)),
                delay_ms=max(60000, int(args.control_plane_optimization_delay_ms)),
                log_mode=str(args.control_plane_optimization_log_mode),
            )
        )
    if bool(args.install_control_plane_optimization_dispatch_job):
        fresh_jobs.append(
            build_control_plane_optimization_dispatch_job(
                script_py=str(Path(args.control_plane_optimization_dispatch_py).expanduser()),
                report_file=str(Path(args.control_plane_optimization_dispatch_report_file).expanduser()),
                task_db=str(Path(args.control_plane_optimization_dispatch_task_db).expanduser()),
                json_output=str(Path(args.control_plane_optimization_dispatch_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_optimization_dispatch_markdown_output).expanduser()),
                execution_workflow_profile=str(args.control_plane_optimization_dispatch_execution_workflow_profile),
                execution_workflow_channel=str(args.control_plane_optimization_dispatch_execution_workflow_channel),
                schedule_gap_minutes=max(0, int(args.control_plane_optimization_dispatch_schedule_gap_minutes)),
                every_ms=max(3600000, int(args.control_plane_optimization_dispatch_every_ms)),
                delay_ms=max(60000, int(args.control_plane_optimization_dispatch_delay_ms)),
                log_mode=str(args.control_plane_optimization_dispatch_log_mode),
            )
        )
    if bool(args.install_control_plane_optimization_review_job):
        fresh_jobs.append(
            build_control_plane_optimization_review_job(
                script_py=str(Path(args.control_plane_optimization_review_py).expanduser()),
                task_db=str(Path(args.control_plane_optimization_review_task_db).expanduser()),
                json_output=str(Path(args.control_plane_optimization_review_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_optimization_review_markdown_output).expanduser()),
                lookback_hours=max(1, int(args.control_plane_optimization_review_lookback_hours)),
                limit=max(1, int(args.control_plane_optimization_review_limit)),
                every_ms=max(3600000, int(args.control_plane_optimization_review_every_ms)),
                delay_ms=max(60000, int(args.control_plane_optimization_review_delay_ms)),
                log_mode=str(args.control_plane_optimization_review_log_mode),
            )
        )
    if bool(args.install_control_plane_profile_update_dispatch_job):
        fresh_jobs.append(
            build_control_plane_profile_update_dispatch_job(
                script_py=str(Path(args.control_plane_profile_update_dispatch_py).expanduser()),
                review_file=str(Path(args.control_plane_profile_update_dispatch_review_file).expanduser()),
                task_db=str(Path(args.control_plane_profile_update_dispatch_task_db).expanduser()),
                json_output=str(Path(args.control_plane_profile_update_dispatch_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_profile_update_dispatch_markdown_output).expanduser()),
                execution_workflow_profile=str(args.control_plane_profile_update_dispatch_execution_workflow_profile),
                execution_workflow_channel=str(args.control_plane_profile_update_dispatch_execution_workflow_channel),
                schedule_gap_minutes=max(0, int(args.control_plane_profile_update_dispatch_schedule_gap_minutes)),
                every_ms=max(3600000, int(args.control_plane_profile_update_dispatch_every_ms)),
                delay_ms=max(60000, int(args.control_plane_profile_update_dispatch_delay_ms)),
                log_mode=str(args.control_plane_profile_update_dispatch_log_mode),
            )
        )
    if bool(args.install_control_plane_profile_update_apply_job):
        fresh_jobs.append(
            build_control_plane_profile_update_apply_job(
                script_py=str(Path(args.control_plane_profile_update_apply_py).expanduser()),
                task_db=str(Path(args.control_plane_profile_update_apply_task_db).expanduser()),
                registry_file=str(Path(args.control_plane_profile_update_apply_registry_file).expanduser()),
                json_output=str(Path(args.control_plane_profile_update_apply_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_profile_update_apply_markdown_output).expanduser()),
                target_channel=str(args.control_plane_profile_update_apply_target_channel),
                lookback_hours=max(1, int(args.control_plane_profile_update_apply_lookback_hours)),
                limit=max(1, int(args.control_plane_profile_update_apply_limit)),
                every_ms=max(3600000, int(args.control_plane_profile_update_apply_every_ms)),
                delay_ms=max(60000, int(args.control_plane_profile_update_apply_delay_ms)),
                log_mode=str(args.control_plane_profile_update_apply_log_mode),
            )
        )
    if bool(args.install_control_plane_profile_update_validation_job):
        fresh_jobs.append(
            build_control_plane_profile_update_validation_job(
                script_py=str(Path(args.control_plane_profile_update_validation_py).expanduser()),
                apply_file=str(Path(args.control_plane_profile_update_validation_apply_file).expanduser()),
                benchmark_suite_file=str(Path(args.control_plane_profile_update_validation_benchmark_suite_file).expanduser()),
                executor_run_dir=str(Path(args.control_plane_profile_update_validation_executor_run_dir).expanduser()),
                output_root=str(Path(args.control_plane_profile_update_validation_output_root).expanduser()),
                state_file=str(Path(args.control_plane_profile_update_validation_state_file).expanduser()),
                task_db=str(Path(args.control_plane_profile_update_validation_task_db).expanduser()),
                workflow_profile_registry=str(Path(args.control_plane_profile_update_validation_workflow_profile_registry).expanduser()),
                json_output=str(Path(args.control_plane_profile_update_validation_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_profile_update_validation_markdown_output).expanduser()),
                every_ms=max(3600000, int(args.control_plane_profile_update_validation_every_ms)),
                delay_ms=max(60000, int(args.control_plane_profile_update_validation_delay_ms)),
                log_mode=str(args.control_plane_profile_update_validation_log_mode),
                auto_create_tasks=bool(args.control_plane_profile_update_validation_auto_create_tasks),
                auto_apply_workflow_promotion=bool(args.control_plane_profile_update_validation_auto_apply_workflow_promotion),
                promotion_operator=str(args.control_plane_profile_update_validation_promotion_operator).strip() or "control-plane-validation",
            )
        )
    if bool(args.install_control_plane_acceptance_job):
        fresh_jobs.append(
            build_control_plane_acceptance_job(
                script_py=str(Path(args.control_plane_acceptance_py).expanduser()),
                jobs_file=str(Path(args.control_plane_acceptance_jobs_file).expanduser()),
                json_output=str(Path(args.control_plane_acceptance_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_acceptance_markdown_output).expanduser()),
                every_ms=max(3600000, int(args.control_plane_acceptance_every_ms)),
                delay_ms=max(60000, int(args.control_plane_acceptance_delay_ms)),
                log_mode=str(args.control_plane_acceptance_log_mode),
            )
        )
    if bool(args.install_control_plane_live_acceptance_job):
        fresh_jobs.append(
            build_control_plane_live_acceptance_job(
                script_py=str(Path(args.control_plane_live_acceptance_py).expanduser()),
                workspace_root=str(Path(args.control_plane_live_acceptance_workspace_root).expanduser()),
                jobs_file=str(Path(args.control_plane_live_acceptance_jobs_file).expanduser()),
                json_output=str(Path(args.control_plane_live_acceptance_json_output).expanduser()),
                markdown_output=str(Path(args.control_plane_live_acceptance_markdown_output).expanduser()),
                lookback_hours=max(1, int(args.control_plane_live_acceptance_lookback_hours)),
                limit=max(1, int(args.control_plane_live_acceptance_limit)),
                every_ms=max(3600000, int(args.control_plane_live_acceptance_every_ms)),
                delay_ms=max(60000, int(args.control_plane_live_acceptance_delay_ms)),
                log_mode=str(args.control_plane_live_acceptance_log_mode),
            )
        )
    if bool(args.install_conversation_evolution_job):
        fresh_jobs.append(
            build_conversation_evolution_job(
                script_py=str(Path(args.conversation_evolution_py).expanduser()),
                db_file=str(Path(args.conversation_evolution_db).expanduser()),
                openclaw_home=str(Path(args.conversation_evolution_openclaw_home).expanduser()),
                state_file=str(Path(args.conversation_evolution_state).expanduser()),
                report_dir=str(Path(args.conversation_evolution_report_dir).expanduser()),
                every_ms=max(600000, int(args.conversation_evolution_every_ms)),
                log_mode=args.conversation_evolution_log_mode,
                lookback_hours=max(1, int(args.conversation_evolution_lookback_hours)),
                min_interval_minutes=max(1, int(args.conversation_evolution_min_interval_minutes)),
                max_files=max(10, int(args.conversation_evolution_max_files)),
                max_evidence_per_candidate=max(1, int(args.conversation_evolution_max_evidence_per_candidate)),
                min_evidence_lines=max(1, int(args.conversation_evolution_min_evidence_lines)),
                min_unique_files=max(1, int(args.conversation_evolution_min_unique_files)),
                min_quality_score=max(1, int(args.conversation_evolution_min_quality_score)),
                recent_dedupe_days=max(0, int(args.conversation_evolution_recent_dedupe_days)),
                max_tasks_per_run=max(1, int(args.conversation_evolution_max_tasks_per_run)),
                schedule_gap_minutes=max(1, int(args.conversation_evolution_schedule_gap_minutes)),
                assignee=str(args.conversation_evolution_assignee).strip() or "optimization-agent",
            )
        )
    if bool(args.install_governance_evolution_job):
        raw_repo_path = str(args.governance_evolution_repo_path or "").strip()
        repo_path = str(Path(raw_repo_path).expanduser()) if raw_repo_path else ""
        fresh_jobs.append(
            build_governance_evolution_job(
                script_py=str(Path(args.governance_evolution_py).expanduser()),
                db_file=str(Path(args.governance_evolution_db).expanduser()),
                state_file=str(Path(args.governance_evolution_state).expanduser()),
                report_dir=str(Path(args.governance_evolution_report_dir).expanduser()),
                repo_path=repo_path,
                openclaw_config=str(Path(args.governance_evolution_openclaw_config).expanduser()),
                project_registry=str(Path(args.governance_evolution_project_registry).expanduser()),
                repo_id=str(args.governance_evolution_repo_id).strip(),
                repo_name=str(args.governance_evolution_repo_name).strip(),
                auto_git_update=bool(args.governance_evolution_auto_git_update),
                git_update_strategy=str(args.governance_evolution_git_update_strategy).strip() or "fetch",
                git_fetch_timeout=max(30, int(args.governance_evolution_git_fetch_timeout)),
                every_ms=max(600000, int(args.governance_evolution_every_ms)),
                log_mode=args.governance_evolution_log_mode,
                max_files=max(10, int(args.governance_evolution_max_files)),
                min_interval_minutes=max(1, int(args.governance_evolution_min_interval_minutes)),
                task_clarity=str(args.governance_evolution_task_clarity).strip() or "ambiguous",
                project_context_gate=bool(args.governance_evolution_project_context_gate),
                project_context_assignee=str(args.governance_evolution_project_context_assignee).strip() or "project-agent",
                create_review_task=bool(args.governance_evolution_create_review_task),
                auto_pr=bool(args.governance_evolution_auto_pr),
                pr_base=str(args.governance_evolution_pr_base).strip() or "main",
                reviewer_gh_user=str(args.governance_evolution_reviewer_gh_user).strip(),
                push_before_pr=bool(args.governance_evolution_push_before_pr),
            )
        )
    if bool(args.install_git_sync_job):
        git_sync_repo_raw = str(args.git_sync_repo_path or args.governance_evolution_repo_path or "").strip()
        git_sync_repo_path = str(Path(git_sync_repo_raw).expanduser()) if git_sync_repo_raw else ""
        include_prefixes = [str(x).strip() for x in (args.git_sync_include_prefix or []) if str(x).strip()]
        if not include_prefixes:
            include_prefixes = [
                "scripts/openclaw-ops/",
                "hooks/",
                "skills/",
                "agents/",
            ]
        exclude_prefixes = [str(x).strip() for x in (args.git_sync_exclude_prefix or []) if str(x).strip()]
        if not exclude_prefixes:
            exclude_prefixes = [
                ".workflow/project-index/",
                ".workflow/project-index-local/",
                ".workflow/experience/",
                ".workflow/sessions/",
                "scripts/openclaw-ops/policy/runtime/",
                "openclaw-memory/",
                "memory/",
            ]
        fresh_jobs.append(
            build_git_sync_job(
                script_py=str(Path(args.git_sync_py).expanduser()),
                repo_path=git_sync_repo_path,
                every_ms=max(600000, int(args.git_sync_every_ms)),
                log_mode=args.git_sync_log_mode,
                remote=str(args.git_sync_remote).strip() or "origin",
                branch=str(args.git_sync_branch).strip(),
                max_files=max(1, int(args.git_sync_max_files)),
                commit_prefix=str(args.git_sync_commit_prefix).strip() or "chore(self-evolution): sync updates",
                auto_pull=bool(args.git_sync_auto_pull),
                push=bool(args.git_sync_push),
                include_prefixes=include_prefixes,
                exclude_prefixes=exclude_prefixes,
                required_remote_urls=[str(x).strip() for x in (args.git_sync_require_remote_url or []) if str(x).strip()],
                notify_on=str(args.git_sync_notify_on or "error").strip() or "error",
            )
        )
    if bool(args.install_auto_update_install_job):
        auto_update_repo_raw = str(args.auto_update_install_repo_path or args.governance_evolution_repo_path or "").strip()
        auto_update_repo_path = str(Path(auto_update_repo_raw).expanduser()) if auto_update_repo_raw else ""
        required_urls = [
            str(x).strip()
            for x in (args.auto_update_install_require_remote_url or [])
            if str(x).strip()
        ]
        if not required_urls:
            required_urls = [
                "https://github.com/XX-Trader/openclaw-hardflow-backup-20260302",
                "https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git",
            ]
        fresh_jobs.append(
            build_auto_update_install_job(
                script_py=str(Path(args.auto_update_install_py).expanduser()),
                repo_path=auto_update_repo_path,
                every_ms=max(600000, int(args.auto_update_install_every_ms)),
                log_mode=args.auto_update_install_log_mode,
                remote=str(args.auto_update_install_remote).strip() or "origin",
                branch=str(args.auto_update_install_branch).strip(),
                install_cmd=str(args.auto_update_install_install_cmd).strip(),
                install_on_no_change=bool(args.auto_update_install_install_on_no_change),
                git_timeout=max(30, int(args.auto_update_install_git_timeout)),
                install_timeout=max(30, int(args.auto_update_install_install_timeout)),
                report_dir=str(Path(args.auto_update_install_report_dir).expanduser()),
                required_remote_urls=required_urls,
                notify_on=str(args.auto_update_install_notify_on or "error").strip() or "error",
            )
        )
    if bool(args.install_github_web_evolution_job):
        fresh_jobs.append(
            build_github_web_evolution_job(
                script_py=str(Path(args.github_web_evolution_py).expanduser()),
                db_file=str(Path(args.github_web_evolution_db).expanduser()),
                openclaw_home=str(Path(args.github_web_evolution_openclaw_home).expanduser()),
                web_root=str(Path(args.github_web_evolution_web_root).expanduser()),
                state_file=str(Path(args.github_web_evolution_state).expanduser()),
                report_dir=str(Path(args.github_web_evolution_report_dir).expanduser()),
                every_ms=max(600000, int(args.github_web_evolution_every_ms)),
                log_mode=args.github_web_evolution_log_mode,
                min_interval_minutes=max(1, int(args.github_web_evolution_min_interval_minutes)),
                max_queries=max(1, int(args.github_web_evolution_max_queries)),
                max_repos_per_query=max(1, int(args.github_web_evolution_max_repos_per_query)),
                max_total_repos=max(1, int(args.github_web_evolution_max_total_repos)),
                min_stars=max(0, int(args.github_web_evolution_min_stars)),
                min_quality_score=max(1, int(args.github_web_evolution_min_quality_score)),
                min_new_or_updated=max(1, int(args.github_web_evolution_min_new_or_updated)),
                recent_dedupe_days=max(0, int(args.github_web_evolution_recent_dedupe_days)),
                max_tasks_per_run=max(1, int(args.github_web_evolution_max_tasks_per_run)),
                schedule_gap_minutes=max(1, int(args.github_web_evolution_schedule_gap_minutes)),
                assignee=str(args.github_web_evolution_assignee).strip() or "optimization-agent",
                github_token_env=str(args.github_web_evolution_github_token_env).strip() or "GITHUB_TOKEN",
            )
        )

    openclaw_home = infer_openclaw_home_from_jobs_file(jobs_file)
    audit_before = audit_jobs(jobs=jobs, expected_jobs=fresh_jobs, channel=channel, target=target)
    merged_jobs, status = upsert_jobs(jobs=jobs, fresh_jobs=fresh_jobs, channel=channel, target=target)
    removed_name_conflicts: list[dict[str, str]] = []
    if not bool(args.keep_name_conflicts):
        merged_jobs, removed_name_conflicts = remove_name_conflicts(jobs=merged_jobs, expected_jobs=fresh_jobs)
    merged_jobs, legacy_optimize_policy_result = apply_legacy_optimize_job_policy(
        jobs=merged_jobs,
        mode=legacy_optimize_mode,
    )
    merged_jobs, daily_report_dedupe_result = apply_daily_report_dedupe_policy(
        jobs=merged_jobs,
        mode=daily_report_dedupe_mode,
    )
    harden_result = harden_known_jobs(jobs=merged_jobs, openclaw_home=openclaw_home)
    harden_missing_refs = list(harden_result.get("missing_refs", []))
    if harden_missing_refs and not bool(args.skip_script_path_check):
        raise SystemExit(
            "harden known jobs failed: missing runtime scripts: "
            + ", ".join(harden_missing_refs)
            + "; run workflow sync first or pass --skip-script-path-check"
        )
    data["jobs"] = merged_jobs
    audit_after = audit_jobs(jobs=merged_jobs, expected_jobs=fresh_jobs, channel=channel, target=target)

    backup_file = ""
    if jobs_file.exists() and not args.dry_run:
        backup = jobs_file.with_name(f"{jobs_file.name}.bak.{stamp()}")
        shutil.copy2(jobs_file, backup)
        backup_file = str(backup)
    if not args.dry_run:
        write_json_atomic(
            jobs_file,
            data,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )

    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "jobs_file": str(jobs_file),
        "backup": backup_file,
        "config_file": str(config_file),
        "delivery": {"channel": channel, "to": target},
        "install_profile": profile_result,
        "legacy_optimize_policy": legacy_optimize_policy_result,
        "daily_report_dedupe_policy": daily_report_dedupe_result,
        "job_status": status,
        "job_ids": [item["id"] for item in fresh_jobs],
        "official_cron_surface": build_official_cron_surface([item["id"] for item in fresh_jobs]),
        "skill_log_switches": cfg.get("skill_log_switches", {}),
        "path_validation": path_validation,
        "audit": {
            "before": audit_before,
            "after": audit_after,
            "removed_name_conflicts": removed_name_conflicts,
        },
        "harden_known_jobs": {
            "status": harden_result.get("status", {}),
            "missing_refs": harden_missing_refs,
        },
        "installed": {
            "core_jobs": True,
            "system_schedule_job": bool(args.install_system_schedule_job),
            "api_test_job": bool(args.install_api_test_job),
            "daily_work_job": bool(args.install_daily_work_job),
            "self_evolution_job": bool(args.install_self_evolution_job),
            "benchmark_sweep_job": bool(args.install_benchmark_sweep_job),
            "control_plane_profile_update_validation_job": bool(args.install_control_plane_profile_update_validation_job),
            "control_plane_acceptance_job": bool(args.install_control_plane_acceptance_job),
            "conversation_evolution_job": bool(args.install_conversation_evolution_job),
            "governance_evolution_job": bool(args.install_governance_evolution_job),
            "git_sync_job": bool(args.install_git_sync_job),
            "auto_update_install_job": bool(args.install_auto_update_install_job),
            "github_web_evolution_job": bool(args.install_github_web_evolution_job),
        },
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if backup_file:
            print(f"backup={backup_file}")
        print(f"jobs_file={jobs_file}")
        print(f"config_file={config_file}")
        print(f"path_validation_ok={path_validation.get('ok')}")
        for jid in result["job_ids"]:
            print(f"{jid}={status.get(jid, 'unknown')}")
        print(f"delivery={channel}:{target}")
        install_profile = result.get("install_profile", {})
        print(f"install_profile={install_profile.get('profile', 'legacy')}")
        if install_profile.get("changes"):
            print("install_profile_changes=" + json.dumps(install_profile.get("changes", {}), ensure_ascii=False))
        if install_profile.get("skipped"):
            print("install_profile_skipped=" + "; ".join(str(x) for x in install_profile.get("skipped", [])))
        legacy_policy = result.get("legacy_optimize_policy", {})
        print(
            "legacy_optimize_policy="
            f"{legacy_policy.get('mode', 'keep')},"
            f"matched:{legacy_policy.get('matched', 0)},"
            f"disabled:{legacy_policy.get('disabled', 0)},"
            f"removed:{legacy_policy.get('removed', 0)}"
        )
        dedupe_policy = result.get("daily_report_dedupe_policy", {})
        print(
            "daily_report_dedupe_policy="
            f"{dedupe_policy.get('mode', 'keep')},"
            f"matched:{dedupe_policy.get('matched', 0)},"
            f"disabled:{dedupe_policy.get('disabled', 0)}"
        )
        before_counts = result.get("audit", {}).get("before", {}).get("counts", {})
        after_counts = result.get("audit", {}).get("after", {}).get("counts", {})
        print(
            "audit_before="
            f"compliant:{before_counts.get('compliant', 0)},"
            f"drifted:{before_counts.get('drifted', 0)},"
            f"missing:{before_counts.get('missing', 0)}"
        )
        print(
            "audit_after="
            f"compliant:{after_counts.get('compliant', 0)},"
            f"drifted:{after_counts.get('drifted', 0)},"
            f"missing:{after_counts.get('missing', 0)}"
        )
        print(f"name_conflicts_removed={len(result.get('audit', {}).get('removed_name_conflicts', []))}")
        harden_status = result.get("harden_known_jobs", {}).get("status", {})
        print(f"hardened_known_jobs={len(harden_status)}")
        if harden_status:
            print("hardened_job_names=" + ",".join(sorted(str(k) for k in harden_status.keys())))
        missing_refs = result.get("harden_known_jobs", {}).get("missing_refs", [])
        if missing_refs:
            print("harden_missing_refs=" + ",".join(str(x) for x in missing_refs))
        cron_surface = result.get("official_cron_surface", {})
        print("cron_surface=official-cron")
        print(f"cron_status_cmd={cron_surface.get('status_cmd', 'openclaw cron status --json')}")
        print("cron_run_hint=openclaw cron run <job-id> --force")
        print("cron_runs_hint=openclaw cron runs --id <job-id> --limit 20")
        print(json.dumps(result["installed"], ensure_ascii=False))
        if args.dry_run:
            print("dry_run=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

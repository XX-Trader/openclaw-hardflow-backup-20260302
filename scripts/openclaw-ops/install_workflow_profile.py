#!/usr/bin/env python3
"""Install OpenClaw workflow cron jobs by profile: core or all."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILES = {"core", "all"}
CORE_TASKS = [1, 2, 3, 4, 5, 7, 8, 9]
ALL_TASKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
OVERLAY_SYNC_STEP = "sync_overlay_openclaw_config (runtime boundary)"
CORE_RUNTIME_HOOKS = (
    "hardflow-command-guard",
    "hardflow-audit",
    "hardflow-stop-gate-reminder",
    "hardflow-policy-enforcer",
)
LOCAL_TELEGRAM_CREDENTIAL_KEYS = (
    "botToken",
    "apiId",
    "apiHash",
    "phone",
    "phoneNumber",
    "session",
    "sessionString",
)


def render_cmd(cmd: list[str]) -> str:
    try:
        return shlex.join(cmd)
    except Exception:
        return " ".join(cmd)


def run_step(name: str, cmd: list[str], dry_run: bool) -> dict[str, Any]:
    print(f"\n== {name} ==")
    print("$ " + render_cmd(cmd))
    if dry_run:
        print("[dry-run] skipped")
        return {"step": name, "ok": True, "dry_run": True, "returncode": 0}

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return {
        "step": name,
        "ok": proc.returncode == 0,
        "dry_run": False,
        "returncode": int(proc.returncode),
        "stdout": stdout,
        "stderr": stderr,
    }


def delivery_args(channel: str, target: str) -> list[str]:
    out: list[str] = []
    if channel.strip():
        out.extend(["--channel", channel.strip()])
    if target.strip():
        out.extend(["--to", target.strip()])
    return out


def build_install_task_executor_cmd(
    *,
    python_bin: str,
    here: Path,
    jobs_file: str,
    ops_home: str,
    task_db: str,
    every_ms: int,
    max_tasks: int,
    model: str,
    local_agent: bool,
    channel: str,
    target: str,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "install_task_executor_job.py"),
        "--jobs-file",
        jobs_file,
        "--executor-py",
        str(Path(ops_home) / "policy/task_executor_runner.py"),
        "--db",
        task_db,
        "--every-ms",
        str(max(300000, int(every_ms))),
        "--max-tasks",
        str(max(1, int(max_tasks))),
        "--actor",
        "coordinator",
        "--planner-id",
        "coordinator",
        "--openclaw-bin",
        "openclaw",
        "--report-dir",
        str(Path(ops_home) / "task-center/executor-runs"),
        "--notify-on",
        "error",
    ]
    if str(model).strip().lower() not in {"", "auto", "default"}:
        cmd.extend(["--model", str(model).strip()])
    cmd.append("--local-agent" if bool(local_agent) else "--no-local-agent")
    cmd.extend(delivery_args(channel, target))
    cmd.append("--emit-json")
    return cmd


def build_install_project_index_cmd(
    *,
    python_bin: str,
    here: Path,
    jobs_file: str,
    ops_home: str,
    project_registry: str,
    task_db: str,
    every_ms: int,
    channel: str,
    target: str,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "install_project_index_job.py"),
        "--jobs-file",
        jobs_file,
        "--every-ms",
        str(max(600000, int(every_ms))),
        "--maintainer-py",
        str(Path(ops_home) / "policy/project_index_maintainer.py"),
        "--registry",
        project_registry,
        "--task-db",
        task_db,
        "--task-id",
        "cron:project-index-maintainer-30m",
        "--actor",
        "project-agent",
        "--no-git-pull",
    ]
    cmd.extend(delivery_args(channel, target))
    cmd.append("--emit-json")
    return cmd


def build_install_web_intel_cmd(
    *,
    python_bin: str,
    here: Path,
    jobs_file: str,
    ops_home: str,
    openclaw_home: str,
    project_registry: str,
    collect_every_ms: int,
    opt_review_every_ms: int,
    project_review_every_ms: int,
    collect_min_interval_minutes: int,
    review_min_interval_minutes: int,
    channel: str,
    target: str,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "install_web_intel_jobs.py"),
        "--jobs-file",
        jobs_file,
        "--python-bin",
        python_bin,
        "--collector-py",
        str(Path(ops_home) / "web_intel_collect_runner.py"),
        "--review-py",
        str(Path(ops_home) / "web_intel_review_runner.py"),
        "--openclaw-home",
        openclaw_home,
        "--collect-sources-file",
        str(Path(ops_home) / "web/sources.json"),
        "--project-doc-sources-file",
        str(Path(ops_home) / "web/project_docs_sources.json"),
        "--project-registry",
        project_registry,
        "--collect-every-ms",
        str(max(600000, int(collect_every_ms))),
        "--opt-review-every-ms",
        str(max(600000, int(opt_review_every_ms))),
        "--project-review-every-ms",
        str(max(600000, int(project_review_every_ms))),
        "--collect-min-interval-minutes",
        str(max(1, int(collect_min_interval_minutes))),
        "--review-min-interval-minutes",
        str(max(1, int(review_min_interval_minutes))),
        "--collect-notify-on",
        "error",
        "--review-notify-on",
        "error",
    ]
    cmd.extend(delivery_args(channel, target))
    return cmd


def build_ensure_runtime_skills_cmd(
    *,
    python_bin: str,
    here: Path,
    openclaw_home: str,
    manifest_path: str,
    dry_run: bool,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "ensure_runtime_skills.py"),
        "--openclaw-home",
        openclaw_home,
        "--manifest",
        manifest_path,
        "--emit-json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def build_sync_runtime_plugin_overrides_cmd(
    *,
    python_bin: str,
    here: Path,
    openclaw_home: str,
    dry_run: bool,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "sync_runtime_plugin_overrides.py"),
        "--source-dir",
        str(here / "runtime-plugin-overrides"),
        "--openclaw-home",
        openclaw_home,
        "--emit-json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def build_normalize_runtime_binding_tasks_cmd(
    *,
    python_bin: str,
    here: Path,
    task_db: str,
    dry_run: bool,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "normalize_runtime_binding_tasks.py"),
        "--db",
        task_db,
        "--emit-json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def build_recover_stale_cron_running_state_cmd(
    *,
    python_bin: str,
    here: Path,
    jobs_file: str,
    stale_minutes: int,
    dry_run: bool,
) -> list[str]:
    cmd = [
        python_bin,
        str(here / "recover_stale_cron_running_state.py"),
        "--jobs-file",
        jobs_file,
        "--stale-minutes",
        str(max(1, int(stale_minutes))),
        "--emit-json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def normalize_path(text: str) -> str:
    return str(Path(os.path.expanduser(text)).resolve())


def now_stamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"json root must be an object: {path}")
    return raw


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    fresh: dict[str, Any] = {}
    parent[key] = fresh
    return fresh


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value or "").strip()
        items = [text] if text else []
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def merge_overlay_object(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_overlay_object(current, value)
        else:
            merged[key] = value
    return merged


def preserve_local_telegram_credentials(base_cfg: dict[str, Any], merged_cfg: dict[str, Any]) -> list[str]:
    base_channels = base_cfg.get("channels")
    merged_channels = merged_cfg.get("channels")
    if not isinstance(base_channels, dict) or not isinstance(merged_channels, dict):
        return []

    base_tg = base_channels.get("telegram")
    merged_tg = merged_channels.get("telegram")
    if not isinstance(base_tg, dict) or not isinstance(merged_tg, dict):
        return []

    preserved: list[str] = []
    for key in LOCAL_TELEGRAM_CREDENTIAL_KEYS:
        value = base_tg.get(key)
        if value in (None, "", [], {}):
            continue
        if merged_tg.get(key) == value:
            continue
        merged_tg[key] = value
        preserved.append(f"channels.telegram.{key}")
    return preserved


def apply_runtime_bridge_config(merged_cfg: dict[str, Any], workflow_repo_path: str) -> dict[str, Any]:
    workflow_root = Path(workflow_repo_path).resolve()
    hooks_dir = workflow_root / "hooks"
    skills_dir = workflow_root / "skills"
    compatibility_cleanup: list[str] = []

    agents_cfg = ensure_object(merged_cfg, "agents")
    defaults_cfg = ensure_object(agents_cfg, "defaults")
    if defaults_cfg.pop("outputPolicy", None) is not None:
        compatibility_cleanup.append("agents.defaults.outputPolicy")

    env_cfg = ensure_object(ensure_object(merged_cfg, "env"), "vars")
    env_cfg["HARDFLOW_OPENCLAW_HOOKS_SOURCE_DIR"] = str(hooks_dir)
    env_cfg["HARDFLOW_OPENCLAW_SKILLS_SOURCE_DIR"] = str(skills_dir)

    hooks_cfg = ensure_object(merged_cfg, "hooks")
    internal_cfg = ensure_object(hooks_cfg, "internal")
    internal_cfg["enabled"] = True
    entries_cfg = ensure_object(internal_cfg, "entries")
    for hook_id in CORE_RUNTIME_HOOKS:
        entry = entries_cfg.get(hook_id)
        if not isinstance(entry, dict):
            entry = {}
        entry["enabled"] = True
        entries_cfg[hook_id] = entry

    bridge: dict[str, Any] = {
        "workflow_repo_path": str(workflow_root),
        "hooks": {
            "managed_by": "official-hooks-loader",
            "install_mode": "config-extraDirs",
            "source_dir": str(hooks_dir),
            "exists": hooks_dir.exists(),
            "core_entries": list(CORE_RUNTIME_HOOKS),
            "link_commands": [
                render_cmd(["openclaw", "hooks", "install", "-l", str((hooks_dir / hook_id).resolve())])
                for hook_id in CORE_RUNTIME_HOOKS
                if (hooks_dir / hook_id).exists()
            ],
        },
        "skills": {
            "managed_by": "official-skills-loader",
            "install_mode": "config-extraDirs",
            "source_dir": str(skills_dir),
            "exists": skills_dir.exists(),
        },
        "channels": {
            "managed_by": "official-channel-surface",
            "config_keys": ["channels.telegram"],
        },
        "plugins": {
            "managed_by": "official-plugin-surface",
            "config_keys": ["plugins.entries.telegram"],
        },
    }
    if compatibility_cleanup:
        bridge["compatibility_cleanup"] = list(compatibility_cleanup)

    if hooks_dir.exists():
        load_cfg = ensure_object(internal_cfg, "load")
        extra_dirs = normalize_string_list(load_cfg.get("extraDirs"))
        hooks_dir_text = str(hooks_dir)
        if hooks_dir_text not in extra_dirs:
            extra_dirs.append(hooks_dir_text)
        load_cfg["extraDirs"] = extra_dirs
        bridge["hooks"]["extra_dirs"] = list(extra_dirs)

    if skills_dir.exists():
        skills_cfg = ensure_object(merged_cfg, "skills")
        load_cfg = ensure_object(skills_cfg, "load")
        load_cfg.setdefault("watch", True)
        load_cfg.setdefault("watchDebounceMs", 1200)
        extra_dirs = normalize_string_list(load_cfg.get("extraDirs"))
        skills_dir_text = str(skills_dir)
        if skills_dir_text not in extra_dirs:
            extra_dirs.append(skills_dir_text)
        load_cfg["extraDirs"] = extra_dirs
        bridge["skills"]["extra_dirs"] = list(extra_dirs)

    return bridge


def sync_overlay_config(
    *,
    source_path: str,
    target_path: str,
    vendor_runtime_root: str,
    boundary_doc_path: str,
    workflow_repo_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    source = Path(source_path)
    target = Path(target_path)
    result: dict[str, Any] = {
        "ok": False,
        "step": OVERLAY_SYNC_STEP,
        "dry_run": dry_run,
        "merge_mode": "repo-overlay-wins-with-local-telegram-credentials",
        "source_role": "workflow-overlay",
        "source": str(source),
        "target": str(target),
        "vendor_runtime_root": str(vendor_runtime_root),
        "boundary_doc": str(boundary_doc_path),
        "workflow_repo_path": str(Path(workflow_repo_path).resolve()),
        "target_exists": target.exists(),
        "changed": False,
        "backup": "",
        "written": False,
    }
    if not source.exists():
        result["error"] = f"overlay_config_missing:{source}"
        return result
    try:
        source_cfg = load_json_object(source)
    except Exception as exc:
        result["error"] = f"overlay_config_invalid:{source}:{exc}"
        return result

    target_cfg: dict[str, Any] = {}
    if target.exists():
        try:
            target_cfg = load_json_object(target)
        except Exception as exc:
            result["error"] = f"target_config_invalid:{target}:{exc}"
            return result

    merged_cfg = merge_overlay_object(target_cfg, source_cfg)
    preserved_local_keys = preserve_local_telegram_credentials(target_cfg, merged_cfg)
    if preserved_local_keys:
        result["preserved_local_config_keys"] = preserved_local_keys
    result["runtime_bridge"] = apply_runtime_bridge_config(merged_cfg, workflow_repo_path=workflow_repo_path)
    changed = (not target.exists()) or (merged_cfg != target_cfg)
    result["changed"] = changed
    if (not changed) or dry_run:
        result["ok"] = True
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup_path = target.with_name(f"{target.name}.bak.overlay.{now_stamp_utc()}")
        shutil.copy2(target, backup_path)
        result["backup"] = str(backup_path)
    write_json_object(target, merged_cfg)
    result["written"] = True
    result["ok"] = True
    return result


def detect_platform_name() -> str:
    raw = platform.system().strip().lower()
    if raw.startswith("linux"):
        return "linux"
    if raw.startswith("darwin"):
        return "macos"
    if raw.startswith("windows"):
        return "windows"
    return raw or "unknown"


def build_cron_setup_cmd(
    *,
    python_bin: str,
    script_path: str,
    jobs_file: str,
    ops_home: str,
    openclaw_home: str,
    workflow_repo_path: str,
    workflow_repo_id: str,
    project_registry: str,
    task_db: str,
    incremental_every_ms: int,
    full_expr: str,
    daily_summary_expr: str,
    daily_work_expr: str,
    self_evolution_expr: str,
    self_evolution_low_score_guarantee_enabled: bool,
    self_evolution_low_score_guarantee_min_agents: int,
    self_evolution_low_score_guarantee_max_agents: int,
    self_evolution_low_score_guarantee_threshold: float,
    conversation_every_ms: int,
    governance_every_ms: int,
    git_sync_every_ms: int,
    auto_update_install_every_ms: int,
    github_web_every_ms: int,
    include_github_web: bool,
    channel: str,
    target: str,
) -> list[str]:
    cmd = [
        python_bin,
        script_path,
        "--jobs-file",
        jobs_file,
        "--install-profile",
        "legacy",
        "--legacy-optimize-jobs-mode",
        "disable",
        "--daily-report-dedupe-mode",
        "disable-digest",
        "--runner-py",
        str(Path(ops_home) / "ops_cron_runner.py"),
        "--config-file",
        str(Path(ops_home) / "cron-monitor-config.json"),
        "--state-file",
        str(Path(ops_home) / "cron-monitor-state.json"),
        "--history-dir",
        str(Path(ops_home) / "cron-runs"),
        "--incremental-every-ms",
        str(max(600000, int(incremental_every_ms))),
        "--full-expr",
        full_expr,
        "--daily-expr",
        daily_summary_expr,
        "--tz",
        "Asia/Shanghai",
        "--incremental-log-mode",
        "silent",
        "--full-log-mode",
        "silent",
        "--daily-log-mode",
        "silent",
        "--install-system-schedule-job",
        "--system-log-mode",
        "silent",
        "--install-daily-work-job",
        "--daily-work-py",
        str(Path(ops_home) / "daily_work_report.py"),
        "--daily-work-db",
        task_db,
        "--daily-work-state",
        str(Path(ops_home) / "daily-work/state.json"),
        "--daily-work-report-dir",
        str(Path(ops_home) / "daily-work/reports"),
        "--daily-work-expr",
        daily_work_expr,
        "--daily-work-log-mode",
        "silent",
        "--dingtalk-webhook-env",
        "DINGTALK_WEBHOOK_URL",
        "--dingtalk-secret-env",
        "DINGTALK_SECRET",
        "--daily-work-env-file",
        str(Path(ops_home) / "runtime.env"),
        "--daily-work-todo-file",
        str(Path(workflow_repo_path) / "todo.md"),
        "--daily-work-todo-file",
        str(Path(workflow_repo_path) / "TODO.md"),
        "--install-self-evolution-job",
        "--self-evolution-py",
        str(Path(ops_home) / "self_evolution_todo.py"),
        "--self-evolution-db",
        task_db,
        "--self-evolution-state",
        str(Path(ops_home) / "self-evolution/state.json"),
        "--self-evolution-report-dir",
        str(Path(ops_home) / "self-evolution/reports"),
        "--self-evolution-expr",
        self_evolution_expr,
        "--self-evolution-log-mode",
        "silent",
        "--self-evolution-lookback-days",
        "30",
        "--self-evolution-min-interval-days",
        "7",
        "--self-evolution-max-tasks-per-run",
        "3",
        "--self-evolution-agent-score-threshold",
        "70",
        "--self-evolution-agent-score-min-reports",
        "3",
        "--self-evolution-agent-score-top-n",
        "12",
        (
            "--self-evolution-low-score-guarantee-enabled"
            if bool(self_evolution_low_score_guarantee_enabled)
            else "--no-self-evolution-low-score-guarantee-enabled"
        ),
        "--self-evolution-low-score-guarantee-min-agents",
        str(max(1, int(self_evolution_low_score_guarantee_min_agents))),
        "--self-evolution-low-score-guarantee-max-agents",
        str(max(1, int(self_evolution_low_score_guarantee_max_agents))),
        "--self-evolution-low-score-guarantee-threshold",
        str(max(1.0, min(float(self_evolution_low_score_guarantee_threshold), 100.0))),
        "--install-governance-evolution-job",
        "--governance-evolution-py",
        str(Path(ops_home) / "governance_evolution_runner.py"),
        "--governance-evolution-db",
        task_db,
        "--governance-evolution-state",
        str(Path(ops_home) / "governance-evolution/state.json"),
        "--governance-evolution-report-dir",
        str(Path(ops_home) / "governance-evolution/reports"),
        "--governance-evolution-openclaw-config",
        str(Path(openclaw_home) / "openclaw.json"),
        "--governance-evolution-project-registry",
        project_registry,
        "--governance-evolution-repo-path",
        workflow_repo_path,
        "--governance-evolution-repo-id",
        workflow_repo_id,
        "--governance-evolution-auto-git-update",
        "--governance-evolution-git-update-strategy",
        "fetch",
        "--governance-evolution-git-fetch-timeout",
        "120",
        "--governance-evolution-every-ms",
        str(max(600000, int(governance_every_ms))),
        "--governance-evolution-log-mode",
        "silent",
        "--governance-evolution-task-clarity",
        "ambiguous",
        "--governance-evolution-project-context-gate",
        "--governance-evolution-project-context-assignee",
        "project-agent",
        "--governance-evolution-create-review-task",
        "--no-governance-evolution-auto-pr",
        "--install-git-sync-job",
        "--git-sync-py",
        str(Path(ops_home) / "git_sync_push_runner.py"),
        "--git-sync-repo-path",
        workflow_repo_path,
        "--git-sync-every-ms",
        str(max(600000, int(git_sync_every_ms))),
        "--git-sync-log-mode",
        "silent",
        "--git-sync-notify-on",
        "error",
        "--git-sync-remote",
        "origin",
        "--git-sync-auto-pull",
        "--git-sync-push",
        "--git-sync-include-prefix",
        ".workflow/",
        "--git-sync-include-prefix",
        "scripts/openclaw-ops/",
        "--git-sync-include-prefix",
        "cron/",
        "--git-sync-include-prefix",
        "skills/",
        "--git-sync-exclude-prefix",
        ".workflow/experience/",
        "--git-sync-exclude-prefix",
        ".workflow/sessions/",
        "--git-sync-exclude-prefix",
        "openclaw-memory/",
        "--git-sync-exclude-prefix",
        "memory/",
        "--git-sync-exclude-prefix",
        "MEMORY.md",
        "--git-sync-require-remote-url",
        "github.com/XX-Trader/openclaw-hardflow-backup-20260302",
        "--install-auto-update-install-job",
        "--auto-update-install-py",
        str(Path(ops_home) / "auto_update_install_runner.py"),
        "--auto-update-install-repo-path",
        workflow_repo_path,
        "--auto-update-install-every-ms",
        str(max(600000, int(auto_update_install_every_ms))),
        "--auto-update-install-log-mode",
        "silent",
        "--auto-update-install-notify-on",
        "error",
        "--auto-update-install-remote",
        "origin",
        "--auto-update-install-report-dir",
        str(Path(ops_home) / "update-install-runs"),
        "--auto-update-install-install-cmd",
        (
            "python3 $HOME/.openclaw/ops/install_workflow_profile.py "
            "--profile core "
            "--openclaw-home $HOME/.openclaw "
            "--workflow-repo-path ${OPENCLAW_WORKFLOW_REPO:-$HOME/openclaw-hardflow-backup-20260302} "
            "--emit-json"
        ),
        "--auto-update-install-require-remote-url",
        "https://github.com/XX-Trader/openclaw-hardflow-backup-20260302",
        "--auto-update-install-require-remote-url",
        "https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git",
    ]
    if include_github_web:
        cmd.extend(
            [
                "--install-github-web-evolution-job",
                "--github-web-evolution-py",
                str(Path(ops_home) / "github_web_evolution_runner.py"),
                "--github-web-evolution-db",
                task_db,
                "--github-web-evolution-openclaw-home",
                openclaw_home,
                "--github-web-evolution-web-root",
                str(Path(openclaw_home) / "web/github"),
                "--github-web-evolution-state",
                str(Path(ops_home) / "github-web-evolution/state.json"),
                "--github-web-evolution-report-dir",
                str(Path(ops_home) / "github-web-evolution/reports"),
                "--github-web-evolution-every-ms",
                str(max(600000, int(github_web_every_ms))),
                "--github-web-evolution-log-mode",
                "silent",
                "--github-web-evolution-min-interval-minutes",
                "360",
                "--github-web-evolution-max-queries",
                "5",
                "--github-web-evolution-max-repos-per-query",
                "20",
                "--github-web-evolution-max-total-repos",
                "40",
                "--github-web-evolution-min-stars",
                "80",
                "--github-web-evolution-min-quality-score",
                "45",
                "--github-web-evolution-min-new-or-updated",
                "2",
                "--github-web-evolution-recent-dedupe-days",
                "14",
                "--github-web-evolution-max-tasks-per-run",
                "2",
                "--github-web-evolution-schedule-gap-minutes",
                "90",
                "--github-web-evolution-assignee",
                "optimization-agent",
                "--github-web-evolution-github-token-env",
                "GITHUB_TOKEN",
            ]
        )
    cmd.extend(delivery_args(channel, target))
    return cmd


def main() -> None:
    here = Path(__file__).resolve().parent
    home = Path(os.path.expanduser("~")).resolve()
    platform_name = detect_platform_name()
    detected_openclaw_home = str((home / ".openclaw").resolve())
    detected_claude_home = str(Path(os.environ.get("CLAUDE_HOME", str(home / ".claude"))).expanduser().resolve())

    parser = argparse.ArgumentParser(description="Install workflow cron jobs by profile")
    parser.add_argument("--profile", default="core", choices=sorted(PROFILES))
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--openclaw-home", default=detected_openclaw_home)
    parser.add_argument("--workflow-repo-path", default=str((home / "openclaw-hardflow-backup-20260302").resolve()))
    parser.add_argument("--overlay-config-source", default="")
    parser.add_argument("--sync-overlay-config", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ensure-runtime-skills", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--required-skills-manifest", default="")
    parser.add_argument("--workflow-repo-id", default="")
    parser.add_argument("--project-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--todo-every-ms", type=int, default=900000)
    parser.add_argument("--todo-output-mode", default="summary", choices=["summary", "verbose", "silent"])
    parser.add_argument("--task-executor-every-ms", type=int, default=600000)
    parser.add_argument("--task-executor-max-tasks", type=int, default=3)
    parser.add_argument("--task-executor-model", default="auto")
    parser.add_argument("--task-executor-local-agent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project-index-every-ms", type=int, default=1800000)
    parser.add_argument("--local-backup-every-ms", type=int, default=3600000)
    parser.add_argument(
        "--local-backup-notify-on",
        default="errors-only",
        choices=["errors-only", "on-change", "always"],
    )
    parser.add_argument("--incremental-every-ms", type=int, default=900000)
    parser.add_argument("--full-expr", default="23 */6 * * *")
    parser.add_argument("--daily-summary-expr", default="5 0 * * *")
    parser.add_argument("--daily-work-expr", default="15 0 * * *")
    parser.add_argument("--self-evolution-expr", default="30 3 * * 1")
    parser.add_argument("--self-evolution-low-score-guarantee-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--self-evolution-low-score-guarantee-min-agents", type=int, default=2)
    parser.add_argument("--self-evolution-low-score-guarantee-max-agents", type=int, default=6)
    parser.add_argument("--self-evolution-low-score-guarantee-threshold", type=float, default=70.0)
    parser.add_argument("--conversation-every-ms", type=int, default=21600000)
    parser.add_argument("--governance-every-ms", type=int, default=21600000)
    parser.add_argument("--git-sync-every-ms", type=int, default=21600000)
    parser.add_argument("--auto-update-install-every-ms", type=int, default=3600000)
    parser.add_argument("--github-web-every-ms", type=int, default=43200000)
    parser.add_argument("--web-intel-collect-every-ms", type=int, default=3600000)
    parser.add_argument("--web-intel-opt-review-every-ms", type=int, default=14400000)
    parser.add_argument("--web-intel-project-review-every-ms", type=int, default=21600000)
    parser.add_argument("--web-intel-collect-min-interval-minutes", type=int, default=60)
    parser.add_argument("--web-intel-review-min-interval-minutes", type=int, default=180)
    parser.add_argument("--install-web-intel-jobs", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--reviewer-daily-expr", default="0 4 * * *")
    parser.add_argument("--reviewer-weekly-expr", default="40 4 * * 1")
    parser.add_argument("--normalize-openclaw-paths", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--recover-stale-cron-running-state", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--stale-running-minutes", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    profile = str(args.profile).strip().lower()
    if profile not in PROFILES:
        raise SystemExit(f"unsupported profile: {args.profile}")

    jobs_file = normalize_path(args.jobs_file)
    openclaw_home = normalize_path(args.openclaw_home)
    workflow_repo_path = normalize_path(args.workflow_repo_path)
    overlay_config_source = normalize_path(args.overlay_config_source) if str(args.overlay_config_source).strip() else str(
        (Path(workflow_repo_path) / "openclaw" / "openclaw.json").resolve()
    )
    project_registry = normalize_path(args.project_registry)
    task_db = normalize_path(args.task_db)
    ops_home = str(Path(openclaw_home) / "ops")
    workflow_repo_id = str(args.workflow_repo_id).strip() or Path(workflow_repo_path).name
    local_config_path = str((Path(openclaw_home) / "openclaw.json").resolve())
    vendor_runtime_root = str((Path(workflow_repo_path) / "vendor" / "openclaw-official").resolve())
    runtime_boundary_doc = str((Path(workflow_repo_path) / "integration" / "openclaw-bridge" / "runtime-boundary.md").resolve())
    hooks_source_dir = str((Path(workflow_repo_path) / "hooks").resolve())
    skills_source_dir = str((Path(workflow_repo_path) / "skills").resolve())
    plugin_overrides_source_dir = str((here / "runtime-plugin-overrides").resolve())
    required_skills_manifest = normalize_path(args.required_skills_manifest) if str(args.required_skills_manifest).strip() else str(
        (here / "runtime-required-skills.json").resolve()
    )

    install_todo_cmd = [
        args.python_bin,
        str(here / "install_todo_patrol_job.py"),
        "--jobs-file",
        jobs_file,
        "--ops-script",
        str(Path(ops_home) / "todo_patrol.py"),
        "--every-ms",
        str(max(600000, int(args.todo_every_ms))),
        "--output-mode",
        str(args.todo_output_mode),
    ]
    install_todo_cmd.extend(delivery_args(args.channel, args.to))

    install_task_executor_cmd = build_install_task_executor_cmd(
        python_bin=args.python_bin,
        here=here,
        jobs_file=jobs_file,
        ops_home=ops_home,
        task_db=task_db,
        every_ms=int(args.task_executor_every_ms),
        max_tasks=int(args.task_executor_max_tasks),
        model=str(args.task_executor_model),
        local_agent=bool(args.task_executor_local_agent),
        channel=str(args.channel),
        target=str(args.to),
    )

    install_index_cmd = build_install_project_index_cmd(
        python_bin=args.python_bin,
        here=here,
        jobs_file=jobs_file,
        ops_home=ops_home,
        project_registry=project_registry,
        task_db=task_db,
        every_ms=int(args.project_index_every_ms),
        channel=str(args.channel),
        target=str(args.to),
    )

    cron_setup_cmd = build_cron_setup_cmd(
        python_bin=args.python_bin,
        script_path=str(here / "cron_setup.py"),
        jobs_file=jobs_file,
        ops_home=ops_home,
        openclaw_home=openclaw_home,
        workflow_repo_path=workflow_repo_path,
        workflow_repo_id=workflow_repo_id,
        project_registry=project_registry,
        task_db=task_db,
        incremental_every_ms=int(args.incremental_every_ms),
        full_expr=str(args.full_expr),
        daily_summary_expr=str(args.daily_summary_expr),
        daily_work_expr=str(args.daily_work_expr),
        self_evolution_expr=str(args.self_evolution_expr),
        self_evolution_low_score_guarantee_enabled=bool(args.self_evolution_low_score_guarantee_enabled),
        self_evolution_low_score_guarantee_min_agents=max(1, int(args.self_evolution_low_score_guarantee_min_agents)),
        self_evolution_low_score_guarantee_max_agents=max(1, int(args.self_evolution_low_score_guarantee_max_agents)),
        self_evolution_low_score_guarantee_threshold=float(args.self_evolution_low_score_guarantee_threshold),
        conversation_every_ms=int(args.conversation_every_ms),
        governance_every_ms=int(args.governance_every_ms),
        git_sync_every_ms=int(args.git_sync_every_ms),
        auto_update_install_every_ms=int(args.auto_update_install_every_ms),
        github_web_every_ms=int(args.github_web_every_ms),
        include_github_web=(profile == "all"),
        channel=str(args.channel),
        target=str(args.to),
    )
    cron_setup_cmd.append("--emit-json")

    install_local_backup_cmd = [
        args.python_bin,
        str(here / "install_local_openclaw_backup_job.py"),
        "--jobs-file",
        jobs_file,
        "--runner-py",
        str(Path(ops_home) / "local_git_backup_runner.py"),
        "--openclaw-home",
        openclaw_home,
        "--every-ms",
        str(max(600000, int(args.local_backup_every_ms))),
        "--notify-on",
        str(args.local_backup_notify_on),
    ]
    install_local_backup_cmd.extend(delivery_args(args.channel, args.to))

    install_reviewer_cmd = [
        args.python_bin,
        str(here / "install_reviewer_scan_jobs.py"),
        "--jobs-file",
        jobs_file,
        "--runner-py",
        str(Path(ops_home) / "reviewer_cron_runner.py"),
        "--workspace",
        str(Path(openclaw_home) / "workspace"),
        "--state-file",
        str(Path(ops_home) / "reviewer-scan-state.json"),
        "--history-dir",
        str(Path(ops_home) / "reviewer-scan-runs"),
        "--reviewer-profile",
        "techdebt",
        "--daily-expr",
        str(args.reviewer_daily_expr),
        "--weekly-expr",
        str(args.reviewer_weekly_expr),
        "--no-enable-hourly",
        "--enable-daily",
        "--no-enable-bi-daily",
        "--enable-weekly",
        "--normal-log-mode",
        "silent",
        "--daily-fix-command",
        f"{args.python_bin} {Path(ops_home) / 'policy' / 'policy_enforcer.py'} next-todo --limit 5",
    ]
    install_reviewer_cmd.extend(delivery_args(args.channel, args.to))
    install_reviewer_cmd.append("--emit-json")

    install_web_intel_cmd = build_install_web_intel_cmd(
        python_bin=args.python_bin,
        here=here,
        jobs_file=jobs_file,
        ops_home=ops_home,
        openclaw_home=openclaw_home,
        project_registry=project_registry,
        collect_every_ms=int(args.web_intel_collect_every_ms),
        opt_review_every_ms=int(args.web_intel_opt_review_every_ms),
        project_review_every_ms=int(args.web_intel_project_review_every_ms),
        collect_min_interval_minutes=int(args.web_intel_collect_min_interval_minutes),
        review_min_interval_minutes=int(args.web_intel_review_min_interval_minutes),
        channel=str(args.channel),
        target=str(args.to),
    )

    normalize_paths_cmd = [
        args.python_bin,
        str(here / "normalize_openclaw_home_paths.py"),
        "--config",
        str(Path(openclaw_home) / "openclaw.json"),
        "--openclaw-home",
        openclaw_home,
        "--claude-home",
        detected_claude_home,
        "--allow-missing",
    ]
    if bool(args.dry_run):
        normalize_paths_cmd.append("--dry-run")

    ensure_runtime_skills_cmd = build_ensure_runtime_skills_cmd(
        python_bin=args.python_bin,
        here=here,
        openclaw_home=openclaw_home,
        manifest_path=required_skills_manifest,
        dry_run=bool(args.dry_run),
    )
    sync_runtime_plugin_overrides_cmd = build_sync_runtime_plugin_overrides_cmd(
        python_bin=args.python_bin,
        here=here,
        openclaw_home=openclaw_home,
        dry_run=bool(args.dry_run),
    )
    normalize_runtime_binding_tasks_cmd = build_normalize_runtime_binding_tasks_cmd(
        python_bin=args.python_bin,
        here=here,
        task_db=task_db,
        dry_run=bool(args.dry_run),
    )
    recover_stale_cron_running_state_cmd = build_recover_stale_cron_running_state_cmd(
        python_bin=args.python_bin,
        here=here,
        jobs_file=jobs_file,
        stale_minutes=max(1, int(args.stale_running_minutes)),
        dry_run=bool(args.dry_run),
    )

    steps: list[tuple[str, list[str]]] = []
    if bool(args.normalize_openclaw_paths):
        steps.append(("normalize_openclaw_home_paths (linux compatibility)", normalize_paths_cmd))
    if bool(args.ensure_runtime_skills):
        steps.append(("ensure_runtime_skills (required skills and bins)", ensure_runtime_skills_cmd))
    if Path(plugin_overrides_source_dir).exists():
        steps.append(("sync_runtime_plugin_overrides (managed plugin patches)", sync_runtime_plugin_overrides_cmd))
    steps.append(("normalize_runtime_binding_tasks (legacy backlog cleanup)", normalize_runtime_binding_tasks_cmd))

    steps.extend([
        ("install_todo_patrol_job (task#1)", install_todo_cmd),
        ("install_task_executor_job (task#1.5)", install_task_executor_cmd),
        ("install_project_index_job (task#3)", install_index_cmd),
        (
            "cron_setup core bundle (task#2,#4,#5,#7,#9"
            + (",#6" if profile == "all" else "")
            + ")",
            cron_setup_cmd,
        ),
        ("install_local_openclaw_backup_job (task#3-local)", install_local_backup_cmd),
        ("install_reviewer_scan_jobs (task#8)", install_reviewer_cmd),
    ])

    install_web_intel = bool(args.install_web_intel_jobs) or (profile == "all")
    if install_web_intel:
        steps.append(("install_web_intel_jobs (task#10-web)", install_web_intel_cmd))
    if bool(args.recover_stale_cron_running_state):
        steps.append(("recover_stale_cron_running_state (stale runningAtMs cleanup)", recover_stale_cron_running_state_cmd))

    expected_tasks = list(ALL_TASKS if profile == "all" else CORE_TASKS)
    if install_web_intel and 10 not in expected_tasks:
        expected_tasks.append(10)
    print(f"profile={profile}")
    print(f"platform={platform_name}")
    print(f"home={home}")
    print("expected_tasks=" + ",".join(str(x) for x in expected_tasks))
    print(f"jobs_file={jobs_file}")
    print(f"openclaw_home={openclaw_home}")
    print(f"claude_home={detected_claude_home}")
    print(f"workflow_repo_path={workflow_repo_path}")
    print(f"workflow_repo_id={workflow_repo_id}")
    print(f"overlay_config_source={overlay_config_source}")
    print(f"local_config_path={local_config_path}")
    print(f"vendor_runtime_root={vendor_runtime_root}")
    print(f"runtime_boundary_doc={runtime_boundary_doc}")
    print(f"hooks_source_dir={hooks_source_dir}")
    print(f"skills_source_dir={skills_source_dir}")
    print(f"plugin_overrides_source_dir={plugin_overrides_source_dir}")
    print(f"required_skills_manifest={required_skills_manifest}")

    results: list[dict[str, Any]] = []
    failed = False

    if bool(args.sync_overlay_config):
        overlay_result = sync_overlay_config(
            source_path=overlay_config_source,
            target_path=local_config_path,
            vendor_runtime_root=vendor_runtime_root,
            boundary_doc_path=runtime_boundary_doc,
            workflow_repo_path=workflow_repo_path,
            dry_run=bool(args.dry_run),
        )
        print(f"\n== {OVERLAY_SYNC_STEP} ==")
        print(json.dumps(overlay_result, ensure_ascii=False, indent=2))
        results.append(overlay_result)
        if not overlay_result.get("ok", False):
            failed = True
    else:
        skipped_result = {
            "step": OVERLAY_SYNC_STEP,
            "ok": True,
            "dry_run": bool(args.dry_run),
            "skipped": True,
            "reason": "sync disabled by flag",
            "source": overlay_config_source,
            "target": local_config_path,
            "vendor_runtime_root": vendor_runtime_root,
            "boundary_doc": runtime_boundary_doc,
            "workflow_repo_path": workflow_repo_path,
        }
        print(f"\n== {OVERLAY_SYNC_STEP} ==")
        print(json.dumps(skipped_result, ensure_ascii=False, indent=2))
        results.append(skipped_result)

    if not failed:
        for step_name, step_cmd in steps:
            result = run_step(step_name, step_cmd, bool(args.dry_run))
            results.append(result)
            if not result.get("ok", False):
                failed = True
                break

    summary = {
        "profile": profile,
        "expected_tasks": expected_tasks,
        "dry_run": bool(args.dry_run),
        "ok": not failed,
        "steps_total": len(steps) + 1,
        "steps_ran": len(results),
        "runtime_boundary": {
            "vendor_runtime_root": vendor_runtime_root,
            "overlay_config_source": overlay_config_source,
            "local_config_path": local_config_path,
            "boundary_doc": runtime_boundary_doc,
            "hooks_source_dir": hooks_source_dir,
            "skills_source_dir": skills_source_dir,
            "plugin_overrides_source_dir": plugin_overrides_source_dir,
            "sync_overlay_config": bool(args.sync_overlay_config),
            "required_skills_manifest": required_skills_manifest,
            "ensure_runtime_skills": bool(args.ensure_runtime_skills),
        },
        "results": results,
    }

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "summary="
            + json.dumps(
                {
                    "profile": profile,
                    "ok": (not failed),
                    "steps_ran": len(results),
                    "steps_total": len(steps) + 1,
                    "dry_run": bool(args.dry_run),
                },
                ensure_ascii=False,
            )
        )
        if failed:
            print("hint=fix the failed step and rerun this installer")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

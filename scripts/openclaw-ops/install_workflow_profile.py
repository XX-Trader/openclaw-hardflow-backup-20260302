#!/usr/bin/env python3
"""Install OpenClaw workflow cron jobs by profile: core or all."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


PROFILES = {"core", "all"}
CORE_TASKS = [1, 2, 3, 4, 5, 7, 8, 9]
ALL_TASKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


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


def normalize_path(text: str) -> str:
    return str(Path(os.path.expanduser(text)).resolve())


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
        "--install-conversation-evolution-job",
        "--conversation-evolution-py",
        str(Path(ops_home) / "conversation_evolution_runner.py"),
        "--conversation-evolution-db",
        task_db,
        "--conversation-evolution-openclaw-home",
        openclaw_home,
        "--conversation-evolution-state",
        str(Path(ops_home) / "conversation-evolution/state.json"),
        "--conversation-evolution-report-dir",
        str(Path(ops_home) / "conversation-evolution/reports"),
        "--conversation-evolution-every-ms",
        str(max(600000, int(conversation_every_ms))),
        "--conversation-evolution-log-mode",
        "silent",
        "--conversation-evolution-assignee",
        "optimization-agent",
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
    parser.add_argument("--workflow-repo-id", default="")
    parser.add_argument("--project-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--todo-every-ms", type=int, default=900000)
    parser.add_argument("--todo-output-mode", default="summary", choices=["summary", "verbose", "silent"])
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    profile = str(args.profile).strip().lower()
    if profile not in PROFILES:
        raise SystemExit(f"unsupported profile: {args.profile}")

    jobs_file = normalize_path(args.jobs_file)
    openclaw_home = normalize_path(args.openclaw_home)
    workflow_repo_path = normalize_path(args.workflow_repo_path)
    project_registry = normalize_path(args.project_registry)
    task_db = normalize_path(args.task_db)
    ops_home = str(Path(openclaw_home) / "ops")
    workflow_repo_id = str(args.workflow_repo_id).strip() or Path(workflow_repo_path).name

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

    install_index_cmd = [
        args.python_bin,
        str(here / "install_project_index_job.py"),
        "--jobs-file",
        jobs_file,
        "--every-ms",
        str(max(600000, int(args.project_index_every_ms))),
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
    ]
    install_index_cmd.extend(delivery_args(args.channel, args.to))

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
        f"{args.python_bin} {Path(ops_home) / 'policy_enforcer.py'} next-todo --limit 5",
    ]
    install_reviewer_cmd.extend(delivery_args(args.channel, args.to))

    install_web_intel_cmd = [
        args.python_bin,
        str(here / "install_web_intel_jobs.py"),
        "--jobs-file",
        jobs_file,
        "--python-bin",
        args.python_bin,
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
        "--collect-every-ms",
        str(max(600000, int(args.web_intel_collect_every_ms))),
        "--opt-review-every-ms",
        str(max(600000, int(args.web_intel_opt_review_every_ms))),
        "--project-review-every-ms",
        str(max(600000, int(args.web_intel_project_review_every_ms))),
        "--collect-min-interval-minutes",
        str(max(1, int(args.web_intel_collect_min_interval_minutes))),
        "--review-min-interval-minutes",
        str(max(1, int(args.web_intel_review_min_interval_minutes))),
    ]
    install_web_intel_cmd.extend(delivery_args(args.channel, args.to))

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

    steps: list[tuple[str, list[str]]] = []
    if bool(args.normalize_openclaw_paths):
        steps.append(("normalize_openclaw_home_paths (linux compatibility)", normalize_paths_cmd))

    steps.extend([
        ("install_todo_patrol_job (task#1)", install_todo_cmd),
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

    results: list[dict[str, Any]] = []
    failed = False
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
        "steps_total": len(steps),
        "steps_ran": len(results),
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
                    "steps_total": len(steps),
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

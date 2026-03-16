#!/usr/bin/env python3
"""Install or update reviewer scan jobs in OpenClaw cron jobs.json."""

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

HOURLY_JOB_ID = "d3859fd5-3ea2-4ee5-ab1d-7fd526f26722"
DAILY_JOB_ID = "0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a"
BI_DAILY_JOB_ID = "a9c4a133-bf5b-4b91-8d89-ec97995f95f9"
WEEKLY_JOB_ID = "771fda88-c8ff-49dc-a4da-6f57167c1d26"
REVIEWER_PROFILES = {"legacy", "minimal", "standard", "aggressive", "techdebt"}
REVIEWER_PROFILE_BASELINE: dict[str, dict[str, int | bool]] = {
    "legacy": {
        "hourly_every_ms": 3600000,
        "enable_hourly": True,
        "enable_daily": True,
        "enable_bi_daily": True,
        "enable_weekly": True,
    },
    "minimal": {
        "hourly_every_ms": 7200000,
        "enable_hourly": True,
        "enable_daily": True,
        "enable_bi_daily": False,
        "enable_weekly": True,
    },
    "standard": {
        "hourly_every_ms": 3600000,
        "enable_hourly": True,
        "enable_daily": True,
        "enable_bi_daily": True,
        "enable_weekly": True,
    },
    "aggressive": {
        "hourly_every_ms": 1800000,
        "enable_hourly": True,
        "enable_daily": True,
        "enable_bi_daily": True,
        "enable_weekly": True,
    },
    "techdebt": {
        "hourly_every_ms": 3600000,
        "enable_hourly": False,
        "enable_daily": True,
        "enable_bi_daily": False,
        "enable_weekly": True,
    },
}
DEFAULT_FAILURE_ALERT_AFTER = 1
DEFAULT_FAILURE_ALERT_COOLDOWN_MS = 30 * 60 * 1000
DEFAULT_REVIEWER_CRON_MODEL = "glmcode/glm-5"


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs file must be JSON object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def infer_delivery(jobs: list[dict[str, Any]], preferred_agents: list[str]) -> tuple[str | None, str | None]:
    for aid in preferred_agents:
        for item in jobs:
            if str(item.get("agentId", "")).strip() != aid:
                continue
            delivery = item.get("delivery") or {}
            channel = str(delivery.get("channel", "")).strip()
            target = str(delivery.get("to", "")).strip()
            if channel and target:
                return channel, target
    return None, None


def build_delivery(channel: str, target: str, *, mode: str = "none") -> dict[str, str]:
    return {"mode": str(mode or "none").strip() or "none", "channel": channel, "to": target}


def build_failure_alert(channel: str, target: str) -> dict[str, Any]:
    return {
        "after": DEFAULT_FAILURE_ALERT_AFTER,
        "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS,
        "channel": channel,
        "to": target,
    }


def build_message(command: str) -> str:
    return build_scheduled_runner_message(
        str(command or "").strip(),
        role="reviewer scheduled runner",
        forbid_file_inspection=True,
    )


def build_official_cron_surface(job_ids: list[str]) -> dict[str, Any]:
    normalized = [str(job_id).strip() for job_id in job_ids if str(job_id).strip()]
    return {
        "surface": "official-cron",
        "status_cmd": "openclaw cron status --json",
        "run_cmds": {job_id: f"openclaw cron run {job_id} --force" for job_id in normalized},
        "runs_cmds": {job_id: f"openclaw cron runs --id {job_id} --limit 20" for job_id in normalized},
        "notes": [
            "Reviewer 扫描任务仍以 jobs.json 为业务定义源。",
            "安装后请用官方 openclaw cron surface 查看状态与手工触发。",
        ],
    }


def normalize_shell_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(raw)
    return expanded.replace("\\", "/")


def apply_reviewer_profile(args: argparse.Namespace) -> dict[str, Any]:
    profile = str(getattr(args, "reviewer_profile", "legacy") or "legacy").strip().lower()
    if profile not in REVIEWER_PROFILES:
        profile = "legacy"
    setattr(args, "reviewer_profile", profile)

    changes: dict[str, dict[str, Any]] = {}

    def set_arg(name: str, value: Any) -> None:
        old = getattr(args, name)
        if old != value:
            setattr(args, name, value)
            changes[name] = {"from": old, "to": value}

    baseline = REVIEWER_PROFILE_BASELINE.get(profile, REVIEWER_PROFILE_BASELINE["legacy"])
    min_hourly = int(baseline.get("hourly_every_ms", 3600000))
    if int(args.hourly_every_ms) < min_hourly:
        set_arg("hourly_every_ms", min_hourly)

    toggle_defaults = {
        "enable_hourly": bool(baseline.get("enable_hourly", True)),
        "enable_daily": bool(baseline.get("enable_daily", True)),
        "enable_bi_daily": bool(baseline.get("enable_bi_daily", True)),
        "enable_weekly": bool(baseline.get("enable_weekly", True)),
    }
    for key, default_value in toggle_defaults.items():
        raw = getattr(args, key)
        if raw is None:
            set_arg(key, default_value)
        else:
            set_arg(key, bool(raw))

    return {"profile": profile, "changes": changes}


def build_jobs(
    *,
    runner_py: str,
    workspace: str,
    state_file: str,
    history_dir: str,
    tz_name: str,
    hourly_every_ms: int,
    daily_expr: str,
    bi_daily_expr: str,
    weekly_expr: str,
    enable_hourly: bool,
    enable_daily: bool,
    enable_bi_daily: bool,
    enable_weekly: bool,
    normal_log_mode: str,
    daily_fix_command: str,
    hourly_git_fetch: bool,
    hourly_check_pr: bool,
    hourly_allow_merge: bool,
    hourly_push_after_merge: bool,
    hourly_merge_approval_file: str,
    hourly_pr_gate_only: bool = False,
    project_context_gate: bool,
    project_context_db: str,
    project_context_assignee: str,
) -> list[dict[str, Any]]:
    ts = now_ms()
    cmd_base = (
        f"python3 {runner_py} --workspace {workspace} "
        f"--state-file {state_file} --history-dir {history_dir} --normal-log-mode {normal_log_mode} "
        f"--project-context-db {project_context_db} --project-context-assignee {project_context_assignee}"
    )
    if project_context_gate:
        cmd_base += " --project-context-gate"
    else:
        cmd_base += " --no-project-context-gate"

    cmd_hourly = f"{cmd_base} --mode hourly_git --task-id cron:reviewer-hourly-git"
    if hourly_git_fetch:
        cmd_hourly += " --git-fetch"
    if hourly_check_pr:
        cmd_hourly += " --check-pr"
    if hourly_pr_gate_only:
        cmd_hourly += " --pr-gate-only"
    if hourly_allow_merge:
        cmd_hourly += " --allow-merge"
        if str(hourly_merge_approval_file).strip():
            cmd_hourly += f" --merge-approval-file \"{hourly_merge_approval_file}\""
        if hourly_push_after_merge:
            cmd_hourly += " --push-after-merge"

    cmd_daily = f"{cmd_base} --mode daily_incremental --task-id cron:reviewer-daily-incremental --fix"
    if str(daily_fix_command).strip():
        cmd_daily += f" --fix-command \"{daily_fix_command}\""

    cmd_bi_daily = f"{cmd_base} --mode bi_daily_recurring --task-id cron:reviewer-bi-daily-recurring"
    cmd_weekly = f"{cmd_base} --mode weekly_structure --task-id cron:reviewer-weekly-structure"

    return [
        {
            "id": HOURLY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_git_update_hourly",
            "description": (
                "Hourly PR review gate (open PR review, approval-gated merge)"
                if bool(hourly_pr_gate_only)
                else "Hourly git incremental scan (branch sync, PR check, optional approved merge)"
            ),
            "enabled": bool(enable_hourly),
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "every", "everyMs": max(600000, int(hourly_every_ms)), "anchorMs": ts},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {
                "kind": "agentTurn",
                "message": build_message(cmd_hourly),
                "model": DEFAULT_REVIEWER_CRON_MODEL,
                "lightContext": True,
                "timeoutSeconds": 1200,
            },
            "delivery": {"mode": "none"},
            "failureAlert": {"after": DEFAULT_FAILURE_ALERT_AFTER, "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS},
        },
        {
            "id": DAILY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_incremental_daily_4am",
            "description": "Daily 04:00 incremental review with optional fix command",
            "enabled": bool(enable_daily),
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": str(daily_expr), "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {
                "kind": "agentTurn",
                "message": build_message(cmd_daily),
                "model": DEFAULT_REVIEWER_CRON_MODEL,
                "lightContext": True,
                "timeoutSeconds": 1800,
            },
            "delivery": {"mode": "none"},
            "failureAlert": {"after": DEFAULT_FAILURE_ALERT_AFTER, "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS},
        },
        {
            "id": BI_DAILY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_recurring_bi_daily",
            "description": "Every 2 days recurring issue scan with dedupe",
            "enabled": bool(enable_bi_daily),
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": str(bi_daily_expr), "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {
                "kind": "agentTurn",
                "message": build_message(cmd_bi_daily),
                "model": DEFAULT_REVIEWER_CRON_MODEL,
                "lightContext": True,
                "timeoutSeconds": 1800,
            },
            "delivery": {"mode": "none"},
            "failureAlert": {"after": DEFAULT_FAILURE_ALERT_AFTER, "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS},
        },
        {
            "id": WEEKLY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_weekly_structure_review",
            "description": "Weekly structure review: coupling, duplication, config dispersion, boundary clarity",
            "enabled": bool(enable_weekly),
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": str(weekly_expr), "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {
                "kind": "agentTurn",
                "message": build_message(cmd_weekly),
                "model": DEFAULT_REVIEWER_CRON_MODEL,
                "lightContext": True,
                "timeoutSeconds": 1800,
            },
            "delivery": {"mode": "none"},
            "failureAlert": {"after": DEFAULT_FAILURE_ALERT_AFTER, "cooldownMs": DEFAULT_FAILURE_ALERT_COOLDOWN_MS},
        },
    ]


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
            status[jid] = "updated"
        else:
            item["state"] = {}
            status[jid] = "created"

        item["updatedAtMs"] = ts
        delivery = item.get("delivery") if isinstance(item.get("delivery"), dict) else {}
        item["delivery"] = build_delivery(channel, target, mode=str(delivery.get("mode", "none")))
        failure_alert = item.get("failureAlert")
        if isinstance(failure_alert, dict):
            failure_alert["channel"] = channel
            failure_alert["to"] = target
            item["failureAlert"] = failure_alert
        if item.get("schedule", {}).get("kind") == "every":
            item["state"]["nextRunAtMs"] = ts + int(item["schedule"].get("everyMs", 0))
        by_id[jid] = item

    ordered: list[dict[str, Any]] = []
    seen = set()
    for old in jobs:
        jid = str(old.get("id", ""))
        if jid in by_id:
            ordered.append(by_id[jid])
            seen.add(jid)
        else:
            ordered.append(old)

    for jid, item in by_id.items():
        if jid not in seen:
            ordered.append(item)
    return ordered, status


def main() -> None:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Install reviewer periodic scan jobs")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/reviewer_cron_runner.py"))
    parser.add_argument("--workspace", default=str(home / ".openclaw/workspace"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/reviewer-scan-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/reviewer-scan-runs"))
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--reviewer-profile", default="legacy", choices=sorted(REVIEWER_PROFILES))
    parser.add_argument("--hourly-every-ms", type=int, default=3600000)
    parser.add_argument("--daily-expr", default="0 4 * * *")
    parser.add_argument("--bi-daily-expr", default="20 4 */2 * *")
    parser.add_argument("--weekly-expr", default="40 4 * * 1")
    parser.add_argument("--enable-hourly", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--enable-daily", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--enable-bi-daily", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--enable-weekly", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--daily-fix-command", default="")

    parser.add_argument("--hourly-git-fetch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hourly-check-pr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hourly-allow-merge", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--hourly-pr-gate-only", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--hourly-push-after-merge", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--hourly-merge-approval-file", default=str(home / ".openclaw/ops/reviewer-merge-approval.json"))
    parser.add_argument("--project-context-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project-context-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--project-context-assignee", default="project-agent")

    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()
    profile_result = apply_reviewer_profile(args)

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data.get("jobs", [])

    channel = str(args.channel).strip()
    target = str(args.to).strip()
    if not channel or not target:
        inferred_channel, inferred_target = infer_delivery(jobs, ["reviewer", "ops-agent", "project-agent"])
        channel = channel or (inferred_channel or "telegram")
        target = target or (inferred_target or "")
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    if args.hourly_allow_merge and not str(args.hourly_merge_approval_file).strip():
        raise SystemExit("--hourly-allow-merge requires --hourly-merge-approval-file")

    fresh_jobs = build_jobs(
        runner_py=normalize_shell_path(args.runner_py),
        workspace=normalize_shell_path(args.workspace),
        state_file=normalize_shell_path(args.state_file),
        history_dir=normalize_shell_path(args.history_dir),
        tz_name=str(args.tz).strip() or "Asia/Shanghai",
        hourly_every_ms=max(600000, int(args.hourly_every_ms)),
        daily_expr=str(args.daily_expr).strip() or "0 4 * * *",
        bi_daily_expr=str(args.bi_daily_expr).strip() or "20 4 */2 * *",
        weekly_expr=str(args.weekly_expr).strip() or "40 4 * * 1",
        enable_hourly=bool(args.enable_hourly),
        enable_daily=bool(args.enable_daily),
        enable_bi_daily=bool(args.enable_bi_daily),
        enable_weekly=bool(args.enable_weekly),
        normal_log_mode=str(args.normal_log_mode).strip(),
        daily_fix_command=str(args.daily_fix_command),
        hourly_git_fetch=bool(args.hourly_git_fetch),
        hourly_check_pr=bool(args.hourly_check_pr),
        hourly_allow_merge=bool(args.hourly_allow_merge),
        hourly_push_after_merge=bool(args.hourly_push_after_merge),
        hourly_merge_approval_file=normalize_shell_path(args.hourly_merge_approval_file),
        hourly_pr_gate_only=bool(args.hourly_pr_gate_only),
        project_context_gate=bool(args.project_context_gate),
        project_context_db=normalize_shell_path(args.project_context_db),
        project_context_assignee=str(args.project_context_assignee).strip() or "project-agent",
    )

    backup_file = ""
    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        backup_file = str(backup)

    merged, status = upsert_jobs(jobs=jobs, fresh_jobs=fresh_jobs, channel=channel, target=target)
    data["jobs"] = merged
    write_json_atomic(
        jobs_path,
        data,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )

    job_ids = [HOURLY_JOB_ID, DAILY_JOB_ID, BI_DAILY_JOB_ID, WEEKLY_JOB_ID]
    result = {
        "ok": True,
        "backup": backup_file,
        "jobs_file": str(jobs_path),
        "runner_py": normalize_shell_path(args.runner_py),
        "workspace": normalize_shell_path(args.workspace),
        "state_file": normalize_shell_path(args.state_file),
        "history_dir": normalize_shell_path(args.history_dir),
        "delivery": {"channel": channel, "to": target},
        "reviewer_profile": profile_result.get("profile", "legacy"),
        "reviewer_profile_changes": profile_result.get("changes", {}),
        "hourly_every_ms": max(600000, int(args.hourly_every_ms)),
        "daily_expr": str(args.daily_expr).strip() or "0 4 * * *",
        "bi_daily_expr": str(args.bi_daily_expr).strip() or "20 4 */2 * *",
        "weekly_expr": str(args.weekly_expr).strip() or "40 4 * * 1",
        "enable_hourly": bool(args.enable_hourly),
        "enable_daily": bool(args.enable_daily),
        "enable_bi_daily": bool(args.enable_bi_daily),
        "enable_weekly": bool(args.enable_weekly),
        "hourly_git_fetch": bool(args.hourly_git_fetch),
        "hourly_check_pr": bool(args.hourly_check_pr),
        "hourly_allow_merge": bool(args.hourly_allow_merge),
        "hourly_merge_approval_file": normalize_shell_path(args.hourly_merge_approval_file),
        "hourly_pr_gate_only": bool(args.hourly_pr_gate_only),
        "hourly_push_after_merge": bool(args.hourly_push_after_merge),
        "project_context_gate": bool(args.project_context_gate),
        "project_context_db": normalize_shell_path(args.project_context_db),
        "project_context_assignee": str(args.project_context_assignee).strip() or "project-agent",
        "job_status": {jid: status.get(jid, "unknown") for jid in job_ids},
        "official_cron_surface": build_official_cron_surface(job_ids),
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    if backup_file:
        print(f"backup={backup_file}")
    print(f"jobs_file={jobs_path}")
    print(f"runner_py={normalize_shell_path(args.runner_py)}")
    print(f"workspace={normalize_shell_path(args.workspace)}")
    print(f"state_file={normalize_shell_path(args.state_file)}")
    print(f"history_dir={normalize_shell_path(args.history_dir)}")
    print(f"delivery={channel}:{target}")
    print(f"reviewer_profile={profile_result.get('profile', 'legacy')}")
    if profile_result.get("changes"):
        print("reviewer_profile_changes=" + json.dumps(profile_result.get("changes", {}), ensure_ascii=False))
    print(f"hourly_every_ms={max(600000, int(args.hourly_every_ms))}")
    print(f"daily_expr={str(args.daily_expr).strip() or '0 4 * * *'}")
    print(f"bi_daily_expr={str(args.bi_daily_expr).strip() or '20 4 */2 * *'}")
    print(f"weekly_expr={str(args.weekly_expr).strip() or '40 4 * * 1'}")
    print(f"enable_hourly={bool(args.enable_hourly)}")
    print(f"enable_daily={bool(args.enable_daily)}")
    print(f"enable_bi_daily={bool(args.enable_bi_daily)}")
    print(f"enable_weekly={bool(args.enable_weekly)}")
    print(f"hourly_git_fetch={bool(args.hourly_git_fetch)}")
    print(f"hourly_check_pr={bool(args.hourly_check_pr)}")
    print(f"hourly_allow_merge={bool(args.hourly_allow_merge)}")
    print(f"hourly_merge_approval_file={normalize_shell_path(args.hourly_merge_approval_file)}")
    print(f"hourly_pr_gate_only={bool(args.hourly_pr_gate_only)}")
    print(f"hourly_push_after_merge={bool(args.hourly_push_after_merge)}")
    print(f"project_context_gate={bool(args.project_context_gate)}")
    print(f"project_context_db={normalize_shell_path(args.project_context_db)}")
    print(f"project_context_assignee={str(args.project_context_assignee).strip() or 'project-agent'}")
    print("cron_surface=official-cron")
    print(f"cron_status_cmd={result['official_cron_surface']['status_cmd']}")
    for jid in job_ids:
        print(f"{jid}={status.get(jid, 'unknown')}")
        print(f"cron_run_cmd[{jid}]={result['official_cron_surface']['run_cmds'][jid]}")
        print(f"cron_runs_cmd[{jid}]={result['official_cron_surface']['runs_cmds'][jid]}")


if __name__ == "__main__":
    main()

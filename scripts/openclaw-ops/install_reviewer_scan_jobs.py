#!/usr/bin/env python3
"""Install or update reviewer scan jobs in OpenClaw cron jobs.json."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOURLY_JOB_ID = "d3859fd5-3ea2-4ee5-ab1d-7fd526f26722"
DAILY_JOB_ID = "0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a"
BI_DAILY_JOB_ID = "a9c4a133-bf5b-4b91-8d89-ec97995f95f9"
WEEKLY_JOB_ID = "771fda88-c8ff-49dc-a4da-6f57167c1d26"


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


def build_message(command: str) -> str:
    return (
        "You are reviewer scheduled runner. Run command only:\n"
        f"{command}\n"
        "Return EXACTLY raw stdout/stderr text from the command; "
        "do not add explanation, greeting, or prefix text. "
        "If output is NO_REPLY, reply NO_REPLY."
    )


def build_jobs(
    *,
    runner_py: str,
    workspace: str,
    state_file: str,
    history_dir: str,
    tz_name: str,
    normal_log_mode: str,
    daily_fix_command: str,
    hourly_git_fetch: bool,
    hourly_check_pr: bool,
    hourly_allow_merge: bool,
    hourly_push_after_merge: bool,
    hourly_merge_approval_file: str,
) -> list[dict[str, Any]]:
    ts = now_ms()
    cmd_base = (
        f"python3 {runner_py} --workspace {workspace} "
        f"--state-file {state_file} --history-dir {history_dir} --normal-log-mode {normal_log_mode}"
    )

    cmd_hourly = f"{cmd_base} --mode hourly_git --task-id cron:reviewer-hourly-git"
    if hourly_git_fetch:
        cmd_hourly += " --git-fetch"
    if hourly_check_pr:
        cmd_hourly += " --check-pr"
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
            "description": "Hourly git incremental scan (branch sync, PR check, optional approved merge)",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "every", "everyMs": 3600000, "anchorMs": ts},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_hourly), "timeoutSeconds": 1200},
        },
        {
            "id": DAILY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_incremental_daily_4am",
            "description": "Daily 04:00 incremental review with optional fix command",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": "0 4 * * *", "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_daily), "timeoutSeconds": 1800},
        },
        {
            "id": BI_DAILY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_recurring_bi_daily",
            "description": "Every 2 days recurring issue scan with dedupe",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": "20 4 */2 * *", "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_bi_daily), "timeoutSeconds": 1800},
        },
        {
            "id": WEEKLY_JOB_ID,
            "agentId": "reviewer",
            "name": "reviewer_weekly_structure_review",
            "description": "Weekly structure review: coupling, duplication, config dispersion, boundary clarity",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": "40 4 * * 1", "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_weekly), "timeoutSeconds": 1800},
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
        item["delivery"] = {"mode": "announce", "channel": channel, "to": target}
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
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--daily-fix-command", default="")

    parser.add_argument("--hourly-git-fetch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hourly-check-pr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hourly-allow-merge", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--hourly-push-after-merge", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--hourly-merge-approval-file", default=str(home / ".openclaw/ops/reviewer-merge-approval.json"))

    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    args = parser.parse_args()

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
        runner_py=str(Path(args.runner_py).expanduser()),
        workspace=str(Path(args.workspace).expanduser()),
        state_file=str(Path(args.state_file).expanduser()),
        history_dir=str(Path(args.history_dir).expanduser()),
        tz_name=str(args.tz).strip() or "Asia/Shanghai",
        normal_log_mode=str(args.normal_log_mode).strip(),
        daily_fix_command=str(args.daily_fix_command),
        hourly_git_fetch=bool(args.hourly_git_fetch),
        hourly_check_pr=bool(args.hourly_check_pr),
        hourly_allow_merge=bool(args.hourly_allow_merge),
        hourly_push_after_merge=bool(args.hourly_push_after_merge),
        hourly_merge_approval_file=str(Path(args.hourly_merge_approval_file).expanduser()),
    )

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    merged, status = upsert_jobs(jobs=jobs, fresh_jobs=fresh_jobs, channel=channel, target=target)
    data["jobs"] = merged
    jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"jobs_file={jobs_path}")
    print(f"runner_py={args.runner_py}")
    print(f"workspace={args.workspace}")
    print(f"state_file={args.state_file}")
    print(f"history_dir={args.history_dir}")
    print(f"delivery={channel}:{target}")
    print(f"hourly_git_fetch={bool(args.hourly_git_fetch)}")
    print(f"hourly_check_pr={bool(args.hourly_check_pr)}")
    print(f"hourly_allow_merge={bool(args.hourly_allow_merge)}")
    print(f"hourly_merge_approval_file={Path(args.hourly_merge_approval_file).expanduser()}")
    print(f"hourly_push_after_merge={bool(args.hourly_push_after_merge)}")
    for jid in [HOURLY_JOB_ID, DAILY_JOB_ID, BI_DAILY_JOB_ID, WEEKLY_JOB_ID]:
        print(f"{jid}={status.get(jid, 'unknown')}")


if __name__ == "__main__":
    main()

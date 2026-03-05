#!/usr/bin/env python3
"""Install local ~/.openclaw git backup job (commit-only, no remote push)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def infer_delivery(jobs: list[dict[str, Any]], preferred_agents: list[str]) -> tuple[str, str]:
    for aid in preferred_agents:
        for item in jobs:
            if item.get("agentId") != aid:
                continue
            delivery = item.get("delivery") or {}
            channel = str(delivery.get("channel", "")).strip()
            target = str(delivery.get("to", "")).strip()
            if channel and target:
                return channel, target
    return "telegram", ""


def upsert_job(
    jobs: list[dict[str, Any]],
    *,
    job_id: str,
    every_ms: int,
    runner_py: str,
    openclaw_home: str,
    task_id: str,
    channel: str,
    target: str,
) -> tuple[list[dict[str, Any]], bool]:
    ts = now_ms()
    existed = False
    created_at = ts
    old_state: dict[str, Any] = {}

    for item in jobs:
        if item.get("id") != job_id:
            continue
        existed = True
        created_at = int(item.get("createdAtMs", ts))
        old_state = item.get("state") if isinstance(item.get("state"), dict) else {}
        break

    cmd = (
        f"python3 \"{runner_py}\" "
        f"--repo-path \"{openclaw_home}\" "
        f"--task-id {task_id} "
        "--normal-log-mode silent "
        "--max-files 600 "
        "--exclude-glob \"**/.git/**\" "
        "--exclude-glob \"**/.locks/**\" "
        "--exclude-glob \"ops/.locks/**\" "
        "--exclude-glob \"**/__pycache__/**\" "
        "--exclude-glob \"*.pyc\" "
        "--exclude-glob \"**/*.pyc\" "
        "--exclude-glob \"ops/cron-backup/**\" "
        "--exclude-glob \"ops/*-runs/**\" "
        "--exclude-glob \"ops/*-reports/**\" "
        "--exclude-glob \"ops/*/reports/**\" "
        "--exclude-glob \"ops/task-center/**/*.db*\" "
        "--exclude-glob \"ops/task-center/*.db*\" "
        "--exclude-glob \"ops/task-center/*.sqlite*\" "
        "--exclude-glob \"workspace-*/logs/**\" "
        "--exclude-glob \"workspace-*/sessions/**\" "
        "--exclude-glob \"workspace-*/downloads/**\" "
        "--exclude-glob \"workspace-*/tmp/**\" "
        "--exclude-glob \"workspace-*/.codex/**\" "
        "--exclude-glob \"agents/*/sessions/**\" "
        "--exclude-glob \"agents/*/sessions.json\" "
        "--exclude-glob \"cron/runs/**\" "
        "--exclude-glob \"cron/jobs.json.bak*\" "
        "--exclude-glob \"openclaw.json.bak*\" "
        "--exclude-glob \"browser/**\" "
        "--exclude-glob \"*.log\" "
        "--exclude-glob \"**/*.log\" "
        "--commit-prefix \"chore(local-backup): snapshot ~/.openclaw\""
    )

    payload = {
        "id": job_id,
        "agentId": "ops-agent",
        "name": "ops_local_openclaw_git_backup",
        "description": "本地 ~/.openclaw git 备份（仅本地 commit，不推远程）",
        "enabled": True,
        "createdAtMs": created_at,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": every_ms,
            "anchorMs": created_at,
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "You are ops-agent scheduled runner. Run command only:\n"
                f"{cmd}\n"
                "Return EXACTLY raw stdout/stderr text from the command; "
                "do not add explanation, greeting, or prefix text. "
                "If output is NO_REPLY, reply NO_REPLY."
            ),
            "timeoutSeconds": 1800,
        },
        "delivery": {
            "mode": "announce",
            "channel": channel,
            "to": target,
        },
        "state": old_state,
    }
    payload["state"]["nextRunAtMs"] = ts + every_ms

    out: list[dict[str, Any]] = []
    replaced = False
    for item in jobs:
        if item.get("id") == job_id:
            out.append(payload)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(payload)
    return out, existed


def main() -> None:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Install local ~/.openclaw git backup job")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--job-id", default="31f0c650-53d2-4b86-9d8b-6ad8e8f0d053")
    parser.add_argument("--every-ms", type=int, default=3600000)
    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/local_git_backup_runner.py"))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--task-id", default="cron:ops-local-openclaw-git-backup")
    parser.add_argument("--skip-path-check", action="store_true")
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    args = parser.parse_args()

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data["jobs"]

    channel = args.channel.strip()
    target = args.to.strip()
    if not channel or not target:
        inferred_channel, inferred_target = infer_delivery(jobs, ["ops-agent", "project-agent"])
        channel = channel or inferred_channel
        target = target or inferred_target
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing ops-agent/project-agent delivery")

    runner_path = Path(args.runner_py).expanduser()
    openclaw_home_path = Path(args.openclaw_home).expanduser()
    if not bool(args.skip_path_check):
        if not runner_path.exists() or not runner_path.is_file():
            raise SystemExit(f"runner script missing: {runner_path}")
        if not openclaw_home_path.exists() or (not openclaw_home_path.is_dir()):
            raise SystemExit(f"openclaw home missing: {openclaw_home_path}")

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=args.job_id,
        every_ms=int(args.every_ms),
        runner_py=str(runner_path),
        openclaw_home=str(openclaw_home_path),
        task_id=str(args.task_id or "").strip() or "cron:ops-local-openclaw-git-backup",
        channel=channel,
        target=target,
    )
    data["jobs"] = updated_jobs
    jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"job_id={args.job_id}")
    print(f"status={'updated' if existed else 'created'}")
    print(f"jobs_file={jobs_path}")
    print(f"runner_py={runner_path}")
    print(f"openclaw_home={openclaw_home_path}")
    print(f"task_id={str(args.task_id or '').strip() or 'cron:ops-local-openclaw-git-backup'}")
    print(f"delivery={channel}:{target}")


if __name__ == "__main__":
    main()

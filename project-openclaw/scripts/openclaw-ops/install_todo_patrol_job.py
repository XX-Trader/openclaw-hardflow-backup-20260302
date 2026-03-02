#!/usr/bin/env python3
"""
Install or update OpenClaw todo-patrol job in ~/.openclaw/cron/jobs.json.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_jobs(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("jobs.json must be a JSON object")
    if "jobs" not in data or not isinstance(data["jobs"], list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def infer_delivery(jobs: list[dict], agent_id: str) -> tuple[str | None, str | None]:
    for job in jobs:
        if job.get("agentId") != agent_id:
            continue
        delivery = job.get("delivery") or {}
        channel = delivery.get("channel")
        target = delivery.get("to")
        if channel and target:
            return str(channel), str(target)
    return None, None


def upsert_job(
    jobs: list[dict],
    job_id: str,
    ops_script: str,
    every_ms: int,
    channel: str,
    target: str,
) -> tuple[list[dict], bool]:
    timestamp = now_ms()
    next_run = timestamp + every_ms
    existed = False
    created_ms = timestamp
    old_state: dict = {}

    for item in jobs:
        if item.get("id") == job_id:
            existed = True
            created_ms = int(item.get("createdAtMs", timestamp))
            old_state = item.get("state") if isinstance(item.get("state"), dict) else {}
            break

    base = {
        "id": job_id,
        "agentId": "ops-agent",
        "name": "TODO 巡检（15分钟）",
        "description": (
            "15分钟周期巡检 TODO.md；去重播报；检测执行状态；"
            "仅对 UNASSIGNED 项请求 coordinator 分配；自动并入 tester 失败项"
        ),
        "enabled": True,
        "createdAtMs": created_ms,
        "updatedAtMs": timestamp,
        "schedule": {
            "kind": "every",
            "everyMs": every_ms,
            "anchorMs": created_ms,
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "你是 todo-patrol 子agent。仅用命令执行："
                f"python3 {ops_script} --task cron:todo-patrol。"
                "将命令输出原样作为唯一回复；若输出 NO_REPLY，则只回复 NO_REPLY。"
            ),
        },
        "delivery": {
            "mode": "announce",
            "channel": channel,
            "to": target,
        },
        "state": old_state,
    }
    base["state"]["nextRunAtMs"] = next_run

    updated = []
    replaced = False
    for item in jobs:
        if item.get("id") == job_id:
            updated.append(base)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(base)
    return updated, existed


def main() -> None:
    home = Path(os.path.expanduser("~"))
    default_jobs = home / ".openclaw/cron/jobs.json"
    default_ops_script = home / ".openclaw/workspace-ops-agent/ops/todo_patrol.py"

    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-file", default=str(default_jobs))
    parser.add_argument("--job-id", default="16cb8d03-beb9-4697-927d-35952353bf8e")
    parser.add_argument("--ops-script", default=str(default_ops_script))
    parser.add_argument("--every-ms", type=int, default=900000)
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--agent-id-for-delivery", default="ops-agent")
    args = parser.parse_args()

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_jobs(jobs_path)
    jobs = data.get("jobs", [])

    channel = args.channel.strip() or None
    target = args.to.strip() or None
    if not channel or not target:
        inferred_channel, inferred_target = infer_delivery(jobs, args.agent_id_for_delivery)
        channel = channel or inferred_channel
        target = target or inferred_target

    if not channel:
        channel = "telegram"
    if not target:
        raise SystemExit(
            "missing delivery target: pass --to or ensure existing ops-agent job has delivery.to"
        )

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{now_stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=args.job_id,
        ops_script=args.ops_script,
        every_ms=args.every_ms,
        channel=channel,
        target=target,
    )
    data["jobs"] = updated_jobs
    jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"job_id={args.job_id}")
    print(f"status={'updated' if existed else 'created'}")
    print(f"jobs_file={jobs_path}")
    print(f"ops_script={args.ops_script}")
    print(f"delivery={channel}:{target}")


if __name__ == "__main__":
    main()


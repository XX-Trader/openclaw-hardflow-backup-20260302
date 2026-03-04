#!/usr/bin/env python3
"""Install or update project-index-maintainer job in OpenClaw cron jobs.json."""

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
    job_id: str,
    every_ms: int,
    maintainer_py: str,
    registry: str,
    task_db: str,
    task_id: str,
    actor: str,
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

    payload = {
        "id": job_id,
        "agentId": "project-agent",
        "name": "project_index_maintainer_30m",
        "description": "Project index + dynamic docs knowledge maintainer (every 30m)",
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
                "You are project-index maintainer. Run command only:\n"
                f"python3 {maintainer_py} --registry {registry} "
                f"--task-db {task_db} --task-id {task_id} --actor {actor} "
                "--git-pull --doc-timeout 8 --doc-fetch-max-chars 24000\n"
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
    parser = argparse.ArgumentParser(description="Install project-index-maintainer cron job")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--job-id", default="5797cd5b-5539-4e95-8d58-dc65a4633ec5")
    parser.add_argument("--every-ms", type=int, default=1800000)
    parser.add_argument("--maintainer-py", default=str(home / ".openclaw/ops/policy/project_index_maintainer.py"))
    parser.add_argument("--registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--task-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--task-id", default="cron:project-index-maintainer-30m")
    parser.add_argument("--actor", default="project-agent")
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
        inferred_channel, inferred_target = infer_delivery(jobs, ["project-agent", "ops-agent"])
        channel = channel or inferred_channel
        target = target or inferred_target
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing project-agent/ops-agent delivery")

    maintainer_path = Path(args.maintainer_py).expanduser()
    registry_path = Path(args.registry).expanduser()
    task_db_path = Path(args.task_db).expanduser()
    task_id = str(args.task_id or "").strip() or "cron:project-index-maintainer-30m"
    actor = str(args.actor or "").strip() or "project-agent"
    if not bool(args.skip_path_check):
        if not maintainer_path.exists() or not maintainer_path.is_file():
            raise SystemExit(f"maintainer script missing: {maintainer_path}")
        if not registry_path.exists() or not registry_path.is_file():
            raise SystemExit(f"project registry missing: {registry_path}")
        if task_db_path.exists() and (not task_db_path.is_file()):
            raise SystemExit(f"task db path is not file: {task_db_path}")

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=args.job_id,
        every_ms=int(args.every_ms),
        maintainer_py=str(maintainer_path),
        registry=str(registry_path),
        task_db=str(task_db_path),
        task_id=task_id,
        actor=actor,
        channel=channel,
        target=target,
    )
    data["jobs"] = updated_jobs
    jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"job_id={args.job_id}")
    print(f"status={'updated' if existed else 'created'}")
    print(f"jobs_file={jobs_path}")
    print(f"maintainer_py={maintainer_path}")
    print(f"registry={registry_path}")
    print(f"task_db={task_db_path}")
    if not task_db_path.exists():
        print("warn=task_db_missing_now; job installed anyway; runtime will self-handle binding")
    print(f"task_id={task_id}")
    print(f"actor={actor}")
    print(f"delivery={channel}:{target}")


if __name__ == "__main__":
    main()

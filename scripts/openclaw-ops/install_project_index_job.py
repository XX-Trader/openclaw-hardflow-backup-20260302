#!/usr/bin/env python3
"""Install or update project-index-maintainer job in OpenClaw cron jobs.json."""

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

from io_write_gateway import write_json_atomic


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


def build_official_cron_surface(job_ids: list[str]) -> dict[str, Any]:
    normalized = [str(job_id).strip() for job_id in job_ids if str(job_id).strip()]
    return {
        "surface": "official-cron",
        "status_cmd": "openclaw cron status --json",
        "run_cmds": {job_id: f"openclaw cron run {job_id} --force" for job_id in normalized},
        "runs_cmds": {job_id: f"openclaw cron runs --id {job_id} --limit 20" for job_id in normalized},
        "notes": [
            "业务 job 定义继续落在 jobs.json。",
            "运行时状态查询与触发统一走官方 openclaw cron surface。",
        ],
    }


def build_runner_command(
    maintainer_py: str,
    registry: str,
    task_db: str,
    task_id: str,
    actor: str,
    git_pull: bool,
) -> str:
    command = (
        f"python3 {maintainer_py} --registry {registry} "
        f"--task-db {task_db} --task-id {task_id} --actor {actor} "
        "--doc-timeout 8 --doc-fetch-max-chars 24000"
    )
    if bool(git_pull):
        command += " --git-pull"
    return command


def build_message(command: str) -> str:
    return (
        "You are project-index maintainer. Run command only:\n"
        f"{str(command or '').strip()}\n"
        "Your first assistant turn MUST contain exactly one exec tool call for that command and no text. "
        "Do not inspect files, list directories, or run any other command. "
        "Execute the command exactly once. "
        "Do not run any follow-up command. "
        "Return EXACTLY raw stdout/stderr text from the command; "
        "do not add explanation, greeting, or prefix text. "
        "Never output sentences like 'Let's run ...', 'Now let's execute ...', or 'Okay, ...'. "
        "If output is NO_REPLY, reply NO_REPLY."
    )


def upsert_job(
    jobs: list[dict[str, Any]],
    job_id: str,
    every_ms: int,
    maintainer_py: str,
    registry: str,
    task_db: str,
    task_id: str,
    actor: str,
    git_pull: bool,
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
            "message": build_message(
                build_runner_command(maintainer_py, registry, task_db, task_id, actor, git_pull)
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
    parser.add_argument("--git-pull", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--skip-path-check", action="store_true")
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--emit-json", action="store_true")
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

    backup_file = ""
    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        backup_file = str(backup)

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=args.job_id,
        every_ms=int(args.every_ms),
        maintainer_py=str(maintainer_path),
        registry=str(registry_path),
        task_db=str(task_db_path),
        task_id=task_id,
        actor=actor,
        git_pull=bool(args.git_pull),
        channel=channel,
        target=target,
    )
    data["jobs"] = updated_jobs
    write_json_atomic(
        jobs_path,
        data,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )

    result = {
        "ok": True,
        "job_id": str(args.job_id),
        "status": ("updated" if existed else "created"),
        "backup": backup_file,
        "jobs_file": str(jobs_path),
        "maintainer_py": str(maintainer_path),
        "registry": str(registry_path),
        "task_db": str(task_db_path),
        "task_db_exists": task_db_path.exists(),
        "task_id": task_id,
        "actor": actor,
        "git_pull": bool(args.git_pull),
        "delivery": {"channel": channel, "to": target},
        "official_cron_surface": build_official_cron_surface([str(args.job_id)]),
    }
    if not task_db_path.exists():
        result["warn"] = "task_db_missing_now; job installed anyway; runtime will self-handle binding"

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    if backup_file:
        print(f"backup={backup_file}")
    print(f"job_id={result['job_id']}")
    print(f"status={result['status']}")
    print(f"jobs_file={jobs_path}")
    print(f"maintainer_py={maintainer_path}")
    print(f"registry={registry_path}")
    print(f"task_db={task_db_path}")
    if not task_db_path.exists():
        print("warn=task_db_missing_now; job installed anyway; runtime will self-handle binding")
    print(f"task_id={task_id}")
    print(f"actor={actor}")
    print(f"git_pull={str(bool(args.git_pull)).lower()}")
    print(f"delivery={channel}:{target}")
    print("cron_surface=official-cron")
    print(f"cron_status_cmd={result['official_cron_surface']['status_cmd']}")
    print(f"cron_run_cmd={result['official_cron_surface']['run_cmds'][str(args.job_id)]}")
    print(f"cron_runs_cmd={result['official_cron_surface']['runs_cmds'][str(args.job_id)]}")


if __name__ == "__main__":
    main()

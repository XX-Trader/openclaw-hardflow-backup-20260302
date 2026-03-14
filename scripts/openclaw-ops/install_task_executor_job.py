#!/usr/bin/env python3
"""Install or update task executor cron job in OpenClaw jobs.json."""

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


AUTO_MODEL_SENTINELS = {"", "auto", "default"}
NOTIFY_ON_MODES = {"error", "activity", "always"}


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs.json must be a JSON object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def infer_delivery(jobs: list[dict[str, Any]], preferred_agents: list[str]) -> tuple[str | None, str | None]:
    for agent_id in preferred_agents:
        for job in jobs:
            if str(job.get("agentId", "")).strip() != agent_id:
                continue
            delivery = job.get("delivery") or {}
            channel = str(delivery.get("channel", "")).strip()
            target = str(delivery.get("to", "")).strip()
            if channel and target:
                return channel, target
    return None, None


def build_official_cron_surface(job_ids: list[str]) -> dict[str, Any]:
    normalized = [str(job_id).strip() for job_id in job_ids if str(job_id).strip()]
    return {
        "surface": "official-cron",
        "status_cmd": "openclaw cron status --json",
        "run_cmds": {job_id: f"openclaw cron run {job_id} --force" for job_id in normalized},
        "runs_cmds": {job_id: f"openclaw cron runs --id {job_id} --limit 20" for job_id in normalized},
        "notes": [
            "任务执行器继续以 jobs.json 为业务定义源。",
            "启停、状态与手工触发统一走官方 openclaw cron surface。",
        ],
    }


def build_message(
    executor_py: str,
    db_path: str,
    max_tasks: int,
    model: str,
    actor: str,
    planner_id: str,
    openclaw_bin: str,
    report_dir: str,
    local_agent: bool,
    notify_on: str,
) -> str:
    command = (
        f'python3 "{executor_py}" '
        f'--task cron:task-executor '
        f'--db "{db_path}" '
        f'--max-tasks {max(1, int(max_tasks))} '
        f'--actor {actor} '
        f'--planner-id {planner_id} '
        f'--openclaw-bin {openclaw_bin} '
        f'--report-dir "{report_dir}" '
        f"--notify-on {notify_on}"
    )
    normalized_model = str(model or "").strip()
    if normalized_model:
        command += f" --model {normalized_model}"
    command += " --local-agent" if local_agent else " --no-local-agent"
    return build_scheduled_runner_message(
        command,
        role="ops-agent scheduled runner",
        extra_rules=[
            "Each process poll MUST use timeout 15000 and you MUST immediately poll again after each 'Process still running' result.",
            "Do not let a single process poll wait exceed 15000 ms.",
        ],
        forbid_file_inspection=True,
    )


def upsert_job(
    jobs: list[dict[str, Any]],
    job_id: str,
    executor_py: str,
    db_path: str,
    every_ms: int,
    max_tasks: int,
    model: str,
    actor: str,
    planner_id: str,
    openclaw_bin: str,
    report_dir: str,
    local_agent: bool,
    notify_on: str,
    channel: str,
    target: str,
) -> tuple[list[dict[str, Any]], bool]:
    timestamp = now_ms()
    next_run = timestamp + every_ms
    existed = False
    created_ms = timestamp
    old_state: dict[str, Any] = {}

    for item in jobs:
        if item.get("id") != job_id:
            continue
        existed = True
        created_ms = int(item.get("createdAtMs", timestamp))
        old_state = item.get("state") if isinstance(item.get("state"), dict) else {}
        break

    payload = {
        "id": job_id,
        "agentId": "ops-agent",
        "name": "task_executor_10m",
        "description": "Consume pending task-center items and execute assigned agents.",
        "enabled": True,
        "createdAtMs": created_ms,
        "updatedAtMs": timestamp,
        "schedule": {"kind": "every", "everyMs": every_ms, "anchorMs": created_ms},
        "sessionTarget": "isolated",
        "lightContext": True,
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(
                executor_py=executor_py,
                db_path=db_path,
                max_tasks=max_tasks,
                model=model,
                actor=actor,
                planner_id=planner_id,
                openclaw_bin=openclaw_bin,
                report_dir=report_dir,
                local_agent=local_agent,
                notify_on=notify_on,
            ),
            "timeoutSeconds": 1800,
        },
        "delivery": {"mode": "announce", "channel": channel, "to": target},
        "state": old_state,
    }
    payload["state"]["nextRunAtMs"] = next_run

    updated: list[dict[str, Any]] = []
    replaced = False
    for item in jobs:
        if item.get("id") == job_id:
            updated.append(payload)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(payload)
    return updated, existed


def main() -> None:
    home = Path(os.path.expanduser("~"))
    default_jobs = home / ".openclaw/cron/jobs.json"
    default_executor = home / ".openclaw/ops/policy/task_executor_runner.py"
    default_db = home / ".openclaw/ops/task-center/task_center.db"
    default_report_dir = home / ".openclaw/ops/task-center/executor-runs"

    parser = argparse.ArgumentParser(description="Install task executor cron job")
    parser.add_argument("--jobs-file", default=str(default_jobs))
    parser.add_argument("--job-id", default="c2c75adf-5e80-4b50-bf18-40ceadfa6bd6")
    parser.add_argument("--executor-py", default=str(default_executor))
    parser.add_argument("--db", default=str(default_db))
    parser.add_argument("--every-ms", type=int, default=600000)
    parser.add_argument("--max-tasks", type=int, default=3)
    parser.add_argument("--model", default="auto")
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--planner-id", default="coordinator")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--report-dir", default=str(default_report_dir))
    parser.add_argument("--local-agent", dest="local_agent", action="store_true", default=True)
    parser.add_argument("--no-local-agent", dest="local_agent", action="store_false")
    parser.add_argument("--notify-on", default="error", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data.get("jobs", [])

    channel = str(args.channel).strip()
    target = str(args.to).strip()
    if not channel or not target:
        inferred_channel, inferred_target = infer_delivery(jobs, ["ops-agent", "coordinator", "project-agent"])
        channel = channel or (inferred_channel or "telegram")
        target = target or (inferred_target or "")
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    executor_py = str(Path(args.executor_py).expanduser())
    db_path = str(Path(args.db).expanduser())
    report_dir = str(Path(args.report_dir).expanduser())
    model = str(args.model).strip()
    if model.lower() in AUTO_MODEL_SENTINELS:
        model = ""

    backup_file = ""
    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{now_stamp()}")
        shutil.copy2(jobs_path, backup)
        backup_file = str(backup)

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=str(args.job_id),
        executor_py=executor_py,
        db_path=db_path,
        every_ms=max(300000, int(args.every_ms)),
        max_tasks=max(1, int(args.max_tasks)),
        model=model,
        actor=str(args.actor),
        planner_id=str(args.planner_id),
        openclaw_bin=str(args.openclaw_bin),
        report_dir=report_dir,
        local_agent=bool(args.local_agent),
        notify_on=str(args.notify_on),
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
        "executor_py": executor_py,
        "db": db_path,
        "every_ms": max(300000, int(args.every_ms)),
        "max_tasks": max(1, int(args.max_tasks)),
        "model": (model or "auto(policy-config)"),
        "actor": str(args.actor),
        "planner_id": str(args.planner_id),
        "openclaw_bin": str(args.openclaw_bin),
        "report_dir": report_dir,
        "local_agent": bool(args.local_agent),
        "notify_on": str(args.notify_on),
        "delivery": {"channel": channel, "to": target},
        "official_cron_surface": build_official_cron_surface([str(args.job_id)]),
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    if backup_file:
        print(f"backup={backup_file}")
    print(f"job_id={result['job_id']}")
    print(f"status={result['status']}")
    print(f"jobs_file={jobs_path}")
    print(f"executor_py={executor_py}")
    print(f"db={db_path}")
    print(f"every_ms={result['every_ms']}")
    print(f"max_tasks={result['max_tasks']}")
    print(f"model={result['model']}")
    print(f"actor={args.actor}")
    print(f"planner_id={args.planner_id}")
    print(f"openclaw_bin={args.openclaw_bin}")
    print(f"report_dir={report_dir}")
    print(f"local_agent={str(bool(args.local_agent)).lower()}")
    print(f"notify_on={args.notify_on}")
    print(f"delivery={channel}:{target}")
    print("cron_surface=official-cron")
    print(f"cron_status_cmd={result['official_cron_surface']['status_cmd']}")
    print(f"cron_run_cmd={result['official_cron_surface']['run_cmds'][str(args.job_id)]}")
    print(f"cron_runs_cmd={result['official_cron_surface']['runs_cmds'][str(args.job_id)]}")


if __name__ == "__main__":
    main()

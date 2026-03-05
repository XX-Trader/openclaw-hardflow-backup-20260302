#!/usr/bin/env python3
"""Install or update TODO patrol job in OpenClaw cron jobs.json."""

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


def build_message(
    ops_script: str,
    max_dispatch: int,
    default_request_source: str,
    ai_context_min_pct: float,
    skip_ops_incidents: bool,
    output_mode: str,
) -> str:
    command = (
        f"python3 {ops_script} --task cron:todo-patrol --max-dispatch {int(max_dispatch)} "
        f"--default-request-source {default_request_source} --ai-context-min-pct {float(ai_context_min_pct)} "
        f"--output-mode {output_mode}"
    )
    if skip_ops_incidents:
        command += " --skip-ops-incidents"
    else:
        command += " --allow-ops-incidents"
    return (
        "You are ops-agent scheduled runner. Run command only:\n"
        f"{command}\n"
        "Execute the command exactly once. "
        "Do not run any follow-up command. "
        "Return EXACTLY raw stdout/stderr text from the command; "
        "do not add explanation, greeting, or prefix text. "
        "Never output sentences like 'Let's run ...' or 'Okay, ...'. "
        "If output is empty, reply NO_REPLY."
    )


def upsert_job(
    jobs: list[dict[str, Any]],
    job_id: str,
    ops_script: str,
    every_ms: int,
    max_dispatch: int,
    default_request_source: str,
    ai_context_min_pct: float,
    skip_ops_incidents: bool,
    output_mode: str,
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
        "name": "todo_patrol_15m",
        "description": "Read coordinator TODO and dispatch non-OPS items (OPS incidents stay manual via coordinator)",
        "enabled": True,
        "createdAtMs": created_ms,
        "updatedAtMs": timestamp,
        "schedule": {"kind": "every", "everyMs": every_ms, "anchorMs": created_ms},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(
                ops_script=ops_script,
                max_dispatch=max_dispatch,
                default_request_source=default_request_source,
                ai_context_min_pct=ai_context_min_pct,
                skip_ops_incidents=skip_ops_incidents,
                output_mode=output_mode,
            ),
            "timeoutSeconds": 1200,
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
    default_ops_script = home / ".openclaw/ops/todo_patrol.py"

    parser = argparse.ArgumentParser(description="Install TODO patrol cron job")
    parser.add_argument("--jobs-file", default=str(default_jobs))
    parser.add_argument("--job-id", default="16cb8d03-beb9-4697-927d-35952353bf8e")
    parser.add_argument("--ops-script", default=str(default_ops_script))
    parser.add_argument("--every-ms", type=int, default=900000)
    parser.add_argument("--max-dispatch", type=int, default=5)
    parser.add_argument("--default-request-source", default="human", choices=["human", "ai"])
    parser.add_argument("--ai-context-min-pct", type=float, default=100.0)
    parser.add_argument("--skip-ops-incidents", dest="skip_ops_incidents", action="store_true", default=True)
    parser.add_argument("--allow-ops-incidents", dest="skip_ops_incidents", action="store_false")
    parser.add_argument("--output-mode", default="summary", choices=["summary", "verbose", "silent"])
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
        inferred_channel, inferred_target = infer_delivery(jobs, ["ops-agent", "coordinator", "project-agent"])
        channel = channel or (inferred_channel or "telegram")
        target = target or (inferred_target or "")
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    ops_script = str(Path(args.ops_script).expanduser())

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{now_stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    updated_jobs, existed = upsert_job(
        jobs=jobs,
        job_id=str(args.job_id),
        ops_script=ops_script,
        every_ms=int(args.every_ms),
        max_dispatch=int(args.max_dispatch),
        default_request_source=str(args.default_request_source),
        ai_context_min_pct=float(args.ai_context_min_pct),
        skip_ops_incidents=bool(args.skip_ops_incidents),
        output_mode=str(args.output_mode),
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

    print(f"job_id={args.job_id}")
    print(f"status={'updated' if existed else 'created'}")
    print(f"jobs_file={jobs_path}")
    print(f"ops_script={ops_script}")
    print(f"default_request_source={args.default_request_source}")
    print(f"ai_context_min_pct={float(args.ai_context_min_pct)}")
    print(f"skip_ops_incidents={str(bool(args.skip_ops_incidents)).lower()}")
    print(f"output_mode={args.output_mode}")
    print(f"delivery={channel}:{target}")


if __name__ == "__main__":
    main()

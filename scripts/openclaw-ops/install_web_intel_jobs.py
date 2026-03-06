#!/usr/bin/env python3
"""Install or update web intelligence cron jobs.

Jobs:
1) web-agent periodic collection.
2) optimization-agent periodic review.
3) project-agent periodic doc-focused review.
"""

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

COLLECT_JOB_ID = "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a1"
OPT_REVIEW_JOB_ID = "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a2"
PROJECT_REVIEW_JOB_ID = "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a3"


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
        "You are scheduled runner. Run command only:\n"
        f"{command}\n"
        "Execute exactly once. "
        "Return EXACTLY raw stdout/stderr text from the command; "
        "do not add explanation, greeting, or prefix text. "
        "If output is empty, reply NO_REPLY."
    )


def normalize_shell_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return os.path.expanduser(raw).replace("\\", "/")


def make_job(
    *,
    job_id: str,
    agent_id: str,
    name: str,
    description: str,
    every_ms: int,
    message: str,
    timeout_seconds: int,
    old: dict[str, Any] | None,
    channel: str,
    target: str,
) -> dict[str, Any]:
    ts = now_ms()
    created_at = int(old.get("createdAtMs", ts)) if isinstance(old, dict) else ts
    old_state = old.get("state") if isinstance(old, dict) and isinstance(old.get("state"), dict) else {}
    payload = {
        "id": job_id,
        "agentId": agent_id,
        "name": name,
        "description": description,
        "enabled": True,
        "createdAtMs": created_at,
        "updatedAtMs": ts,
        "schedule": {
            "kind": "every",
            "everyMs": max(600000, int(every_ms)),
            "anchorMs": created_at,
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": message,
            "timeoutSeconds": max(300, int(timeout_seconds)),
        },
        "delivery": {
            "mode": "announce",
            "channel": channel,
            "to": target,
        },
        "state": old_state,
    }
    payload["state"]["nextRunAtMs"] = ts + max(600000, int(every_ms))
    return payload


def main() -> None:
    home = Path(os.path.expanduser("~")).resolve()
    parser = argparse.ArgumentParser(description="Install web intelligence jobs")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--collector-job-id", default=COLLECT_JOB_ID)
    parser.add_argument("--opt-review-job-id", default=OPT_REVIEW_JOB_ID)
    parser.add_argument("--project-review-job-id", default=PROJECT_REVIEW_JOB_ID)
    parser.add_argument("--collector-py", default=str(home / ".openclaw/ops/web_intel_collect_runner.py"))
    parser.add_argument("--review-py", default=str(home / ".openclaw/ops/web_intel_review_runner.py"))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--collect-sources-file", default=str(home / ".openclaw/ops/web/sources.json"))
    parser.add_argument("--project-doc-sources-file", default=str(home / ".openclaw/ops/web/project_docs_sources.json"))
    parser.add_argument("--collect-every-ms", type=int, default=3600000)
    parser.add_argument("--opt-review-every-ms", type=int, default=14400000)
    parser.add_argument("--project-review-every-ms", type=int, default=21600000)
    parser.add_argument("--collect-min-interval-minutes", type=int, default=60)
    parser.add_argument("--review-min-interval-minutes", type=int, default=180)
    parser.add_argument("--skip-path-check", action="store_true")
    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data["jobs"]

    channel = str(args.channel).strip()
    target = str(args.to).strip()
    if not channel or not target:
        got_channel, got_target = infer_delivery(
            jobs,
            ["web-agent", "optimization-agent", "project-agent", "ops-agent", "coordinator"],
        )
        channel = channel or (got_channel or "telegram")
        target = target or (got_target or "")
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    collector_py = Path(args.collector_py).expanduser()
    review_py = Path(args.review_py).expanduser()
    openclaw_home = Path(args.openclaw_home).expanduser()
    collect_sources_file = Path(args.collect_sources_file).expanduser()
    project_doc_sources_file = Path(args.project_doc_sources_file).expanduser()

    if not bool(args.skip_path_check):
        if not collector_py.exists():
            raise SystemExit(f"collector runner missing: {collector_py}")
        if not review_py.exists():
            raise SystemExit(f"review runner missing: {review_py}")
        if not collect_sources_file.exists():
            raise SystemExit(f"sources file missing: {collect_sources_file}")
        if not project_doc_sources_file.exists():
            raise SystemExit(f"project docs sources file missing: {project_doc_sources_file}")

    openclaw_home_sh = normalize_shell_path(str(openclaw_home))
    collector_py_sh = normalize_shell_path(str(collector_py))
    review_py_sh = normalize_shell_path(str(review_py))
    collect_sources_sh = normalize_shell_path(str(collect_sources_file))
    project_sources_sh = normalize_shell_path(str(project_doc_sources_file))

    collect_cmd = (
        f"{args.python_bin} {collector_py_sh} "
        f"--task-id cron:web-intel-collect "
        f"--openclaw-home {openclaw_home_sh} "
        f"--sources-file {collect_sources_sh} "
        f"--state-file {openclaw_home_sh}/ops/web-intel/state.json "
        f"--report-dir {openclaw_home_sh}/ops/web-intel/reports "
        f"--min-interval-minutes {max(1, int(args.collect_min_interval_minutes))} "
        "--normal-log-mode silent"
    )
    opt_review_cmd = (
        f"{args.python_bin} {review_py_sh} "
        f"--mode optimization "
        f"--task-id cron:web-intel-review-optimization "
        f"--openclaw-home {openclaw_home_sh} "
        f"--sources-file {collect_sources_sh} "
        f"--state-file {openclaw_home_sh}/ops/web-intel/review-state.json "
        f"--report-dir {openclaw_home_sh}/ops/web-intel/review-reports "
        f"--min-interval-minutes {max(1, int(args.review_min_interval_minutes))} "
        "--normal-log-mode silent"
    )
    project_review_cmd = (
        f"{args.python_bin} {review_py_sh} "
        f"--mode project-doc "
        f"--task-id cron:web-intel-review-project-doc "
        f"--openclaw-home {openclaw_home_sh} "
        f"--sources-file {project_sources_sh} "
        f"--state-file {openclaw_home_sh}/ops/web-intel/review-state.json "
        f"--report-dir {openclaw_home_sh}/ops/web-intel/review-reports "
        f"--min-interval-minutes {max(1, int(args.review_min_interval_minutes))} "
        "--normal-log-mode silent"
    )

    jobs_by_id = {str(item.get("id", "")): item for item in jobs if isinstance(item, dict)}
    fresh_jobs = [
        make_job(
            job_id=str(args.collector_job_id),
            agent_id="web-agent",
            name="web_intel_collect_hourly",
            description="web-agent collects internet intelligence with browser fallback",
            every_ms=max(600000, int(args.collect_every_ms)),
            message=build_message(collect_cmd),
            timeout_seconds=1500,
            old=jobs_by_id.get(str(args.collector_job_id)),
            channel=channel,
            target=target,
        ),
        make_job(
            job_id=str(args.opt_review_job_id),
            agent_id="optimization-agent",
            name="web_intel_review_optimization_4h",
            description="optimization-agent reviews collected web intel and outputs workflow optimization suggestions",
            every_ms=max(600000, int(args.opt_review_every_ms)),
            message=build_message(opt_review_cmd),
            timeout_seconds=1500,
            old=jobs_by_id.get(str(args.opt_review_job_id)),
            channel=channel,
            target=target,
        ),
        make_job(
            job_id=str(args.project_review_job_id),
            agent_id="project-agent",
            name="web_intel_review_project_docs_6h",
            description="project-agent reviews official docs and outputs code change recommendations",
            every_ms=max(600000, int(args.project_review_every_ms)),
            message=build_message(project_review_cmd),
            timeout_seconds=1500,
            old=jobs_by_id.get(str(args.project_review_job_id)),
            channel=channel,
            target=target,
        ),
    ]

    status: dict[str, str] = {}
    updated_by_id = {str(item.get("id", "")): item for item in jobs if isinstance(item, dict)}
    for item in fresh_jobs:
        jid = str(item.get("id", ""))
        status[jid] = "updated" if jid in updated_by_id else "created"
        updated_by_id[jid] = item

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for old in jobs:
        jid = str(old.get("id", ""))
        if jid in updated_by_id:
            ordered.append(updated_by_id[jid])
            seen.add(jid)
        else:
            ordered.append(old)
    for item in fresh_jobs:
        jid = str(item.get("id", ""))
        if jid not in seen:
            ordered.append(item)

    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        print(f"backup={backup}")

    data["jobs"] = ordered
    write_json_atomic(
        jobs_path,
        data,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )

    summary = {
        "ok": True,
        "jobs_file": str(jobs_path),
        "delivery": f"{channel}:{target}",
        "collector_job_id": str(args.collector_job_id),
        "opt_review_job_id": str(args.opt_review_job_id),
        "project_review_job_id": str(args.project_review_job_id),
        "status": status,
        "collector_every_ms": max(600000, int(args.collect_every_ms)),
        "opt_review_every_ms": max(600000, int(args.opt_review_every_ms)),
        "project_review_every_ms": max(600000, int(args.project_review_every_ms)),
        "collector_sources_file": str(collect_sources_file),
        "project_doc_sources_file": str(project_doc_sources_file),
    }
    if bool(args.emit_json):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"jobs_file={jobs_path}")
        print(f"delivery={channel}:{target}")
        print(f"collector_job={args.collector_job_id} status={status.get(str(args.collector_job_id), 'updated')}")
        print(f"opt_review_job={args.opt_review_job_id} status={status.get(str(args.opt_review_job_id), 'updated')}")
        print(
            f"project_review_job={args.project_review_job_id} status={status.get(str(args.project_review_job_id), 'updated')}"
        )
        print(f"collector_every_ms={summary['collector_every_ms']}")
        print(f"opt_review_every_ms={summary['opt_review_every_ms']}")
        print(f"project_review_every_ms={summary['project_review_every_ms']}")


if __name__ == "__main__":
    main()

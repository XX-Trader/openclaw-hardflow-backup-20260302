#!/usr/bin/env python3
"""Clear stale runningAtMs markers from OpenClaw cron jobs.json."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def now_stamp_utc() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def recover_stale_running_state(
    jobs_file: Path,
    *,
    stale_minutes: int = 30,
    dry_run: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if not jobs_file.exists():
        return {
            "ok": False,
            "jobs_file": str(jobs_file),
            "error": f"jobs_file_missing:{jobs_file}",
            "updated_count": 0,
            "updated_jobs": [],
            "backup_path": "",
        }

    raw = json.loads(jobs_file.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        return {
            "ok": False,
            "jobs_file": str(jobs_file),
            "error": f"jobs_file_invalid:{jobs_file}",
            "updated_count": 0,
            "updated_jobs": [],
            "backup_path": "",
        }

    jobs = raw.get("jobs", [])
    if not isinstance(jobs, list):
        return {
            "ok": False,
            "jobs_file": str(jobs_file),
            "error": f"jobs_list_invalid:{jobs_file}",
            "updated_count": 0,
            "updated_jobs": [],
            "backup_path": "",
        }

    now_ms = _safe_int(now_ms, 0) or int(datetime.now(UTC).timestamp() * 1000)
    threshold_ms = max(1, int(stale_minutes)) * 60 * 1000
    updated_jobs: list[dict[str, Any]] = []

    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            continue
        state = job.get("state")
        if not isinstance(state, dict):
            continue
        running_at_ms = _safe_int(state.get("runningAtMs"), 0)
        if running_at_ms <= 0:
            continue
        age_ms = now_ms - running_at_ms
        if age_ms < threshold_ms:
            continue
        updated_jobs.append(
            {
                "index": index,
                "name": str(job.get("name", "")).strip() or f"job-{index + 1}",
                "running_at_ms": running_at_ms,
                "stale_minutes": round(age_ms / 60000.0, 2),
            }
        )
        state["runningAtMs"] = None

    backup_path = ""
    if updated_jobs and not dry_run:
        backup = jobs_file.with_name(f"{jobs_file.name}.bak.recover-{now_stamp_utc()}")
        shutil.copy2(jobs_file, backup)
        jobs_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        backup_path = str(backup)

    return {
        "ok": True,
        "jobs_file": str(jobs_file),
        "dry_run": bool(dry_run),
        "stale_minutes": max(1, int(stale_minutes)),
        "updated_count": len(updated_jobs),
        "updated_jobs": updated_jobs,
        "backup_path": backup_path,
    }


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Clear stale runningAtMs markers from cron jobs.json")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    result = recover_stale_running_state(
        Path(args.jobs_file).expanduser(),
        stale_minutes=max(1, int(args.stale_minutes)),
        dry_run=bool(args.dry_run),
    )
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"ok={str(bool(result.get('ok'))).lower()}")
        print(f"jobs_file={result.get('jobs_file', '')}")
        print(f"dry_run={str(bool(result.get('dry_run'))).lower()}")
        print(f"stale_minutes={int(result.get('stale_minutes', 0) or 0)}")
        print(f"updated_count={int(result.get('updated_count', 0) or 0)}")
        if result.get("backup_path"):
            print(f"backup_path={result['backup_path']}")
        for item in result.get("updated_jobs", []) or []:
            print(f"updated_job={item.get('name', '')}")
        if result.get("error"):
            print(f"error={result['error']}")
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

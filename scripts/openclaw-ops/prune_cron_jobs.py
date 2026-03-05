#!/usr/bin/env python3
"""Prune OpenClaw cron jobs.json by allowed job names."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs file must be JSON object")
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Prune jobs.json by allowed names")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--allow-name", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_file = Path(args.jobs_file).expanduser()
    allow_names = {str(x).strip() for x in args.allow_name if str(x).strip()}
    if not allow_names:
        raise SystemExit("at least one --allow-name is required")

    data = load_jobs(jobs_file)
    jobs = data.get("jobs", [])
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    for item in jobs:
        if not isinstance(item, dict):
            removed.append({"id": "", "name": str(item)})
            continue
        name = str(item.get("name", "")).strip()
        if name in allow_names:
            kept.append(item)
        else:
            removed.append({"id": str(item.get("id", "")), "name": name})

    result = {
        "jobs_file": str(jobs_file),
        "allow_names": sorted(allow_names),
        "before_total": len(jobs),
        "after_total": len(kept),
        "removed_total": len(removed),
        "removed": removed,
        "dry_run": bool(args.dry_run),
    }

    if not args.dry_run:
        if jobs_file.exists():
            backup = jobs_file.with_name(f"{jobs_file.name}.bak.{now_stamp()}")
            shutil.copy2(jobs_file, backup)
            result["backup"] = str(backup)
        data["jobs"] = kept
        jobs_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


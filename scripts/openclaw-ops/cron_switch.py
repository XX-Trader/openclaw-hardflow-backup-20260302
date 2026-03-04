#!/usr/bin/env python3
"""Pause/resume/status for OpenClaw cron jobs.

Use this when you need to quickly disable all scheduled jobs to save token cost.
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

from io_write_gateway import FileWriteError, write_json_atomic

UTC = timezone.utc
SCHEDULE_KINDS = {"every", "cron"}
MANAGED_NAME_PREFIXES = (
    "ops_",
    "reviewer_",
    "project_index_maintainer",
    "todo_patrol",
    "experience_maintain",
    "daily_todo_digest",
    "log-watcher",
)


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def load_jobs(path: Path) -> dict[str, Any]:
    data = load_json(path, {"version": 1, "jobs": []})
    if not isinstance(data, dict):
        data = {"version": 1, "jobs": []}
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def get_schedule_kind(item: dict[str, Any]) -> str:
    schedule = item.get("schedule")
    if not isinstance(schedule, dict):
        return ""
    return str(schedule.get("kind", "")).strip().lower()


def is_scheduled_job(item: dict[str, Any]) -> bool:
    return get_schedule_kind(item) in SCHEDULE_KINDS


def match_scope(item: dict[str, Any], scope: str) -> bool:
    if not is_scheduled_job(item):
        return False
    if scope == "all":
        return True
    name = str(item.get("name", "")).strip().lower()
    if any(name.startswith(prefix) for prefix in MANAGED_NAME_PREFIXES):
        return True
    agent_id = str(item.get("agentId", "")).strip().lower()
    if agent_id in {"ops-agent", "reviewer", "project-agent"}:
        return True
    return False


def build_overview(jobs: list[dict[str, Any]], scope: str) -> dict[str, int]:
    total_jobs = 0
    matched_jobs = 0
    enabled_jobs = 0
    disabled_jobs = 0
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not is_scheduled_job(item):
            continue
        total_jobs += 1
        if not match_scope(item, scope):
            continue
        matched_jobs += 1
        if bool(item.get("enabled", False)):
            enabled_jobs += 1
        else:
            disabled_jobs += 1
    return {
        "scheduled_jobs_total": total_jobs,
        "matched_jobs": matched_jobs,
        "enabled_jobs": enabled_jobs,
        "disabled_jobs": disabled_jobs,
    }


def disable_jobs(
    jobs: list[dict[str, Any]],
    scope: str,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    changed_ids: list[str] = []
    already_disabled_ids: list[str] = []
    ts = now_ms()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not match_scope(item, scope):
            continue
        jid = str(item.get("id", "")).strip()
        if not jid:
            continue
        if bool(item.get("enabled", False)):
            item["enabled"] = False
            item["updatedAtMs"] = ts
            changed_ids.append(jid)
        else:
            already_disabled_ids.append(jid)
    return jobs, changed_ids, already_disabled_ids


def enable_jobs(
    jobs: list[dict[str, Any]],
    scope: str,
    resume_ids: set[str] | None,
    force_all: bool,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    changed_ids: list[str] = []
    skipped_ids: list[str] = []
    ts = now_ms()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not match_scope(item, scope):
            continue
        jid = str(item.get("id", "")).strip()
        if not jid:
            continue
        if (not force_all) and resume_ids is not None and jid not in resume_ids:
            skipped_ids.append(jid)
            continue
        if not bool(item.get("enabled", False)):
            item["enabled"] = True
            item["updatedAtMs"] = ts
            changed_ids.append(jid)
    return jobs, changed_ids, skipped_ids


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Pause/resume OpenClaw scheduled jobs")
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "off", "on"],
        help="status|off|on",
    )
    parser.add_argument("--jobs-file", default=str(home / ".openclaw" / "cron" / "jobs.json"))
    parser.add_argument(
        "--state-file",
        default=str(home / ".openclaw" / "ops" / "cron-switch" / "state.json"),
    )
    parser.add_argument("--scope", default="all", choices=["all", "managed"])
    parser.add_argument("--force-all", action="store_true", help="for action=on: enable all matched jobs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_file = Path(args.jobs_file).expanduser()
    state_file = Path(args.state_file).expanduser()
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_file)
    jobs_raw = data.get("jobs", [])
    jobs: list[dict[str, Any]] = [x for x in jobs_raw if isinstance(x, dict)]
    state = load_json(state_file, {})
    if not isinstance(state, dict):
        state = {}

    overview_before = build_overview(jobs, str(args.scope))
    changed_ids: list[str] = []
    notes: list[str] = []
    action_result = "noop"
    backup_file = ""

    if args.action == "off":
        _jobs, changed_ids, already_disabled = disable_jobs(jobs, scope=str(args.scope))
        if changed_ids:
            action_result = "disabled"
        else:
            action_result = "already_disabled"
        if already_disabled:
            notes.append(f"already_disabled={len(already_disabled)}")

        paused_map = state.get("paused_by_switch")
        if not isinstance(paused_map, dict):
            paused_map = {}
        for jid in changed_ids:
            paused_map[jid] = True
        state["paused_by_switch"] = paused_map
        state["last_action"] = "off"
        state["updated_at"] = now_iso()
        state["scope"] = str(args.scope)
        state["jobs_file"] = str(jobs_file)

    elif args.action == "on":
        paused_map = state.get("paused_by_switch")
        if isinstance(paused_map, dict):
            resume_ids = {str(k).strip() for k, v in paused_map.items() if bool(v)}
        else:
            resume_ids = set()
        _jobs, changed_ids, skipped = enable_jobs(
            jobs,
            scope=str(args.scope),
            resume_ids=resume_ids,
            force_all=bool(args.force_all),
        )
        if changed_ids:
            action_result = "enabled"
        else:
            action_result = "already_enabled_or_not_tracked"
        if skipped and (not args.force_all):
            notes.append(f"skipped_not_tracked={len(skipped)}")

        if isinstance(paused_map, dict):
            for jid in changed_ids:
                paused_map.pop(jid, None)
            state["paused_by_switch"] = paused_map
        state["last_action"] = "on"
        state["updated_at"] = now_iso()
        state["scope"] = str(args.scope)
        state["jobs_file"] = str(jobs_file)

    overview_after = build_overview(jobs, str(args.scope))

    if args.action in {"off", "on"} and changed_ids and not bool(args.dry_run):
        if jobs_file.exists():
            backup = jobs_file.with_name(f"{jobs_file.name}.bak.switch.{stamp()}")
            shutil.copy2(jobs_file, backup)
            backup_file = str(backup)
        data["jobs"] = jobs
        save_json(jobs_file, data)
        save_json(state_file, state)

    result = {
        "ok": True,
        "action": args.action,
        "action_result": action_result,
        "scope": str(args.scope),
        "dry_run": bool(args.dry_run),
        "jobs_file": str(jobs_file),
        "state_file": str(state_file),
        "backup": backup_file,
        "changed_job_ids": changed_ids,
        "changed_count": len(changed_ids),
        "overview_before": overview_before,
        "overview_after": overview_after,
        "notes": notes,
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"action={result['action']}")
        print(f"result={result['action_result']}")
        print(f"scope={result['scope']}")
        print(f"changed_count={result['changed_count']}")
        print(f"before={json.dumps(result['overview_before'], ensure_ascii=False)}")
        print(f"after={json.dumps(result['overview_after'], ensure_ascii=False)}")
        if result["notes"]:
            print("notes=" + ";".join(result["notes"]))
        if result["backup"]:
            print(f"backup={result['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

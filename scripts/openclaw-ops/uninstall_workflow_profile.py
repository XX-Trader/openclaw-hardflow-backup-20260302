#!/usr/bin/env python3
"""Uninstall OpenClaw workflow runtime artifacts without touching repository sources."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILES = {"core", "all"}
MANAGED_ENV_PREFIX = "HARDFLOW_OPENCLAW_"
CORE_RUNTIME_HOOKS = (
    "hardflow-command-guard",
    "hardflow-audit",
    "hardflow-stop-gate-reminder",
    "hardflow-policy-enforcer",
)
CORE_JOB_IDS = {
    "16cb8d03-beb9-4697-927d-35952353bf8e",  # todo_patrol_15m
    "c2c75adf-5e80-4b50-bf18-40ceadfa6bd6",  # task_executor_10m
    "5797cd5b-5539-4e95-8d58-dc65a4633ec5",  # project_index_maintainer_30m
    "31f0c650-53d2-4b86-9d8b-6ad8e8f0d053",  # ops_local_openclaw_git_backup
    "d3859fd5-3ea2-4ee5-ab1d-7fd526f26722",  # reviewer_git_update_hourly
    "0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a",  # reviewer_incremental_daily_4am
    "a9c4a133-bf5b-4b91-8d89-ec97995f95f9",  # reviewer_recurring_bi_daily
    "771fda88-c8ff-49dc-a4da-6f57167c1d26",  # reviewer_weekly_structure_review
}
CORE_JOB_NAMES = {
    "todo_patrol_15m",
    "task_executor_10m",
    "project_index_maintainer_30m",
    "ops_incremental_monitor",
    "ops_full_calibration",
    "ops_daily_summary",
    "ops_git_sync_push",
    "ops_governance_evolution_incremental",
    "ops_conversation_evolution_incremental",
    "ops_self_evolution_weekly_todo",
    "ops_daily_work_report_dingtalk",
    "ops_auto_update_install_hourly",
    "ops_system_schedule_audit",
    "ops_local_openclaw_git_backup",
    "reviewer_git_update_hourly",
    "reviewer_incremental_daily_4am",
    "reviewer_recurring_bi_daily",
    "reviewer_weekly_structure_review",
}
ALL_JOB_IDS = CORE_JOB_IDS | {
    "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a1",  # web_intel_collect_hourly
    "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a2",  # web_intel_review_optimization_4h
    "fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a3",  # web_intel_review_project_docs_6h
}
ALL_JOB_NAMES = CORE_JOB_NAMES | {
    "ops_github_web_evolution_incremental",
    "web_intel_collect_hourly",
    "web_intel_review_optimization_4h",
    "web_intel_review_project_docs_6h",
}


def now_stamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"json root must be an object: {path}")
    return raw


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    fresh: dict[str, Any] = {}
    parent[key] = fresh
    return fresh


def cleanup_empty_nodes(value: Any) -> bool:
    if isinstance(value, dict):
        for key in list(value.keys()):
            child = value[key]
            should_drop = cleanup_empty_nodes(child)
            if should_drop:
                value.pop(key, None)
        return not value
    if isinstance(value, list):
        return len(value) == 0
    return False


def normalize_path_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    expanded = os.path.expanduser(text)
    try:
        resolved = Path(expanded).resolve()
        return os.path.normcase(str(resolved))
    except Exception:
        return os.path.normcase(expanded)


def managed_job_scope(profile: str) -> tuple[set[str], set[str]]:
    selected = str(profile or "all").strip().lower()
    if selected not in PROFILES:
        selected = "all"
    if selected == "core":
        return set(CORE_JOB_IDS), set(CORE_JOB_NAMES)
    return set(ALL_JOB_IDS), set(ALL_JOB_NAMES)


def plan_jobs_uninstall(jobs_file: Path, profile: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "jobs_file": str(jobs_file),
        "profile": profile,
        "changed": False,
        "removed": [],
        "kept_count": 0,
        "removed_count": 0,
        "backup": "",
        "written": False,
    }
    if not jobs_file.exists():
        result["note"] = "jobs_file_missing"
        return result

    try:
        data = load_json_object(jobs_file)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"jobs_file_invalid:{jobs_file}:{exc}"
        return result

    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        result["ok"] = False
        result["error"] = f"jobs_list_missing:{jobs_file}"
        return result

    managed_ids, managed_names = managed_job_scope(profile)
    kept_jobs: list[dict[str, Any]] = []
    removed_jobs: list[dict[str, str]] = []
    for job in jobs:
        if not isinstance(job, dict):
            kept_jobs.append(job)
            continue
        job_id = str(job.get("id") or "").strip()
        job_name = str(job.get("name") or "").strip()
        if job_id in managed_ids or job_name in managed_names:
            removed_jobs.append({"id": job_id, "name": job_name})
            continue
        kept_jobs.append(job)

    result["removed"] = removed_jobs
    result["removed_count"] = len(removed_jobs)
    result["kept_count"] = len(kept_jobs)
    result["changed"] = len(removed_jobs) > 0
    if result["changed"]:
        planned = dict(data)
        planned["jobs"] = kept_jobs
        result["_planned_payload"] = planned
    return result


def remove_from_string_list(root: dict[str, Any], path: list[str], removed_keys: set[str]) -> list[str]:
    cursor: Any = root
    for key in path[:-1]:
        if not isinstance(cursor, dict):
            return []
        cursor = cursor.get(key)
    if not isinstance(cursor, dict):
        return []
    leaf = path[-1]
    items = cursor.get(leaf)
    if not isinstance(items, list):
        return []

    removed: list[str] = []
    kept: list[Any] = []
    for item in items:
        key = normalize_path_key(str(item))
        if key and key in removed_keys:
            removed.append(str(item))
            continue
        kept.append(item)
    if removed:
        if kept:
            cursor[leaf] = kept
        else:
            cursor.pop(leaf, None)
    return removed


def plan_runtime_config_uninstall(runtime_config: Path, workflow_repo_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "runtime_config": str(runtime_config),
        "workflow_repo_path": str(workflow_repo_path.resolve()),
        "changed": False,
        "removed_env_vars": [],
        "removed_hook_dirs": [],
        "removed_skill_dirs": [],
        "removed_hook_entries": [],
        "backup": "",
        "written": False,
    }
    if not runtime_config.exists():
        result["note"] = "runtime_config_missing"
        return result

    try:
        current = load_json_object(runtime_config)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"runtime_config_invalid:{runtime_config}:{exc}"
        return result

    planned = json.loads(json.dumps(current))
    env_cfg = ensure_object(ensure_object(planned, "env"), "vars")
    removed_env = [key for key in list(env_cfg.keys()) if str(key).startswith(MANAGED_ENV_PREFIX)]
    for key in removed_env:
        env_cfg.pop(key, None)

    remove_keys = {
        normalize_path_key(str(workflow_repo_path / "hooks")),
        normalize_path_key(str(workflow_repo_path / "skills")),
    }
    removed_hook_dirs = remove_from_string_list(planned, ["hooks", "internal", "load", "extraDirs"], remove_keys)
    removed_skill_dirs = remove_from_string_list(planned, ["skills", "load", "extraDirs"], remove_keys)

    removed_hook_entries: list[str] = []
    hooks_entries = (
        planned.get("hooks", {})
        if isinstance(planned.get("hooks"), dict)
        else {}
    )
    internal = hooks_entries.get("internal") if isinstance(hooks_entries.get("internal"), dict) else {}
    entries = internal.get("entries") if isinstance(internal.get("entries"), dict) else {}
    for hook_name in CORE_RUNTIME_HOOKS:
        entry = entries.get(hook_name)
        if isinstance(entry, dict) and set(entry.keys()) == {"enabled"} and bool(entry.get("enabled")):
            entries.pop(hook_name, None)
            removed_hook_entries.append(hook_name)

    cleanup_empty_nodes(planned)

    result["removed_env_vars"] = sorted(removed_env)
    result["removed_hook_dirs"] = removed_hook_dirs
    result["removed_skill_dirs"] = removed_skill_dirs
    result["removed_hook_entries"] = removed_hook_entries
    result["changed"] = planned != current
    if result["changed"]:
        result["_planned_payload"] = planned
    return result


def cleanup_empty_parent_dirs(target_ops_dir: Path, path: Path) -> None:
    parent = path.parent
    while parent.exists() and parent != target_ops_dir.parent:
        try:
            parent.rmdir()
        except OSError:
            break
        if parent == target_ops_dir:
            break
        parent = parent.parent


def plan_ops_manifest_uninstall(target_ops_dir: Path, manifest_file: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "target_ops_dir": str(target_ops_dir),
        "manifest_file": str(manifest_file),
        "changed": False,
        "managed_files": [],
        "delete_candidates": [],
        "missing_managed_files": [],
        "deleted_count": 0,
        "manifest_removed": False,
    }
    if not manifest_file.exists():
        result["note"] = "manifest_missing"
        return result

    try:
        manifest = load_json_object(manifest_file)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"manifest_invalid:{manifest_file}:{exc}"
        return result

    managed_files = manifest.get("managed_files", [])
    if not isinstance(managed_files, list):
        result["ok"] = False
        result["error"] = f"manifest_managed_files_missing:{manifest_file}"
        return result

    delete_candidates: list[str] = []
    missing_managed_files: list[str] = []
    for rel in managed_files:
        rel_text = str(rel).replace("\\", "/").lstrip("/")
        if not rel_text:
            continue
        target = target_ops_dir / rel_text
        if target.exists():
            delete_candidates.append(str(target))
        else:
            missing_managed_files.append(rel_text)

    result["managed_files"] = [str(x).replace("\\", "/").lstrip("/") for x in managed_files if str(x).strip()]
    result["delete_candidates"] = delete_candidates
    result["missing_managed_files"] = missing_managed_files
    result["deleted_count"] = len(delete_candidates)
    result["manifest_removed"] = True
    result["changed"] = bool(delete_candidates) or manifest_file.exists()
    return result


def apply_jobs_uninstall(result: dict[str, Any], dry_run: bool) -> None:
    if dry_run or (not result.get("changed")):
        return
    jobs_file = Path(result["jobs_file"])
    backup = jobs_file.with_name(f"{jobs_file.name}.bak.uninstall.{now_stamp_utc()}")
    shutil.copy2(jobs_file, backup)
    write_json_object(jobs_file, result["_planned_payload"])
    result["backup"] = str(backup)
    result["written"] = True
    result.pop("_planned_payload", None)


def apply_runtime_config_uninstall(result: dict[str, Any], dry_run: bool) -> None:
    if dry_run or (not result.get("changed")):
        return
    runtime_config = Path(result["runtime_config"])
    backup = runtime_config.with_name(f"{runtime_config.name}.bak.uninstall.{now_stamp_utc()}")
    shutil.copy2(runtime_config, backup)
    write_json_object(runtime_config, result["_planned_payload"])
    result["backup"] = str(backup)
    result["written"] = True
    result.pop("_planned_payload", None)


def apply_ops_manifest_uninstall(result: dict[str, Any], dry_run: bool) -> None:
    if dry_run or (not result.get("changed")):
        return
    target_ops_dir = Path(result["target_ops_dir"])
    manifest_file = Path(result["manifest_file"])
    deleted: list[str] = []
    for target_text in result.get("delete_candidates", []):
        target = Path(target_text)
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        deleted.append(str(target))
        cleanup_empty_parent_dirs(target_ops_dir, target)
    if manifest_file.exists():
        manifest_file.unlink()
        cleanup_empty_parent_dirs(target_ops_dir, manifest_file)
    result["delete_candidates"] = deleted


def main() -> int:
    home = Path.home()
    parser = argparse.ArgumentParser(description="Uninstall OpenClaw workflow runtime artifacts")
    parser.add_argument("--profile", default="all", choices=sorted(PROFILES))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--jobs-file", default="")
    parser.add_argument("--runtime-config", default="")
    parser.add_argument("--workflow-repo-path", default=str(home / "openclaw-hardflow-backup-20260302"))
    parser.add_argument("--target-ops-dir", default="")
    parser.add_argument("--manifest-file", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    openclaw_home = Path(args.openclaw_home).expanduser()
    jobs_file = Path(args.jobs_file).expanduser() if str(args.jobs_file).strip() else (openclaw_home / "cron" / "jobs.json")
    runtime_config = (
        Path(args.runtime_config).expanduser()
        if str(args.runtime_config).strip()
        else (openclaw_home / "openclaw.json")
    )
    target_ops_dir = (
        Path(args.target_ops_dir).expanduser()
        if str(args.target_ops_dir).strip()
        else (openclaw_home / "ops")
    )
    manifest_file = (
        Path(args.manifest_file).expanduser()
        if str(args.manifest_file).strip()
        else (target_ops_dir / ".hardflow-sync-manifest.json")
    )
    workflow_repo_path = Path(args.workflow_repo_path).expanduser()

    jobs_result = plan_jobs_uninstall(jobs_file, str(args.profile))
    runtime_result = plan_runtime_config_uninstall(runtime_config, workflow_repo_path)
    ops_result = plan_ops_manifest_uninstall(target_ops_dir, manifest_file)

    result = {
        "ok": bool(jobs_result.get("ok")) and bool(runtime_result.get("ok")) and bool(ops_result.get("ok")),
        "dry_run": bool(args.dry_run),
        "profile": str(args.profile),
        "jobs": jobs_result,
        "runtime_config": runtime_result,
        "ops_files": ops_result,
    }
    result["changed"] = any(
        bool(section.get("changed"))
        for section in (jobs_result, runtime_result, ops_result)
    )

    if result["ok"] and result["changed"]:
        apply_jobs_uninstall(jobs_result, bool(args.dry_run))
        apply_runtime_config_uninstall(runtime_result, bool(args.dry_run))
        apply_ops_manifest_uninstall(ops_result, bool(args.dry_run))

    for section in (jobs_result, runtime_result, ops_result):
        section.pop("_planned_payload", None)

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ok={str(result['ok']).lower()}")
        print(f"changed={str(result['changed']).lower()}")
        print(f"profile={result['profile']}")
        print(f"jobs_removed={jobs_result.get('removed_count', 0)}")
        print(f"runtime_config_changed={str(bool(runtime_result.get('changed'))).lower()}")
        print(f"ops_files_deleted={ops_result.get('deleted_count', 0)}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

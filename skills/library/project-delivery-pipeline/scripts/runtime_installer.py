#!/usr/bin/env python3
"""Install the project delivery pipeline into a configurable runtime home."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


UTC = timezone.utc
MANIFEST_SCHEMA = "2026-04-24.project-delivery-runtime-install"
ROLLBACK_SCHEMA = "2026-08-14.project-delivery-runtime-rollback"
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".git", ".venv", "venv", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}
REQUIRED_SKILLS = (
    "project-delivery-pipeline",
    "control-plane-ops",
    "todo-patrol",
    "log-monitor",
    "task-cost-analytics",
)
OPS_SCRIPT_MAP = {
    "pipeline_runner.py": "skills/library/project-delivery-pipeline/scripts/pipeline_runner.py",
    "project_delivery_pipeline.py": "skills/library/project-delivery-pipeline/scripts/pipeline_runner.py",
    "hermes_profile_smoke.py": "skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py",
    "todo_patrol.py": "skills/library/todo-patrol/scripts/todo_patrol.py",
    "daily_todo_digest.py": "skills/library/todo-patrol/scripts/daily_todo_digest.py",
    "todo_deadline_checker.py": "skills/library/todo-patrol/scripts/todo_deadline_checker.py",
    "deadline_to_task_bridge.py": "skills/library/todo-patrol/scripts/deadline_to_task_bridge.py",
    "unified_exception_logger.py": "skills/library/log-monitor/scripts/unified_exception_logger.py",
    "exception_to_task_bridge.py": "skills/library/log-monitor/scripts/exception_to_task_bridge.py",
    "runtime_profile_healthcheck.py": "skills/library/log-monitor/scripts/runtime_profile_healthcheck.py",
    "claim_verification_auditor.py": "skills/library/openclaw-security-audit/scripts/claim_verification_auditor.py",
    "config_watchdog.py": "skills/library/config-watchdog/scripts/config_watchdog.py",
    "source_registry_watcher.py": "scripts/openclaw-ops/source_registry_watcher.py",
    "repo_hygiene_reviewer.py": "scripts/openclaw-ops/repo_hygiene_reviewer.py",
    "backlog_runner.py": "scripts/openclaw-ops/backlog_runner.py",
    "project_memory_writer.py": "scripts/openclaw-ops/project_memory_writer.py",
    "project_memory_injector.py": "scripts/openclaw-ops/project_memory_injector.py",
    "live_runtime_bridge.py": "scripts/openclaw-ops/live_runtime_bridge.py",
    "project_pipeline_entry.py": "scripts/openclaw-ops/project_pipeline_entry.py",
}
OPS_SHARED_SCRIPT_MAP = {
    "chat_output.py": "scripts/openclaw-ops/shared/chat_output.py",
    "utf8_runtime.py": "scripts/openclaw-ops/shared/utf8_runtime.py",
    "repo_imports.py": "scripts/openclaw-ops/shared/repo_imports.py",
    "workflow_views.py": "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
}


@dataclass(frozen=True)
class InstallConfig:
    runtime_home: Path
    runtime_name: str
    repo_root: Path
    skills_dir: Path
    ops_dir: Path
    cron_file: Path
    state_dir: Path
    project_memory_dir: Path
    task_center_db: Path
    job_names: tuple[str, ...] = ()
    dry_run: bool = False
    keep_placeholders: bool = False
    runtime_home_expr: str = ""
    repo_root_expr: str = ""
    notification_channel: str = ""
    notification_target: str = ""
    timezone: str = "UTC"


@dataclass
class InstallReport:
    ok: bool = True
    mode: str = "install"
    dry_run: bool = False
    runtime_name: str = ""
    runtime_home: str = ""
    changed: bool = False
    installed_skills: list[str] = field(default_factory=list)
    installed_ops_scripts: list[str] = field(default_factory=list)
    installed_policy_files: list[str] = field(default_factory=list)
    installed_cron_jobs: list[str] = field(default_factory=list)
    preserved_cron_jobs: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    manifest_file: str = ""
    rollback_snapshot: str = ""
    rolled_back: bool = False
    restored_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "runtime_name": self.runtime_name,
            "runtime_home": self.runtime_home,
            "changed": self.changed,
            "installed_skills": self.installed_skills,
            "installed_ops_scripts": self.installed_ops_scripts,
            "installed_policy_files": self.installed_policy_files,
            "installed_cron_jobs": self.installed_cron_jobs,
            "preserved_cron_jobs": self.preserved_cron_jobs,
            "missing_sources": self.missing_sources,
            "manifest_file": self.manifest_file,
            "rollback_snapshot": self.rollback_snapshot,
            "rolled_back": self.rolled_back,
            "restored_files": self.restored_files,
            "removed_files": self.removed_files,
            "errors": self.errors,
        }


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "skills" / "library" / "project-delivery-pipeline").exists():
            return candidate
    raise RuntimeError(f"repo root not found from {start}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip(path: Path) -> bool:
    if path.name == "file_write_audit.jsonl":
        return True
    return path.name in SKIP_DIRS or path.suffix.lower() in SKIP_SUFFIXES or path.name.endswith("~")


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for cur, dirs, files in os.walk(root):
        cur_path = Path(cur)
        dirs[:] = [d for d in dirs if not should_skip(cur_path / d)]
        for name in files:
            path = cur_path / name
            if not should_skip(path):
                out.append(path)
    return sorted(out)


def copy_file(src: Path, dst: Path, *, dry_run: bool) -> bool:
    if not src.exists() or not src.is_file():
        return False
    changed = True
    if dst.exists() and dst.is_file():
        changed = sha256_file(src) != sha256_file(dst)
    if changed and not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return changed


def ensure_executable(path: Path, *, dry_run: bool) -> bool:
    # Windows does not persist POSIX execute bits; repeatedly chmod-ing there
    # makes every identical installation look changed.
    if os.name == "nt" or not path.exists():
        return False
    mode = path.stat().st_mode
    wanted = mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if wanted == mode:
        return False
    if not dry_run:
        path.chmod(wanted)
    return True


def copy_tree(src: Path, dst: Path, *, dry_run: bool) -> tuple[bool, list[str]]:
    changed = False
    managed: list[str] = []
    for path in iter_files(src):
        rel = path.relative_to(src)
        target = dst / rel
        managed.append(str(rel).replace("\\", "/"))
        if copy_file(path, target, dry_run=dry_run):
            changed = True
    return changed, managed


def json_payload_changed(path: Path, payload: dict[str, Any]) -> bool:
    """Compare generated JSON while ignoring its audit timestamp."""

    if not path.exists():
        return True
    try:
        current = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(current, dict):
        return True
    current_without_timestamp = dict(current)
    current_without_timestamp.pop("generated_at", None)
    return current_without_timestamp != payload


def timestamped_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Insert a fresh timestamp only when a semantic write is needed."""

    out = dict(payload)
    out["generated_at"] = utc_now()
    return out


def load_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return [job for job in jobs if isinstance(job, dict)]


def job_key(job: dict[str, Any]) -> str:
    return str(job.get("name") or job.get("id") or "").strip()


def normalize_runtime_path(path: Path) -> str:
    return str(path.expanduser()).replace("\\", "/")


def render_message(text: str, config: InstallConfig) -> str:
    if config.keep_placeholders:
        return text
    runtime_expr = config.runtime_home_expr or normalize_runtime_path(config.runtime_home)
    repo_expr = config.repo_root_expr or normalize_runtime_path(config.repo_root)
    rendered = str(text)
    rendered = rendered.replace("${HARDFLOW_RUNTIME_HOME:-$HOME/.hardflow-runtime}", runtime_expr)
    rendered = rendered.replace("${HARDFLOW_RUNTIME_HOME:-$HOME/.openclaw}", runtime_expr)
    rendered = rendered.replace("${HARDFLOW_WORKFLOW_REPO:-$HOME/workflow-infra}", repo_expr)
    rendered = rendered.replace("${OPENCLAW_WORKFLOW_REPO:-$HOME/workflow-infra}", repo_expr)
    rendered = rendered.replace("${HARDFLOW_NOTIFICATION_CHANNEL}", config.notification_channel)
    rendered = rendered.replace("${HARDFLOW_NOTIFICATION_TARGET}", config.notification_target)
    rendered = rendered.replace("${HARDFLOW_TIMEZONE}", config.timezone or "UTC")
    return rendered


def render_value(value: Any, config: InstallConfig) -> Any:
    if isinstance(value, str):
        return render_message(value, config)
    if isinstance(value, list):
        return [render_value(item, config) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, config) for key, item in value.items()}
    return value


def render_job(job: dict[str, Any], config: InstallConfig) -> dict[str, Any]:
    rendered = render_value(json.loads(json.dumps(job, ensure_ascii=False)), config)
    if not config.keep_placeholders and not (
        config.notification_channel.strip() and config.notification_target.strip()
    ):
        rendered.pop("delivery", None)
        rendered.pop("failureAlert", None)
    return rendered


def merge_cron_jobs(config: InstallConfig, report: InstallReport) -> bool:
    source_file = config.repo_root / "cron" / "jobs.json"
    source_jobs = load_jobs(source_file)
    wanted = {name.strip() for name in config.job_names if name.strip()}
    if wanted:
        source_jobs = [job for job in source_jobs if job_key(job) in wanted]

    existing_jobs = load_jobs(config.cron_file)
    existing_by_key = {job_key(job): job for job in existing_jobs if job_key(job)}
    source_by_key = {job_key(job): render_job(job, config) for job in source_jobs if job_key(job)}
    merged_keys = list(existing_by_key)
    for key in source_by_key:
        if key not in existing_by_key:
            merged_keys.append(key)

    merged_jobs = [
        source_by_key[key] if key in source_by_key else existing_by_key[key]
        for key in merged_keys
        if key in existing_by_key or key in source_by_key
    ]
    payload = {
        "version": "project-delivery-runtime",
        "runtime_name": config.runtime_name,
        "jobs": merged_jobs,
    }
    changed = json_payload_changed(config.cron_file, payload)
    if changed and not config.dry_run:
        config.cron_file.parent.mkdir(parents=True, exist_ok=True)
        config.cron_file.write_text(
            json.dumps(timestamped_payload(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    report.installed_cron_jobs = sorted(source_by_key)
    report.preserved_cron_jobs = sorted(set(existing_by_key) - set(source_by_key))
    return changed


def manifest_path(config: InstallConfig) -> Path:
    return config.ops_dir / "install" / "project-delivery-runtime-install.json"


def allowed_target_roots(config: InstallConfig) -> tuple[Path, ...]:
    roots = (
        config.runtime_home,
        config.skills_dir,
        config.ops_dir,
        config.cron_file.parent,
        config.state_dir,
        config.project_memory_dir,
        config.task_center_db.parent,
    )
    return tuple(dict.fromkeys(path.expanduser().resolve(strict=False) for path in roots))


def checked_target(config: InstallConfig, path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise RuntimeError(f"managed target must not be a symbolic link: {expanded}")
    target = expanded.resolve(strict=False)
    if not any(target == root or target.is_relative_to(root) for root in allowed_target_roots(config)):
        raise RuntimeError(f"managed target is outside configured runtime roots: {target}")
    return target


def managed_target_paths(config: InstallConfig) -> list[Path]:
    targets: list[Path] = []
    for skill_name in REQUIRED_SKILLS:
        src = config.repo_root / "skills" / "library" / skill_name
        if src.exists():
            targets.extend(config.skills_dir / skill_name / path.relative_to(src) for path in iter_files(src))

    for dst_name, rel_src in (*OPS_SCRIPT_MAP.items(), *OPS_SHARED_SCRIPT_MAP.items()):
        if (config.repo_root / rel_src).is_file():
            targets.append(config.ops_dir / dst_name)

    policy_src = config.repo_root / "skills" / "library" / "control-plane-ops" / "scripts" / "policy"
    if policy_src.exists():
        targets.extend(config.ops_dir / "policy" / path.relative_to(policy_src) for path in iter_files(policy_src))

    targets.extend((config.cron_file, manifest_path(config)))
    checked = [checked_target(config, path) for path in targets]
    unique = {str(path): path for path in checked}
    return [unique[key] for key in sorted(unique)]


def current_rollback_snapshot(config: InstallConfig) -> str:
    path = manifest_path(config)
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("rollback_snapshot") or "").strip()


def create_rollback_snapshot(config: InstallConfig) -> Path:
    backup_root = config.runtime_home / ".workflow" / "install-backups"
    snapshot_id = f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    snapshot_dir = backup_root / snapshot_id
    files_dir = snapshot_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, Any]] = []
    for index, target in enumerate(managed_target_paths(config)):
        if target.exists() and not target.is_file():
            raise RuntimeError(f"managed target must be a regular file: {target}")
        existed = target.is_file()
        backup_rel = ""
        if existed:
            backup_rel = f"files/{index:06d}"
            shutil.copy2(target, snapshot_dir / backup_rel)
        entries.append(
            {
                "target": str(target),
                "existed": existed,
                "backup": backup_rel,
            }
        )

    payload = {
        "schema_version": ROLLBACK_SCHEMA,
        "created_at": utc_now(),
        "runtime_name": config.runtime_name,
        "entries": entries,
    }
    (snapshot_dir / "snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot_dir


def write_manifest(config: InstallConfig, report: InstallReport) -> bool:
    manifest_file = manifest_path(config)
    report.manifest_file = str(manifest_file)
    payload = {
        "schema_version": MANIFEST_SCHEMA,
        "runtime_name": config.runtime_name,
        "runtime_home": str(config.runtime_home),
        "repo_root": str(config.repo_root),
        "skills_dir": str(config.skills_dir),
        "ops_dir": str(config.ops_dir),
        "cron_file": str(config.cron_file),
        "state_dir": str(config.state_dir),
        "project_memory_dir": str(config.project_memory_dir),
        "task_center_db": str(config.task_center_db),
        "installed_skills": report.installed_skills,
        "installed_ops_scripts": report.installed_ops_scripts,
        "installed_policy_files": report.installed_policy_files,
        "installed_cron_jobs": report.installed_cron_jobs,
        "missing_sources": report.missing_sources,
        "rollback_snapshot": report.rollback_snapshot,
    }
    changed = json_payload_changed(manifest_file, payload)
    if changed and not config.dry_run:
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(
            json.dumps(timestamped_payload(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def _install_runtime_once(config: InstallConfig, *, rollback_snapshot: str) -> InstallReport:
    report = InstallReport(
        dry_run=config.dry_run,
        runtime_name=config.runtime_name,
        runtime_home=str(config.runtime_home),
        rollback_snapshot=rollback_snapshot,
    )

    for path in (config.skills_dir, config.ops_dir, config.cron_file.parent, config.state_dir, config.project_memory_dir, config.task_center_db.parent):
        if not config.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    for skill_name in REQUIRED_SKILLS:
        src = config.repo_root / "skills" / "library" / skill_name
        dst = config.skills_dir / skill_name
        if not src.exists():
            report.missing_sources.append(str(src))
            continue
        changed, _ = copy_tree(src, dst, dry_run=config.dry_run)
        report.changed = report.changed or changed
        report.installed_skills.append(skill_name)

    for dst_name, rel_src in OPS_SCRIPT_MAP.items():
        src = config.repo_root / rel_src
        dst = config.ops_dir / dst_name
        if not src.exists():
            report.missing_sources.append(str(src))
            continue
        if copy_file(src, dst, dry_run=config.dry_run):
            report.changed = True
        if ensure_executable(dst, dry_run=config.dry_run):
            report.changed = True
        report.installed_ops_scripts.append(dst_name)

    for dst_name, rel_src in OPS_SHARED_SCRIPT_MAP.items():
        src = config.repo_root / rel_src
        dst = config.ops_dir / dst_name
        if not src.exists():
            report.missing_sources.append(str(src))
            continue
        if copy_file(src, dst, dry_run=config.dry_run):
            report.changed = True
        report.installed_ops_scripts.append(dst_name)

    policy_src = config.repo_root / "skills" / "library" / "control-plane-ops" / "scripts" / "policy"
    policy_dst = config.ops_dir / "policy"
    if policy_src.exists():
        changed, copied = copy_tree(policy_src, policy_dst, dry_run=config.dry_run)
        report.changed = report.changed or changed
        report.installed_policy_files = copied
    else:
        report.missing_sources.append(str(policy_src))

    if merge_cron_jobs(config, report):
        report.changed = True

    if write_manifest(config, report):
        report.changed = True

    report.ok = len(report.missing_sources) == 0
    return report


def install_runtime(config: InstallConfig) -> InstallReport:
    previous_snapshot = current_rollback_snapshot(config)
    if config.dry_run:
        return _install_runtime_once(config, rollback_snapshot=previous_snapshot)

    preflight = _install_runtime_once(replace(config, dry_run=True), rollback_snapshot=previous_snapshot)
    if not preflight.changed:
        return _install_runtime_once(config, rollback_snapshot=previous_snapshot)

    snapshot = create_rollback_snapshot(config)
    return _install_runtime_once(config, rollback_snapshot=str(snapshot.resolve()))


def rollback_runtime(config: InstallConfig) -> InstallReport:
    report = InstallReport(
        mode="rollback",
        dry_run=config.dry_run,
        runtime_name=config.runtime_name,
        runtime_home=str(config.runtime_home),
        manifest_file=str(manifest_path(config)),
    )
    manifest_file = manifest_path(config)
    if not manifest_file.is_file():
        report.ok = False
        report.errors.append(f"install manifest not found: {manifest_file}")
        return report

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict):
            raise RuntimeError("install manifest must contain a JSON object")
        if manifest.get("schema_version") != MANIFEST_SCHEMA:
            raise RuntimeError(f"unsupported install manifest schema: {manifest.get('schema_version')}")
        snapshot_text = str(manifest.get("rollback_snapshot") or "").strip()
        if not snapshot_text:
            raise RuntimeError("install manifest has no rollback snapshot")

        backup_root = (config.runtime_home / ".workflow" / "install-backups").resolve(strict=False)
        snapshot_dir = Path(snapshot_text).expanduser().resolve(strict=False)
        if snapshot_dir == backup_root or not snapshot_dir.is_relative_to(backup_root):
            raise RuntimeError(f"rollback snapshot is outside the configured backup root: {snapshot_dir}")
        snapshot_file = snapshot_dir / "snapshot.json"
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8-sig"))
        if not isinstance(snapshot, dict):
            raise RuntimeError("rollback snapshot must contain a JSON object")
        if snapshot.get("schema_version") != ROLLBACK_SCHEMA:
            raise RuntimeError(f"unsupported rollback snapshot schema: {snapshot.get('schema_version')}")
        if str(snapshot.get("runtime_name") or "") != config.runtime_name:
            raise RuntimeError("rollback snapshot runtime name does not match the configured runtime")

        validated: list[tuple[Path, bool, Path | None]] = []
        for raw_entry in snapshot.get("entries", []):
            if not isinstance(raw_entry, dict):
                raise RuntimeError("rollback snapshot contains an invalid entry")
            target = checked_target(config, Path(str(raw_entry.get("target") or "")))
            existed = raw_entry.get("existed") is True
            backup: Path | None = None
            if existed:
                backup_rel = str(raw_entry.get("backup") or "").strip()
                backup = (snapshot_dir / backup_rel).resolve(strict=False)
                if backup == snapshot_dir or not backup.is_relative_to(snapshot_dir) or not backup.is_file():
                    raise RuntimeError(f"rollback backup is missing or outside snapshot: {backup}")
            elif target.exists() and not target.is_file():
                raise RuntimeError(f"rollback target must be a regular file: {target}")
            validated.append((target, existed, backup))

        report.rollback_snapshot = str(snapshot_dir)
        for target, existed, backup in validated:
            if existed:
                assert backup is not None
                changed = not target.is_file() or sha256_file(target) != sha256_file(backup)
                report.changed = report.changed or changed
                report.restored_files.append(str(target))
                if not config.dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
            elif target.is_file():
                report.changed = True
                report.removed_files.append(str(target))
                if not config.dry_run:
                    target.unlink()
        report.rolled_back = not config.dry_run
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        report.ok = False
        report.errors.append(str(exc))
    return report


def derive_runtime_name(runtime_home: Path) -> str:
    name = runtime_home.name.strip().lstrip(".")
    return name or "hardflow-runtime"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or roll back project-delivery-pipeline in any runtime home")
    parser.add_argument(
        "mode",
        nargs="?",
        default="install",
        choices=["install", "setup", "init", "rollback"],
        help="install aliases or restore the state before the latest changed install",
    )
    parser.add_argument("--runtime-home", default=os.environ.get("HARDFLOW_RUNTIME_HOME", ""))
    parser.add_argument("--runtime-name", default="")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--skills-dir", default="")
    parser.add_argument("--ops-dir", default="")
    parser.add_argument("--cron-file", default="")
    parser.add_argument("--state-dir", default="")
    parser.add_argument("--project-memory-dir", default="")
    parser.add_argument("--task-center-db", default="")
    parser.add_argument("--job-name", action="append", default=[], help="install only selected cron job names")
    parser.add_argument("--keep-placeholders", action="store_true")
    parser.add_argument("--runtime-home-expr", default="", help="string used when rendering cron payloads")
    parser.add_argument("--repo-root-expr", default="", help="string used when rendering cron payloads")
    parser.add_argument("--notification-channel", default=os.environ.get("HARDFLOW_NOTIFICATION_CHANNEL", ""))
    parser.add_argument("--notification-target", default=os.environ.get("HARDFLOW_NOTIFICATION_TARGET", ""))
    parser.add_argument("--timezone", default=os.environ.get("HARDFLOW_TIMEZONE", "UTC"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> InstallConfig:
    repo_root = Path(args.repo_root).expanduser() if str(args.repo_root).strip() else find_repo_root(Path(__file__))
    runtime_home = Path(args.runtime_home).expanduser() if str(args.runtime_home).strip() else Path.home() / ".hardflow-runtime"
    runtime_name = str(args.runtime_name).strip() or derive_runtime_name(runtime_home)
    skills_dir = Path(args.skills_dir).expanduser() if str(args.skills_dir).strip() else runtime_home / "skills"
    ops_dir = Path(args.ops_dir).expanduser() if str(args.ops_dir).strip() else runtime_home / "ops"
    cron_file = Path(args.cron_file).expanduser() if str(args.cron_file).strip() else runtime_home / "cron" / "jobs.json"
    state_dir = Path(args.state_dir).expanduser() if str(args.state_dir).strip() else runtime_home / ".workflow" / "pipeline-runs"
    project_memory_dir = (
        Path(args.project_memory_dir).expanduser()
        if str(args.project_memory_dir).strip()
        else runtime_home / ".workflow" / "project-memory"
    )
    task_center_db = (
        Path(args.task_center_db).expanduser()
        if str(args.task_center_db).strip()
        else runtime_home / "ops" / "task-center" / "task_center.db"
    )
    return InstallConfig(
        runtime_home=runtime_home,
        runtime_name=runtime_name,
        repo_root=repo_root,
        skills_dir=skills_dir,
        ops_dir=ops_dir,
        cron_file=cron_file,
        state_dir=state_dir,
        project_memory_dir=project_memory_dir,
        task_center_db=task_center_db,
        job_names=tuple(args.job_name or ()),
        dry_run=bool(args.dry_run),
        keep_placeholders=bool(args.keep_placeholders),
        runtime_home_expr=str(args.runtime_home_expr).strip(),
        repo_root_expr=str(args.repo_root_expr).strip(),
        notification_channel=str(args.notification_channel).strip(),
        notification_target=str(args.notification_target).strip(),
        timezone=str(args.timezone).strip() or "UTC",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    report = rollback_runtime(config) if args.mode == "rollback" else install_runtime(config)
    payload = report.as_dict()
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"runtime_name={payload['runtime_name']}")
        print(f"runtime_home={payload['runtime_home']}")
        print(f"mode={payload['mode']}")
        print(f"changed={payload['changed']}")
        print(f"installed_skills={len(payload['installed_skills'])}")
        print(f"installed_ops_scripts={len(payload['installed_ops_scripts'])}")
        print(f"installed_cron_jobs={len(payload['installed_cron_jobs'])}")
        if payload["missing_sources"]:
            print("missing_sources:")
            for item in payload["missing_sources"]:
                print(f"- {item}")
        if payload["rollback_snapshot"]:
            print(f"rollback_snapshot={payload['rollback_snapshot']}")
        if payload["errors"]:
            print("errors:")
            for item in payload["errors"]:
                print(f"- {item}")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

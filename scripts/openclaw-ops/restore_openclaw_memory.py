#!/usr/bin/env python3
"""Restore project-bound OpenClaw memory files into the runtime workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def should_skip_file(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return path.name.endswith("~")


def normalize_relpath(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def resolve_workspace(openclaw_home: Path, explicit_workspace: Path | None) -> Path:
    if explicit_workspace is not None:
        return explicit_workspace.expanduser()

    cfg_file = openclaw_home / "openclaw.json"
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            agents = data.get("agents", {})
            if isinstance(agents, dict):
                defaults = agents.get("defaults", {})
                if isinstance(defaults, dict):
                    value = defaults.get("workspace")
                    if isinstance(value, str) and value.strip():
                        return Path(value.strip()).expanduser()
                items = agents.get("list", [])
                if isinstance(items, list):
                    main_item: dict[str, Any] | None = None
                    for item in items:
                        if isinstance(item, dict) and item.get("default") is True:
                            main_item = item
                            break
                    if main_item is None:
                        for item in items:
                            if isinstance(item, dict) and str(item.get("id", "")).strip() == "main":
                                main_item = item
                                break
                    if isinstance(main_item, dict):
                        value = main_item.get("workspace")
                        if isinstance(value, str) and value.strip():
                            return Path(value.strip()).expanduser()
    return (openclaw_home / "workspace").expanduser()


def find_source_dir(project_root: Path, source_dirname: str, allow_legacy_source: bool) -> Path | None:
    candidates = [project_root / source_dirname]
    if allow_legacy_source:
        legacy = project_root / ".workflow" / "openclaw-memory"
        if legacy not in candidates:
            candidates.append(legacy)
    for item in candidates:
        if item.exists() and item.is_dir():
            return item
    return None


def iter_memory_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    memory_md = source_dir / "MEMORY.md"
    if memory_md.exists() and memory_md.is_file() and (not should_skip_file(memory_md)):
        files.append(memory_md)

    memory_dir = source_dir / "memory"
    if memory_dir.exists() and memory_dir.is_dir():
        for cur, dirs, names in os.walk(memory_dir):
            cur_path = Path(cur)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                full = cur_path / name
                if should_skip_file(full):
                    continue
                files.append(full)

    return sorted(files)


def sync_memory_files(
    source_dir: Path,
    workspace: Path,
    dry_run: bool,
    check_only: bool,
) -> dict[str, Any]:
    source_files = iter_memory_files(source_dir)
    if not source_files:
        return {
            "ok": True,
            "status": "source_empty",
            "warning": f"memory source is empty: {source_dir}",
            "counts": {
                "source_files": 0,
                "copied": 0,
                "updated": 0,
                "unchanged": 0,
                "would_copy": 0,
                "would_update": 0,
            },
        }

    copied: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    would_copy: list[str] = []
    would_update: list[str] = []

    if not check_only and not dry_run:
        workspace.mkdir(parents=True, exist_ok=True)

    for src in source_files:
        rel = normalize_relpath(str(src.relative_to(source_dir)))
        dst = workspace / rel
        src_hash = sha256_file(src)

        if not dst.exists() or dst.is_dir():
            if check_only or dry_run:
                would_copy.append(rel)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)
            continue

        dst_hash = sha256_file(dst)
        if src_hash != dst_hash:
            if check_only or dry_run:
                would_update.append(rel)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                updated.append(rel)
        else:
            unchanged.append(rel)

    if check_only:
        status = "out_of_sync" if (would_copy or would_update) else "in_sync"
    elif dry_run:
        status = "dry_run_changes" if (would_copy or would_update) else "dry_run_no_change"
    else:
        status = "restored" if (copied or updated) else "up_to_date"

    warning = ""
    if status in {"out_of_sync", "dry_run_changes"}:
        warning = "memory files are not synchronized yet"

    return {
        "ok": True,
        "status": status,
        "warning": warning,
        "counts": {
            "source_files": len(source_files),
            "copied": len(copied),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "would_copy": len(would_copy),
            "would_update": len(would_update),
        },
        "changes": {
            "copied": copied,
            "updated": updated,
            "unchanged": unchanged,
            "would_copy": would_copy,
            "would_update": would_update,
        },
    }


def restore_for_project(
    project_root: Path,
    workspace: Path,
    source_dirname: str,
    allow_legacy_source: bool,
    dry_run: bool,
    check_only: bool,
) -> dict[str, Any]:
    project_root = project_root.expanduser()
    payload: dict[str, Any] = {
        "project_path": str(project_root),
        "workspace": str(workspace),
        "source_dirname": source_dirname,
        "source_dir": "",
        "ok": True,
        "status": "",
        "warning": "",
    }

    if not project_root.exists() or not project_root.is_dir():
        payload["ok"] = False
        payload["status"] = "project_missing"
        payload["error"] = f"project path not found: {project_root}"
        return payload

    source_dir = find_source_dir(project_root, source_dirname, allow_legacy_source=allow_legacy_source)
    if source_dir is None:
        payload["status"] = "source_missing"
        payload["warning"] = (
            f"memory source missing for project: {project_root}. "
            f"expected `{source_dirname}/` (or `.workflow/openclaw-memory/` when legacy is enabled)"
        )
        return payload

    payload["source_dir"] = str(source_dir)
    sync_result = sync_memory_files(
        source_dir=source_dir,
        workspace=workspace,
        dry_run=dry_run,
        check_only=check_only,
    )
    payload.update(sync_result)
    return payload


def build_summary(project_items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "project_count": len(project_items),
        "source_found_projects": 0,
        "restored_projects": 0,
        "up_to_date_projects": 0,
        "warning_projects": 0,
        "error_projects": 0,
        "copied_files": 0,
        "updated_files": 0,
        "would_copy_files": 0,
        "would_update_files": 0,
    }
    warning_statuses = {"source_missing", "source_empty", "out_of_sync", "dry_run_changes"}
    for item in project_items:
        status = str(item.get("status", "")).strip()
        if str(item.get("source_dir", "")).strip():
            summary["source_found_projects"] += 1
        if status in {"restored"}:
            summary["restored_projects"] += 1
        if status in {"up_to_date", "in_sync", "dry_run_no_change"}:
            summary["up_to_date_projects"] += 1
        if status in warning_statuses:
            summary["warning_projects"] += 1
        if item.get("ok") is False:
            summary["error_projects"] += 1
        counts = item.get("counts", {})
        if isinstance(counts, dict):
            summary["copied_files"] += int(counts.get("copied", 0) or 0)
            summary["updated_files"] += int(counts.get("updated", 0) or 0)
            summary["would_copy_files"] += int(counts.get("would_copy", 0) or 0)
            summary["would_update_files"] += int(counts.get("would_update", 0) or 0)
    return summary


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Restore project OpenClaw memory into workspace")
    parser.add_argument("--project-root", action="append", default=[], help="project root path (repeatable)")
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--workspace", default="", help="target workspace path (default from openclaw.json)")
    parser.add_argument("--source-dirname", default="openclaw-memory", help="project memory source directory name")
    parser.add_argument("--disable-legacy-source", action="store_true")
    parser.add_argument("--manifest-file", default="", help="result manifest file path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    project_roots = [Path(x).expanduser() for x in args.project_root if str(x).strip()]
    if not project_roots:
        payload = {"ok": False, "error": "at least one --project-root is required"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    openclaw_home = Path(args.openclaw_home).expanduser()
    explicit_workspace = Path(args.workspace).expanduser() if str(args.workspace).strip() else None
    workspace = resolve_workspace(openclaw_home=openclaw_home, explicit_workspace=explicit_workspace)
    source_dirname = str(args.source_dirname).strip() or "openclaw-memory"
    allow_legacy_source = not bool(args.disable_legacy_source)
    dry_run = bool(args.dry_run)
    check_only = bool(args.check_only)

    items: list[dict[str, Any]] = []
    for project_root in project_roots:
        items.append(
            restore_for_project(
                project_root=project_root,
                workspace=workspace,
                source_dirname=source_dirname,
                allow_legacy_source=allow_legacy_source,
                dry_run=dry_run,
                check_only=check_only,
            )
        )

    warnings: list[str] = []
    for item in items:
        warning = str(item.get("warning", "")).strip()
        if warning:
            warnings.append(warning)

    totals = build_summary(items)
    ok = totals["error_projects"] == 0
    result = {
        "ok": ok,
        "generated_at": now_iso(),
        "openclaw_home": str(openclaw_home),
        "target_workspace": str(workspace),
        "source_dirname": source_dirname,
        "legacy_source_enabled": allow_legacy_source,
        "dry_run": dry_run,
        "check_only": check_only,
        "totals": totals,
        "warnings": warnings,
        "projects": items,
    }

    manifest_file = (
        Path(args.manifest_file).expanduser()
        if str(args.manifest_file).strip()
        else (openclaw_home / "ops" / "memory-restore" / "last-restore.json")
    )
    if not dry_run and not check_only:
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["manifest_file"] = str(manifest_file)

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"target_workspace={result['target_workspace']}")
        print(f"project_count={totals['project_count']}")
        print(f"source_found_projects={totals['source_found_projects']}")
        print(f"restored_projects={totals['restored_projects']}")
        print(f"warning_projects={totals['warning_projects']}")
        print(f"error_projects={totals['error_projects']}")
        print(f"copied_files={totals['copied_files']}")
        print(f"updated_files={totals['updated_files']}")
        if warnings:
            print("warnings:")
            for message in warnings:
                print(f"- {message}")
        if dry_run:
            print("dry_run=true")
        if check_only:
            print("check_only=true")
        print(f"manifest_file={result['manifest_file']}")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

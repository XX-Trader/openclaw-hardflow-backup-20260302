#!/usr/bin/env python3
"""Sync managed runtime plugin override files into OPENCLAW_HOME/extensions."""

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
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_relpath(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def should_skip_file(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return path.name.endswith("~")


def iter_managed_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for cur, dirs, filenames in os.walk(source_dir):
        cur_path = Path(cur)
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for filename in filenames:
            full = cur_path / filename
            if should_skip_file(full):
                continue
            files.append(full)
    return sorted(files)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cleanup_empty_dirs(stop_dir: Path, path: Path) -> None:
    parent = path.parent
    while parent.exists() and parent != stop_dir.parent:
        try:
            parent.rmdir()
        except OSError:
            break
        if parent == stop_dir:
            break
        parent = parent.parent


def sync_plugin_overrides(
    *,
    source_dir: Path,
    target_extensions_dir: Path,
    manifest_file: Path,
    dry_run: bool,
    keep_stale_files: bool,
) -> dict[str, Any]:
    source_dir = source_dir.resolve()
    target_extensions_dir = target_extensions_dir.resolve()

    source_files = iter_managed_files(source_dir)
    source_rel = [normalize_relpath(str(path.relative_to(source_dir))) for path in source_files]
    source_rel_set = set(source_rel)
    source_by_rel = {
        normalize_relpath(str(path.relative_to(source_dir))): path
        for path in source_files
    }

    previous = load_manifest(manifest_file)
    prev_managed = {
        normalize_relpath(str(item))
        for item in (
            previous.get("managed_files", [])
            if isinstance(previous.get("managed_files"), list)
            else []
        )
        if str(item).strip()
    }

    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    deleted: list[str] = []
    managed_plugins = sorted({rel.split("/", 1)[0] for rel in source_rel if rel})

    if not dry_run:
        target_extensions_dir.mkdir(parents=True, exist_ok=True)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)

    for rel in source_rel:
        src = source_by_rel[rel]
        dst = target_extensions_dir / rel
        src_hash = sha256_file(src)

        if not dst.exists():
            added.append(rel)
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            continue

        if dst.is_dir():
            updated.append(rel)
            if not dry_run:
                shutil.rmtree(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            continue

        if sha256_file(dst) != src_hash:
            updated.append(rel)
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        else:
            unchanged.append(rel)

    stale_candidates = sorted(prev_managed - source_rel_set) if not keep_stale_files else []
    for rel in stale_candidates:
        dst = target_extensions_dir / rel
        if not dst.exists():
            deleted.append(rel)
            continue
        deleted.append(rel)
        if not dry_run:
            try:
                dst.unlink()
            except IsADirectoryError:
                shutil.rmtree(dst)
            cleanup_empty_dirs(target_extensions_dir, dst)

    if not dry_run:
        manifest_payload = {
            "schema_version": "2026-03-12",
            "generated_at": now_iso(),
            "source_dir": str(source_dir),
            "target_extensions_dir": str(target_extensions_dir),
            "managed_plugins": managed_plugins,
            "managed_files": sorted(source_rel_set),
            "counts": {
                "added": len(added),
                "updated": len(updated),
                "unchanged": len(unchanged),
                "deleted": len(deleted),
            },
        }
        write_manifest(manifest_file, manifest_payload)

    return {
        "ok": True,
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "source_dir": str(source_dir),
        "target_extensions_dir": str(target_extensions_dir),
        "manifest_file": str(manifest_file),
        "managed_plugins": managed_plugins,
        "counts": {
            "managed_source_files": len(source_rel),
            "previous_managed_files": len(prev_managed),
            "added": len(added),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "deleted": len(deleted),
        },
        "changes": {
            "added": added,
            "updated": updated,
            "deleted": deleted,
        },
        "notes": {
            "keep_stale_files": keep_stale_files,
            "managed_scope": "runtime-plugin-overrides",
            "target_surface": "~/.openclaw/extensions/<plugin-id>/...",
        },
    }


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    home = Path.home()
    parser = argparse.ArgumentParser(description="Sync managed runtime plugin override files")
    parser.add_argument(
        "--source-dir",
        default=str(script_dir / "runtime-plugin-overrides"),
        help="repository runtime-plugin-overrides directory",
    )
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument(
        "--target-extensions-dir",
        default="",
        help="target extensions directory (default: <openclaw-home>/extensions)",
    )
    parser.add_argument(
        "--manifest-file",
        default="",
        help="manifest path (default: <openclaw-home>/ops/.runtime-plugin-overrides-manifest.json)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-stale-files", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser()
    openclaw_home = Path(args.openclaw_home).expanduser()
    target_extensions_dir = (
        Path(args.target_extensions_dir).expanduser()
        if str(args.target_extensions_dir).strip()
        else (openclaw_home / "extensions")
    )
    manifest_file = (
        Path(args.manifest_file).expanduser()
        if str(args.manifest_file).strip()
        else (openclaw_home / "ops" / ".runtime-plugin-overrides-manifest.json")
    )

    if not source_dir.exists() or not source_dir.is_dir():
        payload = {"ok": False, "error": f"source directory not found: {source_dir}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    result = sync_plugin_overrides(
        source_dir=source_dir,
        target_extensions_dir=target_extensions_dir,
        manifest_file=manifest_file,
        dry_run=bool(args.dry_run),
        keep_stale_files=bool(args.keep_stale_files),
    )
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "summary="
            + json.dumps(
                {
                    "ok": result["ok"],
                    "managed_plugins": result["managed_plugins"],
                    "counts": result["counts"],
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

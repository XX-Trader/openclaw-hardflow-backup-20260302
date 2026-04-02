#!/usr/bin/env python3
"""Sync runtime-safe hook files from repository hooks/ into OPENCLAW_HOME runtime hooks dir."""

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
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp", ".ts", ".tsx", ".map"}
ALLOWED_SUFFIXES = {".md", ".json", ".js", ".mjs", ".cjs", ".py", ".sh", ".yaml", ".yml", ".txt"}


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_relpath(path: str) -> str:
    """Normalize a relative path for manifest storage."""
    return path.replace("\\", "/").lstrip("/")


def should_skip_file(path: Path) -> bool:
    """Return whether a file should be excluded from runtime hooks sync."""
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    if path.name.endswith("~"):
        return True
    if path.name == "HOOK.md":
        return False
    return path.suffix.lower() not in ALLOWED_SUFFIXES


def iter_runtime_files(source_dir: Path) -> list[Path]:
    """Return runtime-safe files that may be synced into hooks runtime dir."""
    files: list[Path] = []
    for current_dir, dirs, filenames in os.walk(source_dir):
        current_path = Path(current_dir)
        dirs[:] = [item for item in dirs if item not in SKIP_DIRS]
        for name in filenames:
            full_path = current_path / name
            if should_skip_file(full_path):
                continue
            files.append(full_path)
    return sorted(files)


def should_purge_runtime_file(path: Path) -> bool:
    """Return whether a runtime file should be purged from the target directory."""
    if path.name.endswith("~"):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def purge_blocked_runtime_files(target_dir: Path, dry_run: bool) -> list[str]:
    """Delete legacy blocked runtime files, such as .ts handlers, from the runtime tree."""
    purged: list[str] = []
    if not target_dir.exists():
        return purged

    for current_dir, dirs, filenames in os.walk(target_dir, topdown=False):
        current_path = Path(current_dir)
        for name in filenames:
            full_path = current_path / name
            if not should_purge_runtime_file(full_path):
                continue
            try:
                rel_path = normalize_relpath(str(full_path.relative_to(target_dir)))
            except Exception:
                rel_path = normalize_relpath(str(full_path))
            purged.append(rel_path)
            if not dry_run:
                full_path.unlink(missing_ok=True)
        for dirname in dirs:
            directory_path = current_path / dirname
            if dry_run:
                continue
            try:
                directory_path.rmdir()
            except OSError:
                continue
    return sorted(set(purged))


def load_manifest(path: Path) -> dict[str, Any]:
    """Load the previous sync manifest if present."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sync_files(
    source_dir: Path,
    target_dir: Path,
    manifest_file: Path,
    dry_run: bool,
    keep_stale_files: bool,
) -> dict[str, Any]:
    """Sync runtime-safe hook files into the runtime hooks directory."""
    source_dir = source_dir.resolve()
    target_dir = target_dir.resolve()

    source_files = iter_runtime_files(source_dir)
    source_rel = [normalize_relpath(str(path.relative_to(source_dir))) for path in source_files]
    source_rel_set = set(source_rel)
    source_by_rel = {normalize_relpath(str(path.relative_to(source_dir))): path for path in source_files}

    prev_manifest = load_manifest(manifest_file)
    prev_managed = {
        normalize_relpath(str(item))
        for item in (prev_manifest.get("managed_files", []) if isinstance(prev_manifest.get("managed_files"), list) else [])
        if str(item).strip()
    }

    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    deleted: list[str] = []

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)

    for rel in source_rel:
        src = source_by_rel[rel]
        dst = target_dir / rel
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

        dst_hash = sha256_file(dst)
        if src_hash != dst_hash:
            updated.append(rel)
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        else:
            unchanged.append(rel)

    stale_candidates = sorted(prev_managed - source_rel_set) if not keep_stale_files else []
    for rel in stale_candidates:
        dst = target_dir / rel
        if not dst.exists():
            deleted.append(rel)
            continue
        deleted.append(rel)
        if not dry_run:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()

    purged_blocked = purge_blocked_runtime_files(target_dir, dry_run)

    if not dry_run:
        for rel in sorted(stale_candidates, reverse=True):
            parent = (target_dir / rel).parent
            while parent != target_dir and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

        manifest_payload = {
            "schema_version": "2026-03-20",
            "generated_at": now_iso(),
            "source_dir": str(source_dir),
            "target_hooks_dir": str(target_dir),
            "managed_files": sorted(source_rel_set),
            "counts": {
                "added": len(added),
                "updated": len(updated),
                "unchanged": len(unchanged),
                "deleted": len(deleted),
                "purged_blocked": len(purged_blocked),
            },
            "notes": {
                "managed_scope": "hooks-runtime",
                "runtime_entry_policy": "handler-js-runtime",
                "allowed_suffixes": sorted(ALLOWED_SUFFIXES),
                "blocked_suffixes": sorted(SKIP_SUFFIXES),
            },
        }
        manifest_file.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "source_dir": str(source_dir),
        "target_hooks_dir": str(target_dir),
        "manifest_file": str(manifest_file),
        "counts": {
            "managed_source_files": len(source_rel),
            "previous_managed_files": len(prev_managed),
            "added": len(added),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "deleted": len(deleted),
            "purged_blocked": len(purged_blocked),
        },
        "changes": {
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "purged_blocked": purged_blocked,
        },
        "notes": {
            "managed_scope": "hooks-runtime",
            "runtime_entry_policy": "handler-js-runtime",
            "keep_stale_files": keep_stale_files,
        },
    }


def main() -> int:
    """CLI entrypoint for runtime hooks sync."""
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Sync runtime-safe hooks into OPENCLAW_HOME")
    parser.add_argument("--source-dir", default=str(script_dir.parent.parent / "hooks"), help="repository hooks directory")
    parser.add_argument("--target-hooks-dir", required=True, help="target runtime hooks directory")
    parser.add_argument(
        "--manifest-file",
        default="",
        help="manifest path (default: <target-hooks-dir>/.hardflow-hooks-sync-manifest.json)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-stale-files", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser()
    target_dir = Path(args.target_hooks_dir).expanduser()
    manifest_file = (
        Path(args.manifest_file).expanduser()
        if str(args.manifest_file).strip()
        else (target_dir / ".hardflow-hooks-sync-manifest.json")
    )

    if not source_dir.exists() or not source_dir.is_dir():
        payload = {"ok": False, "error": f"source directory not found: {source_dir}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    result = sync_files(
        source_dir=source_dir,
        target_dir=target_dir,
        manifest_file=manifest_file,
        dry_run=bool(args.dry_run),
        keep_stale_files=bool(args.keep_stale_files),
    )

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"source_dir={result['source_dir']}")
        print(f"target_hooks_dir={result['target_hooks_dir']}")
        print(f"manifest_file={result['manifest_file']}")
        print("managed_scope=hooks-runtime")
        print(json.dumps(result["counts"], ensure_ascii=False))
        if result.get("dry_run"):
            print("dry_run=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

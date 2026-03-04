#!/usr/bin/env python3
"""Sync managed openclaw-ops files from repository into OPENCLAW_HOME/ops."""

from __future__ import annotations

import argparse
import hashlib
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


def iter_managed_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for cur, dirs, filenames in os.walk(source_dir):
        cur_path = Path(cur)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in filenames:
            full = cur_path / name
            if should_skip_file(full):
                continue
            files.append(full)
    return sorted(files)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_relpath(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def sync_files(
    source_dir: Path,
    target_dir: Path,
    manifest_file: Path,
    dry_run: bool,
    keep_stale_files: bool,
) -> dict[str, Any]:
    source_dir = source_dir.resolve()
    target_dir = target_dir.resolve()

    source_files = iter_managed_files(source_dir)
    source_rel = [normalize_relpath(str(p.relative_to(source_dir))) for p in source_files]
    source_rel_set = set(source_rel)
    source_by_rel = {normalize_relpath(str(p.relative_to(source_dir))): p for p in source_files}

    prev_manifest = load_manifest(manifest_file)
    prev_managed = {
        normalize_relpath(str(x))
        for x in (prev_manifest.get("managed_files", []) if isinstance(prev_manifest.get("managed_files"), list) else [])
        if str(x).strip()
    }

    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    deleted: list[str] = []
    moves: list[dict[str, str]] = []

    added_hash_to_rel: dict[str, list[str]] = {}
    deleted_hash_to_rel: dict[str, list[str]] = {}

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)

    for rel in source_rel:
        src = source_by_rel[rel]
        dst = target_dir / rel
        src_hash = sha256_file(src)
        added_hash_to_rel.setdefault(src_hash, []).append(rel)

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
        if dst.is_file():
            deleted_hash_to_rel.setdefault(sha256_file(dst), []).append(rel)
        deleted.append(rel)
        if not dry_run:
            try:
                dst.unlink()
            except IsADirectoryError:
                shutil.rmtree(dst)

    for digest, from_list in deleted_hash_to_rel.items():
        to_list = added_hash_to_rel.get(digest, [])
        if not to_list:
            continue
        pair_count = min(len(from_list), len(to_list))
        for idx in range(pair_count):
            moves.append({"from": from_list[idx], "to": to_list[idx]})

    if not dry_run:
        # Cleanup empty directories created by stale file removal.
        for rel in sorted(stale_candidates, reverse=True):
            parent = (target_dir / rel).parent
            while parent != target_dir and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

        manifest_payload = {
            "schema_version": "2026-03-02",
            "generated_at": now_iso(),
            "source_dir": str(source_dir),
            "target_ops_dir": str(target_dir),
            "managed_files": sorted(source_rel_set),
            "counts": {
                "added": len(added),
                "updated": len(updated),
                "unchanged": len(unchanged),
                "deleted": len(deleted),
                "moved": len(moves),
            },
        }
        write_json_atomic(
            manifest_file,
            manifest_payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )

    return {
        "ok": True,
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "source_dir": str(source_dir),
        "target_ops_dir": str(target_dir),
        "manifest_file": str(manifest_file),
        "counts": {
            "managed_source_files": len(source_rel),
            "previous_managed_files": len(prev_managed),
            "added": len(added),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "deleted": len(deleted),
            "moved": len(moves),
        },
        "changes": {
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "moved": moves,
        },
        "notes": {
            "keep_stale_files": keep_stale_files,
        },
    }


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Sync openclaw-ops files into OPENCLAW_HOME/ops")
    parser.add_argument("--source-dir", default=str(script_dir), help="repository scripts/openclaw-ops directory")
    parser.add_argument("--target-ops-dir", required=True, help="target OPENCLAW_HOME/ops path")
    parser.add_argument(
        "--manifest-file",
        default="",
        help="manifest path (default: <target-ops-dir>/.hardflow-sync-manifest.json)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-stale-files", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser()
    target_dir = Path(args.target_ops_dir).expanduser()
    manifest_file = (
        Path(args.manifest_file).expanduser()
        if str(args.manifest_file).strip()
        else (target_dir / ".hardflow-sync-manifest.json")
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
        print(f"target_ops_dir={result['target_ops_dir']}")
        print(f"manifest_file={result['manifest_file']}")
        print(json.dumps(result["counts"], ensure_ascii=False))
        if result.get("dry_run"):
            print("dry_run=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

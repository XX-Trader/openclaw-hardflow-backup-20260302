#!/usr/bin/env python3
"""Build runtime project registry with local-path adaptation."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from io_write_gateway import write_json_atomic

UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("projects", [])
    else:
        return []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def project_exists(item: dict[str, Any]) -> bool:
    path = Path(str(item.get("path", "")).strip()).expanduser()
    return path.exists() and path.is_dir()


def match_reference(local_item: dict[str, Any], refs: list[dict[str, Any]], used: set[int]) -> tuple[int, dict[str, Any] | None, str]:
    local_id = normalize_text(str(local_item.get("id", "")))
    local_name = normalize_text(str(local_item.get("name", "")))
    local_base = normalize_text(Path(str(local_item.get("path", "")).strip()).name)

    # 1) Match by id.
    if local_id:
        for idx, ref in enumerate(refs):
            if idx in used:
                continue
            if normalize_text(str(ref.get("id", ""))) == local_id:
                return idx, ref, "id"

    # 2) Match by name.
    if local_name:
        for idx, ref in enumerate(refs):
            if idx in used:
                continue
            if normalize_text(str(ref.get("name", ""))) == local_name:
                return idx, ref, "name"

    # 3) Match by path basename.
    if local_base:
        for idx, ref in enumerate(refs):
            if idx in used:
                continue
            ref_path = str(ref.get("path", "")).strip()
            ref_base = normalize_text(Path(ref_path).name) if ref_path else ""
            if ref_base and ref_base == local_base:
                return idx, ref, "path_basename"

    return -1, None, "none"


def merge_with_local_path(local_item: dict[str, Any], ref_item: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(ref_item) if isinstance(ref_item, dict) else {}
    merged.update(local_item)

    # Always keep local path if provided.
    local_path = str(local_item.get("path", "")).strip()
    if local_path:
        merged["path"] = local_path

    # Keep local id/name when available.
    for key in ("id", "name"):
        value = str(local_item.get(key, "")).strip()
        if value:
            merged[key] = value

    # Ensure common fields exist.
    merged.setdefault("index_dir", ".workflow/project-index-local")
    if "auto_pull" not in merged:
        merged["auto_pull"] = True
    merged.setdefault("git_remote", "origin")
    merged.setdefault("git_branch", "main")
    return merged


def make_output(
    *,
    local_projects: list[dict[str, Any]],
    reference_projects: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    valid_local = [item for item in local_projects if project_exists(item)]
    used_ref: set[int] = set()
    runtime_projects: list[dict[str, Any]] = []
    matched: list[dict[str, str]] = []

    for local_item in valid_local:
        idx, ref_item, reason = match_reference(local_item, reference_projects, used_ref)
        if idx >= 0:
            used_ref.add(idx)
        runtime_projects.append(merge_with_local_path(local_item, ref_item))
        matched.append(
            {
                "local_id": str(local_item.get("id", "")),
                "ref_id": str(ref_item.get("id", "")) if isinstance(ref_item, dict) else "",
                "reason": reason,
            }
        )

    unresolved_refs: list[dict[str, Any]] = []
    for idx, item in enumerate(reference_projects):
        if idx in used_ref:
            continue
        unresolved_refs.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "path": str(item.get("path", "")),
            }
        )

    output = {
        "generated_at": now_iso(),
        "generator": "project_registry_runtime.py",
        "projects": runtime_projects,
        "meta": {
            "local_total": len(local_projects),
            "local_valid_paths": len(valid_local),
            "reference_total": len(reference_projects),
            "matched_count": len(matched),
            "unresolved_reference_count": len(unresolved_refs),
            "matched": matched,
            "unresolved_reference_projects": unresolved_refs,
        },
    }

    summary = {
        "project_count": len(runtime_projects),
        "local_total": len(local_projects),
        "local_valid_paths": len(valid_local),
        "reference_total": len(reference_projects),
        "unresolved_reference_count": len(unresolved_refs),
    }
    return output, summary


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Build runtime project registry with local path adaptation")
    parser.add_argument("--local-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--reference-registry", default=str(home / ".openclaw/ops/task-center/project-registry.hangqing.json"))
    parser.add_argument("--output-registry", default=str(home / ".openclaw/ops/task-center/project-registry.runtime.json"))
    parser.add_argument("--require-non-empty", action="store_true", help="exit non-zero when runtime projects is empty")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    local_registry = Path(args.local_registry).expanduser()
    ref_registry = Path(args.reference_registry).expanduser()
    output_registry = Path(args.output_registry).expanduser()

    local_projects = load_registry(local_registry)
    reference_projects = load_registry(ref_registry)

    payload, summary = make_output(local_projects=local_projects, reference_projects=reference_projects)
    write_json_atomic(
        output_registry,
        payload,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )

    result = {
        "ok": (len(payload.get("projects", [])) > 0) or not bool(args.require_non_empty),
        "local_registry": str(local_registry),
        "reference_registry": str(ref_registry),
        "output_registry": str(output_registry),
        "summary": summary,
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

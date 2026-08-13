#!/usr/bin/env python3
"""Build runtime web source lists from static config and project registry."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def repository_root(start: Path) -> Path | None:
    return next(
        (
            parent
            for parent in (start, *start.parents)
            if (parent / "skills" / "library").is_dir() and (parent / "scripts" / "openclaw-ops").is_dir()
        ),
        None,
    )


REPOSITORY_ROOT = repository_root(ROOT)
IMPORT_DIRS = [ROOT, ROOT / "policy"]
if REPOSITORY_ROOT is not None:
    IMPORT_DIRS.extend(
        [
            REPOSITORY_ROOT / "skills" / "library" / "control-plane-ops" / "scripts",
            REPOSITORY_ROOT / "skills" / "library" / "openclaw-workflow-manager" / "scripts",
        ]
    )
for import_dir in reversed(IMPORT_DIRS):
    value = str(import_dir)
    if import_dir.is_dir() and value not in sys.path:
        sys.path.insert(0, value)

from project_registry_discovery import load_project_registry as load_project_registry_runtime
from vendor_source_catalog import (
    DEFAULT_PROJECT_INDEX_DIR,
    LEGACY_PROJECT_INDEX_DIR,
    build_host_repo_sources,
    build_vendor_doc_sources,
    build_vendor_repo_source,
    detect_vendors_from_fragments,
)

PROJECT_HINT_FIELDS = (
    "id",
    "name",
    "description",
    "notes",
    "tags",
    "keywords",
    "integrations",
    "vendors",
    "api_providers",
    "dependencies",
    "api_base_urls",
)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def slugify(text: str, default: str) -> str:
    raw = str(text or "").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-")
    return slug or default


def unique_tags(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value or "").strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def iter_text_fragments(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(iter_text_fragments(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(iter_text_fragments(item))
        return out
    text = str(value or "").strip()
    return [text] if text else []


def normalize_source_entry(item: dict[str, Any], *, default_id: str) -> dict[str, Any] | None:
    url = str(item.get("url", "")).strip()
    if not url:
        return None
    tags_raw = item.get("tags")
    tags = [str(x).strip() for x in tags_raw] if isinstance(tags_raw, list) else []
    tags = unique_tags(tags)
    return {
        "id": slugify(str(item.get("id", "")).strip(), default=default_id),
        "url": url,
        "enabled": bool(item.get("enabled", True)),
        "category": str(item.get("category", "")).strip(),
        "tags": tags,
        "browser_fallback": bool(item.get("browser_fallback", True)),
        "min_interval_minutes": max(1, int(item.get("min_interval_minutes", 60) or 60)),
        "project_id": str(item.get("project_id", "")).strip(),
        "project_name": str(item.get("project_name", "")).strip(),
        "vendor_hint": str(item.get("vendor_hint", "")).strip(),
    }


def load_static_sources(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path, {})
    if isinstance(payload, dict):
        items = payload.get("sources", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        normalized = normalize_source_entry(item, default_id=f"source-{idx+1}")
        if normalized is not None:
            out.append(normalized)
    return out


def load_project_registry(path: Path) -> list[dict[str, Any]]:
    return load_project_registry_runtime(path)


def collect_vendor_hints(project: dict[str, Any]) -> set[str]:
    fragments: list[str] = []
    for field in PROJECT_HINT_FIELDS:
        fragments.extend(iter_text_fragments(project.get(field)))
    return detect_vendors_from_fragments(fragments)


def vendor_monitoring_enabled(project: dict[str, Any]) -> bool:
    cfg = project.get("vendor_monitoring")
    if isinstance(cfg, dict) and "enabled" in cfg:
        return bool(cfg.get("enabled"))
    return True


def normalize_project_doc_source(
    project: dict[str, Any],
    item: dict[str, Any],
    *,
    default_id: str,
) -> dict[str, Any] | None:
    row = dict(item)
    row["project_id"] = str(project.get("id", "")).strip()
    row["project_name"] = str(project.get("name", "")).strip()
    normalized = normalize_source_entry(row, default_id=default_id)
    if normalized is None:
        return None
    tags = normalized.get("tags", [])
    normalized["category"] = normalized.get("category") or "project-doc"
    normalized["tags"] = unique_tags([*tags, "project", "doc"])
    return normalized


def build_project_registry_sources(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    projects = load_project_registry(path)
    out: list[dict[str, Any]] = []
    for project_idx, project in enumerate(projects):
        project_slug = slugify(
            str(project.get("id", "")).strip() or str(project.get("name", "")).strip(),
            default=f"project-{project_idx+1}",
        )

        explicit_sources = project.get("doc_sources", [])
        if isinstance(explicit_sources, list):
            for idx, raw_item in enumerate(explicit_sources):
                item = {"url": raw_item} if isinstance(raw_item, str) else raw_item
                if not isinstance(item, dict):
                    continue
                normalized = normalize_project_doc_source(
                    project,
                    item,
                    default_id=f"{project_slug}-doc-{idx+1}",
                )
                if normalized is not None:
                    out.append(normalized)

        if not vendor_monitoring_enabled(project):
            continue

        for vendor in sorted(collect_vendor_hints(project)):
            for raw_item in build_vendor_doc_sources(vendor):
                item = dict(raw_item)
                item["id"] = f"{project_slug}-{item.get('id', vendor)}"
                item["project_id"] = str(project.get("id", "")).strip()
                item["project_name"] = str(project.get("name", "")).strip()
                item["vendor_hint"] = vendor
                normalized = normalize_source_entry(
                    item,
                    default_id=f"{project_slug}-{vendor}",
                )
                if normalized is None:
                    continue
                normalized["tags"] = unique_tags([*normalized.get("tags", []), "project", vendor])
                out.append(normalized)
    return out


def project_index_dirs(project: dict[str, Any]) -> list[str]:
    configured = str(project.get("index_dir", "")).strip()
    out = [configured] if configured else []
    for candidate in (DEFAULT_PROJECT_INDEX_DIR, LEGACY_PROJECT_INDEX_DIR):
        if candidate not in out:
            out.append(candidate)
    return out


def load_project_doc_knowledge(project: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(project.get("path", "")).strip()
    if not raw_path:
        return {}
    root = Path(raw_path).expanduser()
    for index_dir in project_index_dirs(project):
        path = root / index_dir / "doc-knowledge.json"
        payload = load_json(path, {})
        if isinstance(payload, dict) and payload:
            return payload
    return {}


def build_project_index_sources(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    projects = load_project_registry(path)
    out: list[dict[str, Any]] = []
    for project_idx, project in enumerate(projects):
        project_slug = slugify(
            str(project.get("id", "")).strip() or str(project.get("name", "")).strip(),
            default=f"project-{project_idx+1}",
        )
        payload = load_project_doc_knowledge(project)
        if not vendor_monitoring_enabled(project):
            continue
        items = payload.get("doc_sources", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            continue
        for idx, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                continue
            normalized = normalize_project_doc_source(
                project,
                raw_item,
                default_id=f"{project_slug}-index-doc-{idx+1}",
            )
            if normalized is None:
                continue
            normalized["tags"] = unique_tags([*normalized.get("tags", []), "project", "index"])
            out.append(normalized)
    return out


def normalize_repo_full_name(value: str) -> str:
    text = str(value or "").strip().lower()
    if text.count("/") != 1:
        return ""
    owner, repo = text.split("/", 1)
    if not owner or not repo:
        return ""
    return f"{owner}/{repo}"


def merge_repo_targets(*items: dict[str, Any]) -> dict[str, Any]:
    queries: list[str] = []
    official_repos: list[str] = []
    seen_queries: set[str] = set()
    seen_repos: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for query in item.get("queries", []):
            text = str(query or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen_queries:
                continue
            seen_queries.add(key)
            queries.append(text)
        for repo in item.get("official_repos", []):
            full_name = normalize_repo_full_name(repo)
            if not full_name or full_name in seen_repos:
                continue
            seen_repos.add(full_name)
            official_repos.append(full_name)
    return {"queries": queries, "official_repos": official_repos}


def build_project_repo_targets(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"queries": [], "official_repos": []}
    projects = load_project_registry(path)
    result = {"queries": [], "official_repos": []}
    for project in projects:
        if not vendor_monitoring_enabled(project):
            continue
        for vendor in sorted(collect_vendor_hints(project)):
            row = build_vendor_repo_source(vendor)
            if row is None:
                continue
            result = merge_repo_targets(
                result,
                {
                    "queries": row.get("repo_queries", []),
                    "official_repos": row.get("official_repos", []),
                },
            )
        payload = load_project_doc_knowledge(project)
        repo_sources = payload.get("repo_sources", []) if isinstance(payload, dict) else []
        if not isinstance(repo_sources, list):
            continue
        for item in repo_sources:
            if not isinstance(item, dict):
                continue
            result = merge_repo_targets(
                result,
                {
                    "queries": item.get("repo_queries", []),
                    "official_repos": item.get("official_repos", []),
                },
            )
        external_api_hosts = payload.get("external_api_hosts", []) if isinstance(payload, dict) else []
        if isinstance(external_api_hosts, list):
            for item in build_host_repo_sources([str(x) for x in external_api_hosts]):
                result = merge_repo_targets(
                    result,
                    {
                        "queries": item.get("repo_queries", []),
                        "official_repos": item.get("official_repos", []),
                    },
                )
    return result


def load_project_repo_targets(path: Path | None) -> dict[str, Any]:
    targets = build_project_repo_targets(path)
    return {
        "queries": list(targets.get("queries", [])),
        "official_repos": list(targets.get("official_repos", [])),
    }


def merge_sources(*source_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for group in source_groups:
        for item in group:
            sid = str(item.get("id", "")).strip()
            url = str(item.get("url", "")).strip()
            if not sid or not url:
                continue
            if sid in seen_ids or url in seen_urls:
                continue
            seen_ids.add(sid)
            seen_urls.add(url)
            out.append(item)
    return out


def load_runtime_sources(
    primary_source_file: Path,
    *,
    extra_source_files: list[Path] | None = None,
    project_registry: Path | None = None,
) -> list[dict[str, Any]]:
    source_groups: list[list[dict[str, Any]]] = [load_static_sources(primary_source_file)]
    for path in extra_source_files or []:
        source_groups.append(load_static_sources(path))
    source_groups.append(build_project_registry_sources(project_registry))
    source_groups.append(build_project_index_sources(project_registry))
    return merge_sources(*source_groups)

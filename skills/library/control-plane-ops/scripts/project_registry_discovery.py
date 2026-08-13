#!/usr/bin/env python3
"""Runtime project registry loader with optional git-repo auto discovery."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
DEFAULT_INDEX_DIR = ".workflow/project-index-local"
DEFAULT_MAX_DEPTH = 4
DEFAULT_MAX_PROJECTS = 40
DEFAULT_HEAVY_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", ".cache"}
ALLOWED_HIDDEN_REPO_NAMES = {".openclaw"}
DEFAULT_EXCLUDE_TOKENS = (
    "/.openclaw/skills/",
    "/.openclaw/workspace/skills/",
    "/.openclaw/workspace/plugins/",
    "/.openclaw/workspace-",
    "/.openclaw.backup",
    "/actions-runner/_work/",
    "/.nvm",
)

_CACHE: dict[tuple[str, int], list[dict[str, Any]]] = {}


def slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-")
    return base or "project"


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def registry_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except Exception:
        return -1


def normalize_projects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("projects", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def normalize_repo_path(path: Path) -> str:
    return path.expanduser().resolve().as_posix().lower().rstrip("/")


def collect_default_scan_roots(projects: list[dict[str, Any]]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for item in projects:
        raw = str(item.get("path", "")).strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        parent = path.parent if path.name else path
        key = normalize_repo_path(parent)
        if key in seen:
            continue
        seen.add(key)
        roots.append(parent)
    home_projects = Path.home() / "projects"
    if home_projects.exists():
        key = normalize_repo_path(home_projects)
        if key not in seen:
            seen.add(key)
            roots.append(home_projects)
    if not roots:
        roots.append(Path.home())
    return roots


def parse_discovery_config(payload: Any, projects: list[dict[str, Any]]) -> dict[str, Any]:
    config = payload.get("discovery", {}) if isinstance(payload, dict) else {}
    if not isinstance(config, dict):
        config = {}
    scan_roots_raw = config.get("scan_roots", [])
    scan_roots = [Path(str(x)).expanduser() for x in scan_roots_raw if str(x or "").strip()] if isinstance(scan_roots_raw, list) else []
    if not scan_roots:
        scan_roots = collect_default_scan_roots(projects)
    exclude_tokens = list(DEFAULT_EXCLUDE_TOKENS)
    extra_excludes = config.get("exclude_path_tokens", [])
    if isinstance(extra_excludes, list):
        for item in extra_excludes:
            text = str(item or "").strip()
            if text:
                exclude_tokens.append(text)
    return {
        "enabled": bool(config.get("enabled", True)),
        "scan_roots": scan_roots,
        "max_depth": max(1, int(config.get("max_depth", DEFAULT_MAX_DEPTH) or DEFAULT_MAX_DEPTH)),
        "max_projects": max(1, int(config.get("max_projects", DEFAULT_MAX_PROJECTS) or DEFAULT_MAX_PROJECTS)),
        "exclude_path_tokens": exclude_tokens,
    }


def should_exclude_repo(path: Path, exclude_tokens: list[str]) -> bool:
    if path.name.startswith(".") and path.name not in ALLOWED_HIDDEN_REPO_NAMES:
        return True
    norm = normalize_repo_path(path)
    return any(str(token or "").strip().lower() in norm for token in exclude_tokens if str(token or "").strip())


def has_project_markers(path: Path) -> bool:
    markers = [
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "manage.py",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "Dockerfile",
        "openclaw.json",
    ]
    if any((path / item).exists() for item in markers):
        return True
    if any((path / item).is_dir() for item in ("src", "app", "backend", "frontend", "services")):
        return True
    if (path / "scripts" / "hardflow" / "hardflow-run.sh").exists():
        return True
    return False


def discover_git_repos(
    *,
    scan_roots: list[Path],
    max_depth: int,
    max_projects: int,
    exclude_tokens: list[str],
) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for root in scan_roots:
        if not root.exists() or not root.is_dir():
            continue
        root_abs = root.resolve()
        for cur, dirs, _files in os.walk(root_abs):
            cur_path = Path(cur)
            try:
                rel_depth = len(cur_path.relative_to(root_abs).parts)
            except Exception:
                rel_depth = 0
            if rel_depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in DEFAULT_HEAVY_DIRS]
            git_dir = cur_path / ".git"
            if not (git_dir.is_dir() or git_dir.is_file()):
                continue
            norm = normalize_repo_path(cur_path)
            if norm in seen:
                dirs[:] = []
                continue
            seen.add(norm)
            dirs[:] = []
            if should_exclude_repo(cur_path, exclude_tokens):
                continue
            if not has_project_markers(cur_path):
                continue
            found.append(cur_path)
            if len(found) >= max_projects:
                return sorted(found)
    return sorted(found)


def run_git(path: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def first_clone_metadata(path: Path) -> tuple[str, str]:
    head_log = path / ".git" / "logs" / "HEAD"
    if not head_log.exists():
        return "", ""
    try:
        line = head_log.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except Exception:
        return "", ""
    if "clone:" not in line.lower():
        return "", line[:240]
    match = re.search(r"\s(\d{10})(?:\s[+-]\d{4})?\s+clone:", line)
    if not match:
        return "", line[:240]
    try:
        dt = datetime.fromtimestamp(int(match.group(1)), tz=UTC).replace(microsecond=0)
        return dt.isoformat(), line[:240]
    except Exception:
        return "", line[:240]


def infer_project_role(*, path: Path, name: str, remote_url: str) -> str:
    norm = normalize_repo_path(path)
    low_remote = str(remote_url or "").strip().lower()
    if norm.endswith("/.openclaw") or "/.openclaw/" in norm:
        return "openclaw-runtime"
    if (
        (path / "setup.py").is_file()
        and (path / "skills" / "library" / "project-delivery-pipeline").is_dir()
    ):
        return "workflow-ops"
    if low_remote.startswith("https://github.com/openclaw/") or low_remote.startswith("git@github.com:openclaw/"):
        return "upstream-reference"
    return "business"


def vendor_monitoring_default_enabled(role: str) -> bool:
    return str(role or "").strip().lower() == "business"


def decorate_project_item(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    raw_path = str(row.get("path", "")).strip()
    if not raw_path:
        return row
    path = Path(raw_path).expanduser().resolve()
    discovery = row.get("discovery")
    discovery_row = dict(discovery) if isinstance(discovery, dict) else {}
    remote_url = str(discovery_row.get("remote_url", "")).strip()
    if not remote_url and (path / ".git").exists():
        remote_url = run_git(path, ["remote", "get-url", "origin"])
    clone_at = str(discovery_row.get("clone_at", "")).strip()
    clone_hint = str(discovery_row.get("clone_hint", "")).strip()
    if (not clone_at) or (not clone_hint):
        detected_clone_at, detected_clone_hint = first_clone_metadata(path)
        clone_at = clone_at or detected_clone_at
        clone_hint = clone_hint or detected_clone_hint
    role = str(row.get("project_role", "")).strip() or infer_project_role(
        path=path,
        name=str(row.get("name", "")).strip() or path.name,
        remote_url=remote_url,
    )
    vendor_monitoring = row.get("vendor_monitoring")
    vendor_row = dict(vendor_monitoring) if isinstance(vendor_monitoring, dict) else {}
    if "enabled" not in vendor_row:
        vendor_row["enabled"] = vendor_monitoring_default_enabled(role)
    vendor_row["reason"] = str(vendor_row.get("reason", "")).strip() or f"default:{role}"
    discovery_row["remote_url"] = remote_url
    discovery_row["clone_at"] = clone_at
    discovery_row["clone_hint"] = clone_hint
    row["path"] = str(path)
    row["project_role"] = role
    row["vendor_monitoring"] = vendor_row
    if discovery_row:
        row["discovery"] = discovery_row
    return row


def build_discovered_project_item(path: Path) -> dict[str, Any]:
    remote = run_git(path, ["remote", "get-url", "origin"])
    branch = run_git(path, ["branch", "--show-current"]) or "main"
    clone_at, clone_hint = first_clone_metadata(path)
    return decorate_project_item(
        {
        "id": slugify(path.name),
        "name": path.name,
        "path": str(path.resolve()),
        "index_dir": DEFAULT_INDEX_DIR,
        "auto_pull": bool(remote),
        "git_remote": "origin",
        "git_branch": branch or "main",
        "discovery": {
            "source": "auto-discovery",
            "detected_at": now_iso(),
            "remote_url": remote,
            "clone_at": clone_at,
            "clone_hint": clone_hint,
        },
    }
    )


def merge_projects(explicit_projects: list[dict[str, Any]], discovered_paths: list[Path]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in explicit_projects:
        raw = str(item.get("path", "")).strip()
        if not raw:
            continue
        merged[normalize_repo_path(Path(raw))] = decorate_project_item(item)
    for path in discovered_paths:
        key = normalize_repo_path(path)
        if key in merged:
            continue
        merged[key] = build_discovered_project_item(path)
    return sorted(merged.values(), key=lambda item: str(item.get("name", "")).lower())


def load_project_registry(path: Path) -> list[dict[str, Any]]:
    key = (str(path.expanduser().resolve()), registry_mtime_ns(path.expanduser()))
    cached = _CACHE.get(key)
    if cached is not None:
        return [dict(item) for item in cached]
    payload = load_json(path, {})
    explicit_projects = normalize_projects(payload)
    config = parse_discovery_config(payload, explicit_projects)
    projects = [decorate_project_item(item) for item in explicit_projects]
    if config.get("enabled", False):
        discovered = discover_git_repos(
            scan_roots=list(config.get("scan_roots", [])),
            max_depth=int(config.get("max_depth", DEFAULT_MAX_DEPTH)),
            max_projects=int(config.get("max_projects", DEFAULT_MAX_PROJECTS)),
            exclude_tokens=list(config.get("exclude_path_tokens", [])),
        )
        projects = merge_projects(projects, discovered)
    _CACHE[key] = [dict(item) for item in projects]
    return [dict(item) for item in projects]

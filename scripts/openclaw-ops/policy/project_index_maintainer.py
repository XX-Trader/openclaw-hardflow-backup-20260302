#!/usr/bin/env python3
"""Project index maintainer for multi-project OpenClaw workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from task_center import TaskCenter
except Exception:  # pragma: no cover
    TaskCenter = None

UTC = timezone.utc

DEFAULT_MODULE_GLOBS = [
    "src/**/*.py",
    "src/**/*.ts",
    "src/**/*.tsx",
    "src/**/*.js",
    "src/**/*.jsx",
    "backend/**/*.py",
    "frontend/src/**/*",
    "app/**/*",
    "services/**/*",
]

DEFAULT_API_GLOBS = [
    "**/*api*.py",
    "**/*api*.ts",
    "**/*api*.js",
    "**/openapi*.yml",
    "**/openapi*.yaml",
    "**/openapi*.json",
    "**/routes*.py",
    "**/routes*.ts",
]

DEFAULT_SCRIPT_GLOBS = [
    "scripts/**/*",
    ".workflow/**/*.sh",
    ".workflow/**/*.py",
]

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
}

STACK_DOC_SOURCES: dict[str, dict[str, str]] = {
    "nextjs": {"name": "Next.js", "url": "https://nextjs.org/docs"},
    "react": {"name": "React", "url": "https://react.dev/reference/react"},
    "vue": {"name": "Vue", "url": "https://vuejs.org/guide/introduction.html"},
    "nuxt": {"name": "Nuxt", "url": "https://nuxt.com/docs/getting-started/introduction"},
    "supabase": {"name": "Supabase", "url": "https://supabase.com/docs"},
    "fastapi": {"name": "FastAPI", "url": "https://fastapi.tiangolo.com/"},
    "django": {"name": "Django", "url": "https://docs.djangoproject.com/en/stable/"},
    "flask": {"name": "Flask", "url": "https://flask.palletsprojects.com/en/stable/"},
    "openapi": {"name": "OpenAPI", "url": "https://spec.openapis.org/oas/latest.html"},
}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)


def should_ignore(path: Path) -> bool:
    return any(part in DEFAULT_IGNORE_DIRS for part in path.parts)


def list_files_by_globs(root: Path, globs: list[str], max_files: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pattern in globs:
        for item in root.glob(pattern):
            if not item.is_file():
                continue
            rel = item.relative_to(root).as_posix()
            if rel in seen:
                continue
            if should_ignore(item.relative_to(root)):
                continue
            seen.add(rel)
            out.append(rel)
            if len(out) >= max_files:
                return sorted(out)
    return sorted(out)


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="utf-8-sig")
        except Exception:
            return ""


def detect_stack_tags(root: Path) -> list[str]:
    tags: set[str] = set()
    package_json = root / "package.json"
    if package_json.exists():
        raw = read_text_safe(package_json)
        try:
            pkg = json.loads(raw)
        except Exception:
            pkg = {}
        if isinstance(pkg, dict):
            deps: dict[str, Any] = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                node = pkg.get(key)
                if isinstance(node, dict):
                    deps.update(node)
            dep_keys = {str(k).lower() for k in deps.keys()}
            if "next" in dep_keys:
                tags.add("nextjs")
            if "react" in dep_keys:
                tags.add("react")
            if "vue" in dep_keys:
                tags.add("vue")
            if "nuxt" in dep_keys or "nuxt3" in dep_keys:
                tags.add("nuxt")
            if any("supabase" in key for key in dep_keys):
                tags.add("supabase")

    requirements = root / "requirements.txt"
    req_text = read_text_safe(requirements).lower() if requirements.exists() else ""
    if "fastapi" in req_text:
        tags.add("fastapi")
    if "django" in req_text:
        tags.add("django")
    if "flask" in req_text:
        tags.add("flask")
    if "supabase" in req_text:
        tags.add("supabase")

    pyproject = root / "pyproject.toml"
    pyproject_text = read_text_safe(pyproject).lower() if pyproject.exists() else ""
    if "fastapi" in pyproject_text:
        tags.add("fastapi")
    if "django" in pyproject_text:
        tags.add("django")
    if "flask" in pyproject_text:
        tags.add("flask")
    if "supabase" in pyproject_text:
        tags.add("supabase")

    if list((root / "app").glob("**/*.tsx")) or list((root / "src").glob("**/*.tsx")):
        tags.add("react")
    if list(root.glob("**/openapi*.yml")) or list(root.glob("**/openapi*.yaml")) or list(root.glob("**/openapi*.json")):
        tags.add("openapi")
    return sorted(tags)


def extract_api_endpoints(root: Path, api_files: list[str], max_items: int = 120) -> list[str]:
    patterns = [
        re.compile(r"router\.(?:get|post|put|delete|patch)\(\s*['\"]([^'\"]+)"),
        re.compile(r"app\.(?:get|post|put|delete|patch)\(\s*['\"]([^'\"]+)"),
        re.compile(r"@\w+\.(?:get|post|put|delete|patch)\(\s*['\"]([^'\"]+)"),
    ]
    endpoints: list[str] = []
    seen: set[str] = set()
    for rel in api_files:
        path = root / rel
        text = read_text_safe(path)
        if not text:
            continue
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = str(match.group(1) or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                endpoints.append(value)
                if len(endpoints) >= max_items:
                    return sorted(endpoints)
    return sorted(endpoints)


def fetch_doc_meta(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url=url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=max(3, timeout)) as resp:
            headers = resp.headers
            return {
                "status": int(getattr(resp, "status", 200)),
                "etag": str(headers.get("ETag", "")).strip(),
                "last_modified": str(headers.get("Last-Modified", "")).strip(),
                "checked_at": now_iso(),
            }
    except urllib.error.HTTPError as exc:
        return {"status": int(exc.code or 0), "etag": "", "last_modified": "", "checked_at": now_iso(), "error": str(exc)}
    except Exception as exc:
        return {"status": 0, "etag": "", "last_modified": "", "checked_at": now_iso(), "error": str(exc)}


def sanitize_source_name(value: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower()).strip("-")
    return base or "doc-source"


def strip_html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_doc_excerpt(url: str, timeout: int, max_chars: int) -> dict[str, Any]:
    req = urllib.request.Request(url=url, method="GET", headers={"User-Agent": "openclaw-project-index/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=max(3, timeout)) as resp:
            status = int(getattr(resp, "status", 200))
            raw_bytes = resp.read(max(1024, int(max_chars)))
            text = raw_bytes.decode("utf-8", errors="replace")
            content_type = str(resp.headers.get("Content-Type", "")).strip()
            if "html" in content_type.lower() or "<html" in text.lower():
                text = strip_html_to_text(text)
            text = text[: max(512, int(max_chars))]
            sha = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else ""
            return {
                "status": status,
                "content_type": content_type,
                "excerpt": text,
                "excerpt_sha256": sha,
                "fetched_at": now_iso(),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": int(exc.code or 0),
            "content_type": "",
            "excerpt": "",
            "excerpt_sha256": "",
            "fetched_at": now_iso(),
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "status": 0,
            "content_type": "",
            "excerpt": "",
            "excerpt_sha256": "",
            "fetched_at": now_iso(),
            "error": str(exc),
        }


def build_excerpt_keywords(text: str, max_keywords: int = 80) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", str(text or "").lower())
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    ordered = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _v in ordered[:max_keywords]]


def load_doc_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"sources": {}}
    if not isinstance(data, dict):
        return {"sources": {}}
    sources = data.get("sources")
    if not isinstance(sources, dict):
        data["sources"] = {}
    return data


def build_doc_knowledge(
    *,
    root: Path,
    index_root: Path,
    api_files: list[str],
    enable_checks: bool,
    timeout: int,
    fetch_content: bool,
    fetch_max_chars: int,
) -> tuple[dict[str, Any], bool]:
    tags = detect_stack_tags(root)
    endpoints = extract_api_endpoints(root, api_files, max_items=120)
    sources: list[dict[str, Any]] = []
    for tag in tags:
        if tag not in STACK_DOC_SOURCES:
            continue
        source = dict(STACK_DOC_SOURCES[tag])
        source["tag"] = tag
        sources.append(source)
    if "openapi" not in tags and endpoints:
        openapi_meta = dict(STACK_DOC_SOURCES["openapi"])
        openapi_meta["tag"] = "openapi"
        sources.append(openapi_meta)

    state_file = index_root / "doc-knowledge-state.json"
    prev_state = load_doc_state(state_file)
    prev_sources = prev_state.get("sources", {}) if isinstance(prev_state.get("sources"), dict) else {}
    next_state: dict[str, Any] = {"updated_at": now_iso(), "sources": {}}
    changed = False
    output_sources: list[dict[str, Any]] = []
    search_index: list[dict[str, Any]] = []
    cache_dir = index_root / "doc-source-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    for src in sources:
        url = str(src.get("url", "")).strip()
        prev = prev_sources.get(url, {}) if isinstance(prev_sources, dict) else {}
        meta: dict[str, Any] = {"checked_at": now_iso(), "status": "skipped"}
        if enable_checks and url:
            meta = fetch_doc_meta(url, timeout=timeout)
        prev_etag = str(prev.get("etag", "")).strip()
        prev_last_modified = str(prev.get("last_modified", "")).strip()
        curr_etag = str(meta.get("etag", "")).strip()
        curr_last_modified = str(meta.get("last_modified", "")).strip()
        remote_changed = bool(
            (curr_etag and prev_etag and curr_etag != prev_etag)
            or (curr_last_modified and prev_last_modified and curr_last_modified != prev_last_modified)
        )
        source_name = sanitize_source_name(f"{src.get('tag', '')}-{src.get('name', '')}")
        cache_file = cache_dir / f"{source_name}.txt"
        need_fetch_content = bool(fetch_content) and (
            not cache_file.exists()
            or remote_changed
            or not bool(prev.get("excerpt_sha256", ""))
        )
        excerpt_sha = str(prev.get("excerpt_sha256", "")).strip()
        excerpt_status = "skipped"
        excerpt_error = ""
        keywords: list[str] = []
        if need_fetch_content and url:
            fetched = fetch_doc_excerpt(url, timeout=max(3, timeout), max_chars=max(2048, int(fetch_max_chars)))
            excerpt = str(fetched.get("excerpt", "") or "")
            excerpt_sha = str(fetched.get("excerpt_sha256", "") or "")
            excerpt_status = str(fetched.get("status", "0"))
            excerpt_error = str(fetched.get("error", "") or "").strip()
            if excerpt:
                cache_file.write_text(excerpt + "\n", encoding="utf-8")
                keywords = build_excerpt_keywords(excerpt, max_keywords=80)
                changed = True
        elif cache_file.exists():
            excerpt = read_text_safe(cache_file)
            keywords = build_excerpt_keywords(excerpt, max_keywords=80) if excerpt else []
            excerpt_status = "cached"

        item = dict(src)
        item.update(meta)
        item["remote_changed"] = remote_changed
        item["acquisition_channels"] = ["direct-fetch", "browser-fallback"]
        item["cache_file"] = str(cache_file)
        item["excerpt_status"] = excerpt_status
        item["excerpt_sha256"] = excerpt_sha
        if excerpt_error:
            item["excerpt_error"] = excerpt_error
        item["keywords"] = keywords[:20]
        output_sources.append(item)
        next_state["sources"][url] = {
            "etag": curr_etag,
            "last_modified": curr_last_modified,
            "checked_at": str(meta.get("checked_at", "")),
            "status": meta.get("status", 0),
            "cache_file": str(cache_file),
            "excerpt_sha256": excerpt_sha,
        }
        search_index.append(
            {
                "tag": str(src.get("tag", "")),
                "name": str(src.get("name", "")),
                "url": url,
                "cache_file": str(cache_file),
                "keywords": keywords,
                "checked_at": str(meta.get("checked_at", "")),
                "remote_changed": remote_changed,
            }
        )
        if remote_changed:
            changed = True

    doc_payload = {
        "generated_at": now_iso(),
        "project_root": str(root),
        "stack_tags": tags,
        "api_endpoints": endpoints,
        "doc_sources": output_sources,
        "checks_enabled": bool(enable_checks),
        "fetch_content_enabled": bool(fetch_content),
        "search_index": search_index,
    }
    changed = write_if_changed(state_file, json.dumps(next_state, ensure_ascii=False, indent=2) + "\n") or changed
    return doc_payload, changed


def render_doc_knowledge_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Dynamic Doc Knowledge")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at', '')}")
    lines.append(f"- project_root: {payload.get('project_root', '')}")
    tags = payload.get("stack_tags", [])
    lines.append(f"- stack_tags: {', '.join(tags) if isinstance(tags, list) and tags else '-'}")
    lines.append("")
    lines.append("## API Endpoints")
    endpoints = payload.get("api_endpoints", [])
    if isinstance(endpoints, list) and endpoints:
        for item in endpoints[:120]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Official Docs Sources")
    sources = payload.get("doc_sources", [])
    if isinstance(sources, list) and sources:
        for item in sources:
            tag = str(item.get("tag", "")).strip()
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            status = str(item.get("status", "")).strip()
            remote_changed = bool(item.get("remote_changed", False))
            checked_at = str(item.get("checked_at", "")).strip()
            excerpt_status = str(item.get("excerpt_status", "")).strip()
            channels = item.get("acquisition_channels", [])
            channels_text = ",".join(channels) if isinstance(channels, list) else ""
            lines.append(
                f"- [{tag}] {name}: {url} "
                f"(status={status}, remote_changed={remote_changed}, checked_at={checked_at}, "
                f"excerpt={excerpt_status}, channels={channels_text})"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Search Index")
    search_index = payload.get("search_index", [])
    if isinstance(search_index, list) and search_index:
        for item in search_index[:120]:
            tag = str(item.get("tag", "")).strip()
            url = str(item.get("url", "")).strip()
            cache_file = str(item.get("cache_file", "")).strip()
            keywords = item.get("keywords", [])
            keywords_text = ", ".join(keywords[:12]) if isinstance(keywords, list) else ""
            lines.append(f"- [{tag}] {url} -> {cache_file} | keywords: {keywords_text}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Usage")
    lines.append("- project-agent should prioritize these sources when planning and coding.")
    lines.append("- if remote_changed=true, refresh project docs and memory index.")
    lines.append("")
    return "\n".join(lines)


def load_registry(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(raw, list):
        projects = raw
    elif isinstance(raw, dict):
        projects = raw.get("projects", [])
    else:
        raise ValueError("registry must be object or list")
    if not isinstance(projects, list):
        raise ValueError("registry.projects must be list")
    result: list[dict[str, Any]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        root = str(item.get("path", "")).strip()
        if not root:
            continue
        result.append(item)
    return result


@dataclass(slots=True)
class ProjectResult:
    project_id: str
    name: str
    path: str
    ok: bool
    changed: bool
    git_repo: bool
    git_pull_attempted: bool
    git_pull_ok: bool
    errors: list[str]
    outputs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "path": self.path,
            "ok": self.ok,
            "changed": self.changed,
            "git_repo": self.git_repo,
            "git_pull_attempted": self.git_pull_attempted,
            "git_pull_ok": self.git_pull_ok,
            "errors": self.errors,
            "outputs": self.outputs,
        }


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def build_index_markdown(
    name: str,
    root: Path,
    git_info: dict[str, Any],
    modules: list[str],
    apis: list[str],
    scripts: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# {name} Project Index")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- root: {root}")
    lines.append(f"- git_repo: {git_info.get('git_repo', False)}")
    lines.append(f"- git_branch: {git_info.get('branch', '-')}")
    lines.append(f"- git_remote: {git_info.get('remote', '-')}")
    lines.append(f"- dirty_files: {git_info.get('dirty_count', 0)}")
    lines.append("")
    lines.append("## Workflow")
    lines.append("1. coordinator intake and requirement alignment")
    lines.append("2. project-agent provides project context and index lookup")
    lines.append("3. coordinator planning and risk dispatch")
    lines.append("4. execution agents implement -> tester validates -> feedback loop")
    lines.append("5. policy-enforcer records status/time/token/cost")
    lines.append("")
    lines.append("## Module Files")
    if modules:
        for item in modules:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## API Related Files")
    if apis:
        for item in apis:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Run / Change Scripts")
    if scripts:
        for item in scripts:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Update Rules")
    lines.append("- API/parameters/process changes must update this index in the same commit.")
    lines.append("- project-agent maintains this index; coordinator consumes it for planning.")
    lines.append("- Dynamic doc knowledge is maintained in DOC_KNOWLEDGE.md and doc-knowledge.json.")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def collect_git_info(root: Path, timeout: int, do_pull: bool, remote: str, branch: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    info = {
        "git_repo": False,
        "branch": "",
        "remote": "",
        "dirty_count": 0,
        "pull_attempted": False,
        "pull_ok": False,
    }
    rc, out, err = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, timeout=timeout)
    if rc != 0 or out.strip() != "true":
        return info, errors

    info["git_repo"] = True
    rc, out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, timeout=timeout)
    if rc == 0:
        info["branch"] = out
    rc, out, _ = run_cmd(["git", "remote", "get-url", remote], cwd=root, timeout=timeout)
    if rc == 0:
        info["remote"] = out
    rc, out, _ = run_cmd(["git", "status", "--porcelain"], cwd=root, timeout=timeout)
    if rc == 0 and out:
        info["dirty_count"] = len([x for x in out.splitlines() if x.strip()])

    if do_pull:
        info["pull_attempted"] = True
        target_branch = branch or str(info["branch"] or "HEAD")
        rc, _, err = run_cmd(["git", "pull", "--ff-only", remote, target_branch], cwd=root, timeout=timeout)
        info["pull_ok"] = rc == 0
        if rc != 0:
            errors.append(f"git pull failed: {err or rc}")
    return info, errors


def normalize_project_id(value: str) -> str:
    base = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.lower()).strip("-")
    return base or "project"


def maintain_project(
    item: dict[str, Any],
    git_pull_flag: bool,
    timeout: int,
    max_files: int,
    *,
    enable_doc_knowledge: bool,
    doc_check_updates: bool,
    doc_timeout: int,
    doc_fetch_content: bool,
    doc_fetch_max_chars: int,
    memory_index_on_change: bool,
) -> ProjectResult:
    name = str(item.get("name", "")).strip() or Path(str(item["path"])).name
    project_id = normalize_project_id(str(item.get("id", "")).strip() or name)
    root = Path(str(item["path"])).expanduser()
    errors: list[str] = []
    outputs: list[str] = []
    changed = False

    if not root.exists() or not root.is_dir():
        return ProjectResult(project_id, name, str(root), False, False, False, False, False, ["project path invalid"], [])

    index_dir = str(item.get("index_dir", ".workflow/project-index")).strip() or ".workflow/project-index"
    index_root = root / index_dir

    git_pull = bool(item.get("auto_pull", True)) and git_pull_flag
    remote = str(item.get("git_remote", "origin")).strip() or "origin"
    branch = str(item.get("git_branch", "")).strip()
    git_info, git_errors = collect_git_info(root, timeout=timeout, do_pull=git_pull, remote=remote, branch=branch)
    errors.extend(git_errors)

    module_globs = item.get("module_globs") or DEFAULT_MODULE_GLOBS
    api_globs = item.get("api_globs") or DEFAULT_API_GLOBS
    script_globs = item.get("script_globs") or DEFAULT_SCRIPT_GLOBS
    if not isinstance(module_globs, list):
        module_globs = DEFAULT_MODULE_GLOBS
    if not isinstance(api_globs, list):
        api_globs = DEFAULT_API_GLOBS
    if not isinstance(script_globs, list):
        script_globs = DEFAULT_SCRIPT_GLOBS

    modules = list_files_by_globs(root, [str(x) for x in module_globs], max_files=max_files)
    apis = list_files_by_globs(root, [str(x) for x in api_globs], max_files=max_files)
    scripts = list_files_by_globs(root, [str(x) for x in script_globs], max_files=max_files)

    index_md = build_index_markdown(name, root, git_info, modules, apis, scripts)
    changed = write_if_changed(index_root / "PROJECT_INDEX.md", index_md) or changed
    outputs.append(str(index_root / "PROJECT_INDEX.md"))

    index_json = {
        "project_id": project_id,
        "name": name,
        "path": str(root),
        "generated_at": now_iso(),
        "git": git_info,
        "modules": modules,
        "apis": apis,
        "scripts": scripts,
    }
    changed = write_if_changed(index_root / "project-index.json", json.dumps(index_json, ensure_ascii=False, indent=2) + "\n") or changed
    outputs.append(str(index_root / "project-index.json"))

    if enable_doc_knowledge:
        doc_payload, doc_state_changed = build_doc_knowledge(
            root=root,
            index_root=index_root,
            api_files=apis,
            enable_checks=doc_check_updates,
            timeout=max(3, int(doc_timeout)),
            fetch_content=doc_fetch_content,
            fetch_max_chars=max(2048, int(doc_fetch_max_chars)),
        )
        changed = write_if_changed(
            index_root / "doc-knowledge.json",
            json.dumps(doc_payload, ensure_ascii=False, indent=2) + "\n",
        ) or changed
        changed = write_if_changed(
            index_root / "doc-search-index.json",
            json.dumps(doc_payload.get("search_index", []), ensure_ascii=False, indent=2) + "\n",
        ) or changed
        changed = write_if_changed(index_root / "DOC_KNOWLEDGE.md", render_doc_knowledge_markdown(doc_payload)) or changed
        changed = doc_state_changed or changed
        outputs.append(str(index_root / "doc-knowledge.json"))
        outputs.append(str(index_root / "doc-search-index.json"))
        outputs.append(str(index_root / "DOC_KNOWLEDGE.md"))

        if changed and memory_index_on_change:
            rc, _out, err = run_cmd(["openclaw", "memory", "index", "--force"], cwd=root, timeout=max(30, timeout))
            if rc != 0:
                outputs.append(f"memory_index_failed:{err or rc}")

    ok = len(errors) == 0
    return ProjectResult(
        project_id=project_id,
        name=name,
        path=str(root),
        ok=ok,
        changed=changed,
        git_repo=bool(git_info["git_repo"]),
        git_pull_attempted=bool(git_info["pull_attempted"]),
        git_pull_ok=bool(git_info["pull_ok"]),
        errors=errors,
        outputs=outputs,
    )


def write_task_event(task_db: str, task_id: str, actor: str, report: dict[str, Any]) -> None:
    if not TaskCenter:
        return
    db = TaskCenter(task_db)
    try:
        db.init_schema()
        db.add_event(
            task_id=task_id,
            actor=actor,
            event_type="project_index_maintained",
            stage="project-index",
            details={"report_summary": {"ok": report["ok"], "project_count": report["project_count"]}},
        )
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain project index docs for multi-project workflows")
    parser.add_argument("--registry", required=True, help="registry json path")
    parser.add_argument("--git-pull", action="store_true", help="perform git pull on each project if git repo")
    parser.add_argument("--timeout", type=int, default=30, help="command timeout seconds")
    parser.add_argument("--max-files", type=int, default=300, help="max listed files per category")
    parser.add_argument("--disable-doc-knowledge", action="store_true", help="disable dynamic doc knowledge index")
    parser.add_argument("--disable-doc-check-updates", action="store_true", help="skip remote docs update checks")
    parser.add_argument("--doc-timeout", type=int, default=8, help="docs metadata request timeout seconds")
    parser.add_argument("--disable-doc-fetch-content", action="store_true", help="skip direct docs content fetch")
    parser.add_argument("--doc-fetch-max-chars", type=int, default=24000, help="max chars fetched per docs source")
    parser.add_argument(
        "--disable-memory-index-on-change",
        action="store_true",
        help="skip openclaw memory index refresh when index/doc files changed",
    )
    parser.add_argument("--output", default="", help="write report json path")
    parser.add_argument("--emit-json", action="store_true", help="print full report json to stdout")
    parser.add_argument("--task-db", default="", help="optional task center sqlite path")
    parser.add_argument("--task-id", default="", help="optional task id for event logging")
    parser.add_argument("--actor", default="project-agent", help="event actor")
    args = parser.parse_args()

    registry = Path(args.registry).expanduser()
    projects = load_registry(registry)
    results: list[ProjectResult] = []
    for item in projects:
        results.append(
            maintain_project(
                item=item,
                git_pull_flag=bool(args.git_pull),
                timeout=max(5, int(args.timeout)),
                max_files=max(50, int(args.max_files)),
                enable_doc_knowledge=not bool(args.disable_doc_knowledge),
                doc_check_updates=not bool(args.disable_doc_check_updates),
                doc_timeout=max(3, int(args.doc_timeout)),
                doc_fetch_content=not bool(args.disable_doc_fetch_content),
                doc_fetch_max_chars=max(2048, int(args.doc_fetch_max_chars)),
                memory_index_on_change=not bool(args.disable_memory_index_on_change),
            )
        )

    report = {
        "ok": all(x.ok for x in results),
        "generated_at": now_iso(),
        "registry": str(registry),
        "project_count": len(results),
        "changed_count": len([x for x in results if x.changed]),
        "projects": [x.to_dict() for x in results],
    }

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.task_db and args.task_id:
        write_task_event(task_db=args.task_db, task_id=args.task_id, actor=args.actor, report=report)

    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        if report["changed_count"] == 0 and report["ok"]:
            print("NO_REPLY")
        else:
            print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

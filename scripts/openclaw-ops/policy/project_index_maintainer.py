#!/usr/bin/env python3
"""Project index maintainer for multi-project OpenClaw workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from io_write_gateway import atomic_write_text, write_json_atomic

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

DEFAULT_INDEX_DIR = ".workflow/project-index-local"
LEGACY_INDEX_DIR = ".workflow/project-index"
SAFE_PULL_UNTRACKED_PREFIXES = (
    f"{LEGACY_INDEX_DIR}/",
    f"{DEFAULT_INDEX_DIR}/",
    "scripts/openclaw-ops/policy/runtime/",
)

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


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def policy_enforcer_path() -> Path:
    custom = str(os.environ.get("POLICY_ENFORCER_PY", "")).strip()
    if custom:
        return Path(custom).expanduser()
    return Path(__file__).resolve().parent / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized = str(task_id or "").strip()
    if not normalized:
        return False
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized,)).fetchone()
        conn.close()
        return bool(row)
    except Exception:
        return False


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "project-agent").strip() or "project-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "project-agent"
    source_name = str(source_module or "project-agent/project-index-maintainer").strip() or "project-agent/project-index-maintainer"
    create_args = [
        "create-task",
        "--task-id",
        normalized,
        "--task-type",
        "ops_runtime_cron",
        "--reason",
        f"[CRON_RUNTIME] bind {normalized}",
        "--source",
        source_name,
        "--request-source",
        "ai",
        "--priority",
        "low",
        "--risk-level",
        "low",
        "--pool",
        "jobs",
        "--assignee",
        assignee,
        "--need-human-confirm",
        "false",
        "--human-confirmed",
        "true",
        "--requirement",
        f"Auto register runtime task for {normalized} to bind observability records.",
        "--result-output",
        "Runtime task exists and accepts module/communication/report records.",
        "--acceptance",
        "Task can be used for cron observability binding without manual action.",
        "--observable-outputs",
        "module_logs,module_communications,agent_task_reports,planner_summary",
        "--acceptance-thresholds",
        "At least one runtime observability record is bound to this task.",
        "--scheduled-at",
        now_iso(),
        "--actor",
        actor_name,
    ]
    ok, _payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
    if ok and task_exists_in_db(db_path, normalized):
        return normalized, ""
    return "", (err or f"auto_register_task_failed:{normalized}")


def invoke_policy_enforcer(db_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, dict[str, Any], str]:
    script = policy_enforcer_path()
    if not script.exists():
        return False, {}, f"policy_enforcer_missing:{script}"
    cmd = [sys.executable, str(script), "--db", str(db_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return False, {}, f"policy_enforcer_exec_failed:{exc}"

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    if not isinstance(payload, dict):
        return False, {}, "policy_enforcer_invalid_json_output"
    if not bool(payload.get("ok", False)):
        return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
    return True, payload, ""


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
                atomic_write_text(
                    cache_file,
                    excerpt + "\n",
                    encoding="utf-8",
                    file_mode=0o640,
                    dir_mode=0o750,
                )
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
    atomic_write_text(
        path,
        content,
        encoding="utf-8",
        newline="\n",
        file_mode=0o640,
        dir_mode=0o750,
    )
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
        if rc == 0:
            info["pull_ok"] = True
        else:
            conflict_paths = extract_untracked_overwrite_paths(err)
            safe_conflicts = [p for p in conflict_paths if is_safe_pull_untracked_path(p)]
            info["pull_conflict_untracked"] = conflict_paths
            retry_attempted = False
            if conflict_paths and len(safe_conflicts) == len(conflict_paths):
                retry_attempted = True
                moved, backup_dir, move_errors = backup_untracked_for_pull(root, safe_conflicts)
                info["pull_retry_attempted"] = True
                info["pull_retry_moved_untracked"] = moved
                if backup_dir:
                    info["pull_retry_backup_dir"] = backup_dir
                if move_errors:
                    info["pull_retry_move_errors"] = move_errors
                if moved:
                    rc2, _, err2 = run_cmd(["git", "pull", "--ff-only", remote, target_branch], cwd=root, timeout=timeout)
                    info["pull_ok"] = rc2 == 0
                    if rc2 != 0:
                        errors.append(f"git pull failed after auto-cleanup: {err2 or rc2}")
                else:
                    errors.append(f"git pull failed: {err or rc}")
            if not retry_attempted:
                info["pull_ok"] = False
                errors.append(f"git pull failed: {err or rc}")
    return info, errors


def normalize_rel_path(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def is_safe_pull_untracked_path(path: str) -> bool:
    rel = normalize_rel_path(path).lower()
    if not rel:
        return False
    for prefix in SAFE_PULL_UNTRACKED_PREFIXES:
        p = normalize_rel_path(prefix).lower()
        if p and rel.startswith(p):
            return True
    return False


def extract_untracked_overwrite_paths(error_text: str) -> list[str]:
    paths: list[str] = []
    collecting = False
    for raw_line in str(error_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "would be overwritten by merge" in line.lower():
            collecting = True
            continue
        if not collecting:
            continue
        lower = line.lower()
        if lower.startswith("please move or remove") or lower.startswith("aborting"):
            break
        paths.append(normalize_rel_path(line))
    uniq: list[str] = []
    seen: set[str] = set()
    for item in paths:
        if not item or item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def backup_untracked_for_pull(root: Path, rel_paths: list[str]) -> tuple[list[str], str, list[str]]:
    moved: list[str] = []
    errors: list[str] = []
    backup_root = root / DEFAULT_INDEX_DIR / "_autobackup-untracked" / datetime.now().strftime("%Y%m%d_%H%M%S")
    for rel in rel_paths:
        rel_norm = normalize_rel_path(rel)
        if not rel_norm:
            continue
        source = root / rel_norm
        if not source.exists():
            continue
        target = backup_root / rel_norm
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source), str(target))
            moved.append(rel_norm)
        except Exception as exc:
            errors.append(f"{rel_norm}:{exc}")
    return moved, str(backup_root) if moved else "", errors


def is_git_tracked_path(root: Path, rel_path: str, timeout: int = 15) -> bool:
    rc, _out, _err = run_cmd(["git", "ls-files", "--error-unmatch", rel_path], cwd=root, timeout=max(5, int(timeout)))
    return rc == 0


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

    configured_index_dir = str(item.get("index_dir", DEFAULT_INDEX_DIR)).strip() or DEFAULT_INDEX_DIR
    index_dir = configured_index_dir
    # If legacy index path is tracked by repository, route runtime artifacts to local-only index dir.
    if configured_index_dir == LEGACY_INDEX_DIR and is_git_tracked_path(root, f"{LEGACY_INDEX_DIR}/PROJECT_INDEX.md", timeout=timeout):
        index_dir = DEFAULT_INDEX_DIR
        outputs.append(f"index_dir_auto_switch:{configured_index_dir}->{index_dir}")
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


def compact_text(value: Any, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def detect_issue_code(project: dict[str, Any]) -> str:
    if not bool(project.get("git_pull_ok", True)) and bool(project.get("git_pull_attempted", False)):
        return "git_pull_failed"
    if not bool(project.get("ok", False)):
        return "project_index_build_failed"
    return "unknown_failure"


def build_failure_output(report: dict[str, Any]) -> str:
    projects = report.get("projects", [])
    if not isinstance(projects, list):
        projects = []

    failed_items: list[dict[str, Any]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        if bool(item.get("ok", False)):
            continue
        failed_items.append(item)

    lines: list[str] = []
    lines.append("# project-index-maintainer")
    lines.append(f"status: {'failed' if failed_items else 'unknown_failure'}")
    lines.append(f"generated_at: {compact_text(report.get('generated_at', '-'), 64)}")
    lines.append(
        "summary: "
        + f"projects_total={int(report.get('project_count', 0) or 0)}, "
        + f"projects_failed={len(failed_items)}, "
        + f"changed_count={int(report.get('changed_count', 0) or 0)}"
    )
    lines.append("failed_modules:")

    if not failed_items:
        lines.append("- module=project_index_maintainer issue=unknown_failure detail=no_project_level_error_found")
        return "\n".join(lines)

    for item in failed_items[:8]:
        project_id = str(item.get("project_id", "")).strip() or "unknown-project"
        issue_code = detect_issue_code(item)
        errors = item.get("errors", [])
        detail = ""
        if isinstance(errors, list):
            for err in errors:
                text = compact_text(err, 220)
                if text:
                    detail = text
                    break
        if not detail:
            detail = "no_error_detail"
        lines.append(
            "- "
            + f"module=project-index/{project_id} "
            + f"issue={issue_code} "
            + f"detail={detail}"
        )
    return "\n".join(lines)


def main() -> int:
    run_started_at = datetime.now(tz=UTC)
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
    try:
        projects = load_registry(registry)
    except Exception as exc:
        report = {
            "ok": False,
            "generated_at": now_iso(),
            "registry": str(registry),
            "project_count": 0,
            "changed_count": 0,
            "projects": [
                {
                    "project_id": "registry",
                    "ok": False,
                    "git_pull_ok": True,
                    "git_pull_attempted": False,
                    "errors": [f"registry_load_failed:{exc}"],
                }
            ],
        }
        if args.emit_json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(build_failure_output(report))
        return 2
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
    run_duration_ms = max(0, int((datetime.now(tz=UTC) - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms

    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    if args.task_db:
        task_db_path = Path(args.task_db).expanduser()
        policy_observability["enabled"] = task_db_path.exists()
        policy_observability["db"] = str(task_db_path)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                task_db_path,
                raw_task_id,
                "project-agent",
                "project-agent/project-index-maintainer",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        if task_db_path.exists():
            err_items: list[str] = []
            for item in report.get("projects", []):
                if not isinstance(item, dict):
                    continue
                for err in item.get("errors", []) if isinstance(item.get("errors"), list) else []:
                    text = str(err).strip()
                    if text:
                        err_items.append(text)

            module_args = [
                "log-module",
                "--module-name",
                "project-agent/project-index-maintainer",
                "--phase",
                "project-index",
                "--level",
                ("error" if not report.get("ok", False) else "info"),
                "--status",
                ("failed" if not report.get("ok", False) else "passed"),
                "--message",
                (
                    "project index maintain completed: "
                    + f"projects={report.get('project_count', 0)} changed={report.get('changed_count', 0)}"
                ),
                "--duration-ms",
                str(run_duration_ms),
                "--details-json",
                json.dumps(
                    {
                        "registry": str(registry),
                        "project_count": report.get("project_count", 0),
                        "changed_count": report.get("changed_count", 0),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                str(args.actor or "project-agent"),
            ]
            if bound_task_id:
                module_args.extend(["--task-id", bound_task_id])
            ok_module, _payload_module, err_module = invoke_policy_enforcer(task_db_path, module_args, timeout=30)
            policy_observability["log_module_ok"] = ok_module
            if not ok_module and err_module:
                policy_observability["errors"].append(err_module)

            comm_args = [
                "log-communication",
                "--from-module",
                "project-agent/project-index-maintainer",
                "--to-module",
                "coordinator",
                "--protocol",
                "policy-enforcer",
                "--message-type",
                "project_context_update",
                "--status",
                ("acked" if report.get("ok", False) else "failed"),
                "--latency-ms",
                str(run_duration_ms),
                "--correlation-id",
                str(report.get("generated_at", "")),
                "--payload-ref",
                str(args.output or ""),
                "--details-json",
                json.dumps(
                    {
                        "project_count": report.get("project_count", 0),
                        "changed_count": report.get("changed_count", 0),
                        "ok": bool(report.get("ok", False)),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                str(args.actor or "project-agent"),
            ]
            if bound_task_id:
                comm_args.extend(["--task-id", bound_task_id])
            ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(task_db_path, comm_args, timeout=30)
            policy_observability["log_communication_ok"] = ok_comm
            if not ok_comm and err_comm:
                policy_observability["errors"].append(err_comm)

            if bound_task_id:
                report_args = [
                    "report-agent-result",
                    "--task-id",
                    bound_task_id,
                    "--agent-id",
                    "project-agent",
                    "--planner-id",
                    "coordinator",
                    "--status",
                    ("passed" if report.get("ok", False) else "failed"),
                    "--solved",
                    ("true" if report.get("ok", False) else "false"),
                    "--resolved-issues",
                    (
                        "project_index_updated"
                        if int(report.get("changed_count", 0) or 0) > 0
                        else "index_checked_no_change"
                    ),
                    "--resolution-summary",
                    (
                        "project index refreshed for coordinator planning"
                        if report.get("ok", False)
                        else "project index maintenance failed"
                    ),
                    "--resolution-steps",
                    "scan,build_index,write_outputs",
                    "--failed-items",
                    ",".join(err_items[:20]),
                    "--failure-count",
                    str(len(err_items)),
                    "--duration-ms",
                    str(run_duration_ms),
                    "--input-tokens",
                    "0",
                    "--output-tokens",
                    "0",
                    "--cost-estimate",
                    "0",
                    "--quality-score",
                    ("96" if report.get("ok", False) else "45"),
                    "--quality-grade",
                    ("a" if report.get("ok", False) else "d"),
                    "--notify-chat",
                    ("false" if report.get("ok", False) else "true"),
                    "--details-json",
                    json.dumps(
                        {
                            "project_count": report.get("project_count", 0),
                            "changed_count": report.get("changed_count", 0),
                            "registry": str(registry),
                        },
                        ensure_ascii=False,
                    ),
                    "--actor",
                    str(args.actor or "project-agent"),
                ]
                ok_report, payload_report, err_report = invoke_policy_enforcer(task_db_path, report_args, timeout=35)
                policy_observability["report_agent_result_ok"] = ok_report
                if ok_report and isinstance(payload_report, dict):
                    result_payload = payload_report.get("result")
                    if isinstance(result_payload, dict):
                        planner_payload = result_payload.get("planner_payload")
                        if isinstance(planner_payload, dict):
                            policy_observability["agent_report"] = {
                                "report_status": planner_payload.get("report_status"),
                                "notify_chat": planner_payload.get("notify_chat"),
                                "failure_count": planner_payload.get("failure_count"),
                            }
                if not ok_report and err_report:
                    policy_observability["errors"].append(err_report)

            since_24h = (datetime.now(tz=UTC) - timedelta(hours=24)).replace(microsecond=0).isoformat()
            ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
                task_db_path,
                [
                    "planner-summary",
                    "--planner-id",
                    "coordinator",
                    "--since",
                    since_24h,
                    "--limit",
                    "60",
                ],
                timeout=30,
            )
            policy_observability["planner_summary_ok"] = ok_summary
            if ok_summary and isinstance(payload_summary, dict):
                summary = payload_summary.get("summary")
                if isinstance(summary, dict):
                    report["planner_summary"] = {
                        "planner_id": summary.get("planner_id"),
                        "report_count": summary.get("report_count", 0),
                        "task_count": summary.get("task_count", 0),
                        "resolved_task_count": summary.get("resolved_task_count", 0),
                        "failed_task_count": summary.get("failed_task_count", 0),
                        "solved_ratio_pct": summary.get("solved_ratio_pct", 0.0),
                        "total_tokens": summary.get("total_tokens", 0),
                        "total_cost_estimate": summary.get("total_cost_estimate", 0.0),
                    }
            if not ok_summary and err_summary:
                policy_observability["errors"].append(err_summary)

    report["policy_observability"] = policy_observability

    if args.task_db and args.task_id:
        write_task_event(task_db=args.task_db, task_id=args.task_id, actor=args.actor, report=report)

    if args.output:
        out = Path(args.output).expanduser()
        write_json_atomic(
            out,
            report,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )

    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        if report["ok"]:
            print("NO_REPLY")
        else:
            print(build_failure_output(report))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

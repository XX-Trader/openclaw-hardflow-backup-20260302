
#!/usr/bin/env python3
"""GitHub web evolution runner.

Loop:
1) Search high-signal GitHub repositories by query packs.
2) Persist web knowledge under OPENCLAW_HOME/web/github/.
3) Create human-reviewed TODO tasks for optimization follow-up.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
policy_dir = str(POLICY_DIR)
if policy_dir in sys.path:
    sys.path.remove(policy_dir)
sys.path.insert(0, policy_dir)

from task_center import TaskCenter  # type: ignore
from task_capability_binding import build_task_constraint_fields  # type: ignore
from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic  # type: ignore
from web_sources_runtime import load_project_repo_targets  # type: ignore
from chat_output import build_trace_id, render_chat_notice

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "optimization-agent/github-web-evolution"
DEFAULT_GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
DEFAULT_QUERY_PACK = [
    "openclaw hooks plugins skills archived:false",
    "openclaw workflow automation agent archived:false",
    "openclaw plugin hook manager archived:false",
    "claude code skills plugins workflow archived:false",
    "browser automation anti bot playwright archived:false",
]
DEFAULT_SKILL_QUERY_PACK = [
    "openclaw",
    "openclaw skills",
    "openclaw hooks",
    "openclaw plugins",
    "openclaw workflow",
]
METHOD_KEYWORDS = {
    "workflow",
    "agent",
    "memory",
    "review",
    "route",
    "routing",
    "scheduler",
    "cron",
    "optimi",
    "token",
    "quality",
    "dedupe",
    "gate",
    "context",
    "rollback",
    "verify",
    "pr",
    "pipeline",
    "self-evolution",
}
PROJECT_SCOPE_KEYWORDS = {
    "agent",
    "automation",
    "browser",
    "crawler",
    "hook",
    "hooks",
    "openclaw",
    "playwright",
    "plugin",
    "plugins",
    "review",
    "scraper",
    "scraping",
    "scrapling",
    "selenium",
    "skill",
    "skills",
    "test",
    "testing",
    "web",
    "workflow",
}
SKILL_SCOPE_KEYWORDS = {
    "agent",
    "api",
    "binance",
    "exchange",
    "hook",
    "hooks",
    "openclaw",
    "plugin",
    "plugins",
    "skill",
    "skills",
    "trading",
    "workflow",
}
INFRA_REPO_FULL_NAMES = {
    "python/cpython",
    "nodejs/node",
    "golang/go",
    "rust-lang/rust",
    "denoland/deno",
    "ruby/ruby",
    "php/php-src",
    "openjdk/jdk",
    "dotnet/runtime",
    "llvm/llvm-project",
}


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


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
    return POLICY_DIR / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized_id = str(task_id or "").strip()
    if not normalized_id or (not db_path.exists()):
        return False
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized_id,)).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "github-web-evolution-agent").strip() or "github-web-evolution-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "optimization-agent"
    source_name = str(source_module or "optimization-agent/github-web-evolution").strip() or "optimization-agent/github-web-evolution"
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


def quality_grade_from_score(score: float) -> str:
    value = max(0.0, min(float(score), 100.0))
    if value >= 95:
        return "a+"
    if value >= 90:
        return "a"
    if value >= 80:
        return "b"
    if value >= 70:
        return "c"
    return "d"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def save_text(path: Path, content: str) -> None:
    try:
        atomic_write_text(
            path,
            str(content or ""),
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_text_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-04",
        "runs": 0,
        "updated_at": "",
        "last_scan_at": "",
        "last_report_file": "",
        "fingerprints": {},
    }


def should_run(*, last_scan_at: str, min_interval_minutes: int, force: bool) -> bool:
    if force:
        return True
    dt = parse_iso(last_scan_at)
    if dt is None:
        return True
    return (now() - dt) >= timedelta(minutes=max(1, int(min_interval_minutes)))


def github_headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "openclaw-github-web-evolution",
    }
    if str(token).strip():
        headers["Authorization"] = f"Bearer {str(token).strip()}"
    return headers


def github_get_json(url: str, token: str, timeout: int) -> tuple[bool, dict[str, Any], str]:
    req = urllib.request.Request(url, headers=github_headers(token), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=max(5, int(timeout))) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return True, payload, ""
            return False, {}, "json_not_object"
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return False, {}, f"http_{exc.code}:{body[:240]}"
    except Exception as exc:
        return False, {}, str(exc)


def github_search_repositories(
    *,
    query: str,
    token: str,
    per_page: int,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return [], {"query": q, "ok": False, "error": "empty_query"}

    url = (
        "https://api.github.com/search/repositories?"
        + urllib.parse.urlencode(
            {
                "q": q,
                "sort": "updated",
                "order": "desc",
                "per_page": max(1, min(100, int(per_page))),
                "page": 1,
            }
        )
    )
    ok, payload, error = github_get_json(url=url, token=token, timeout=timeout)
    if not ok:
        return [], {"query": q, "ok": False, "error": error}

    items = payload.get("items", [])
    out: list[dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                out.append(dict(item))

    return out, {
        "query": q,
        "ok": True,
        "total_count": int(payload.get("total_count", 0) or 0),
        "incomplete_results": bool(payload.get("incomplete_results", False)),
        "returned": len(out),
    }


def github_get_repository(*, full_name: str, token: str, timeout: int) -> tuple[dict[str, Any] | None, str]:
    normalized = normalize_repo_full_name(full_name)
    if not normalized:
        return None, "invalid_full_name"
    owner, repo = normalized.split("/", 1)
    ok, payload, error = github_get_json(
        url=f"https://api.github.com/repos/{owner}/{repo}",
        token=token,
        timeout=timeout,
    )
    if not ok:
        return None, error
    return payload, ""


def calc_repo_quality(repo: dict[str, Any]) -> int:
    stars = max(0, int(repo.get("stargazers_count", 0) or 0))
    forks = max(0, int(repo.get("forks_count", 0) or 0))
    pushed_at = parse_iso(str(repo.get("pushed_at", "")))

    stars_score = min(50, int(round(math.log10(stars + 1) * 18)))
    community_score = min(15, int(round(math.log10(forks + 1) * 10)))
    recency_score = 0
    if pushed_at is not None:
        days = max(0, int((now() - pushed_at).days))
        if days <= 30:
            recency_score = 35
        elif days <= 90:
            recency_score = 26
        elif days <= 180:
            recency_score = 17
        elif days <= 365:
            recency_score = 8
        else:
            recency_score = 2
    return int(max(0, min(100, stars_score + community_score + recency_score)))


def normalize_repo_item(item: dict[str, Any], query: str) -> dict[str, Any] | None:
    full_name = str(item.get("full_name", "")).strip()
    if "/" not in full_name:
        return None
    owner, name = full_name.split("/", 1)
    repo = {
        "full_name": full_name,
        "owner": owner,
        "name": name,
        "html_url": str(item.get("html_url", "")).strip(),
        "description": str(item.get("description", "") or "").strip(),
        "stargazers_count": int(item.get("stargazers_count", 0) or 0),
        "forks_count": int(item.get("forks_count", 0) or 0),
        "watchers_count": int(item.get("watchers_count", 0) or 0),
        "open_issues_count": int(item.get("open_issues_count", 0) or 0),
        "language": str(item.get("language", "") or "").strip(),
        "topics": item.get("topics", []) if isinstance(item.get("topics"), list) else [],
        "updated_at": str(item.get("updated_at", "") or "").strip(),
        "pushed_at": str(item.get("pushed_at", "") or "").strip(),
        "default_branch": str(item.get("default_branch", "") or "").strip(),
        "archived": bool(item.get("archived", False)),
        "fork": bool(item.get("fork", False)),
        "query_hits": [str(query).strip()],
    }
    repo["quality_score"] = calc_repo_quality(repo)
    return repo


def repo_text_blob(repo: dict[str, Any]) -> str:
    parts: list[str] = [
        str(repo.get("full_name", "")).strip(),
        str(repo.get("description", "")).strip(),
        str(repo.get("language", "")).strip(),
    ]
    parts.extend(str(x).strip() for x in (repo.get("topics") or []) if str(x).strip())
    parts.extend(str(x).strip() for x in (repo.get("query_hits") or []) if str(x).strip())
    return " ".join(parts).lower()


def is_infrastructure_repo(repo: dict[str, Any]) -> bool:
    full_name = str(repo.get("full_name", "")).strip().lower()
    return full_name in INFRA_REPO_FULL_NAMES


def matches_project_scope(repo: dict[str, Any]) -> bool:
    blob = repo_text_blob(repo)
    return any(keyword in blob for keyword in PROJECT_SCOPE_KEYWORDS)


def build_query_list(raw_queries: list[str], min_stars: int, max_queries: int) -> list[str]:
    base = [str(x).strip() for x in raw_queries if str(x).strip()]
    if not base:
        base = list(DEFAULT_QUERY_PACK)

    out: list[str] = []
    for q in base[: max(1, int(max_queries))]:
        if "stars:" not in q:
            q = f"{q} stars:>={max(0, int(min_stars))}"
        out.append(q)
    return out


def normalize_repo_full_name(value: str) -> str:
    text = str(value or "").strip().lower()
    if text.count("/") != 1:
        return ""
    owner, repo = text.split("/", 1)
    if not owner or not repo:
        return ""
    return f"{owner}/{repo}"


def build_repo_scan_inputs(
    *,
    raw_queries: list[str],
    min_stars: int,
    max_queries: int,
    project_repo_targets: dict[str, Any] | None,
) -> dict[str, Any]:
    queries = build_query_list(raw_queries, min_stars, max_queries)
    seen_queries = {str(item).strip().lower() for item in queries}
    official_repos: list[str] = []
    seen_repos: set[str] = set()
    targets = project_repo_targets if isinstance(project_repo_targets, dict) else {}
    for raw_query in targets.get("queries", []):
        query = str(raw_query or "").strip()
        if not query:
            continue
        if "stars:" not in query:
            query = f"{query} stars:>={max(0, int(min_stars))}"
        key = query.lower()
        if key in seen_queries:
            continue
        seen_queries.add(key)
        queries.append(query)
    for raw_repo in targets.get("official_repos", []):
        full_name = normalize_repo_full_name(raw_repo)
        if not full_name or full_name in seen_repos:
            continue
        seen_repos.add(full_name)
        official_repos.append(full_name)
    return {"queries": queries, "official_repos": official_repos}


def build_skill_query_list(raw_queries: list[str], max_queries: int) -> list[str]:
    base = [str(x).strip() for x in raw_queries if str(x).strip()]
    if not base:
        base = list(DEFAULT_SKILL_QUERY_PACK)
    out: list[str] = []
    seen: set[str] = set()
    for query in base:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(query)
        if len(out) >= max(1, int(max_queries)):
            break
    return out


def resolve_skill4agent_bin(binary: str) -> str:
    candidate = str(binary or "skill4agent").strip() or "skill4agent"
    found = shutil.which(candidate)
    if found:
        return found
    home = Path.home()
    fallbacks = [
        home / ".npm-global" / "bin" / candidate,
        home / ".local" / "bin" / candidate,
        home / "node_modules" / ".bin" / candidate,
    ]
    for path in fallbacks:
        if path.exists() and path.is_file():
            return str(path)
    return ""


def skill_text_blob(skill: dict[str, Any]) -> str:
    parts = [
        str(skill.get("source", "")).strip(),
        str(skill.get("skillName", "")).strip(),
        str(skill.get("description", "")).strip(),
        str(skill.get("categoryName", "")).strip(),
    ]
    tags = skill.get("tags")
    if isinstance(tags, list):
        parts.extend(str(x).strip() for x in tags if str(x).strip())
    else:
        parts.extend(str(tags or "").split(","))
    parts.extend(str(x).strip() for x in (skill.get("query_hits") or []) if str(x).strip())
    return " ".join(parts).lower()


def matches_skill_scope(skill: dict[str, Any]) -> bool:
    blob = skill_text_blob(skill)
    return any(keyword in blob for keyword in SKILL_SCOPE_KEYWORDS)


def calc_skill_quality(skill: dict[str, Any]) -> int:
    installs = max(0, int(skill.get("totalInstalls", 0) or 0))
    relevance = max(0, int(skill.get("relevance", 0) or 0))
    translation = skill.get("translation", {}) if isinstance(skill.get("translation"), dict) else {}
    script = skill.get("script", {}) if isinstance(skill.get("script"), dict) else {}
    translation_bonus = 10 if bool(translation.get("has_translation")) else 0
    script_state = str(script.get("script_check_result", "")).strip().lower()
    if script_state == "safe":
        script_bonus = 8
    elif script_state == "need attention":
        script_bonus = -6
    else:
        script_bonus = 0
    return max(1, min(100, installs + (relevance * 20) + translation_bonus + script_bonus))


def normalize_skill4agent_item(item: dict[str, Any], query: str) -> dict[str, Any] | None:
    source = str(item.get("source", "")).strip()
    skill_name = str(item.get("skillName", "")).strip()
    if not source or not skill_name:
        return None
    tags_raw = item.get("tags")
    if isinstance(tags_raw, list):
        tags = [str(x).strip() for x in tags_raw if str(x).strip()]
    else:
        tags = [part.strip() for part in str(tags_raw or "").split(",") if part.strip()]
    row = {
        "full_name": f"skill4agent::{source}/{skill_name}",
        "display_name": f"{source}/{skill_name}",
        "source": source,
        "skillName": skill_name,
        "skillId": str(item.get("skillId", "")).strip(),
        "description": str(item.get("description", "") or "").strip(),
        "tags": tags,
        "categoryName": str(item.get("categoryName", "") or "").strip(),
        "totalInstalls": int(item.get("totalInstalls", 0) or 0),
        "relevance": int(item.get("relevance", 0) or 0),
        "translation": item.get("translation", {}) if isinstance(item.get("translation"), dict) else {},
        "script": item.get("script", {}) if isinstance(item.get("script"), dict) else {},
        "query_hits": [str(query).strip()],
    }
    row["quality_score"] = calc_skill_quality(row)
    return row


def search_skill4agent_skills(
    *,
    query: str,
    skill4agent_bin: str,
    limit: int,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    binary = str(skill4agent_bin or "skill4agent").strip() or "skill4agent"
    found_bin = resolve_skill4agent_bin(binary)
    if not found_bin:
        return [], {
            "ok": False,
            "query": query,
            "returned_count": 0,
            "total_results": 0,
            "error": f"skill4agent_not_found:{binary}",
        }

    cmd = [found_bin, "search", str(query).strip(), "-j", "-l", str(max(1, int(limit)))]
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
        return [], {
            "ok": False,
            "query": query,
            "returned_count": 0,
            "total_results": 0,
            "error": f"skill4agent_exec_failed:{exc}",
        }

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or f"exit={proc.returncode}"
        return [], {
            "ok": False,
            "query": query,
            "returned_count": 0,
            "total_results": 0,
            "error": f"skill4agent_failed:{err_text}",
        }
    if not isinstance(payload, dict):
        return [], {
            "ok": False,
            "query": query,
            "returned_count": 0,
            "total_results": 0,
            "error": "skill4agent_invalid_json_output",
        }

    skills = payload.get("skills", [])
    items = [item for item in skills if isinstance(item, dict)] if isinstance(skills, list) else []
    return items, {
        "ok": True,
        "query": query,
        "returned_count": len(items),
        "total_results": int(payload.get("totalResults", len(items)) or len(items)),
        "error": "",
    }


def merge_skill_results(
    *,
    query_results: list[tuple[str, list[dict[str, Any]]]],
    min_quality_score: int,
    max_total_skills: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for query, items in query_results:
        for item in items:
            skill = normalize_skill4agent_item(item, query=query)
            if skill is None:
                continue
            if not matches_skill_scope(skill):
                continue
            if int(skill.get("quality_score", 0) or 0) < max(1, int(min_quality_score)):
                continue
            key = str(skill.get("full_name", "")).strip().lower()
            old = merged.get(key)
            if old is None:
                merged[key] = skill
                continue
            query_hits = set(old.get("query_hits", []))
            query_hits.update(skill.get("query_hits", []))
            old["query_hits"] = sorted(str(x) for x in query_hits if str(x).strip())
            old["quality_score"] = max(int(old.get("quality_score", 0) or 0), int(skill.get("quality_score", 0) or 0))
            old["totalInstalls"] = max(int(old.get("totalInstalls", 0) or 0), int(skill.get("totalInstalls", 0) or 0))

    items_sorted = sorted(
        merged.values(),
        key=lambda x: (
            int(x.get("quality_score", 0) or 0),
            int(x.get("totalInstalls", 0) or 0),
            str(x.get("display_name", "")),
        ),
        reverse=True,
    )
    return items_sorted[: max(1, int(max_total_skills))]


def merge_query_results(
    *,
    query_results: list[tuple[str, list[dict[str, Any]]]],
    min_stars: int,
    min_quality_score: int,
    max_total_repos: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for query, items in query_results:
        for item in items:
            repo = normalize_repo_item(item, query=query)
            if repo is None:
                continue
            if repo.get("archived"):
                continue
            if is_infrastructure_repo(repo):
                continue
            if not matches_project_scope(repo):
                continue
            if int(repo.get("stargazers_count", 0) or 0) < max(0, int(min_stars)):
                continue
            if int(repo.get("quality_score", 0) or 0) < max(1, int(min_quality_score)):
                continue
            key = str(repo.get("full_name", "")).lower()
            old = merged.get(key)
            if old is None:
                merged[key] = repo
                continue
            query_hits = set(old.get("query_hits", []))
            query_hits.update(repo.get("query_hits", []))
            old["query_hits"] = sorted(str(x) for x in query_hits if str(x).strip())
            old["quality_score"] = max(int(old.get("quality_score", 0) or 0), int(repo.get("quality_score", 0) or 0))
            old["stargazers_count"] = max(int(old.get("stargazers_count", 0) or 0), int(repo.get("stargazers_count", 0) or 0))
            old["updated_at"] = str(repo.get("updated_at") or old.get("updated_at") or "")
            old["pushed_at"] = str(repo.get("pushed_at") or old.get("pushed_at") or "")

    items_sorted = sorted(
        merged.values(),
        key=lambda x: (
            int(x.get("quality_score", 0) or 0),
            int(x.get("stargazers_count", 0) or 0),
            str(x.get("pushed_at", "")),
        ),
        reverse=True,
    )
    return items_sorted[: max(1, int(max_total_repos))]


def upsert_selected_repo(rows: dict[str, dict[str, Any]], repo: dict[str, Any]) -> None:
    full_name = str(repo.get("full_name", "")).strip()
    if not full_name:
        return
    old = rows.get(full_name)
    if old is None:
        rows[full_name] = dict(repo)
        return
    query_hits = set(old.get("query_hits", []))
    query_hits.update(repo.get("query_hits", []))
    old["query_hits"] = sorted(str(x) for x in query_hits if str(x).strip())
    old["quality_score"] = max(int(old.get("quality_score", 0) or 0), int(repo.get("quality_score", 0) or 0))
    old["stargazers_count"] = max(int(old.get("stargazers_count", 0) or 0), int(repo.get("stargazers_count", 0) or 0))
    old["forks_count"] = max(int(old.get("forks_count", 0) or 0), int(repo.get("forks_count", 0) or 0))
    old["official_target"] = bool(old.get("official_target")) or bool(repo.get("official_target"))
    for field in ("html_url", "description", "language", "updated_at", "pushed_at", "default_branch"):
        if not str(old.get(field, "")).strip() and str(repo.get(field, "")).strip():
            old[field] = repo.get(field)


def merge_selected_repositories(
    *,
    selected: list[dict[str, Any]],
    official_repo_items: list[dict[str, Any]],
    max_total_repos: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in official_repo_items:
        full_name = str(item.get("full_name", "")).strip()
        repo = normalize_repo_item(item, query=f"official:{full_name}")
        if repo is None or repo.get("archived"):
            continue
        repo["official_target"] = True
        upsert_selected_repo(merged, repo)
    for repo in selected:
        upsert_selected_repo(merged, repo)
    items = sorted(
        merged.values(),
        key=lambda x: (
            0 if bool(x.get("official_target")) else 1,
            -int(x.get("quality_score", 0) or 0),
            -int(x.get("stargazers_count", 0) or 0),
            str(x.get("pushed_at", "")),
        ),
    )
    return items[: max(1, int(max_total_repos))]


def fetch_repo_readme(
    *,
    owner: str,
    repo: str,
    token: str,
    timeout: int,
    max_readme_bytes: int,
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    ok, payload, error = github_get_json(url=url, token=token, timeout=timeout)
    if not ok:
        return {"ok": False, "error": error, "text": "", "sha": "", "path": ""}

    content = str(payload.get("content", "") or "")
    encoding = str(payload.get("encoding", "") or "")
    text = ""
    if encoding.lower() == "base64" and content:
        try:
            raw = base64.b64decode(content.encode("utf-8"), validate=False)
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    if not text and str(payload.get("download_url", "")).strip():
        dl = str(payload.get("download_url", "")).strip()
        req = urllib.request.Request(dl, headers={"User-Agent": "openclaw-github-web-evolution"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=max(5, int(timeout))) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    text = text[: max(1024, int(max_readme_bytes))]
    return {
        "ok": True,
        "error": "",
        "text": text,
        "sha": str(payload.get("sha", "") or "").strip(),
        "path": str(payload.get("path", "README.md") or "README.md").strip(),
    }


def normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:220]


def extract_method_lines(readme_text: str, max_lines: int) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in str(readme_text or "").splitlines():
        line = normalize_line(raw)
        if not line or len(line) < 12:
            continue
        low = line.lower()
        if not any(k in low for k in METHOD_KEYWORDS):
            continue
        if low in seen:
            continue
        seen.add(low)
        lines.append(line)
        if len(lines) >= max(1, int(max_lines)):
            break
    return lines


def repo_slug(full_name: str) -> str:
    return (
        str(full_name or "")
        .replace("/", "__")
        .replace("\\", "__")
        .replace(":", "__")
        .replace("?", "_")
        .replace("*", "_")
        .replace("\"", "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
    )


def load_index(index_file: Path) -> dict[str, Any]:
    data = load_json(index_file, None)
    if not isinstance(data, dict):
        data = {}
    repos = data.get("repos")
    if not isinstance(repos, dict):
        repos = {}
    skills = data.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    return {
        "schema_version": str(data.get("schema_version", "2026-03-09")),
        "updated_at": str(data.get("updated_at", "")),
        "repos": repos,
        "skills": skills,
    }


def write_catalog_markdown(index_payload: dict[str, Any], out_file: Path) -> None:
    repos = index_payload.get("repos", {}) if isinstance(index_payload.get("repos"), dict) else {}
    skills = index_payload.get("skills", {}) if isinstance(index_payload.get("skills"), dict) else {}
    items: list[dict[str, Any]] = []
    for full_name, payload in repos.items():
        if not isinstance(payload, dict):
            continue
        row = dict(payload)
        row["full_name"] = full_name
        items.append(row)
    skill_items: list[dict[str, Any]] = []
    for full_name, payload in skills.items():
        if not isinstance(payload, dict):
            continue
        row = dict(payload)
        row["full_name"] = full_name
        skill_items.append(row)

    items.sort(
        key=lambda x: (
            int(x.get("quality_score", 0) or 0),
            int(x.get("stargazers_count", 0) or 0),
            str(x.get("pushed_at", "")),
        ),
        reverse=True,
    )

    lines = [
        "# GitHub Knowledge Catalog",
        "",
        f"- updated_at: {index_payload.get('updated_at', '')}",
        f"- total_repos: {len(items)}",
        f"- total_skills: {len(skill_items)}",
        "",
        "## Repositories",
        "",
    ]
    for item in items[:400]:
        full_name = str(item.get("full_name", ""))
        html_url = str(item.get("html_url", ""))
        lines.append(
            "- "
            + f"[{full_name}]({html_url}) "
            + f"score={int(item.get('quality_score', 0) or 0)} "
            + f"stars={int(item.get('stargazers_count', 0) or 0)} "
            + f"pushed={item.get('pushed_at', '')}"
        )
    lines.extend(["", "## Skills", ""])
    for item in sorted(
        skill_items,
        key=lambda x: (
            int(x.get("quality_score", 0) or 0),
            int(x.get("totalInstalls", 0) or 0),
            str(x.get("display_name", "")),
        ),
        reverse=True,
    )[:200]:
        lines.append(
            "- "
            + f"{item.get('display_name', item.get('full_name', ''))} "
            + f"score={int(item.get('quality_score', 0) or 0)} "
            + f"installs={int(item.get('totalInstalls', 0) or 0)} "
            + f"source={item.get('source', '')}"
        )
    save_text(out_file, "\n".join(lines) + "\n")

def fingerprint_from_changes(changes: list[dict[str, Any]]) -> str:
    raw = [
        {
            "full_name": str(x.get("full_name", "")).lower(),
            "change_type": str(x.get("change_type", "")),
            "pushed_at": str(x.get("pushed_at", "")),
            "readme_sha": str(x.get("readme_sha", "")),
        }
        for x in changes
    ]
    digest = hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def dedupe_key_from_changes(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return ""
    raw = sorted(str(x.get("full_name", "")).lower() for x in changes)
    return hashlib.sha1(json.dumps(raw, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def split_changes_for_tasks(
    changes: list[dict[str, Any]],
    *,
    max_tasks_per_run: int,
    min_changes_per_task: int,
) -> list[list[dict[str, Any]]]:
    n = len(changes)
    if n <= 0:
        return []
    min_size = max(1, int(min_changes_per_task))
    max_tasks = max(1, int(max_tasks_per_run))
    feasible_tasks = max(1, n // min_size)
    task_count = min(max_tasks, feasible_tasks)
    if task_count <= 1:
        return [list(changes)]

    base = n // task_count
    rem = n % task_count
    out: list[list[dict[str, Any]]] = []
    cursor = 0
    for i in range(task_count):
        size = base + (1 if i < rem else 0)
        part = changes[cursor : cursor + size]
        if part:
            out.append(part)
        cursor += size
    return out if out else [list(changes)]


def parse_marker(text: str, marker: str) -> str:
    pattern = rf"\[{re.escape(str(marker or '').strip())}:([a-f0-9]{{8,64}})\]"
    m = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    return str(m.group(1)).lower() if m else ""


def collect_open_markers(tc: TaskCenter, marker: str) -> set[str]:
    rows = tc.conn.execute(
        """
        SELECT requirement
        FROM tasks
        WHERE source = 'github-web-evolution-agent'
          AND pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        val = parse_marker(str(row["requirement"] or ""), marker)
        if val:
            out.add(val)
    return out


def collect_recent_marker(tc: TaskCenter, marker: str, recent_days: int) -> set[str]:
    days = max(0, int(recent_days))
    if days <= 0:
        return set()
    cutoff = now() - timedelta(days=days)
    rows = tc.conn.execute(
        """
        SELECT requirement, created_at
        FROM tasks
        WHERE source = 'github-web-evolution-agent'
          AND pool = 'todo'
        ORDER BY created_at DESC
        LIMIT 5000
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        created_at = parse_iso(str(row["created_at"] or ""))
        if created_at and created_at < cutoff:
            continue
        val = parse_marker(str(row["requirement"] or ""), marker)
        if val:
            out.add(val)
    return out


def infer_next_schedule_base(tc: TaskCenter) -> datetime:
    row = tc.conn.execute(
        """
        SELECT scheduled_at, created_at
        FROM tasks
        WHERE pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        ORDER BY COALESCE(scheduled_at, created_at) DESC, created_at DESC
        LIMIT 1
        """
    ).fetchone()
    base = now()
    if row:
        chosen = parse_iso(str(row["scheduled_at"] or row["created_at"] or ""))
        if chosen and chosen > base:
            base = chosen
    return base


def create_todo_task(
    *,
    tc: TaskCenter,
    fingerprint: str,
    dedupe_key: str,
    assignee: str,
    schedule_gap_minutes: int,
    report_file: Path,
    catalog_file: Path,
    changes: list[dict[str, Any]],
    query_list: list[str],
    recent_dedupe_days: int,
) -> dict[str, Any] | None:
    open_fps = collect_open_markers(tc, marker="fingerprint")
    if fingerprint in open_fps:
        return None

    recent_keys = collect_recent_marker(tc, marker="dedupe_key", recent_days=recent_dedupe_days)
    if dedupe_key and dedupe_key in recent_keys:
        return None

    who = str(assignee or "").strip() or "optimization-agent"
    constraint_fields = build_task_constraint_fields(who)
    base = infer_next_schedule_base(tc)
    schedule_at = (base + timedelta(minutes=max(1, int(schedule_gap_minutes)))).replace(microsecond=0).isoformat()

    lines = [
        f"[fingerprint:{fingerprint}]",
        f"[dedupe_key:{dedupe_key}]",
        f"Web evolution report: {report_file}",
        f"Web evolution catalog: {catalog_file}",
        "",
        "Incremental changes (new/updated repositories or skills):",
    ]
    for item in changes[:40]:
        if str(item.get("entity_type", "")) == "skill":
            lines.append(
                "- "
                + f"{item.get('change_type', 'updated')} skill "
                + f"{item.get('display_name', item.get('full_name', ''))} "
                + f"score={int(item.get('quality_score', 0) or 0)} "
                + f"installs={int(item.get('stargazers_count', 0) or 0)} "
                + f"source={item.get('source', '')}"
            )
        else:
            lines.append(
                "- "
                + f"{item.get('change_type', 'updated')} repo "
                + f"{item.get('full_name', '')} "
                + f"score={int(item.get('quality_score', 0) or 0)} "
                + f"stars={int(item.get('stargazers_count', 0) or 0)} "
                + f"url={item.get('html_url', '')}"
            )
    lines.extend(
        [
            "",
            "Search queries used:",
            *[f"- {q}" for q in query_list[:20]],
            "",
            "Output requirements:",
            "- Propose high-value improvements for openclaw workflow/skills/routing based on these repositories and skills.",
            "- Mark uncertain items that require project-agent context package first.",
            "- Keep only executable, evidence-backed changes with validation and rollback.",
            "- If code change is approved, follow governance evolution flow (optimize -> reviewer -> PR).",
        ]
    )

    payload = {
        "task_id": f"todo-github-web-evolution-{now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "pool": "todo",
        "task_type": "github_web_evolution",
        "reason": f"[WEB_EVOLUTION] new_or_updated={len(changes)}",
        "source": "github-web-evolution-agent",
        "request_source": "ai",
        "priority": "low",
        "risk_level": "high",
        "assignee": who,
        **constraint_fields,
        "status": "pending",
        "need_human_confirm": True,
        "human_confirmed": False,
        "requirement": "\n".join(lines),
        "result_output": "Output structured optimization proposals and change plan. Do not execute high-risk changes directly.",
        "acceptance": "At least one actionable improvement with evidence, validation steps, and rollback path.",
        "observable_outputs": "Task center record, optimization checklist, validation commands.",
        "acceptance_thresholds": "Contains clear scope, risk notes, and reproducible verification commands.",
        "scheduled_at": schedule_at,
    }
    task = tc.create_task(payload, actor="github-web-evolution-agent")
    tc.add_event(
        task_id=task["task_id"],
        actor="github-web-evolution-agent",
        event_type="github_web_evolution_task_packaged",
        stage="web_scan",
        details={
            "fingerprint": fingerprint,
            "dedupe_key": dedupe_key,
            "scheduled_at": schedule_at,
            "changes_count": len(changes),
        },
    )
    return {
        "task_id": task["task_id"],
        "fingerprint": fingerprint,
        "dedupe_key": dedupe_key,
        "scheduled_at": schedule_at,
        "assignee": who,
    }

def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="GitHub web evolution incremental runner")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--web-root", default="")
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/github-web-evolution/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/github-web-evolution/reports"))
    parser.add_argument("--project-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--min-interval-minutes", type=int, default=360)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--max-queries", type=int, default=5)
    parser.add_argument("--max-repos-per-query", type=int, default=20)
    parser.add_argument("--max-total-repos", type=int, default=40)
    parser.add_argument("--max-readme-repos", type=int, default=25)
    parser.add_argument("--readme-max-bytes", type=int, default=120000)
    parser.add_argument("--method-lines-per-repo", type=int, default=24)
    parser.add_argument("--min-stars", type=int, default=80)
    parser.add_argument("--min-quality-score", type=int, default=45)
    parser.add_argument("--enable-skill4agent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skill4agent-bin", default="skill4agent")
    parser.add_argument("--skill4agent-query", action="append", default=[])
    parser.add_argument("--skill4agent-max-queries", type=int, default=5)
    parser.add_argument("--skill4agent-limit", type=int, default=12)
    parser.add_argument("--skill4agent-max-total-skills", type=int, default=20)
    parser.add_argument("--skill4agent-min-quality-score", type=int, default=20)
    parser.add_argument("--skill4agent-timeout", type=int, default=35)
    parser.add_argument("--min-new-or-updated", type=int, default=2)
    parser.add_argument("--recent-dedupe-days", type=int, default=14)
    parser.add_argument("--max-tasks-per-run", type=int, default=1)
    parser.add_argument("--schedule-gap-minutes", type=int, default=90)
    parser.add_argument("--assignee", default="optimization-agent")
    parser.add_argument("--github-token-env", default=DEFAULT_GITHUB_TOKEN_ENV)
    parser.add_argument("--http-timeout", type=int, default=25)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    openclaw_home = Path(args.openclaw_home).expanduser()
    web_root = Path(args.web_root).expanduser() if str(args.web_root).strip() else (openclaw_home / "web" / "github")
    report_dir = Path(args.report_dir).expanduser()
    state_file = Path(args.state_file).expanduser()

    repos_dir = web_root / "repos"
    skills_dir = web_root / "skills"
    readmes_dir = web_root / "readmes"
    methods_dir = web_root / "methods"
    runs_dir = web_root / "runs"
    index_file = web_root / "index.json"
    catalog_file = web_root / "CATALOG.md"

    for p in [report_dir, repos_dir, skills_dir, readmes_dir, methods_dir, runs_dir]:
        p.mkdir(parents=True, exist_ok=True)

    state = load_json(state_file, None)
    if not isinstance(state, dict):
        state = state_default()

    run_allowed = should_run(
        last_scan_at=str(state.get("last_scan_at", "")),
        min_interval_minutes=max(1, int(args.min_interval_minutes)),
        force=bool(args.force),
    )

    sender_identity = normalize_sender_identity(args.sender_identity)
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    github_token = str(os.environ.get(str(args.github_token_env or DEFAULT_GITHUB_TOKEN_ENV), "") or "").strip()
    project_registry = Path(args.project_registry).expanduser() if str(args.project_registry).strip() else None
    project_repo_targets = load_project_repo_targets(project_registry)
    repo_scan_inputs = build_repo_scan_inputs(
        raw_queries=[str(x) for x in args.query],
        min_stars=max(0, int(args.min_stars)),
        max_queries=max(1, int(args.max_queries)),
        project_repo_targets=project_repo_targets,
    )
    query_list = list(repo_scan_inputs.get("queries", []))
    project_official_repos = list(repo_scan_inputs.get("official_repos", []))
    skill_query_list = build_skill_query_list(
        raw_queries=[str(x) for x in args.skill4agent_query],
        max_queries=max(1, int(args.skill4agent_max_queries)),
    )

    query_logs: list[dict[str, Any]] = []
    query_results: list[tuple[str, list[dict[str, Any]]]] = []
    selected: list[dict[str, Any]] = []
    official_repo_logs: list[dict[str, Any]] = []
    skill_query_logs: list[dict[str, Any]] = []
    skill_query_results: list[tuple[str, list[dict[str, Any]]]] = []
    selected_skills: list[dict[str, Any]] = []
    readme_fetch: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    created_tasks: list[dict[str, Any]] = []
    task_skipped_reason = ""
    run_errors: list[str] = []

    index_payload = load_index(index_file)
    previous_repos = index_payload.get("repos", {}) if isinstance(index_payload.get("repos"), dict) else {}
    previous_skills = index_payload.get("skills", {}) if isinstance(index_payload.get("skills"), dict) else {}
    skill4agent_bin = str(args.skill4agent_bin or "skill4agent").strip() or "skill4agent"
    skill4agent_resolved_bin = resolve_skill4agent_bin(skill4agent_bin)
    skill4agent_available = bool(skill4agent_resolved_bin)

    run_id = uuid.uuid4().hex[:12]
    run_stamp = now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / f"{run_stamp}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        if run_allowed:
            for q in query_list:
                items, qlog = github_search_repositories(
                    query=q,
                    token=github_token,
                    per_page=max(1, int(args.max_repos_per_query)),
                    timeout=max(5, int(args.http_timeout)),
                )
                query_logs.append(qlog)
                query_results.append((q, items))

            official_repo_items: list[dict[str, Any]] = []
            for full_name in project_official_repos:
                payload, error = github_get_repository(
                    full_name=full_name,
                    token=github_token,
                    timeout=max(5, int(args.http_timeout)),
                )
                official_repo_logs.append(
                    {
                        "full_name": full_name,
                        "ok": payload is not None,
                        "error": error,
                    }
                )
                if isinstance(payload, dict):
                    official_repo_items.append(payload)

            selected = merge_query_results(
                query_results=query_results,
                min_stars=max(0, int(args.min_stars)),
                min_quality_score=max(1, int(args.min_quality_score)),
                max_total_repos=max(1, int(args.max_total_repos)),
            )
            selected = merge_selected_repositories(
                selected=selected,
                official_repo_items=official_repo_items,
                max_total_repos=max(1, int(args.max_total_repos)),
            )

            max_readme = max(0, int(args.max_readme_repos))
            for repo in selected[:max_readme]:
                full_name = str(repo.get("full_name", ""))
                slug = repo_slug(full_name)
                owner = str(repo.get("owner", ""))
                name = str(repo.get("name", ""))
                readme_info = fetch_repo_readme(
                    owner=owner,
                    repo=name,
                    token=github_token,
                    timeout=max(5, int(args.http_timeout)),
                    max_readme_bytes=max(4096, int(args.readme_max_bytes)),
                )
                readme_fetch.append({"full_name": full_name, **{k: v for k, v in readme_info.items() if k != "text"}})

                methods = extract_method_lines(
                    readme_text=str(readme_info.get("text", "")),
                    max_lines=max(1, int(args.method_lines_per_repo)),
                )
                readme_file = readmes_dir / f"{slug}.md"
                methods_file = methods_dir / f"{slug}.md"
                meta_file = repos_dir / f"{slug}.json"

                if str(readme_info.get("text", "")).strip():
                    save_text(readme_file, str(readme_info.get("text", "")) + "\n")
                if methods:
                    save_text(
                        methods_file,
                        "# Method Snippets\n\n" + "\n".join(f"- {x}" for x in methods) + "\n",
                    )

                prev = previous_repos.get(full_name, {}) if isinstance(previous_repos.get(full_name), dict) else {}
                prev_pushed = str(prev.get("pushed_at", ""))
                prev_sha = str(prev.get("readme_sha", ""))
                prev_stars = int(prev.get("stargazers_count", 0) or 0)

                readme_sha = str(readme_info.get("sha", ""))
                if not readme_sha and str(readme_info.get("text", "")).strip():
                    readme_sha = hashlib.sha1(str(readme_info.get("text", "")).encode("utf-8", errors="ignore")).hexdigest()[:16]

                repo_row = {
                    **repo,
                    "readme_sha": readme_sha,
                    "readme_path": str(readme_info.get("path", "")),
                    "readme_file": str(readme_file),
                    "methods_file": str(methods_file),
                    "methods_count": len(methods),
                    "last_seen_at": now_iso(),
                }
                save_json(meta_file, repo_row)
                previous_repos[full_name] = repo_row

                change_type = ""
                change_flags: list[str] = []
                if not prev:
                    change_type = "new"
                else:
                    if str(repo.get("pushed_at", "")) != prev_pushed:
                        change_flags.append("pushed_at")
                    if readme_sha and readme_sha != prev_sha:
                        change_flags.append("readme")
                    if int(repo.get("stargazers_count", 0) or 0) != prev_stars:
                        change_flags.append("stars")
                    if change_flags:
                        change_type = "updated"

                if change_type:
                    changes.append(
                        {
                            "change_type": change_type,
                            "change_flags": change_flags,
                            "entity_type": "repo",
                            "full_name": full_name,
                            "html_url": str(repo.get("html_url", "")),
                            "quality_score": int(repo.get("quality_score", 0) or 0),
                            "stargazers_count": int(repo.get("stargazers_count", 0) or 0),
                            "pushed_at": str(repo.get("pushed_at", "")),
                            "readme_sha": readme_sha,
                            "meta_file": str(meta_file),
                            "readme_file": str(readme_file),
                            "methods_file": str(methods_file),
                        }
                    )

            if bool(args.enable_skill4agent):
                if skill4agent_available:
                    for query in skill_query_list:
                        items, slog = search_skill4agent_skills(
                            query=query,
                            skill4agent_bin=skill4agent_resolved_bin or skill4agent_bin,
                            limit=max(1, int(args.skill4agent_limit)),
                            timeout=max(5, int(args.skill4agent_timeout)),
                        )
                        skill_query_logs.append(slog)
                        skill_query_results.append((query, items))

                    selected_skills = merge_skill_results(
                        query_results=skill_query_results,
                        min_quality_score=max(1, int(args.skill4agent_min_quality_score)),
                        max_total_skills=max(1, int(args.skill4agent_max_total_skills)),
                    )

                    for skill in selected_skills:
                        full_name = str(skill.get("full_name", "")).strip()
                        slug = repo_slug(full_name)
                        meta_file = skills_dir / f"{slug}.json"
                        prev = previous_skills.get(full_name, {}) if isinstance(previous_skills.get(full_name), dict) else {}
                        prev_installs = int(prev.get("totalInstalls", 0) or 0)
                        prev_fingerprint = str(prev.get("skill_fingerprint", "") or "")

                        skill_fingerprint = hashlib.sha1(
                            json.dumps(
                                {
                                    "description": str(skill.get("description", "")),
                                    "tags": skill.get("tags", []),
                                    "categoryName": str(skill.get("categoryName", "")),
                                    "script": skill.get("script", {}),
                                    "translation": skill.get("translation", {}),
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            ).encode("utf-8")
                        ).hexdigest()[:16]

                        skill_row = {
                            **skill,
                            "skill_fingerprint": skill_fingerprint,
                            "meta_file": str(meta_file),
                            "last_seen_at": now_iso(),
                        }
                        save_json(meta_file, skill_row)
                        previous_skills[full_name] = skill_row

                        change_type = ""
                        change_flags: list[str] = []
                        if not prev:
                            change_type = "new"
                        else:
                            if int(skill.get("totalInstalls", 0) or 0) != prev_installs:
                                change_flags.append("installs")
                            if skill_fingerprint and skill_fingerprint != prev_fingerprint:
                                change_flags.append("skill_payload")
                            if change_flags:
                                change_type = "updated"

                        if change_type:
                            changes.append(
                                {
                                    "change_type": change_type,
                                    "change_flags": change_flags,
                                    "entity_type": "skill",
                                    "full_name": full_name,
                                    "display_name": str(skill.get("display_name", "")),
                                    "source": str(skill.get("source", "")),
                                    "skill_name": str(skill.get("skillName", "")),
                                    "html_url": "",
                                    "quality_score": int(skill.get("quality_score", 0) or 0),
                                    "stargazers_count": int(skill.get("totalInstalls", 0) or 0),
                                    "pushed_at": str(skill_row.get("last_seen_at", "")),
                                    "readme_sha": skill_fingerprint,
                                    "meta_file": str(meta_file),
                                    "readme_file": "",
                                    "methods_file": "",
                                }
                            )
                else:
                    skill_query_logs.append(
                        {
                            "ok": False,
                            "query": "",
                            "returned_count": 0,
                            "total_results": 0,
                            "error": f"skill4agent_not_found:{skill4agent_bin}",
                        }
                    )

            index_payload["repos"] = previous_repos
            index_payload["skills"] = previous_skills
            index_payload["updated_at"] = now_iso()
            save_json(index_file, index_payload)
            write_catalog_markdown(index_payload, catalog_file)
    except Exception as exc:
        run_errors.append(f"github_web_collect_failed:{exc}")

    fingerprint = fingerprint_from_changes(changes) if changes else ""
    dedupe_key = dedupe_key_from_changes(changes)
    candidate_batches: list[list[dict[str, Any]]] = []
    task_query_list = list(query_list) + [f"skill4agent:{query}" for query in skill_query_list]

    try:
        save_json(run_dir / "queries.json", {"queries": query_list, "logs": query_logs})
        save_json(
            run_dir / "project_repo_targets.json",
            {
                "project_registry": str(project_registry) if project_registry is not None else "",
                "queries": list(project_repo_targets.get("queries", [])),
                "official_repos": project_official_repos,
                "official_repo_logs": official_repo_logs,
            },
        )
        save_json(run_dir / "skill_queries.json", {"queries": skill_query_list, "logs": skill_query_logs})
        save_json(run_dir / "selected_repositories.json", {"count": len(selected), "items": selected})
        save_json(run_dir / "selected_skills.json", {"count": len(selected_skills), "items": selected_skills})
        save_json(run_dir / "changes.json", {"count": len(changes), "items": changes})

        if run_allowed and len(changes) >= max(1, int(args.min_new_or_updated)):
            candidate_batches = split_changes_for_tasks(
                changes,
                max_tasks_per_run=max(1, int(args.max_tasks_per_run)),
                min_changes_per_task=max(1, int(args.min_new_or_updated)),
            )
            tc = TaskCenter(Path(args.db).expanduser())
            try:
                tc.init_schema()
                for batch in candidate_batches:
                    fp = fingerprint_from_changes(batch)
                    if not fp:
                        continue
                    dk = dedupe_key_from_changes(batch)
                    created = create_todo_task(
                        tc=tc,
                        fingerprint=fp,
                        dedupe_key=dk,
                        assignee=str(args.assignee or "optimization-agent").strip() or "optimization-agent",
                        schedule_gap_minutes=max(1, int(args.schedule_gap_minutes)),
                        report_file=Path("<pending>"),
                        catalog_file=catalog_file,
                        changes=batch,
                        query_list=task_query_list,
                        recent_dedupe_days=max(0, int(args.recent_dedupe_days)),
                    )
                    if created:
                        created_tasks.append(created)
                if created_tasks:
                    task_skipped_reason = "" if len(created_tasks) == len(candidate_batches) else "partially_duplicate_or_open"
                else:
                    task_skipped_reason = "already_open_or_duplicate_recent"
            finally:
                tc.close()
        elif run_allowed and len(changes) < max(1, int(args.min_new_or_updated)):
            task_skipped_reason = "changes_below_threshold"
    except Exception as exc:
        run_errors.append(f"github_web_package_failed:{exc}")

    report_file = report_dir / f"{run_stamp}_{run_id}.json"
    if created_tasks:
        tc = TaskCenter(Path(args.db).expanduser())
        try:
            for item in created_tasks:
                task_id = str(item.get("task_id", ""))
                if not task_id:
                    continue
                row = tc.get_task(task_id)
                if not isinstance(row, dict):
                    continue
                requirement = str(row.get("requirement", "")).replace("<pending>", str(report_file))
                tc.update_task(task_id, actor="github-web-evolution-agent", fields={"requirement": requirement})
        except Exception as exc:
            run_errors.append(f"github_web_requirement_update_failed:{exc}")
        finally:
            tc.close()

    report = {
        "run_id": run_id,
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "normal_log_mode": log_mode,
        "openclaw_home": str(openclaw_home),
        "web_root": str(web_root),
        "run_dir": str(run_dir),
        "state_file": str(state_file),
        "run_allowed": run_allowed,
        "github_token_present": bool(github_token),
        "github_token_env": str(args.github_token_env or DEFAULT_GITHUB_TOKEN_ENV),
        "project_registry": str(project_registry) if project_registry is not None else "",
        "project_repo_queries": list(project_repo_targets.get("queries", [])),
        "project_official_repos": project_official_repos,
        "official_repo_logs": official_repo_logs,
        "queries": query_list,
        "query_logs": query_logs,
        "skill4agent_enabled": bool(args.enable_skill4agent),
        "skill4agent_bin": skill4agent_bin,
        "skill4agent_resolved_bin": skill4agent_resolved_bin,
        "skill4agent_available": bool(skill4agent_available),
        "skill_queries": skill_query_list,
        "skill_query_logs": skill_query_logs,
        "selected_count": len(selected),
        "selected": selected[:200],
        "selected_skill_count": len(selected_skills),
        "selected_skills": selected_skills[:200],
        "readme_fetch": readme_fetch[:200],
        "changes_count": len(changes),
        "changes": changes[:300],
        "repo_changes_count": len([x for x in changes if str(x.get("entity_type", "")) != "skill"]),
        "skill_changes_count": len([x for x in changes if str(x.get("entity_type", "")) == "skill"]),
        "new_count": len([x for x in changes if str(x.get("change_type")) == "new"]),
        "updated_count": len([x for x in changes if str(x.get("change_type")) == "updated"]),
        "task_threshold_min_new_or_updated": max(1, int(args.min_new_or_updated)),
        "task_max_tasks_per_run": max(1, int(args.max_tasks_per_run)),
        "task_candidate_batch_count": len(candidate_batches),
        "task_candidate_batch_sizes": [len(x) for x in candidate_batches],
        "task_created_count": len(created_tasks),
        "task_created": created_tasks,
        "task_skipped_reason": task_skipped_reason,
        "fingerprint": fingerprint,
        "dedupe_key": dedupe_key,
        "catalog_file": str(catalog_file),
        "index_file": str(index_file),
        "run_errors": run_errors,
    }

    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms

    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    db_file = Path(args.db).expanduser()
    if db_file.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_file)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_file,
                raw_task_id,
                "github-web-evolution-agent",
                "optimization-agent/github-web-evolution",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        module_args = [
            "log-module",
            "--module-name",
            "optimization-agent/github-web-evolution",
            "--phase",
            "web_scan",
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            (
                "github web evolution run finished: "
                + f"selected={len(selected)} changed={len(changes)} created={len(created_tasks)}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "run_allowed": bool(run_allowed),
                    "query_count": len(query_list),
                    "selected_count": len(selected),
                    "changes_count": len(changes),
                    "created_task_count": len(created_tasks),
                    "run_error_count": len(run_errors),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "github-web-evolution-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(db_file, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "optimization-agent/github-web-evolution",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "github_web_evolution_result",
            "--status",
            ("failed" if run_errors else "acked"),
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(run_id),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "dedupe_key": dedupe_key,
                    "task_created_count": len(created_tasks),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "github-web-evolution-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_file, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        report_count = 0
        if bound_task_id:
            runtime_quality = 70.0 if run_errors else 90.0
            runtime_report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "github-web-evolution-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("failed" if run_errors else "passed"),
                "--solved",
                ("false" if run_errors else "true"),
                "--resolved-issues",
                "github_web_evolution_runtime_recorded",
                "--resolution-summary",
                (
                    "github web evolution run recorded"
                    if not run_errors
                    else "github web evolution run recorded with runtime exceptions"
                ),
                "--resolution-steps",
                "search_github,extract_readme_methods,detect_changes,record_runtime_observability",
                "--failed-items",
                ",".join(run_errors[:20]),
                "--failure-count",
                str(len(run_errors)),
                "--duration-ms",
                str(run_duration_ms),
                "--input-tokens",
                "0",
                "--output-tokens",
                "0",
                "--cost-estimate",
                "0",
                "--quality-score",
                str(round(runtime_quality, 2)),
                "--quality-grade",
                ("c" if run_errors else "a"),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": run_id,
                        "fingerprint": fingerprint,
                        "dedupe_key": dedupe_key,
                        "created_task_count": len(created_tasks),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "github-web-evolution-agent",
            ]
            ok_runtime_report, _payload_runtime_report, err_runtime_report = invoke_policy_enforcer(
                db_file,
                runtime_report_args,
                timeout=35,
            )
            if ok_runtime_report:
                report_count += 1
            elif err_runtime_report:
                policy_observability["errors"].append(err_runtime_report)
        policy_observability["report_agent_result_count"] = report_count

        since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            db_file,
            ["planner-summary", "--planner-id", "coordinator", "--since", since_24h, "--limit", "60"],
            timeout=30,
        )
        policy_observability["planner_summary_ok"] = ok_summary
        if ok_summary and isinstance(payload_summary, dict):
            summary = payload_summary.get("summary")
            if isinstance(summary, dict):
                planner_summary_snapshot = {
                    "planner_id": summary.get("planner_id"),
                    "report_count": summary.get("report_count", 0),
                    "task_count": summary.get("task_count", 0),
                    "resolved_task_count": summary.get("resolved_task_count", 0),
                    "failed_task_count": summary.get("failed_task_count", 0),
                    "solved_ratio_pct": summary.get("solved_ratio_pct", 0.0),
                    "total_tokens": summary.get("total_tokens", 0),
                    "total_cost_estimate": summary.get("total_cost_estimate", 0.0),
                }
        if (not ok_summary) and err_summary:
            policy_observability["errors"].append(err_summary)

    report["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        report["planner_summary"] = planner_summary_snapshot
    save_json(report_file, report)

    state["runs"] = int(state.get("runs", 0)) + 1
    state["updated_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    if run_allowed:
        state["last_scan_at"] = now_iso()
    fps = state.get("fingerprints")
    if not isinstance(fps, dict):
        fps = {}
    if fingerprint:
        fps[fingerprint] = {
            "time": now_iso(),
            "changes_count": len(changes),
            "report_file": str(report_file),
            "task_created_count": len(created_tasks),
        }
    state["fingerprints"] = fps
    save_json(state_file, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(exception_reasons)

    output = "NO_REPLY"
    if notify:
        detail_lines = [
            f"变更样例{idx}：{item.get('full_name', '')}，类型 {item.get('change_type', 'updated')}，质量分 {int(item.get('quality_score', 0) or 0)}"
            for idx, item in enumerate(changes[:12], start=1)
        ]
        output = render_chat_notice(
            "GitHub 情报巡检异常",
            status="需关注",
            task_id=str(args.task_id or ""),
            sender_identity=sender_identity,
            run_time=now_iso(),
            trace_id=build_trace_id(report_file=report_file),
            summary=f"GitHub 情报巡检发现 {len(exception_reasons)} 个异常，并生成 {len(created_tasks)} 条建议任务。",
            extra_lines=[
                f"允许执行：{'是' if run_allowed else '否'}",
                f"查询词：{len(query_list)} 组",
                f"入选仓库：{len(selected)} 个",
                f"入选技能：{len(selected_skills)} 个",
                f"变化项：{len(changes)} 项（新增 {report['new_count']} 项，更新 {report['updated_count']} 项，技能变化 {report['skill_changes_count']} 项）",
                f"新建建议任务：{len(created_tasks)} 项",
                f"跳过原因：{task_skipped_reason or '无'}",
                f"异常数量：{len(exception_reasons)} 项",
            ],
            details=detail_lines,
            next_step="请按留痕编号查看详细采集报告，并确认是否纳入后续优化。",
        )

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(output)
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

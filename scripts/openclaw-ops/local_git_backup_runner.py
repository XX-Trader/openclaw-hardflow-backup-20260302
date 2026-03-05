#!/usr/bin/env python3
"""Local git backup runner for ~/.openclaw (commit only, no push)."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}

DEFAULT_INCLUDE_PREFIXES = (
    "openclaw.json",
    ".gitignore",
    ".workflow/",
    "agents/",
    "cron/",
    "ops/",
    "hooks/",
    "workflows/",
    ".skill-index.json",
    ".skill-master-index.json",
    ".skill-aliases.json",
)

DEFAULT_EXCLUDE_GLOBS = (
    "**/.git/**",
    ".git/**",
    "**/.locks/**",
    "ops/.locks/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    "ops/cron-backup/**",
    "ops/*-runs/**",
    "ops/*-reports/**",
    "ops/*/reports/**",
    "ops/task-center/**/*.db*",
    "ops/task-center/*.db*",
    "ops/task-center/*.sqlite*",
    "workspace-*/logs/**",
    "workspace-*/sessions/**",
    "workspace-*/downloads/**",
    "workspace-*/tmp/**",
    "workspace-*/.codex/**",
    "agents/*/sessions/**",
    "agents/*/sessions.json",
    "cron/runs/**",
    "cron/jobs.json.bak*",
    "openclaw.json.bak*",
    "browser/**",
    "*.log",
    "**/*.log",
)

DEFAULT_GITIGNORE_LINES = (
    "# openclaw local backup (auto)",
    "*.log",
    "**/*.log",
    ".DS_Store",
    "Thumbs.db",
    "**/.locks/",
    "ops/cron-backup/",
    "__pycache__/",
    "*.pyc",
    "ops/*-runs/",
    "ops/*-reports/",
    "ops/task-center/*.db*",
    "workspace-*/logs/",
    "workspace-*/sessions/",
    "workspace-*/downloads/",
    "workspace-*/tmp/",
    "workspace-*/.codex/",
    "agents/*/sessions/",
    "cron/runs/",
    "cron/jobs.json.bak*",
    "openclaw.json.bak*",
    "browser/",
)


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_rel(path: str) -> str:
    text = str(path or "").replace("\\", "/").lstrip("/")
    while text.startswith("./"):
        text = text[2:]
    return text


def run_git(repo: Path, args: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def parse_status_porcelain_z(raw: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    items = str(raw or "").split("\0")
    idx = 0
    while idx < len(items):
        token = items[idx]
        idx += 1
        if not token:
            continue
        if len(token) < 4:
            continue
        status = token[:2]
        path = normalize_rel(token[3:])
        if status and ("R" in status or "C" in status) and idx < len(items):
            renamed = normalize_rel(items[idx])
            idx += 1
            if renamed:
                out.append({"status": status, "path": renamed})
            continue
        if path:
            out.append({"status": status, "path": path})
    return out


def matches_any_glob(path: str, patterns: list[str]) -> bool:
    rel = normalize_rel(path)
    for pattern in patterns:
        p = normalize_rel(pattern)
        if not p:
            continue
        if fnmatch.fnmatch(rel, p):
            return True
    return False


def startswith_any(path: str, prefixes: list[str]) -> bool:
    rel = normalize_rel(path).lower()
    for prefix in prefixes:
        p = normalize_rel(prefix).lower()
        if p and rel.startswith(p):
            return True
    return False


def should_include(
    path: str,
    *,
    include_prefixes: list[str],
    exclude_prefixes: list[str],
    include_globs: list[str],
    exclude_globs: list[str],
) -> bool:
    rel = normalize_rel(path)
    if not rel:
        return False
    if startswith_any(rel, exclude_prefixes):
        return False
    if matches_any_glob(rel, exclude_globs):
        return False
    include_limited = bool(include_prefixes) or bool(include_globs)
    if not include_limited:
        return True
    if startswith_any(rel, include_prefixes):
        return True
    if matches_any_glob(rel, include_globs):
        return True
    return False


def chunked(values: list[str], size: int) -> list[list[str]]:
    out: list[list[str]] = []
    step = max(1, int(size))
    for idx in range(0, len(values), step):
        out.append(values[idx : idx + step])
    return out


def ensure_repo_ready(repo: Path, *, author_name: str, author_email: str) -> tuple[bool, list[str], bool]:
    errors: list[str] = []
    initialized = False
    if not repo.exists() or (not repo.is_dir()):
        return False, [f"repo_invalid:{repo}"], initialized

    if not (repo / ".git").exists():
        rc, _out, err = run_git(repo, ["init", "-b", "main"], timeout=30)
        if rc != 0:
            rc2, _out2, err2 = run_git(repo, ["init"], timeout=30)
            if rc2 != 0:
                return False, [f"git_init_failed:{err or err2 or rc}"], initialized
            run_git(repo, ["checkout", "-B", "main"], timeout=30)
        initialized = True

    rc, out, err = run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=20)
    if rc != 0 or str(out).strip().lower() != "true":
        return False, [f"not_git_repo:{err or out or repo}"], initialized

    rc_name, name_out, _err_name = run_git(repo, ["config", "--get", "user.name"], timeout=20)
    rc_mail, mail_out, _err_mail = run_git(repo, ["config", "--get", "user.email"], timeout=20)
    if rc_name != 0 or not str(name_out).strip():
        rc_set_name, _out_set_name, err_set_name = run_git(repo, ["config", "user.name", author_name], timeout=20)
        if rc_set_name != 0:
            errors.append(f"git_config_user_name_failed:{err_set_name or rc_set_name}")
    if rc_mail != 0 or not str(mail_out).strip():
        rc_set_mail, _out_set_mail, err_set_mail = run_git(repo, ["config", "user.email", author_email], timeout=20)
        if rc_set_mail != 0:
            errors.append(f"git_config_user_email_failed:{err_set_mail or rc_set_mail}")
    return len(errors) == 0, errors, initialized


def ensure_gitignore(repo: Path) -> bool:
    p = repo / ".gitignore"
    existing = p.read_text(encoding="utf-8", errors="ignore").splitlines() if p.exists() else []
    seen = {line.strip() for line in existing}
    changed = False
    for line in DEFAULT_GITIGNORE_LINES:
        if line.strip() not in seen:
            existing.append(line)
            seen.add(line.strip())
            changed = True
    if changed:
        p.write_text("\n".join(existing).rstrip() + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Local git backup runner (commit only, no push)")
    parser.add_argument("--repo-path", default=str(Path.home() / ".openclaw"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--author-name", default="openclaw-local-backup")
    parser.add_argument("--author-email", default="openclaw@local")
    parser.add_argument("--commit-prefix", default="chore(local-backup): snapshot ~/.openclaw")
    parser.add_argument("--commit-message", default="")
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    parser.add_argument("--include-glob", action="append", default=[])
    parser.add_argument("--exclude-glob", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    repo = Path(str(args.repo_path or ".")).expanduser().resolve()
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    include_prefixes = [normalize_rel(x) for x in args.include_prefix if str(x).strip()]
    exclude_prefixes = [normalize_rel(x) for x in args.exclude_prefix if str(x).strip()]
    include_globs = [normalize_rel(x) for x in args.include_glob if str(x).strip()]
    exclude_globs = [normalize_rel(x) for x in args.exclude_glob if str(x).strip()]
    if not include_prefixes and not include_globs:
        include_prefixes = [normalize_rel(x) for x in DEFAULT_INCLUDE_PREFIXES]
    if not exclude_globs:
        exclude_globs = [normalize_rel(x) for x in DEFAULT_EXCLUDE_GLOBS]

    result: dict[str, Any] = {
        "time": now_iso(),
        "task_id": str(args.task_id or "").strip(),
        "repo": str(repo),
        "normal_log_mode": log_mode,
        "initialized": False,
        "gitignore_updated": False,
        "committed": False,
        "commit_sha": "",
        "eligible_files": [],
        "skipped_files": [],
        "errors": [],
    }

    ok, errors, initialized = ensure_repo_ready(
        repo,
        author_name=str(args.author_name or "openclaw-local-backup").strip() or "openclaw-local-backup",
        author_email=str(args.author_email or "openclaw@local").strip() or "openclaw@local",
    )
    result["initialized"] = initialized
    if not ok:
        result["errors"].extend(errors)

    if not result["errors"]:
        result["gitignore_updated"] = ensure_gitignore(repo)

    if not result["errors"]:
        rc, status_out, err = run_git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], timeout=30)
        if rc != 0:
            result["errors"].append(f"git_status_failed:{err or rc}")
        else:
            changes = parse_status_porcelain_z(status_out)
            eligible: list[str] = []
            skipped: list[str] = []
            for item in changes:
                path = str(item.get("path", "")).strip()
                if should_include(
                    path,
                    include_prefixes=include_prefixes,
                    exclude_prefixes=exclude_prefixes,
                    include_globs=include_globs,
                    exclude_globs=exclude_globs,
                ):
                    eligible.append(path)
                else:
                    skipped.append(path)
            max_files = max(1, int(args.max_files))
            if len(eligible) > max_files:
                skipped.extend(eligible[max_files:])
                eligible = eligible[:max_files]
            result["eligible_files"] = sorted(set(eligible))
            result["skipped_files"] = sorted(set(skipped))

    if not result["errors"] and result["eligible_files"]:
        for group in chunked(list(result["eligible_files"]), 80):
            rc, _out, err = run_git(repo, ["add", "--", *group], timeout=60)
            if rc != 0:
                result["errors"].append(f"git_add_failed:{err or rc}")
                break

    if not result["errors"] and result["eligible_files"]:
        rc, staged_out, err = run_git(repo, ["diff", "--cached", "--name-only"], timeout=20)
        if rc != 0:
            result["errors"].append(f"git_diff_cached_failed:{err or rc}")
        elif not str(staged_out).strip():
            result["eligible_files"] = []
        else:
            commit_message = str(args.commit_message or "").strip()
            if not commit_message:
                commit_prefix = str(args.commit_prefix or "").strip() or "chore(local-backup): snapshot ~/.openclaw"
                ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
                task_suffix = f" [{result['task_id']}]" if result["task_id"] else ""
                commit_message = f"{commit_prefix}{task_suffix} ({ts})"
            rc, _out, err = run_git(repo, ["commit", "-m", commit_message], timeout=120)
            if rc != 0:
                result["errors"].append(f"git_commit_failed:{err or rc}")
            else:
                result["committed"] = True
                rc2, sha, _err2 = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
                if rc2 == 0 and str(sha).strip():
                    result["commit_sha"] = str(sha).strip()

    notify = bool(result["errors"]) or bool(result["committed"]) or bool(result["initialized"]) or bool(
        result["gitignore_updated"]
    )
    output = "NO_REPLY"
    if notify:
        lines = [
            "# local-git-backup",
            f"- task: {result['task_id'] or '-'}",
            f"- time: {result['time']}",
            f"- repo: {result['repo']}",
            f"- initialized: {result['initialized']}",
            f"- gitignore_updated: {result['gitignore_updated']}",
            f"- committed: {result['committed']}",
            f"- eligible_files: {len(result['eligible_files'])}",
            f"- skipped_files: {len(result['skipped_files'])}",
            f"- error_count: {len(result['errors'])}",
        ]
        if str(result.get("commit_sha", "")).strip():
            lines.append(f"- commit_sha: {result['commit_sha']}")
        for err in result["errors"][:10]:
            lines.append(f"- error: {err}")
        for path in result["eligible_files"][:20]:
            lines.append(f"- changed: {path}")
        output = "\n".join(lines)

    if bool(args.emit_json):
        print(json.dumps({"notify": notify, "output": output, "result": result}, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

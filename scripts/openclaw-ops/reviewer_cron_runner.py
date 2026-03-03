#!/usr/bin/env python3
"""Reviewer scheduled scan runner.

Modes:
- hourly_git: git incremental record + branch sync + PR scan (+ optional approved merges).
- daily_incremental: incremental code-quality scan and optional fix command.
- bi_daily_recurring: recurring issue scan with full-scan dedupe.
- weekly_structure: structure audit (coupling, duplication hints, config dispersion, I/O contract).

Output contract:
- Print `NO_REPLY` when no notification is required.
- Otherwise print concise markdown + evidence file path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
DEFAULT_SENDER_PREFIX = "reviewer/reviewer-cron-runner"
SKIP_DIR_NAMES = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "dist", "build", ".next", ".idea", ".vscode"
}
SCANNED_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
DATA_FUNC_HINTS = ("process", "transform", "compute", "calculate", "parse", "normalize", "aggregate", "clean")
JS_DATA_FUNC_HINTS = DATA_FUNC_HINTS
COMMON_DUP_NAMES = {"main", "run", "handler", "init", "setup", "test", "render", "create", "update", "delete"}


@dataclass(slots=True)
class RunResult:
    notify: bool
    output: str
    record: dict[str, Any]


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"silent", "chat"} else default


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha1_text(text: str, limit: int = 20) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:limit]


def run_cmd(command: list[str] | str, *, cwd: Path | None = None, timeout: int = 30, shell: bool = False) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=shell,
            check=False,
        )
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def run_git(repo: Path, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    return run_cmd(["git", *args], cwd=repo, timeout=timeout, shell=False)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def repo_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def rel_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve()).replace("\\", "/")


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def discover_git_repos(workspace: Path, max_depth: int = 4, max_repos: int = 80) -> list[Path]:
    if not workspace.exists():
        return []
    repos: list[Path] = []
    seen: set[str] = set()
    ws = workspace.resolve()
    if is_git_repo(ws):
        repos.append(ws)
        seen.add(repo_key(ws))

    root_depth = len(ws.parts)
    for current, dirs, _files in os.walk(ws):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        if ".git" in dirs:
            key = repo_key(current_path)
            if key not in seen:
                repos.append(current_path.resolve())
                seen.add(key)
            dirs[:] = [d for d in dirs if d != ".git"]
        if len(repos) >= max_repos:
            break
    repos.sort(key=lambda p: str(p))
    return repos


def list_changed_files_since(repo: Path, old_head: str, new_head: str) -> list[str]:
    old = str(old_head or "").strip()
    new = str(new_head or "").strip()
    if not old or not new or old == new:
        return []
    rc, _out, _err = run_git(repo, ["merge-base", "--is-ancestor", old, new], timeout=20)
    if rc != 0:
        return []
    rc, out, _err = run_git(repo, ["diff", "--name-only", f"{old}..{new}"], timeout=40)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_branch_sync(repo: Path, max_branches: int = 40) -> list[dict[str, Any]]:
    rc, out, _err = run_git(repo, ["for-each-ref", "--format=%(refname:short)|%(upstream:short)", "refs/heads"], timeout=30)
    if rc != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        branch, upstream = line.split("|", 1)
        branch = branch.strip()
        upstream = upstream.strip()
        if not branch or not upstream:
            continue
        rc2, out2, _err2 = run_git(repo, ["rev-list", "--left-right", "--count", f"{branch}...{upstream}"], timeout=20)
        if rc2 != 0:
            continue
        parts = out2.split()
        ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
        behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        rows.append({"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind})
        if len(rows) >= max_branches:
            break
    return rows


def collect_git_snapshot(repo: Path, *, git_fetch: bool, previous_head: str) -> dict[str, Any]:
    data: dict[str, Any] = {"repo": repo_key(repo), "name": repo.name, "errors": [], "fetch_ok": False}
    if git_fetch:
        rc, _out, err = run_git(repo, ["fetch", "--all", "--prune"], timeout=120)
        data["fetch_ok"] = rc == 0
        if rc != 0:
            data["errors"].append(f"git_fetch_failed:{err or rc}")

    rc, head, err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    if rc != 0 or not head:
        data["errors"].append(f"git_rev_parse_failed:{err or rc}")
        return data
    data["head"] = head
    data["head_changed"] = bool(previous_head and previous_head != head)
    data["changed_files_since_prev"] = list_changed_files_since(repo, previous_head, head)[:200]

    rc, branch, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    data["branch"] = branch if rc == 0 else "UNKNOWN"
    rc, upstream, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=20)
    data["upstream"] = upstream if rc == 0 else ""

    ahead = behind = 0
    if data["upstream"]:
        rc, out, _err = run_git(repo, ["rev-list", "--left-right", "--count", "HEAD...@{u}"], timeout=20)
        if rc == 0:
            parts = out.split()
            ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
            behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    data["ahead"] = ahead
    data["behind"] = behind

    rc, out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    data["dirty_count"] = len([x for x in out.splitlines() if x.strip()]) if rc == 0 else 0
    data["branch_sync"] = collect_branch_sync(repo)
    return data


def collect_prs(repo: Path, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "available": False, "prs": []}
    if not has_command("gh"):
        return {"enabled": True, "available": False, "error": "gh_not_found", "prs": []}
    rc, out, err = run_cmd(
        ["gh", "pr", "list", "--limit", "50", "--json", "number,title,isDraft,mergeable,headRefName,baseRefName,updatedAt,url"],
        cwd=repo,
        timeout=40,
        shell=False,
    )
    if rc != 0:
        return {"enabled": True, "available": False, "error": err or f"gh_pr_list_exit_{rc}", "prs": []}
    try:
        rows = json.loads(out)
    except Exception:
        return {"enabled": True, "available": False, "error": "gh_pr_json_parse_failed", "prs": []}
    if not isinstance(rows, list):
        rows = []

    prs = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        prs.append(
            {
                "number": int(item.get("number", 0) or 0),
                "title": str(item.get("title", "")).strip(),
                "draft": bool(item.get("isDraft", False)),
                "mergeable": str(item.get("mergeable", "")).strip().upper(),
                "head": str(item.get("headRefName", "")).strip(),
                "base": str(item.get("baseRefName", "")).strip(),
                "updated_at": str(item.get("updatedAt", "")).strip(),
                "url": str(item.get("url", "")).strip(),
            }
        )
    return {"enabled": True, "available": True, "prs": prs}


def load_merge_approvals(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "approved_prs": [], "approved_branches": []}
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {"exists": True, "approved_prs": [], "approved_branches": []}

    approved_prs: list[dict[str, Any]] = []
    approved_branches: list[dict[str, Any]] = []
    for key in ("approved_prs", "prs", "pr_numbers"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, int):
                approved_prs.append({"repo": "", "number": int(item)})
            elif isinstance(item, str) and item.strip().isdigit():
                approved_prs.append({"repo": "", "number": int(item.strip())})
            elif isinstance(item, dict):
                number = item.get("number", item.get("pr", 0))
                if str(number).strip().isdigit():
                    approved_prs.append({"repo": str(item.get("repo", item.get("repository", ""))).strip(), "number": int(str(number).strip())})

    for key in ("approved_branches", "branches"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                text = item.strip()
                if not text or "->" not in text:
                    continue
                repo_sel = ""
                pair = text
                if ":" in text:
                    left, right = text.split(":", 1)
                    if "->" in right:
                        repo_sel = left.strip()
                        pair = right.strip()
                source, target = [x.strip() for x in pair.split("->", 1)]
                if source and target:
                    approved_branches.append({"repo": repo_sel, "source": source, "target": target})
            elif isinstance(item, dict):
                source = str(item.get("source", item.get("from", ""))).strip()
                target = str(item.get("target", item.get("to", ""))).strip()
                if source and target:
                    approved_branches.append({"repo": str(item.get("repo", item.get("repository", ""))).strip(), "source": source, "target": target})
    return {"exists": True, "approved_prs": approved_prs, "approved_branches": approved_branches}


def repo_matches_selector(repo: Path, selector: str) -> bool:
    needle = str(selector or "").strip().lower().replace("\\", "/")
    if needle in {"", "*", "all"}:
        return True
    path_text = repo_key(repo).lower()
    return path_text.endswith(needle) or repo.name.lower() == needle or f"/{needle}/" in path_text

def merge_approved_prs(repo: Path, prs: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not approvals:
        return actions
    if not has_command("gh"):
        actions.append({"kind": "pr", "ok": False, "reason": "gh_not_found"})
        return actions

    by_number = {int(item.get("number", 0)): item for item in prs if int(item.get("number", 0)) > 0}
    for item in approvals:
        number = int(item.get("number", 0) or 0)
        if number <= 0 or not repo_matches_selector(repo, str(item.get("repo", ""))):
            continue
        pr = by_number.get(number)
        if pr and pr.get("draft"):
            actions.append({"kind": "pr", "number": number, "ok": False, "reason": "draft"})
            continue
        if pr and str(pr.get("mergeable", "")).upper() == "CONFLICTING":
            actions.append({"kind": "pr", "number": number, "ok": False, "reason": "merge_conflict"})
            continue
        rc, out, err = run_cmd(["gh", "pr", "merge", str(number), "--merge", "--delete-branch"], cwd=repo, timeout=180)
        actions.append({"kind": "pr", "number": number, "ok": rc == 0, "reason": "" if rc == 0 else (err or f"exit_{rc}"), "stdout": out[:300]})
    return actions


def merge_branch_ff_only(repo: Path, source: str, target: str, *, push_after_merge: bool) -> dict[str, Any]:
    source = source.strip()
    target = target.strip()
    if not source or not target or source == target:
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": "invalid_source_target"}

    rc, out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    if rc == 0 and out.strip():
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": "dirty_worktree"}

    rc, original_branch, err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    if rc != 0 or not original_branch:
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "current_branch_unknown"}

    switched = False
    try:
        if original_branch != target:
            rc, _out, err = run_git(repo, ["checkout", target], timeout=40)
            if rc != 0:
                return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "checkout_target_failed"}
            switched = True
        rc, _out, err = run_git(repo, ["merge", "--ff-only", source], timeout=80)
        if rc != 0:
            return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "ff_merge_failed"}

        push_reason = ""
        if push_after_merge:
            rc, _out, err = run_git(repo, ["push"], timeout=120)
            if rc != 0:
                push_reason = err or "push_failed"
        return {"kind": "branch", "source": source, "target": target, "ok": push_reason == "", "reason": push_reason}
    finally:
        if switched:
            run_git(repo, ["checkout", original_branch], timeout=30)


def merge_approved_branches(repo: Path, approvals: list[dict[str, Any]], *, push_after_merge: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in approvals:
        if not repo_matches_selector(repo, str(item.get("repo", ""))):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if source and target:
            actions.append(merge_branch_ff_only(repo, source, target, push_after_merge=push_after_merge))
    return actions


def issue_key(category: str, path: str, symbol: str, detail: str) -> str:
    return sha1_text(f"{category}|{path}|{symbol}|{detail}")


def parse_python_params(text: str) -> list[str]:
    return [x.strip() for x in text.split(",")]


def py_param_has_annotation(token: str) -> bool:
    raw = token.strip()
    if raw in {"", "self", "cls", "*", "/"}:
        return True
    if raw.startswith("**"):
        return True
    if raw.startswith("*"):
        raw = raw[1:].strip()
        if raw in {"", "args"}:
            return True
    return ":" in raw


def has_jsdoc_contract(lines: list[str], line_index: int) -> bool:
    start = max(0, line_index - 6)
    chunk = "\n".join(lines[start:line_index])
    return ("@param" in chunk) and ("@returns" in chunk or "@return" in chunk)


def scan_python_file(path: Path, repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    symbols: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    rel = rel_to(repo_root, path)

    if len(lines) > 900:
        findings.append({"key": issue_key("maintainability.file_too_long", rel, "", f"lines={len(lines)}"), "category": "maintainability.file_too_long", "severity": "medium", "path": rel, "title": f"File too long ({len(lines)} lines): {rel}", "detail": "split into smaller modules"})

    for idx, line in enumerate(lines, start=1):
        if re.search(r"^\s*from\s+\.\.\.\.", line):
            findings.append({"key": issue_key("coupling.deep_relative_import", rel, str(idx), line.strip()), "category": "coupling.deep_relative_import", "severity": "high", "path": rel, "title": f"Deep relative import at {rel}:{idx}", "detail": line.strip()[:180]})
        if "sys.path.append(" in line:
            findings.append({"key": issue_key("coupling.dynamic_path_import", rel, str(idx), line.strip()), "category": "coupling.dynamic_path_import", "severity": "high", "path": rel, "title": f"Dynamic import path at {rel}:{idx}", "detail": line.strip()[:180]})

    pattern = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\(([^)]*)\)\s*(?:->\s*([^:]+))?:")
    for idx, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if not match:
            continue
        name, params_raw, return_ann = match.groups()
        symbols.append(name)
        if any(h in name.lower() for h in DATA_FUNC_HINTS):
            params = parse_python_params(params_raw)
            all_annotated = all(py_param_has_annotation(p) for p in params)
            has_return = bool(str(return_ann or "").strip())
            if not (all_annotated and has_return):
                findings.append({"key": issue_key("io_contract.missing_signature", rel, name, line.strip()), "category": "io_contract.missing_signature", "severity": "high", "path": rel, "title": f"Missing explicit input/output contract: {name} ({rel}:{idx})", "detail": "add parameter annotations and return annotation"})
    return findings, symbols


def scan_js_ts_file(path: Path, repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    symbols: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    rel = rel_to(repo_root, path)

    import_pattern = re.compile(r"(from\s+['\"](\.\./){3,}[^'\"]+['\"])|(require\(['\"](\.\./){3,}[^'\"]+['\"]\))")
    for idx, line in enumerate(lines, start=1):
        if import_pattern.search(line):
            findings.append({"key": issue_key("coupling.deep_relative_import", rel, str(idx), line.strip()), "category": "coupling.deep_relative_import", "severity": "high", "path": rel, "title": f"Deep relative import at {rel}:{idx}", "detail": line.strip()[:180]})

    fn_patterns = [
        re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\("),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
    ]
    for idx, line in enumerate(lines):
        matched_name = ""
        for pat in fn_patterns:
            m = pat.match(line)
            if m:
                matched_name = m.group(1)
                break
        if not matched_name:
            continue
        symbols.append(matched_name)
        if any(h in matched_name.lower() for h in JS_DATA_FUNC_HINTS) and not has_jsdoc_contract(lines, idx):
            findings.append({"key": issue_key("io_contract.missing_signature", rel, matched_name, line.strip()), "category": "io_contract.missing_signature", "severity": "high", "path": rel, "title": f"Missing explicit input/output contract: {matched_name} ({rel}:{idx + 1})", "detail": "add JSDoc @param and @returns"})
    return findings, symbols


def iter_code_files(repo: Path, max_files: int = 3000) -> list[Path]:
    files: list[Path] = []
    root_depth = len(repo.parts)
    for current, dirs, names in os.walk(repo):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        if len(current_path.parts) - root_depth > 8:
            dirs[:] = []
            continue
        for name in names:
            path = current_path / name
            if path.suffix.lower() in SCANNED_SUFFIXES:
                files.append(path)
                if len(files) >= max_files:
                    return files
    return files


def file_fp(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def scan_paths(*, mode: str, repo: Path, paths: list[Path], state: dict[str, Any], skip_unchanged: bool) -> tuple[list[dict[str, Any]], dict[str, set[str]], dict[str, int], int]:
    scan_fp = state.setdefault("scan_fingerprints", {})
    mode_fp = scan_fp.setdefault(mode, {})
    if not isinstance(mode_fp, dict):
        mode_fp = {}
        scan_fp[mode] = mode_fp

    findings: list[dict[str, Any]] = []
    function_index: dict[str, set[str]] = {}
    metrics = {"files_scanned": 0, "files_skipped": 0, "config_files": 0}
    io_contract_count = 0

    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        rel = rel_to(repo, path)
        fp = file_fp(path)
        if skip_unchanged and mode_fp.get(rel) == fp:
            metrics["files_skipped"] += 1
            continue
        mode_fp[rel] = fp
        metrics["files_scanned"] += 1

        if "config" in path.name.lower() or path.name.lower().startswith(("settings", "env.")):
            metrics["config_files"] += 1

        suffix = path.suffix.lower()
        if suffix == ".py":
            file_findings, symbols = scan_python_file(path, repo)
        elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
            file_findings, symbols = scan_js_ts_file(path, repo)
        else:
            file_findings, symbols = [], []

        for item in file_findings:
            if item.get("category") == "io_contract.missing_signature":
                io_contract_count += 1
            findings.append(item)

        for name in symbols:
            function_index.setdefault(name.lower(), set()).add(rel)

    duplicate_hits = 0
    for func_name, locations in function_index.items():
        if len(locations) < 2 or func_name in COMMON_DUP_NAMES or len(func_name) <= 3:
            continue
        duplicate_hits += 1
        locs = sorted(locations)
        findings.append({"key": issue_key("duplication.same_function_name", repo.name, func_name, "|".join(locs[:4])), "category": "duplication.same_function_name", "severity": "medium", "path": repo.name, "title": f"Function name repeated across files: {func_name}", "detail": ", ".join(locs[:4])})
        if duplicate_hits >= 20:
            break

    if metrics["config_files"] >= 8:
        findings.append({"key": issue_key("config.dispersion", repo.name, "", f"count={metrics['config_files']}"), "category": "config.dispersion", "severity": "medium", "path": repo.name, "title": f"Config files appear dispersed in repo: count={metrics['config_files']}", "detail": "consider centralized config layout"})

    return findings, function_index, metrics, io_contract_count


def update_issues(state: dict[str, Any], *, findings: list[dict[str, Any]], mode: str, resolve_after_missed_runs: int = 2, keep_resolved_days: int = 30) -> dict[str, int]:
    issues = state.setdefault("issues", {})
    if not isinstance(issues, dict):
        issues = {}
        state["issues"] = issues
    ts = now_iso()
    seen: set[str] = set()
    created = reopened = resolved = created_high = reopened_high = 0

    for item in findings:
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        seen.add(key)
        rec = issues.get(key)
        severity = str(item.get("severity", "medium")).lower()
        if not isinstance(rec, dict):
            issues[key] = {"key": key, "mode": mode, "title": str(item.get("title", "")).strip(), "path": str(item.get("path", "")).strip(), "category": str(item.get("category", "")).strip(), "severity": severity, "status": "open", "first_seen": ts, "last_seen": ts, "resolved_at": "", "occurrences": 1, "missed_runs": 0, "reopened_count": 0}
            created += 1
            if severity == "high":
                created_high += 1
            continue

        if rec.get("status") == "resolved":
            rec["status"] = "open"
            rec["resolved_at"] = ""
            rec["reopened_count"] = int(rec.get("reopened_count", 0)) + 1
            reopened += 1
            if severity == "high":
                reopened_high += 1

        rec["mode"] = mode
        rec["title"] = str(item.get("title", rec.get("title", ""))).strip()
        rec["path"] = str(item.get("path", rec.get("path", ""))).strip()
        rec["category"] = str(item.get("category", rec.get("category", ""))).strip()
        rec["severity"] = "high" if rec.get("severity") == "high" or severity == "high" else "medium"
        rec["last_seen"] = ts
        rec["occurrences"] = int(rec.get("occurrences", 0)) + 1
        rec["missed_runs"] = 0

    for key, rec in list(issues.items()):
        if not isinstance(rec, dict) or str(rec.get("mode", "")).strip() != mode or rec.get("status") != "open" or key in seen:
            continue
        rec["missed_runs"] = int(rec.get("missed_runs", 0)) + 1
        if rec["missed_runs"] >= max(1, int(resolve_after_missed_runs)):
            rec["status"] = "resolved"
            rec["resolved_at"] = ts
            resolved += 1

    if keep_resolved_days > 0:
        cutoff = now() - timedelta(days=max(1, int(keep_resolved_days)))
        for key, rec in list(issues.items()):
            if not isinstance(rec, dict) or rec.get("status") != "resolved":
                continue
            stamp = str(rec.get("resolved_at", "")).strip()
            if not stamp:
                continue
            try:
                resolved_at = datetime.fromisoformat(stamp)
            except Exception:
                continue
            if resolved_at < cutoff:
                issues.pop(key, None)

    open_total = open_high_total = recurring_total = 0
    for rec in issues.values():
        if not isinstance(rec, dict) or rec.get("status") != "open":
            continue
        open_total += 1
        if str(rec.get("severity", "")).lower() == "high":
            open_high_total += 1
        if int(rec.get("occurrences", 0)) >= 3 or int(rec.get("reopened_count", 0)) >= 1:
            recurring_total += 1

    return {
        "new": created,
        "new_high": created_high,
        "reopened": reopened,
        "reopened_high": reopened_high,
        "resolved": resolved,
        "open_total": open_total,
        "open_high_total": open_high_total,
        "recurring_open_total": recurring_total,
    }

def run_hourly_git(args: argparse.Namespace, state: dict[str, Any], normal_log_mode: str) -> RunResult:
    run_started_at = datetime.now(TZ)
    repos = discover_git_repos(Path(args.workspace).expanduser())
    repo_state = state.setdefault("repos", {})
    findings: list[dict[str, Any]] = []
    repo_summaries: list[dict[str, Any]] = []
    total_changed_repos = total_behind_branches = total_dirty = pr_open_total = 0
    merge_actions: list[dict[str, Any]] = []

    approvals = load_merge_approvals(Path(args.merge_approval_file).expanduser()) if args.allow_merge else {"exists": False, "approved_prs": [], "approved_branches": []}

    for repo in repos:
        key = repo_key(repo)
        rec = repo_state.get(key, {}) if isinstance(repo_state.get(key), dict) else {}
        prev_head = str(rec.get("last_hourly_head", "")).strip()
        snap = collect_git_snapshot(repo, git_fetch=bool(args.git_fetch), previous_head=prev_head)
        repo_summaries.append(snap)
        if snap.get("head_changed"):
            total_changed_repos += 1
        total_dirty += int(snap.get("dirty_count", 0) or 0)

        branch_sync = snap.get("branch_sync", [])
        if isinstance(branch_sync, list):
            for item in branch_sync:
                behind = int(item.get("behind", 0) or 0)
                if behind > 0:
                    total_behind_branches += 1
                    findings.append({"key": issue_key("git.branch_behind", key, str(item.get("branch", "")), str(behind)), "category": "git.branch_behind", "severity": "high" if behind >= 10 else "medium", "path": key, "title": f"Branch behind upstream: {item.get('branch')} behind={behind}", "detail": f"upstream={item.get('upstream')}"})

        pr_data = collect_prs(repo, enabled=bool(args.check_pr))
        snap["pr"] = pr_data
        prs = pr_data.get("prs", []) if isinstance(pr_data, dict) else []
        pr_open_total += len(prs) if isinstance(prs, list) else 0

        if args.allow_merge:
            pr_actions = merge_approved_prs(repo, prs if isinstance(prs, list) else [], approvals.get("approved_prs", []))
            branch_actions = merge_approved_branches(repo, approvals.get("approved_branches", []), push_after_merge=bool(args.push_after_merge))
            actions = pr_actions + branch_actions
            if actions:
                merge_actions.extend([{**x, "repo": key} for x in actions])
                for action in actions:
                    if not action.get("ok", False):
                        findings.append({"key": issue_key("merge.failure", key, str(action.get("kind", "")), str(action)), "category": "merge.failure", "severity": "high", "path": key, "title": f"Approved merge failed ({action.get('kind')}): {key}", "detail": str(action.get("reason", ""))[:180]})

        rec["last_hourly_head"] = str(snap.get("head", "")).strip()
        rec["last_hourly_at"] = now_iso()
        repo_state[key] = rec

    issue_stats = update_issues(state, findings=findings, mode="hourly_git")

    risk_reasons: list[str] = []
    change_reasons: list[str] = []
    if total_behind_branches > 0:
        risk_reasons.append(f"branches_behind={total_behind_branches}")
    merge_failed = sum(1 for x in merge_actions if not x.get("ok", False))
    if merge_failed > 0:
        risk_reasons.append(f"merge_failed={merge_failed}")
    if issue_stats["new_high"] > 0 or issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"high_issue_delta={issue_stats['new_high'] + issue_stats['reopened_high']}")

    if total_changed_repos > 0:
        change_reasons.append(f"repos_head_changed={total_changed_repos}")
    if total_dirty > 0:
        change_reasons.append(f"dirty_repos={total_dirty}")
    if pr_open_total > 0 and args.check_pr:
        change_reasons.append(f"open_prs={pr_open_total}")
    if merge_actions:
        ok_merges = sum(1 for x in merge_actions if x.get("ok", False))
        change_reasons.append(f"merge_actions={len(merge_actions)},ok={ok_merges}")

    # Noise control: silent mode only notifies on risks.
    notify = bool(risk_reasons)
    if not notify and normal_log_mode == "chat" and change_reasons:
        notify = True

    run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
    run_id = uuid.uuid4().hex[:12]
    job_name = str(args.task_id or "").split(":", 1)[-1] if ":" in str(args.task_id or "") else "reviewer_hourly_git"
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    lines = ["NO_REPLY"]
    if notify:
        lines = [
            "# reviewer-cron/hourly_git",
            f"agent: {DEFAULT_SENDER_PREFIX}:hourly_git",
            f"job: {job_name}",
            f"task_id: {args.task_id or '-'}",
            f"run_id: {run_id}",
            f"time: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} UTC+8",
            f"run_duration_ms: {run_duration_ms}",
            f"priority: {priority}",
            f"risk_level: {risk_level}",
            f"normal_log_mode: {normal_log_mode}",
            f"repos: total={len(repos)}, head_changed={total_changed_repos}, dirty={total_dirty}",
            f"branches_behind: {total_behind_branches}",
            f"prs_open: {pr_open_total}",
            f"issue_summary: new={issue_stats['new']}, reopened={issue_stats['reopened']}, resolved={issue_stats['resolved']}, open={issue_stats['open_total']}, open_high={issue_stats['open_high_total']}",
            f"approvals: allow_merge={bool(args.allow_merge)}, approval_file={args.merge_approval_file}",
        ]
        if risk_reasons:
            lines.append(f"risk_reasons: {', '.join(risk_reasons)}")
        if change_reasons:
            lines.append(f"change_reasons: {', '.join(change_reasons)}")
        manual_required = bool(risk_reasons)
        lines.append(f"manual_action_required: {str(manual_required).lower()}")
        if manual_required:
            lines.append("manual_action: coordinator 需确认分支同步/合并风险后再继续自动执行。")

    record = {
        "run_id": run_id,
        "sender_identity": f"{DEFAULT_SENDER_PREFIX}:hourly_git",
        "task_id": args.task_id,
        "job_name": job_name,
        "priority": priority,
        "risk_level": risk_level,
        "run_duration_ms": run_duration_ms,
        "mode": "hourly_git",
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": normal_log_mode,
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "issue_stats": issue_stats,
        "repos": repo_summaries,
        "merge_actions": merge_actions,
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_estimate": 0.0,
    }
    return RunResult(notify=notify, output="\n".join(lines), record=record)


def run_quality_scan(
    args: argparse.Namespace,
    state: dict[str, Any],
    normal_log_mode: str,
    *,
    mode: str,
    incremental_from_head: bool,
    full_scan_skip_unchanged: bool,
    run_fix_command: bool,
) -> RunResult:
    run_started_at = datetime.now(TZ)
    repos = discover_git_repos(Path(args.workspace).expanduser())
    repo_state = state.setdefault("repos", {})
    findings: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    total_io_missing = total_files_scanned = total_files_skipped = 0
    fix_result: dict[str, Any] = {}

    for repo in repos:
        key = repo_key(repo)
        rec = repo_state.get(key, {}) if isinstance(repo_state.get(key), dict) else {}
        rc, head, _err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
        if rc != 0 or not head:
            continue

        paths: list[Path] = []
        if incremental_from_head:
            previous = str(rec.get("last_daily_head", "")).strip()
            changed = list_changed_files_since(repo, previous, head)
            if not changed:
                rc2, out2, _err2 = run_git(repo, ["diff", "--name-only", "HEAD~1..HEAD"], timeout=20)
                if rc2 == 0:
                    changed = [line.strip() for line in out2.splitlines() if line.strip()]
            for rel in changed[:400]:
                path = repo / rel
                if path.exists() and path.is_file() and path.suffix.lower() in SCANNED_SUFFIXES:
                    paths.append(path)
            rec["last_daily_head"] = head
            rec["last_daily_at"] = now_iso()
            repo_state[key] = rec
        else:
            paths = iter_code_files(repo, max_files=3000)
            rec[f"last_{mode}_at"] = now_iso()
            repo_state[key] = rec

        repo_findings, _function_index, metrics, io_missing = scan_paths(mode=mode, repo=repo, paths=paths, state=state, skip_unchanged=full_scan_skip_unchanged)
        findings.extend(repo_findings)
        total_io_missing += io_missing
        total_files_scanned += int(metrics.get("files_scanned", 0))
        total_files_skipped += int(metrics.get("files_skipped", 0))
        summary.append({"repo": key, "files": len(paths), "scanned": int(metrics.get("files_scanned", 0)), "skipped": int(metrics.get("files_skipped", 0)), "findings": len(repo_findings), "io_missing": io_missing})

    if run_fix_command and args.fix and str(args.fix_command or "").strip():
        rc, out, err = run_cmd(str(args.fix_command), cwd=Path(args.workspace).expanduser(), timeout=1800, shell=True)
        fix_result = {"ran": True, "ok": rc == 0, "exit_code": rc, "stdout": out[-1000:], "stderr": err[-1000:]}
        if rc != 0:
            findings.append({"key": issue_key("fix_command.failed", mode, "", str(rc)), "category": "fix_command.failed", "severity": "high", "path": str(Path(args.workspace).expanduser()), "title": f"Fix command failed in mode={mode}", "detail": (err or out or f"exit_code={rc}")[:180]})

    issue_stats = update_issues(state, findings=findings, mode=mode)

    risk_reasons: list[str] = []
    change_reasons: list[str] = []
    if issue_stats["new_high"] > 0 or issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"high_issue_delta={issue_stats['new_high'] + issue_stats['reopened_high']}")
    if fix_result.get("ran") and not fix_result.get("ok", True):
        risk_reasons.append("fix_command_failed")
    if issue_stats["new"] > 0:
        change_reasons.append(f"new_issue={issue_stats['new']}")
    if issue_stats["reopened"] > 0:
        change_reasons.append(f"reopened_issue={issue_stats['reopened']}")
    if issue_stats["resolved"] > 0:
        change_reasons.append(f"resolved_issue={issue_stats['resolved']}")
    if total_io_missing > 0:
        change_reasons.append(f"io_contract_missing={total_io_missing}")
    if mode == "bi_daily_recurring" and issue_stats["recurring_open_total"] > 0:
        change_reasons.append(f"recurring_open={issue_stats['recurring_open_total']}")

    # Noise control: silent mode only notifies on risks.
    notify = bool(risk_reasons)
    if not notify and normal_log_mode == "chat" and change_reasons:
        notify = True

    run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
    run_id = uuid.uuid4().hex[:12]
    job_name = str(args.task_id or "").split(":", 1)[-1] if ":" in str(args.task_id or "") else f"reviewer_{mode}"
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    lines = ["NO_REPLY"]
    if notify:
        lines = [
            f"# reviewer-cron/{mode}",
            f"agent: {DEFAULT_SENDER_PREFIX}:{mode}",
            f"job: {job_name}",
            f"task_id: {args.task_id or '-'}",
            f"run_id: {run_id}",
            f"time: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} UTC+8",
            f"run_duration_ms: {run_duration_ms}",
            f"priority: {priority}",
            f"risk_level: {risk_level}",
            f"normal_log_mode: {normal_log_mode}",
            f"repos: {len(repos)}",
            f"files: scanned={total_files_scanned}, skipped={total_files_skipped}",
            f"issue_summary: new={issue_stats['new']}, reopened={issue_stats['reopened']}, resolved={issue_stats['resolved']}, open={issue_stats['open_total']}, open_high={issue_stats['open_high_total']}, recurring_open={issue_stats['recurring_open_total']}",
            f"io_contract_missing: {total_io_missing} (planner should create TODO/request info before edits)",
        ]
        if risk_reasons:
            lines.append(f"risk_reasons: {', '.join(risk_reasons)}")
        if change_reasons:
            lines.append(f"change_reasons: {', '.join(change_reasons)}")
        if fix_result.get("ran"):
            lines.append(f"fix_command: ok={fix_result.get('ok')}, exit_code={fix_result.get('exit_code')}")
        manual_required = bool(risk_reasons)
        lines.append(f"manual_action_required: {str(manual_required).lower()}")
        if manual_required:
            lines.append("manual_action: coordinator 需确认高风险代码质量问题后再下发修复。")

    record = {
        "run_id": run_id,
        "sender_identity": f"{DEFAULT_SENDER_PREFIX}:{mode}",
        "task_id": args.task_id,
        "job_name": job_name,
        "priority": priority,
        "risk_level": risk_level,
        "run_duration_ms": run_duration_ms,
        "mode": mode,
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": normal_log_mode,
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "issue_stats": issue_stats,
        "summary": summary[:80],
        "fix_result": fix_result,
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_estimate": 0.0,
    }
    return RunResult(notify=notify, output="\n".join(lines), record=record)


def default_state() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-03",
        "updated_at": "",
        "runs": {"hourly_git": 0, "daily_incremental": 0, "bi_daily_recurring": 0, "weekly_structure": 0},
        "repos": {},
        "issues": {},
        "scan_fingerprints": {},
        "last_run_record": "",
    }


def run_mode(args: argparse.Namespace, state: dict[str, Any], normal_log_mode: str) -> RunResult:
    state.setdefault("runs", {})
    state["runs"][args.mode] = int(state["runs"].get(args.mode, 0) or 0) + 1
    if args.mode == "hourly_git":
        return run_hourly_git(args, state, normal_log_mode)
    if args.mode == "daily_incremental":
        return run_quality_scan(args, state, normal_log_mode, mode="daily_incremental", incremental_from_head=True, full_scan_skip_unchanged=False, run_fix_command=True)
    if args.mode == "bi_daily_recurring":
        return run_quality_scan(args, state, normal_log_mode, mode="bi_daily_recurring", incremental_from_head=False, full_scan_skip_unchanged=True, run_fix_command=False)
    return run_quality_scan(args, state, normal_log_mode, mode="weekly_structure", incremental_from_head=False, full_scan_skip_unchanged=False, run_fix_command=False)


def build_parser() -> argparse.ArgumentParser:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Reviewer scheduled scan runner")
    parser.add_argument("--mode", choices=["hourly_git", "daily_incremental", "bi_daily_recurring", "weekly_structure"], default="hourly_git")
    parser.add_argument("--workspace", default=str(home / ".openclaw/workspace"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/reviewer-scan-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/reviewer-scan-runs"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--emit-json", action="store_true")

    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--fix-command", default="")

    parser.add_argument("--git-fetch", action="store_true")
    parser.add_argument("--check-pr", action="store_true")
    parser.add_argument("--allow-merge", action="store_true")
    parser.add_argument("--push-after-merge", action="store_true")
    parser.add_argument("--merge-approval-file", default=str(home / ".openclaw/ops/reviewer-merge-approval.json"), help="json file with approved_prs/approved_branches")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    history_dir = Path(args.history_dir).expanduser()
    history_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state_file).expanduser()
    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    result = run_mode(args, state, normal_log_mode)

    stamp = now().strftime("%Y%m%d_%H%M%S")
    run_id = result.record.get("run_id", uuid.uuid4().hex[:8])
    run_file = history_dir / f"{stamp}_{args.mode}_{run_id}.json"
    save_json(run_file, result.record)
    state["updated_at"] = now_iso()
    state["last_run_record"] = str(run_file)
    save_json(state_path, state)

    if args.emit_json:
        print(json.dumps({"notify": result.notify, "output": result.output, "record": str(run_file)}, ensure_ascii=False))
        return 0

    if result.notify:
        print(f"{result.output}\n- evidence: {run_file}")
    else:
        print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

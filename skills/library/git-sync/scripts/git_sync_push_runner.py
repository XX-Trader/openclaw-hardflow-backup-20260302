#!/usr/bin/env python3
"""Git sync + commit + push runner for OpenClaw self-evolution flow.

Goals:
1) Keep local repository synced with remote via fetch/pull --ff-only.
2) Commit eligible local changes produced by automation.
3) Push to remote repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from chat_output import render_chat_notice, short_location_label

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_ON_MODES = {"error", "all"}
DEFAULT_EXCLUDE_PREFIXES = (
    ".workflow/project-index/",
    ".workflow/project-index-local/",
    ".workflow/experience/",
    ".workflow/sessions/",
    "scripts/openclaw-ops/policy/runtime/",
    "openclaw-memory/",
    "memory/",
)

# ── 第二层审核：敏感信息内容正则 ──────────────────────────────────────────
# 匹配到任何 pattern 的文件会被自动移出 eligible 列表，阻止 push。
SENSITIVE_CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key",     re.compile(r"(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.IGNORECASE)),
    ("private_key", re.compile(r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----")),
    ("openai_key",  re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("password",    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}", re.IGNORECASE)),
    ("bearer_token",re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE)),
    ("generic_token",re.compile(r"(?:token|access_token|auth_token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}", re.IGNORECASE)),
]

# 二进制/大文件扩展名跳过扫描（避免误报和性能问题）
SKIP_SCAN_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".gz", ".zip", ".tar", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ttf", ".eot", ".ico", ".db", ".sqlite"}


def scan_sensitive_content(
    repo: Path,
    files: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    """扫描 eligible 文件内容，检测敏感信息。

    Args:
        repo: 仓库根目录。
        files: 待检测的相对路径列表。

    Returns:
        (clean_files, alerts): clean_files 为通过检测的文件列表；
        alerts 为检测到敏感信息的告警记录列表，每条含 file/pattern/line_num。
    """
    clean: list[str] = []
    alerts: list[dict[str, str]] = []
    for rel_path in files:
        full_path = repo / rel_path
        if not full_path.is_file():
            clean.append(rel_path)
            continue
        suffix = full_path.suffix.lower()
        if suffix in SKIP_SCAN_EXTENSIONS:
            clean.append(rel_path)
            continue
        # 限制扫描文件大小（超过 512KB 跳过，避免卡住）
        try:
            file_size = full_path.stat().st_size
        except OSError:
            clean.append(rel_path)
            continue
        if file_size > 512 * 1024:
            clean.append(rel_path)
            continue
        found = False
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            for line_num, line in enumerate(content.splitlines(), start=1):
                for pattern_name, pattern_re in SENSITIVE_CONTENT_PATTERNS:
                    if pattern_re.search(line):
                        alerts.append({
                            "file": rel_path,
                            "pattern": pattern_name,
                            "line_num": str(line_num),
                        })
                        found = True
                        break
                if found:
                    break
        except Exception:
            pass
        if not found:
            clean.append(rel_path)
    return clean, alerts


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_rel(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("/")


def normalize_remote_url(url: str) -> str:
    text = str(url or "").strip()
    # Handle git@host:owner/repo(.git)
    if text.startswith("git@"):
        text = text[4:]
        if ":" in text:
            host, path = text.split(":", 1)
            text = f"{host}/{path}"

    # Handle scheme URL: https://host/owner/repo(.git), ssh://git@host/owner/repo
    if "://" in text:
        text = text.split("://", 1)[1]

    # Drop optional user part before host: git@github.com/owner/repo
    first_part, sep, rest = text.partition("/")
    if "@" in first_part:
        first_part = first_part.split("@", 1)[1]
    text = f"{first_part}{sep}{rest}" if sep else first_part

    # Drop host port if present: github.com:443/owner/repo
    host, sep, path = text.partition("/")
    if ":" in host:
        host = host.split(":", 1)[0]
    text = f"{host}{sep}{path}" if sep else host

    while text.endswith("/"):
        text = text[:-1]
    if text.lower().endswith(".git"):
        text = text[:-4]
    return text.strip().lower()


def run_git(
    repo: Path,
    args: list[str],
    *,
    timeout: int = 60,
) -> tuple[int, str, str]:
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
    stdout = (proc.stdout or "").replace("\r\n", "\n")
    stderr = (proc.stderr or "").strip()
    return proc.returncode, stdout, stderr


def parse_status_porcelain(raw: str) -> list[dict[str, str]]:
    if "\x00" in str(raw or ""):
        out_z: list[dict[str, str]] = []
        parts = [x for x in str(raw or "").split("\x00") if x]
        idx = 0
        while idx < len(parts):
            token = str(parts[idx] or "")
            if len(token) < 2:
                idx += 1
                continue
            if len(token) >= 3 and token[2] == " ":
                status = token[:2]
                path_raw = token[3:]
            elif len(token) >= 2 and token[1] == " ":
                # Defensive path: tolerate accidentally trimmed leading space in first record.
                status = f" {token[0]}"
                path_raw = token[2:]
            else:
                idx += 1
                continue
            path = normalize_rel(path_raw)
            if status[:1] in {"R", "C"} and idx + 1 < len(parts):
                renamed_to = normalize_rel(parts[idx + 1])
                if renamed_to:
                    path = renamed_to
                idx += 2
            else:
                idx += 1
            if not path:
                continue
            out_z.append({"status": status, "path": path})
        return out_z

    out: list[dict[str, str]] = []
    for line in str(raw or "").splitlines():
        text = line.rstrip("\n")
        if not text:
            continue
        # format: XY<space>path or XY<space>old -> new
        if len(text) < 2:
            continue
        if len(text) >= 3 and text[2] == " ":
            status = text[:2]
            path_raw = text[3:]
        elif len(text) >= 2 and text[1] == " ":
            status = f" {text[0]}"
            path_raw = text[2:]
        else:
            continue
        if " -> " in path_raw:
            path_raw = path_raw.split(" -> ", 1)[1]
        path = normalize_rel(path_raw)
        if not path:
            continue
        out.append({"status": status, "path": path})
    return out


def should_include(
    path: str,
    *,
    include_prefixes: list[str],
    exclude_prefixes: list[str],
) -> bool:
    rel = normalize_rel(path)
    if not rel:
        return False
    low = rel.lower()
    for prefix in exclude_prefixes:
        p = normalize_rel(prefix).lower()
        if p and low.startswith(p):
            return False
    if not include_prefixes:
        return True
    for prefix in include_prefixes:
        p = normalize_rel(prefix).lower()
        if p and low.startswith(p):
            return True
    return False


def resolve_branch(repo: Path, branch_arg: str) -> tuple[str, str]:
    wanted = str(branch_arg or "").strip()
    if wanted:
        return wanted, ""
    rc, out, err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    if rc != 0 or not out:
        return "", f"branch_detect_failed:{err or rc}"
    branch = str(out).strip()
    if branch in {"", "HEAD"}:
        return "", "detached_head_not_supported"
    return branch, ""


def resolve_upstream(repo: Path, remote: str, branch: str) -> str:
    rc, out, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=20)
    if rc == 0 and str(out).strip():
        return str(out).strip()
    candidate = f"{remote}/{branch}"
    rc2, _out2, _err2 = run_git(repo, ["rev-parse", "--verify", candidate], timeout=20)
    if rc2 == 0:
        return candidate
    return ""


def ahead_behind(repo: Path, upstream: str) -> tuple[int, int]:
    if not str(upstream or "").strip():
        return 0, 0
    rc, out, _err = run_git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"], timeout=20)
    if rc != 0:
        return 0, 0
    parts = str(out).split()
    ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
    behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    return ahead, behind


def chunked(values: list[str], size: int) -> list[list[str]]:
    out: list[list[str]] = []
    step = max(1, int(size))
    for idx in range(0, len(values), step):
        out.append(values[idx : idx + step])
    return out


def humanize_error(err: str) -> str:
    text = str(err or "").strip()
    if not text:
        return "未知错误"
    if text.startswith("repo_invalid:"):
        return f"仓库路径无效：{text.split(':', 1)[1]}"
    if text.startswith("not_git_repo:"):
        return f"目标目录不是 Git 仓库：{text.split(':', 1)[1]}"
    if text.startswith("branch_detect_failed:"):
        return f"分支识别失败：{text.split(':', 1)[1]}"
    if text == "detached_head_not_supported":
        return "当前仓库为 detached HEAD，无法自动同步"
    if text.startswith("remote_get_url_failed:"):
        return f"读取远程地址失败：{text.split(':', 1)[1]}"
    if text.startswith("remote_url_not_allowed:"):
        return f"远程仓库地址不在允许列表：{text.split(':', 1)[1]}"
    if text.startswith("git_fetch_failed:"):
        return f"git fetch 失败：{text.split(':', 1)[1]}"
    if text == "behind_with_local_changes_requires_manual_rebase":
        return "本地有未处理改动且落后远端，需人工处理后再 pull"
    if text.startswith("git_pull_rebase_conflict:"):
        return f"pull --rebase 冲突（已自动 abort 回滚），需人工解决：{text.split(':', 1)[1]}"
    if text.startswith("git_pull_ff_only_failed:"):
        return f"git pull --ff-only 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_status_failed:"):
        return f"git status 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_add_failed:"):
        return f"git add 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_diff_cached_failed:"):
        return f"读取暂存区变更失败：{text.split(':', 1)[1]}"
    if text.startswith("git_commit_failed:"):
        return f"git commit 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_push_failed:"):
        return f"git push 失败：{text.split(':', 1)[1]}"
    return text


def classify_pull_blockers(
    changes: list[dict[str, str]],
    *,
    include_prefixes: list[str],
    exclude_prefixes: list[str],
) -> tuple[list[str], list[str]]:
    """Return (blocking_files, ignored_untracked_files) before pull.

    Blocking rules:
    1) Any tracked local change blocks pull.
    2) Any untracked change that falls into include scope blocks pull.
    3) Untracked excluded/runtime files are ignored for pull pre-check.
    """

    blocking: list[str] = []
    ignored_untracked: list[str] = []
    for item in changes:
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        status = str(item.get("status", "")).strip()
        is_untracked = status == "??"
        if not is_untracked:
            blocking.append(path)
            continue
        if should_include(path, include_prefixes=include_prefixes, exclude_prefixes=exclude_prefixes):
            blocking.append(path)
        else:
            ignored_untracked.append(path)
    return sorted(set(blocking)), sorted(set(ignored_untracked))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local git repository and push self-evolution changes")
    parser.add_argument("--repo-path", default=".", help="target git repository path")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="")
    parser.add_argument("--auto-pull", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--push", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-remote-url", action="append", default=[])
    parser.add_argument("--commit-prefix", default="chore(self-evolution): sync updates")
    parser.add_argument("--commit-message", default="")
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--notify-on", default="error", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    repo = Path(str(args.repo_path or ".")).expanduser().resolve()
    remote = str(args.remote or "origin").strip() or "origin"
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    include_prefixes = [normalize_rel(x) for x in args.include_prefix if str(x).strip()]
    exclude_prefixes = [normalize_rel(x) for x in args.exclude_prefix if str(x).strip()]
    if not exclude_prefixes:
        exclude_prefixes = [normalize_rel(x) for x in DEFAULT_EXCLUDE_PREFIXES]

    result: dict[str, Any] = {
        "time": now_iso(),
        "task_id": str(args.task_id or "").strip(),
        "repo": str(repo),
        "remote": remote,
        "remote_url": "",
        "required_remote_urls": [],
        "normal_log_mode": log_mode,
        "branch": "",
        "upstream": "",
        "fetch_ok": False,
        "pull_ok": False,
        "pulled": False,
        "committed": False,
        "commit_sha": "",
        "pushed": False,
        "ahead": 0,
        "behind": 0,
        "pull_blocking_files": [],
        "pull_ignored_untracked": [],
        "eligible_files": [],
        "skipped_files": [],
        "errors": [],
    }

    if not repo.exists() or (not repo.is_dir()):
        result["errors"].append(f"repo_invalid:{repo}")
    else:
        rc, out, err = run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=20)
        if rc != 0 or str(out).strip().lower() != "true":
            result["errors"].append(f"not_git_repo:{err or out or repo}")

    branch = ""
    if not result["errors"]:
        branch, branch_err = resolve_branch(repo, str(args.branch or ""))
        if branch_err:
            result["errors"].append(branch_err)
        else:
            result["branch"] = branch
        rc, remote_url, err = run_git(repo, ["remote", "get-url", remote], timeout=20)
        if rc != 0 or not str(remote_url).strip():
            result["errors"].append(f"remote_get_url_failed:{err or rc}")
        else:
            remote_url_text = str(remote_url).strip()
            result["remote_url"] = remote_url_text
            required_urls = [str(x).strip() for x in args.require_remote_url if str(x).strip()]
            result["required_remote_urls"] = required_urls
            if required_urls:
                got = normalize_remote_url(remote_url_text)
                allow = {normalize_remote_url(x) for x in required_urls if normalize_remote_url(x)}
                if got not in allow:
                    result["errors"].append(
                        "remote_url_not_allowed:"
                        + f"got={remote_url_text}"
                    )

    if not result["errors"]:
        rc, _out, err = run_git(repo, ["fetch", "--all", "--prune"], timeout=180)
        result["fetch_ok"] = rc == 0
        if rc != 0:
            result["errors"].append(f"git_fetch_failed:{err or rc}")

    upstream = ""
    if not result["errors"]:
        upstream = resolve_upstream(repo, remote=remote, branch=branch)
        result["upstream"] = upstream
        ahead, behind = ahead_behind(repo, upstream)
        result["ahead"] = ahead
        result["behind"] = behind

    # ── 阶段 1：收集本地变更、筛选 eligible 文件 ────────────────────────
    if not result["errors"]:
        rc, status_out, err = run_git(repo, ["status", "--porcelain", "-z", "--untracked-files=all"], timeout=30)
        if rc != 0:
            result["errors"].append(f"git_status_failed:{err or rc}")
        else:
            changes = parse_status_porcelain(status_out)
            eligible: list[str] = []
            skipped: list[str] = []
            for item in changes:
                path = str(item.get("path", "")).strip()
                if should_include(path, include_prefixes=include_prefixes, exclude_prefixes=exclude_prefixes):
                    eligible.append(path)
                else:
                    skipped.append(path)
            max_files = max(1, int(args.max_files))
            if len(eligible) > max_files:
                skipped.extend(eligible[max_files:])
                eligible = eligible[:max_files]
            result["eligible_files"] = sorted(set(eligible))
            result["skipped_files"] = sorted(set(skipped))

    # ── 阶段 2：敏感信息内容扫描 ──────────────────────────────────────
    if not result["errors"] and result["eligible_files"]:
        clean_files, sensitive_alerts = scan_sensitive_content(
            repo, list(result["eligible_files"])
        )
        if sensitive_alerts:
            result["sensitive_alerts"] = sensitive_alerts
            blocked_files = sorted({a["file"] for a in sensitive_alerts})
            result["sensitive_blocked_files"] = blocked_files
            result["eligible_files"] = sorted(set(clean_files))
            result["skipped_files"] = sorted(
                set(result.get("skipped_files", []) + blocked_files)
            )
            result["errors"].append(
                f"sensitive_content_detected:{len(blocked_files)}_files_blocked"
            )

    # ── 阶段 3：Agent 审核摘要（异步复查凭据） ────────────────────────
    if not result["errors"] and result["eligible_files"]:
        review_summary = {
            "review_time": now_iso(),
            "task_id": result.get("task_id", ""),
            "eligible_count": len(result["eligible_files"]),
            "eligible_files": result["eligible_files"][:50],
            "skipped_count": len(result.get("skipped_files", [])),
            "sensitive_alerts": result.get("sensitive_alerts", []),
            "review_status": "auto_approved",
            "review_note": "第二层密钥检测通过，自动放行。ops-agent 可异步复查本摘要。",
        }
        review_dir = repo / ".workflow" / "sync-reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_file = review_dir / f"review-{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}.json"
        try:
            review_file.write_text(
                json.dumps(review_summary, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            result["agent_review_file"] = str(review_file)
        except OSError:
            pass  # 审核摘要写入失败不阻断主流程

    # ── 阶段 4：git add + commit（先提交本地 eligible 改动）────────────
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
                commit_prefix = str(args.commit_prefix or "").strip() or "chore(self-evolution): sync updates"
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

    # ── 阶段 5：pull --rebase（commit 后再同步远端）───────────────────
    # 先刷新 ahead/behind 状态（commit 后 ahead 可能变化）
    if not result["errors"]:
        upstream_after = resolve_upstream(repo, remote=remote, branch=branch)
        result["upstream"] = upstream_after or result["upstream"]
        ahead, behind = ahead_behind(repo, upstream_after)
        result["ahead"] = ahead
        result["behind"] = behind

    if not result["errors"] and bool(args.auto_pull) and int(result.get("behind", 0)) > 0:
        # commit-first 策略：本地改动已提交，可以安全 rebase
        rc, _out, err = run_git(repo, ["pull", "--rebase", remote, branch], timeout=240)
        if rc == 0:
            result["pull_ok"] = True
            result["pulled"] = True
            upstream_ref = upstream or f"{remote}/{branch}"
            ahead, behind = ahead_behind(repo, upstream_ref)
            result["ahead"] = ahead
            result["behind"] = behind
        else:
            # rebase 冲突：自动 abort 回滚，不丢代码，通知人工处理
            run_git(repo, ["rebase", "--abort"], timeout=30)
            result["errors"].append(f"git_pull_rebase_conflict:{err or rc}")

    # ── 阶段 6：push ─────────────────────────────────────────────────
    should_push = bool(args.push)
    if not result["errors"] and should_push and int(result.get("ahead", 0)) > 0:
        rc, _out, err = run_git(repo, ["push", "-u", remote, branch], timeout=240)
        if rc != 0:
            result["errors"].append(f"git_push_failed:{err or rc}")
        else:
            result["pushed"] = True

    notify_on = str(args.notify_on or "error").strip().lower()
    if notify_on not in NOTIFY_ON_MODES:
        notify_on = "error"
    notify = bool(result["errors"])
    if notify_on == "all":
        notify = notify or bool(result["committed"]) or bool(result["pushed"]) or bool(result["pulled"])
    output = "NO_REPLY"
    if notify:
        if result["errors"]:
            output = render_chat_notice(
                "Git 同步异常",
                status="需处理",
                task_id=str(result["task_id"] or ""),
                sender_identity="optimization-agent/git-sync",
                run_time=str(result["time"] or ""),
                summary=f"Git 同步发现 {len(result['errors'])} 个异常。",
                extra_lines=[
                    f"目标仓库：{short_location_label(str(result['repo'] or ''))}",
                    f"分支：{result['branch'] or '-'}",
                    f"远程地址：{result['remote_url'] or '-'}",
                    f"上游分支：{result['upstream'] or '-'}",
                ],
                details=[f"异常{idx}：{humanize_error(err)}" for idx, err in enumerate(result["errors"][:10], start=1)],
                next_step="请先检查远端连通性、分支状态和自动提交结果。",
            )
        else:
            extra_lines = [
                f"目标仓库：{short_location_label(str(result['repo'] or ''))}",
                f"分支：{result['branch'] or '-'}",
                f"抓取远端：{'成功' if result['fetch_ok'] else '失败'}",
                f"拉取更新：{'已执行' if result['pulled'] else '未执行'}",
                f"自动提交：{'已提交' if result['committed'] else '无变更'}",
                f"远端推送：{'已推送' if result['pushed'] else '未推送'}",
            ]
            if str(result.get("commit_sha", "")).strip():
                extra_lines.append(f"提交哈希：{result['commit_sha']}")
            output = render_chat_notice(
                "Git 同步结果",
                status="已完成",
                task_id=str(result["task_id"] or ""),
                sender_identity="optimization-agent/git-sync",
                run_time=str(result["time"] or ""),
                summary="Git 同步流程已执行完成。",
                extra_lines=extra_lines,
                next_step="如需复核，请查看远端提交记录与内部运行日志。",
            )

    if bool(args.emit_json):
        print(json.dumps({"notify": notify, "output": output, "result": result}, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

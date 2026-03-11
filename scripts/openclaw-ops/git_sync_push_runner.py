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
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

    if not result["errors"] and bool(args.auto_pull) and int(result.get("behind", 0)) > 0:
        rc, status_out, status_err = run_git(repo, ["status", "--porcelain", "-z", "--untracked-files=all"], timeout=20)
        if rc != 0:
            result["errors"].append(f"git_status_failed:{status_err or rc}")
        else:
            changes_before_pull = parse_status_porcelain(status_out)
            blockers, ignored_untracked = classify_pull_blockers(
                changes_before_pull,
                include_prefixes=include_prefixes,
                exclude_prefixes=exclude_prefixes,
            )
            result["pull_blocking_files"] = blockers
            result["pull_ignored_untracked"] = ignored_untracked
            if blockers:
                result["errors"].append("behind_with_local_changes_requires_manual_rebase")
            else:
                rc, _out, err = run_git(repo, ["pull", "--ff-only", remote, branch], timeout=240)
                result["pull_ok"] = rc == 0
                result["pulled"] = rc == 0
                if rc != 0:
                    result["errors"].append(f"git_pull_ff_only_failed:{err or rc}")
                else:
                    ahead, behind = ahead_behind(repo, upstream or f"{remote}/{branch}")
                    result["ahead"] = ahead
                    result["behind"] = behind

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

    if not result["errors"]:
        upstream_after = resolve_upstream(repo, remote=remote, branch=branch)
        result["upstream"] = upstream_after or result["upstream"]
        ahead, behind = ahead_behind(repo, upstream_after)
        result["ahead"] = ahead
        result["behind"] = behind

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

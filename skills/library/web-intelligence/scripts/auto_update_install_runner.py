#!/usr/bin/env python3
"""Hourly workflow auto update runner: pull latest code, then run installer."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Source checkouts keep each script under its owning Skill; installed runtimes
# flatten the same dependencies into the ops directory. Bootstrap only when
# the repository marker is present so both layouts share one implementation.
for _candidate_root in Path(__file__).resolve().parents:
    _shared_dir = _candidate_root / "scripts" / "openclaw-ops" / "shared"
    if _shared_dir.is_dir():
        _shared_value = str(_shared_dir)
        if _shared_value not in sys.path:
            sys.path.insert(0, _shared_value)
        from repo_imports import bootstrap_repository_imports

        bootstrap_repository_imports(__file__)
        break

from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_ON_MODES = {"error", "all"}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def now_compact() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_remote_url(url: str) -> str:
    text = str(url or "").strip()
    if text.startswith("git@"):
        text = text[4:]
        if ":" in text:
            host, path = text.split(":", 1)
            text = f"{host}/{path}"
    if "://" in text:
        text = text.split("://", 1)[1]
    first, sep, rest = text.partition("/")
    if "@" in first:
        first = first.split("@", 1)[1]
    text = f"{first}{sep}{rest}" if sep else first
    host, sep, path = text.partition("/")
    if ":" in host:
        host = host.split(":", 1)[0]
    text = f"{host}{sep}{path}" if sep else host
    while text.endswith("/"):
        text = text[:-1]
    if text.lower().endswith(".git"):
        text = text[:-4]
    return text.strip().lower()


def run_git(repo: Path, args: list[str], *, timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def run_shell(command: str, *, cwd: Path, timeout: int) -> tuple[int, str, str]:
    shell_executable = "/bin/bash" if os.name == "posix" else None
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout)),
            check=False,
            shell=True,
            executable=shell_executable,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or ""), (proc.stderr or "")


def repo_is_dirty(repo: Path) -> tuple[bool, str]:
    rc, out, err = run_git(repo, ["status", "--porcelain"], timeout=20)
    if rc != 0:
        return False, f"git_status_failed:{err or rc}"
    return bool(str(out).strip()), ""


def stash_local_changes(repo: Path, label: str, *, timeout: int) -> tuple[bool, str]:
    rc, out, err = run_git(
        repo,
        ["stash", "push", "--include-untracked", "--message", label],
        timeout=timeout,
    )
    if rc != 0:
        return False, f"git_stash_failed:{err or out or rc}"
    text = str(out or err or "").strip()
    if "No local changes to save" in text:
        return False, ""
    return True, ""


def resolve_branch(repo: Path, branch_arg: str) -> tuple[str, str]:
    wanted = str(branch_arg or "").strip()
    if wanted:
        return wanted, ""
    rc, out, err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    if rc != 0 or not out:
        return "", f"branch_detect_failed:{err or rc}"
    branch = str(out).strip()
    if not branch or branch == "HEAD":
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
        return "当前仓库为 detached HEAD，无法自动更新"
    if text.startswith("remote_get_url_failed:"):
        return f"读取远程地址失败：{text.split(':', 1)[1]}"
    if text.startswith("remote_url_not_allowed:"):
        return f"远程仓库地址不在允许列表：{text.split(':', 1)[1]}"
    if text.startswith("git_fetch_failed:"):
        return f"git fetch 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_status_failed:"):
        return f"git status 失败：{text.split(':', 1)[1]}"
    if text.startswith("git_stash_failed:"):
        return f"自动暂存失败：{text.split(':', 1)[1]}"
    if text.startswith("git_pull_ff_only_failed:"):
        return f"git pull --ff-only 失败：{text.split(':', 1)[1]}"
    if text == "install_cmd_missing":
        return "缺少安装命令（install_cmd）"
    if text.startswith("install_failed:"):
        return f"安装命令执行失败：{text.split(':', 1)[1]}"
    return text


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto pull latest workflow repo and run installer")
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="")
    parser.add_argument("--auto-pull", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-remote-url", action="append", default=[])
    parser.add_argument("--install-cmd", default="")
    parser.add_argument("--install-on-no-change", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--auto-stash-before-pull", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--git-timeout", type=int, default=240)
    parser.add_argument("--install-timeout", type=int, default=2400)
    parser.add_argument("--report-dir", default=str(Path.home() / ".openclaw/ops/update-install-runs"))
    parser.add_argument("--notify-on", default="error", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    repo = Path(str(args.repo_path or ".")).expanduser().resolve()
    report_dir = Path(str(args.report_dir or "")).expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{now_compact()}_{(str(args.task_id or 'auto-update').replace(':', '_') or 'run')}"
    stdout_file = report_dir / f"{run_id}.install.stdout.log"
    stderr_file = report_dir / f"{run_id}.install.stderr.log"
    report_file = report_dir / f"{run_id}.json"

    result: dict[str, Any] = {
        "time": now_iso(),
        "task_id": str(args.task_id or "").strip(),
        "repo": str(repo),
        "remote": str(args.remote or "origin").strip() or "origin",
        "branch": "",
        "upstream": "",
        "remote_url": "",
        "required_remote_urls": [str(x).strip() for x in args.require_remote_url if str(x).strip()],
        "fetch_ok": False,
        "pull_ok": False,
        "pulled": False,
        "ahead": 0,
        "behind": 0,
        "install_cmd": str(args.install_cmd or "").strip(),
        "install_ran": False,
        "install_ok": False,
        "install_returncode": None,
        "repo_dirty_before_pull": False,
        "stashed_before_pull": False,
        "stash_label": "",
        "stdout_log": str(stdout_file),
        "stderr_log": str(stderr_file),
        "report_file": str(report_file),
        "errors": [],
    }

    if not repo.exists() or not repo.is_dir():
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
        rc, out, err = run_git(repo, ["remote", "get-url", result["remote"]], timeout=20)
        if rc != 0 or not str(out).strip():
            result["errors"].append(f"remote_get_url_failed:{err or rc}")
        else:
            remote_url = str(out).strip()
            result["remote_url"] = remote_url
            if result["required_remote_urls"]:
                got = normalize_remote_url(remote_url)
                allow = {normalize_remote_url(x) for x in result["required_remote_urls"] if normalize_remote_url(x)}
                if got not in allow:
                    result["errors"].append(f"remote_url_not_allowed:got={remote_url}")

    if not result["errors"]:
        rc, _out, err = run_git(repo, ["fetch", "--all", "--prune"], timeout=args.git_timeout)
        result["fetch_ok"] = rc == 0
        if rc != 0:
            result["errors"].append(f"git_fetch_failed:{err or rc}")

    if not result["errors"]:
        upstream = resolve_upstream(repo, result["remote"], branch)
        result["upstream"] = upstream
        ahead, behind = ahead_behind(repo, upstream)
        result["ahead"] = ahead
        result["behind"] = behind

    if not result["errors"] and bool(args.auto_pull) and int(result.get("behind", 0)) > 0:
        if bool(args.auto_stash_before_pull):
            dirty, dirty_err = repo_is_dirty(repo)
            if dirty_err:
                result["errors"].append(dirty_err)
            else:
                result["repo_dirty_before_pull"] = bool(dirty)
                if dirty:
                    stash_label = f"auto-update-install:{now_compact()}"
                    stashed, stash_err = stash_local_changes(
                        repo,
                        stash_label,
                        timeout=int(args.git_timeout),
                    )
                    if stash_err:
                        result["errors"].append(stash_err)
                    else:
                        result["stashed_before_pull"] = bool(stashed)
                        if stashed:
                            result["stash_label"] = stash_label
        rc, _out, err = run_git(
            repo,
            ["pull", "--ff-only", result["remote"], branch],
            timeout=args.git_timeout,
        )
        result["pull_ok"] = rc == 0
        result["pulled"] = rc == 0
        if rc != 0:
            result["errors"].append(f"git_pull_ff_only_failed:{err or rc}")
        else:
            upstream = resolve_upstream(repo, result["remote"], branch)
            result["upstream"] = upstream
            ahead, behind = ahead_behind(repo, upstream)
            result["ahead"] = ahead
            result["behind"] = behind

    should_install = bool(result["pulled"]) or bool(args.install_on_no_change)
    install_stdout = ""
    install_stderr = ""
    if should_install:
        if not result["install_cmd"]:
            result["errors"].append("install_cmd_missing")
        elif not result["errors"]:
            result["install_ran"] = True
            rc, out, err = run_shell(
                result["install_cmd"],
                cwd=repo,
                timeout=int(args.install_timeout),
            )
            result["install_returncode"] = int(rc)
            install_stdout = out
            install_stderr = err
            if rc == 0:
                result["install_ok"] = True
            else:
                result["errors"].append(f"install_failed:rc={rc}")

    write_text(stdout_file, install_stdout)
    write_text(stderr_file, install_stderr)
    write_text(report_file, json.dumps(result, ensure_ascii=False, indent=2))

    notify_on = str(args.notify_on or "error").strip().lower()
    if notify_on not in NOTIFY_ON_MODES:
        notify_on = "error"
    notify = bool(result["errors"])
    if notify_on == "all":
        notify = notify or bool(result["pulled"]) or bool(result["install_ran"])
    output = "NO_REPLY"
    if notify:
        if result["errors"]:
            lines = [
                "# 自动更新安装异常",
                f"- 任务: {result['task_id'] or '-'}",
                f"- 时间: {result['time']}",
                f"- 仓库: {result['repo']}",
                f"- 分支: {result['branch'] or '-'}",
                f"- 远程: {result['remote_url'] or '-'}",
                f"- 错误数量: {len(result['errors'])}",
            ]
            for idx, err in enumerate(result["errors"][:10], start=1):
                lines.append(f"- 异常{idx}: {humanize_error(err)}")
            lines.append(f"- 详细报告: {result['report_file']}")
            lines.append(f"- 安装标准输出: {result['stdout_log']}")
            lines.append(f"- 安装标准错误: {result['stderr_log']}")
        else:
            lines = [
                "# 自动更新安装结果",
                f"- 任务: {result['task_id'] or '-'}",
                f"- 时间: {result['time']}",
                f"- 仓库: {result['repo']}",
                f"- 分支: {result['branch'] or '-'}",
                f"- 拉取最新: {'是' if result['pulled'] else '否'}",
                f"- 安装执行: {'是' if result['install_ran'] else '否'}",
                f"- 安装成功: {'是' if result['install_ok'] else '否'}",
            ]
        output = "\n".join(lines)

    if bool(args.emit_json):
        print(json.dumps({"notify": notify, "output": output, "result": result}, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

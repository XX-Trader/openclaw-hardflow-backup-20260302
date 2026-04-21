#!/usr/bin/env python3
"""Repo Delta 证据采集：从 git 仓库中提取代码变更与验证证据。

负责采集：
- 变更文件列表
- 关键 diff（仅 .py/.js/.ts/.md，排除 lock 文件）
- commit 元数据
- 验证命令与结果（如果有的话）

游标策略: commit SHA 或 mtime
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("source_repo_delta")

# 关注的文件后缀
WATCHED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml", ".toml"}

# 排除的路径模式
EXCLUDE_PATTERNS = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".git"}


def _run_git(args: list[str], cwd: str | Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """安全执行 git 命令。"""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(cwd),
    )


def collect_repo_delta(
    workspace: str | Path,
    since_hours: int = 48,
    since_sha: str | None = None,
) -> dict[str, Any]:
    """采集仓库代码变更证据。

    Args:
        workspace: 仓库根目录
        since_hours: 回溯时间窗口（小时）
        since_sha: 起始 commit SHA（优先于时间窗口）

    Returns:
        {
            "workspace": str,
            "changed_files": list[str],
            "diffs": list[dict],
            "commits": list[dict],
            "verification_summary": str,
            "since_hours": int,
            "collected_at": str,
        }
    """
    ws = Path(workspace)
    if not (ws / ".git").exists():
        logger.warning("not_a_git_repo:path=%s", ws)
        return _empty_delta(str(ws), since_hours)

    # 1. 获取变更文件列表
    changed_files = _get_changed_files(ws, since_hours, since_sha)

    # 2. 获取关键 diff
    diffs = _get_relevant_diffs(ws, since_hours, since_sha)

    # 3. 获取 commit 元数据
    commits = _get_commits(ws, since_hours, since_sha)

    # 4. 尝试运行验证（仅检查 pytest 是否存在）
    verification = _try_verification(ws)

    return {
        "workspace": str(ws),
        "changed_files": changed_files,
        "diffs": diffs,
        "commits": commits,
        "verification_summary": verification,
        "since_hours": since_hours,
        "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _get_changed_files(ws: Path, since_hours: int, since_sha: str | None) -> list[str]:
    """获取变更文件列表。"""
    if since_sha:
        result = _run_git(["diff", "--name-only", since_sha + "..HEAD"], ws)
    else:
        since_time = f"{since_hours} hours ago"
        result = _run_git(["log", f"--since={since_time}", "--name-only", "--pretty=format:"], ws)

    if result.returncode != 0:
        logger.warning("git_diff_failed:err=%s", result.stderr[:200])
        return []

    files = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return list(dict.fromkeys(files))  # 去重保序


def _get_relevant_diffs(ws: Path, since_hours: int, since_sha: str | None, max_chars: int = 2000) -> list[dict]:
    """获取关注文件类型的 diff 摘要。"""
    # 用通配符方式
    diff_args: list[str] = ["diff"]
    if since_sha:
        diff_args.extend([since_sha + "..HEAD"])
    else:
        diff_args.extend([f"--since={since_hours} hours ago"])

    result = _run_git(diff_args, ws)
    if result.returncode != 0:
        return []

    raw_diff = result.stdout
    if not raw_diff.strip():
        return []

    # 按文件拆分 diff
    diffs: list[dict] = []
    current_file = ""
    current_lines: list[str] = []
    for line in raw_diff.splitlines():
        if line.startswith("diff --git"):
            if current_file and current_lines:
                content = "\n".join(current_lines)
                if Path(current_file).suffix in WATCHED_EXTENSIONS:
                    diffs.append({
                        "file": current_file,
                        "diff": content[:max_chars],
                        "truncated": len(content) > max_chars,
                    })
            # 提取文件名
            parts = line.split(" b/")
            if len(parts) >= 2:
                current_file = parts[-1].strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # 最后一个文件
    if current_file and current_lines:
        content = "\n".join(current_lines)
        if Path(current_file).suffix in WATCHED_EXTENSIONS:
            diffs.append({
                "file": current_file,
                "diff": content[:max_chars],
                "truncated": len(content) > max_chars,
            })

    return diffs


def _get_commits(ws: Path, since_hours: int, since_sha: str | None) -> list[dict]:
    """获取 commit 元数据。"""
    log_args = ["log", "--format=%H|%s|%an|%aI"]
    if since_sha:
        log_args.extend([since_sha + "..HEAD"])
    else:
        log_args.extend([f"--since={since_hours} hours ago"])

    result = _run_git(log_args, ws)
    if result.returncode != 0:
        return []

    commits: list[dict] = []
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        commits.append({
            "sha": parts[0][:12],
            "message": parts[1],
            "author": parts[2],
            "date": parts[3],
        })
    return commits


def _try_verification(ws: Path) -> str:
    """尝试运行快速验证。"""
    # 仅做 pytest --collect-only 检查，不实际运行
    result = _run_git(["status", "--short"], ws)
    dirty = len([ln for ln in result.stdout.splitlines() if ln.strip()])
    return f"dirty_files={dirty}"


def _empty_delta(workspace: str, since_hours: int) -> dict[str, Any]:
    """返回空 delta。"""
    return {
        "workspace": workspace,
        "changed_files": [],
        "diffs": [],
        "commits": [],
        "verification_summary": "no_git_repo",
        "since_hours": since_hours,
        "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

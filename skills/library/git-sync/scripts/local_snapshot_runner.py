#!/usr/bin/env python3
"""Local snapshot runner: sync core config from .openclaw/ (C layer) to the hardflow backup repo (B layer).

This script is intended to run hourly via cron. It copies key configuration and
workflow files from the OpenClaw runtime directory (~/.openclaw/) into the git
backup repository so that ops_git_sync_push can later commit and push them.

Usage:
    python3 local_snapshot_runner.py \
        --openclaw-home ~/.openclaw \
        --repo-path ~/openclaw-hardflow-backup-20260302 \
        --task-id cron:local-snapshot \
        --notify-on error
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

# ── 同步白名单：只同步这些核心配置到 B 层 ────────────────────────────
# 相对于 ~/.openclaw/ 的路径前缀
SYNC_INCLUDE_PATTERNS: list[str] = [
    "openclaw.json",
    "hooks/",
    "skills/",
    "agents/",
    "cron/jobs.json",
    "cron/jobs_agent_mapping.md",
    "ops/",
]

# ── 排除列表：即使命中白名单也不同步 ─────────────────────────────────
SYNC_EXCLUDE_PATTERNS: list[str] = [
    "ops/task-center/",
    "ops/governance-evolution/reports/",
    "ops/exception-reports/",
    "ops/daily-todo-digest/",
    "skills/library/",
    "skills/pua-methodology/",
    "sessions/",
    "auth-profiles.json",
    "__pycache__/",
    ".pyc",
    ".DS_Store",
    ".bak",
    "node_modules/",
]


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def should_sync(rel_path: str) -> bool:
    """判断相对路径是否在同步白名单内且不在排除列表中。"""
    normalized = rel_path.replace("\\", "/")

    # 先检查排除
    for exclude in SYNC_EXCLUDE_PATTERNS:
        if exclude in normalized:
            return False

    # 再检查白名单
    for include in SYNC_INCLUDE_PATTERNS:
        if normalized == include or normalized.startswith(include):
            return True
    return False


def collect_syncable_files(openclaw_home: Path) -> list[str]:
    """扫描 C 层，收集所有需要同步的文件相对路径。"""
    result: list[str] = []
    for root, _dirs, files in os.walk(str(openclaw_home)):
        for fname in files:
            full = Path(root) / fname
            try:
                rel = str(full.relative_to(openclaw_home)).replace("\\", "/")
            except ValueError:
                continue
            if should_sync(rel):
                result.append(rel)
    return sorted(result)


def sync_file(src: Path, dst: Path) -> bool:
    """复制单个文件（仅当内容变更时复制）。返回是否发生了实际复制。

    Args:
        src: 源文件（C 层）。
        dst: 目标文件（B 层）。

    Returns:
        True 表示文件有更新，False 表示无变化跳过。
    """
    if not src.exists():
        return False

    # 目标已存在且内容相同则跳过
    if dst.exists():
        try:
            if filecmp.cmp(str(src), str(dst), shallow=False):
                return False
        except OSError:
            pass

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync core config from .openclaw/ to backup repo")
    parser.add_argument("--openclaw-home", default=os.path.expanduser("~/.openclaw"),
                        help="OpenClaw runtime directory (C layer)")
    parser.add_argument("--repo-path", default=os.path.expanduser("~/openclaw-hardflow-backup-20260302"),
                        help="Backup git repo (B layer)")
    parser.add_argument("--task-id", default="cron:local-snapshot")
    parser.add_argument("--notify-on", default="error", choices=["error", "all"])
    parser.add_argument("--dry-run", action="store_true", help="Only list files, don't copy")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    openclaw_home = Path(args.openclaw_home).expanduser().resolve()
    repo_path = Path(args.repo_path).expanduser().resolve()

    result: dict[str, Any] = {
        "time": now_iso(),
        "task_id": args.task_id,
        "openclaw_home": str(openclaw_home),
        "repo_path": str(repo_path),
        "synced_files": [],
        "skipped_files": [],
        "errors": [],
    }

    # 校验目录
    if not openclaw_home.is_dir():
        result["errors"].append(f"openclaw_home_not_found:{openclaw_home}")
    if not repo_path.is_dir():
        result["errors"].append(f"repo_path_not_found:{repo_path}")

    if not result["errors"]:
        syncable = collect_syncable_files(openclaw_home)
        for rel in syncable:
            src = openclaw_home / rel
            dst = repo_path / rel
            if args.dry_run:
                result["synced_files"].append(rel)
                continue
            try:
                if sync_file(src, dst):
                    result["synced_files"].append(rel)
                else:
                    result["skipped_files"].append(rel)
            except OSError as e:
                result["errors"].append(f"copy_failed:{rel}:{e}")

    # 输出
    notify_on = args.notify_on
    has_changes = bool(result["synced_files"])
    has_errors = bool(result["errors"])
    should_notify = has_errors or (notify_on == "all" and has_changes)

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    elif should_notify:
        if has_errors:
            print(f"[快照异常] {len(result['errors'])} 个错误")
            for err in result["errors"][:5]:
                print(f"  - {err}")
        if has_changes:
            print(f"[快照完成] 同步 {len(result['synced_files'])} 个文件到 B 层")
            for f in result["synced_files"][:20]:
                print(f"  + {f}")
    else:
        print("NO_REPLY")

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

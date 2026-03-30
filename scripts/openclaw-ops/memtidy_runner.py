#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memtidy_runner.py — 记忆文件自动整理工具

扫描记忆目录中的 .md 文件，按热/温/冷三层策略执行：
- 热记忆（30天内）：保持原样
- 温记忆（31-180天）：超长文件压缩摘要
- 冷记忆（180天+）：移入归档目录
- 修剪：删除匹配废弃关键词的文件
- 保护：跳过核心身份/偏好等关键文件

用法:
    python memtidy_runner.py --help
    python memtidy_runner.py --rules-file config/memtidy_rules.json --dry-run
    python memtidy_runner.py --rules-file config/memtidy_rules.json --memory-dirs /root/.openclaw/memory/
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# 规则加载
# ──────────────────────────────────────────────

DEFAULT_RULES = {
    "hot_memory": {"days": 30},
    "warm_memory": {"days_min": 31, "days_max": 180, "compact_threshold_lines": 200, "compact_target_lines": 80},
    "cold_memory": {"days": 181, "archive_dir": "~/.openclaw/memory-archive/"},
    "prune": {"keywords": ["测试对话", "调试日志", "临时笔记", "test_session", "debug_log", "tmp_", "scratch_"], "max_file_size_bytes": 102400, "empty_file_action": "delete"},
    "protected_patterns": ["MEMORY.md", "core-identity", "偏好", "system-prompt", "soul", "INDEX.md", "agent.md"],
    "backup": {"enabled": True, "dir": "~/.openclaw/ops/memtidy-backups/", "max_backups": 7},
    "report": {"output_dir": "~/.openclaw/ops/memtidy-reports/", "format": ["json", "markdown"]},
}


def load_rules(rules_file_path):
    """
    加载 MemTidy 规则配置文件。

    Args:
        rules_file_path: 规则 JSON 文件路径，为 None 则使用默认规则。

    Returns:
        dict: 合并后的规则配置。

    Raises:
        FileNotFoundError: 指定的规则文件不存在时抛出。
    """
    if not rules_file_path:
        return DEFAULT_RULES

    rules_path = Path(rules_file_path)
    if not rules_path.exists():
        raise FileNotFoundError(f"规则文件不存在: {rules_file_path}")

    with open(rules_path, "r", encoding="utf-8") as rules_handle:
        loaded_rules = json.load(rules_handle)

    # 用加载的规则覆盖默认值
    merged = dict(DEFAULT_RULES)
    merged.update(loaded_rules)
    return merged


def expand_path(path_str):
    """
    展开路径中的 ~ 和环境变量。

    Args:
        path_str: 可能包含 ~ 的路径字符串。

    Returns:
        Path: 展开后的绝对路径。
    """
    return Path(os.path.expanduser(os.path.expandvars(path_str)))


# ──────────────────────────────────────────────
# 文件分类
# ──────────────────────────────────────────────

def classify_file(file_path, rules, now=None):
    """
    根据规则将文件分类为 hot / warm / cold / prune / protected。

    Args:
        file_path: 文件路径。
        rules: 规则配置。
        now: 当前时间（用于测试注入）。

    Returns:
        str: 分类标签（"protected" / "prune" / "hot" / "warm" / "cold"）。
    """
    if now is None:
        now = datetime.now()

    file_name = file_path.name
    file_stem = file_path.stem.lower()

    # 检查保护模式
    for protected_pattern in rules.get("protected_patterns", []):
        if protected_pattern.lower() in file_name.lower() or protected_pattern.lower() in file_stem:
            return "protected"

    # 检查修剪关键词
    prune_config = rules.get("prune", {})
    prune_keywords = prune_config.get("keywords", [])
    for keyword in prune_keywords:
        if keyword.lower() in file_name.lower():
            return "prune"

    # 检查空文件
    try:
        file_size = file_path.stat().st_size
        if file_size == 0 and prune_config.get("empty_file_action") == "delete":
            return "prune"
    except OSError:
        return "prune"

    # 检查文件年龄
    try:
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        age_days = (now - file_mtime).days
    except OSError:
        return "cold"

    hot_days = rules.get("hot_memory", {}).get("days", 30)
    cold_days = rules.get("cold_memory", {}).get("days", 181)

    if age_days <= hot_days:
        return "hot"
    elif age_days < cold_days:
        return "warm"
    else:
        return "cold"


# ──────────────────────────────────────────────
# 操作执行
# ──────────────────────────────────────────────

def compact_file(file_path, rules, dry_run=False):
    """
    压缩过长的温记忆文件，保留前 N 行 + 尾部摘要标记。

    Args:
        file_path: 文件路径。
        rules: 规则配置。
        dry_run: 仅报告不修改。

    Returns:
        dict: 操作结果（action / original_lines / compacted_lines / skipped）。
    """
    warm_config = rules.get("warm_memory", {})
    threshold = warm_config.get("compact_threshold_lines", 200)
    target = warm_config.get("compact_target_lines", 80)

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as read_error:
        return {"action": "compact_error", "error": str(read_error)}

    lines = content.splitlines()
    original_line_count = len(lines)

    if original_line_count <= threshold:
        return {"action": "skip", "reason": f"行数 {original_line_count} <= 阈值 {threshold}"}

    # 保留前 target 行 + 插入压缩标记
    kept_lines = lines[:target]
    kept_lines.append("")
    kept_lines.append(f"<!-- MemTidy: 以下 {original_line_count - target} 行已于 {datetime.now().strftime('%Y-%m-%d')} 压缩归档 -->")
    kept_lines.append(f"<!-- 原始行数: {original_line_count}, 压缩后: {target + 3} -->")

    if not dry_run:
        file_path.write_text("\n".join(kept_lines), encoding="utf-8")

    return {
        "action": "compacted",
        "original_lines": original_line_count,
        "compacted_lines": len(kept_lines),
        "dry_run": dry_run,
    }


def archive_file(file_path, archive_dir, dry_run=False):
    """
    将冷记忆文件移至归档目录。

    Args:
        file_path: 文件路径。
        archive_dir: 归档目录路径。
        dry_run: 仅报告不移动。

    Returns:
        dict: 操作结果（action / destination）。
    """
    archive_path = expand_path(archive_dir)
    destination = archive_path / file_path.name

    # 避免覆盖同名文件
    if destination.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = archive_path / f"{stem}_{timestamp}{suffix}"

    if not dry_run:
        archive_path.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(destination))

    return {"action": "archived", "destination": str(destination), "dry_run": dry_run}


def prune_file(file_path, dry_run=False):
    """
    删除匹配修剪规则的文件。

    Args:
        file_path: 文件路径。
        dry_run: 仅报告不删除。

    Returns:
        dict: 操作结果（action / dry_run）。
    """
    if not dry_run:
        file_path.unlink(missing_ok=True)

    return {"action": "pruned", "dry_run": dry_run}


# ──────────────────────────────────────────────
# 备份
# ──────────────────────────────────────────────

def create_backup(memory_dirs, backup_dir, max_backups=7):
    """
    备份当前所有记忆目录到指定位置。

    Args:
        memory_dirs: 要备份的记忆目录列表。
        backup_dir: 备份目标目录。
        max_backups: 最多保留的备份数量。

    Returns:
        dict: 备份结果（backup_path / file_count / total_bytes）。
    """
    backup_base = expand_path(backup_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_base / f"memtidy-backup-{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    file_count = 0
    total_bytes = 0

    for memory_dir in memory_dirs:
        source_dir = expand_path(memory_dir)
        if not source_dir.exists():
            continue

        for md_file in source_dir.rglob("*.md"):
            relative_path = md_file.relative_to(source_dir)
            dest_file = backup_path / source_dir.name / relative_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(md_file), str(dest_file))
            file_count += 1
            total_bytes += md_file.stat().st_size

    # 清理旧备份
    existing_backups = sorted(backup_base.glob("memtidy-backup-*"), key=lambda p: p.name, reverse=True)
    for old_backup in existing_backups[max_backups:]:
        shutil.rmtree(str(old_backup), ignore_errors=True)

    return {"backup_path": str(backup_path), "file_count": file_count, "total_bytes": total_bytes}


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_memtidy(memory_dirs, rules, dry_run=False, task_id=None):
    """
    执行 MemTidy 记忆整理的主流程。

    Args:
        memory_dirs: 记忆目录路径列表。
        rules: 规则配置字典。
        dry_run: 仅报告不修改。
        task_id: 任务 ID（用于 cron 集成）。

    Returns:
        dict: 整理结果摘要。
    """
    now = datetime.now()
    stats = {
        "timestamp": now.isoformat(),
        "task_id": task_id,
        "dry_run": dry_run,
        "scanned": 0,
        "protected": 0,
        "hot": 0,
        "warm_skipped": 0,
        "warm_compacted": 0,
        "cold_archived": 0,
        "pruned": 0,
        "errors": 0,
        "actions": [],
    }

    # 备份（非 dry-run）
    backup_config = rules.get("backup", {})
    if backup_config.get("enabled", True) and not dry_run:
        backup_dir = backup_config.get("dir", "~/.openclaw/ops/memtidy-backups/")
        max_backups = backup_config.get("max_backups", 7)
        backup_result = create_backup(memory_dirs, backup_dir, max_backups)
        stats["backup"] = backup_result
        print(f"📦 备份完成: {backup_result['file_count']} 文件 → {backup_result['backup_path']}")

    # 扫描并处理
    for memory_dir_str in memory_dirs:
        memory_dir = expand_path(memory_dir_str)
        if not memory_dir.exists():
            # 静默跳过不存在的目录（部分节点可能未启用 memory 功能）
            continue

        md_files = list(memory_dir.rglob("*.md"))
        stats["scanned"] += len(md_files)

        for md_file in md_files:
            category = classify_file(md_file, rules, now=now)
            relative_name = str(md_file.relative_to(memory_dir))

            if category == "protected":
                stats["protected"] += 1
                continue

            if category == "hot":
                stats["hot"] += 1
                continue

            if category == "prune":
                result = prune_file(md_file, dry_run=dry_run)
                stats["pruned"] += 1
                action_record = {"file": relative_name, "category": "prune", "result": result}
                stats["actions"].append(action_record)
                prefix = "[DRY-RUN] " if dry_run else ""
                print(f"  🗑️ {prefix}修剪: {relative_name}")
                continue

            if category == "warm":
                result = compact_file(md_file, rules, dry_run=dry_run)
                if result.get("action") == "compacted":
                    stats["warm_compacted"] += 1
                    action_record = {"file": relative_name, "category": "warm_compact", "result": result}
                    stats["actions"].append(action_record)
                    prefix = "[DRY-RUN] " if dry_run else ""
                    print(f"  📝 {prefix}压缩: {relative_name} ({result['original_lines']}→{result['compacted_lines']}行)")
                elif result.get("action") == "compact_error":
                    stats["errors"] += 1
                else:
                    stats["warm_skipped"] += 1
                continue

            if category == "cold":
                archive_dir = rules.get("cold_memory", {}).get("archive_dir", "~/.openclaw/memory-archive/")
                result = archive_file(md_file, archive_dir, dry_run=dry_run)
                stats["cold_archived"] += 1
                action_record = {"file": relative_name, "category": "cold_archive", "result": result}
                stats["actions"].append(action_record)
                prefix = "[DRY-RUN] " if dry_run else ""
                print(f"  📁 {prefix}归档: {relative_name} → {result['destination']}")

    # 输出报告
    report_config = rules.get("report", {})
    report_dir = report_config.get("output_dir", "~/.openclaw/ops/memtidy-reports/")

    if not dry_run:
        report_path = expand_path(report_dir)
        report_path.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        json_path = report_path / f"memtidy-{timestamp}.json"
        json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        md_path = report_path / f"memtidy-{timestamp}.md"
        md_path.write_text(build_markdown_report(stats), encoding="utf-8")

    # 打印摘要
    print_summary(stats)
    return stats


def build_markdown_report(stats):
    """
    构建 Markdown 格式的 MemTidy 报告。

    Args:
        stats: 整理结果统计。

    Returns:
        str: Markdown 格式报告。
    """
    lines = [
        "# 🧹 MemTidy 整理报告",
        "",
        f"> 📅 {stats['timestamp']}",
        "",
        "## 概览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 扫描文件数 | {stats['scanned']} |",
        f"| 🛡️ 受保护 | {stats['protected']} |",
        f"| 🔥 热记忆（保持） | {stats['hot']} |",
        f"| 📝 温记忆（已压缩） | {stats['warm_compacted']} |",
        f"| 📁 冷记忆（已归档） | {stats['cold_archived']} |",
        f"| 🗑️ 已修剪 | {stats['pruned']} |",
        f"| ❌ 错误 | {stats['errors']} |",
        "",
    ]

    if stats.get("actions"):
        lines.append("## 操作明细")
        lines.append("")
        for action in stats["actions"]:
            result = action.get("result", {})
            lines.append(f"- **{action['category']}** `{action['file']}` → {result.get('action', 'unknown')}")
        lines.append("")

    return "\n".join(lines)


def print_summary(stats):
    """打印整理摘要到 stdout。"""
    mode = "[DRY-RUN] " if stats.get("dry_run") else ""
    print(f"\n{'='*50}")
    print(f"🧹 {mode}MemTidy 整理完成")
    print(f"{'='*50}")
    print(f"  扫描: {stats['scanned']} 文件")
    print(f"  保护: {stats['protected']} | 热: {stats['hot']}")
    print(f"  压缩: {stats['warm_compacted']} | 归档: {stats['cold_archived']} | 修剪: {stats['pruned']}")
    if stats['errors'] > 0:
        print(f"  ❌ 错误: {stats['errors']}")
    total_actions = stats['warm_compacted'] + stats['cold_archived'] + stats['pruned']
    print(f"  总操作: {total_actions}")


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """
    构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器。
    """
    parser = argparse.ArgumentParser(
        description="MemTidy — 记忆文件自动整理工具（热/温/冷三层管理 + 修剪 + 归档）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --rules-file config/memtidy_rules.json --dry-run
  %(prog)s --memory-dirs /root/.openclaw/memory/ --rules-file config/memtidy_rules.json
  %(prog)s --memory-dirs /dir1 /dir2 --dry-run
        """,
    )
    parser.add_argument("--memory-dirs", nargs="+", default=None, help="要扫描的记忆目录列表")
    parser.add_argument("--rules-file", default=None, help="规则配置 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只报告不修改文件")
    parser.add_argument("--task-id", default=None, help="当前任务 ID（用于 cron 集成）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    # 加载规则
    rules = load_rules(args.rules_file)

    # 确定记忆目录
    memory_dirs = args.memory_dirs
    if not memory_dirs:
        memory_dirs = rules.get("scan_directories", ["~/.openclaw/memory/"])

    result = run_memtidy(
        memory_dirs=memory_dirs,
        rules=rules,
        dry_run=args.dry_run,
        task_id=args.task_id,
    )

    if result.get("errors", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

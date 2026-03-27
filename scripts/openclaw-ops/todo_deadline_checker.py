#!/usr/bin/env python3
"""todo_deadline_checker.py — TODO 截止时间解析 + 超期自动升级

解析 TODO.md 中带截止时间的任务行，检测超期任务并：
1. 标记为超期（在原行追加 🔴超期 标签）
2. 将超期高风险任务升级为紧急

截止时间格式支持：
- [截止:2026-04-15]
- [deadline:2026-04-15]
- [due:2026-04-15]

用法:
    python todo_deadline_checker.py --todo-file ~/openclaw-hardflow-backup-20260302/todo.md
    python todo_deadline_checker.py --todo-file ~/todo.md --dry-run
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 支持多种截止时间格式
DEADLINE_PATTERN = re.compile(
    r"\[(?:截止|deadline|due)\s*[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})\]",
    re.IGNORECASE | re.UNICODE,
)

# 未完成的任务行
UNCHECKED_PATTERN = re.compile(r"^(\s*-\s*\[\s*[ /]\s*\])")


def parse_deadline(text: str) -> datetime | None:
    """从文本中提取截止日期。

    Args:
        text: 包含截止日期标记的文本行。

    Returns:
        datetime | None: 解析出的截止日期，无匹配返回 None。
    """
    match = DEADLINE_PATTERN.search(text)
    if not match:
        return None
    date_str = match.group(1).replace("/", "-")
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def check_deadlines(todo_path: Path, dry_run: bool = False) -> dict:
    """检查 TODO 文件中的截止时间，标记超期任务。

    Args:
        todo_path: TODO.md 文件路径。
        dry_run: 仅输出不修改文件。

    Returns:
        dict: 检查结果摘要。
    """
    if not todo_path.exists():
        return {"error": f"文件不存在: {todo_path}"}

    content = todo_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    now = datetime.now(tz=timezone.utc)
    overdue_count = 0
    upcoming_count = 0
    modified_lines: list[str] = []

    for line in lines:
        deadline = parse_deadline(line)
        is_unchecked = bool(UNCHECKED_PATTERN.match(line))

        if deadline and is_unchecked:
            days_until = (deadline - now).days
            if days_until < 0 and "🔴超期" not in line:
                # 超期：追加标记
                line = f"{line.rstrip()} 🔴超期{abs(days_until)}天"
                overdue_count += 1
            elif 0 <= days_until <= 3 and "⚠️即将到期" not in line:
                # 即将到期（3天内）
                line = f"{line.rstrip()} ⚠️即将到期"
                upcoming_count += 1
        modified_lines.append(line)

    result = {
        "total_lines": len(lines),
        "overdue_count": overdue_count,
        "upcoming_count": upcoming_count,
        "modified": overdue_count > 0 or upcoming_count > 0,
    }

    if not dry_run and result["modified"]:
        todo_path.write_text("\n".join(modified_lines), encoding="utf-8")
        result["written"] = True

    return result


def main() -> None:
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(
        description="TODO 截止时间检测 + 超期自动标记"
    )
    parser.add_argument("--todo-file", required=True, help="TODO.md 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅输出不修改文件")
    parser.add_argument("--task-id", default="", help="任务 ID")
    args = parser.parse_args()

    todo_path = Path(args.todo_file).expanduser().resolve()
    result = check_deadlines(todo_path, dry_run=args.dry_run)

    if result.get("error"):
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)

    if result["overdue_count"] == 0 and result["upcoming_count"] == 0:
        print("NO_REPLY")
        return

    print(f"📋 截止时间检查完成：")
    if result["overdue_count"]:
        print(f"   🔴 超期任务：{result['overdue_count']} 项")
    if result["upcoming_count"]:
        print(f"   ⚠️ 即将到期：{result['upcoming_count']} 项")
    if result.get("written"):
        print(f"   ✅ 已更新: {todo_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
项目记忆注入器。
会话启动时按 project_key 注入记忆摘要到上下文。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


def setup_logging() -> logging.Logger:
    log_dir = Path(".workflow/logs/project_memory_injector")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("project_memory_injector")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


DATA_DIR = Path(".workflow/project-memory")


def read_file(path: Path, max_lines: int | None = None) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    if max_lines:
        lines = content.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n... (截断，共 {len(lines)} 行)"
    return content


def read_decisions_summary(path: Path, max_entries: int = 5) -> str:
    content = read_file(path)
    if not content:
        return ""

    # 简单按 ## 分割，取最近的几条
    sections = content.split("\n## ")
    if len(sections) <= max_entries + 1:
        return content

    return sections[0] + "\n## " + "\n## ".join(sections[-max_entries:])


def inject(project_key: str, level: str = "summary") -> tuple[str, dict]:
    project_dir = DATA_DIR / project_key

    if not project_dir.exists():
        return (
            f"⚠️ 项目 [{project_key}] 尚未建立记忆模块。\n",
            {"status": "project_not_found", "project_key": project_key},
        )

    profile = read_file(project_dir / "PROJECT_PROFILE.md", max_lines=100 if level == "full" else 30)
    rules = read_file(project_dir / "DELIVERY_RULES.md", max_lines=50 if level == "full" else 20)
    decisions = read_decisions_summary(project_dir / "DECISIONS.md", max_entries=10 if level == "full" else 5)

    injected_tokens = len(profile) + len(rules) + len(decisions)

    markdown = f"""# 项目上下文

## 基本信息
- 项目：{project_key}

"""

    if profile:
        markdown += f"## 项目画像\n\n{profile}\n\n"
    if rules:
        markdown += f"## 交付规则\n\n{rules}\n\n"
    if decisions:
        markdown += f"## 关键决策\n\n{decisions}\n\n"

    meta = {
        "status": "success",
        "project_key": project_key,
        "inject_level": level,
        "injected_files": [],
        "injected_tokens": injected_tokens,
    }

    if profile:
        meta["injected_files"].append("PROJECT_PROFILE.md")
    if rules:
        meta["injected_files"].append("DELIVERY_RULES.md")
    if decisions:
        meta["injected_files"].append("DECISIONS.md")

    return markdown, meta


def list_projects() -> list[str]:
    if not DATA_DIR.exists():
        return []
    return sorted([d.name for d in DATA_DIR.iterdir() if d.is_dir()])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="项目记忆注入器")
    parser.add_argument("--project-key", help="项目标识")
    parser.add_argument("--session-id", help="会话标识")
    parser.add_argument("--inject-level", choices=["full", "summary", "minimal"], default="summary")
    parser.add_argument("--output-format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--list", action="store_true", help="列出所有项目")
    args = parser.parse_args(argv)

    logger = setup_logging()

    if args.list:
        projects = list_projects()
        print(json.dumps({"projects": projects}, ensure_ascii=False, indent=2))
        return 0

    if not args.project_key:
        print(json.dumps({"error": "missing_project_key"}, ensure_ascii=False))
        return 1

    markdown, meta = inject(args.project_key, args.inject_level)
    meta["session_id"] = args.session_id
    meta["timestamp"] = datetime.now(timezone.utc).isoformat()

    logger.info("注入 %s level=%s files=%s", args.project_key, args.inject_level, meta["injected_files"])

    if args.output_format == "json":
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

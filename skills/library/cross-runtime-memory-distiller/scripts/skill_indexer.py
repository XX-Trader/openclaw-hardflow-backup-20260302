#!/usr/bin/env python3
"""技能索引器：扫描所有技能目录，生成统一索引。

扫描平台：
- Windows: ~/.agents/skills/, ~/.claude/skills/, ~/.codex/skills/
- Linux/WSL: ~/.openclaw/skills/, ~/.hermes/skills/
- 工作区: skills/library/, .claude/skills/, .codex/skills/

输出：skill-index.json，包含每个技能的名称、描述、来源目录、标签等。

CLI 用法:
  python skill_indexer.py                           # 扫描全部并输出到 stdout
  python skill_indexer.py --output skill-index.json  # 保存到文件
  python skill_indexer.py --workspace /path/to/repo  # 指定工作区
  python skill_indexer.py --diff                     # 只输出与上次索引的差异
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("skill_indexer")

# ── 平台搜索路径 ─────────────────────────────────────────────────────

# Windows 用户目录
_WINDOWS_ROOTS = [
    ("agents", ".agents/skills"),
    ("claude", ".claude/skills"),
    ("codex", ".codex/skills"),
    ("openclaw", ".openclaw/skills"),
]

# Linux/WSL 用户目录（含 Hermes 运行时）
_LINUX_ROOTS = [
    ("openclaw", ".openclaw/skills/library"),
    ("openclaw-lib", ".openclaw/skills"),
    ("hermes", ".hermes/skills"),
    ("hermes-optional", ".hermes/hermes-agent/optional-skills"),
]

# Hermes 运行时技能子目录（optional-skills 下按类别分）
_HERMES_OPTIONAL_CATEGORIES = [
    "research", "devops", "creative", "data-science",
    "productivity", "software-development", "mlops",
]

# 工作区内技能目录
_WORKSPACE_DIRS = [
    ("workspace-lib", "skills/library"),
    ("workspace-claude", ".claude/skills"),
    ("workspace-codex", ".codex/skills"),
]


# ── Frontmatter 解析 ────────────────────────────────────────────────


def parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 SKILL.md 的 YAML frontmatter（轻量实现，不依赖 yaml 库）。"""
    m = re.match(r"^---\s*\n(.*?\n)---\s*\n", text, re.DOTALL)
    if not m:
        return {}

    raw = m.group(1)
    meta: dict[str, Any] = {}
    current_key = ""
    current_value = ""
    in_block = False

    for line in raw.splitlines():
        # 多行块值：以空格/制表符开头
        if in_block and (line.startswith("  ") or line.startswith("\t")):
            current_value += " " + line.strip()
            continue

        # 上一个 key 结束，保存
        if in_block and current_key:
            meta[current_key] = _clean_value(current_value)
            in_block = False

        # 新 key
        kv_match = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if kv_match:
            current_key = kv_match.group(1).lower().replace("-", "_")
            current_value = kv_match.group(2).strip()
            if current_value:
                in_block = True
            else:
                in_block = True  # value 可能在下一行
        else:
            in_block = False

    if in_block and current_key:
        meta[current_key] = _clean_value(current_value)

    return meta


def _clean_value(val: str) -> str:
    """清理 YAML 值：去引号、去 > 前缀。"""
    s = val.strip()
    if s.startswith(">"):
        s = s[1:].strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s


# ── 扫描逻辑 ────────────────────────────────────────────────────────


def _scan_dir(root: Path, source: str, skills: dict[str, dict], depth: int = 1) -> int:
    """扫描技能根目录，结果写入 skills。返回新增数量。

    Args:
        root: 技能根目录
        source: 来源标识
        skills: 结果字典
        depth: 递归深度（1=只扫直接子目录，2=扫到孙目录用于 optional-skills 类别结构）
    """
    if not root.is_dir():
        return 0

    added = 0
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        # 名字以 . 或 _ 开头的跳过（node_modules, .git, __pycache__ 等）
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue

        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            added += _add_skill(entry, skill_md, source, skills)
        elif depth > 1:
            # 递归扫子目录（如 optional-skills/research/duckduckgo-search/）
            added += _scan_dir(entry, source, skills, depth - 1)

    return added


def _add_skill(skill_path: Path, skill_md: Path, source: str, skills: dict[str, dict]) -> int:
    """添加单个技能到索引。"""
    skill_name = skill_path.name
    if skill_name in skills:
        return 0

    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    meta = parse_frontmatter(text)
    stat = skill_md.stat()

    skills[skill_name] = {
        "name": meta.get("name", skill_name),
        "display_name": meta.get("displayname") or meta.get("display_name", ""),
        "description": meta.get("description", ""),
        "description_zh": meta.get("description_zh", ""),
        "tags": meta.get("tags", ""),
        "tags_cn": meta.get("tags_cn", ""),
        "version": meta.get("version", ""),
        "source": source,
        "path": str(skill_path),
        "skill_md": str(skill_md),
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return 1


def build_index(workspace: str | Path | None = None) -> dict[str, Any]:
    """构建技能索引。

    Args:
        workspace: 工作区路径（可选）

    Returns:
        {
            "generated_at": str,
            "total": int,
            "by_source": {source: count},
            "skills": {name: {name, description, source, path, ...}}
        }
    """
    skills: dict[str, dict] = {}
    home = Path.home()
    import platform

    is_windows = platform.system() == "Windows" or os.name == "nt"

    # 1. 平台用户目录
    roots = _WINDOWS_ROOTS if is_windows else _LINUX_ROOTS
    for source, rel in roots:
        root = home / rel
        # Hermes skills/ 和 optional-skills 都是两级目录结构（category/skill/SKILL.md）
        depth = 2 if "hermes" in source else 1
        count = _scan_dir(root, source, skills, depth=depth)
        if count:
            logger.info("scanned:source=%s path=%s found=%d", source, root, count)

    # 2. 工作区目录
    if workspace:
        ws = Path(workspace)
        for source, rel in _WORKSPACE_DIRS:
            root = ws / rel
            count = _scan_dir(root, source, skills)
            if count:
                logger.info("scanned:source=%s path=%s found=%d", source, root, count)

    # 按来源统计
    by_source: dict[str, int] = {}
    for s in skills.values():
        src = s.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(skills),
        "by_source": by_source,
        "skills": skills,
    }


def diff_index(old_index: dict, new_index: dict) -> dict[str, Any]:
    """对比两次索引，返回新增/删除/变更。

    Returns:
        {"added": [...], "removed": [...], "changed": [...]}
    """
    old_skills = old_index.get("skills", {})
    new_skills = new_index.get("skills", {})

    old_names = set(old_skills)
    new_names = set(new_skills)

    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    changed = sorted(
        name for name in old_names & new_names
        if old_skills[name].get("updated_at") != new_skills[name].get("updated_at")
    )

    return {
        "added": [{"name": n, **new_skills[n]} for n in added],
        "removed": [{"name": n, **old_skills[n]} for n in removed],
        "changed": [{"name": n, **new_skills[n]} for n in changed],
    }


def search_skills(index: dict, query: str, limit: int = 20) -> list[dict]:
    """在索引中搜索技能。

    匹配字段：name, display_name, description, tags, tags_cn
    """
    q = query.lower().strip()
    if not q:
        return []

    results: list[tuple[float, dict]] = []
    for skill in index.get("skills", {}).values():
        score = 0.0
        # 名称精确匹配
        if q == skill.get("name", "").lower():
            score = 1.0
        # 名称包含
        elif q in skill.get("name", "").lower():
            score = 0.8
        # display_name 包含
        elif q in skill.get("display_name", "").lower():
            score = 0.7
        # 标签包含
        elif q in skill.get("tags", "").lower() or q in skill.get("tags_cn", "").lower():
            score = 0.6
        # 描述包含
        elif q in skill.get("description", "").lower() or q in skill.get("description_zh", "").lower():
            score = 0.4
        else:
            continue

        results.append((score, skill))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


# ── CLI ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="技能索引器：扫描并索引所有技能")
    parser.add_argument("--workspace", default="", help="工作区路径")
    parser.add_argument("--output", "-o", default="", help="输出文件路径（默认 stdout）")
    parser.add_argument("--diff", action="store_true", help="与上次索引对比差异")
    parser.add_argument("--search", default="", help="搜索关键词")
    parser.add_argument("--log-level", default="WARNING")
    return parser.parse_args(argv)


def _run_cli(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="技能索引器：扫描并索引所有技能")
    parser.add_argument("--workspace", default="", help="工作区路径")
    parser.add_argument("--output", "-o", default="", help="输出文件路径（默认 stdout）")
    parser.add_argument("--diff", action="store_true", help="与上次索引对比差异")
    parser.add_argument("--search", default="", help="搜索关键词")
    parser.add_argument("--log-level", default="WARNING")

    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))

    workspace = args.workspace.strip() or None
    index = build_index(workspace)

    # 搜索模式
    if args.search:
        results = search_skills(index, args.search)
        for r in results:
            print(f"  {r['name']:40s}  [{r.get('source', '?')}]  {r.get('description', '')[:60]}")
        return 0

    # 差异模式
    if args.diff and args.output:
        output_path = Path(args.output)
        old_index: dict = {}
        if output_path.exists():
            try:
                old_index = json.loads(output_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        delta = diff_index(old_index, index)
        print(json.dumps(delta, ensure_ascii=False, indent=2))
        return 0

    # 输出
    output = json.dumps(index, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"索引已保存: {args.output} ({index['total']} 个技能)")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(_run_cli())

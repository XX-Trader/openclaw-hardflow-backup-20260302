#!/usr/bin/env python3
"""memory_to_skill_extractor.py — 记忆→Skill/Hook 自动封装（draft 模式）

扫描 MCP Memory 中的最佳实践和模式记忆，自动提取高频可复用的
操作模式，封装为 draft Skill 或 Hook 模板。所有产出均为 draft 状态，
必须由人工审核激活后才会生效。

用法:
    python memory_to_skill_extractor.py --memory-dir ~/.openclaw/memory/ --output-dir ~/.openclaw/ops/skill-drafts/
    python memory_to_skill_extractor.py --memory-dir ~/.openclaw/memory/ --dry-run
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
# 可提取模式的关键词特征
# ──────────────────────────────────────────────

EXTRACTABLE_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "recurring_fix",
        "label": "重复修复模式",
        "keywords": ["fix", "修复", "repair", "workaround", "hotfix", "patch"],
        "min_occurrences": 2,
        "target": "hook",
    },
    {
        "id": "best_practice",
        "label": "最佳实践",
        "keywords": ["best practice", "最佳实践", "推荐", "优先使用", "should always"],
        "min_occurrences": 1,
        "target": "skill",
    },
    {
        "id": "automation_pattern",
        "label": "自动化模式",
        "keywords": ["自动", "automation", "cron", "定时", "scheduled", "batch"],
        "min_occurrences": 2,
        "target": "skill",
    },
    {
        "id": "error_handling",
        "label": "错误处理模式",
        "keywords": ["error handling", "异常处理", "fallback", "retry", "降级"],
        "min_occurrences": 2,
        "target": "hook",
    },
]


def scan_memory_files(memory_dir: Path) -> list[dict[str, Any]]:
    """扫描记忆目录中的 JSON 文件，提取观察记录。

    Args:
        memory_dir: 记忆文件目录。

    Returns:
        list[dict]: 提取的观察记录列表。
    """
    observations: list[dict[str, Any]] = []
    if not memory_dir.exists():
        return observations
    for json_file in memory_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            # 单条记忆
            observations.append({
                "source": str(json_file),
                "content": json.dumps(data, ensure_ascii=False)[:2000],
                "entities": data.get("entities", []),
                "observations": data.get("observations", []),
            })
        elif isinstance(data, list):
            for item in data[:100]:
                if isinstance(item, dict):
                    observations.append({
                        "source": str(json_file),
                        "content": json.dumps(item, ensure_ascii=False)[:2000],
                        "entities": item.get("entities", []),
                        "observations": item.get("observations", []),
                    })
    return observations


def match_patterns(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将观察记录与可提取模式进行匹配。

    Args:
        observations: 扫描得到的观察记录。

    Returns:
        list[dict]: 匹配到的模式列表，含匹配次数和样本。
    """
    results: list[dict[str, Any]] = []
    for pattern in EXTRACTABLE_PATTERNS:
        matched_samples: list[str] = []
        for obs in observations:
            content_lower = obs["content"].lower()
            if any(kw.lower() in content_lower for kw in pattern["keywords"]):
                matched_samples.append(obs["content"][:200])
        if len(matched_samples) >= pattern["min_occurrences"]:
            results.append({
                "pattern_id": pattern["id"],
                "label": pattern["label"],
                "target": pattern["target"],
                "match_count": len(matched_samples),
                "samples": matched_samples[:5],
            })
    return results


def generate_draft(pattern_match: dict[str, Any], output_dir: Path) -> Path | None:
    """为匹配到的模式生成 draft 文件。

    Args:
        pattern_match: 模式匹配结果。
        output_dir: 输出目录。

    Returns:
        Path | None: 生成的 draft 文件路径，失败返回 None。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern_id = pattern_match["pattern_id"]
    target = pattern_match["target"]
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    filename = f"draft-{target}-{pattern_id}-{ts}.md"
    draft_path = output_dir / filename
    samples_text = "\n".join(
        f"  - {s[:150]}" for s in pattern_match.get("samples", [])[:3]
    )
    content = f"""# [DRAFT] {pattern_match['label']}

> ⚠️ 本文件由 memory_to_skill_extractor 自动提取，必须人工审核后激活。
> 生成时间：{datetime.now(tz=timezone.utc).isoformat()}
> 模式 ID：{pattern_id}
> 目标类型：{target}（skill / hook）
> 匹配次数：{pattern_match['match_count']}

## 模式描述

从历史记忆中发现 {pattern_match['match_count']} 次 「{pattern_match['label']}」 重复模式。

## 样本摘要

{samples_text}

## 建议封装

- [ ] 确认模式是否具有通用性
- [ ] 编写正式 {target.upper()} 定义
- [ ] 添加测试用例
- [ ] 审核通过后激活

## 状态: DRAFT（待审核）
"""
    try:
        draft_path.write_text(content, encoding="utf-8")
        return draft_path
    except OSError:
        return None


def main() -> None:
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(
        description="从 MCP Memory 中提取可复用模式，生成 draft Skill/Hook 模板"
    )
    parser.add_argument(
        "--memory-dir", required=True,
        help="记忆文件目录（如 ~/.openclaw/memory/）"
    )
    parser.add_argument(
        "--output-dir", default="",
        help="draft 输出目录（默认 ~/.openclaw/ops/skill-drafts/）"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅输出不写文件")
    parser.add_argument("--task-id", default="", help="任务 ID")
    args = parser.parse_args()

    memory_dir = Path(args.memory_dir).expanduser().resolve()
    output_dir = Path(args.output_dir or "~/.openclaw/ops/skill-drafts/").expanduser().resolve()

    observations = scan_memory_files(memory_dir)
    if not observations:
        print("NO_REPLY")
        return

    matches = match_patterns(observations)
    if not matches:
        print("NO_REPLY")
        return

    if args.dry_run:
        print(f"发现 {len(matches)} 个可封装模式：")
        for m in matches:
            print(f"  - [{m['target']}] {m['label']}（匹配 {m['match_count']} 次）")
        return

    drafts: list[str] = []
    for m in matches:
        path = generate_draft(m, output_dir)
        if path:
            drafts.append(str(path))

    if drafts:
        print(f"✅ 生成 {len(drafts)} 个 draft 文件：")
        for d in drafts:
            print(f"  - {d}")
    else:
        print("NO_REPLY")


if __name__ == "__main__":
    main()

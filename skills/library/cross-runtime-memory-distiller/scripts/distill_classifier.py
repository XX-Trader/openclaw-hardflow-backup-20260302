#!/usr/bin/env python3
"""蒸馏分类器：对高分候选做结构化摘要与分类。

当宿主内 Parser Agent 不可用时，使用规则降级分类。
当可用时，把候选封装成 ParserCandidatePacket 交给宿主适配器。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

logger = logging.getLogger("distill_classifier")

# 结构化摘要模板
SUMMARY_TEMPLATE = """### 目标 (Goal)
{goal}

### 约束与偏好 (Constraints & Preferences)
{constraints}

### 进展 (Progress)
{progress}

### 关键决策 (Key Decisions)
{decisions}

### 相关文件 (Relevant Files)
{files}

### 下一步 (Next Steps)
{next_steps}

### 关键上下文 (Critical Context)
{critical}
"""


def classify_with_rules(window_text: str, window_id: str = "", source: str = "") -> dict[str, Any]:
    """纯规则分类 + 结构化摘要生成。

    这是当宿主内 Parser Agent 不可用时的降级方案。

    Args:
        window_text: 候选窗口正文
        window_id: 窗口 ID
        source: 数据源

    Returns:
        DistillArtifact 格式的字典
    """
    # 导入降级分类
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from distill_cleaner import fallback_classify

    classification = fallback_classify(window_text)

    # 生成简单摘要
    lines = window_text.strip().splitlines()
    title = lines[0][:80] if lines else "未命名"
    if len(title) > 60:
        title = title[:57] + "..."

    # 从窗口文本中提取各部分
    goal = _extract_section(window_text, ["目标", "goal", "目的"])
    constraints = _extract_section(window_text, ["约束", "constraint", "偏好", "限制"])
    progress = _extract_section(window_text, ["进展", "progress", "进度", "完成"])
    decisions = _extract_section(window_text, ["决策", "decision", "决定", "选择"])
    files = _extract_files(window_text)
    next_steps = _extract_section(window_text, ["下一步", "next step", "待办"])
    critical = _extract_section(window_text, ["关键上下文", "critical", "重要"])

    # 如果没提取到，用第一段做 goal
    if not goal:
        goal = title

    summary = SUMMARY_TEMPLATE.format(
        goal=goal or "（未明确）",
        constraints=constraints or "（未明确）",
        progress=progress or "（未明确）",
        decisions=decisions or "（未明确）",
        files=files or "（未涉及）",
        next_steps=next_steps or "（未明确）",
        critical=critical or "（无特殊上下文）",
    )

    return {
        "artifact_id": "",
        "kind": classification["kind"],
        "title": title,
        "summary": summary,
        "rationale": f"规则降级分类，来源 {source}，置信度 {classification['confidence']}",
        "evidence_refs": [],
        "confidence": classification["confidence"],
        "target_kind": "hot_memory" if classification["kind"] in ("user", "memory") else "knowledge",
        "trace_id": "",
        "task_id": "",
        "run_id": "",
        "requires_human_review": classification["requires_human_review"],
    }


def _extract_section(text: str, keywords: list[str]) -> str:
    """从文本中提取包含关键词的段落。"""
    lines = text.splitlines()
    result: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip().lower()
        if any(kw in stripped for kw in keywords):
            capturing = True
            # 如果这行本身有内容，加入
            if len(line.strip()) > len(keywords[0]) + 5:
                result.append(line.strip())
            continue
        if capturing:
            if not line.strip() or line.strip().startswith("#") or line.strip().startswith("###"):
                break
            result.append(line.strip())
    return "\n".join(result).strip()


def _extract_files(text: str) -> str:
    """从文本中提取文件路径。"""
    import re
    paths: list[str] = []
    # Unix 路径
    for m in re.finditer(r"(?:^|[\s(])(/[a-zA-Z0-9_./\-]+(?:\.\w+))", text):
        paths.append(m.group(1))
    # Windows 路径
    for m in re.finditer(r"[A-Z]:\\[a-zA-Z0-9_\\.\-]+", text):
        paths.append(m.group(0))
    # 代码文件引用
    for m in re.finditer(r"[\w/\-]+\.(py|js|ts|tsx|jsx|md|json|yaml|yml|toml)\b", text):
        p = m.group(0)
        if p not in paths:
            paths.append(p)
    return "\n".join(paths[:20]) if paths else ""

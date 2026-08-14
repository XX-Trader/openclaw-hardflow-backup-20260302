#!/usr/bin/env python3
"""技能草稿生成器：从 pattern 类型的蒸馏产物生成或更新 Skill Draft。

策略：
1. 优先匹配已有技能（按名称相似度 + 关键词命中）
2. 匹配到 → 追加 origin.json 记录 + 标记待审核更新
3. 未匹配 → 才新建独立技能草稿

当 pattern 类型产物满足以下条件时触发：
- 置信度 ≥ 0.5
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("skill_draft_generator")

# 已有技能库路径（用于匹配）
_SKILL_LIB_DIRS: list[str] = [
    "skills/library",
    ".claude/skills",
    ".codex/skills",
]

# 补丁追加模板（用于已有技能更新）
APPENDIX_TEMPLATE = """

---

## 蒸馏补充（{generated_at}）

> 以下内容由记忆蒸馏引擎自动从 {trigger_count} 次重复操作中提炼，待人工审核后合入正式内容。

### 适用场景补充

{scenarios}

### 操作步骤补充

{steps}

### 来源证据

- 首次发现: {first_seen}，来源: {first_source}
- 重复次数: {trigger_count}
- 触发模式: {pattern_description}
"""

SKILL_TEMPLATE = """---
name: {name}
description: >
  {description}
status: draft
generated_by: cross-runtime-memory-distiller
generated_at: "{generated_at}"
trigger_count: {trigger_count}
---

# {title}

> 状态：Draft（待人工审核激活）
> 来源：由记忆蒸馏引擎自动从 {trigger_count} 次重复操作中提炼

## 适用场景

{scenarios}

## 操作步骤

{steps}

## 验证方法

{verification}

## 注意事项

{notes}

## 来源证据

- 首次发现: {first_seen}，来源: {first_source}
- 重复次数: {trigger_count}
- 触发模式: {pattern_description}
- 详细证据: `{origin_path}`
"""

ORIGIN_TEMPLATE = {
    "skill_name": "",
    "action": "create",
    "matched_existing": None,
    "status": "draft",
    "trigger_count": 0,
    "first_seen": "",
    "last_seen": "",
    "pattern_description": "",
    "evidence_sessions": [],
    "generated_at": "",
    "human_review": {
        "reviewed": False,
        "reviewer": None,
        "decision": None,
        "reviewed_at": None,
    },
}


# ── 已有技能发现（平台感知） ──────────────────────────────────────────

# 各平台技能搜索根目录（相对于用户 home 或固定路径）
_WINDOWS_SKILL_ROOTS: list[str] = [
    ".agents/skills",
    ".claude/skills",
    ".codex/skills",
]
_LINUX_SKILL_ROOTS: list[str] = [
    ".openclaw/skills/library",
    ".openclaw/skills",
    ".hermes/skills",
]


def _get_platform_skill_dirs() -> list[Path]:
    """当前平台目录优先，同时扫描跨运行时共享的技能根目录。"""
    dirs: list[Path] = []
    home = Path.home()
    import platform

    if platform.system() == "Windows" or os.name == "nt":
        ordered_roots = [*_WINDOWS_SKILL_ROOTS, *_LINUX_SKILL_ROOTS]
    else:
        ordered_roots = [*_LINUX_SKILL_ROOTS, *_WINDOWS_SKILL_ROOTS]

    seen: set[str] = set()
    for rel in ordered_roots:
        directory = home / rel
        key = str(directory)
        if directory.is_dir() and key not in seen:
            seen.add(key)
            dirs.append(directory)

    return dirs


def discover_existing_skills(
    workspace: str | Path | None = None,
) -> dict[str, Path]:
    """扫描已有技能，返回 {技能名: SKILL.md 路径}。

    优先从索引文件加载（skill-index.json），不存在则实时扫描。

    搜索策略（按优先级）：
    1. 索引文件（如果存在且不超过 1 小时）
    2. 用户 home 下的跨运行时技能目录（当前平台目录优先）
       - Windows 系：~/.agents/skills/, ~/.claude/skills/, ~/.codex/skills/
       - Linux/WSL 系：~/.openclaw/skills/, ~/.hermes/skills/
    3. 工作区下的 skills/library/, .claude/skills/, .codex/skills/
    """
    # 尝试从索引文件加载
    index_path = _find_index_file(workspace)
    if index_path:
        try:
            return _load_from_index(index_path)
        except (json.JSONDecodeError, OSError):
            pass

    # 实时扫描
    skills: dict[str, Path] = {}

    # 平台用户目录
    for skill_root in _get_platform_skill_dirs():
        _scan_skill_dir(skill_root, skills)

    # 工作区目录
    if workspace:
        ws = Path(workspace)
        for lib_dir in _SKILL_LIB_DIRS:
            skill_root = ws / lib_dir
            if skill_root.is_dir():
                _scan_skill_dir(skill_root, skills)

    return skills


def _find_index_file(workspace: str | Path | None = None) -> Path | None:
    """查找最近的索引文件。"""
    candidates: list[Path] = []

    # 工作区根目录
    if workspace:
        candidates.append(Path(workspace) / "skill-index.json")

    # distill 数据目录
    home = Path.home()
    candidates.append(home / ".openclaw" / "ops" / "distill" / "skill-index.json")

    for p in candidates:
        if p.exists():
            # 不超过 1 小时的索引才用
            import time
            age = time.time() - p.stat().st_mtime
            if age < 3600:
                return p
    return None


def _load_from_index(index_path: Path) -> dict[str, Path]:
    """从索引文件加载技能路径。"""
    data = json.loads(index_path.read_text(encoding="utf-8"))
    result: dict[str, Path] = {}
    for name, info in data.get("skills", {}).items():
        p = Path(info.get("skill_md", info.get("path", ""))) / "SKILL.md"
        # 兼容：skill_md 可能已经是完整路径
        if info.get("skill_md") and Path(info["skill_md"]).exists():
            result[name] = Path(info["skill_md"])
        elif info.get("path") and Path(info["path"]).is_dir():
            result[name] = Path(info["path"]) / "SKILL.md"
    return result


def _scan_skill_dir(skill_root: Path, skills: dict[str, Path]) -> None:
    """扫描单个技能根目录，结果写入 skills 字典（同名不覆盖）。"""
    if not skill_root.is_dir():
        return
    for skill_path in sorted(skill_root.iterdir()):
        if not skill_path.is_dir():
            continue
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists() and skill_path.name not in skills:
            skills[skill_path.name] = skill_md


def _normalize_for_match(name: str) -> str:
    """归一化技能名用于模糊匹配。"""
    s = name.lower().strip()
    s = re.sub(r"[-_\s]+", "-", s)
    s = re.sub(r"[^\w-]", "", s)
    return s


def _extract_keywords(title: str) -> set[str]:
    """从标题中提取关键词。"""
    # 分词：按中文单字 + 英文单词拆分
    tokens: list[str] = []
    for part in re.findall(r"[a-zA-Z]+|[\u4e00-\u9fff]", title.lower()):
        if len(part) >= 2 or re.match(r"[\u4e00-\u9fff]", part):
            tokens.append(part)
    # 英文单词直接加入；中文连续字做 bigram
    keywords: set[str] = set()
    for t in tokens:
        if re.match(r"[a-zA-Z]", t):
            keywords.add(t)
        else:
            keywords.add(t)
    return keywords


def match_existing_skill(
    title: str,
    existing_skills: dict[str, Path],
    threshold: float = 0.3,
) -> tuple[str | None, float]:
    """尝试将蒸馏产物匹配到已有技能。

    匹配策略：
    1. 名称归一化后完全包含 → 直接命中
    2. 关键词交集率 ≥ threshold → 模糊命中

    Returns:
        (matched_skill_name, confidence) 或 (None, 0.0)
    """
    title_norm = _normalize_for_match(title)
    title_keywords = _extract_keywords(title)

    best_name: str | None = None
    best_score = 0.0

    for skill_name, _skill_path in existing_skills.items():
        skill_norm = _normalize_for_match(skill_name)

        # 策略 1: 归一化名称互含
        if title_norm and skill_norm:
            if title_norm in skill_norm or skill_norm in title_norm:
                return skill_name, 0.95

        # 策略 2: 关键词交集率
        skill_keywords = _extract_keywords(skill_name.replace("-", " ").replace("_", " "))
        if not title_keywords or not skill_keywords:
            continue
        intersection = title_keywords & skill_keywords
        union = title_keywords | skill_keywords
        jaccard = len(intersection) / len(union) if union else 0
        if jaccard > best_score:
            best_score = jaccard
            best_name = skill_name

    if best_score >= threshold:
        return best_name, best_score
    return None, 0.0


# ── 核心：生成/更新技能 ────────────────────────────────────────────────


def generate_skill_draft(
    artifacts: Sequence[dict[str, Any]],
    output_dir: str | Path,
    workspace: str | Path | None = None,
) -> list[dict[str, Any]]:
    """从 pattern 产物中生成或更新 Skill Draft。

    Args:
        artifacts: DistillArtifact 列表（只处理 kind=pattern 的）
        output_dir: 技能候选输出目录
        workspace: 工作区路径（用于扫描已有技能）

    Returns:
        生成的 Skill Draft 信息列表
    """
    patterns = [a for a in artifacts if a.get("kind") == "pattern"]
    if not patterns:
        logger.info("no_pattern_artifacts:skip_skill_draft")
        return []

    out = Path(output_dir)
    drafts: list[dict[str, Any]] = []

    # 扫描已有技能
    existing_skills = discover_existing_skills(workspace)
    logger.info("existing_skills_scanned:count=%d workspace=%s", len(existing_skills), workspace)

    for artifact in patterns:
        title = artifact.get("title", "unnamed-pattern")
        name = _title_to_skill_name(title)
        confidence = artifact.get("confidence", 0)

        if confidence < 0.5:
            logger.info("low_confidence_pattern:skip name=%s conf=%.2f", name, confidence)
            continue

        generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        trigger_count = 1
        evidence_refs = artifact.get("evidence_refs", [])
        summary = artifact.get("summary", "")
        steps = _extract_steps(summary)
        scenarios = _extract_scenarios(summary)

        # 尝试匹配已有技能
        matched_name, match_score = match_existing_skill(title, existing_skills)

        if matched_name and matched_name in existing_skills:
            # 匹配到 → 追加到已有技能
            skill_md_path = existing_skills[matched_name]
            action = "update"
            logger.info("matched_existing:name=%s matched=%s score=%.2f",
                        name, matched_name, match_score)

            _append_to_existing_skill(
                skill_md_path=skill_md_path,
                title=title,
                generated_at=generated_at,
                trigger_count=trigger_count,
                scenarios=scenarios,
                steps=steps,
                first_seen=generated_at,
                first_source=", ".join(evidence_refs[:3]) if evidence_refs else "蒸馏引擎",
                pattern_description=artifact.get("rationale", title),
            )

            # origin.json 写到已有技能目录
            _write_origin(
                skill_dir=skill_md_path.parent,
                name=matched_name,
                action="update",
                matched_existing=matched_name,
                trigger_count=trigger_count,
                generated_at=generated_at,
                artifact=artifact,
                title=title,
            )

            drafts.append({
                "skill_name": matched_name,
                "skill_dir": str(skill_md_path.parent),
                "artifact_id": artifact.get("artifact_id", ""),
                "confidence": confidence,
                "action": "update",
                "matched_existing": matched_name,
                "match_score": match_score,
            })
        else:
            # 未匹配 → 新建技能草稿
            action = "create"
            skill_dir = out / name
            skill_dir.mkdir(parents=True, exist_ok=True)

            skill_md = SKILL_TEMPLATE.format(
                name=name,
                description=title[:100],
                generated_at=generated_at,
                trigger_count=trigger_count,
                title=title,
                scenarios=scenarios,
                steps=steps,
                verification="- 人工审核待定",
                notes="- 本草稿由蒸馏引擎自动生成，需人工审核后方可激活",
                first_seen=generated_at,
                first_source=", ".join(evidence_refs[:3]) if evidence_refs else "蒸馏引擎",
                pattern_description=artifact.get("rationale", title),
                origin_path=f"reports/skill-candidates/{name}/origin.json",
            )
            (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

            _write_origin(
                skill_dir=skill_dir,
                name=name,
                action="create",
                matched_existing=None,
                trigger_count=trigger_count,
                generated_at=generated_at,
                artifact=artifact,
                title=title,
            )

            drafts.append({
                "skill_name": name,
                "skill_dir": str(skill_dir),
                "artifact_id": artifact.get("artifact_id", ""),
                "confidence": confidence,
                "action": "create",
                "matched_existing": None,
                "match_score": 0.0,
            })
            logger.info("skill_draft_created:name=%s dir=%s", name, skill_dir)

    return drafts


def _append_to_existing_skill(
    skill_md_path: Path,
    title: str,
    generated_at: str,
    trigger_count: int,
    scenarios: str,
    steps: str,
    first_seen: str,
    first_source: str,
    pattern_description: str,
) -> None:
    """在已有技能的 SKILL.md 末尾追加蒸馏补充段落。"""
    existing = skill_md_path.read_text(encoding="utf-8")
    appendix = APPENDIX_TEMPLATE.format(
        generated_at=generated_at,
        trigger_count=trigger_count,
        scenarios=scenarios,
        steps=steps,
        first_seen=first_seen,
        first_source=first_source,
        pattern_description=pattern_description,
    )
    skill_md_path.write_text(existing + appendix, encoding="utf-8")
    logger.info("appended_to_skill:path=%s", skill_md_path)


def _write_origin(
    skill_dir: Path,
    name: str,
    action: str,
    matched_existing: str | None,
    trigger_count: int,
    generated_at: str,
    artifact: dict[str, Any],
    title: str,
) -> None:
    """写入/更新 origin.json。"""
    origin_path = skill_dir / "origin.json"
    existing_origin: dict[str, Any] = {}
    if origin_path.exists():
        try:
            existing_origin = json.loads(origin_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 合并 evidence_sessions
    sessions = existing_origin.get("evidence_sessions", [])
    sessions.append({
        "source": artifact.get("source", ""),
        "session_id": "",
        "timestamp": generated_at,
        "snippet": title,
    })

    origin = {
        **ORIGIN_TEMPLATE,
        "skill_name": name,
        "action": action,
        "matched_existing": matched_existing,
        "status": "draft" if action == "create" else "update-pending",
        "trigger_count": existing_origin.get("trigger_count", 0) + trigger_count,
        "first_seen": existing_origin.get("first_seen", generated_at),
        "last_seen": generated_at,
        "pattern_description": artifact.get("rationale", title),
        "evidence_sessions": sessions,
        "generated_at": generated_at,
        "human_review": existing_origin.get("human_review", ORIGIN_TEMPLATE["human_review"]),
    }
    origin_path.write_text(
        json.dumps(origin, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _title_to_skill_name(title: str) -> str:
    """把标题转为合法的技能目录名。"""
    name = title.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = name.strip("-")[:64]
    if not name:
        name = f"auto-pattern-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return name


def _extract_steps(summary: str) -> str:
    """从摘要中提取步骤列表。"""
    lines = summary.splitlines()
    steps: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+\.\s+", stripped) or stripped.startswith("- "):
            steps.append(stripped)
    if steps:
        formatted: list[str] = []
        for i, s in enumerate(steps):
            cleaned = s.lstrip("- ")
            num_match = re.match(r"\d+\.\s+", cleaned)
            if num_match:
                cleaned = cleaned[num_match.end():]
            formatted.append(f"{i+1}. {cleaned}")
        return "\n".join(formatted)
    return "1. （待人工补充）"


def _extract_scenarios(summary: str) -> str:
    """从摘要中提取适用场景。"""
    lines = summary.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") and len(stripped) > 5:
            return stripped
    return "- 当遇到类似模式时使用本技能"

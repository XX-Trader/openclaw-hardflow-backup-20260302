#!/usr/bin/env python3
"""蒸馏清洗器：工具输出裁剪、冗余去重、敏感扫描、候选窗口切分与打分。

处理链路：
原始事件 → 清洗 → 切分为窗口 → 规则打分 → 路由（高价值进解析 Agent / 低价值进检索）
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("distill_cleaner")

# ── 清洗参数 ──────────────────────────────────────────────────────────

MAX_WINDOW_CHARS = 4000
MIN_WINDOW_CHARS = 200
HARD_CUT_THRESHOLD = 6000
TOOL_OUTPUT_HEAD = 500
TOOL_OUTPUT_TAIL = 200

# ── 打分配置加载 ──────────────────────────────────────────────────────

_SCORING_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_scoring_policy() -> dict:
    """加载打分策略配置，缺失时使用内置默认值。"""
    config_path = _SCORING_CONFIG_DIR / "scoring_policy.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# 默认打分权重（scoring_policy.json 可覆盖）
_DEFAULT_WEIGHTS = {
    "density": 0.3,
    "decision": 0.25,
    "failure": 0.2,
    "reusability": 0.15,
}

# 默认路由阈值（scoring_policy.json 可覆盖）
_DEFAULT_THRESHOLDS = {
    "high_value": 0.7,
    "index_only": 0.4,
}

# 默认关键词命中上限
_DEFAULT_KEYWORD_HIT_CAP = 3

# ── 打分关键词 ────────────────────────────────────────────────────────

DENSITY_PATTERNS = [
    r"```[\s\S]*?```",
    r"`[^`]+`",
    r"[A-Z_]{2,}=\S+",
    r"/[\w./\-]+",
    r"[A-Z]:\\[\w\\.\-]+",
    r"(?:pip|npm|git|ssh|docker|kubectl)\s+\w+",
]

DECISION_KEYWORDS = ["决定", "选择", "改为", "采用", "切换到", "修复", "升级", "因为", "原因", "权衡",
                     "decided", "chose", "because", "switched", "fixed", "upgraded"]

FAILURE_KEYWORDS = ["error", "失败", "超时", "异常", "回滚", "traceback", "failed", "crash", "OOM", "死锁",
                    "timeout", "rollback"]

STEP_PATTERNS = [r"步骤\s*\d", r"[Ss]tep\s*\d", r"\d+\.\s+\w+", r"首先.*然后.*最后"]

# ── 数据模型 ──────────────────────────────────────────────────────────


@dataclass
class CandidateWindow:
    """候选窗口：经过清洗和切分后的事件片段。"""

    window_id: str
    session_id: str
    source: str
    host: str
    event_ids: list[str]
    text: str
    char_count: int
    turn_count: int
    time_span: list[str]
    score: float = 0.0
    status: str = "pending"  # pending | high_value | index_only | skip

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# ── 清洗函数 ──────────────────────────────────────────────────────────


def clean_tool_outputs(content: str, role: str = "") -> str:
    """裁剪工具输出，保留头部和尾部。"""
    if role != "tool" and "tool_result" not in role:
        return content
    if len(content) <= TOOL_OUTPUT_HEAD + TOOL_OUTPUT_TAIL:
        return content
    return content[:TOOL_OUTPUT_HEAD] + f"\n... [truncated] ...\n" + content[-TOOL_OUTPUT_TAIL:]


def clean_heartbeat_and_templates(content: str) -> str:
    """剔除心跳、模板化噪音。"""
    # 去除纯空白行
    lines = [ln for ln in content.splitlines() if ln.strip()]
    # 去除重复行（连续重复）
    deduped: list[str] = []
    prev = ""
    for ln in lines:
        if ln.strip() == prev:
            continue
        deduped.append(ln)
        prev = ln.strip()
    return "\n".join(deduped)


def clean_event(event: dict[str, Any]) -> dict[str, Any]:
    """清洗单个事件：裁剪工具输出 + 去噪。"""
    content = event.get("content", "")
    role = event.get("role", "")
    content = clean_tool_outputs(content, role)
    content = clean_heartbeat_and_templates(content)
    return {**event, "content": content}


# ── 窗口切分 ──────────────────────────────────────────────────────────


def segment_events_into_windows(
    events: Sequence[dict[str, Any]],
    source: str = "",
    host: str = "",
) -> list[CandidateWindow]:
    """把事件序列切分为候选窗口。

    策略：
    1. 按 session_id 分组
    2. 按 timestamp 排序
    3. 在 session 内按 turn (role 变化) 切分
    4. 合并相邻 turn 直到接近 MAX_WINDOW_CHARS
    5. 如果单 turn 超 HARD_CUT，裁剪

    Args:
        events: 清洗后的归一化事件列表
        source: 数据源名称
        host: 宿主名称

    Returns:
        候选窗口列表
    """
    # 按 session 分组
    sessions: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        sid = ev.get("session_id", "unknown")
        sessions.setdefault(sid, []).append(ev)

    windows: list[CandidateWindow] = []
    for sid, session_events in sessions.items():
        # 按 timestamp 排序
        sorted_events = sorted(session_events, key=lambda e: e.get("timestamp", ""))
        if not sorted_events:
            continue

        # 按 turn 切分（role 变化处）
        turns = _split_by_turns(sorted_events)

        # 合并 turns 成窗口
        win_idx = 0
        current_text_parts: list[str] = []
        current_ids: list[str] = []
        current_turns = 0
        current_start_time = ""
        current_end_time = ""

        for turn in turns:
            turn_text = "\n".join(ev.get("content", "") for ev in turn)
            turn_ids = [ev.get("event_id", "") for ev in turn]
            turn_time = turn[0].get("timestamp", "")
            if not turn_time and len(turn) > 1:
                turn_time = turn[-1].get("timestamp", "")

            combined_len = sum(len(p) for p in current_text_parts) + len(turn_text)

            if combined_len > HARD_CUT_THRESHOLD and current_text_parts:
                # 当前窗口已满，输出
                _flush_window(
                    windows, sid, source, host, win_idx,
                    current_text_parts, current_ids, current_turns,
                    current_start_time, current_end_time,
                )
                win_idx += 1
                current_text_parts = [turn_text[:MAX_WINDOW_CHARS]]
                current_ids = turn_ids
                current_turns = 1
                current_start_time = turn_time
                current_end_time = turn_time
            elif combined_len > MAX_WINDOW_CHARS and current_text_parts:
                # 接近上限，也输出
                _flush_window(
                    windows, sid, source, host, win_idx,
                    current_text_parts, current_ids, current_turns,
                    current_start_time, current_end_time,
                )
                win_idx += 1
                current_text_parts = [turn_text]
                current_ids = list(turn_ids)
                current_turns = 1
                current_start_time = turn_time
                current_end_time = turn_time
            else:
                current_text_parts.append(turn_text)
                current_ids.extend(turn_ids)
                current_turns += 1
                if not current_start_time:
                    current_start_time = turn_time
                current_end_time = turn_time

        # 最后一个窗口
        if current_text_parts:
            _flush_window(
                windows, sid, source, host, win_idx,
                current_text_parts, current_ids, current_turns,
                current_start_time, current_end_time,
            )

    return windows


def _split_by_turns(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 role 变化切分为 turns。"""
    if not events:
        return []
    turns: list[list[dict[str, Any]]] = [[events[0]]]
    for ev in events[1:]:
        if ev.get("role") != turns[-1][-1].get("role"):
            turns.append([ev])
        else:
            turns[-1].append(ev)
    return turns


def _flush_window(
    windows: list[CandidateWindow],
    session_id: str,
    source: str,
    host: str,
    win_idx: int,
    text_parts: list[str],
    event_ids: list[str],
    turn_count: int,
    start_time: str,
    end_time: str,
) -> None:
    """将当前累积的文本刷入一个窗口。"""
    text = "\n\n".join(text_parts)
    char_count = len(text)
    # 短窗口合并到上一个（如果有）
    if char_count < MIN_WINDOW_CHARS and windows:
        prev = windows[-1]
        prev.text += "\n\n" + text
        prev.char_count = len(prev.text)
        prev.event_ids.extend(event_ids)
        prev.turn_count += turn_count
        if end_time:
            prev.time_span[1] = end_time
        return

    sid_short = session_id.split(":")[-1][:12] if ":" in session_id else session_id[:12]
    windows.append(CandidateWindow(
        window_id=f"win_{source}_{sid_short}_{win_idx}",
        session_id=session_id,
        source=source,
        host=host,
        event_ids=event_ids,
        text=text,
        char_count=char_count,
        turn_count=turn_count,
        time_span=[start_time, end_time],
    ))


# ── 规则打分 ──────────────────────────────────────────────────────────


def score_window(window: CandidateWindow) -> float:
    """对候选窗口做规则打分。

    评分公式：
    score = density*0.3 + decision*0.25 + failure*0.2 + reusability*0.15 + sensitive_risk*(-0.1)

    Args:
        window: 候选窗口

    Returns:
        0.0 ~ 1.0 的分数
    """
    text = window.text.lower()

    density = _score_density(text)
    decision = _score_keywords(text, DECISION_KEYWORDS)
    failure = _score_keywords(text, FAILURE_KEYWORDS)
    reusability = _score_reusability(text)
    # sensitive_risk 暂不在此处计算，由写入网关处理

    score = density * 0.3 + decision * 0.25 + failure * 0.2 + reusability * 0.15
    return max(0.0, min(1.0, score))


def score_window_with_config(window: CandidateWindow, config: dict | None = None) -> float:
    """使用配置化权重对候选窗口打分。

    Args:
        window: 候选窗口
        config: scoring_policy.json 配置字典（可选，None 时自动加载）

    Returns:
        0.0 ~ 1.0 的分数
    """
    if config is None:
        config = _load_scoring_policy()

    weights = config.get("weights", _DEFAULT_WEIGHTS)
    hit_cap = config.get("keyword_hit_cap", _DEFAULT_KEYWORD_HIT_CAP)

    text = window.text.lower()
    density = _score_density(text)
    decision = _score_keywords(text, DECISION_KEYWORDS, hit_cap)
    failure = _score_keywords(text, FAILURE_KEYWORDS, hit_cap)
    reusability = _score_reusability(text)

    score = (
        density * weights.get("density", 0.3)
        + decision * weights.get("decision", 0.25)
        + failure * weights.get("failure", 0.2)
        + reusability * weights.get("reusability", 0.15)
    )
    return max(0.0, min(1.0, score))


def _score_density(text: str) -> float:
    """信息密度评分。"""
    total_len = len(text)
    if total_len == 0:
        return 0.0
    code_len = 0
    for pattern in DENSITY_PATTERNS:
        for match in re.finditer(pattern, text):
            code_len += len(match.group(0))
    return min(1.0, code_len / total_len * 5)  # 放大系数


def _score_keywords(text: str, keywords: list[str], hit_cap: int = 3) -> float:
    """关键词匹配评分。"""
    if not text:
        return 0.0
    hits = sum(1 for kw in keywords if kw in text)
    return min(1.0, hits / hit_cap)


def _score_reusability(text: str) -> float:
    """操作可复用评分（连续步骤模式）。"""
    for pattern in STEP_PATTERNS:
        matches = re.findall(pattern, text)
        if len(matches) >= 3:
            return 1.0
        if len(matches) >= 2:
            return 0.6
    return 0.0


def score_and_route(
    windows: list[CandidateWindow],
    config: dict | None = None,
) -> list[CandidateWindow]:
    """对窗口列表打分并路由。

    阈值可通过 scoring_policy.json 配置，默认：
    ≥ 0.7: 高价值 → status=high_value
    0.4~0.7: 仅索引 → status=index_only
    < 0.4: 跳过 → status=skip
    """
    if config is None:
        config = _load_scoring_policy()

    thresholds = config.get("thresholds", _DEFAULT_THRESHOLDS)
    high_value_threshold = thresholds.get("high_value", 0.7)
    index_only_threshold = thresholds.get("index_only", 0.4)

    for window in windows:
        window.score = score_window_with_config(window, config)
        if window.score >= high_value_threshold:
            window.status = "high_value"
        elif window.score >= index_only_threshold:
            window.status = "index_only"
        else:
            window.status = "skip"
        logger.debug(
            "window_scored:id=%s score=%.3f status=%s",
            window.window_id, window.score, window.status,
        )
    return windows


# ── 降级分类（不依赖 LLM） ───────────────────────────────────────────


def fallback_classify(window_text: str) -> dict[str, Any]:
    """纯规则降级分类，不依赖 LLM。

    Returns:
        {"kind": str, "confidence": float, "requires_human_review": bool}
    """
    text = window_text.lower()

    # 检测路径/端口/配置值 → memory
    if re.search(r"(/[\w./\-]+|[A-Z]:\\[\w\\.\-]+|:\d{2,5}|=\S+)", text):
        return {"kind": "memory", "confidence": 0.5, "requires_human_review": True}

    # 检测错误/失败/修复 → experience
    if any(kw in text for kw in FAILURE_KEYWORDS):
        return {"kind": "experience", "confidence": 0.5, "requires_human_review": True}

    # 检测决策/选择/决定 → adr
    if any(kw in text for kw in DECISION_KEYWORDS):
        return {"kind": "adr", "confidence": 0.5, "requires_human_review": True}

    # 默认 → memory（低置信度）
    return {"kind": "memory", "confidence": 0.3, "requires_human_review": True}

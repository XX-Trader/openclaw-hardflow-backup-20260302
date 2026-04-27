#!/usr/bin/env python3
"""统一的人类可读聊天输出格式。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

TZ = timezone(timedelta(hours=8))
UTC8_SUFFIX = "UTC+8"
PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s，。；;]+|/(?:[^/\s，。；;]+/)*[^/\s，。；;]+|[\w./-]+\.(?:json|log|txt|md|png|jpg|jpeg|webp))"
)
LOCAL_TIME_RE = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:\s*(?:\(?UTC\+8\)?|（北京时间）|\(北京时间\)))?$"
)

SENDER_LABELS = {
    "coordinator": "协调代理",
    "deployer": "部署代理",
    "doc-writer": "文档代理",
    "backend-dev": "后端执行代理",
    "frontend-dev": "前端执行代理",
    "ops-agent": "运维代理",
    "optimization-agent": "优化代理",
    "project-agent": "项目代理",
    "reviewer": "审查代理",
    "tester": "测试代理",
    "web-agent": "网页采集代理",
}


def _now_beijing() -> datetime:
    return datetime.now(TZ)


def strip_list_marker(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("- "):
        return value[2:].strip()
    if value.startswith("* "):
        return value[2:].strip()
    return value


def sanitize_text(value: object, max_len: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = PATH_RE.sub("已留痕", text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def format_beijing_time(value: str = "", fallback: datetime | None = None) -> str:
    raw = str(value or "").strip()
    if raw:
        normalized = raw.replace("（", "(").replace("）", ")").replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=TZ)
            return parsed.astimezone(TZ).strftime(f"%Y-%m-%d %H:%M:%S {UTC8_SUFFIX}")
        except Exception:
            local_match = LOCAL_TIME_RE.match(normalized)
            if local_match:
                parsed = datetime.fromisoformat(local_match.group("stamp").replace("T", " "))
                parsed = parsed.replace(tzinfo=TZ)
                return parsed.astimezone(TZ).strftime(f"%Y-%m-%d %H:%M:%S {UTC8_SUFFIX}")
            cleaned = sanitize_text(raw, max_len=48)
            if cleaned:
                return cleaned.replace("(UTC+8)", UTC8_SUFFIX).replace("（北京时间）", UTC8_SUFFIX)
    target = fallback or _now_beijing()
    if target.tzinfo is None:
        target = target.replace(tzinfo=TZ)
    target = target.astimezone(TZ)
    return target.strftime(f"%Y-%m-%d %H:%M:%S {UTC8_SUFFIX}")


def sender_label(sender_identity: str) -> str:
    raw = str(sender_identity or "").strip().lower()
    if not raw:
        return "系统"
    prefix = raw.split("/", 1)[0]
    return SENDER_LABELS.get(prefix, "系统")


def short_location_label(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    normalized = raw.replace("\\", "/").rstrip("/")
    if "://" in normalized:
        return normalized.rsplit("/", 1)[-1] or normalized
    if "/" in normalized:
        return normalized.split("/")[-1] or Path(normalized).name or normalized
    return normalized


def build_trace_id(*, run_id: str = "", report_file: str | Path | None = None) -> str:
    candidate = str(run_id or "").strip()
    if candidate:
        return candidate
    if report_file is None:
        return ""
    path = Path(str(report_file))
    return path.stem


def render_chat_notice(
    title: str,
    *,
    status: str,
    task_id: str = "",
    sender_identity: str = "",
    run_time: str = "",
    trace_id: str = "",
    summary: str = "",
    details: Iterable[str] | None = None,
    extra_lines: Iterable[str] | None = None,
    next_step: str = "",
) -> str:
    normalized_title = sanitize_text(title, max_len=80) or "系统通知"
    normalized_summary = sanitize_text(summary, max_len=160)
    headline = f"{format_beijing_time(run_time)} {normalized_title}"
    if normalized_summary:
        headline = f"{headline}：{normalized_summary}"
    lines = [headline]
    lines.append(f"- 状态：{sanitize_text(status, max_len=40) or '待处理'}")
    lines.append(f"- 时间：{format_beijing_time(run_time)}")
    normalized_task = sanitize_text(task_id, max_len=80)
    if normalized_task:
        lines.append(f"- 任务编号：{normalized_task}")
    lines.append(f"- 发送方：{sender_label(sender_identity)}")
    for item in extra_lines or []:
        text = sanitize_text(strip_list_marker(str(item or "")), max_len=160)
        if text:
            lines.append(f"- {text}")
    detail_index = 1
    for item in details or []:
        text = sanitize_text(strip_list_marker(str(item or "")), max_len=180)
        if not text:
            continue
        lines.append(f"- 说明{detail_index}：{text}")
        detail_index += 1
    normalized_next = sanitize_text(next_step, max_len=160)
    if normalized_next:
        lines.append(f"- 下一步：{normalized_next}")
    normalized_trace = sanitize_text(trace_id, max_len=80)
    if normalized_trace:
        lines.append(f"- 留痕编号：{normalized_trace}")
    else:
        lines.append("- 留痕：已归档")
    return "\n".join(lines)

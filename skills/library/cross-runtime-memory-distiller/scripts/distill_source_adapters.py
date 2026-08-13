#!/usr/bin/env python3
"""多源数据适配器：从 Claude / Gemini / OpenClaw / Hermes 会话中提取归一化事件。

每个 SourceAdapter 实现统一接口：
- probe(): 探测可用的会话路径
- extract(): 提取增量事件
- cursor_hint(): 返回最新游标值

适配器注册表: ADAPTER_REGISTRY
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

logger = logging.getLogger("distill_source_adapters")

# ── 数据模型 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RawEvent:
    """适配器输出的归一化原始事件。"""

    event_id: str
    source: str
    host: str
    project: str
    session_id: str
    role: str
    content: str
    timestamp: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# ── 适配器接口 ────────────────────────────────────────────────────────


@runtime_checkable
class SourceAdapter(Protocol):
    """所有数据源适配器必须满足的接口契约。"""

    def probe(self, probe_result: dict) -> list[str]:
        """探测并返回当前可用的会话/文件路径列表。"""
        ...

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从指定路径提取增量事件。"""
        ...

    def cursor_hint(self, path: str) -> dict:
        """返回当前路径的最新游标值。"""
        ...


# ── 工具函数 ──────────────────────────────────────────────────────────


def _safe_read_jsonl(path: str | Path, encoding: str = "utf-8") -> list[dict]:
    """安全读取 JSONL 文件，跳过解析失败的行。"""
    events: list[dict] = []
    p = Path(path)
    if not p.exists():
        return events
    try:
        text = p.read_text(encoding=encoding, errors="replace")
    except OSError:
        return events
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            logger.debug("jsonl_skip:file=%s line=%d", p, i)
    return events


def _truncate_tool_output(content: str, max_chars: int = 500, tail_chars: int = 200) -> str:
    """裁剪工具原始输出，保留头部和尾部。"""
    if len(content) <= max_chars + tail_chars:
        return content
    return content[:max_chars] + f"\n... [truncated {len(content) - max_chars - tail_chars} chars] ...\n" + content[-tail_chars:]


def _timestamp_now() -> str:
    """返回当前时间的 ISO 8601 字符串。"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Claude 适配器 ────────────────────────────────────────────────────


class ClaudeSourceAdapter:
    """Claude Code transcript 数据源适配器。

    路径（按优先级探测）：
    1. ~/.claude/projects/{project-slug}/*.jsonl  （Claude Code 实际存放位置）
    2. ~/.claude/transcripts/*.jsonl              （旧版路径兼容）
    格式: JSONL, 每行一条消息
    游标策略: mtime + file_offset
    """

    def probe(self, probe_result: dict) -> list[str]:
        """探测 Claude Code 会话 JSONL 文件。

        同时扫描 projects/ 和 transcripts/ 两个目录，去重后返回。
        支持通过 probe_result['since_hours'] 过滤老文件。
        """
        home = Path.home()
        files: list[Path] = []

        # 优先：projects/{slug}/*.jsonl（Claude Code 当前版本）
        projects_dir = home / ".claude" / "projects"
        if projects_dir.exists():
            for project in projects_dir.iterdir():
                if project.is_dir():
                    files.extend(project.glob("*.jsonl"))

        # 兼容：transcripts/*.jsonl（旧版）
        transcript_dir = home / ".claude" / "transcripts"
        if transcript_dir.exists():
            files.extend(transcript_dir.glob("*.jsonl"))

        if not files:
            logger.debug("claude_no_jsonl_found")
            return []

        # 按 mtime 过滤（since_hours）
        since_hours = probe_result.get("since_hours", 0)
        if since_hours > 0:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(hours=since_hours)
            files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff]

        # 去重（同名文件可能出现在两个目录）+ 排序
        seen: set[str] = set()
        unique: list[str] = []
        for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
            if f.name not in seen:
                seen.add(f.name)
                unique.append(str(f))
        return unique

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从 Claude transcript 提取增量事件。

        兼容两种 Claude transcript 格式：
        1. 顶层 content: {"type":"user","content":"xxx","timestamp":"..."}
        2. 嵌套 message: {"type":"assistant","message":{"role":"assistant","content":"xxx"}}
        """
        raw_events = _safe_read_jsonl(path)
        if not raw_events:
            return []

        # 从文件名推断 session_id
        file_stem = Path(path).stem
        session_id = f"claude:{file_stem}"
        offset = 0
        if cursor and "last_offset" in cursor:
            offset = cursor["last_offset"]

        events: list[RawEvent] = []
        for i, raw in enumerate(raw_events):
            if i < offset:
                continue

            # ── 提取 role ──
            raw_type = raw.get("type", "user")
            role_map = {"user": "user", "assistant": "assistant", "tool_result": "tool",
                        "tool": "tool", "system": "system"}
            mapped_role = role_map.get(raw_type, "user")
            # 也检查 message.role
            if "message" in raw and isinstance(raw["message"], dict):
                msg_role = raw["message"].get("role", "")
                if msg_role in role_map.values():
                    mapped_role = msg_role

            # ── 提取 content ──
            content = ""
            metadata: dict[str, Any] = {}

            # 优先：顶层 content（Claude Code 格式）
            top_content = raw.get("content", "")
            if isinstance(top_content, str) and top_content.strip():
                content = top_content
            elif isinstance(top_content, list):
                # content 是数组（含 text/tool_use blocks）
                parts = []
                for block in top_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            metadata["tool_name"] = block.get("name", "")
                            metadata["tool_input_summary"] = str(block.get("input", ""))[:200]
                        elif block.get("type") == "tool_result":
                            parts.append(str(block.get("content", ""))[:500])
                content = "\n".join(p for p in parts if p)
            elif isinstance(raw.get("message", {}).get("content"), str):
                content = raw["message"]["content"]
            elif isinstance(raw.get("message", {}).get("content"), list):
                parts = []
                for block in raw["message"]["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = "\n".join(parts)

            if mapped_role == "tool":
                content = _truncate_tool_output(str(content))

            # 提取工具调用信息（嵌套 message 格式）
            tool_uses = raw.get("message", {}).get("tool_use", [])
            if tool_uses and "tool_name" not in metadata:
                metadata["tool_name"] = tool_uses[0].get("name", "")
                metadata["tool_input_summary"] = str(tool_uses[0].get("input", ""))[:200]

            if not content.strip():
                continue

            events.append(RawEvent(
                event_id=f"claude:{file_stem}:{i}",
                source="claude",
                host="openclaw",
                project="",
                session_id=session_id,
                role=mapped_role,
                content=content,
                timestamp=raw.get("timestamp", _timestamp_now()),
                metadata=metadata,
            ))

        return events

    def cursor_hint(self, path: str) -> dict:
        """返回 Claude transcript 的最新游标。"""
        p = Path(path)
        if not p.exists():
            return {"last_mtime": "", "last_file": path, "last_offset": 0}
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        line_count = sum(1 for _ in p.read_text(encoding="utf-8", errors="replace").splitlines() if _.strip())
        return {"last_mtime": mtime, "last_file": path, "last_offset": line_count}


# ── OpenClaw 适配器 ──────────────────────────────────────────────────


class OpenClawSourceAdapter:
    """OpenClaw / Codex session 数据源适配器。

    路径: ~/.openclaw/agents/*/sessions/*.jsonl
    格式: JSONL, 含 agent_id / task_id / trace_id
    游标策略: mtime + file_offset
    """

    def probe(self, probe_result: dict) -> list[str]:
        """探测 OpenClaw session 目录。"""
        home = Path(probe_result.get("home", Path.home() / ".openclaw"))
        session_glob = home / "agents" / "*" / "sessions" / "*.jsonl"
        files = sorted(Path(session_glob.parent).glob(session_glob.name) if session_glob.parent.exists() else [])
        # 回退：直接扫描
        if not files:
            session_dir = home / "agents"
            if session_dir.exists():
                files = sorted(session_dir.rglob("*.jsonl"))
        return [str(f) for f in files]

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从 OpenClaw session 提取增量事件。"""
        raw_events = _safe_read_jsonl(path)
        if not raw_events:
            return []

        file_stem = Path(path).stem
        offset = 0
        if cursor and "last_offset" in cursor:
            offset = cursor["last_offset"]

        events: list[RawEvent] = []
        for i, raw in enumerate(raw_events):
            if i < offset:
                continue

            role = raw.get("role", "user")
            content = raw.get("content", "")
            if not content or not str(content).strip():
                continue

            metadata: dict[str, Any] = {}
            for key in ("agent_id", "task_id", "trace_id", "tool_name", "exit_code"):
                if key in raw:
                    metadata[key] = raw[key]

            # 工具调用摘要
            tool_calls = raw.get("tool_calls", [])
            if tool_calls:
                metadata["tool_name"] = tool_calls[0].get("name", "")
                metadata["tool_input_summary"] = str(tool_calls[0].get("arguments", ""))[:200]

            # 从路径推断 agent_id
            parts = Path(path).parts
            if "agents" in parts:
                idx = parts.index("agents")
                if idx + 1 < len(parts):
                    metadata.setdefault("agent_id", parts[idx + 1])

            events.append(RawEvent(
                event_id=f"openclaw:{file_stem}:{i}",
                source="openclaw",
                host="openclaw",
                project="",
                session_id=f"openclaw:{file_stem}",
                role=role,
                content=str(content) if role != "tool" else _truncate_tool_output(str(content)),
                timestamp=raw.get("timestamp", _timestamp_now()),
                metadata=metadata,
            ))

        return events

    def cursor_hint(self, path: str) -> dict:
        """返回 OpenClaw session 的最新游标。"""
        p = Path(path)
        if not p.exists():
            return {"last_mtime": "", "last_file": path, "last_offset": 0}
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        line_count = sum(1 for _ in p.read_text(encoding="utf-8", errors="replace").splitlines() if _.strip())
        return {"last_mtime": mtime, "last_file": path, "last_offset": line_count}


# ── Gemini 适配器 ────────────────────────────────────────────────────


class GeminiSourceAdapter:
    """Gemini brain / artifact 数据源适配器。

    路径: ~/.gemini/antigravity/brain/**
    格式: 多样（Markdown / JSON），保守策略处理
    游标策略: mtime
    """

    def probe(self, probe_result: dict) -> list[str]:
        """探测 Gemini brain 目录。支持 since_hours 时间过滤。"""
        home = Path.home()
        brain_dir = home / ".gemini" / "antigravity" / "brain"
        if not brain_dir.exists():
            return []
        files = [f for f in brain_dir.rglob("*") if f.is_file() and f.suffix in (".md", ".json", ".txt")]

        # 按 mtime 过滤（since_hours）
        since_hours = probe_result.get("since_hours", 0)
        if since_hours > 0:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(hours=since_hours)
            files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff]

        return [str(f) for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从 Gemini brain 文件提取事件。"""
        p = Path(path)
        if not p.exists():
            return []

        # 游标检查
        if cursor and "last_mtime" in cursor:
            try:
                file_mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                if file_mtime <= cursor["last_mtime"]:
                    return []
            except OSError:
                return []

        session_id = f"gemini:{p.stem}"

        if p.suffix == ".md":
            content = p.read_text(encoding="utf-8", errors="replace")
            return [RawEvent(
                event_id=f"gemini:{p.stem}:0",
                source="gemini",
                host="openclaw",
                project="",
                session_id=session_id,
                role="assistant",
                content=content[:5000],
                timestamp=_timestamp_now(),
                metadata={"artifact_type": "markdown"},
            )]

        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                return []
            content = data.get("summary", "")
            if not content:
                content = str(data)[:2000]
            metadata = {"artifact_type": "json"}
            if "logs" in data:
                metadata["logs_summary"] = str(data["logs"])[:200]
            return [RawEvent(
                event_id=f"gemini:{p.stem}:0",
                source="gemini",
                host="openclaw",
                project="",
                session_id=session_id,
                role="assistant",
                content=str(content)[:5000],
                timestamp=_timestamp_now(),
                metadata=metadata,
            )]

        return []

    def cursor_hint(self, path: str) -> dict:
        """返回 Gemini 文件的最新游标。"""
        p = Path(path)
        if not p.exists():
            return {"last_mtime": ""}
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        return {"last_mtime": mtime, "last_file": path}


# ── Hermes 适配器 ────────────────────────────────────────────────────


class HermesSourceAdapter:
    """Hermes session 数据源适配器。

    路径: ~/.hermes/sessions（WSL: /home/runtime-user/.hermes/sessions/）
    格式: JSONL 或 SQLite state.db
    游标策略: mtime / session_id_set
    """

    def __init__(self, wsl_distro: str = "Ubuntu") -> None:
        self.wsl_distro = wsl_distro

    def probe(self, probe_result: dict) -> list[str]:
        """探测 Hermes session 文件。"""
        home = probe_result.get("home", "")
        if not home:
            return []
        transport = probe_result.get("transport", "native_fs")

        if transport == "wsl_exec":
            # WSL 环境，尝试 UNC 读取
            distro = probe_result.get("distro", self.wsl_distro)
            unc_base = Path(f"\\\\wsl$\\{distro}") / home.lstrip("/") / "sessions"
            if unc_base.exists():
                return [str(f) for f in sorted(unc_base.rglob("*.jsonl"))]
            return []

        # 原生环境
        session_dir = Path(home) / "sessions"
        if not session_dir.exists():
            return []
        return [str(f) for f in sorted(session_dir.rglob("*.jsonl"))]

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从 Hermes session 提取事件。"""
        raw_events = _safe_read_jsonl(path)
        if not raw_events:
            return []

        file_stem = Path(path).stem
        offset = 0
        if cursor and "last_offset" in cursor:
            offset = cursor["last_offset"]

        events: list[RawEvent] = []
        for i, raw in enumerate(raw_events):
            if i < offset:
                continue

            content = raw.get("content", "")
            if not content or not str(content).strip():
                continue

            metadata: dict[str, Any] = {}
            if "memory_actions" in raw:
                metadata["memory_action"] = raw["memory_actions"]
            if "summary_version" in raw:
                metadata["summary_version"] = raw["summary_version"]
            if "compression_round" in raw:
                metadata["compression_round"] = raw["compression_round"]

            events.append(RawEvent(
                event_id=f"hermes:{file_stem}:{i}",
                source="hermes",
                host="hermes",
                project="",
                session_id=f"hermes:{raw.get('session_id', file_stem)}",
                role=raw.get("role", "user"),
                content=str(content),
                timestamp=raw.get("timestamp", _timestamp_now()),
                metadata=metadata,
            ))

        return events

    def cursor_hint(self, path: str) -> dict:
        """返回 Hermes session 的最新游标。"""
        p = Path(path)
        if not p.exists():
            return {"last_mtime": "", "last_file": path, "last_offset": 0}
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        except OSError:
            mtime = ""
        line_count = sum(1 for _ in p.read_text(encoding="utf-8", errors="replace").splitlines() if _.strip())
        return {"last_mtime": mtime, "last_file": path, "last_offset": line_count}


# ── Docs 适配器 ──────────────────────────────────────────────────────


class DocsSourceAdapter:
    """文档证据适配器（todo.md / done.md / ADR / 功能三件套）。

    路径: 仓库内 docs/**, todo.md, done.md
    游标策略: mtime + file_hash
    """

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root

    def probe(self, probe_result: dict) -> list[str]:
        """探测仓库中的文档文件。"""
        root = Path(self.workspace_root) if self.workspace_root else Path(".")
        if not root.exists():
            return []
        files: list[str] = []
        # 根目录文档
        for name in ("todo.md", "done.md"):
            p = root / name
            if p.exists():
                files.append(str(p))
        # docs 目录
        docs_dir = root / "docs"
        if docs_dir.exists():
            for p in docs_dir.rglob("*.md"):
                files.append(str(p))
        return sorted(files)

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从文档文件提取事件。"""
        p = Path(path)
        if not p.exists():
            return []

        # 游标检查（mtime）
        if cursor and "last_mtime" in cursor:
            try:
                file_mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                if file_mtime <= cursor["last_mtime"]:
                    return []
            except OSError:
                return []

        content = p.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return []

        # 推断 doc_type
        doc_type = "feature_readme"
        if p.name == "todo.md":
            doc_type = "todo"
        elif p.name == "done.md":
            doc_type = "done"
        elif "adr" in str(p).lower():
            doc_type = "adr"

        return [RawEvent(
            event_id=f"docs:{p.stem}:0",
            source="docs",
            host="openclaw",
            project="",
            session_id=f"docs:{p.stem}",
            role="system",
            content=content[:5000],
            timestamp=_timestamp_now(),
            metadata={"doc_type": doc_type, "file_path": str(p)},
        )]

    def cursor_hint(self, path: str) -> dict:
        """返回文档文件的最新游标。"""
        p = Path(path)
        if not p.exists():
            return {"last_mtime": "", "last_file": path}
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        return {"last_mtime": mtime, "last_file": path}


# ── 适配器注册表 ─────────────────────────────────────────────────────

ADAPTER_REGISTRY: dict[str, type] = {
    "claude": ClaudeSourceAdapter,
    "gemini": GeminiSourceAdapter,
    "openclaw": OpenClawSourceAdapter,
    "hermes": HermesSourceAdapter,
    "docs": DocsSourceAdapter,
}


def get_adapter(source: str, **kwargs: Any) -> SourceAdapter:
    """按名称获取适配器实例。

    Args:
        source: 数据源名称
        **kwargs: 适配器构造参数

    Returns:
        适配器实例

    Raises:
        ValueError: 未知数据源
    """
    cls = ADAPTER_REGISTRY.get(source)
    if cls is None:
        raise ValueError(f"unknown_source:{source},available={list(ADAPTER_REGISTRY.keys())}")
    # 只传递适配器实际接受的参数
    import inspect
    sig = inspect.signature(cls.__init__)
    valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return cls(**valid_kwargs)

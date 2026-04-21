#!/usr/bin/env python3
"""热记忆写入网关：受控 add/replace/remove 操作、去重、预算校验、敏感扫描。

写入网关是热记忆层的唯一入口。所有对 USER.md / MEMORY.md 的修改
都必须经过本模块，保证去重、预算、备份和敏感扫描的强制执行。

设计原则：
- 写前备份（最近 3 版）
- 去重指纹（MD5(normalize(title + body))）
- 容量预算校验（超限拒绝写入）
- 敏感信息扫描（命中拒绝或掩码）
- 唯一子串匹配（replace/remove 多命中时报错）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

# ── 日志 ──────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("memory_write_gateway")


def _setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """配置日志输出。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        force=True,
    )
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(fh)


# ── UTF-8 stdio ───────────────────────────────────────────────────────


def _configure_utf8_stdio() -> None:
    """尽量复用仓库现有 UTF-8 运行时配置。"""
    shared_dir = Path(__file__).resolve().parents[4] / "scripts" / "openclaw-ops" / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    try:
        from utf8_runtime import configure_process_utf8_stdio  # type: ignore
    except Exception:
        return
    configure_process_utf8_stdio()


_configure_utf8_stdio()


# ── 配置加载 ──────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config(name: str) -> dict:
    """加载 config/ 下的 JSON 配置文件。

    加载优先级：
    1. 环境变量 {NAME}_CONFIG_PATH 指定的路径（覆盖）
    2. config/{name}.json 文件

    Args:
        name: 配置文件名（如 "memory_limits", "distill_rules"）

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        json.JSONDecodeError: 配置文件格式错误
    """
    env_key = f"{name.upper().replace('.', '_').replace('-', '_')}_CONFIG_PATH"
    env_path = os.environ.get(env_key)
    config_path = Path(env_path) if env_path else CONFIG_DIR / f"{name}.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config_not_found:{config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


# ── 领域对象 ──────────────────────────────────────────────────────────


@dataclass
class MemoryAction:
    """仿照 Hermes 记忆工具的受控动作。"""

    action: str  # add | replace | remove
    target: str  # user | memory | experience | adr | pattern
    old_text: str = ""  # replace/remove 时必填
    content: str = ""  # add/replace 时的正文
    title: str = ""  # 条目标题（用于去重指纹）
    reason: str = ""  # 为什么要写/替换/删除
    source_report: str = ""  # 来源蒸馏报告

    def validate(self) -> list[str]:
        """校验动作合法性，返回错误列表。"""
        errors: list[str] = []
        if self.action not in ("add", "replace", "remove"):
            errors.append(f"invalid_action:{self.action}")
        if self.target not in ("user", "memory", "experience", "adr", "pattern"):
            errors.append(f"invalid_target:{self.target}")
        if self.action in ("add", "replace") and not self.content.strip():
            errors.append("empty_content")
        if self.action in ("replace", "remove") and not self.old_text.strip():
            errors.append("empty_old_text")
        return errors


@dataclass
class WriteResult:
    """写入操作结果。"""

    success: bool
    action: str
    target: str
    message: str
    file_path: str = ""
    bytes_written: int = 0
    total_bytes: int = 0
    max_bytes: int = 0
    duplicates_skipped: bool = False
    sensitive_found: list[str] = field(default_factory=list)
    compression_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 去重指纹 ─────────────────────────────────────────────────────────


def normalize_for_fingerprint(title: str, body: str) -> str:
    """去重指纹归一化：去除空白差异、标点差异，统一小写。

    注意：不做中文折叠，只做空白和简单标点归一化。
    """
    text = f"{title} {body}".lower()
    # 去除多余空白
    text = re.sub(r"\s+", " ", text).strip()
    # 归一化标点（中文标点 → 英文等效）
    for cn, en in [("，", ","), ("。", "."), ("：", ":"), ("；", ";"), ("！", "!"), ("？", "?")]:
        text = text.replace(cn, en)
    return text


def compute_fingerprint(title: str, body: str) -> str:
    """计算去重指纹：MD5(normalize(title + body))。"""
    normalized = normalize_for_fingerprint(title, body)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def check_duplicate(fingerprint: str, db_path: str | Path) -> bool:
    """查询指纹是否已存在。

    Args:
        fingerprint: MD5 指纹
        db_path: distill.db 路径

    Returns:
        True 表示已存在（重复），False 表示不重复
    """
    db = Path(db_path)
    if not db.exists():
        return False
    # 并发安全：只读连接也设置 busy_timeout 防止长时间等待
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            row = conn.execute(
                "SELECT 1 FROM dedup_fingerprints WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # 表不存在，视为不重复
        return False


def record_fingerprint(fingerprint: str, artifact_id: str, db_path: str | Path) -> None:
    """记录新指纹到数据库。

    Args:
        fingerprint: MD5 指纹
        artifact_id: 关联的产物 ID
        db_path: distill.db 路径
    """
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dedup_fingerprints (
                fingerprint   TEXT PRIMARY KEY,
                artifact_id   TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            )
            """,
        )
        conn.execute(
            "INSERT OR IGNORE INTO dedup_fingerprints (fingerprint, artifact_id) VALUES (?, ?)",
            (fingerprint, artifact_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── 写前备份 ──────────────────────────────────────────────────────────


def backup_file(path: Path, max_backups: int = 3) -> Path:
    """写前备份，保留最近 N 个版本。

    Args:
        path: 要备份的文件
        max_backups: 最多保留几个备份

    Returns:
        备份文件路径
    """
    if not path.exists():
        return path
    backup_dir = path.parent / ".memory-backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}.{ts}{path.suffix}"
    shutil.copy2(path, backup_path)
    # 清理旧备份
    # 精确匹配时间戳格式备份文件：{stem}.YYYYMMDD_HHMMSS{suffix}
    backups = sorted(backup_dir.glob(f"{path.stem}.[0-9]*{path.suffix}"))
    for old in backups[:-max_backups]:
        old.unlink()
    return backup_path


# ── 敏感信息扫描 ──────────────────────────────────────────────────────

# 内置扫描规则（用于 config 未提供或规则为空时的兜底）
_BUILTIN_SENSITIVE_RULES: list[dict[str, str]] = [
    {"name": "api_key", "pattern": r"(sk-|ghp_|gho_|xoxb-|xoxp-)[a-zA-Z0-9]{20,}", "action": "mask"},
    {"name": "aws_credential", "pattern": r"AKIA[0-9A-Z]{16}", "action": "mask"},
    {"name": "private_key", "pattern": r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY", "action": "replace"},
    {"name": "db_connection", "pattern": r"(mongodb|postgres|mysql)://[^\s]+:[^\s]+@", "action": "mask"},
    {"name": "jwt_token", "pattern": r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}", "action": "mask"},
    {"name": "email", "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "action": "warn"},
    {"name": "prompt_injection", "pattern": r"(ignore previous|disregard above|system:|<system>)", "action": "reject"},
]


def _load_sensitive_rules(config: dict | None = None) -> list[dict]:
    """从配置加载敏感扫描规则，缺失时使用内置规则。"""
    if config and config.get("sensitive_scan", {}).get("enabled"):
        rules = config["sensitive_scan"].get("rules", [])
        if rules:
            return rules
    return _BUILTIN_SENSITIVE_RULES


@dataclass
class SensitiveScanResult:
    """敏感扫描结果。"""

    has_sensitive: bool
    has_reject: bool  # 包含必须拒绝的内容（如 prompt injection）
    hits: list[str]  # 命中的规则名称列表
    masked_content: str  # 掩码后的内容


def scan_sensitive(content: str, config: dict | None = None) -> SensitiveScanResult:
    """扫描内容中的敏感信息。

    Args:
        content: 要扫描的文本
        config: memory_limits.json 配置字典（可选）

    Returns:
        SensitiveScanResult 实例
    """
    rules = _load_sensitive_rules(config)
    hits: list[str] = []
    has_reject = False
    masked = content

    for rule in rules:
        name = rule.get("name", "unknown")
        pattern = rule.get("pattern", "")
        action = rule.get("action", "mask")
        try:
            matches = re.findall(pattern, masked, re.IGNORECASE)
        except re.error:
            continue
        if not matches:
            continue
        hits.append(name)
        if action == "reject":
            has_reject = True
            continue
        # 掩码替换
        if action == "mask":
            masked = re.sub(
                pattern,
                lambda m: m.group(0)[:6] + "****[REDACTED]",
                masked,
                flags=re.IGNORECASE,
            )
        elif action == "replace":
            replacement = rule.get("replacement", "[REDACTED]")
            masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)

    return SensitiveScanResult(
        has_sensitive=len(hits) > 0,
        has_reject=has_reject,
        hits=hits,
        masked_content=masked,
    )


# ── 热记忆文件格式 ───────────────────────────────────────────────────


def parse_memory_file(content: str) -> dict[str, Any]:
    """解析 USER.md / MEMORY.md 的元数据与正文。

    Returns:
        {"version": int, "last_updated": str, "entry_count": int,
         "total_bytes": int, "body": str, "meta_raw": str}
    """
    meta: dict[str, Any] = {
        "version": 1,
        "last_updated": "",
        "entry_count": 0,
        "total_bytes": 0,
    }
    meta_raw = ""
    body = content

    # 提取 HTML 注释块中的元数据
    meta_match = re.search(r"<!--\s*memory-meta\s*\n(.*?)-->", content, re.DOTALL)
    if meta_match:
        meta_raw = meta_match.group(0)
        body = content[: meta_match.start()] + content[meta_match.end() :]
        for line in meta_match.group(1).strip().splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "version":
                    meta["version"] = int(val)
                elif key == "last_updated":
                    meta["last_updated"] = val
                elif key == "entry_count":
                    meta["entry_count"] = int(val)
                elif key == "total_bytes":
                    meta["total_bytes"] = int(val)

    body = body.strip()
    meta["total_bytes"] = len(body.encode("utf-8"))
    return {**meta, "body": body, "meta_raw": meta_raw}


def build_memory_meta(version: int, entry_count: int, total_bytes: int) -> str:
    """生成 memory-meta HTML 注释块。"""
    return (
        f"<!-- memory-meta\n"
        f"version: {version}\n"
        f"last_updated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"entry_count: {entry_count}\n"
        f"total_bytes: {total_bytes}\n"
        f"-->"
    )


def find_unique_substring(file_content: str, old_text: str) -> tuple[int, int] | None:
    """在文件中查找唯一匹配的子串位置。

    策略：
    1. 精确匹配
    2. 按行匹配（去除首尾空白后比较）
    3. 未找到返回 None
    4. 多处匹配抛 ValueError

    Args:
        file_content: 文件完整内容
        old_text: 要查找的文本

    Returns:
        (start, end) 偏移量

    Raises:
        ValueError: 多处匹配时
    """
    # 1. 精确匹配
    count = file_content.count(old_text)
    if count == 1:
        start = file_content.index(old_text)
        return (start, start + len(old_text))
    if count > 1:
        raise ValueError(f"ambiguous_match:found={count}")

    # 2. 按行匹配
    old_lines = [ln.strip() for ln in old_text.strip().splitlines() if ln.strip()]
    if not old_lines:
        return None
    file_lines = file_content.splitlines(keepends=True)
    matches: list[int] = []
    for i in range(len(file_lines) - len(old_lines) + 1):
        window = [ln.strip() for ln in file_lines[i : i + len(old_lines)] if ln.strip()]
        if window == old_lines:
            matches.append(i)
    if len(matches) == 1:
        start = sum(len(ln) for ln in file_lines[: matches[0]])
        end = start + sum(len(ln) for ln in file_lines[matches[0] : matches[0] + len(old_lines)])
        return (start, end)
    if len(matches) > 1:
        raise ValueError(f"ambiguous_line_match:found={len(matches)}")

    return None


# ── 写入网关核心 ──────────────────────────────────────────────────────

# 热记忆目标文件映射
TARGET_FILE_MAP = {
    "user": "USER.md",
    "memory": "MEMORY.md",
}


def _resolve_memory_path(target: str, hot_memory_paths: dict[str, str]) -> Path:
    """解析目标文件路径。

    Args:
        target: 目标类型（user / memory）
        hot_memory_paths: RuntimeProbeResult.hot_memory_paths

    Returns:
        文件路径

    Raises:
        ValueError: 目标类型不支持
    """
    if target not in TARGET_FILE_MAP:
        raise ValueError(f"unsupported_target:{target}")
    key = target
    if key not in hot_memory_paths:
        raise ValueError(f"missing_path_for_target:{key}")
    return Path(hot_memory_paths[key])


def _count_entries(body: str) -> int:
    """统计正文中条目数量（以 '- ' 开头的行数）。"""
    return sum(1 for line in body.splitlines() if line.strip().startswith("- "))


def _budget_key_for_target(target: str) -> str:
    """返回 target 对应的预算配置 key。"""
    return "user_md" if target == "user" else "memory_md"


def execute_write(
    action_obj: MemoryAction,
    hot_memory_paths: dict[str, str],
    config: dict,
    db_path: str | Path = "",
    artifact_id: str = "",
) -> WriteResult:
    """执行单次热记忆写入操作。

    流程：
    1. 校验动作合法性
    2. 敏感扫描
    3. 去重检查（add 时）
    4. 预算校验
    5. 写前备份
    6. 执行 add/replace/remove
    7. 回写文件
    8. 记录去重指纹

    Args:
        action_obj: 记忆动作
        hot_memory_paths: RuntimeProbeResult.hot_memory_paths
        config: memory_limits.json 配置
        db_path: distill.db 路径（可选，用于去重）
        artifact_id: 关联产物 ID（可选，用于去重记录）

    Returns:
        WriteResult
    """
    # 1. 校验
    errors = action_obj.validate()
    if errors:
        return WriteResult(
            success=False,
            action=action_obj.action,
            target=action_obj.target,
            message=f"validation_failed:{','.join(errors)}",
        )

    # 非热记忆目标直接返回（experience/adr/pattern 暂不处理）
    if action_obj.target not in TARGET_FILE_MAP:
        return WriteResult(
            success=False,
            action=action_obj.action,
            target=action_obj.target,
            message=f"target_not_hot_memory:{action_obj.target}",
        )

    # 2. 敏感扫描
    scan_result = scan_sensitive(action_obj.content, config)
    if scan_result.has_reject:
        return WriteResult(
            success=False,
            action=action_obj.action,
            target=action_obj.target,
            message=f"sensitive_reject:{','.join(scan_result.hits)}",
            sensitive_found=scan_result.hits,
        )

    # 使用掩码后的内容
    safe_content = scan_result.masked_content

    # 3. 去重检查（add 时）
    if action_obj.action == "add" and db_path:
        fp = compute_fingerprint(action_obj.title, safe_content)
        if check_duplicate(fp, db_path):
            return WriteResult(
                success=False,
                action=action_obj.action,
                target=action_obj.target,
                message="duplicate_skipped",
                duplicates_skipped=True,
            )

    # 4. 解析路径
    try:
        file_path = _resolve_memory_path(action_obj.target, hot_memory_paths)
    except ValueError as exc:
        return WriteResult(
            success=False,
            action=action_obj.action,
            target=action_obj.target,
            message=str(exc),
        )

    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有内容
    if file_path.exists():
        raw = file_path.read_text(encoding="utf-8")
    else:
        file_title = "USER" if action_obj.target == "user" else "MEMORY"
        raw = f"# {file_title}\n"

    parsed = parse_memory_file(raw)
    body = parsed["body"]

    # 5. 预算校验（add/replace 时检查写入后大小）
    budget_key = _budget_key_for_target(action_obj.target)
    budget = config.get("hot_memory", {}).get(budget_key, {})
    max_bytes = budget.get("max_bytes", 8192)

    if action_obj.action in ("add", "replace"):
        # 预估写入后大小
        if action_obj.action == "add":
            new_body = body.rstrip() + "\n" + safe_content.strip() + "\n"
        else:
            pos = find_unique_substring(body, action_obj.old_text)
            if pos is None:
                return WriteResult(
                    success=False,
                    action=action_obj.action,
                    target=action_obj.target,
                    message="old_text_not_found",
                )
            new_body = body[: pos[0]] + safe_content.strip() + body[pos[1] :]
            new_body = new_body.strip() + "\n"

        new_size = len(new_body.encode("utf-8"))
        if new_size > max_bytes:
            # 生成压缩建议
            hints = _generate_compression_hints(body, max_bytes)
            return WriteResult(
                success=False,
                action=action_obj.action,
                target=action_obj.target,
                message=f"budget_exceeded:current={new_size}B,max={max_bytes}B",
                file_path=str(file_path),
                bytes_written=0,
                total_bytes=len(body.encode("utf-8")),
                max_bytes=max_bytes,
                compression_hints=hints,
            )

        # 检查预警阈值
        warn_pct = budget.get("warn_threshold_pct", 80)
        if new_size > max_bytes * warn_pct / 100:
            logger.warning(
                "memory_budget_warning:target=%s usage=%.1f%% (%d/%d bytes)",
                action_obj.target,
                new_size / max_bytes * 100,
                new_size,
                max_bytes,
            )

        final_body = new_body
    elif action_obj.action == "remove":
        pos = find_unique_substring(body, action_obj.old_text)
        if pos is None:
            return WriteResult(
                success=False,
                action=action_obj.action,
                target=action_obj.target,
                message="old_text_not_found",
            )
        final_body = (body[: pos[0]] + body[pos[1] :]).strip() + "\n"
    else:
        return WriteResult(
            success=False,
            action=action_obj.action,
            target=action_obj.target,
            message=f"unsupported_action:{action_obj.action}",
        )

    # 6. 写前备份
    backup_file(file_path)

    # 7. 组装并写入
    file_title = "USER" if action_obj.target == "user" else "MEMORY"
    entry_count = _count_entries(final_body)
    total_bytes = len(final_body.encode("utf-8"))
    meta_block = build_memory_meta(
        version=parsed.get("version", 1),
        entry_count=entry_count,
        total_bytes=total_bytes,
    )
    final_content = f"# {file_title}\n\n{meta_block}\n\n{final_body.strip()}\n"

    file_path.write_text(final_content, encoding="utf-8")

    # 8. 记录去重指纹
    if action_obj.action == "add" and db_path:
        fp = compute_fingerprint(action_obj.title, safe_content)
        record_fingerprint(fp, artifact_id or f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}", db_path)

    logger.info(
        "memory_write_ok:action=%s target=%s file=%s bytes=%d",
        action_obj.action,
        action_obj.target,
        file_path,
        total_bytes,
    )

    return WriteResult(
        success=True,
        action=action_obj.action,
        target=action_obj.target,
        message="ok",
        file_path=str(file_path),
        bytes_written=len(safe_content.encode("utf-8")),
        total_bytes=total_bytes,
        max_bytes=max_bytes,
        sensitive_found=scan_result.hits if scan_result.has_sensitive else [],
    )


def _generate_compression_hints(body: str, max_bytes: int) -> list[str]:
    """生成压缩建议，帮助用户知道哪些条目可以合并/降级/归档。"""
    hints: list[str] = []
    lines = [ln for ln in body.splitlines() if ln.strip().startswith("- ")]
    if len(lines) > 10:
        hints.append(f"条目数 {len(lines)} 较多，考虑合并相似条目")
    long_lines = [ln for ln in lines if len(ln) > 200]
    if long_lines:
        hints.append(f"存在 {len(long_lines)} 条超长条目（>200字），考虑精简或拆分到经验层")
    current_bytes = len(body.encode("utf-8"))
    hints.append(f"当前 {current_bytes}B / 预算 {max_bytes}B，需压缩约 {current_bytes - max_bytes}B")
    return hints


# ── 批量执行 ──────────────────────────────────────────────────────────


def execute_batch(
    actions: Sequence[MemoryAction],
    hot_memory_paths: dict[str, str],
    config: dict,
    db_path: str | Path = "",
) -> list[WriteResult]:
    """批量执行多个写入动作。

    Args:
        actions: 动作列表
        hot_memory_paths: RuntimeProbeResult.hot_memory_paths
        config: memory_limits.json 配置
        db_path: distill.db 路径

    Returns:
        每个动作的执行结果列表
    """
    results: list[WriteResult] = []
    for i, action_obj in enumerate(actions):
        logger.info("batch_executing:%d/%d action=%s target=%s", i + 1, len(actions), action_obj.action, action_obj.target)
        result = execute_write(
            action_obj=action_obj,
            hot_memory_paths=hot_memory_paths,
            config=config,
            db_path=db_path,
            artifact_id=f"batch_{i:04d}",
        )
        results.append(result)
    return results


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="Memory Write Gateway: add/replace/remove 热记忆条目")
    parser.add_argument(
        "--action",
        required=True,
        choices=["add", "replace", "remove"],
        help="执行动作",
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=["user", "memory"],
        help="目标文件",
    )
    parser.add_argument("--content", default="", help="add/replace 时的正文")
    parser.add_argument("--old-text", default="", help="replace/remove 时的旧文本")
    parser.add_argument("--title", default="", help="条目标题（用于去重）")
    parser.add_argument("--reason", default="", help="操作原因")
    parser.add_argument("--hot-memory-path", default="", help="目标文件的完整路径（覆盖自动探测）")
    parser.add_argument("--db-path", default="", help="distill.db 路径（启用去重）")
    parser.add_argument("--artifact-id", default="", help="关联产物 ID")
    parser.add_argument("--config-path", default="", help="memory_limits.json 路径（覆盖默认）")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写入")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument("--log-file", default="", help="日志文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level, args.log_file or None)

    # 加载配置
    try:
        if args.config_path:
            config = json.loads(Path(args.config_path).read_text(encoding="utf-8"))
        else:
            config = load_config("memory_limits")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("config_load_failed:%s", exc)
        return 1

    # 构造 hot_memory_paths
    if args.hot_memory_path:
        hot_memory_paths = {args.target: args.hot_memory_path}
    else:
        logger.error("hot_memory_path_required:请通过 --hot-memory-path 指定目标文件路径")
        return 1

    # 构造动作
    action_obj = MemoryAction(
        action=args.action,
        target=args.target,
        old_text=args.old_text,
        content=args.content,
        title=args.title,
        reason=args.reason,
    )

    if args.dry_run:
        errors = action_obj.validate()
        scan_result = scan_sensitive(args.content, config)
        info = {
            "action": args.action,
            "target": args.target,
            "validation_errors": errors,
            "sensitive_hits": scan_result.hits,
            "has_reject": scan_result.has_reject,
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    result = execute_write(
        action_obj=action_obj,
        hot_memory_paths=hot_memory_paths,
        config=config,
        db_path=args.db_path,
        artifact_id=args.artifact_id,
    )

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

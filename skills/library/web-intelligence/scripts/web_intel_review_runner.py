#!/usr/bin/env python3
"""Review web intelligence outputs for optimization-agent / project-agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))


# Source checkouts keep each script under its owning Skill; installed runtimes
# flatten the same dependencies into the ops directory. Bootstrap only when
# the repository marker is present so both layouts share one implementation.
for _candidate_root in Path(__file__).resolve().parents:
    _shared_dir = _candidate_root / "scripts" / "openclaw-ops" / "shared"
    if _shared_dir.is_dir():
        _shared_value = str(_shared_dir)
        if _shared_value not in sys.path:
            sys.path.insert(0, _shared_value)
        from repo_imports import bootstrap_repository_imports

        bootstrap_repository_imports(__file__)
        break

from utf8_runtime import configure_process_utf8_stdio
from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic  # type: ignore
from chat_output import build_trace_id, render_chat_notice
from task_capability_binding import extend_create_task_args_with_constraints
from web_sources_runtime import load_runtime_sources  # type: ignore

configure_process_utf8_stdio()

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_ON_MODES = {"error", "change", "always"}
MODES = {"optimization", "project-doc"}
DEFAULT_SENDER_BY_MODE = {
    "optimization": "optimization-agent/web-intel-review",
    "project-doc": "project-agent/web-doc-review",
}
PROJECT_DOC_CATEGORY_HINTS = {"project-doc", "api-doc", "official-doc", "sdk-doc"}
PROJECT_DOC_TAG_HINTS = {"api", "doc", "docs", "official", "reference", "sdk"}
SIGNAL_RULES = [
    {
        "id": "deprecation",
        "pattern": r"\bdeprecated|sunset|will be removed|retire\b",
        "title": "废弃/下线信号",
        "optimization_action": "检查工作流和脚本中是否仍调用旧能力，补迁移计划。",
        "project_action": "更新接口调用与文档注释，补充兼容性测试。",
    },
    {
        "id": "breaking-change",
        "pattern": r"\bbreaking change|incompatible|migration|migrate\b",
        "title": "破坏性变更信号",
        "optimization_action": "创建跨 agent 迁移任务并评估影响窗口。",
        "project_action": "先修契约测试，再调整实现并验证回归。",
    },
    {
        "id": "rate-limit",
        "pattern": r"\brate limit|quota|429|throttl",
        "title": "限流/配额信号",
        "optimization_action": "优化调度频率与重试退避策略，防止任务雪崩。",
        "project_action": "在调用层增加重试、缓存和告警阈值。",
    },
    {
        "id": "security",
        "pattern": r"\bsecurity|vulnerab|cve|auth|permission\b",
        "title": "安全相关信号",
        "optimization_action": "安排安全审查任务，优先验证密钥与权限配置。",
        "project_action": "补充鉴权与安全测试，收敛高风险接口暴露。",
    },
    {
        "id": "api-contract",
        "pattern": r"\brequest|response|schema|parameter|endpoint|api reference\b",
        "title": "API 契约信号",
        "optimization_action": "同步索引规则，确保项目索引优先纳入最新契约。",
        "project_action": "更新请求/响应模型与契约测试用例。",
    },
]


def trace_token(value: str | Path) -> str:
    token = build_trace_id(report_file=value)
    return token or "已归档"
HTTP_METHOD_RE = r"(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)"
INTERFACE_RE = re.compile(
    rf"(?i)\b({HTTP_METHOD_RE})\s+((?:https?://[^\s`\"'<>]+)|(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*[A-Za-z0-9_/#-]))"
)
HIGHLIGHT_KEYWORDS = (
    "new",
    "added",
    "新增",
    "更新",
    "update",
    "changed",
    "deprecated",
    "breaking",
    "endpoint",
    "接口",
    "parameter",
    "response",
    "schema",
    "field",
)


def should_quiet(log_mode: str, notify_on: str, changed_count: int) -> bool:
    if str(log_mode or "").strip().lower() != "silent":
        return False
    mode = str(notify_on or "change").strip().lower()
    if mode == "always":
        return False
    if mode == "error":
        return True
    return int(changed_count) <= 0


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, mode: str) -> str:
    sender = str(value or "").strip()
    return sender or DEFAULT_SENDER_BY_MODE.get(mode, "optimization-agent/web-intel-review")


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def policy_enforcer_path() -> Path:
    return POLICY_DIR / "policy_enforcer.py"


def invoke_policy_enforcer(db_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, dict[str, Any], str]:
    script = policy_enforcer_path()
    if not script.exists():
        return False, {}, f"policy_enforcer_missing:{script}"
    cmd = [sys.executable, str(script), "--db", str(db_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return False, {}, f"policy_enforcer_exec_failed:{exc}"

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    if not isinstance(payload, dict):
        return False, {}, "policy_enforcer_invalid_json_output"
    if not bool(payload.get("ok", False)):
        return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
    return True, payload, ""


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def save_text(path: Path, content: str) -> None:
    try:
        atomic_write_text(
            path,
            str(content or ""),
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_text_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def compact(text: str, max_len: int = 180) -> str:
    one_line = " ".join(str(text or "").split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3].rstrip() + "..."


def normalize_doc_text(content: str) -> str:
    text = str(content or "")
    if "<" not in text and ">" not in text:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]
        return "\n".join(line for line in lines if line)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(?:p|div|section|article|li|tr|td|th|pre|code|ul|ol|h[1-6])>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def split_doc_units(text: str) -> list[str]:
    normalized = normalize_doc_text(text)
    raw_lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    units = raw_lines if len(raw_lines) > 1 else [part.strip() for part in re.split(r"(?<=[。.!?;；])\s+", normalized) if part.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for unit in units:
        cleaned = re.sub(r"\s+", " ", unit).strip(" -\t")
        if len(cleaned) < 8:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def score_highlight(unit: str) -> tuple[int, int]:
    lower = unit.casefold()
    score = 0
    if any(keyword in lower for keyword in HIGHLIGHT_KEYWORDS):
        score += 3
    if INTERFACE_RE.search(unit):
        score += 4
    if any(ch.isdigit() for ch in unit):
        score += 1
    if 16 <= len(unit) <= 180:
        score += 1
    return score, -len(unit)


def extract_new_information(previous_text: str, current_text: str, limit: int = 4) -> list[str]:
    previous_units = {unit.casefold() for unit in split_doc_units(previous_text)}
    candidates = [unit for unit in split_doc_units(current_text) if unit.casefold() not in previous_units]
    ranked = sorted(candidates, key=score_highlight, reverse=True)
    return ranked[: max(1, int(limit))]


def normalize_interface(method: str, target: str) -> str:
    value = str(target or "").strip().rstrip(".,;:)]}>")
    if value.lower().startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(value)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        value = path
    if value != "/" and value.endswith("/"):
        value = value[:-1]
    return f"{str(method or '').upper()} {value}"


def extract_interfaces_from_unit(unit: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for match in INTERFACE_RE.finditer(str(unit or "")):
        interface = normalize_interface(match.group(1), match.group(2))
        if interface in seen:
            continue
        seen.add(interface)
        out.append(interface)
    return out


def build_interface_context_map(text: str, max_context_units: int = 6) -> dict[str, list[str]]:
    contexts: dict[str, list[str]] = {}
    active_interfaces: list[str] = []
    for unit in split_doc_units(text):
        interfaces = extract_interfaces_from_unit(unit)
        if interfaces:
            active_interfaces = interfaces
            for interface in interfaces:
                bucket = contexts.setdefault(interface, [])
                if unit not in bucket and len(bucket) < max_context_units:
                    bucket.append(unit)
            continue
        if not active_interfaces:
            continue
        for interface in active_interfaces:
            bucket = contexts.setdefault(interface, [])
            if unit not in bucket and len(bucket) < max_context_units:
                bucket.append(unit)
    return contexts


def extract_interface_changes(previous_text: str, current_text: str, limit: int = 8) -> list[dict[str, str]]:
    previous_map = build_interface_context_map(previous_text)
    current_map = build_interface_context_map(current_text)
    previous_keys = set(previous_map)
    current_keys = set(current_map)
    changes: list[dict[str, str]] = []

    for interface in sorted(current_keys - previous_keys):
        detail = next((unit for unit in current_map.get(interface, []) if unit != interface), "") or interface
        changes.append({"change_type": "新增接口", "interface": interface, "detail": compact(detail, 160)})
    for interface in sorted(previous_keys - current_keys):
        detail = next((unit for unit in previous_map.get(interface, []) if unit != interface), "") or interface
        changes.append({"change_type": "移除接口", "interface": interface, "detail": compact(detail, 160)})
    for interface in sorted(previous_keys & current_keys):
        previous_block = "\n".join(previous_map.get(interface, []))
        current_block = "\n".join(current_map.get(interface, []))
        if previous_block.casefold() == current_block.casefold():
            continue
        detail = extract_new_information(previous_block, current_block, limit=1)
        changes.append(
            {
                "change_type": "接口说明更新",
                "interface": interface,
                "detail": compact(detail[0] if detail else current_block, 160),
            }
        )
    return changes[: max(1, int(limit))]


def analyze_content_change(previous_text: str, current_text: str, mode: str) -> dict[str, Any]:
    new_information = extract_new_information(previous_text, current_text, limit=4)
    updated_interfaces = extract_interface_changes(previous_text, current_text, limit=8)
    return {
        "new_information": new_information,
        "updated_interfaces": updated_interfaces,
    }


def render_review_item_summary(item: dict[str, Any]) -> list[str]:
    parsed_trace = trace_token(str(item.get("parsed_file", "")).strip())
    lines = [
        f"## {item.get('id')}: {compact(str(item.get('title', '')), 120)}",
        f"- url: {item.get('url')}",
        f"- 解析留痕编号: {parsed_trace}",
    ]
    signals = item.get("signals") or []
    if isinstance(signals, list):
        for signal in signals[:3]:
            if not isinstance(signal, dict):
                continue
            lines.append(f"- {compact(str(signal.get('signal', '')), 80)}: {compact(str(signal.get('action', '')), 180)}")
    new_information = item.get("new_information") or []
    if isinstance(new_information, list) and new_information:
        lines.append("- 新增信息:")
        for info in new_information[:3]:
            lines.append(f"  - {compact(str(info), 180)}")
    updated_interfaces = item.get("updated_interfaces") or []
    if isinstance(updated_interfaces, list) and updated_interfaces:
        lines.append("- 接口更新:")
        for change in updated_interfaces[:5]:
            if not isinstance(change, dict):
                continue
            detail = compact(str(change.get("detail", "")).strip(), 120)
            base = f"  - {str(change.get('change_type', '')).strip()}: {str(change.get('interface', '')).strip()}"
            lines.append(f"{base} | {detail}" if detail else base)
    lines.append("")
    return lines


def load_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def resolve_previous_raw_file(current_raw_file: str) -> str:
    raw_path = Path(str(current_raw_file or "")).expanduser()
    if not raw_path.exists() or not raw_path.is_file():
        return ""
    try:
        current_resolved = raw_path.resolve()
    except Exception:
        current_resolved = raw_path
    candidates = sorted(path for path in raw_path.parent.glob("*.txt") if path.is_file())
    previous_candidates: list[Path] = []
    for candidate in candidates:
        try:
            candidate_resolved = candidate.resolve()
        except Exception:
            candidate_resolved = candidate
        if candidate_resolved == current_resolved:
            continue
        previous_candidates.append(candidate)
    earlier = [path for path in previous_candidates if path.name < raw_path.name]
    target = earlier[-1] if earlier else (previous_candidates[-1] if previous_candidates else None)
    return str(target) if target is not None else ""


def humanize_review_error(error_text: str) -> tuple[str, str]:
    text = compact(error_text, 220)
    lower = text.lower()
    if lower.startswith("parsed_dir_missing:"):
        detail = text.split(":", 1)[1].strip()
        return "解析结果目录缺失", detail or "未找到 parsed 目录"
    if lower.startswith("save_json_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "写入 JSON 失败", compact(detail or "报告写入失败", 180)
    if lower.startswith("save_text_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "写入文本失败", compact(detail or "摘要写入失败", 180)
    if lower.startswith("mode_invalid:"):
        detail = text.split(":", 1)[1].strip()
        return "复核模式无效", detail or "mode 参数不在允许范围内"
    return "复核失败", text or "未提供详细信息"


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-06",
        "updated_at": "",
        "modes": {
            "optimization": {
                "last_run_at": "",
                "last_report_file": "",
                "fingerprints": {},
            },
            "project-doc": {
                "last_run_at": "",
                "last_report_file": "",
                "fingerprints": {},
            },
        },
    }


def should_skip(last_run_at: str, min_interval_minutes: int, force: bool) -> bool:
    if force:
        return False
    dt = parse_iso(last_run_at)
    if dt is None:
        return False
    return (now() - dt) < timedelta(minutes=max(1, int(min_interval_minutes)))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_sources_map(path: Path, *, project_registry: Path | None = None) -> dict[str, dict[str, Any]]:
    items = load_runtime_sources(path, project_registry=project_registry)
    out: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(items):
        sid = str(item.get("id", "")).strip() or f"source-{idx+1}"
        out[sid] = item
    return out


def load_parsed_entries(parsed_dir: Path, limit: int) -> list[dict[str, Any]]:
    files = sorted(parsed_dir.glob("*.json"))
    if int(limit) > 0:
        files = files[: int(limit)]
    entries: list[dict[str, Any]] = []
    for path in files:
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        sid = str(payload.get("id", "")).strip()
        fingerprint = str(payload.get("fingerprint", "")).strip()
        if not sid or not fingerprint:
            continue
        payload["_file"] = str(path)
        entries.append(payload)
    return entries


def is_project_doc_entry(entry: dict[str, Any], sources_map: dict[str, dict[str, Any]]) -> bool:
    category = str(entry.get("category", "")).strip().lower()
    tags = {str(x).strip().lower() for x in (entry.get("tags") or []) if str(x).strip()}
    sid = str(entry.get("id", "")).strip()
    source_cfg = sources_map.get(sid) or {}
    src_category = str(source_cfg.get("category", "")).strip().lower()
    src_tags = {str(x).strip().lower() for x in (source_cfg.get("tags") or []) if str(x).strip()}

    combined_category = {category, src_category}
    combined_tags = tags | src_tags
    if any(x in PROJECT_DOC_CATEGORY_HINTS for x in combined_category if x):
        return True
    return any(x in PROJECT_DOC_TAG_HINTS for x in combined_tags if x)


def detect_signals(text: str, mode: str) -> list[dict[str, str]]:
    body = str(text or "").lower()
    found: list[dict[str, str]] = []
    for rule in SIGNAL_RULES:
        if re.search(rule["pattern"], body):
            action_key = "project_action" if mode == "project-doc" else "optimization_action"
            found.append(
                {
                    "signal": rule["title"],
                    "action": str(rule[action_key]),
                }
            )
    if found:
        return found
    if mode == "project-doc":
        return [{"signal": "常规文档更新", "action": "检查接口定义与示例代码是否需要同步，补最小回归测试。"}]
    return [{"signal": "常规信息更新", "action": "评估是否需要调整定时频率、上下文索引与执行流程。"}]


def build_output(
    *,
    mode: str,
    sender_identity: str,
    task_id: str,
    started_at: str,
    scanned: int,
    reviewed: int,
    changed: int,
    report_file: Path,
    sample_items: list[dict[str, Any]],
    follow_up_tasks: list[dict[str, Any]] | None = None,
    follow_up_errors: list[str] | None = None,
) -> str:
    extra_lines = [
        f"复核模式：{mode}",
        f"扫描文件：{int(scanned or 0)} 个",
        f"复核文件：{int(reviewed or 0)} 个",
        f"发生变更：{int(changed or 0)} 个",
    ]
    detail_lines: list[str] = []
    if sample_items:
        for idx, item in enumerate(sample_items[:8], start=1):
            sid = str(item.get("id", ""))
            title = compact(str(item.get("title", "")).strip() or sid, 80)
            detail_lines.append(f"复核重点{idx}：{sid}，标题 {title}")
    if follow_up_tasks:
        detail_lines.append(f"已派生后续任务：{len(follow_up_tasks)} 项")
        for idx, item in enumerate(follow_up_tasks[:8], start=1):
            detail_lines.append(
                f"后续任务{idx}：{item.get('task_id')} -> {item.get('assignee') or '-'}"
            )
    if follow_up_errors:
        detail_lines.append(f"后续建单失败：{len(follow_up_errors)} 项")
        for idx, item in enumerate(follow_up_errors[:8], start=1):
            detail_lines.append(f"建单异常{idx}：{item}")
    return render_chat_notice(
        "网页情报复核提醒",
        status="有更新" if int(changed or 0) > 0 else "需关注",
        task_id=task_id,
        sender_identity=sender_identity,
        run_time=started_at,
        trace_id=build_trace_id(report_file=report_file),
        summary=(
            f"网页情报复核已扫描 {int(scanned or 0)} 个文件，"
            f"完成 {int(reviewed or 0)} 个复核，发现 {int(changed or 0)} 个变更。"
        ),
        extra_lines=extra_lines,
        details=detail_lines,
        next_step="请按留痕编号查看复核报告，并确认是否进入后续任务处理。",
    )


def build_failure_output(
    *,
    mode: str,
    sender_identity: str,
    task_id: str,
    started_at: str,
    error_text: str,
) -> str:
    issue, detail = humanize_review_error(error_text)
    return render_chat_notice(
        "网页情报复核异常",
        status="需处理",
        task_id=task_id,
        sender_identity=sender_identity,
        run_time=started_at,
        summary="网页情报复核器入口运行失败。",
        extra_lines=[f"复核模式：{mode}"],
        details=[
            "问题：复核器入口异常",
            f"详情：{issue}：{detail}",
        ],
        next_step="请先检查解析目录和复核输入，再重新执行复核任务。",
    )


def default_follow_up_assignee(mode: str) -> str:
    return "project-agent" if mode == "project-doc" else "optimization-agent"


def create_review_follow_up_tasks(
    *,
    db_path: Path,
    mode: str,
    assignee: str,
    actor: str,
    report_file: Path,
    review_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    created: list[dict[str, Any]] = []
    errors: list[str] = []
    task_type = "web_intel_review_project_doc" if mode == "project-doc" else "web_intel_review_optimization"
    priority = "medium" if mode == "project-doc" else "low"
    pool = "todo"

    for item in review_items:
        sid = str(item.get("id", "")).strip() or "source"
        fingerprint = str(item.get("fingerprint", "")).strip() or "nofp"
        task_id = f"todo-web-intel-review-{mode}-{sid}-{fingerprint[:10]}"
        title = str(item.get("title", "")).strip() or sid
        url = str(item.get("url", "")).strip()
        parsed_file = str(item.get("parsed_file", "")).strip()
        parsed_trace = trace_token(parsed_file)
        report_trace = trace_token(report_file)
        signals = item.get("signals") or []
        signal_lines: list[str] = []
        if isinstance(signals, list):
            for signal in signals[:8]:
                if not isinstance(signal, dict):
                    continue
                signal_name = compact(str(signal.get("signal", "")).strip(), 80)
                signal_action = compact(str(signal.get("action", "")).strip(), 180)
                signal_lines.append(f"- {signal_name}: {signal_action}")
        if not signal_lines:
            signal_lines.append("- 常规更新: 请根据文档变化给出最小可执行方案")
        change_lines: list[str] = []
        new_information = item.get("new_information") or []
        if isinstance(new_information, list):
            for info in new_information[:3]:
                change_lines.append(f"- 新增信息: {compact(str(info), 180)}")
        updated_interfaces = item.get("updated_interfaces") or []
        if isinstance(updated_interfaces, list):
            for change in updated_interfaces[:5]:
                if not isinstance(change, dict):
                    continue
                change_lines.append(
                    f"- 接口更新: {compact(str(change.get('change_type', '')), 40)} {compact(str(change.get('interface', '')), 120)}"
                )

        requirement = "\n".join(
            [
                f"复核模式：{mode}",
                f"来源编号：{sid}",
                f"标题：{title}",
                f"来源地址：{url or '-'}",
                f"解析留痕编号：{parsed_trace}",
                f"运行留痕编号：{report_trace}",
                "",
                "检测到的信号与动作建议:",
                *signal_lines,
                *(["", "结构化变化摘录:", *change_lines] if change_lines else []),
                "",
                "要求：",
                "1. 先读取证据文件与当前实现，确认变更影响面。",
                "2. 若任务清晰，直接给出修复/更新方案并执行；若不清晰，再转给规划者。",
                "3. 完成后至少重跑一次相关脚本或验证命令，确认结果闭环。",
            ]
        )
        acceptance = "任务结论可追溯到运行留痕和解析留痕，并附最小验证结果。"
        signal_summary = ", ".join(
            compact(str(signal.get("signal", "")).strip(), 40)
            for signal in signals
            if isinstance(signal, dict) and str(signal.get("signal", "")).strip()
        ) or "doc-change"
        context_payload = {
            "problem": f"{sid} 复核发现更新：{signal_summary}",
            "location": url or sid,
            "first_seen_at": str(item.get("fetched_at", "")).strip() or now_iso(),
            "impact": signal_summary,
            "evidence": f"运行留痕编号：{report_trace}；解析留痕编号：{parsed_trace}",
            "current_state": f"{sid} 已检测到复核信号，但尚未完成同步处理",
            "expected_state": "相关文档变化已被吸收为可执行方案并完成必要同步。",
            "operation_path": f"web_intel_review_runner::{mode}::{sid}",
            "reproduction_steps": "先查看运行留痕和解析留痕，再根据信号执行最小变更并复验。",
            "scope": f"网页情报复核 mode={mode}, source={sid}",
            "constraints": "优先最小改动；若任务边界不清晰，先交给规划者再继续执行。",
            "acceptance_criteria": acceptance,
            "full_background": requirement,
        }
        create_args = [
            "create-task",
            "--task-id",
            task_id,
            "--task-type",
            task_type,
            "--reason",
            f"[WEB_INTEL_REVIEW] {mode} {sid}",
            "--source",
            actor,
            "--request-source",
            "ai",
            "--priority",
            priority,
            "--risk-level",
            "low",
            "--pool",
            pool,
            "--assignee",
            assignee,
            "--need-human-confirm",
            "false",
            "--human-confirmed",
            "true",
            "--context-json",
            json.dumps(context_payload, ensure_ascii=False),
            "--requirement",
            requirement,
            "--result-output",
            "相关文档变化已被吸收为可执行方案，必要的代码/配置/流程已同步更新。",
            "--acceptance",
            acceptance,
            "--observable-outputs",
            f"运行留痕编号={report_trace},解析留痕编号={parsed_trace},source_id={sid}",
            "--acceptance-thresholds",
            "至少包含影响分析、执行结果、验证命令；若不能自动解决，需要明确阻断原因。",
            "--scheduled-at",
            now_iso(),
            "--actor",
            actor,
        ]
        extend_create_task_args_with_constraints(create_args, assignee)
        ok, payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
        if ok:
            created.append(
                {
                    "task_id": task_id,
                    "assignee": assignee,
                    "status": "created",
                    "source_id": sid,
                }
            )
            continue
        if "task_id already exists" in err:
            created.append(
                {
                    "task_id": task_id,
                    "assignee": assignee,
                    "status": "existing",
                    "source_id": sid,
                }
            )
            continue
        payload_error = str(payload.get("error", "")).strip() if isinstance(payload, dict) else ""
        errors.append(f"{sid}:{err or payload_error or 'create_follow_up_task_failed'}")
    return created, errors


def cli_flag_enabled(flag: str) -> bool:
    return str(flag or "").strip() in {str(part).strip() for part in sys.argv[1:]}


def cli_flag_value(flag: str, default: str = "") -> str:
    parts = sys.argv[1:]
    for idx, part in enumerate(parts):
        if part == flag and idx + 1 < len(parts):
            return str(parts[idx + 1]).strip()
        if part.startswith(flag + "="):
            return str(part.split("=", 1)[1]).strip()
    return default


def main() -> None:
    home = Path(os.path.expanduser("~")).resolve()
    parser = argparse.ArgumentParser(description="Review parsed web intelligence outputs")
    parser.add_argument("--mode", default="optimization", choices=sorted(MODES))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--parsed-dir", default="")
    parser.add_argument("--summary-dir", default="")
    parser.add_argument("--sources-file", default="")
    parser.add_argument("--project-registry", default="")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default="")
    parser.add_argument("--assignee", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--notify-on", default="change", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--min-interval-minutes", type=int, default=180)
    parser.add_argument("--max-items", type=int, default=120)
    parser.add_argument("--create-follow-up-tasks", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    mode = str(args.mode).strip()
    openclaw_home = Path(args.openclaw_home).expanduser().resolve()
    ops_home = openclaw_home / "ops"
    web_home = openclaw_home / "web"

    parsed_dir = Path(args.parsed_dir).expanduser() if str(args.parsed_dir).strip() else (web_home / "parsed")
    summary_dir = Path(args.summary_dir).expanduser() if str(args.summary_dir).strip() else (web_home / "summary")
    sources_file = (
        Path(args.sources_file).expanduser()
        if str(args.sources_file).strip()
        else (
            (ops_home / "web" / "project_docs_sources.json")
            if mode == "project-doc"
            else (ops_home / "web" / "sources.json")
        )
    )
    project_registry = (
        Path(args.project_registry).expanduser()
        if str(args.project_registry).strip()
        else (ops_home / "task-center" / "project-registry.json")
    )
    state_file = (
        Path(args.state_file).expanduser()
        if str(args.state_file).strip()
        else (ops_home / "web-intel" / "review-state.json")
    )
    report_dir = (
        Path(args.report_dir).expanduser()
        if str(args.report_dir).strip()
        else (ops_home / "web-intel" / "review-reports")
    )
    db_path = Path(args.db).expanduser() if str(args.db).strip() else (ops_home / "task-center" / "task_center.db")
    task_id = str(args.task_id).strip() or (
        "cron:web-intel-review-project-doc" if mode == "project-doc" else "cron:web-intel-review-optimization"
    )
    sender_identity = normalize_sender_identity(args.sender_identity, mode)
    follow_up_assignee = str(args.assignee).strip() or default_follow_up_assignee(mode)
    log_mode = normalize_log_mode(args.normal_log_mode)

    for p in (parsed_dir, summary_dir, state_file.parent, report_dir):
        ensure_dir(p)

    state = load_json(state_file, state_default())
    if not isinstance(state, dict):
        state = state_default()
    modes = state.get("modes")
    if not isinstance(modes, dict):
        modes = state_default()["modes"]
        state["modes"] = modes
    mode_state = modes.get(mode)
    if not isinstance(mode_state, dict):
        mode_state = {"last_run_at": "", "last_report_file": "", "fingerprints": {}}
        modes[mode] = mode_state
    fingerprints = mode_state.get("fingerprints")
    if not isinstance(fingerprints, dict):
        fingerprints = {}
        mode_state["fingerprints"] = fingerprints

    if should_skip(str(mode_state.get("last_run_at", "")), int(args.min_interval_minutes), bool(args.force)):
        payload = {"ok": True, "notify": False, "output": "NO_REPLY", "reason": "min_interval_not_reached"}
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print("NO_REPLY")
        return

    sources_map = load_sources_map(
        sources_file,
        project_registry=(project_registry if project_registry.exists() else None),
    )
    entries = load_parsed_entries(parsed_dir, int(args.max_items))
    scanned = len(entries)
    if mode == "project-doc":
        entries = [entry for entry in entries if is_project_doc_entry(entry, sources_map)]
    reviewed = len(entries)

    changed_entries: list[dict[str, Any]] = []
    for entry in entries:
        sid = str(entry.get("id", "")).strip()
        fp = str(entry.get("fingerprint", "")).strip()
        if not sid or not fp:
            continue
        if (not bool(args.force)) and str(fingerprints.get(sid, "")) == fp:
            continue
        changed_entries.append(entry)

    review_items: list[dict[str, Any]] = []
    for entry in changed_entries:
        sid = str(entry.get("id", "")).strip()
        fp = str(entry.get("fingerprint", "")).strip()
        text = str(entry.get("text_excerpt", "") or "")
        raw_file = str(entry.get("raw_file", "")).strip()
        previous_raw_file = resolve_previous_raw_file(raw_file)
        current_text = normalize_doc_text(load_text_file(Path(raw_file))) if raw_file else normalize_doc_text(text)
        previous_text = normalize_doc_text(load_text_file(Path(previous_raw_file))) if previous_raw_file else ""
        change_details = analyze_content_change(previous_text, current_text, mode)
        signals = detect_signals(text, mode)
        review_items.append(
            {
                "id": sid,
                "fingerprint": fp,
                "title": str(entry.get("title", "")).strip() or sid,
                "url": str(entry.get("url", "")).strip(),
                "category": str(entry.get("category", "")).strip(),
                "tags": list(entry.get("tags") or []),
                "parsed_file": str(entry.get("_file", "")),
                "raw_file": raw_file,
                "previous_raw_file": previous_raw_file,
                "signals": signals,
                "new_information": change_details.get("new_information", []),
                "updated_interfaces": change_details.get("updated_interfaces", []),
                "fetched_at": str(entry.get("fetched_at", "")),
            }
        )
        fingerprints[sid] = fp

    mode_state["last_run_at"] = now_iso()
    state["updated_at"] = now_iso()

    report_payload = {
        "ok": True,
        "mode": mode,
        "task": task_id,
        "sender_identity": sender_identity,
        "generated_at": now_iso(),
        "sources_file": str(sources_file),
        "counts": {
            "scanned_files": scanned,
            "reviewed_files": reviewed,
            "changed_files": len(changed_entries),
            "suggestions": sum(len(x.get("signals", [])) for x in review_items),
        },
        "items": review_items,
    }
    report_file = report_dir / f"web_review_{mode}_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}.json"
    save_json(report_file, report_payload)
    follow_up_tasks: list[dict[str, Any]] = []
    follow_up_errors: list[str] = []
    if bool(args.create_follow_up_tasks) and review_items:
        follow_up_tasks, follow_up_errors = create_review_follow_up_tasks(
            db_path=db_path,
            mode=mode,
            assignee=follow_up_assignee,
            actor=sender_identity,
            report_file=report_file,
            review_items=review_items,
        )
        for item in review_items:
            sid = str(item.get("id", "")).strip()
            task_row = next((x for x in follow_up_tasks if str(x.get("source_id", "")).strip() == sid), None)
            if task_row:
                item["follow_up_task_id"] = str(task_row.get("task_id", "")).strip()
                item["follow_up_status"] = str(task_row.get("status", "")).strip()
        report_payload["follow_up_tasks"] = follow_up_tasks
        report_payload["follow_up_errors"] = follow_up_errors
        save_json(report_file, report_payload)
    mode_state["last_report_file"] = str(report_file)
    save_json(state_file, state)

    started_at = now_iso()
    output = build_output(
        mode=mode,
        sender_identity=sender_identity,
        task_id=task_id,
        started_at=started_at,
        scanned=scanned,
        reviewed=reviewed,
        changed=len(changed_entries),
        report_file=report_file,
        sample_items=review_items,
        follow_up_tasks=follow_up_tasks,
        follow_up_errors=follow_up_errors,
    )
    summary_file = summary_dir / f"latest_review_{mode}.md"
    summary_lines = [output]
    if review_items:
        summary_lines.append("")
        summary_lines.append("复核重点明细")
        for idx, item in enumerate(review_items[:24], start=1):
            sid = str(item.get("id", "")).strip() or "-"
            title = compact(str(item.get("title", "")).strip() or sid, 120)
            summary_lines.append(f"- 重点{idx}：{sid}，标题 {title}")
    save_text(summary_file, "\n".join(summary_lines).strip() + "\n")
    quiet_no_reply = should_quiet(log_mode, str(args.notify_on), changed_count=len(changed_entries))
    output_text = "NO_REPLY" if quiet_no_reply else output
    response_payload = {
        "ok": True,
        "notify": (not quiet_no_reply),
        "output": output_text,
        "report_file": str(report_file),
        "summary_file": str(summary_file),
        "state_file": str(state_file),
        "follow_up_tasks": follow_up_tasks,
        "follow_up_errors": follow_up_errors,
    }
    if bool(args.emit_json):
        print(json.dumps(response_payload, ensure_ascii=False))
    else:
        print(output_text)


def run_cli() -> int:
    try:
        main()
        return 0
    except Exception as exc:
        mode = cli_flag_value("--mode", "optimization") or "optimization"
        task_id = cli_flag_value(
            "--task-id",
            "cron:web-intel-review-project-doc" if mode == "project-doc" else "cron:web-intel-review-optimization",
        )
        sender_identity = normalize_sender_identity(cli_flag_value("--sender-identity", ""), mode)
        output = build_failure_output(
            mode=mode,
            sender_identity=sender_identity,
            task_id=task_id,
            started_at=now_iso(),
            error_text=str(exc),
        )
        payload = {
            "ok": False,
            "notify": True,
            "output": output,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if cli_flag_enabled("--emit-json"):
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(output)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

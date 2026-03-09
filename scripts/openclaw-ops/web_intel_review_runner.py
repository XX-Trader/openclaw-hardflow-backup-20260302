#!/usr/bin/env python3
"""Review web intelligence outputs for optimization-agent / project-agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic  # type: ignore
from web_sources_runtime import load_runtime_sources  # type: ignore

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
) -> str:
    lines = [
        "网页情报复核",
        f"- 模式: {mode}",
        f"- 任务: {task_id}",
        f"- 时间: {started_at}",
        f"- 汇总: 扫描文件={scanned}，复核文件={reviewed}，发生变更={changed}",
        f"- 报告文件: {report_file}",
    ]
    if sample_items:
        lines.append("- 复核重点:")
        for item in sample_items[:8]:
            sid = str(item.get("id", ""))
            title = compact(str(item.get("title", "")).strip() or sid, 80)
            lines.append(f"  - {sid}: {title}")
    return "\n".join(lines)


def build_failure_output(
    *,
    mode: str,
    sender_identity: str,
    task_id: str,
    started_at: str,
    error_text: str,
) -> str:
    issue, detail = humanize_review_error(error_text)
    lines = [
        "网页情报复核异常",
        f"- 模式: {mode}",
        f"- 任务: {task_id}",
        f"- 时间: {started_at}",
        "- 问题: 复核器入口异常",
        f"- 详情: {issue}：{detail}",
    ]
    return "\n".join(lines)


def follow_up_lines(tasks: list[dict[str, Any]]) -> list[str]:
    if not tasks:
        return []
    lines = ["- 已派生后续任务:"]
    for item in tasks[:8]:
        task_id = str(item.get("task_id", "")).strip() or "-"
        assignee = str(item.get("assignee", "")).strip() or "-"
        status = str(item.get("status", "")).strip() or "created"
        lines.append(f"  - {task_id} -> {assignee} ({status})")
    return lines


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

        requirement = "\n".join(
            [
                f"web-intel review mode: {mode}",
                f"source_id: {sid}",
                f"title: {title}",
                f"url: {url}",
                f"parsed_file: {parsed_file}",
                f"report_file: {report_file}",
                "",
                "检测到的信号与动作建议:",
                *signal_lines,
                "",
                "要求：",
                "1. 先读取证据文件与当前实现，确认变更影响面。",
                "2. 若任务清晰，直接给出修复/更新方案并执行；若不清晰，再转给规划者。",
                "3. 完成后至少重跑一次相关脚本或验证命令，确认结果闭环。",
            ]
        )
        acceptance = "任务结论可追溯到 report_file/parsed_file，并附最小验证结果。"
        signal_summary = ", ".join(
            compact(str(signal.get("signal", "")).strip(), 40)
            for signal in signals
            if isinstance(signal, dict) and str(signal.get("signal", "")).strip()
        ) or "doc-change"
        context_payload = {
            "problem": f"{sid} review detected update: {signal_summary}",
            "location": url or parsed_file or sid,
            "first_seen_at": str(item.get("fetched_at", "")).strip() or now_iso(),
            "impact": signal_summary,
            "evidence": ",".join(x for x in [str(report_file), parsed_file] if x),
            "current_state": f"review signal detected for {sid}, not yet applied",
            "expected_state": "相关文档变化已被吸收为可执行方案并完成必要同步。",
            "operation_path": f"web_intel_review_runner::{mode}::{sid}",
            "reproduction_steps": f"查看 {parsed_file} 与 {report_file}，根据信号执行最小变更并复验。",
            "scope": f"web-intel review mode={mode}, source={sid}",
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
            f"report_file={report_file},parsed_file={parsed_file},source_id={sid}",
            "--acceptance-thresholds",
            "至少包含影响分析、执行结果、验证命令；若不能自动解决，需要明确阻断原因。",
            "--scheduled-at",
            now_iso(),
            "--actor",
            actor,
        ]
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
                "signals": signals,
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

    summary_file = summary_dir / f"latest_review_{mode}.md"
    summary_lines = [
        f"# web-intel-review ({mode})",
        "",
        f"- task: {task_id}",
        f"- sender_identity: {sender_identity}",
        f"- generated_at: {now_iso()}",
        f"- report_file: {report_file}",
        "",
    ]
    for item in review_items[:24]:
        summary_lines.append(f"## {item.get('id')}: {compact(str(item.get('title', '')), 120)}")
        summary_lines.append(f"- url: {item.get('url')}")
        summary_lines.append(f"- parsed_file: {item.get('parsed_file')}")
        signals = item.get("signals") or []
        if isinstance(signals, list):
            for signal in signals[:3]:
                if not isinstance(signal, dict):
                    continue
                summary_lines.append(
                    f"- {compact(str(signal.get('signal', '')), 80)}: {compact(str(signal.get('action', '')), 180)}"
                )
        summary_lines.append("")
    save_text(summary_file, "\n".join(summary_lines).strip() + "\n")

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
    )
    extra_lines = follow_up_lines(follow_up_tasks)
    if follow_up_errors:
        extra_lines.append("- 建单失败:")
        for item in follow_up_errors[:8]:
            extra_lines.append(f"  - {item}")
    if extra_lines:
        output = output + "\n" + "\n".join(extra_lines)
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

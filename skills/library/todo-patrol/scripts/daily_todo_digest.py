#!/usr/bin/env python3
"""Daily TODO/DONE digest (no external push, only chat output)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
from io_write_gateway import FileWriteError, write_json_atomic
from chat_output import build_trace_id, render_chat_notice, strip_list_marker

configure_process_utf8_stdio()

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "ops-agent/daily-todo-digest"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def policy_enforcer_path() -> Path:
    custom = str(os.environ.get("POLICY_ENFORCER_PY", "")).strip()
    if custom:
        return Path(custom).expanduser()
    return Path(__file__).resolve().parent / "policy" / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized_id = str(task_id or "").strip()
    if not normalized_id or (not db_path.exists()):
        return False
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized_id,)).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "ops-agent").strip() or "ops-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "ops-agent"
    source_name = str(source_module or "ops-agent/daily-todo-digest").strip() or "ops-agent/daily-todo-digest"
    create_args = [
        "create-task",
        "--task-id",
        normalized,
        "--task-type",
        "ops_runtime_cron",
        "--reason",
        f"[CRON_RUNTIME] bind {normalized}",
        "--source",
        source_name,
        "--request-source",
        "ai",
        "--priority",
        "low",
        "--risk-level",
        "low",
        "--pool",
        "jobs",
        "--assignee",
        assignee,
        "--need-human-confirm",
        "false",
        "--human-confirmed",
        "true",
        "--requirement",
        f"Auto register runtime task for {normalized} to bind observability records.",
        "--result-output",
        "Runtime task exists and accepts module/communication/report records.",
        "--acceptance",
        "Task can be used for cron observability binding without manual action.",
        "--observable-outputs",
        "module_logs,module_communications,agent_task_reports,planner_summary",
        "--acceptance-thresholds",
        "At least one runtime observability record is bound to this task.",
        "--scheduled-at",
        now_iso(),
        "--actor",
        actor_name,
    ]
    ok, _payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
    if ok and task_exists_in_db(db_path, normalized):
        return normalized, ""
    return "", (err or f"auto_register_task_failed:{normalized}")


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


def default_state() -> dict[str, Any]:
    return {
        "updated_at": "",
        "sent_todo_ids": [],
        "sent_done_ids": [],
        "last_report_file": "",
    }


def is_today_local(iso_text: str) -> bool:
    text = str(iso_text or "").strip()
    if not text:
        return False
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        dt = dt.astimezone(TZ)
        return dt.date() == now().date()
    except Exception:
        return False


def load_tasks(db_path: Path, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = conn.execute(
            """
            SELECT
              task_id,
              task_type,
              reason,
              priority,
              risk_level,
              assignee,
              status,
              requirement,
              result_output,
              acceptance,
              retry_count,
              failure_count,
              scheduled_at,
              created_at,
              updated_at
            FROM tasks
            ORDER BY
              CASE
                WHEN LOWER(status) IN ('pending', 'running', 'failed', 'escalated') THEN
                  CASE
                    WHEN scheduled_at IS NULL OR TRIM(scheduled_at) = '' OR scheduled_at <= ? THEN 0
                    ELSE 1
                  END
                ELSE 2
              END ASC,
              COALESCE(NULLIF(TRIM(scheduled_at), ''), created_at) ASC,
              updated_at DESC
            LIMIT ?
            """,
            (now_utc_iso, max(1, int(limit))),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def is_runtime_binding_task(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if str(item.get("task_type", "")).strip().lower() == "ops_runtime_cron":
        return True
    return str(item.get("reason", "")).strip().startswith("[CRON_RUNTIME] bind ")


def split_compact_text_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    normalized = raw.replace("\r", "\n")
    line_parts = [part.strip() for part in normalized.split("\n") if part.strip()]
    if len(line_parts) > 1:
        return line_parts
    if "," in raw:
        comma_parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(comma_parts) > 1:
            return comma_parts
    return [raw]


def load_latest_agent_reports(db_path: Path, task_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
    if (not normalized_ids) or (not db_path.exists()):
        return {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        table_exists = conn.execute(
            "SELECT 1 AS ok FROM sqlite_master WHERE type = 'table' AND name = 'agent_task_reports'"
        ).fetchone()
        if not table_exists:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM agent_task_reports
            WHERE task_id IN ({placeholders})
            ORDER BY task_id ASC, ts DESC, id DESC
            """,
            normalized_ids,
        ).fetchall()
        latest_reports: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            task_id = str(item.get("task_id", "")).strip()
            if (not task_id) or task_id in latest_reports:
                continue
            item["failed_items"] = split_compact_text_list(item.get("failed_items", ""))
            item["resolved_issues"] = split_compact_text_list(item.get("resolved_issues", ""))
            latest_reports[task_id] = item
        return latest_reports
    except Exception:
        return {}
    finally:
        if conn is not None:
            conn.close()


def attach_latest_agent_reports(items: list[dict[str, Any]], latest_reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not items or not latest_reports:
        return items
    enriched: list[dict[str, Any]] = []
    for item in items:
        cloned = dict(item)
        task_id = str(cloned.get("task_id", "")).strip()
        if task_id and task_id in latest_reports:
            cloned["latest_report"] = dict(latest_reports[task_id])
        enriched.append(cloned)
    return enriched


def compact_task_text(value: Any, max_len: int = 88) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def priority_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 3


def risk_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 3


def status_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized in {"failed", "escalated"}:
        return 0
    if normalized == "running":
        return 1
    if normalized == "pending":
        return 2
    if normalized == "passed":
        return 3
    return 4


def pick_focus_todo_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        ranked.append(
            (
                status_rank(item.get("status", "")),
                priority_rank(item.get("priority", "")),
                risk_rank(item.get("risk_level", "")),
                idx,
                item,
            )
        )
    ranked.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return [item for _status, _priority, _risk, _idx, item in ranked[: max(1, int(limit))]]


def format_duration_ms_human(value: Any) -> str:
    duration_ms = max(0, int(value or 0))
    if duration_ms <= 0:
        return "未记录"
    if duration_ms < 1000:
        return f"{duration_ms}毫秒"
    duration_sec = duration_ms / 1000.0
    if duration_sec < 60:
        if abs(duration_sec - round(duration_sec)) < 0.05:
            return f"{int(round(duration_sec))}秒"
        return f"{duration_sec:.1f}秒"
    minutes = int(duration_sec // 60)
    remain_sec = duration_sec - (minutes * 60)
    if abs(remain_sec - round(remain_sec)) < 0.05:
        remain_text = f"{int(round(remain_sec))}秒"
    else:
        remain_text = f"{remain_sec:.1f}秒"
    if remain_sec <= 0.05:
        return f"{minutes}分"
    return f"{minutes}分{remain_text}"


def format_cost_estimate(value: Any) -> str:
    try:
        cost_value = float(value or 0.0)
    except Exception:
        cost_value = 0.0
    if cost_value <= 0:
        return "未记录"
    return f"${cost_value:.6f}"


def build_failure_reason_text(item: dict[str, Any]) -> str:
    latest_report = item.get("latest_report", {})
    latest_report = latest_report if isinstance(latest_report, dict) else {}
    failed_items = split_compact_text_list(latest_report.get("failed_items", []))
    if failed_items:
        return compact_task_text(failed_items[0], 96)
    resolution_summary = compact_task_text(latest_report.get("resolution_summary", ""), 96)
    if resolution_summary:
        return resolution_summary
    raw_status = str(item.get("status", "")).strip().lower()
    if raw_status == "escalated":
        return "自动执行未闭环，当前需要人工介入。"
    if raw_status == "failed":
        return "执行失败，详细失败原因未留痕。"
    return ""


def build_failure_metrics_line(index: int, item: dict[str, Any]) -> str:
    raw_status = str(item.get("status", "")).strip().lower()
    if raw_status not in {"failed", "escalated"}:
        return ""
    latest_report = item.get("latest_report", {})
    latest_report = latest_report if isinstance(latest_report, dict) else {}
    failure_count = max(
        0,
        int(item.get("failure_count", 0) or 0),
        int(latest_report.get("failure_count", 0) or 0),
    )
    retry_count = max(0, int(item.get("retry_count", 0) or 0))
    duration_text = format_duration_ms_human(latest_report.get("duration_ms", 0))
    parts = [
        f"原因={build_failure_reason_text(item) or '未记录'}",
        f"失败次数={max(1, failure_count)}次",
        f"最近耗时={duration_text}",
    ]
    if retry_count > 0:
        parts.append(f"已重试={retry_count}次")
    return f"失败信息{index}：" + "；".join(parts)


def build_execution_metrics_line(index: int, item: dict[str, Any]) -> str:
    raw_status = str(item.get("status", "")).strip().lower()
    if raw_status not in {"failed", "escalated"}:
        return ""
    latest_report = item.get("latest_report", {})
    latest_report = latest_report if isinstance(latest_report, dict) else {}
    model_id = compact_task_text(str(latest_report.get("model_id", "")).replace("/", " · "), 48) or "未记录"
    input_tokens = max(0, int(latest_report.get("input_tokens", 0) or 0))
    output_tokens = max(0, int(latest_report.get("output_tokens", 0) or 0))
    total_tokens = max(0, int(latest_report.get("total_tokens", 0) or 0))
    if total_tokens <= 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    cost_text = format_cost_estimate(latest_report.get("cost_estimate", 0))
    if model_id == "未记录" and total_tokens <= 0 and cost_text == "未记录":
        return ""
    token_text = f"总={total_tokens}（输入={input_tokens}，输出={output_tokens}）" if total_tokens > 0 else "未记录"
    return f"执行概况{index}：模型={model_id}；tokens={token_text}；成本≈{cost_text}"


def build_focus_task_subject(item: dict[str, Any]) -> str:
    reason = compact_task_text(item.get("reason", ""), 72)
    requirement = compact_task_text(item.get("requirement", ""), 72)
    if reason and ("task_id=" not in reason) and ("assignee=" not in reason) and ("|" not in reason):
        return reason
    if requirement:
        return requirement
    if reason:
        return reason
    task_label = str(item.get("task_id", "")).strip()
    return task_label or "未命名任务"


def build_focus_task_requirement(item: dict[str, Any]) -> str:
    requirement = compact_task_text(item.get("requirement", ""), 92)
    acceptance = compact_task_text(item.get("acceptance", ""), 64)
    if requirement and acceptance:
        return f"{requirement} 验收：{acceptance}"
    if requirement:
        return requirement
    if acceptance:
        return f"验收：{acceptance}"
    reason = compact_task_text(item.get("reason", ""), 92)
    return reason or "未补充明确要求"


def humanize_task_status(item: dict[str, Any]) -> str:
    priority = str(item.get("priority", "")).strip() or "-"
    risk_level = str(item.get("risk_level", "")).strip() or "-"
    assignee = str(item.get("assignee", "")).strip() or "未分配"
    raw_status = str(item.get("status", "")).strip().lower()
    if raw_status == "pending":
        status_label = "任务中心待处理"
    elif raw_status == "running":
        status_label = "任务中心进行中"
    elif raw_status == "failed":
        status_label = "任务中心执行失败"
    elif raw_status == "escalated":
        status_label = "任务中心待人工介入"
    elif raw_status == "passed":
        status_label = "任务中心已完成"
    else:
        status_label = "任务中心状态待确认"
    return f"{status_label}（优先级={priority}，风险={risk_level}，负责人={assignee}）"


def explain_task_value(index: int, item: dict[str, Any], has_exceptions: bool) -> str:
    raw_status = str(item.get("status", "")).strip().lower()
    priority = str(item.get("priority", "")).strip().lower()
    risk_level = str(item.get("risk_level", "")).strip().lower()
    if raw_status in {"failed", "escalated"}:
        return "这项已经失败或升级，不先处理会继续阻塞后续推进。"
    if priority == "high" or risk_level == "high":
        return "这项属于高优先级或高风险事项，拖延会继续积压。"
    if raw_status == "running":
        return "这项已经在执行中，及时跟进能避免任务卡住。"
    if has_exceptions and index == 1:
        return "异常收口后，这项最适合作为今天的第一顺位推进。"
    return "这是今天新增待办里最值得先确认的一项。"


def humanize_chat_error(reason: str) -> str:
    raw = str(reason or "").strip()
    if not raw:
        return "未知异常"
    if raw.startswith("webhook_missing:"):
        detail = raw.split(":", 1)[1].strip() or raw
        env_name = detail.split(";", 1)[0].strip() or detail
        return f"钉钉 Webhook 未配置：{env_name}"
    if raw.startswith("dingtalk_post_failed:"):
        detail = raw.split(":", 1)[1].strip() or raw
        return f"钉钉发送失败：{detail}"
    if raw.startswith("policy_enforcer_failed:"):
        detail = raw.split(":", 1)[1].strip() or raw
        return f"策略记录失败：{detail}"
    return raw


def build_digest_judgement(new_todo: list[dict[str, Any]], new_done: list[dict[str, Any]], reasons: list[str]) -> str:
    if reasons and new_todo:
        return "异常优先，先收口运行问题，再确认新增待办是否需要人工接管。"
    if reasons:
        return "先处理异常，再决定今天是否需要补发通知。"
    if new_todo:
        high_priority_count = sum(
            1
            for item in new_todo
            if str(item.get("priority", "")).strip().lower() == "high"
            or str(item.get("risk_level", "")).strip().lower() == "high"
        )
        if high_priority_count > 0:
            return f"今天新增待办里有 {high_priority_count} 项高优先级事项，建议先看前排任务。"
        return "今天新增待办不算少，先确认优先级再安排推进顺序。"
    if new_done:
        return "今天以完成项复核为主，确认是否还有收尾动作。"
    return ""


def append_focus_task_details(detail_lines: list[str], items: list[dict[str, Any]], has_exceptions: bool) -> None:
    for idx, item in enumerate(items, start=1):
        detail_lines.append(f"任务{idx}：{build_focus_task_subject(item)}")
        detail_lines.append(f"要求{idx}：{build_focus_task_requirement(item)}")
        detail_lines.append(f"状态{idx}：{humanize_task_status(item)}")
        failure_line = build_failure_metrics_line(idx, item)
        if failure_line:
            detail_lines.append(failure_line)
        execution_line = build_execution_metrics_line(idx, item)
        if execution_line:
            detail_lines.append(execution_line)
        detail_lines.append(f"值得做{idx}：{explain_task_value(idx, item, has_exceptions)}")


def summarize_completed_items(items: list[dict[str, Any]], limit: int) -> list[str]:
    lines: list[str] = []
    for idx, item in enumerate(items[: max(1, int(limit))], start=1):
        subject = build_focus_task_subject(item)
        lines.append(f"完成{idx}：{subject}（任务中心已完成，可复核交付质量）")
    return lines


def build_chat_output(
    *,
    sender_identity: str,
    task_id: str,
    run_time: str,
    run_id: str,
    new_todo: list[dict[str, Any]],
    new_done: list[dict[str, Any]],
    planner_summary: dict[str, Any] | None,
    exception_reasons: list[str],
    max_notify_items: int,
) -> str:
    reasons = [str(reason).strip() for reason in exception_reasons if str(reason).strip()]
    has_updates = bool(new_todo or new_done)
    has_exceptions = bool(reasons)
    if (not has_updates) and (not has_exceptions):
        return "NO_REPLY"

    focus_items = pick_focus_todo_items(new_todo, min(int(max_notify_items), 3)) if new_todo else []
    title = "每日任务摘要需关注" if has_updates and has_exceptions else ("每日任务摘要" if has_updates else "每日任务摘要异常")
    status = "需处理" if has_exceptions else ("需跟进" if new_todo else "已汇报")
    summary_parts: list[str] = []
    judgement = build_digest_judgement(new_todo, new_done, reasons)
    if judgement:
        summary_parts.append(judgement)
    if new_todo:
        summary_parts.append(f"新增待办 {len(new_todo)} 项")
    if new_done:
        summary_parts.append(f"新增完成 {len(new_done)} 项")
    if has_exceptions:
        summary_parts.append(f"发现 {len(reasons)} 个运行异常")

    extra_lines: list[str] = []
    if judgement:
        extra_lines.append(f"人工判断：{judgement}")
    if has_updates:
        extra_lines.append(f"待办变化：新增待办 {len(new_todo)} 项，新增完成 {len(new_done)} 项。")
    if isinstance(planner_summary, dict) and planner_summary:
        extra_lines.append(
            "近24小时处理："
            f"任务 {int(planner_summary.get('task_count', 0) or 0)} 项，"
            f"已解决 {int(planner_summary.get('resolved_task_count', 0) or 0)} 项，"
            f"失败 {int(planner_summary.get('failed_task_count', 0) or 0)} 项。"
        )

    detail_lines: list[str] = []
    if focus_items:
        append_focus_task_details(detail_lines, focus_items, has_exceptions)
    for text in summarize_completed_items(new_done, min(int(max_notify_items), 2)):
        detail_lines.append(text)
    if has_exceptions:
        for idx, reason in enumerate(reasons[:3], start=1):
            detail_lines.append(f"异常{idx}：{humanize_chat_error(reason)}")
        detail_lines.append("运行详情已写入内部留痕，不再在群聊中展示底层文件路径。")

    return render_chat_notice(
        title,
        status=status,
        task_id=str(task_id or "").strip(),
        sender_identity=str(sender_identity or DEFAULT_SENDER_IDENTITY).strip(),
        run_time=str(run_time or now_iso()).strip(),
        trace_id=build_trace_id(run_id=run_id),
        summary="；".join(summary_parts),
        details=detail_lines,
        extra_lines=extra_lines,
        next_step=(
            "请先处理异常，再确认新增待办和完成项是否需要进一步跟进。"
            if has_exceptions
            else "请按任务编号进入任务中心确认新增待办，并复核今天新增完成项。"
        ),
    )


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Daily TODO digest")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/daily-todo-digest/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/daily-todo-digest/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--max-db-tasks", type=int, default=2000)
    parser.add_argument("--max-notify-items", type=int, default=15)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    tasks = load_tasks(db_path, limit=int(args.max_db_tasks))
    sent_todo_ids = {str(x) for x in state.get("sent_todo_ids", [])}
    sent_done_ids = {str(x) for x in state.get("sent_done_ids", [])}

    unresolved_statuses = {"pending", "running", "failed", "escalated"}
    todo_candidates = [
        x
        for x in tasks
        if str(x.get("status", "")).lower() in unresolved_statuses and not is_runtime_binding_task(x)
    ]
    done_candidates = [
        x
        for x in tasks
        if str(x.get("status", "")).lower() == "passed"
        and is_today_local(x.get("updated_at", ""))
        and not is_runtime_binding_task(x)
    ]

    new_todo = [x for x in todo_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_todo_ids]
    new_done = [x for x in done_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_done_ids]
    latest_reports = load_latest_agent_reports(
        db_path,
        [str(item.get("task_id", "")).strip() for item in [*new_todo, *new_done] if str(item.get("task_id", "")).strip()],
    )
    new_todo = attach_latest_agent_reports(new_todo, latest_reports)
    new_done = attach_latest_agent_reports(new_done, latest_reports)

    sender_identity = normalize_sender_identity(args.sender_identity)
    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    run_errors: list[str] = []
    notify = bool(new_todo or new_done)
    output = "NO_REPLY"

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "normal_log_mode": normal_log_mode,
        "notify": notify,
        "db": str(db_path),
        "new_todo_count": len(new_todo),
        "new_done_count": len(new_done),
        "new_todo_ids": [str(x.get("task_id", "")) for x in new_todo if x.get("task_id")],
        "new_done_ids": [str(x.get("task_id", "")) for x in new_done if x.get("task_id")],
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "cost_estimate": 0.0,
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
    report["run_duration_ms"] = run_duration_ms
    report["observability_window_since"] = since_24h

    planner_summary_snapshot: dict[str, Any] = {}
    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    if db_path.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_path)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_path,
                raw_task_id,
                "ops-agent",
                "ops-agent/daily-todo-digest",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            db_path,
            ["planner-summary", "--planner-id", "coordinator", "--since", since_24h, "--limit", "80"],
            timeout=30,
        )
        policy_observability["planner_summary_ok"] = ok_summary
        if ok_summary and isinstance(payload_summary, dict):
            summary = payload_summary.get("summary")
            if isinstance(summary, dict):
                planner_summary_snapshot = {
                    "planner_id": summary.get("planner_id"),
                    "report_count": summary.get("report_count", 0),
                    "task_count": summary.get("task_count", 0),
                    "resolved_task_count": summary.get("resolved_task_count", 0),
                    "failed_task_count": summary.get("failed_task_count", 0),
                    "solved_ratio_pct": summary.get("solved_ratio_pct", 0.0),
                    "total_tokens": summary.get("total_tokens", 0),
                    "total_cost_estimate": summary.get("total_cost_estimate", 0.0),
                }
        if (not ok_summary) and err_summary:
            policy_observability["errors"].append(err_summary)

        module_args = [
            "log-module",
            "--module-name",
            "ops-agent/daily-todo-digest",
            "--phase",
            "daily_digest",
            "--level",
            "info",
            "--status",
            "passed",
            "--message",
            f"daily todo digest generated: new_todo={len(new_todo)} new_done={len(new_done)}",
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "notify": bool(notify),
                    "new_todo_count": len(new_todo),
                    "new_done_count": len(new_done),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(db_path, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "ops-agent/daily-todo-digest",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "daily_todo_digest",
            "--status",
            "acked",
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(report.get("run_id", "")),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps(
                {
                    "new_todo_count": len(new_todo),
                    "new_done_count": len(new_done),
                    "scheduled_priority_order_enabled": True,
                },
                ensure_ascii=False,
            ),
            "--actor",
            "ops-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_path, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        if bound_task_id:
            report_status = "failed" if run_errors else "passed"
            quality_score = 70.0 if run_errors else 90.0
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "ops-agent",
                "--planner-id",
                "coordinator",
                "--status",
                report_status,
                "--solved",
                ("false" if run_errors else "true"),
                "--resolved-issues",
                "daily_todo_digest",
                "--resolution-summary",
                (
                    "daily todo digest generated"
                    if not run_errors
                    else "daily todo digest generated with runtime exceptions"
                ),
                "--resolution-steps",
                "load_tasks,order_by_schedule,build_digest,record_state",
                "--failed-items",
                ",".join(str(x) for x in run_errors[:20]),
                "--failure-count",
                str(len(run_errors)),
                "--duration-ms",
                str(run_duration_ms),
                "--input-tokens",
                "0",
                "--output-tokens",
                "0",
                "--cost-estimate",
                "0",
                "--quality-score",
                str(round(float(quality_score), 2)),
                "--quality-grade",
                ("c" if run_errors else "a"),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "report_file": str(report_file),
                        "new_todo_count": len(new_todo),
                        "new_done_count": len(new_done),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "ops-agent",
            ]
            ok_report, payload_report, err_report = invoke_policy_enforcer(db_path, report_args, timeout=35)
            policy_observability["report_agent_result_ok"] = ok_report
            if ok_report and isinstance(payload_report, dict):
                result_payload = payload_report.get("result")
                if isinstance(result_payload, dict):
                    planner_payload = result_payload.get("planner_payload")
                    if isinstance(planner_payload, dict):
                        policy_observability["agent_report"] = {
                            "report_status": planner_payload.get("report_status"),
                            "notify_chat": planner_payload.get("notify_chat"),
                            "failure_count": planner_payload.get("failure_count"),
                        }
            if (not ok_report) and err_report:
                policy_observability["errors"].append(err_report)

    report["planner_summary"] = planner_summary_snapshot
    report["policy_observability"] = policy_observability
    save_json(report_file, report)

    state["updated_at"] = now_iso()
    if notify:
        state["sent_todo_ids"] = sorted(set(sent_todo_ids).union(report["new_todo_ids"]))
        state["sent_done_ids"] = sorted(set(sent_done_ids).union(report["new_done_ids"]))
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(new_todo or new_done or exception_reasons)
    report["notify"] = notify
    report["run_errors"] = run_errors
    save_json(report_file, report)

    output = build_chat_output(
        sender_identity=sender_identity,
        task_id=str(args.task_id or ""),
        run_time=now_iso(),
        run_id=str(report.get("run_id", "")),
        new_todo=new_todo,
        new_done=new_done,
        planner_summary=planner_summary_snapshot,
        exception_reasons=exception_reasons[:12],
        max_notify_items=int(args.max_notify_items),
    )

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(output)
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

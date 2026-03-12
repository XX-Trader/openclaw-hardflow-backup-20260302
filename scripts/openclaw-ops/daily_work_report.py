#!/usr/bin/env python3
"""Daily work digest with DingTalk notification and TODO/DONE dedupe."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import FileWriteError, write_json_atomic
from chat_output import build_trace_id, render_chat_notice
from todo_patrol import norm_text, parse_todo_items

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "ops-agent/daily-work-report"


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
    source_name = str(source_module or "ops-agent/daily-work-report").strip() or "ops-agent/daily-work-report"
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


def collect_observability_stats(db_path: Path, since_iso: str) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "module_error_count": 0,
            "communication_error_count": 0,
            "agent_failed_report_count": 0,
            "agent_total_report_count": 0,
        }
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        module_error = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM module_logs
            WHERE ts >= ?
              AND (LOWER(level) = 'error' OR LOWER(status) IN ('failed', 'timeout'))
            """,
            (since_iso,),
        ).fetchone()
        comm_error = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM module_communications
            WHERE ts >= ?
              AND LOWER(status) IN ('failed', 'timeout')
            """,
            (since_iso,),
        ).fetchone()
        report_rows = conn.execute(
            """
            SELECT
              COUNT(*) AS total_cnt,
              SUM(CASE WHEN LOWER(status) IN ('failed', 'escalated') OR solved = 0 THEN 1 ELSE 0 END) AS failed_cnt
            FROM agent_task_reports
            WHERE ts >= ?
            """,
            (since_iso,),
        ).fetchone()
        return {
            "module_error_count": int(module_error["cnt"] or 0) if module_error else 0,
            "communication_error_count": int(comm_error["cnt"] or 0) if comm_error else 0,
            "agent_failed_report_count": int(report_rows["failed_cnt"] or 0) if report_rows else 0,
            "agent_total_report_count": int(report_rows["total_cnt"] or 0) if report_rows else 0,
        }
    finally:
        conn.close()


def load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def load_env_files(paths: list[Path]) -> dict[str, str]:
    envs: dict[str, str] = {}
    for path in paths:
        envs.update(load_env_file(path))
    return envs


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


def load_tasks(db_path: Path, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT task_id, pool, task_type, reason, priority, risk_level, assignee, status, created_at, updated_at
            FROM tasks
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_runtime_binding_task(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if str(item.get("task_type", "")).strip().lower() == "ops_runtime_cron":
        return True
    return str(item.get("reason", "")).strip().startswith("[CRON_RUNTIME] bind ")


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


def build_dingtalk_url(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    ts = str(int(time.time() * 1000))
    sign_base = f"{ts}\n{secret}".encode("utf-8")
    sign = base64.b64encode(hmac.new(secret.encode("utf-8"), sign_base, digestmod=hashlib.sha256).digest()).decode(
        "utf-8"
    )
    sign = urllib.parse.quote_plus(sign)
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={ts}&sign={sign}"


def post_dingtalk(webhook: str, secret: str, title: str, text: str, timeout: int = 10) -> tuple[bool, str]:
    url = build_dingtalk_url(webhook, secret)
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    req = urllib.request.Request(url=url, method="POST")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=max(1, int(timeout))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(raw)
            except Exception:
                return False, raw[:240]
            ok = int(obj.get("errcode", -1)) == 0
            return ok, raw[:240]
    except Exception as exc:
        return False, str(exc)


def summarize_items(items: list[dict[str, Any]], limit: int) -> list[str]:
    out: list[str] = []
    for row in items[: max(1, int(limit))]:
        task_id = str(row.get("task_id", "")).strip() or "-"
        reason = str(row.get("reason", "")).strip()[:70] or "未填写原因"
        priority = str(row.get("priority", "")).strip() or "-"
        risk_level = str(row.get("risk_level", "")).strip() or "-"
        assignee = str(row.get("assignee", "")).strip() or "-"
        out.append(f"- [{task_id}] {reason}（优先级={priority}，风险={risk_level}，负责人={assignee}）")
    return out


def summarize_todo_file_items(items: list[dict[str, Any]], limit: int) -> list[str]:
    out: list[str] = []
    for row in items[: max(1, int(limit))]:
        task_id = str(row.get("task_id", "")).strip() or "-"
        reason = str(row.get("reason", "")).strip()[:70] or "未填写待办"
        source_file = str(row.get("source_file", "")).strip() or "todo.md"
        section = str(row.get("section", "")).strip()
        if section:
            out.append(f"- [{task_id}] {reason}（来源={source_file} / {section}）")
        else:
            out.append(f"- [{task_id}] {reason}（来源={source_file}）")
    return out


def infer_todo_file_priority(section: str, priority_tag: str) -> tuple[str, str]:
    tag = str(priority_tag or "").strip().upper()
    section_text = norm_text(section)
    if tag in {"P0", "P1"}:
        return "high", "high"
    if tag == "P2":
        return "medium", "low"
    if "重要紧急" in section_text:
        return "high", "high"
    if "重要不紧急" in section_text:
        return "medium", "low"
    if "不重要紧急" in section_text:
        return "medium", "low"
    return "planned", "low"


def build_task_reason_keys(items: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in items:
        status = str(item.get("status", "")).strip().lower()
        if status == "passed":
            continue
        task_id = str(item.get("task_id", "")).strip()
        reason = str(item.get("reason", "")).strip()
        combined = " ".join(part for part in [task_id, reason] if part).strip()
        if combined:
            keys.add(norm_text(combined))
        if task_id:
            keys.add(norm_text(task_id))
        if reason:
            keys.add(norm_text(reason))
    return keys


def load_todo_file_pending_items(todo_files: list[Path], existing_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not todo_files:
        return []
    existing_keys = build_task_reason_keys(existing_tasks)
    pending_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for todo_file in todo_files:
        if not todo_file.exists():
            continue
        try:
            content = todo_file.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for item in parse_todo_items(content):
            match_keys = {
                norm_text(item.text),
                norm_text(f"todo-file-{item.item_id}"),
                norm_text(f"todo-file-{item.item_id} {item.text}"),
            }
            if existing_keys.intersection(match_keys):
                continue
            dedupe_key = f"{todo_file.name}:{item.item_id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            priority, risk_level = infer_todo_file_priority(item.section, item.priority_tag)
            pending_items.append(
                {
                    "task_id": f"todo-file-{item.item_id}",
                    "reason": item.text,
                    "priority": priority,
                    "risk_level": risk_level,
                    "assignee": "待入任务中心",
                    "source_file": todo_file.name,
                    "section": item.section,
                    "line_num": item.line_num,
                }
            )
    return pending_items


def humanize_chat_error(reason: str) -> str:
    raw = str(reason or "").strip()
    if not raw:
        return "未知异常"
    if raw.startswith("dingtalk_post_failed:"):
        detail = raw.split(":", 1)[1].strip() or raw
        if detail.lower() == "timeout":
            detail = "请求超时"
        return f"钉钉发送失败：{detail}"
    if raw.startswith("webhook_missing:"):
        detail = raw.split(":", 1)[1].strip() or raw
        return f"钉钉 Webhook 未配置：{detail}"
    if raw.startswith("policy_enforcer_failed:"):
        detail = raw.split(":", 1)[1].strip() or raw
        return f"策略记录失败：{detail}"
    if raw.startswith("policy_enforcer_"):
        return f"策略记录异常：{raw}"
    return raw


def build_chat_output(
    *,
    sender_identity: str,
    task_id: str,
    run_time: str,
    new_todo: list[dict[str, Any]],
    new_done: list[dict[str, Any]],
    todo_file_pending: list[dict[str, Any]],
    planner_summary: dict[str, Any],
    exception_reasons: list[str],
    report_file: Path,
) -> str:
    reasons = [str(item).strip() for item in exception_reasons if str(item).strip()]
    has_digest = bool(new_todo or new_done or todo_file_pending)
    if (not reasons) and (not has_digest):
        return "NO_REPLY"

    if has_digest and reasons:
        title = "每日工作报告需关注"
        status = "需处理"
        next_step = "请先处理异常，再确认日报中的待办和完成项是否需要进一步跟进。"
    elif reasons:
        title = "每日工作报告异常"
        status = "需处理"
        next_step = "请先检查钉钉配置、网络连通性和策略留痕。"
    else:
        title = "每日工作报告"
        status = "已汇报"
        next_step = "请按日报继续推进待办，并确认 todo 清单中的任务是否达到入任务中心条件。"

    summary_parts: list[str] = []
    if new_todo:
        summary_parts.append(f"任务中心待办 {len(new_todo)} 项")
    if todo_file_pending:
        summary_parts.append(f"todo清单待办 {len(todo_file_pending)} 项")
    if new_done:
        summary_parts.append(f"任务中心完成 {len(new_done)} 项")
    if reasons:
        summary_parts.append(f"异常 {len(reasons)} 项")

    extra_lines: list[str] = []
    if planner_summary:
        report_count = int(planner_summary.get("report_count", 0) or 0)
        task_count = int(planner_summary.get("task_count", 0) or 0)
        failed_task_count = int(planner_summary.get("failed_task_count", 0) or 0)
        extra_lines.append(f"24小时留痕：报告 {report_count} 条，任务 {task_count} 条，失败 {failed_task_count} 条")

    detail_lines: list[str] = []
    for idx, item in enumerate(new_todo[:5], start=1):
        task_label = str(item.get("task_id", "")).strip() or "-"
        reason = str(item.get("reason", "")).strip() or "未填写原因"
        detail_lines.append(f"任务中心待办{idx}：[{task_label}] {reason}")
    for idx, item in enumerate(todo_file_pending[:5], start=1):
        task_label = str(item.get("task_id", "")).strip() or "-"
        reason = str(item.get("reason", "")).strip() or "未填写待办"
        source_file = str(item.get("source_file", "")).strip() or "todo.md"
        section = str(item.get("section", "")).strip()
        if section:
            detail_lines.append(f"todo清单待办{idx}：[{task_label}] {reason}（来源={source_file} / {section}）")
        else:
            detail_lines.append(f"todo清单待办{idx}：[{task_label}] {reason}（来源={source_file}）")
    for idx, item in enumerate(new_done[:5], start=1):
        task_label = str(item.get("task_id", "")).strip() or "-"
        reason = str(item.get("reason", "")).strip() or "已完成"
        detail_lines.append(f"任务中心完成{idx}：[{task_label}] {reason}")
    for idx, reason in enumerate(reasons[:8], start=1):
        detail_lines.append(f"异常{idx}：{humanize_chat_error(reason)}")

    return render_chat_notice(
        title,
        status=status,
        task_id=str(task_id or "").strip(),
        sender_identity=str(sender_identity or DEFAULT_SENDER_IDENTITY).strip(),
        run_time=str(run_time or now_iso()).strip(),
        trace_id=build_trace_id(report_file=report_file),
        summary="，".join(summary_parts),
        extra_lines=extra_lines,
        details=detail_lines,
        next_step=next_step,
    )


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Daily work digest with DingTalk")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/daily-work/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/daily-work/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--dingtalk-webhook", default="")
    parser.add_argument("--dingtalk-webhook-env", default="DINGTALK_WEBHOOK_URL")
    parser.add_argument("--dingtalk-secret", default="")
    parser.add_argument("--dingtalk-secret-env", default="DINGTALK_SECRET")
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--todo-file", action="append", default=[])
    parser.add_argument("--max-db-tasks", type=int, default=2000)
    parser.add_argument("--max-notify-items", type=int, default=15)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    env_files: list[Path] = [Path(x).expanduser() for x in args.env_file if str(x).strip()]
    todo_files: list[Path] = [Path(x).expanduser() for x in args.todo_file if str(x).strip()]
    openclaw_home = Path(os.environ.get("OPENCLAW_HOME", str(home / ".openclaw"))).expanduser()
    default_runtime_env = openclaw_home / "ops" / "runtime.env"
    if default_runtime_env not in env_files:
        env_files.append(default_runtime_env)
    env_from_files = load_env_files(env_files)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    tasks = load_tasks(db_path, limit=int(args.max_db_tasks))
    sent_todo_ids = set(str(x) for x in state.get("sent_todo_ids", []))
    sent_done_ids = set(str(x) for x in state.get("sent_done_ids", []))

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
    todo_file_pending = load_todo_file_pending_items(todo_files, todo_candidates)

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)
    run_errors: list[str] = []

    should_send_digest = bool(new_todo or new_done or todo_file_pending)
    digest_notify = bool(should_send_digest)

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "db": str(db_path),
        "normal_log_mode": normal_log_mode,
        "notify": False,
        "todo_files": [str(path.name) for path in todo_files],
        "new_todo_count": len(new_todo),
        "new_done_count": len(new_done),
        "todo_file_pending_count": len(todo_file_pending),
        "new_todo_ids": [str(x.get("task_id", "")) for x in new_todo if x.get("task_id")],
        "new_done_ids": [str(x.get("task_id", "")) for x in new_done if x.get("task_id")],
        "todo_file_pending_ids": [str(x.get("task_id", "")) for x in todo_file_pending if x.get("task_id")],
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"

    dingtalk_status = {"attempted": False, "ok": False, "note": ""}
    dingtalk_text = ""
    if should_send_digest:
        lines: list[str] = []
        title = f"每日工作报告 {now().strftime('%Y-%m-%d')}"
        lines.append(f"# {title}")
        lines.append(f"- 发送方：{sender_identity}")
        lines.append(f"- 任务编号：{args.task_id or '-'}")
        lines.append(f"- 时间：{now_iso()}")
        lines.append(f"- 任务中心待办：{len(new_todo)}")
        lines.append(f"- todo清单待办：{len(todo_file_pending)}")
        lines.append(f"- 任务中心完成：{len(new_done)}")
        lines.append("")
        lines.append("## 任务中心待办")
        lines.extend(summarize_items(new_todo, int(args.max_notify_items)) or ["- 无"])
        lines.append("")
        lines.append("## todo清单待办")
        lines.extend(summarize_todo_file_items(todo_file_pending, int(args.max_notify_items)) or ["- 无"])
        lines.append("")
        lines.append("## 任务中心完成")
        lines.extend(summarize_items(new_done, int(args.max_notify_items)) or ["- 无"])
        dingtalk_text = "\n".join(lines)

        webhook = str(
            args.dingtalk_webhook
            or os.environ.get(args.dingtalk_webhook_env, "")
            or env_from_files.get(args.dingtalk_webhook_env, "")
        ).strip()
        secret = str(
            args.dingtalk_secret
            or os.environ.get(args.dingtalk_secret_env, "")
            or env_from_files.get(args.dingtalk_secret_env, "")
        ).strip()
        if webhook:
            dingtalk_status["attempted"] = True
            ok, note = post_dingtalk(webhook=webhook, secret=secret, title=title, text=dingtalk_text)
            dingtalk_status["ok"] = ok
            dingtalk_status["note"] = note
            if not ok:
                run_errors.append(f"dingtalk_post_failed:{note}")
        else:
            dingtalk_status["attempted"] = True
            dingtalk_status["ok"] = False
            dingtalk_status["note"] = (
                f"webhook_missing:{args.dingtalk_webhook_env};"
                f"checked_env_files={','.join(str(x) for x in env_files if x.exists())}"
            )
            run_errors.append(str(dingtalk_status["note"]))

        for item in new_todo:
            tid = str(item.get("task_id", "")).strip()
            if tid:
                sent_todo_ids.add(tid)
        for item in new_done:
            tid = str(item.get("task_id", "")).strip()
            if tid:
                sent_done_ids.add(tid)

    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
    report["run_duration_ms"] = run_duration_ms
    report["observability_window_since"] = since_24h
    report["observability"] = collect_observability_stats(db_path, since_iso=since_24h)

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
                "ops-agent/daily-work-report",
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
            "ops-agent/daily-work-report",
            "--phase",
            "daily_digest",
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            (
                "daily work report generated: "
                f"new_todo={len(new_todo)} todo_file_pending={len(todo_file_pending)} new_done={len(new_done)}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "notify": bool(digest_notify),
                    "new_todo_count": len(new_todo),
                    "todo_file_pending_count": len(todo_file_pending),
                    "new_done_count": len(new_done),
                    "run_error_count": len(run_errors),
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
            "ops-agent/daily-work-report",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "daily_work_report",
            "--status",
            ("failed" if run_errors else "acked"),
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(report.get("run_id", "")),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps(
                {
                    "notify": bool(digest_notify),
                    "dingtalk_attempted": dingtalk_status.get("attempted", False),
                    "dingtalk_ok": dingtalk_status.get("ok", False),
                    "todo_file_pending_count": len(todo_file_pending),
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
            quality_score = 65.0 if run_errors else 92.0
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
                "daily_work_report",
                "--resolution-summary",
                (
                    "daily work report generated and synced"
                    if not run_errors
                    else "daily work report generated with runtime exceptions"
                ),
                "--resolution-steps",
                "load_tasks,load_todo_files,build_digest,post_dingtalk,record_state",
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
                ("true" if (should_send_digest or run_errors) else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "report_file": str(report_file),
                        "new_todo_count": len(new_todo),
                        "todo_file_pending_count": len(todo_file_pending),
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

    report["run_errors"] = run_errors
    report["todo_file_pending"] = todo_file_pending
    report["planner_summary"] = planner_summary_snapshot
    report["policy_observability"] = policy_observability
    report["dingtalk"] = dingtalk_status
    save_json(report_file, report)

    state["updated_at"] = now_iso()
    state["sent_todo_ids"] = sorted(sent_todo_ids)[-10000:]
    state["sent_done_ids"] = sorted(sent_done_ids)[-10000:]
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    output = build_chat_output(
        sender_identity=sender_identity,
        task_id=str(args.task_id or ""),
        run_time=now_iso(),
        new_todo=new_todo,
        new_done=new_done,
        todo_file_pending=todo_file_pending,
        planner_summary=planner_summary_snapshot,
        exception_reasons=exception_reasons,
        report_file=report_file,
    )
    chat_notify = output != "NO_REPLY"

    report["notify"] = chat_notify
    save_json(report_file, report)

    if args.emit_json:
        print(json.dumps({"notify": chat_notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if chat_notify:
            print(output)
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

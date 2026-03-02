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
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
            SELECT task_id, pool, reason, priority, risk_level, assignee, status, created_at, updated_at
            FROM tasks
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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
        out.append(
            "- "
            + f"[{row.get('task_id')}] "
            + f"{row.get('reason', '')[:70]} "
            + f"(priority={row.get('priority')}, risk={row.get('risk_level')}, assignee={row.get('assignee')})"
        )
    return out


def main() -> int:
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
    parser.add_argument("--max-db-tasks", type=int, default=2000)
    parser.add_argument("--max-notify-items", type=int, default=15)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    env_files: list[Path] = [Path(x).expanduser() for x in args.env_file if str(x).strip()]
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
    todo_candidates = [x for x in tasks if str(x.get("status", "")).lower() in unresolved_statuses]
    done_candidates = [
        x for x in tasks if str(x.get("status", "")).lower() == "passed" and is_today_local(x.get("updated_at", ""))
    ]

    new_todo = [x for x in todo_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_todo_ids]
    new_done = [x for x in done_candidates if str(x.get("task_id", "")) and str(x.get("task_id", "")) not in sent_done_ids]

    has_new_records = bool(new_todo or new_done)
    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)

    # Only send message when new TODO/DONE records exist.
    notify = has_new_records

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "db": str(db_path),
        "normal_log_mode": normal_log_mode,
        "notify": notify,
        "new_todo_count": len(new_todo),
        "new_done_count": len(new_done),
        "new_todo_ids": [str(x.get("task_id", "")) for x in new_todo if x.get("task_id")],
        "new_done_ids": [str(x.get("task_id", "")) for x in new_done if x.get("task_id")],
    }

    dingtalk_status = {"attempted": False, "ok": False, "note": ""}
    output = "NO_REPLY"
    if notify:
        lines: list[str] = []
        title = f"每日工作报告 {now().strftime('%Y-%m-%d')}"
        lines.append(f"# {title}")
        lines.append(f"- sender_identity: {sender_identity}")
        lines.append(f"- task: {args.task_id or '-'}")
        lines.append(f"- time: {now_iso()}")
        lines.append(f"- new_todo: {len(new_todo)}")
        lines.append(f"- new_done: {len(new_done)}")
        lines.append("")
        lines.append("## TODO (新增)")
        lines.extend(summarize_items(new_todo, int(args.max_notify_items)) or ["- 无"])
        lines.append("")
        lines.append("## DONE (新增)")
        lines.extend(summarize_items(new_done, int(args.max_notify_items)) or ["- 无"])
        text = "\n".join(lines)
        output = text

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
            ok, note = post_dingtalk(webhook=webhook, secret=secret, title=title, text=text)
            dingtalk_status["ok"] = ok
            dingtalk_status["note"] = note
        else:
            dingtalk_status["attempted"] = True
            dingtalk_status["ok"] = False
            dingtalk_status["note"] = (
                f"webhook_missing:{args.dingtalk_webhook_env};"
                f"checked_env_files={','.join(str(x) for x in env_files if x.exists())}"
            )

        for item in new_todo:
            tid = str(item.get("task_id", "")).strip()
            if tid:
                sent_todo_ids.add(tid)
        for item in new_done:
            tid = str(item.get("task_id", "")).strip()
            if tid:
                sent_done_ids.add(tid)

    report["dingtalk"] = dingtalk_status
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    save_json(report_file, report)

    state["updated_at"] = now_iso()
    state["sent_todo_ids"] = sorted(sent_todo_ids)[-10000:]
    state["sent_done_ids"] = sorted(sent_done_ids)[-10000:]
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(f"{output}\n- evidence: {report_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

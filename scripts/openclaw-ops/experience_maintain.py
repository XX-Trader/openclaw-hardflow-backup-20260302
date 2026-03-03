#!/usr/bin/env python3
"""Stable experience maintenance runner for daily/weekly/monthly cron jobs."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
MODES = {"daily", "weekly", "monthly"}
DEFAULT_SENDER_IDENTITY = "optimization-agent/experience-maintain"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


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


def ensure_memory_files(workspace: Path) -> list[str]:
    actions: list[str] = []
    workspace.mkdir(parents=True, exist_ok=True)
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    actions.append(f"ensure_dir:{memory_dir}")

    memory_md = workspace / "MEMORY.md"
    if not memory_md.exists():
        memory_md.write_text(
            "# MEMORY.md\n\n"
            "## Purpose\n"
            "- Keep durable context for recurring tasks and operational decisions.\n\n"
            "## Policy\n"
            "- Prefer concise records in memory/YYYY-MM-DD.md.\n"
            "- Keep only actionable conclusions and verified outcomes.\n",
            encoding="utf-8",
        )
        actions.append(f"create_file:{memory_md}")

    today_md = memory_dir / f"{now().strftime('%Y-%m-%d')}.md"
    if not today_md.exists():
        today_md.write_text(f"# {now().strftime('%Y-%m-%d')} 维护记录\n\n", encoding="utf-8")
        actions.append(f"create_file:{today_md}")
    return actions


def default_state() -> dict[str, Any]:
    return {
        "updated_at": "",
        "last_run_by_mode": {},
        "last_report_file": "",
    }


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Experience maintenance runner")
    parser.add_argument("--mode", default="daily", choices=sorted(MODES))
    parser.add_argument("--workspace", default=str(home / ".openclaw/workspace"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/experience-maintain/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/experience-maintain/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    mode = str(args.mode).strip().lower()
    if mode not in MODES:
        raise SystemExit(f"invalid mode: {mode}")

    workspace = Path(args.workspace).expanduser()
    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    actions = ensure_memory_files(workspace)
    run_id = uuid.uuid4().hex[:12]
    report = {
        "run_id": run_id,
        "time": now_iso(),
        "mode": mode,
        "sender_identity": str(args.sender_identity or DEFAULT_SENDER_IDENTITY).strip() or DEFAULT_SENDER_IDENTITY,
        "task_id": str(args.task_id or ""),
        "workspace": str(workspace),
        "actions": actions,
        "ok": True,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "cost_estimate": 0.0,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{mode}_{run_id}.json"
    save_json(report_file, report)

    last_runs = state.get("last_run_by_mode")
    if not isinstance(last_runs, dict):
        last_runs = {}
    last_runs[mode] = {
        "time": now_iso(),
        "run_id": run_id,
        "report_file": str(report_file),
    }
    state["last_run_by_mode"] = last_runs
    state["updated_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    save_json(state_path, state)

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    notify = normal_log_mode == "chat"
    output = "NO_REPLY"
    if notify:
        output = (
            f"# experience-maintain {mode}\n"
            f"- sender_identity: {report['sender_identity']}\n"
            f"- task: {args.task_id or '-'}\n"
            f"- time: {report['time']}\n"
            f"- actions: {len(actions)}\n"
            f"- evidence: {report_file}"
        )

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


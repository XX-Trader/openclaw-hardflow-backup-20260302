#!/usr/bin/env python3
"""Consume task control-plane records into unified human and machine output views."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import write_json_atomic  # type: ignore
from task_center import TaskCenter  # type: ignore
from utf8_runtime import configure_process_utf8_stdio
from workflow_views import build_task_control_plane_event, render_human_view

configure_process_utf8_stdio()


def build_task_output_consumer_payload(
    *,
    db_file: str | Path,
    task_id: str,
    event_limit: int = 200,
    notify_on: str = "activity",
) -> dict[str, Any]:
    """Build the unified output payload for one task control-plane record."""

    task_center = TaskCenter(Path(db_file).expanduser())
    try:
        report = task_center.task_report(
            str(task_id).strip(),
            event_limit=max(20, int(event_limit or 200)),
            display_safe=False,
        )
    finally:
        task_center.close()

    event = build_task_control_plane_event(report, notify_on=notify_on)
    human_text = render_human_view(event["views"]["human"])
    return {
        "task_id": str(task_id).strip(),
        "notify": bool(event["views"]["human"].get("visible", False)),
        "event": event,
        "human_text": human_text,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Render unified task control-plane output views.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--event-limit", default="200")
    parser.add_argument("--notify-on", default="activity", choices=["error", "activity", "always"])
    parser.add_argument("--output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the generated payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_task_output_consumer_payload(
        db_file=str(args.db).strip(),
        task_id=str(args.task_id).strip(),
        event_limit=max(20, int(args.event_limit or 200)),
        notify_on=str(args.notify_on).strip(),
    )
    if str(args.output or "").strip():
        write_json_atomic(
            Path(str(args.output).strip()).expanduser(),
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(payload["human_text"])
    return payload


if __name__ == "__main__":
    main()

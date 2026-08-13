#!/usr/bin/env python3
"""Broadcast changed task control-plane events through one deduplicated runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve()
LIBRARY_DIR = ROOT.parents[2]
REPO_ROOT = ROOT.parents[4]
IMPORT_DIRS = [
    LIBRARY_DIR / "control-plane-ops" / "scripts" / "policy",
    LIBRARY_DIR / "openclaw-workflow-manager" / "scripts",
    REPO_ROOT / "scripts" / "openclaw-ops" / "shared",
]
for import_dir in IMPORT_DIRS:
    if import_dir.exists() and str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

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

from io_write_gateway import write_json_atomic  # type: ignore
from task_center import TaskCenter, parse_json, utc_now_iso  # type: ignore
from task_output_consumer import build_task_output_consumer_payload
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


def _load_state(path: Path) -> dict[str, Any]:
    """Load the dedupe state file from disk."""

    if not path.exists():
        return {"items": {}, "updated_at": ""}
    payload = parse_json(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return {"items": {}, "updated_at": ""}
    items = payload.get("items")
    if not isinstance(items, dict):
        items = {}
    return {
        "items": {str(task_id).strip(): value for task_id, value in items.items() if str(task_id).strip()},
        "updated_at": str(payload.get("updated_at", "")).strip(),
    }


def _save_state(path: Path, state: dict[str, Any]) -> None:
    """Persist the dedupe state file."""

    write_json_atomic(
        path,
        state,
        ensure_ascii=False,
        indent=2,
        file_mode=0o644,
        dir_mode=0o755,
    )


def _event_signature(payload: dict[str, Any]) -> str:
    """Build a stable signature for one task control-plane payload."""

    return hashlib.sha1(
        json.dumps(payload.get("event", {}), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _join_human_sections(items: list[dict[str, Any]]) -> str:
    """Render a compact multi-task human summary."""

    if not items:
        return "NO_REPLY"
    sections = [
        "# 任务控制面更新",
        f"- 任务数: {len(items)}",
        f"- 时间: {utc_now_iso()}",
    ]
    for item in items:
        sections.append("")
        sections.append(f"## {item['task_id']}")
        sections.append(str(item["human_text"]).strip() or "NO_REPLY")
    return "\n".join(sections).strip()


def build_task_output_broadcast_payload(
    *,
    db_file: str | Path,
    state_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 12,
    event_limit: int = 200,
    notify_on: str = "error",
) -> dict[str, Any]:
    """Build a deduplicated batch payload for recent task control-plane changes."""

    db_path = Path(db_file).expanduser()
    state_path = Path(state_file).expanduser()
    since = (
        datetime.now(tz=timezone.utc) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()

    task_center = TaskCenter(db_path)
    try:
        candidates = task_center.recent_control_plane_task_ids(
            since=since,
            limit=max(1, int(limit or 12)),
            display_safe=False,
        )
    finally:
        task_center.close()

    prior_state = _load_state(state_path)
    prior_items = prior_state.get("items", {}) if isinstance(prior_state.get("items"), dict) else {}
    next_items = dict(prior_items)
    changed_items: list[dict[str, Any]] = []

    for candidate in candidates:
        task_id = str(candidate.get("task_id", "")).strip()
        if not task_id:
            continue
        payload = build_task_output_consumer_payload(
            db_file=db_path,
            task_id=task_id,
            event_limit=max(20, int(event_limit or 200)),
            notify_on=str(notify_on).strip() or "error",
        )
        signature = _event_signature(payload)
        previous_signature = ""
        previous_entry = prior_items.get(task_id)
        if isinstance(previous_entry, dict):
            previous_signature = str(previous_entry.get("signature", "")).strip()
        if bool(payload.get("notify")):
            next_items[task_id] = {
                "signature": signature,
                "latest_ts": str(candidate.get("latest_ts", "")).strip(),
                "sources": candidate.get("sources", []),
                "updated_at": utc_now_iso(),
            }
            if signature != previous_signature:
                changed_items.append(
                    {
                        "task_id": task_id,
                        "latest_ts": str(candidate.get("latest_ts", "")).strip(),
                        "sources": candidate.get("sources", []),
                        "event": payload["event"],
                        "human_text": payload["human_text"],
                    }
                )
        else:
            next_items.pop(task_id, None)

    state_payload = {
        "items": next_items,
        "updated_at": utc_now_iso(),
    }
    _save_state(state_path, state_payload)
    human_text = _join_human_sections(changed_items)
    return {
        "db_file": str(db_path),
        "state_file": str(state_path),
        "notify": bool(changed_items),
        "lookback_hours": max(1, int(lookback_hours or 24)),
        "candidate_task_count": len(candidates),
        "notified_task_count": len(changed_items),
        "items": changed_items,
        "human_text": human_text,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Broadcast changed task control-plane events.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--lookback-hours", default="24")
    parser.add_argument("--limit", default="12")
    parser.add_argument("--event-limit", default="200")
    parser.add_argument("--notify-on", default="error", choices=["error", "activity", "always"])
    parser.add_argument("--output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the generated batch payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_task_output_broadcast_payload(
        db_file=str(args.db).strip(),
        state_file=str(args.state_file).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 24)),
        limit=max(1, int(args.limit or 12)),
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

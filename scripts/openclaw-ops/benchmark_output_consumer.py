#!/usr/bin/env python3
"""Consume benchmark sweep summaries into unified human and machine output views."""

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
from utf8_runtime import configure_process_utf8_stdio
from workflow_views import build_benchmark_sweep_event, render_human_view

configure_process_utf8_stdio()


def _load_summary(path: Path) -> dict[str, Any]:
    """Load one benchmark sweep summary JSON file."""

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"benchmark sweep summary must be a JSON object: {path}")
    payload.setdefault("summary_file", str(path))
    return payload


def build_benchmark_output_consumer_payload(
    *,
    summary_file: str | Path,
    notify_on: str = "activity",
) -> dict[str, Any]:
    """Build the unified output payload for one benchmark sweep summary."""

    summary_path = Path(summary_file).expanduser()
    summary = _load_summary(summary_path)
    event = build_benchmark_sweep_event(summary, notify_on=notify_on)
    human_text = render_human_view(event["views"]["human"])
    return {
        "summary_file": str(summary_path),
        "notify": bool(event["views"]["human"].get("visible", False)),
        "event": event,
        "human_text": human_text,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Render unified benchmark sweep output views.")
    parser.add_argument("--summary-file", required=True)
    parser.add_argument("--notify-on", default="activity", choices=["error", "activity", "always"])
    parser.add_argument("--output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the generated payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_benchmark_output_consumer_payload(
        summary_file=str(args.summary_file).strip(),
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

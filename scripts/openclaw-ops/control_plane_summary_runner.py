#!/usr/bin/env python3
"""Aggregate recent control-plane activity into one deduplicated summary event."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import write_json_atomic  # type: ignore
from task_center import TaskCenter, parse_json, utc_now_iso  # type: ignore
from utf8_runtime import configure_process_utf8_stdio
from workflow_views import build_control_plane_summary_event, render_human_view

configure_process_utf8_stdio()


def _load_state(path: Path) -> dict[str, Any]:
    """Load the summary dedupe state file."""

    if not path.exists():
        return {"signature": "", "updated_at": ""}
    payload = parse_json(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return {"signature": "", "updated_at": ""}
    return {
        "signature": str(payload.get("signature", "")).strip(),
        "updated_at": str(payload.get("updated_at", "")).strip(),
    }


def _save_state(path: Path, state: dict[str, Any]) -> None:
    """Persist the summary dedupe state file."""

    write_json_atomic(
        path,
        state,
        ensure_ascii=False,
        indent=2,
        file_mode=0o644,
        dir_mode=0o755,
    )


def _summary_signature(summary: dict[str, Any]) -> str:
    """Build a stable signature for one control-plane summary."""

    return hashlib.sha1(json.dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _normalize_veto_reason_counts(counter: dict[str, int]) -> list[dict[str, Any]]:
    """Normalize veto counters into sorted list payload."""

    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if reason and count > 0
    ]


def _build_top_task_item(report: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    task = report.get("task", {}) if isinstance(report.get("task", {}), dict) else {}
    control = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
    latest_benchmark = control.get("latest_benchmark_run", {}) if isinstance(control.get("latest_benchmark_run", {}), dict) else {}
    decision = latest_benchmark.get("decision", {}) if isinstance(latest_benchmark.get("decision", {}), dict) else {}
    return {
        "task_id": str(task.get("task_id", "")).strip(),
        "workflow_profile_id": str(task.get("workflow_profile_id", "")).strip(),
        "workflow_channel": str(task.get("workflow_channel", "")).strip(),
        "stage_id": str(task.get("stage_id", "")).strip(),
        "latest_ts": str(candidate.get("latest_ts", "")).strip(),
        "sources": candidate.get("sources", []),
        "open_incident_count": int(control.get("open_incident_count", 0) or 0),
        "critical_open_incident_count": int(control.get("critical_open_incident_count", 0) or 0),
        "requires_human_assistance": bool(control.get("requires_human_assistance", False)),
        "waiting_human_confirm": bool(control.get("waiting_human_confirm", False)),
        "needs_clarification": bool(control.get("needs_clarification", False)),
        "benchmark_blocked": bool(latest_benchmark) and not bool(decision.get("promote_to_new_baseline", False)),
        "benchmark_promoted": bool(decision.get("promote_to_new_baseline", False)),
    }


def _collect_candidate_metrics(
    *,
    candidate: dict[str, Any],
    report: dict[str, Any],
    totals: dict[str, int | float],
    veto_counter: dict[str, int],
    top_tasks: list[dict[str, Any]],
) -> None:
    """Merge one task report into the rolling control-plane summary."""

    control = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
    diagnostics = report.get("diagnostics", {}) if isinstance(report.get("diagnostics", {}), dict) else {}
    latest_benchmark = control.get("latest_benchmark_run", {}) if isinstance(control.get("latest_benchmark_run", {}), dict) else {}
    decision = latest_benchmark.get("decision", {}) if isinstance(latest_benchmark.get("decision", {}), dict) else {}
    token_usage = report.get("token_usage_effective", {}) if isinstance(report.get("token_usage_effective", {}), dict) else {}

    totals["open_incident_count"] += max(0, int(control.get("open_incident_count", 0) or 0))
    totals["critical_open_incident_count"] += max(0, int(control.get("critical_open_incident_count", 0) or 0))
    totals["human_assistance_task_count"] += 1 if bool(control.get("requires_human_assistance", False)) else 0
    totals["waiting_human_confirm_task_count"] += 1 if bool(control.get("waiting_human_confirm", False)) else 0
    totals["needs_clarification_task_count"] += 1 if bool(control.get("needs_clarification", False)) else 0
    totals["total_tokens"] += max(0, int(token_usage.get("total_tokens", 0) or 0))
    totals["total_cost_estimate"] += float(token_usage.get("cost_estimate", 0.0) or 0.0)

    if int(diagnostics.get("benchmark_run_count", 0) or 0) > 0 and latest_benchmark:
        totals["benchmark_run_task_count"] += 1
        if bool(decision.get("promote_to_new_baseline", False)):
            totals["benchmark_promoted_count"] += 1
        else:
            totals["benchmark_blocked_count"] += 1
        veto_reasons = decision.get("veto_reasons", [])
        if isinstance(veto_reasons, list):
            for reason in veto_reasons:
                reason_text = str(reason or "").strip()
                if reason_text:
                    veto_counter[reason_text] = veto_counter.get(reason_text, 0) + 1

    top_tasks.append(_build_top_task_item(report, candidate))


def collect_control_plane_summary(
    *,
    db_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 20,
) -> dict[str, Any]:
    """Collect one pure control-plane summary without dedupe side effects."""

    db_path = Path(db_file).expanduser()
    since = (
        datetime.now(tz=timezone.utc) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()

    task_center = TaskCenter(db_path)
    try:
        candidates = task_center.recent_control_plane_task_ids(
            since=since,
            limit=max(1, int(limit or 20)),
            display_safe=False,
        )
        veto_counter: dict[str, int] = {}
        top_tasks: list[dict[str, Any]] = []
        totals: dict[str, int | float] = {
            "open_incident_count": 0,
            "critical_open_incident_count": 0,
            "human_assistance_task_count": 0,
            "waiting_human_confirm_task_count": 0,
            "needs_clarification_task_count": 0,
            "benchmark_run_task_count": 0,
            "benchmark_promoted_count": 0,
            "benchmark_blocked_count": 0,
            "total_tokens": 0,
            "total_cost_estimate": 0.0,
        }
        for candidate in candidates:
            task_id = str(candidate.get("task_id", "")).strip()
            if not task_id:
                continue
            report = task_center.task_report(task_id, event_limit=200, display_safe=False)
            _collect_candidate_metrics(
                candidate=candidate,
                report=report,
                totals=totals,
                veto_counter=veto_counter,
                top_tasks=top_tasks,
            )
    finally:
        task_center.close()

    return {
        "generated_at": utc_now_iso(),
        "lookback_hours": max(1, int(lookback_hours or 24)),
        "scanned_task_count": len(candidates),
        "open_incident_count": int(totals["open_incident_count"]),
        "critical_open_incident_count": int(totals["critical_open_incident_count"]),
        "human_assistance_task_count": int(totals["human_assistance_task_count"]),
        "waiting_human_confirm_task_count": int(totals["waiting_human_confirm_task_count"]),
        "needs_clarification_task_count": int(totals["needs_clarification_task_count"]),
        "benchmark_run_task_count": int(totals["benchmark_run_task_count"]),
        "benchmark_promoted_count": int(totals["benchmark_promoted_count"]),
        "benchmark_blocked_count": int(totals["benchmark_blocked_count"]),
        "total_tokens": int(totals["total_tokens"]),
        "total_cost_estimate": round(float(totals["total_cost_estimate"]), 6),
        "veto_reason_counts": _normalize_veto_reason_counts(veto_counter),
        "top_tasks": top_tasks[:5],
    }


def build_control_plane_summary_payload(
    *,
    db_file: str | Path,
    state_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 20,
    notify_on: str = "activity",
) -> dict[str, Any]:
    """Build one deduplicated control-plane summary payload."""

    db_path = Path(db_file).expanduser()
    state_path = Path(state_file).expanduser()
    summary = collect_control_plane_summary(
        db_file=db_path,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    summary["state_file"] = str(state_path)
    event = build_control_plane_summary_event(summary, notify_on=notify_on)
    signature = _summary_signature(event.get("facts", {}))
    prior_state = _load_state(state_path)
    changed = signature != str(prior_state.get("signature", "")).strip()
    _save_state(
        state_path,
        {
            "signature": signature,
            "updated_at": utc_now_iso(),
        },
    )
    notify = bool(event["views"]["human"].get("visible", False)) and changed
    human_text = render_human_view(event["views"]["human"]) if notify else "NO_REPLY"
    return {
        "db_file": str(db_path),
        "state_file": str(state_path),
        "notify": notify,
        "summary": summary,
        "event": event,
        "human_text": human_text,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Render one deduplicated control-plane summary event.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--lookback-hours", default="24")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--notify-on", default="activity", choices=["error", "activity", "always"])
    parser.add_argument("--output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the control-plane summary payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_control_plane_summary_payload(
        db_file=str(args.db).strip(),
        state_file=str(args.state_file).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 24)),
        limit=max(1, int(args.limit or 20)),
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

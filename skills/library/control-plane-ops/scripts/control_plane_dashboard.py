#!/usr/bin/env python3
"""Build a static control-plane dashboard snapshot in JSON, Markdown, and HTML."""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
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

from control_plane_summary_runner import collect_control_plane_summary
from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import TaskCenter, utc_now_iso  # type: ignore
from utf8_runtime import configure_process_utf8_stdio
from workflow_views import humanize_task_stage

UTC = timezone.utc
DEFAULT_TREND_DAYS = 7
DEFAULT_WORKFLOW_BREAKDOWN_LIMIT = 6

configure_process_utf8_stdio()


def _load_benchmark_overview(summary_file: str | Path | None) -> dict[str, Any]:
    """Load one optional benchmark sweep summary and normalize overview fields."""

    if not summary_file:
        return {
            "available": False,
            "summary_file": "",
            "requested_suite_ids": [],
            "success_count": 0,
            "failure_count": 0,
            "promoted_count": 0,
            "blocked_count": 0,
            "failures": [],
        }
    path = Path(summary_file).expanduser()
    if not path.exists():
        return {
            "available": False,
            "summary_file": str(path),
            "requested_suite_ids": [],
            "success_count": 0,
            "failure_count": 0,
            "promoted_count": 0,
            "blocked_count": 0,
            "failures": [],
        }

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"benchmark summary must be a JSON object: {path}")
    results = payload.get("results", [])
    if not isinstance(results, list):
        results = []
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        failures = []

    promoted_count = 0
    blocked_count = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        workflow_scorecard = summary.get("workflow_scorecard", {})
        if not isinstance(workflow_scorecard, dict):
            workflow_scorecard = {}
        decision = workflow_scorecard.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}
        if bool(decision.get("promote_to_new_baseline", False)):
            promoted_count += 1
        else:
            blocked_count += 1

    requested_suite_ids = payload.get("requested_suite_ids", [])
    if not isinstance(requested_suite_ids, list):
        requested_suite_ids = []
    return {
        "available": True,
        "summary_file": str(path),
        "requested_suite_ids": [str(item).strip() for item in requested_suite_ids if str(item).strip()],
        "success_count": max(0, int(payload.get("success_count", 0) or 0)),
        "failure_count": max(0, int(payload.get("failure_count", 0) or 0)),
        "promoted_count": promoted_count,
        "blocked_count": blocked_count,
        "failures": failures[:5],
    }


def _format_task_line(item: dict[str, Any]) -> str:
    """Render one focus task line for Markdown and HTML."""

    task_id = str(item.get("task_id", "")).strip() or "unknown-task"
    workflow_profile_id = str(item.get("workflow_profile_id", "")).strip() or "unbound"
    workflow_channel = str(item.get("workflow_channel", "")).strip()
    workflow_stage = humanize_task_stage(str(item.get("stage_id", "")).strip())
    workflow_label = workflow_profile_id
    if workflow_channel:
        workflow_label += f"@{workflow_channel}"
    if workflow_stage:
        workflow_label += f" / {workflow_stage}"
    badges: list[str] = []
    open_incident_count = max(0, int(item.get("open_incident_count", 0) or 0))
    critical_open_incident_count = max(0, int(item.get("critical_open_incident_count", 0) or 0))
    if open_incident_count > 0:
        badges.append(f"open_incidents={open_incident_count}")
    if critical_open_incident_count > 0:
        badges.append(f"critical={critical_open_incident_count}")
    if bool(item.get("requires_human_assistance", False)):
        badges.append("需要人工协助")
    if bool(item.get("waiting_human_confirm", False)):
        badges.append("等待人工确认")
    if bool(item.get("needs_clarification", False)):
        badges.append("待补充上下文")
    if bool(item.get("benchmark_blocked", False)):
        badges.append("benchmark 未通过")
    if bool(item.get("benchmark_promoted", False)):
        badges.append("benchmark 允许晋升")
    return f"- {task_id} {workflow_label}" + (f" -> {'，'.join(badges)}" if badges else "")


def _build_day_buckets(lookback_days: int) -> list[str]:
    """Build daily UTC buckets covering the requested time window."""

    now = datetime.now(tz=UTC).replace(microsecond=0)
    days = max(1, int(lookback_days or DEFAULT_TREND_DAYS))
    start_day = (now - timedelta(days=days - 1)).date()
    return [(start_day + timedelta(days=offset)).isoformat() for offset in range(days)]


def _empty_trend_bucket(day: str) -> dict[str, Any]:
    """Create one empty daily trend bucket."""

    return {
        "day": day,
        "benchmark_run_count": 0,
        "benchmark_promoted_count": 0,
        "benchmark_blocked_count": 0,
        "incident_count": 0,
        "critical_incident_count": 0,
        "human_assistance_count": 0,
    }


def _normalize_workflow_label(value: Any) -> str:
    """Normalize workflow label shown in breakdown views."""

    workflow = str(value or "").strip()
    return workflow or "unbound"


def _merge_metric_row(
    *,
    daily_map: dict[str, dict[str, Any]],
    workflow_map: dict[str, dict[str, Any]],
    day: str,
    workflow_profile_id: str,
    benchmark_run_count: int = 0,
    benchmark_promoted_count: int = 0,
    incident_count: int = 0,
    critical_incident_count: int = 0,
    human_assistance_count: int = 0,
) -> None:
    """Merge one SQL metric row into daily and workflow aggregates."""

    if day in daily_map:
        daily_map[day]["benchmark_run_count"] += max(0, int(benchmark_run_count or 0))
        daily_map[day]["benchmark_promoted_count"] += max(0, int(benchmark_promoted_count or 0))
        daily_map[day]["incident_count"] += max(0, int(incident_count or 0))
        daily_map[day]["critical_incident_count"] += max(0, int(critical_incident_count or 0))
        daily_map[day]["human_assistance_count"] += max(0, int(human_assistance_count or 0))
        daily_map[day]["benchmark_blocked_count"] = max(
            0,
            int(daily_map[day]["benchmark_run_count"]) - int(daily_map[day]["benchmark_promoted_count"]),
        )

    workflow_key = _normalize_workflow_label(workflow_profile_id)
    workflow_entry = workflow_map.setdefault(
        workflow_key,
        {
            "workflow_profile_id": workflow_key,
            "benchmark_run_count": 0,
            "benchmark_promoted_count": 0,
            "benchmark_blocked_count": 0,
            "incident_count": 0,
            "critical_incident_count": 0,
            "human_assistance_count": 0,
        },
    )
    workflow_entry["benchmark_run_count"] += max(0, int(benchmark_run_count or 0))
    workflow_entry["benchmark_promoted_count"] += max(0, int(benchmark_promoted_count or 0))
    workflow_entry["incident_count"] += max(0, int(incident_count or 0))
    workflow_entry["critical_incident_count"] += max(0, int(critical_incident_count or 0))
    workflow_entry["human_assistance_count"] += max(0, int(human_assistance_count or 0))
    workflow_entry["benchmark_blocked_count"] = max(
        0,
        int(workflow_entry["benchmark_run_count"]) - int(workflow_entry["benchmark_promoted_count"]),
    )


def _query_benchmark_trend_rows(task_center: TaskCenter, since_iso: str) -> list[dict[str, Any]]:
    """Query benchmark trend rows grouped by day and workflow."""

    rows = task_center.conn.execute(
        """
        SELECT
            substr(ts, 1, 10) AS day,
            COALESCE(workflow_profile_id, '') AS workflow_profile_id,
            COUNT(*) AS benchmark_run_count,
            SUM(
                CASE
                    WHEN json_extract(decision_json, '$.promote_to_new_baseline') = 1 THEN 1
                    ELSE 0
                END
            ) AS benchmark_promoted_count
        FROM benchmark_runs
        WHERE ts >= ?
        GROUP BY day, workflow_profile_id
        ORDER BY day ASC, workflow_profile_id ASC
        """,
        (since_iso,),
    ).fetchall()
    return [dict(row) for row in rows]


def _query_incident_trend_rows(task_center: TaskCenter, since_iso: str) -> list[dict[str, Any]]:
    """Query incident trend rows grouped by day and workflow."""

    rows = task_center.conn.execute(
        """
        SELECT
            substr(i.ts, 1, 10) AS day,
            COALESCE(t.workflow_profile_id, '') AS workflow_profile_id,
            COUNT(*) AS incident_count,
            SUM(CASE WHEN i.severity = 'critical' THEN 1 ELSE 0 END) AS critical_incident_count
        FROM task_incidents AS i
        LEFT JOIN tasks AS t ON t.task_id = i.task_id
        WHERE i.ts >= ?
        GROUP BY day, workflow_profile_id
        ORDER BY day ASC, workflow_profile_id ASC
        """,
        (since_iso,),
    ).fetchall()
    return [dict(row) for row in rows]


def _query_human_assistance_rows(task_center: TaskCenter, since_iso: str) -> list[dict[str, Any]]:
    """Query human-assistance trend rows grouped by day and workflow."""

    rows = task_center.conn.execute(
        """
        SELECT
            substr(o.ts, 1, 10) AS day,
            COALESCE(t.workflow_profile_id, '') AS workflow_profile_id,
            SUM(
                CASE
                    WHEN json_extract(o.payload_json, '$.human_gate.requires_human_assistance') = 1 THEN 1
                    ELSE 0
                END
            ) AS human_assistance_count
        FROM task_outputs AS o
        LEFT JOIN tasks AS t ON t.task_id = o.task_id
        WHERE o.ts >= ?
        GROUP BY day, workflow_profile_id
        ORDER BY day ASC, workflow_profile_id ASC
        """,
        (since_iso,),
    ).fetchall()
    return [dict(row) for row in rows]


def collect_control_plane_trends(
    *,
    db_file: str | Path,
    lookback_days: int = DEFAULT_TREND_DAYS,
    workflow_limit: int = DEFAULT_WORKFLOW_BREAKDOWN_LIMIT,
) -> dict[str, Any]:
    """Collect daily and workflow trend metrics for the dashboard."""

    days = _build_day_buckets(lookback_days)
    daily_map = {day: _empty_trend_bucket(day) for day in days}
    workflow_map: dict[str, dict[str, Any]] = {}
    since_iso = f"{days[0]}T00:00:00+00:00"

    task_center = TaskCenter(Path(db_file).expanduser())
    try:
        for row in _query_benchmark_trend_rows(task_center, since_iso):
            _merge_metric_row(
                daily_map=daily_map,
                workflow_map=workflow_map,
                day=str(row.get("day", "")).strip(),
                workflow_profile_id=str(row.get("workflow_profile_id", "")).strip(),
                benchmark_run_count=int(row.get("benchmark_run_count", 0) or 0),
                benchmark_promoted_count=int(row.get("benchmark_promoted_count", 0) or 0),
            )
        for row in _query_incident_trend_rows(task_center, since_iso):
            _merge_metric_row(
                daily_map=daily_map,
                workflow_map=workflow_map,
                day=str(row.get("day", "")).strip(),
                workflow_profile_id=str(row.get("workflow_profile_id", "")).strip(),
                incident_count=int(row.get("incident_count", 0) or 0),
                critical_incident_count=int(row.get("critical_incident_count", 0) or 0),
            )
        for row in _query_human_assistance_rows(task_center, since_iso):
            _merge_metric_row(
                daily_map=daily_map,
                workflow_map=workflow_map,
                day=str(row.get("day", "")).strip(),
                workflow_profile_id=str(row.get("workflow_profile_id", "")).strip(),
                human_assistance_count=int(row.get("human_assistance_count", 0) or 0),
            )
    finally:
        task_center.close()

    workflow_breakdown = sorted(
        workflow_map.values(),
        key=lambda item: (
            -int(item.get("benchmark_run_count", 0) or 0),
            -int(item.get("incident_count", 0) or 0),
            str(item.get("workflow_profile_id", "")),
        ),
    )[: max(1, int(workflow_limit or DEFAULT_WORKFLOW_BREAKDOWN_LIMIT))]

    totals = {
        "benchmark_run_count": 0,
        "benchmark_promoted_count": 0,
        "benchmark_blocked_count": 0,
        "incident_count": 0,
        "critical_incident_count": 0,
        "human_assistance_count": 0,
    }
    for bucket in daily_map.values():
        totals["benchmark_run_count"] += int(bucket["benchmark_run_count"])
        totals["benchmark_promoted_count"] += int(bucket["benchmark_promoted_count"])
        totals["benchmark_blocked_count"] += int(bucket["benchmark_blocked_count"])
        totals["incident_count"] += int(bucket["incident_count"])
        totals["critical_incident_count"] += int(bucket["critical_incident_count"])
        totals["human_assistance_count"] += int(bucket["human_assistance_count"])

    return {
        "lookback_days": max(1, int(lookback_days or DEFAULT_TREND_DAYS)),
        "daily": [daily_map[day] for day in days],
        "workflow_breakdown": workflow_breakdown,
        "totals": totals,
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    """Return one safe ratio or None when the denominator is empty."""

    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _safe_average(total: float, count: float) -> float | None:
    """Return one safe average or None when the sample size is empty."""

    if count <= 0:
        return None
    return round(float(total) / float(count), 4)


def build_control_plane_roi_snapshot(
    *,
    summary: dict[str, Any],
    trend_overview: dict[str, Any],
    benchmark_overview: dict[str, Any],
) -> dict[str, Any]:
    """Build one ROI summary from control-plane aggregate metrics."""

    trend_totals = trend_overview.get("totals", {}) if isinstance(trend_overview.get("totals", {}), dict) else {}
    benchmark_run_count = max(
        int(summary.get("benchmark_run_task_count", 0) or 0),
        int(trend_totals.get("benchmark_run_count", 0) or 0),
        int(benchmark_overview.get("success_count", 0) or 0) + int(benchmark_overview.get("failure_count", 0) or 0),
    )
    promoted_count = max(
        int(summary.get("benchmark_promoted_count", 0) or 0),
        int(trend_totals.get("benchmark_promoted_count", 0) or 0),
        int(benchmark_overview.get("promoted_count", 0) or 0),
    )
    blocked_count = max(
        int(summary.get("benchmark_blocked_count", 0) or 0),
        int(trend_totals.get("benchmark_blocked_count", 0) or 0),
        int(benchmark_overview.get("blocked_count", 0) or 0),
    )
    incident_count = max(
        int(summary.get("open_incident_count", 0) or 0),
        int(trend_totals.get("incident_count", 0) or 0),
    )
    human_assistance_count = max(
        int(summary.get("human_assistance_task_count", 0) or 0),
        int(trend_totals.get("human_assistance_count", 0) or 0),
    )
    total_tokens = int(summary.get("total_tokens", 0) or 0)
    total_cost_estimate = float(summary.get("total_cost_estimate", 0.0) or 0.0)
    return {
        "benchmark_sample_size": benchmark_run_count,
        "benchmark_promote_rate": _safe_ratio(promoted_count, benchmark_run_count),
        "benchmark_block_rate": _safe_ratio(blocked_count, benchmark_run_count),
        "incident_per_100_benchmark_runs": _safe_average(incident_count * 100.0, benchmark_run_count),
        "human_assistance_per_100_benchmark_runs": _safe_average(human_assistance_count * 100.0, benchmark_run_count),
        "tokens_per_benchmark_run": _safe_average(total_tokens, benchmark_run_count),
        "cost_per_benchmark_run": _safe_average(total_cost_estimate, benchmark_run_count),
        "tokens_per_promotion": _safe_average(total_tokens, promoted_count),
        "cost_per_promotion": _safe_average(total_cost_estimate, promoted_count),
    }


def _new_roi_breakdown_entry(
    *,
    workflow_profile_id: str,
    stage_id: str = "",
) -> dict[str, Any]:
    """Build one ROI breakdown bucket for workflow or workflow-stage aggregation."""

    return {
        "workflow_profile_id": workflow_profile_id or "unbound",
        "stage_id": stage_id,
        "stage_label": humanize_task_stage(stage_id) if stage_id else "",
        "task_count": 0,
        "benchmark_run_count": 0,
        "benchmark_promoted_count": 0,
        "benchmark_blocked_count": 0,
        "open_incident_task_count": 0,
        "critical_incident_task_count": 0,
        "human_assistance_task_count": 0,
        "total_tokens": 0,
        "total_cost_estimate": 0.0,
    }


def _finalize_roi_breakdown(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Finalize one ROI breakdown list with derived rates and averages."""

    finalized: list[dict[str, Any]] = []
    for raw_entry in entries:
        entry = dict(raw_entry)
        task_count = max(0, int(entry.get("task_count", 0) or 0))
        benchmark_run_count = max(0, int(entry.get("benchmark_run_count", 0) or 0))
        benchmark_promoted_count = max(0, int(entry.get("benchmark_promoted_count", 0) or 0))
        benchmark_blocked_count = max(0, int(entry.get("benchmark_blocked_count", 0) or 0))
        open_incident_task_count = max(0, int(entry.get("open_incident_task_count", 0) or 0))
        critical_incident_task_count = max(0, int(entry.get("critical_incident_task_count", 0) or 0))
        human_assistance_task_count = max(0, int(entry.get("human_assistance_task_count", 0) or 0))
        total_tokens = max(0, int(entry.get("total_tokens", 0) or 0))
        total_cost_estimate = round(float(entry.get("total_cost_estimate", 0.0) or 0.0), 6)
        entry.update(
            {
                "task_count": task_count,
                "benchmark_run_count": benchmark_run_count,
                "benchmark_promoted_count": benchmark_promoted_count,
                "benchmark_blocked_count": benchmark_blocked_count,
                "open_incident_task_count": open_incident_task_count,
                "critical_incident_task_count": critical_incident_task_count,
                "human_assistance_task_count": human_assistance_task_count,
                "total_tokens": total_tokens,
                "total_cost_estimate": total_cost_estimate,
                "benchmark_promote_rate": _safe_ratio(benchmark_promoted_count, benchmark_run_count),
                "benchmark_block_rate": _safe_ratio(benchmark_blocked_count, benchmark_run_count),
                "incident_task_rate": _safe_ratio(open_incident_task_count, task_count),
                "human_assistance_rate": _safe_ratio(human_assistance_task_count, task_count),
                "avg_tokens_per_task": _safe_average(total_tokens, task_count),
                "avg_cost_per_task": _safe_average(total_cost_estimate, task_count),
                "avg_tokens_per_benchmark": _safe_average(total_tokens, benchmark_run_count),
                "avg_cost_per_benchmark": _safe_average(total_cost_estimate, benchmark_run_count),
            }
        )
        finalized.append(entry)
    finalized.sort(
        key=lambda item: (
            -int(item.get("benchmark_blocked_count", 0) or 0),
            -int(item.get("critical_incident_task_count", 0) or 0),
            -int(item.get("open_incident_task_count", 0) or 0),
            -float(item.get("total_cost_estimate", 0.0) or 0.0),
            -int(item.get("task_count", 0) or 0),
            str(item.get("workflow_profile_id", "")),
            str(item.get("stage_id", "")),
        )
    )
    return finalized


def collect_control_plane_roi_breakdown(
    *,
    db_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Collect workflow/stage ROI breakdown from recent control-plane reports."""

    db_path = Path(db_file).expanduser()
    since = (
        datetime.now(tz=UTC) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()

    task_center = TaskCenter(db_path)
    try:
        candidates = task_center.recent_control_plane_task_ids(
            since=since,
            limit=max(1, int(limit or 20)),
            display_safe=False,
        )
        workflow_entries: dict[str, dict[str, Any]] = {}
        stage_entries: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in candidates:
            task_id = str(candidate.get("task_id", "")).strip()
            if not task_id:
                continue
            report = task_center.task_report(task_id, event_limit=200, display_safe=False)
            task = report.get("task", {}) if isinstance(report.get("task", {}), dict) else {}
            control = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
            token_usage = report.get("token_usage_effective", {}) if isinstance(report.get("token_usage_effective", {}), dict) else {}
            latest_benchmark = control.get("latest_benchmark_run", {}) if isinstance(control.get("latest_benchmark_run", {}), dict) else {}
            decision = latest_benchmark.get("decision", {}) if isinstance(latest_benchmark.get("decision", {}), dict) else {}

            workflow_profile_id = str(task.get("workflow_profile_id", "")).strip() or "unbound"
            stage_id = str(task.get("stage_id", "")).strip() or "unknown"
            workflow_entry = workflow_entries.setdefault(
                workflow_profile_id,
                _new_roi_breakdown_entry(workflow_profile_id=workflow_profile_id),
            )
            stage_entry = stage_entries.setdefault(
                (workflow_profile_id, stage_id),
                _new_roi_breakdown_entry(workflow_profile_id=workflow_profile_id, stage_id=stage_id),
            )

            for entry in (workflow_entry, stage_entry):
                entry["task_count"] += 1
                entry["total_tokens"] += max(0, int(token_usage.get("total_tokens", 0) or 0))
                entry["total_cost_estimate"] += float(token_usage.get("cost_estimate", 0.0) or 0.0)
                if int(control.get("open_incident_count", 0) or 0) > 0:
                    entry["open_incident_task_count"] += 1
                if int(control.get("critical_open_incident_count", 0) or 0) > 0:
                    entry["critical_incident_task_count"] += 1
                if bool(control.get("requires_human_assistance", False)):
                    entry["human_assistance_task_count"] += 1
                if latest_benchmark:
                    entry["benchmark_run_count"] += 1
                    if bool(decision.get("promote_to_new_baseline", False)):
                        entry["benchmark_promoted_count"] += 1
                    else:
                        entry["benchmark_blocked_count"] += 1
    finally:
        task_center.close()

    return {
        "workflow_breakdown": _finalize_roi_breakdown(list(workflow_entries.values())),
        "stage_breakdown": _finalize_roi_breakdown(list(stage_entries.values())),
    }


def _render_trend_lines(trend_overview: dict[str, Any]) -> list[str]:
    """Render trend overview lines for Markdown."""

    totals = trend_overview.get("totals", {}) if isinstance(trend_overview.get("totals", {}), dict) else {}
    daily = trend_overview.get("daily", []) if isinstance(trend_overview.get("daily", []), list) else []
    lines = [
        "## 最近趋势",
        f"- 观察窗口：最近 {trend_overview.get('lookback_days', DEFAULT_TREND_DAYS)} 天",
        (
            f"- 累计 benchmark {totals.get('benchmark_run_count', 0)} 次，允许晋升 "
            f"{totals.get('benchmark_promoted_count', 0)} 次，阻断 {totals.get('benchmark_blocked_count', 0)} 次"
        ),
        (
            f"- 累计 incident {totals.get('incident_count', 0)} 条（critical "
            f"{totals.get('critical_incident_count', 0)}），人工协助 {totals.get('human_assistance_count', 0)} 次"
        ),
    ]
    for item in daily[-7:]:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- {day}: benchmark {run_count} / 晋升 {promoted_count} / 阻断 {blocked_count} / "
            "incident {incident_count} / critical {critical_count} / 人工协助 {human_count}".format(
                day=str(item.get("day", "")).strip() or "-",
                run_count=int(item.get("benchmark_run_count", 0) or 0),
                promoted_count=int(item.get("benchmark_promoted_count", 0) or 0),
                blocked_count=int(item.get("benchmark_blocked_count", 0) or 0),
                incident_count=int(item.get("incident_count", 0) or 0),
                critical_count=int(item.get("critical_incident_count", 0) or 0),
                human_count=int(item.get("human_assistance_count", 0) or 0),
            )
        )
    return lines


def _render_workflow_breakdown_lines(trend_overview: dict[str, Any]) -> list[str]:
    """Render workflow breakdown lines for Markdown."""

    lines = ["## Workflow 分布"]
    breakdown = trend_overview.get("workflow_breakdown", [])
    if not isinstance(breakdown, list) or not breakdown:
        lines.append("- 当前窗口内暂无 workflow 历史指标")
        return lines
    for item in breakdown:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- {workflow}: benchmark {run_count} / 晋升 {promoted_count} / 阻断 {blocked_count} / "
            "incident {incident_count} / critical {critical_count} / 人工协助 {human_count}".format(
                workflow=str(item.get("workflow_profile_id", "")).strip() or "unbound",
                run_count=int(item.get("benchmark_run_count", 0) or 0),
                promoted_count=int(item.get("benchmark_promoted_count", 0) or 0),
                blocked_count=int(item.get("benchmark_blocked_count", 0) or 0),
                incident_count=int(item.get("incident_count", 0) or 0),
                critical_count=int(item.get("critical_incident_count", 0) or 0),
                human_count=int(item.get("human_assistance_count", 0) or 0),
            )
        )
    return lines


def _render_roi_lines(roi_snapshot: dict[str, Any]) -> list[str]:
    """Render ROI summary lines for Markdown."""

    def ratio_text(value: float | None) -> str:
        return "-" if value is None else f"{round(value * 100, 2)}%"

    def scalar_text(value: float | None) -> str:
        return "-" if value is None else str(value)

    return [
        "## ROI 摘要",
        f"- benchmark 样本数：{int(roi_snapshot.get('benchmark_sample_size', 0) or 0)}",
        f"- 晋升率：{ratio_text(roi_snapshot.get('benchmark_promote_rate'))}",
        f"- 阻断率：{ratio_text(roi_snapshot.get('benchmark_block_rate'))}",
        f"- 每 100 次 benchmark 的 incident：{scalar_text(roi_snapshot.get('incident_per_100_benchmark_runs'))}",
        f"- 每 100 次 benchmark 的人工协助：{scalar_text(roi_snapshot.get('human_assistance_per_100_benchmark_runs'))}",
        f"- 每次 benchmark 平均 token：{scalar_text(roi_snapshot.get('tokens_per_benchmark_run'))}",
        f"- 每次 benchmark 平均成本：{scalar_text(roi_snapshot.get('cost_per_benchmark_run'))}",
        f"- 每次晋升平均 token：{scalar_text(roi_snapshot.get('tokens_per_promotion'))}",
        f"- 每次晋升平均成本：{scalar_text(roi_snapshot.get('cost_per_promotion'))}",
    ]


def _render_workflow_roi_lines(workflow_roi_breakdown: list[dict[str, Any]]) -> list[str]:
    """Render workflow ROI lines for Markdown."""

    lines = ["## Workflow ROI"]
    if not isinstance(workflow_roi_breakdown, list) or not workflow_roi_breakdown:
        lines.append("- 当前窗口内暂无 workflow ROI 样本")
        return lines
    for item in workflow_roi_breakdown[:8]:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- {workflow}: task {task_count} / benchmark {benchmark_count} / 晋升率 {promote_rate} / "
            "阻断 {blocked_count} / incident_task {incident_count} / 人工协助 {human_count} / 单 task 成本 {avg_cost}".format(
                workflow=str(item.get("workflow_profile_id", "")).strip() or "unbound",
                task_count=int(item.get("task_count", 0) or 0),
                benchmark_count=int(item.get("benchmark_run_count", 0) or 0),
                promote_rate="-" if item.get("benchmark_promote_rate") is None else f"{round(float(item.get('benchmark_promote_rate')) * 100, 2)}%",
                blocked_count=int(item.get("benchmark_blocked_count", 0) or 0),
                incident_count=int(item.get("open_incident_task_count", 0) or 0),
                human_count=int(item.get("human_assistance_task_count", 0) or 0),
                avg_cost="-" if item.get("avg_cost_per_task") is None else str(item.get("avg_cost_per_task")),
            )
        )
    return lines


def _render_stage_roi_lines(stage_roi_breakdown: list[dict[str, Any]]) -> list[str]:
    """Render stage ROI lines for Markdown."""

    lines = ["## Stage ROI"]
    if not isinstance(stage_roi_breakdown, list) or not stage_roi_breakdown:
        lines.append("- 当前窗口内暂无 stage ROI 样本")
        return lines
    for item in stage_roi_breakdown[:10]:
        if not isinstance(item, dict):
            continue
        workflow_profile_id = str(item.get("workflow_profile_id", "")).strip() or "unbound"
        stage_label = str(item.get("stage_label", "")).strip() or humanize_task_stage(str(item.get("stage_id", "")).strip())
        lines.append(
            "- {workflow} / {stage}: task {task_count} / benchmark {benchmark_count} / 晋升率 {promote_rate} / "
            "阻断 {blocked_count} / incident_task {incident_count} / 人工协助 {human_count} / 单 task 成本 {avg_cost}".format(
                workflow=workflow_profile_id,
                stage=stage_label or "未知阶段",
                task_count=int(item.get("task_count", 0) or 0),
                benchmark_count=int(item.get("benchmark_run_count", 0) or 0),
                promote_rate="-" if item.get("benchmark_promote_rate") is None else f"{round(float(item.get('benchmark_promote_rate')) * 100, 2)}%",
                blocked_count=int(item.get("benchmark_blocked_count", 0) or 0),
                incident_count=int(item.get("open_incident_task_count", 0) or 0),
                human_count=int(item.get("human_assistance_task_count", 0) or 0),
                avg_cost="-" if item.get("avg_cost_per_task") is None else str(item.get("avg_cost_per_task")),
            )
        )
    return lines


def render_control_plane_dashboard_markdown(snapshot: dict[str, Any]) -> str:
    """Render one Markdown dashboard snapshot."""

    summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary", {}), dict) else {}
    hotspots = snapshot.get("hotspots", {}) if isinstance(snapshot.get("hotspots", {}), dict) else {}
    benchmark = snapshot.get("benchmark_overview", {}) if isinstance(snapshot.get("benchmark_overview", {}), dict) else {}
    trend_overview = snapshot.get("trend_overview", {}) if isinstance(snapshot.get("trend_overview", {}), dict) else {}
    roi_snapshot = snapshot.get("roi_snapshot", {}) if isinstance(snapshot.get("roi_snapshot", {}), dict) else {}
    workflow_roi_breakdown = snapshot.get("workflow_roi_breakdown", [])
    stage_roi_breakdown = snapshot.get("stage_roi_breakdown", [])
    lines = [
        "# OpenClaw Control Plane Dashboard",
        "",
        f"- 生成时间：{snapshot.get('generated_at', '')}",
        f"- 时间窗口：最近 {summary.get('lookback_hours', 24)} 小时",
        f"- 扫描 task：{summary.get('scanned_task_count', 0)}",
        f"- 未关闭 incident：{summary.get('open_incident_count', 0)}（critical {summary.get('critical_open_incident_count', 0)}）",
        (
            f"- 人工协助：{summary.get('human_assistance_task_count', 0)}，等待确认："
            f"{summary.get('waiting_human_confirm_task_count', 0)}，待澄清：{summary.get('needs_clarification_task_count', 0)}"
        ),
        (
            f"- benchmark：有结果 {summary.get('benchmark_run_task_count', 0)} 个 task，允许晋升 "
            f"{summary.get('benchmark_promoted_count', 0)} 个，未通过 {summary.get('benchmark_blocked_count', 0)} 个"
        ),
        f"- 资源：tokens {summary.get('total_tokens', 0)}，成本估算 {summary.get('total_cost_estimate', 0.0)}",
        "",
        "## Veto 热点",
    ]
    top_veto_reasons = hotspots.get("top_veto_reasons", [])
    if isinstance(top_veto_reasons, list) and top_veto_reasons:
        for item in top_veto_reasons:
            if isinstance(item, dict):
                lines.append(f"- {item.get('reason', '')} x{item.get('count', 0)}")
    else:
        lines.append("- 当前暂无 veto 热点")

    lines.extend(["", "## 重点任务"])
    top_tasks = snapshot.get("top_tasks", [])
    if isinstance(top_tasks, list) and top_tasks:
        for item in top_tasks:
            if isinstance(item, dict):
                lines.append(_format_task_line(item))
    else:
        lines.append("- 当前无重点任务")

    lines.extend(["", "## 最新 Benchmark Sweep"])
    if bool(benchmark.get("available", False)):
        requested_suite_ids = benchmark.get("requested_suite_ids", [])
        suite_text = ", ".join(str(item) for item in requested_suite_ids) if isinstance(requested_suite_ids, list) and requested_suite_ids else "-"
        lines.append(f"- 请求基准集：{suite_text}")
        lines.append(
            f"- 成功 {benchmark.get('success_count', 0)}，失败 {benchmark.get('failure_count', 0)}，允许晋升 {benchmark.get('promoted_count', 0)}，未通过 {benchmark.get('blocked_count', 0)}"
        )
        failures = benchmark.get("failures", [])
        if isinstance(failures, list) and failures:
            for item in failures:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('suite_id', '')} -> {item.get('error_type', 'Error')}: {item.get('error', '')}"
                    )
    else:
        lines.append("- 当前暂无 benchmark sweep 摘要")

    lines.extend([""] + _render_trend_lines(trend_overview))
    lines.extend([""] + _render_workflow_breakdown_lines(trend_overview))
    lines.extend([""] + _render_roi_lines(roi_snapshot))
    lines.extend([""] + _render_workflow_roi_lines(workflow_roi_breakdown))
    lines.extend([""] + _render_stage_roi_lines(stage_roi_breakdown))
    return "\n".join(lines).rstrip() + "\n"


def _html_list(items: list[str]) -> str:
    """Render one simple HTML unordered list."""

    if not items:
        return '<p class="empty">当前暂无数据</p>'
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _html_metric_card(label: str, value: Any) -> str:
    """Render one metric card."""

    return (
        '<div class="metric-card">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(str(value))}</div>'
        "</div>"
    )


def _format_ratio_html(value: float | None) -> str:
    """Format one ratio value for HTML cards."""

    if value is None:
        return "-"
    return f"{round(value * 100, 2)}%"


def _format_scalar_html(value: float | None) -> str:
    """Format one scalar value for HTML cards."""

    if value is None:
        return "-"
    return str(value)


def render_control_plane_dashboard_html(snapshot: dict[str, Any]) -> str:
    """Render one static HTML dashboard snapshot."""

    summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary", {}), dict) else {}
    hotspots = snapshot.get("hotspots", {}) if isinstance(snapshot.get("hotspots", {}), dict) else {}
    benchmark = snapshot.get("benchmark_overview", {}) if isinstance(snapshot.get("benchmark_overview", {}), dict) else {}
    trend_overview = snapshot.get("trend_overview", {}) if isinstance(snapshot.get("trend_overview", {}), dict) else {}
    roi_snapshot = snapshot.get("roi_snapshot", {}) if isinstance(snapshot.get("roi_snapshot", {}), dict) else {}
    workflow_roi_breakdown = snapshot.get("workflow_roi_breakdown", [])
    stage_roi_breakdown = snapshot.get("stage_roi_breakdown", [])

    top_task_items = []
    for item in snapshot.get("top_tasks", []) if isinstance(snapshot.get("top_tasks", []), list) else []:
        if isinstance(item, dict):
            top_task_items.append(html.escape(_format_task_line(item)[2:]))

    veto_items = []
    for item in hotspots.get("top_veto_reasons", []) if isinstance(hotspots.get("top_veto_reasons", []), list) else []:
        if isinstance(item, dict):
            veto_items.append(html.escape(f"{item.get('reason', '')} x{item.get('count', 0)}"))

    benchmark_items: list[str] = []
    if bool(benchmark.get("available", False)):
        requested_suite_ids = benchmark.get("requested_suite_ids", [])
        suite_text = ", ".join(str(item) for item in requested_suite_ids) if isinstance(requested_suite_ids, list) and requested_suite_ids else "-"
        benchmark_items.append(html.escape(f"请求基准集：{suite_text}"))
        benchmark_items.append(
            html.escape(
                f"成功 {benchmark.get('success_count', 0)}，失败 {benchmark.get('failure_count', 0)}，"
                f"允许晋升 {benchmark.get('promoted_count', 0)}，阻断 {benchmark.get('blocked_count', 0)}"
            )
        )
        failures = benchmark.get("failures", [])
        if isinstance(failures, list):
            for item in failures[:5]:
                if isinstance(item, dict):
                    benchmark_items.append(
                        html.escape(
                            f"{item.get('suite_id', '')} -> {item.get('error_type', 'Error')}: {item.get('error', '')}"
                        )
                    )
    else:
        benchmark_items.append("当前暂无 benchmark sweep 摘要")

    totals = trend_overview.get("totals", {}) if isinstance(trend_overview.get("totals", {}), dict) else {}
    trend_cards = [
        _html_metric_card("Benchmark", int(totals.get("benchmark_run_count", 0) or 0)),
        _html_metric_card("允许晋升", int(totals.get("benchmark_promoted_count", 0) or 0)),
        _html_metric_card("阻断", int(totals.get("benchmark_blocked_count", 0) or 0)),
        _html_metric_card("Incident", int(totals.get("incident_count", 0) or 0)),
        _html_metric_card("Critical", int(totals.get("critical_incident_count", 0) or 0)),
        _html_metric_card("人工协助", int(totals.get("human_assistance_count", 0) or 0)),
    ]
    roi_cards = [
        _html_metric_card("ROI 样本数", int(roi_snapshot.get("benchmark_sample_size", 0) or 0)),
        _html_metric_card("晋升率", _format_ratio_html(roi_snapshot.get("benchmark_promote_rate"))),
        _html_metric_card("阻断率", _format_ratio_html(roi_snapshot.get("benchmark_block_rate"))),
        _html_metric_card(
            "每 100 次 benchmark incident",
            _format_scalar_html(roi_snapshot.get("incident_per_100_benchmark_runs")),
        ),
        _html_metric_card(
            "每 100 次 benchmark 人工协助",
            _format_scalar_html(roi_snapshot.get("human_assistance_per_100_benchmark_runs")),
        ),
        _html_metric_card(
            "每次 benchmark 平均 token",
            _format_scalar_html(roi_snapshot.get("tokens_per_benchmark_run")),
        ),
        _html_metric_card(
            "每次 benchmark 平均成本",
            _format_scalar_html(roi_snapshot.get("cost_per_benchmark_run")),
        ),
        _html_metric_card(
            "每次晋升平均 token",
            _format_scalar_html(roi_snapshot.get("tokens_per_promotion")),
        ),
        _html_metric_card(
            "每次晋升平均成本",
            _format_scalar_html(roi_snapshot.get("cost_per_promotion")),
        ),
    ]

    workflow_rows: list[str] = []
    for item in trend_overview.get("workflow_breakdown", []) if isinstance(trend_overview.get("workflow_breakdown", []), list) else []:
        if not isinstance(item, dict):
            continue
        workflow_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('workflow_profile_id', '')).strip() or 'unbound')}</td>"
            f"<td>{int(item.get('benchmark_run_count', 0) or 0)}</td>"
            f"<td>{int(item.get('benchmark_promoted_count', 0) or 0)}</td>"
            f"<td>{int(item.get('benchmark_blocked_count', 0) or 0)}</td>"
            f"<td>{int(item.get('incident_count', 0) or 0)}</td>"
            f"<td>{int(item.get('critical_incident_count', 0) or 0)}</td>"
            f"<td>{int(item.get('human_assistance_count', 0) or 0)}</td>"
            "</tr>"
        )

    workflow_roi_rows: list[str] = []
    for item in workflow_roi_breakdown if isinstance(workflow_roi_breakdown, list) else []:
        if not isinstance(item, dict):
            continue
        workflow_roi_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('workflow_profile_id', '')).strip() or 'unbound')}</td>"
            f"<td>{int(item.get('task_count', 0) or 0)}</td>"
            f"<td>{int(item.get('benchmark_run_count', 0) or 0)}</td>"
            f"<td>{_format_ratio_html(item.get('benchmark_promote_rate'))}</td>"
            f"<td>{int(item.get('benchmark_blocked_count', 0) or 0)}</td>"
            f"<td>{int(item.get('open_incident_task_count', 0) or 0)}</td>"
            f"<td>{int(item.get('human_assistance_task_count', 0) or 0)}</td>"
            f"<td>{_format_scalar_html(item.get('avg_cost_per_task'))}</td>"
            "</tr>"
        )

    stage_roi_rows: list[str] = []
    for item in stage_roi_breakdown if isinstance(stage_roi_breakdown, list) else []:
        if not isinstance(item, dict):
            continue
        stage_roi_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('workflow_profile_id', '')).strip() or 'unbound')}</td>"
            f"<td>{html.escape(str(item.get('stage_label', '')).strip() or humanize_task_stage(str(item.get('stage_id', '')).strip()))}</td>"
            f"<td>{int(item.get('task_count', 0) or 0)}</td>"
            f"<td>{int(item.get('benchmark_run_count', 0) or 0)}</td>"
            f"<td>{_format_ratio_html(item.get('benchmark_promote_rate'))}</td>"
            f"<td>{int(item.get('benchmark_blocked_count', 0) or 0)}</td>"
            f"<td>{int(item.get('open_incident_task_count', 0) or 0)}</td>"
            f"<td>{int(item.get('human_assistance_task_count', 0) or 0)}</td>"
            f"<td>{_format_scalar_html(item.get('avg_cost_per_task'))}</td>"
            "</tr>"
        )

    generated_at = html.escape(str(snapshot.get("generated_at", "")).strip())
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpenClaw Control Plane Dashboard</title>
  <style>
    :root {{
      --bg: #f4f1e8;
      --panel: #fffaf0;
      --ink: #1f2a1f;
      --muted: #5b6357;
      --line: #d7cfbf;
      --accent: #0e7c66;
      --danger: #b63a2b;
      --shadow: 0 12px 30px rgba(33, 42, 30, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(14,124,102,0.12), transparent 28%),
        linear-gradient(180deg, #f9f5ec 0%, var(--bg) 100%);
    }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(14,124,102,0.95), rgba(21,34,28,0.92));
      color: #f7f4ea;
      border-radius: 24px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 34px; }}
    .hero p {{ margin: 6px 0; color: rgba(247,244,234,0.88); }}
    .section {{ margin-top: 24px; background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 22px; box-shadow: var(--shadow); }}
    .section h2 {{ margin: 0 0 16px; font-size: 22px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }}
    .metric-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.75);
    }}
    .metric-label {{ font-size: 13px; color: var(--muted); margin-bottom: 10px; }}
    .metric-value {{ font-size: 28px; font-weight: 700; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 8px 0; line-height: 1.5; }}
    .empty {{ color: var(--muted); margin: 0; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .summary-item {{
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      background: rgba(14,124,102,0.06);
      border-radius: 14px;
    }}
    .summary-item strong {{ display: block; margin-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ color: var(--muted); font-size: 13px; }}
    .danger {{ color: var(--danger); }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>OpenClaw Control Plane Dashboard</h1>
      <p>生成时间：{generated_at}</p>
      <p>最近 {int(summary.get("lookback_hours", 24) or 24)} 小时控制面总览</p>
    </section>

    <section class="section">
      <h2>总览</h2>
      <div class="summary-grid">
        <div class="summary-item"><strong>扫描任务</strong>{int(summary.get("scanned_task_count", 0) or 0)}</div>
        <div class="summary-item"><strong>未关闭 Incident</strong>{int(summary.get("open_incident_count", 0) or 0)}</div>
        <div class="summary-item"><strong>Critical Incident</strong><span class="danger">{int(summary.get("critical_open_incident_count", 0) or 0)}</span></div>
        <div class="summary-item"><strong>人工协助</strong>{int(summary.get("human_assistance_task_count", 0) or 0)}</div>
        <div class="summary-item"><strong>Benchmark 阻断</strong>{int(summary.get("benchmark_blocked_count", 0) or 0)}</div>
        <div class="summary-item"><strong>总 Token</strong>{int(summary.get("total_tokens", 0) or 0)}</div>
      </div>
    </section>

    <section class="section">
      <h2>Veto 热点</h2>
      {_html_list(veto_items)}
    </section>

    <section class="section">
      <h2>重点任务</h2>
      {_html_list(top_task_items)}
    </section>

    <section class="section">
      <h2>最新 Benchmark Sweep</h2>
      {_html_list([html.escape(item) for item in benchmark_items])}
    </section>

    <section class="section">
      <h2>最近趋势</h2>
      <div class="metrics">
        {''.join(trend_cards)}
      </div>
    </section>

    <section class="section">
      <h2>ROI 摘要</h2>
      <div class="metrics">
        {''.join(roi_cards)}
      </div>
    </section>

    <section class="section">
      <h2>Workflow 分布</h2>
      <table>
        <thead>
          <tr>
            <th>Workflow</th>
            <th>Benchmark</th>
            <th>晋升</th>
            <th>阻断</th>
            <th>Incident</th>
            <th>Critical</th>
            <th>人工协助</th>
          </tr>
        </thead>
        <tbody>
          {''.join(workflow_rows) if workflow_rows else '<tr><td colspan="7">当前暂无 workflow 趋势数据</td></tr>'}
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>Workflow ROI</h2>
      <table>
        <thead>
          <tr>
            <th>Workflow</th>
            <th>Task</th>
            <th>Benchmark</th>
            <th>晋升率</th>
            <th>阻断</th>
            <th>Incident Task</th>
            <th>人工协助</th>
            <th>单 Task 成本</th>
          </tr>
        </thead>
        <tbody>
          {''.join(workflow_roi_rows) if workflow_roi_rows else '<tr><td colspan="8">当前暂无 workflow ROI 样本</td></tr>'}
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>Stage ROI</h2>
      <table>
        <thead>
          <tr>
            <th>Workflow</th>
            <th>Stage</th>
            <th>Task</th>
            <th>Benchmark</th>
            <th>晋升率</th>
            <th>阻断</th>
            <th>Incident Task</th>
            <th>人工协助</th>
            <th>单 Task 成本</th>
          </tr>
        </thead>
        <tbody>
          {''.join(stage_roi_rows) if stage_roi_rows else '<tr><td colspan="9">当前暂无 stage ROI 样本</td></tr>'}
        </tbody>
      </table>
    </section>
  </div>
</body>
</html>
"""


def build_control_plane_dashboard_snapshot(
    *,
    db_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 20,
    benchmark_summary_file: str | Path | None = None,
    trend_days: int = DEFAULT_TREND_DAYS,
) -> dict[str, Any]:
    """Build one static dashboard snapshot from control-plane and benchmark data."""

    summary = collect_control_plane_summary(
        db_file=db_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    benchmark_overview = _load_benchmark_overview(benchmark_summary_file)
    trend_overview = collect_control_plane_trends(
        db_file=db_file,
        lookback_days=max(1, int(trend_days or DEFAULT_TREND_DAYS)),
        workflow_limit=DEFAULT_WORKFLOW_BREAKDOWN_LIMIT,
    )
    roi_breakdown = collect_control_plane_roi_breakdown(
        db_file=db_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    roi_snapshot = build_control_plane_roi_snapshot(
        summary=summary,
        trend_overview=trend_overview,
        benchmark_overview=benchmark_overview,
    )
    snapshot = {
        "generated_at": utc_now_iso(),
        "summary": summary,
        "top_tasks": summary.get("top_tasks", []),
        "hotspots": {
            "top_veto_reasons": summary.get("veto_reason_counts", [])[:5],
            "critical_open_incident_count": summary.get("critical_open_incident_count", 0),
            "human_assistance_task_count": summary.get("human_assistance_task_count", 0),
            "benchmark_blocked_count": summary.get("benchmark_blocked_count", 0),
        },
        "benchmark_overview": benchmark_overview,
        "trend_overview": trend_overview,
        "roi_snapshot": roi_snapshot,
        "workflow_roi_breakdown": roi_breakdown.get("workflow_breakdown", []),
        "stage_roi_breakdown": roi_breakdown.get("stage_breakdown", []),
    }
    snapshot["markdown"] = render_control_plane_dashboard_markdown(snapshot)
    snapshot["html"] = render_control_plane_dashboard_html(snapshot)
    return snapshot


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Build one static control-plane dashboard snapshot.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--lookback-hours", default="24")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--benchmark-summary-file", default="")
    parser.add_argument("--trend-days", default=str(DEFAULT_TREND_DAYS))
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--html-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the generated dashboard payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    snapshot = build_control_plane_dashboard_snapshot(
        db_file=str(args.db).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 24)),
        limit=max(1, int(args.limit or 20)),
        benchmark_summary_file=str(args.benchmark_summary_file).strip() or None,
        trend_days=max(1, int(args.trend_days or DEFAULT_TREND_DAYS)),
    )
    payload = {"snapshot": snapshot}
    if str(args.json_output or "").strip():
        write_json_atomic(
            Path(str(args.json_output).strip()).expanduser(),
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            snapshot["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if str(args.html_output or "").strip():
        atomic_write_text(
            Path(str(args.html_output).strip()).expanduser(),
            snapshot["html"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(snapshot["markdown"])
    return payload


if __name__ == "__main__":
    main()

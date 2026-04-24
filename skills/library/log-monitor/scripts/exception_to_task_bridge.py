#!/usr/bin/env python3
"""Scan runtime logs and create deduplicated Task Center tasks for exceptions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_RUNTIME_HOME = (
    os.environ.get("HARDFLOW_RUNTIME_HOME")
    or os.environ.get("OPENCLAW_HOME")
    or os.environ.get("HERMES_HOME")
    or str(Path.home() / ".hardflow-runtime")
)
RUNTIME_HOME = Path(DEFAULT_RUNTIME_HOME).expanduser()
POLICY_DIR_CANDIDATES = [
    SCRIPT_PATH.parent / "policy",
    RUNTIME_HOME / "ops" / "policy",
    Path.home() / ".openclaw" / "ops" / "policy",
    SCRIPT_PATH.parents[2] / "control-plane-ops" / "scripts" / "policy",
]
for candidate in POLICY_DIR_CANDIDATES:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))

from task_center import TaskCenter, TaskCenterError  # noqa: E402
from unified_exception_logger import (  # noqa: E402
    EXCEPTION_CATEGORIES,
    _build_markdown_report,
    _compute_alert_level,
    _exc_to_serializable,
    archive_to_abnormal,
    cleanup_old_reports,
    discover_log_dirs,
    extract_exceptions_from_file,
)


ALERT_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


def default_task_db() -> Path:
    return RUNTIME_HOME / "ops" / "task-center" / "task_center.db"


def scan_exceptions(log_dirs: list[Path], *, scan_since_hours: int) -> dict[str, Any]:
    cutoff_time = datetime.now() - timedelta(hours=max(1, int(scan_since_hours)))
    all_exceptions: list[dict[str, Any]] = []
    scanned_files = 0

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for extension in ("*.log", "*.jsonl", "*.txt", "*.md"):
            for log_file in log_dir.rglob(extension):
                scanned_files += 1
                all_exceptions.extend(extract_exceptions_from_file(log_file, scan_since=cutoff_time))

    seen_fingerprints: Counter[str] = Counter()
    unique_exceptions: list[dict[str, Any]] = []
    for exc in all_exceptions:
        fingerprint = str(exc.get("fingerprint", "")).strip()
        if not fingerprint:
            continue
        seen_fingerprints[fingerprint] += 1
        if seen_fingerprints[fingerprint] == 1:
            unique_exceptions.append(exc)

    for exc in unique_exceptions:
        exc["occurrence_count"] = int(seen_fingerprints[str(exc["fingerprint"])])

    category_stats: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "unique": 0, "samples": []})
    for exc in unique_exceptions:
        category = str(exc.get("category") or "unknown")
        category_stats[category]["count"] += int(exc.get("occurrence_count") or 1)
        category_stats[category]["unique"] += 1
        if len(category_stats[category]["samples"]) < 3:
            category_stats[category]["samples"].append(str(exc.get("line_content", ""))[:150])

    summary = {
        "timestamp": datetime.now().isoformat(),
        "scan_since_hours": scan_since_hours,
        "scanned_files": scanned_files,
        "total_exceptions": sum(seen_fingerprints.values()),
        "unique_exceptions": len(unique_exceptions),
        "category_breakdown": {
            category: {
                "label": EXCEPTION_CATEGORIES.get(category, {}).get("label", category),
                "total": stats["count"],
                "unique": stats["unique"],
            }
            for category, stats in sorted(category_stats.items(), key=lambda item: item[1]["count"], reverse=True)
        },
        "alert_level": _compute_alert_level(category_stats),
    }
    return {"summary": summary, "exceptions": unique_exceptions, "category_stats": category_stats}


def write_reports(
    *,
    scan_result: dict[str, Any],
    output_dir: Path | None,
    abnormal_dir: Path | None,
    task_id: str,
    cleanup: bool,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    if output_dir is None:
        return paths
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = scan_result["summary"]
    exceptions = scan_result["exceptions"]
    category_stats = scan_result["category_stats"]
    json_path = output_dir / f"exception-report-{timestamp}.json"
    md_path = output_dir / f"exception-report-{timestamp}.md"
    json_path.write_text(
        json.dumps(
            {"summary": summary, "exceptions": [_exc_to_serializable(exc) for exc in exceptions]},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    md_path.write_text(_build_markdown_report(summary, category_stats, exceptions), encoding="utf-8")
    paths = {"json": str(json_path), "markdown": str(md_path)}
    if abnormal_dir is not None:
        archive_to_abnormal(abnormal_dir=abnormal_dir, json_path=json_path, md_path=md_path, task_id=task_id)
    if cleanup:
        cleanup_old_reports(output_dir)
        if abnormal_dir is not None:
            cleanup_old_reports(abnormal_dir)
    return paths


def exception_severity(summary: dict[str, Any], exception: dict[str, Any]) -> str:
    category = str(exception.get("category") or "")
    alert_level = str(summary.get("alert_level") or "ok")
    if alert_level == "critical" or category == "system_error":
        return "critical"
    if alert_level == "warning" or category in {"config_error", "filesystem_error", "agent_comm_error"}:
        return "warning"
    return "info"


def build_exception_task(
    *,
    summary: dict[str, Any],
    exception: dict[str, Any],
    report_paths: dict[str, str],
    assignee: str,
    human_assignee: str,
) -> dict[str, Any]:
    fingerprint = str(exception.get("fingerprint", "")).strip()
    category = str(exception.get("category") or "unknown")
    severity = exception_severity(summary, exception)
    needs_human = severity == "critical"
    line_content = str(exception.get("line_content") or "").strip()
    task_id = f"ops-exception-{fingerprint[:16]}"
    return {
        "task_id": task_id,
        "pool": "jobs",
        "task_type": "ops_exception",
        "reason": f"{severity} runtime exception: {category}",
        "source": "exception-to-task-bridge",
        "request_source": "ai",
        "priority": "high" if severity in {"critical", "warning"} else "medium",
        "risk_level": "high" if severity == "critical" else "low",
        "assignee": human_assignee if needs_human else assignee,
        "status": "pending",
        "need_human_confirm": needs_human,
        "human_confirmed": False,
        "action": "await_human_confirm" if needs_human else "investigate",
        "requirement": (
            "Investigate the runtime exception, identify root cause, and create or apply a safe remediation. "
            "Do not perform risky production changes without human confirmation."
        ),
        "result_output": "Root-cause summary, affected runtime scope, remediation plan, and verification evidence.",
        "acceptance": "The exception is resolved, suppressed with reason, or escalated with enough evidence for a human.",
        "observable_outputs": "Task Center task, incident record, exception report, verification output",
        "acceptance_thresholds": "No repeated matching exception in the next scan window, or a human-approved mitigation exists.",
        "context_payload": {
            "bridge": "exception_to_task_bridge",
            "fingerprint": fingerprint,
            "category": category,
            "severity": severity,
            "occurrence_count": int(exception.get("occurrence_count") or 1),
            "source_file": str(exception.get("file") or ""),
            "line_number": exception.get("line_number"),
            "line_content": line_content[:500],
            "report_paths": report_paths,
            "scan_summary": summary,
        },
        "allowed_agents": ["ops-agent", "debugger", "human-inbox"],
        "required_capabilities": ["log_analysis", "runtime_triage", "task_routing"],
        "required_skills": ["log-monitor", "systematic-debugging"],
    }


def create_exception_tasks(
    *,
    scan_result: dict[str, Any],
    task_db: Path,
    report_paths: dict[str, str],
    actor: str,
    assignee: str,
    human_assignee: str,
    min_alert_level: str,
    max_tasks: int,
    dry_run: bool,
) -> dict[str, Any]:
    summary = scan_result["summary"]
    exceptions = sorted(
        scan_result["exceptions"],
        key=lambda exc: (int(exc.get("occurrence_count") or 1), str(exc.get("category") or "")),
        reverse=True,
    )
    min_rank = ALERT_ORDER.get(str(min_alert_level or "info"), 1)
    out: dict[str, Any] = {
        "alert_level": summary.get("alert_level"),
        "total_exceptions": summary.get("total_exceptions"),
        "unique_exceptions": summary.get("unique_exceptions"),
        "created": [],
        "existing": [],
        "planned": [],
        "report_paths": report_paths,
    }
    if ALERT_ORDER.get(str(summary.get("alert_level") or "ok"), 0) < min_rank:
        return out

    selected = exceptions[: max(1, int(max_tasks))]
    planned = [
        build_exception_task(
            summary=summary,
            exception=exc,
            report_paths=report_paths,
            assignee=assignee,
            human_assignee=human_assignee,
        )
        for exc in selected
    ]
    if dry_run:
        out["planned"] = planned
        return out

    center = TaskCenter(task_db)
    try:
        center.init_schema()
        for task, exc in zip(planned, selected):
            task_id = str(task["task_id"])
            try:
                existing = center.get_task(task_id, display_safe=False)
            except TaskCenterError:
                existing = None
            if existing:
                out["existing"].append(task_id)
                continue
            created = center.create_task(task, actor=actor)
            severity = str(task["context_payload"]["severity"])
            center.record_task_incident(
                task_id=task_id,
                incident_type="runtime_exception",
                severity=severity,
                status="open",
                reason=str(task["reason"]),
                summary=str(exc.get("line_content") or "")[:300],
                owner=str(task["assignee"] or ""),
                details=task["context_payload"],
                actor=actor,
            )
            if bool(task.get("need_human_confirm")):
                center.record_task_output(
                    task_id=task_id,
                    output_type="human_question",
                    audience="human",
                    channel="human_inbox",
                    status="prepared",
                    summary=f"Critical runtime exception requires human confirmation: {task_id}",
                    payload={
                        "question": "Critical runtime exception detected. Confirm whether ops-agent may investigate/remediate?",
                        "commands": {
                            "confirm": (
                                "python3 ${HARDFLOW_RUNTIME_HOME:-$HOME/.openclaw}/ops/policy/human_inbox.py "
                                f"confirm --task-db {task_db} --task-id {task_id} --assignee {assignee}"
                            ),
                            "decline": (
                                "python3 ${HARDFLOW_RUNTIME_HOME:-$HOME/.openclaw}/ops/policy/human_inbox.py "
                                f"decline --task-db {task_db} --task-id {task_id}"
                            ),
                        },
                    },
                    actor=actor,
                )
            out["created"].append(created["task_id"])
    finally:
        center.close()
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge runtime exceptions into Task Center tasks.")
    parser.add_argument("--log-dirs", nargs="*", default=[])
    parser.add_argument("--auto-discover", action="store_true")
    parser.add_argument("--openclaw-home", default=str(Path.home() / ".openclaw"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--abnormal-dir", default="")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--scan-since-hours", type=int, default=6)
    parser.add_argument("--task-db", default=str(default_task_db()))
    parser.add_argument("--task-id", default="cron:exception-to-task-bridge")
    parser.add_argument("--actor", default="exception-to-task-bridge")
    parser.add_argument("--assignee", default="ops-agent")
    parser.add_argument("--human-assignee", default="human-inbox")
    parser.add_argument("--min-alert-level", choices=["info", "warning", "critical"], default="info")
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    log_dirs = [Path(item).expanduser() for item in args.log_dirs if str(item).strip()]
    if args.auto_discover:
        for item in discover_log_dirs(str(Path(args.openclaw_home).expanduser())):
            path = Path(item)
            if path not in log_dirs:
                log_dirs.append(path)
    if not log_dirs:
        print("FAILED exception_to_task_bridge: no log dirs", file=sys.stderr)
        return 2

    scan_result = scan_exceptions(log_dirs, scan_since_hours=int(args.scan_since_hours))
    report_paths = write_reports(
        scan_result=scan_result,
        output_dir=Path(args.output_dir).expanduser() if str(args.output_dir).strip() else None,
        abnormal_dir=Path(args.abnormal_dir).expanduser() if str(args.abnormal_dir).strip() else None,
        task_id=str(args.task_id),
        cleanup=bool(args.cleanup),
    )
    task_summary = create_exception_tasks(
        scan_result=scan_result,
        task_db=Path(args.task_db).expanduser().resolve(),
        report_paths=report_paths,
        actor=str(args.actor or args.task_id or "exception-to-task-bridge"),
        assignee=str(args.assignee or "ops-agent"),
        human_assignee=str(args.human_assignee or "human-inbox"),
        min_alert_level=str(args.min_alert_level or "info"),
        max_tasks=int(args.max_tasks),
        dry_run=bool(args.dry_run),
    )
    payload = {"scan": scan_result["summary"], "tasks": task_summary}
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    if not task_summary["created"] and not task_summary["planned"]:
        print("NO_REPLY")
        return 0
    print(
        "exception_to_task_bridge "
        f"alert={task_summary['alert_level']} created={len(task_summary['created'])} "
        f"existing={len(task_summary['existing'])} planned={len(task_summary['planned'])}"
    )
    for task_id in task_summary["created"]:
        print(f"task_created task_id={task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

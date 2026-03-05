#!/usr/bin/env python3
"""Weekly self-evolution reviewer.

Hard boundary:
- Only outputs suggestions and task packages.
- Does NOT modify workflow or skills automatically.
- Pushes low-priority, high-risk tasks into TODO queue for human confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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

from task_center import TaskCenter  # type: ignore
from io_write_gateway import FileWriteError, write_json_atomic  # type: ignore

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "self-evolution-agent/weekly-review"


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


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
    return POLICY_DIR / "policy_enforcer.py"


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

    actor_name = str(actor or "self-evolution-agent").strip() or "self-evolution-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "optimization-agent"
    source_name = str(source_module or "self-evolution-agent/weekly-review").strip() or "self-evolution-agent/weekly-review"
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


def quality_grade_from_score(score: float) -> str:
    value = max(0.0, min(float(score), 100.0))
    if value >= 95:
        return "a+"
    if value >= 90:
        return "a"
    if value >= 80:
        return "b"
    if value >= 70:
        return "c"
    return "d"


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


def parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-02",
        "runs": 0,
        "updated_at": "",
        "last_full_review_at": "",
        "last_report_file": "",
        "fingerprints": {},
    }


def should_run_weekly(last_review_at: str, min_days: int, force: bool) -> bool:
    if force:
        return True
    if not str(last_review_at or "").strip():
        return True
    dt = parse_iso(last_review_at)
    if dt is None:
        return True
    return (now() - dt) >= timedelta(days=max(1, int(min_days)))


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def parse_fingerprint(text: str) -> str:
    m = re.search(r"\[fingerprint:([a-f0-9]{8,40})\]", str(text or ""), flags=re.IGNORECASE)
    return str(m.group(1)).lower() if m else ""


def candidate_fingerprint(title: str, requirement: str) -> str:
    raw = f"{title}\n{requirement}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def collect_open_fingerprints(tc: TaskCenter) -> set[str]:
    rows = tc.conn.execute(
        """
        SELECT requirement
        FROM tasks
        WHERE source = 'self-evolution-agent'
          AND pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        fp = parse_fingerprint(str(row["requirement"] or ""))
        if fp:
            out.add(fp)
    return out


def infer_next_schedule_base(tc: TaskCenter) -> datetime:
    row = tc.conn.execute(
        """
        SELECT scheduled_at, created_at
        FROM tasks
        WHERE pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        ORDER BY COALESCE(scheduled_at, created_at) DESC, created_at DESC
        LIMIT 1
        """
    ).fetchone()
    base = now()
    if row:
        chosen = parse_iso(str(row["scheduled_at"] or row["created_at"] or ""))
        if chosen and chosen > base:
            base = chosen
    return base


def clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 100.0))


def build_agent_scorecards(
    tc: TaskCenter,
    *,
    since: str,
    score_threshold: float,
    min_reports: int,
    top_n: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    min_reports_norm = max(1, int(min_reports))
    top_n_norm = max(1, int(top_n))

    report_rows = tc.conn.execute(
        """
        SELECT
          agent_id,
          COUNT(*) AS report_count,
          SUM(CASE WHEN solved = 1 THEN 1 ELSE 0 END) AS solved_count,
          SUM(CASE WHEN solved = 0 OR status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS failed_count,
          AVG(COALESCE(quality_score, 0)) AS avg_quality_score,
          SUM(total_tokens) AS total_tokens,
          SUM(cost_estimate) AS total_cost,
          AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
        FROM agent_task_reports
        WHERE ts >= ?
        GROUP BY agent_id
        ORDER BY report_count DESC, total_tokens DESC
        """,
        (since,),
    ).fetchall()
    report_map: dict[str, dict[str, Any]] = {}
    for row in report_rows:
        report_map[str(row["agent_id"] or "")] = {
            "report_count": int(row["report_count"] or 0),
            "solved_count": int(row["solved_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "avg_quality_score": float(row["avg_quality_score"] or 0.0),
            "total_tokens": int(row["total_tokens"] or 0),
            "total_cost": float(row["total_cost"] or 0.0),
            "avg_duration_ms": int(float(row["avg_duration_ms"] or 0.0)),
        }

    points_rows = tc.conn.execute(
        """
        SELECT
          actor_id AS agent_id,
          COUNT(*) AS point_records,
          SUM(points) AS total_points,
          AVG(points) AS avg_points
        FROM agent_points_ledger
        WHERE actor_type = 'agent' AND ts >= ?
        GROUP BY actor_id
        ORDER BY total_points DESC
        """,
        (since,),
    ).fetchall()
    points_map: dict[str, dict[str, Any]] = {}
    for row in points_rows:
        points_map[str(row["agent_id"] or "")] = {
            "point_records": int(row["point_records"] or 0),
            "total_points": float(row["total_points"] or 0.0),
            "avg_points": float(row["avg_points"] or 0.0),
        }

    task_rows = tc.conn.execute(
        """
        SELECT
          COALESCE(NULLIF(assignee, ''), 'unassigned') AS assignee,
          COUNT(*) AS task_count,
          SUM(CASE WHEN status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS failed_task_count
        FROM tasks
        WHERE created_at >= ?
        GROUP BY COALESCE(NULLIF(assignee, ''), 'unassigned')
        ORDER BY task_count DESC
        """,
        (since,),
    ).fetchall()
    task_map: dict[str, dict[str, Any]] = {}
    for row in task_rows:
        task_map[str(row["assignee"] or "")] = {
            "task_count": int(row["task_count"] or 0),
            "failed_task_count": int(row["failed_task_count"] or 0),
        }

    risk_rows = tc.conn.execute(
        """
        SELECT
          COALESCE(NULLIF(assignee, ''), 'unassigned') AS assignee,
          SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_total,
          SUM(CASE WHEN risk_level = 'high' AND status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS high_risk_failed
        FROM tasks
        WHERE created_at >= ?
        GROUP BY COALESCE(NULLIF(assignee, ''), 'unassigned')
        """,
        (since,),
    ).fetchall()
    risk_map: dict[str, dict[str, Any]] = {}
    for row in risk_rows:
        risk_map[str(row["assignee"] or "")] = {
            "high_risk_total": int(row["high_risk_total"] or 0),
            "high_risk_failed": int(row["high_risk_failed"] or 0),
        }

    agent_ids = sorted(set(report_map) | set(points_map) | set(task_map) | set(risk_map))
    max_points = 0.0
    for info in points_map.values():
        max_points = max(max_points, float(info.get("total_points", 0.0) or 0.0))

    score_threshold_norm = clamp_score(score_threshold)
    cards: list[dict[str, Any]] = []
    for agent_id in agent_ids:
        if not agent_id:
            continue
        report_info = report_map.get(agent_id, {})
        points_info = points_map.get(agent_id, {})
        task_info = task_map.get(agent_id, {})
        risk_info = risk_map.get(agent_id, {})

        report_count = int(report_info.get("report_count", 0))
        solved_count = int(report_info.get("solved_count", 0))
        failed_count = int(report_info.get("failed_count", 0))
        quality_avg = clamp_score(float(report_info.get("avg_quality_score", 0.0) or 0.0))
        total_tokens = int(report_info.get("total_tokens", 0))
        total_cost = float(report_info.get("total_cost", 0.0) or 0.0)
        avg_duration_ms = int(report_info.get("avg_duration_ms", 0))

        point_records = int(points_info.get("point_records", 0))
        total_points = float(points_info.get("total_points", 0.0) or 0.0)
        avg_points = float(points_info.get("avg_points", 0.0) or 0.0)

        task_count = int(task_info.get("task_count", 0))
        failed_task_count = int(task_info.get("failed_task_count", 0))
        high_risk_total = int(risk_info.get("high_risk_total", 0))
        high_risk_failed = int(risk_info.get("high_risk_failed", 0))

        if report_count <= 0 and point_records <= 0 and task_count <= 0:
            continue

        has_enough_data = bool(report_count >= min_reports_norm or task_count >= min_reports_norm)

        if report_count > 0:
            solved_ratio = safe_ratio(solved_count, report_count)
            failure_ratio = safe_ratio(failed_count, report_count)
            quality_score = quality_avg
        else:
            solved_ratio = 0.0
            failure_ratio = safe_ratio(failed_task_count, max(1, task_count))
            quality_score = 60.0

        risk_fail_ratio = safe_ratio(high_risk_failed, high_risk_total) if high_risk_total > 0 else 0.0
        risk_control_score = 100.0 if high_risk_total <= 0 else clamp_score((1.0 - risk_fail_ratio) * 100.0)

        points_norm = 60.0
        if max_points > 0:
            points_norm = clamp_score((total_points / max_points) * 100.0)

        solved_score = clamp_score(solved_ratio * 100.0)
        reliability_score = clamp_score((1.0 - failure_ratio) * 100.0)
        comprehensive = clamp_score(
            quality_score * 0.35
            + solved_score * 0.20
            + reliability_score * 0.20
            + risk_control_score * 0.15
            + points_norm * 0.10
        )

        reasons: list[str] = []
        if comprehensive < score_threshold_norm:
            reasons.append(f"comprehensive<{score_threshold_norm:.1f}")
        if failure_ratio >= 0.30:
            reasons.append(f"failure_ratio={failure_ratio:.2f}")
        if quality_score < 70.0:
            reasons.append(f"quality<{70.0:.1f}")
        if (report_count >= min_reports_norm) and solved_score < 70.0:
            reasons.append(f"solved_ratio={solved_ratio:.2f}")
        if high_risk_total >= 2 and risk_fail_ratio >= 0.40:
            reasons.append(f"high_risk_fail_ratio={risk_fail_ratio:.2f}")

        cards.append(
            {
                "agent_id": agent_id,
                "report_count": report_count,
                "task_count": task_count,
                "point_records": point_records,
                "avg_quality_score": round(quality_score, 2),
                "solved_ratio": round(solved_ratio, 4),
                "failure_ratio": round(failure_ratio, 4),
                "solved_ratio_pct": round(solved_score, 2),
                "failure_ratio_pct": round(failure_ratio * 100.0, 2),
                "high_risk_total": high_risk_total,
                "high_risk_failed": high_risk_failed,
                "risk_fail_ratio": round(risk_fail_ratio, 4),
                "risk_control_score": round(risk_control_score, 2),
                "total_points": round(total_points, 4),
                "avg_points": round(avg_points, 4),
                "points_norm_score": round(points_norm, 2),
                "total_tokens": total_tokens,
                "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
                "total_cost": round(total_cost, 6),
                "avg_duration_ms": avg_duration_ms,
                "comprehensive_score": round(comprehensive, 2),
                "comprehensive_grade": quality_grade_from_score(comprehensive),
                "has_enough_data": has_enough_data,
                "needs_optimization": bool(reasons) and has_enough_data,
                "reasons": reasons,
            }
        )

    cards.sort(
        key=lambda item: (
            0 if bool(item.get("needs_optimization")) else 1,
            float(item.get("comprehensive_score", 0.0)),
            -int(item.get("report_count", 0)),
        )
    )
    reviewed = len(cards)
    needs_opt_count = sum(1 for item in cards if bool(item.get("needs_optimization")))
    avg_score = (
        round(sum(float(item.get("comprehensive_score", 0.0)) for item in cards) / reviewed, 2)
        if reviewed > 0
        else 0.0
    )
    summary = {
        "agent_count_reviewed": reviewed,
        "agent_count_needs_optimization": needs_opt_count,
        "average_comprehensive_score": avg_score,
        "score_threshold": round(score_threshold_norm, 2),
        "min_reports": min_reports_norm,
    }
    return cards[:top_n_norm], summary


def collect_metrics(
    tc: TaskCenter,
    lookback_days: int,
    *,
    agent_score_threshold: float,
    agent_score_min_reports: int,
    agent_score_top_n: int,
) -> dict[str, Any]:
    since = (now() - timedelta(days=max(1, int(lookback_days)))).isoformat()
    metrics: dict[str, Any] = {
        "since": since,
        "agent_score_threshold": round(clamp_score(agent_score_threshold), 2),
        "agent_score_min_reports": max(1, int(agent_score_min_reports)),
        "agent_score_top_n": max(1, int(agent_score_top_n)),
    }

    agent_rows = tc.conn.execute(
        """
        SELECT
          COALESCE(NULLIF(assignee, ''), 'unassigned') AS assignee,
          COUNT(*) AS total,
          SUM(CASE WHEN status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS failed
        FROM tasks
        WHERE created_at >= ?
        GROUP BY COALESCE(NULLIF(assignee, ''), 'unassigned')
        HAVING COUNT(*) >= 3
        ORDER BY failed DESC, total DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    agent_health: list[dict[str, Any]] = []
    for row in agent_rows:
        total = int(row["total"] or 0)
        failed = int(row["failed"] or 0)
        agent_health.append(
            {
                "assignee": str(row["assignee"] or ""),
                "total": total,
                "failed": failed,
                "failure_ratio": round(safe_ratio(failed, total), 4),
            }
        )
    metrics["agent_health"] = agent_health

    stage_rows = tc.conn.execute(
        """
        SELECT
          stage,
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
          AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
        FROM stage_runs
        WHERE started_at >= ?
        GROUP BY stage
        HAVING COUNT(*) >= 3
        ORDER BY failed DESC, total DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    stage_health: list[dict[str, Any]] = []
    for row in stage_rows:
        total = int(row["total"] or 0)
        failed = int(row["failed"] or 0)
        stage_health.append(
            {
                "stage": str(row["stage"] or ""),
                "total": total,
                "failed": failed,
                "failure_ratio": round(safe_ratio(failed, total), 4),
                "avg_duration_ms": int(float(row["avg_duration_ms"] or 0.0)),
            }
        )
    metrics["stage_health"] = stage_health

    token_rows = tc.conn.execute(
        """
        SELECT
          task_id,
          SUM(total_tokens) AS total_tokens,
          SUM(cost_estimate) AS total_cost
        FROM token_usage
        WHERE ts >= ?
        GROUP BY task_id
        ORDER BY total_tokens DESC
        LIMIT 8
        """,
        (since,),
    ).fetchall()
    heavy_tasks: list[dict[str, Any]] = []
    for row in token_rows:
        heavy_tasks.append(
            {
                "task_id": str(row["task_id"] or ""),
                "total_tokens": int(row["total_tokens"] or 0),
                "total_tokens_m": round(int(row["total_tokens"] or 0) / 1_000_000.0, 6),
                "total_cost": round(float(row["total_cost"] or 0.0), 6),
            }
        )
    metrics["heavy_tasks"] = heavy_tasks

    scorecards, score_summary = build_agent_scorecards(
        tc,
        since=since,
        score_threshold=float(agent_score_threshold),
        min_reports=int(agent_score_min_reports),
        top_n=int(agent_score_top_n),
    )
    metrics["agent_scorecards"] = scorecards
    metrics["agent_score_summary"] = score_summary

    return metrics


def build_candidates(
    metrics: dict[str, Any],
    *,
    low_score_guarantee_enabled: bool = True,
    low_score_guarantee_min_agents: int = 2,
    low_score_guarantee_max_agents: int = 6,
    low_score_guarantee_threshold: float | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    since = str(metrics.get("since", ""))
    agent_health = metrics.get("agent_health", []) if isinstance(metrics.get("agent_health"), list) else []
    stage_health = metrics.get("stage_health", []) if isinstance(metrics.get("stage_health"), list) else []
    heavy_tasks = metrics.get("heavy_tasks", []) if isinstance(metrics.get("heavy_tasks"), list) else []
    agent_scorecards = metrics.get("agent_scorecards", []) if isinstance(metrics.get("agent_scorecards"), list) else []
    score_threshold = clamp_score(float(metrics.get("agent_score_threshold", 70.0) or 70.0))
    low_score_threshold = (
        score_threshold if low_score_guarantee_threshold is None else clamp_score(float(low_score_guarantee_threshold))
    )
    guarantee_enabled = bool(low_score_guarantee_enabled)
    guarantee_min_agents = max(1, int(low_score_guarantee_min_agents))
    guarantee_max_agents = max(guarantee_min_agents, int(low_score_guarantee_max_agents))

    low_score_agents: list[dict[str, Any]] = []
    for item in agent_scorecards:
        if not isinstance(item, dict):
            continue
        score = clamp_score(float(item.get("comprehensive_score", 0.0) or 0.0))
        if bool(item.get("needs_optimization")) or (score <= low_score_threshold):
            low_score_agents.append(item)
    low_score_agents.sort(
        key=lambda item: (
            float(item.get("comprehensive_score", 0.0) or 0.0),
            -int(item.get("report_count", 0) or 0),
        )
    )

    guarantee_targets: list[dict[str, Any]] = []
    if guarantee_enabled and low_score_agents:
        guarantee_targets = low_score_agents[:guarantee_max_agents]
        for item in guarantee_targets:
            agent_id = str(item.get("agent_id", "")).strip()
            if not agent_id:
                continue
            reasons_raw = item.get("reasons", [])
            reasons = []
            if isinstance(reasons_raw, list):
                reasons = [str(x).strip() for x in reasons_raw if str(x).strip()]
            score = round(clamp_score(float(item.get("comprehensive_score", 0.0) or 0.0)), 2)
            quality = round(clamp_score(float(item.get("avg_quality_score", 0.0) or 0.0)), 2)
            failure_pct = round(clamp_score(float(item.get("failure_ratio_pct", 0.0) or 0.0)), 2)
            solved_pct = round(clamp_score(float(item.get("solved_ratio_pct", 0.0) or 0.0)), 2)
            risk_fail_pct = round(
                max(0.0, min(float(item.get("risk_fail_ratio", 0.0) or 0.0), 1.0)) * 100.0,
                2,
            )
            requirement = (
                f"Review window: {since}\n"
                f"Target agent: {agent_id}\n"
                f"Comprehensive score: {score} (guarantee threshold: {round(low_score_threshold, 2)})\n"
                f"Quality={quality}, Failure={failure_pct}%, Solved={solved_pct}%, HighRiskFailure={risk_fail_pct}%\n"
                f"Scorecard reasons: {', '.join(reasons[:6]) if reasons else 'score_below_threshold'}\n"
                "Generate an optimization task package with measurable actions, risk controls, and rollback strategy; "
                "submit to TODO only and do not auto-apply workflow changes."
            )
            candidates.append(
                {
                    "title": f"Weekly low-score guarantee optimization for {agent_id}",
                    "reason": "Low score agent selected by self-evolution guarantee policy",
                    "requirement": requirement,
                    "assignee": "optimization-agent",
                }
            )
    metrics["low_score_guarantee"] = {
        "enabled": guarantee_enabled,
        "threshold": round(low_score_threshold, 2),
        "min_agents": guarantee_min_agents,
        "max_agents": guarantee_max_agents,
        "candidate_pool_count": len(low_score_agents),
        "selected_count": len(guarantee_targets),
        "selected_agents": [str(item.get("agent_id", "")).strip() for item in guarantee_targets],
        "guarantee_hit": len(guarantee_targets) >= guarantee_min_agents,
    }
    if low_score_agents:
        top = "; ".join(
            (
                f"{x.get('agent_id')}:score={x.get('comprehensive_score')},"
                f"quality={x.get('avg_quality_score')},fail={x.get('failure_ratio_pct')}%,"
                f"solve={x.get('solved_ratio_pct')}%,risk_fail={round(float(x.get('risk_fail_ratio', 0.0)) * 100.0, 2)}%"
            )
            for x in low_score_agents[:8]
        )
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"Agent 综合评估触发阈值: {score_threshold}\n"
            f"低分/高风险 agent: {top}\n"
            "请先完成“全面评估”（质量、稳定性、风险、积分、token成本、时效），"
            "再输出针对性优化任务包（策略/流程/技能/路由），禁止自动改配置；仅生成 TODO 待人工确认。"
        )
        candidates.append(
            {
                "title": "周度Agent综合评分与全量评估优化包",
                "reason": "自我进化复盘发现agent综合评分偏低或高风险失败偏高，需要先评估再优化",
                "requirement": requirement,
                "assignee": "optimization-agent",
            }
        )

    unstable_agents = [x for x in agent_health if float(x.get("failure_ratio", 0)) >= 0.30]
    if unstable_agents:
        top = ", ".join(
            f"{x.get('assignee')}({x.get('failed')}/{x.get('total')})" for x in unstable_agents[:5]
        )
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"识别到执行稳定性偏低的agent: {top}\n"
            "请输出优化任务包（修改/升级/删除建议），但禁止自动执行变更；仅允许提交给 TODO 并等待人工确认。"
        )
        candidates.append(
            {
                "title": "周度Agent稳定性优化建议包",
                "reason": "自我进化复盘发现部分agent失败率偏高，需要人工确认后优化",
                "requirement": requirement,
                "assignee": "optimization-agent",
            }
        )

    bad_stages = [x for x in stage_health if int(x.get("failed", 0)) > 0]
    if bad_stages:
        top = ", ".join(
            f"{x.get('stage')}({x.get('failed')}/{x.get('total')},avg={x.get('avg_duration_ms')}ms)"
            for x in bad_stages[:5]
        )
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"识别到流程热点: {top}\n"
            "请拆解成可执行任务包交给规划者分发，不允许直接修改工作流主配置。"
        )
        candidates.append(
            {
                "title": "周度工作流瓶颈与错误热点建议包",
                "reason": "自我进化复盘发现流程阶段异常，需要先任务化再优化",
                "requirement": requirement,
                "assignee": "coordinator",
            }
        )

    if heavy_tasks:
        top = ", ".join(f"{x.get('task_id')}({x.get('total_tokens_m')}M)" for x in heavy_tasks[:6])
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"高token任务: {top}\n"
            "请输出成本优化建议与路由优化建议，涉及技能增删改必须人工确认后执行。"
        )
        candidates.append(
            {
                "title": "周度成本与路由优化建议包",
                "reason": "自我进化复盘发现token成本偏高，需要人工确认后推进",
                "requirement": requirement,
                "assignee": "optimization-agent",
            }
        )

    if not candidates:
        candidates.append(
            {
                "title": "周度经验沉淀建议包",
                "reason": "自我进化常规复盘，沉淀可复用经验并任务化",
                "requirement": (
                    f"周度复盘窗口: {since}\n"
                    "总结可复用经验、流程改进点、技能治理建议；仅产出任务包到 TODO，不自动改配置。"
                ),
                "assignee": "coordinator",
            }
        )
    return candidates


def create_todo_tasks(
    tc: TaskCenter,
    *,
    candidates: list[dict[str, Any]],
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_fingerprints = collect_open_fingerprints(tc)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    base = infer_next_schedule_base(tc)
    limit = max(1, int(max_tasks_per_run))
    gap = max(1, int(schedule_gap_minutes))

    for candidate in candidates:
        title = str(candidate.get("title", "")).strip()
        reason = str(candidate.get("reason", "")).strip()
        requirement_raw = str(candidate.get("requirement", "")).strip()
        assignee = str(candidate.get("assignee", "coordinator")).strip() or "coordinator"
        if not title or not requirement_raw:
            continue

        fp = candidate_fingerprint(title=title, requirement=requirement_raw)
        if fp in open_fingerprints:
            skipped.append({"fingerprint": fp, "reason": "already_open"})
            continue
        if len(created) >= limit:
            skipped.append({"fingerprint": fp, "reason": "run_limit_reached"})
            continue

        schedule_at = (base + timedelta(minutes=gap * (len(created) + 1))).replace(microsecond=0).isoformat()
        requirement = f"[fingerprint:{fp}]\n{requirement_raw}"
        payload = {
            "task_id": f"todo-self-evolution-{now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            "pool": "todo",
            "task_type": "self_evolution",
            "reason": f"[SELF_EVOLUTION] {reason}",
            "source": "self-evolution-agent",
            "priority": "low",
            "risk_level": "high",
            "assignee": assignee,
            "status": "pending",
            "need_human_confirm": True,
            "human_confirmed": False,
            "requirement": requirement,
            "result_output": "输出建议与任务包，提交给规划者；不得自动改工作流",
            "acceptance": "任务包字段完整、可追溯、可人工审批",
            "observable_outputs": "task_center记录/建议包json/周报摘要",
            "acceptance_thresholds": "建议>=1条；包含风险与回滚说明；人工确认后才执行",
            "scheduled_at": schedule_at,
        }
        task = tc.create_task(payload, actor="self-evolution-agent")
        tc.add_event(
            task_id=task["task_id"],
            actor="self-evolution-agent",
            event_type="self_evolution_task_packaged",
            stage="weekly_review",
            details={"fingerprint": fp, "scheduled_at": schedule_at},
        )
        created.append(
            {
                "task_id": task["task_id"],
                "fingerprint": fp,
                "scheduled_at": schedule_at,
                "title": title,
                "assignee": assignee,
            }
        )
        open_fingerprints.add(fp)
    return created, skipped


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Weekly self-evolution TODO packager")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/self-evolution/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/self-evolution/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--min-review-interval-days", type=int, default=7)
    parser.add_argument("--max-tasks-per-run", type=int, default=3)
    parser.add_argument("--schedule-gap-minutes", type=int, default=120)
    parser.add_argument("--agent-score-threshold", type=float, default=70.0)
    parser.add_argument("--agent-score-min-reports", type=int, default=3)
    parser.add_argument("--agent-score-top-n", type=int, default=12)
    parser.add_argument("--low-score-guarantee-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--low-score-guarantee-min-agents", type=int, default=2)
    parser.add_argument("--low-score-guarantee-max-agents", type=int, default=6)
    parser.add_argument("--low-score-guarantee-threshold", type=float, default=70.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)
    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = state_default()

    run_allowed = should_run_weekly(
        last_review_at=str(state.get("last_full_review_at", "")),
        min_days=int(args.min_review_interval_days),
        force=bool(args.force),
    )

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    run_errors: list[str] = []
    try:
        if run_allowed:
            tc = TaskCenter(Path(args.db).expanduser())
            try:
                tc.init_schema()
                metrics = collect_metrics(
                    tc,
                    lookback_days=int(args.lookback_days),
                    agent_score_threshold=float(args.agent_score_threshold),
                    agent_score_min_reports=int(args.agent_score_min_reports),
                    agent_score_top_n=int(args.agent_score_top_n),
                )
                candidates = build_candidates(
                    metrics,
                    low_score_guarantee_enabled=bool(args.low_score_guarantee_enabled),
                    low_score_guarantee_min_agents=max(1, int(args.low_score_guarantee_min_agents)),
                    low_score_guarantee_max_agents=max(1, int(args.low_score_guarantee_max_agents)),
                    low_score_guarantee_threshold=float(args.low_score_guarantee_threshold),
                )
                created, skipped = create_todo_tasks(
                    tc,
                    candidates=candidates,
                    max_tasks_per_run=int(args.max_tasks_per_run),
                    schedule_gap_minutes=int(args.schedule_gap_minutes),
                )
            finally:
                tc.close()
    except Exception as exc:
        run_errors.append(f"self_evolution_run_failed:{exc}")

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "run_allowed": run_allowed,
        "normal_log_mode": log_mode,
        "lookback_days": int(args.lookback_days),
        "min_review_interval_days": int(args.min_review_interval_days),
        "max_tasks_per_run": int(args.max_tasks_per_run),
        "agent_score_threshold": round(clamp_score(float(args.agent_score_threshold)), 2),
        "agent_score_min_reports": max(1, int(args.agent_score_min_reports)),
        "agent_score_top_n": max(1, int(args.agent_score_top_n)),
        "low_score_guarantee_enabled": bool(args.low_score_guarantee_enabled),
        "low_score_guarantee_min_agents": max(1, int(args.low_score_guarantee_min_agents)),
        "low_score_guarantee_max_agents": max(1, int(args.low_score_guarantee_max_agents)),
        "low_score_guarantee_threshold": round(clamp_score(float(args.low_score_guarantee_threshold)), 2),
        "candidates_count": len(candidates),
        "created_count": len(created),
        "created": created,
        "skipped": skipped,
        "metrics": metrics,
        "run_errors": run_errors,
    }

    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms

    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    db_file = Path(args.db).expanduser()
    if db_file.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_file)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_file,
                raw_task_id,
                "self-evolution-agent",
                "self-evolution-agent/weekly-review",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        module_args = [
            "log-module",
            "--module-name",
            "self-evolution-agent/weekly-review",
            "--phase",
            "weekly_review",
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            (
                "self evolution weekly run finished: "
                + f"candidates={len(candidates)} created={len(created)}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "run_allowed": bool(run_allowed),
                    "candidates_count": len(candidates),
                    "created_count": len(created),
                    "run_error_count": len(run_errors),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "self-evolution-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(db_file, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "self-evolution-agent/weekly-review",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "self_evolution_result",
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
                    "created_count": len(created),
                    "candidate_count": len(candidates),
                    "run_allowed": bool(run_allowed),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "self-evolution-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_file, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        report_count = 0
        for item in created:
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            success = not run_errors
            quality_score = 90.0 if success else 55.0
            report_args = [
                "report-agent-result",
                "--task-id",
                task_id,
                "--agent-id",
                "self-evolution-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("passed" if success else "partial"),
                "--solved",
                ("true" if success else "false"),
                "--resolved-issues",
                "self_evolution_todo_packaged",
                "--resolution-summary",
                (
                    "self evolution todo package created"
                    if success
                    else "todo package created with partial runtime errors"
                ),
                "--resolution-steps",
                "collect_metrics,build_candidates,create_todo_tasks",
                "--failed-items",
                ",".join(run_errors[:20]),
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
                str(quality_score),
                "--quality-grade",
                quality_grade_from_score(quality_score),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "fingerprint": item.get("fingerprint"),
                        "scheduled_at": item.get("scheduled_at"),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "self-evolution-agent",
            ]
            ok_report, _payload_report, err_report = invoke_policy_enforcer(db_file, report_args, timeout=35)
            if ok_report:
                report_count += 1
            elif err_report:
                policy_observability["errors"].append(err_report)
        policy_observability["report_agent_result_count"] = report_count

        since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            db_file,
            ["planner-summary", "--planner-id", "coordinator", "--since", since_24h, "--limit", "60"],
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

    report["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        report["planner_summary"] = planner_summary_snapshot
    save_json(report_file, report)

    state["runs"] = int(state.get("runs", 0)) + 1
    state["updated_at"] = now_iso()
    if run_allowed:
        state["last_full_review_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    state_fps = state.get("fingerprints")
    if not isinstance(state_fps, dict):
        state_fps = {}
    for item in created:
        state_fps[str(item.get("fingerprint", ""))] = str(item.get("task_id", ""))
    state["fingerprints"] = state_fps
    save_json(state_path, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(exception_reasons)

    output = "NO_REPLY"
    if notify:
        lines: list[str] = []
        lines.append("# self-evolution-weekly")
        lines.append(f"- sender_identity: {sender_identity}")
        lines.append(f"- task: {args.task_id or '-'}")
        lines.append(f"- time: {now_iso()}")
        lines.append(f"- run_allowed: {run_allowed}")
        lines.append(f"- candidates: {len(candidates)}")
        lines.append(f"- created_todo: {len(created)}")
        lines.append(f"- max_tasks_per_run: {int(args.max_tasks_per_run)}")
        lines.append(f"- exception_count: {len(exception_reasons)}")
        lines.append("- policy: suggestions_only=true, auto_workflow_change=false, human_confirm_required=true")
        for reason in exception_reasons[:12]:
            lines.append(f"- exception: {reason}")
        for item in created[:8]:
            lines.append(f"- todo[{item.get('task_id')}]: scheduled_at={item.get('scheduled_at')}")
        output = "\n".join(lines)

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

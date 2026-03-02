#!/usr/bin/env python3
"""Task-Center atomic storage and reporting utilities."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

TASK_STATUSES = {
    "pending",
    "running",
    "passed",
    "failed",
    "escalated",
    "cancelled",
}

TASK_POOLS = {"todo", "jobs"}
TASK_PRIORITIES = {"low", "medium", "high"}
TASK_RISK_LEVELS = {"low", "high"}


class TaskCenterError(RuntimeError):
    """Raised when task-center operations fail."""


@dataclass(slots=True)
class TimeRange:
    start: str
    end: str


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def iso_day_range(target_date: date) -> TimeRange:
    start_dt = datetime.combine(target_date, time.min, tzinfo=UTC)
    end_dt = start_dt + timedelta(days=1)
    return TimeRange(start=start_dt.isoformat(), end=end_dt.isoformat())


def to_bool(value: Any) -> bool:
    return bool(int(value)) if isinstance(value, (int, bool)) else str(value).lower() in {
        "1",
        "true",
        "yes",
    }


def ensure_json(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


def parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_pricing(pricing_file: str | Path) -> dict[str, Any]:
    path = Path(pricing_file)
    if not path.exists():
        return {"models": {}, "currency": "CNY", "unit": "per_1m_tokens"}

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise TaskCenterError("pricing file must be a JSON object")

    models = data.get("models")
    if not isinstance(models, dict):
        data["models"] = {}

    return data


def estimate_cost(
    pricing: dict[str, Any],
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    model_cfg = pricing.get("models", {}).get(model_id, {})
    if not isinstance(model_cfg, dict):
        model_cfg = {}

    price_in = float(model_cfg.get("input", 0) or 0)
    price_out = float(model_cfg.get("output", 0) or 0)
    return (input_tokens / 1_000_000.0) * price_in + (output_tokens / 1_000_000.0) * price_out


class TaskCenter:
    """Atomic task-center backed by SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                pool TEXT NOT NULL,
                task_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL,
                priority TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                assignee TEXT,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                need_human_confirm INTEGER NOT NULL DEFAULT 0,
                human_confirmed INTEGER NOT NULL DEFAULT 0,
                requirement TEXT NOT NULL,
                result_output TEXT NOT NULL,
                acceptance TEXT NOT NULL,
                score_raw REAL,
                score_normalized REAL,
                action TEXT,
                scheduled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                stage TEXT,
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost_estimate REAL NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_task_id ON token_usage(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);
            """
        )
        self.conn.commit()

    def _normalize_task(self, task: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        normalized = {
            "task_id": task.get("task_id")
            or f"task-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
            "pool": str(task.get("pool", "jobs")).lower(),
            "task_type": str(task.get("task_type", "workflow")).strip(),
            "reason": str(task.get("reason", "")).strip(),
            "source": str(task.get("source", "openclaw")).strip(),
            "priority": str(task.get("priority", "medium")).lower(),
            "risk_level": str(task.get("risk_level", "low")).lower(),
            "assignee": str(task.get("assignee", "")).strip() or None,
            "status": str(task.get("status", "pending")).lower(),
            "retry_count": int(task.get("retry_count", 0) or 0),
            "failure_count": int(task.get("failure_count", 0) or 0),
            "need_human_confirm": 1 if to_bool(task.get("need_human_confirm", False)) else 0,
            "human_confirmed": 1 if to_bool(task.get("human_confirmed", False)) else 0,
            "requirement": str(task.get("requirement", "")).strip(),
            "result_output": str(task.get("result_output", "")).strip(),
            "acceptance": str(task.get("acceptance", "")).strip(),
            "score_raw": task.get("score_raw"),
            "score_normalized": task.get("score_normalized"),
            "action": str(task.get("action", "")).strip() or None,
            "scheduled_at": task.get("scheduled_at"),
            "created_at": task.get("created_at") or now,
            "updated_at": now,
        }

        if normalized["pool"] not in TASK_POOLS:
            raise TaskCenterError(f"invalid pool: {normalized['pool']}")
        if normalized["priority"] not in TASK_PRIORITIES:
            raise TaskCenterError(f"invalid priority: {normalized['priority']}")
        if normalized["risk_level"] not in TASK_RISK_LEVELS:
            raise TaskCenterError(f"invalid risk_level: {normalized['risk_level']}")
        if normalized["status"] not in TASK_STATUSES:
            raise TaskCenterError(f"invalid status: {normalized['status']}")

        required_text_fields = ["task_type", "reason", "source", "requirement", "result_output", "acceptance"]
        for field in required_text_fields:
            if not normalized[field]:
                raise TaskCenterError(f"missing required field: {field}")

        return normalized

    def create_task(self, task: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        payload = self._normalize_task(task)

        with self.conn:
            exists = self.conn.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?",
                (payload["task_id"],),
            ).fetchone()
            if exists:
                raise TaskCenterError(f"task_id already exists: {payload['task_id']}")

            self.conn.execute(
                """
                INSERT INTO tasks (
                    task_id, pool, task_type, reason, source, priority, risk_level,
                    assignee, status, retry_count, failure_count,
                    need_human_confirm, human_confirmed,
                    requirement, result_output, acceptance,
                    score_raw, score_normalized, action,
                    scheduled_at, created_at, updated_at
                ) VALUES (
                    :task_id, :pool, :task_type, :reason, :source, :priority, :risk_level,
                    :assignee, :status, :retry_count, :failure_count,
                    :need_human_confirm, :human_confirmed,
                    :requirement, :result_output, :acceptance,
                    :score_raw, :score_normalized, :action,
                    :scheduled_at, :created_at, :updated_at
                )
                """,
                payload,
            )
            self.add_event(
                task_id=payload["task_id"],
                actor=actor,
                event_type="task_created",
                stage="create",
                details={"pool": payload["pool"], "priority": payload["priority"], "risk_level": payload["risk_level"]},
            )

        return self.get_task(payload["task_id"])

    def get_task(self, task_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise TaskCenterError(f"task not found: {task_id}")

        data = dict(row)
        data["need_human_confirm"] = bool(data["need_human_confirm"])
        data["human_confirmed"] = bool(data["human_confirmed"])
        return data

    def add_event(
        self,
        task_id: str,
        actor: str,
        event_type: str,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO task_events (task_id, ts, actor, event_type, stage, details_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, utc_now_iso(), actor, event_type, stage, ensure_json(details)),
        )

    def assign_task(self, task_id: str, assignee: str, actor: str) -> dict[str, Any]:
        assignee = assignee.strip()
        if not assignee:
            raise TaskCenterError("assignee cannot be empty")

        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET assignee = ?, updated_at = ? WHERE task_id = ?",
                (assignee, utc_now_iso(), task_id),
            )
            self.add_event(task_id, actor, "task_assigned", stage="assign", details={"assignee": assignee})

        return self.get_task(task_id)

    def confirm_human(self, task_id: str, actor: str, confirmed: bool = True) -> dict[str, Any]:
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET human_confirmed = ?, updated_at = ? WHERE task_id = ?",
                (1 if confirmed else 0, utc_now_iso(), task_id),
            )
            self.add_event(
                task_id,
                actor,
                "human_confirmation_updated",
                stage="risk_confirm",
                details={"confirmed": confirmed},
            )

        return self.get_task(task_id)

    def transition_status(
        self,
        task_id: str,
        new_status: str,
        actor: str,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
        allowed_from: set[str] | None = None,
    ) -> dict[str, Any]:
        normalized_status = new_status.lower().strip()
        if normalized_status not in TASK_STATUSES:
            raise TaskCenterError(f"invalid status: {new_status}")

        current = self.get_task(task_id)
        current_status = str(current["status"])
        if allowed_from and current_status not in allowed_from:
            raise TaskCenterError(
                f"status transition blocked: {current_status} -> {normalized_status}, allowed: {sorted(allowed_from)}"
            )

        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (normalized_status, utc_now_iso(), task_id),
            )
            merged_details = {"from": current_status, "to": normalized_status}
            if details:
                merged_details.update(details)
            self.add_event(task_id, actor, "status_changed", stage=stage, details=merged_details)

        return self.get_task(task_id)

    def increment_failure(
        self,
        task_id: str,
        actor: str,
        stage: str,
        max_failure_before_escalate: int,
        reason: str,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        next_failure = int(task["failure_count"]) + 1
        next_retry = int(task["retry_count"]) + 1

        if next_failure >= max_failure_before_escalate:
            next_status = "escalated"
            next_action = "escalate_human"
        else:
            next_status = "failed"
            next_action = "retry"

        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET failure_count = ?, retry_count = ?, status = ?, action = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (next_failure, next_retry, next_status, next_action, utc_now_iso(), task_id),
            )
            self.add_event(
                task_id,
                actor,
                "failure_recorded",
                stage=stage,
                details={
                    "failure_count": next_failure,
                    "retry_count": next_retry,
                    "status": next_status,
                    "action": next_action,
                    "reason": reason,
                },
            )

        return self.get_task(task_id)

    def upsert_score(
        self,
        task_id: str,
        actor: str,
        raw_score: float,
        normalized_score: float,
        action: str,
    ) -> dict[str, Any]:
        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET score_raw = ?, score_normalized = ?, action = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (raw_score, normalized_score, action, utc_now_iso(), task_id),
            )
            self.add_event(
                task_id,
                actor,
                "score_updated",
                stage="acceptance",
                details={"score_raw": raw_score, "score_normalized": normalized_score, "action": action},
            )

        return self.get_task(task_id)

    def record_token_usage(
        self,
        task_id: str,
        agent_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_estimate: float,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        total_tokens = int(input_tokens) + int(output_tokens)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO token_usage (
                    task_id, ts, agent_id, model_id,
                    input_tokens, output_tokens, total_tokens,
                    cost_estimate, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    utc_now_iso(),
                    agent_id,
                    model_id,
                    int(input_tokens),
                    int(output_tokens),
                    total_tokens,
                    float(cost_estimate),
                    ensure_json(details),
                ),
            )
            self.add_event(
                task_id,
                actor=agent_id,
                event_type="token_usage_recorded",
                stage="usage",
                details={
                    "model_id": model_id,
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": total_tokens,
                    "cost_estimate": float(cost_estimate),
                },
            )

        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "total_tokens": total_tokens,
            "cost_estimate": float(cost_estimate),
        }

    def unresolved_tasks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running', 'failed') ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def daily_summary(self, target_date: date) -> dict[str, Any]:
        tr = iso_day_range(target_date)

        by_status_rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM tasks
            WHERE created_at >= ? AND created_at < ?
            GROUP BY status
            """,
            (tr.start, tr.end),
        ).fetchall()
        by_status = {str(row["status"]): int(row["cnt"]) for row in by_status_rows}

        token_rows = self.conn.execute(
            """
            SELECT
              agent_id,
              SUM(input_tokens) AS input_tokens,
              SUM(output_tokens) AS output_tokens,
              SUM(total_tokens) AS total_tokens,
              SUM(cost_estimate) AS cost_estimate
            FROM token_usage
            WHERE ts >= ? AND ts < ?
            GROUP BY agent_id
            ORDER BY total_tokens DESC
            """,
            (tr.start, tr.end),
        ).fetchall()

        by_agent: list[dict[str, Any]] = []
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0}
        for row in token_rows:
            input_tokens = int(row["input_tokens"] or 0)
            output_tokens = int(row["output_tokens"] or 0)
            total_tokens = int(row["total_tokens"] or 0)
            cost_estimate = float(row["cost_estimate"] or 0.0)
            by_agent.append(
                {
                    "agent_id": str(row["agent_id"]),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
                    "cost_estimate": round(cost_estimate, 6),
                }
            )
            totals["input_tokens"] += input_tokens
            totals["output_tokens"] += output_tokens
            totals["total_tokens"] += total_tokens
            totals["cost_estimate"] += cost_estimate

        escalated_rows = self.conn.execute(
            """
            SELECT task_id, reason, assignee, failure_count, updated_at
            FROM tasks
            WHERE status = 'escalated' AND updated_at >= ? AND updated_at < ?
            ORDER BY updated_at DESC
            """,
            (tr.start, tr.end),
        ).fetchall()

        escalated = [dict(row) for row in escalated_rows]

        return {
            "date": target_date.isoformat(),
            "task_counts": by_status,
            "token_usage": {
                "totals": {
                    "input_tokens": totals["input_tokens"],
                    "output_tokens": totals["output_tokens"],
                    "total_tokens": totals["total_tokens"],
                    "total_tokens_m": round(totals["total_tokens"] / 1_000_000.0, 6),
                    "cost_estimate": round(totals["cost_estimate"], 6),
                },
                "by_agent": by_agent,
            },
            "escalated": escalated,
            "unresolved_count": len(self.unresolved_tasks()),
        }


def format_daily_summary_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Summary {summary['date']}")
    lines.append("")

    task_counts = summary.get("task_counts", {})
    lines.append("## Tasks")
    if task_counts:
        for key in sorted(task_counts.keys()):
            lines.append(f"- {key}: {task_counts[key]}")
    else:
        lines.append("- no tasks")
    lines.append("")

    usage = summary.get("token_usage", {})
    totals = usage.get("totals", {})
    lines.append("## Token Usage")
    lines.append(f"- total_tokens: {totals.get('total_tokens', 0)}")
    lines.append(f"- total_tokens_m: {totals.get('total_tokens_m', 0)}")
    lines.append(f"- cost_estimate: {totals.get('cost_estimate', 0)}")
    lines.append("")

    by_agent = usage.get("by_agent", [])
    lines.append("## Token Usage By Agent")
    if by_agent:
        for item in by_agent:
            lines.append(
                "- "
                + f"{item['agent_id']}: total_tokens={item['total_tokens']} "
                + f"({item['total_tokens_m']}M), cost={item['cost_estimate']}"
            )
    else:
        lines.append("- no usage records")
    lines.append("")

    escalated = summary.get("escalated", [])
    lines.append("## Escalated Tasks")
    if escalated:
        for item in escalated:
            lines.append(
                "- "
                + f"{item['task_id']}: failure_count={item['failure_count']}, "
                + f"assignee={item.get('assignee') or 'unassigned'}, reason={item.get('reason', '')}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append(f"- unresolved_count: {summary.get('unresolved_count', 0)}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"

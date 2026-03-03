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
TASK_REQUEST_SOURCES = {"human", "ai"}
STAGE_RUN_STATUSES = {"running", "passed", "failed"}


class TaskCenterError(RuntimeError):
    """Raised when task-center operations fail."""


@dataclass(slots=True)
class TimeRange:
    start: str
    end: str


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_utc_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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


def normalize_request_source(value: Any, default: str = "human") -> str:
    raw = str(value or "").strip().lower()
    if raw in {"human", "user", "manual", "chat"}:
        return "human"
    if raw in {"ai", "agent", "bot", "cron", "system", "automation", "auto"}:
        return "ai"
    if any(token in raw for token in {"human", "manual", "user", "chat"}):
        return "human"
    if any(token in raw for token in {"agent", "bot", "cron", "auto", "automation", "patrol", "audit", "ops"}):
        return "ai"
    return default if default in TASK_REQUEST_SOURCES else "human"


def normalize_context_missing_fields(value: Any) -> str:
    fields: list[str] = []
    if isinstance(value, str):
        fields = [x.strip() for x in value.split(",") if x.strip()]
    elif isinstance(value, list):
        fields = [str(x).strip() for x in value if str(x).strip()]
    elif isinstance(value, tuple):
        fields = [str(x).strip() for x in value if str(x).strip()]

    unique: list[str] = []
    seen: set[str] = set()
    for item in fields:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return ",".join(unique)


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

    with path.open("r", encoding="utf-8-sig") as fh:
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
                request_source TEXT NOT NULL DEFAULT 'human',
                priority TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                assignee TEXT,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                needs_clarification INTEGER NOT NULL DEFAULT 0,
                clarification_reason TEXT NOT NULL DEFAULT '',
                need_human_confirm INTEGER NOT NULL DEFAULT 0,
                human_confirmed INTEGER NOT NULL DEFAULT 0,
                context_completeness REAL NOT NULL DEFAULT 0,
                context_fields_missing TEXT NOT NULL DEFAULT '',
                context_payload TEXT NOT NULL DEFAULT '{}',
                requirement TEXT NOT NULL,
                result_output TEXT NOT NULL,
                acceptance TEXT NOT NULL,
                observable_outputs TEXT NOT NULL DEFAULT '',
                acceptance_thresholds TEXT NOT NULL DEFAULT '',
                score_raw REAL,
                score_normalized REAL,
                score_payload TEXT NOT NULL DEFAULT '{}',
                token_usage_summary TEXT NOT NULL DEFAULT '{}',
                cost_estimate_total REAL NOT NULL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS stage_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms INTEGER,
                exit_code INTEGER,
                error_reason TEXT,
                input_ref TEXT,
                output_ref TEXT,
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_task_id ON token_usage(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);
            CREATE INDEX IF NOT EXISTS idx_stage_runs_task_id ON stage_runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_stage_runs_started_at ON stage_runs(started_at);
            """
        )
        self._ensure_task_columns()
        self.conn.commit()

    def _ensure_task_columns(self) -> None:
        required_columns = {
            "request_source": "TEXT NOT NULL DEFAULT 'human'",
            "needs_clarification": "INTEGER NOT NULL DEFAULT 0",
            "clarification_reason": "TEXT NOT NULL DEFAULT ''",
            "context_completeness": "REAL NOT NULL DEFAULT 0",
            "context_fields_missing": "TEXT NOT NULL DEFAULT ''",
            "context_payload": "TEXT NOT NULL DEFAULT '{}'",
            "observable_outputs": "TEXT NOT NULL DEFAULT ''",
            "acceptance_thresholds": "TEXT NOT NULL DEFAULT ''",
            "score_payload": "TEXT NOT NULL DEFAULT '{}'",
            "token_usage_summary": "TEXT NOT NULL DEFAULT '{}'",
            "cost_estimate_total": "REAL NOT NULL DEFAULT 0",
        }
        rows = self.conn.execute("PRAGMA table_info(tasks)").fetchall()
        existing = {str(row["name"]) for row in rows}
        for column, ddl in required_columns.items():
            if column in existing:
                continue
            self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {ddl}")

    def _normalize_task(self, task: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        source_hint = normalize_request_source(task.get("source"), default="human")
        request_source = normalize_request_source(task.get("request_source"), default=source_hint)
        needs_clarification = 1 if to_bool(task.get("needs_clarification", False)) else 0
        clarification_reason = str(task.get("clarification_reason", "")).strip()
        if needs_clarification and not clarification_reason:
            clarification_reason = "context_incomplete"

        context_payload_raw = task.get("context_payload") or {}
        if isinstance(context_payload_raw, str):
            parsed = parse_json(context_payload_raw)
            context_payload_raw = parsed if parsed else {"raw": context_payload_raw}
        if not isinstance(context_payload_raw, dict):
            context_payload_raw = {"raw": str(context_payload_raw)}

        try:
            context_completeness = float(task.get("context_completeness", 0) or 0)
        except (TypeError, ValueError):
            context_completeness = 0.0
        context_completeness = max(0.0, min(100.0, context_completeness))
        context_fields_missing = normalize_context_missing_fields(task.get("context_fields_missing"))

        normalized = {
            "task_id": task.get("task_id")
            or f"task-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
            "pool": str(task.get("pool", "jobs")).lower(),
            "task_type": str(task.get("task_type", "workflow")).strip(),
            "reason": str(task.get("reason", "")).strip(),
            "source": str(task.get("source", "openclaw")).strip(),
            "request_source": request_source,
            "priority": str(task.get("priority", "medium")).lower(),
            "risk_level": str(task.get("risk_level", "low")).lower(),
            "assignee": str(task.get("assignee", "")).strip() or None,
            "status": str(task.get("status", "pending")).lower(),
            "retry_count": int(task.get("retry_count", 0) or 0),
            "failure_count": int(task.get("failure_count", 0) or 0),
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "need_human_confirm": 1 if to_bool(task.get("need_human_confirm", False)) else 0,
            "human_confirmed": 1 if to_bool(task.get("human_confirmed", False)) else 0,
            "context_completeness": context_completeness,
            "context_fields_missing": context_fields_missing,
            "context_payload": ensure_json(context_payload_raw),
            "requirement": str(task.get("requirement", "")).strip(),
            "result_output": str(task.get("result_output", "")).strip(),
            "acceptance": str(task.get("acceptance", "")).strip(),
            "observable_outputs": str(task.get("observable_outputs", "")).strip(),
            "acceptance_thresholds": str(task.get("acceptance_thresholds", "")).strip(),
            "score_raw": task.get("score_raw"),
            "score_normalized": task.get("score_normalized"),
            "score_payload": ensure_json(task.get("score_payload") or {}),
            "token_usage_summary": ensure_json(task.get("token_usage_summary") or {}),
            "cost_estimate_total": float(task.get("cost_estimate_total", 0) or 0),
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
        if normalized["request_source"] not in TASK_REQUEST_SOURCES:
            raise TaskCenterError(f"invalid request_source: {normalized['request_source']}")
        if normalized["status"] not in TASK_STATUSES:
            raise TaskCenterError(f"invalid status: {normalized['status']}")

        required_text_fields = [
            "task_type",
            "reason",
            "source",
            "requirement",
            "result_output",
            "acceptance",
            "observable_outputs",
            "acceptance_thresholds",
        ]
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
                    task_id, pool, task_type, reason, source, request_source, priority, risk_level,
                    assignee, status, retry_count, failure_count,
                    needs_clarification, clarification_reason,
                    need_human_confirm, human_confirmed,
                    context_completeness, context_fields_missing, context_payload,
                    requirement, result_output, acceptance,
                    observable_outputs, acceptance_thresholds,
                    score_raw, score_normalized, score_payload,
                    token_usage_summary, cost_estimate_total, action,
                    scheduled_at, created_at, updated_at
                ) VALUES (
                    :task_id, :pool, :task_type, :reason, :source, :request_source, :priority, :risk_level,
                    :assignee, :status, :retry_count, :failure_count,
                    :needs_clarification, :clarification_reason,
                    :need_human_confirm, :human_confirmed,
                    :context_completeness, :context_fields_missing, :context_payload,
                    :requirement, :result_output, :acceptance,
                    :observable_outputs, :acceptance_thresholds,
                    :score_raw, :score_normalized, :score_payload,
                    :token_usage_summary, :cost_estimate_total, :action,
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
                details={
                    "pool": payload["pool"],
                    "priority": payload["priority"],
                    "risk_level": payload["risk_level"],
                    "request_source": payload["request_source"],
                    "needs_clarification": bool(payload["needs_clarification"]),
                },
            )

        return self.get_task(payload["task_id"])

    def get_task(self, task_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise TaskCenterError(f"task not found: {task_id}")

        data = dict(row)
        data["need_human_confirm"] = bool(data["need_human_confirm"])
        data["human_confirmed"] = bool(data["human_confirmed"])
        data["needs_clarification"] = bool(data.get("needs_clarification"))
        data["context_payload"] = parse_json(str(data.get("context_payload") or ""))
        missing_fields = str(data.get("context_fields_missing") or "").strip()
        data["context_fields_missing"] = [x for x in missing_fields.split(",") if x]
        data["score_payload"] = parse_json(str(data.get("score_payload") or ""))
        data["token_usage_summary"] = parse_json(str(data.get("token_usage_summary") or ""))
        data["context_completeness"] = round(float(data.get("context_completeness") or 0.0), 2)
        data["cost_estimate_total"] = round(float(data.get("cost_estimate_total") or 0.0), 6)
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

    def start_stage_run(
        self,
        task_id: str,
        stage: str,
        agent_id: str,
        model_id: str,
        input_ref: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stage = stage.strip()
        agent_id = agent_id.strip()
        model_id = model_id.strip()
        if not stage:
            raise TaskCenterError("stage cannot be empty")
        if not agent_id:
            raise TaskCenterError("agent_id cannot be empty")
        if not model_id:
            raise TaskCenterError("model_id cannot be empty")

        started_at = utc_now_iso()
        payload = {
            "task_id": task_id,
            "stage": stage,
            "agent_id": agent_id,
            "model_id": model_id,
            "status": "running",
            "started_at": started_at,
            "finished_at": None,
            "duration_ms": None,
            "exit_code": None,
            "error_reason": None,
            "input_ref": input_ref.strip() or None,
            "output_ref": None,
            "details_json": ensure_json(details),
        }

        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO stage_runs (
                    task_id, stage, agent_id, model_id, status, started_at,
                    finished_at, duration_ms, exit_code, error_reason,
                    input_ref, output_ref, details_json
                ) VALUES (
                    :task_id, :stage, :agent_id, :model_id, :status, :started_at,
                    :finished_at, :duration_ms, :exit_code, :error_reason,
                    :input_ref, :output_ref, :details_json
                )
                """,
                payload,
            )
            stage_run_id = int(cursor.lastrowid)

        return self.get_stage_run(stage_run_id)

    def get_stage_run(self, stage_run_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM stage_runs WHERE id = ?", (int(stage_run_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"stage_run not found: {stage_run_id}")
        out = dict(row)
        out["details"] = parse_json(out.pop("details_json", ""))
        return out

    def finish_stage_run(
        self,
        task_id: str,
        stage: str,
        status: str,
        exit_code: int,
        error_reason: str = "",
        output_ref: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = status.strip().lower()
        if normalized_status not in STAGE_RUN_STATUSES:
            raise TaskCenterError(f"invalid stage_run status: {status}")
        if normalized_status == "running":
            raise TaskCenterError("stage_run finish status cannot be running")

        row = self.conn.execute(
            """
            SELECT *
            FROM stage_runs
            WHERE task_id = ? AND stage = ? AND status = 'running' AND finished_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (task_id, stage),
        ).fetchone()
        if not row:
            raise TaskCenterError(f"running stage_run not found for task={task_id}, stage={stage}")

        started_at = parse_utc_iso(str(row["started_at"]))
        finished_at = parse_utc_iso(utc_now_iso())
        duration_ms: int | None = None
        if started_at and finished_at:
            duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))

        merged_details = parse_json(str(row["details_json"]))
        if details:
            merged_details.update(details)

        with self.conn:
            self.conn.execute(
                """
                UPDATE stage_runs
                SET status = ?,
                    finished_at = ?,
                    duration_ms = ?,
                    exit_code = ?,
                    error_reason = ?,
                    output_ref = ?,
                    details_json = ?
                WHERE id = ?
                """,
                (
                    normalized_status,
                    finished_at.isoformat() if finished_at else utc_now_iso(),
                    duration_ms,
                    int(exit_code),
                    error_reason.strip() or None,
                    output_ref.strip() or None,
                    ensure_json(merged_details),
                    int(row["id"]),
                ),
            )

        return self.get_stage_run(int(row["id"]))

    def list_stage_runs(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM stage_runs
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = parse_json(item.pop("details_json", ""))
            out.append(item)
        return out

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
        score_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(score_payload or {})
        if not payload:
            payload = {
                "raw_score": raw_score,
                "normalized_score": normalized_score,
                "action": action,
            }
        updated_at = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET score_raw = ?, score_normalized = ?, action = ?, score_payload = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (raw_score, normalized_score, action, ensure_json(payload), updated_at, task_id),
            )
            self.add_event(
                task_id,
                actor,
                "score_updated",
                stage="acceptance",
                details={
                    "score_raw": raw_score,
                    "score_normalized": normalized_score,
                    "action": action,
                    "score_payload": payload,
                },
            )

        return self.get_task(task_id)

    def update_clarification(
        self,
        task_id: str,
        actor: str,
        *,
        needs_clarification: bool,
        clarification_reason: str = "",
        context_payload: dict[str, Any] | None = None,
        context_completeness: float | None = None,
        context_fields_missing: list[str] | None = None,
    ) -> dict[str, Any]:
        current = self.get_task(task_id)
        payload = context_payload if isinstance(context_payload, dict) else current.get("context_payload", {})
        if not isinstance(payload, dict):
            payload = {}

        completeness = (
            float(context_completeness)
            if context_completeness is not None
            else float(current.get("context_completeness") or 0.0)
        )
        completeness = max(0.0, min(100.0, completeness))

        missing = (
            context_fields_missing
            if isinstance(context_fields_missing, list)
            else list(current.get("context_fields_missing") or [])
        )
        missing_text = normalize_context_missing_fields(missing)
        reason = str(clarification_reason or "").strip()
        if needs_clarification and not reason:
            reason = "context_incomplete"

        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET needs_clarification = ?,
                    clarification_reason = ?,
                    context_payload = ?,
                    context_completeness = ?,
                    context_fields_missing = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    1 if needs_clarification else 0,
                    reason,
                    ensure_json(payload),
                    completeness,
                    missing_text,
                    utc_now_iso(),
                    task_id,
                ),
            )
            self.add_event(
                task_id=task_id,
                actor=actor,
                event_type="clarification_updated",
                stage="intake",
                details={
                    "needs_clarification": bool(needs_clarification),
                    "clarification_reason": reason,
                    "context_completeness": completeness,
                    "context_fields_missing": [x for x in missing_text.split(",") if x],
                },
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
            summary = self.task_token_summary(task_id)
            self.conn.execute(
                """
                UPDATE tasks
                SET token_usage_summary = ?, cost_estimate_total = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    ensure_json(summary),
                    float(summary.get("cost_estimate", 0.0)),
                    utc_now_iso(),
                    task_id,
                ),
            )

        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "total_tokens": total_tokens,
            "cost_estimate": float(cost_estimate),
            "task_token_usage_summary": summary,
        }

    def has_token_usage(self, task_id: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(1) AS cnt FROM token_usage WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return int(row["cnt"] or 0) > 0 if row else False

    def task_token_summary(self, task_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(cost_estimate), 0.0) AS cost_estimate
            FROM token_usage
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_tokens_m": 0.0,
                "cost_estimate": 0.0,
            }
        total_tokens = int(row["total_tokens"] or 0)
        return {
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "total_tokens": total_tokens,
            "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
            "cost_estimate": round(float(row["cost_estimate"] or 0.0), 6),
        }

    def list_task_events(self, task_id: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 1000))
        rows = self.conn.execute(
            """
            SELECT id, task_id, ts, actor, event_type, stage, details_json
            FROM task_events
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = parse_json(item.pop("details_json", ""))
            out.append(item)
        out.reverse()
        return out

    def task_report(self, task_id: str, event_limit: int = 200) -> dict[str, Any]:
        return {
            "task": self.get_task(task_id),
            "token_usage": self.task_token_summary(task_id),
            "stage_runs": self.list_stage_runs(task_id),
            "events": self.list_task_events(task_id, limit=event_limit),
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

        by_pool_rows = self.conn.execute(
            """
            SELECT pool, COUNT(*) AS cnt
            FROM tasks
            WHERE created_at >= ? AND created_at < ?
            GROUP BY pool
            """,
            (tr.start, tr.end),
        ).fetchall()
        by_pool = {str(row["pool"]): int(row["cnt"]) for row in by_pool_rows}

        risk_row = self.conn.execute(
            """
            SELECT
              COUNT(*) AS total_count,
              SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_count
            FROM tasks
            WHERE created_at >= ? AND created_at < ?
            """,
            (tr.start, tr.end),
        ).fetchone()
        total_count = int(risk_row["total_count"] or 0) if risk_row else 0
        high_risk_count = int(risk_row["high_risk_count"] or 0) if risk_row else 0
        high_risk_ratio_pct = round((high_risk_count / total_count) * 100.0, 2) if total_count > 0 else 0.0

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
        escalated_count = len(escalated)

        failure_over_limit_rows = self.conn.execute(
            """
            SELECT task_id, reason, assignee, status, failure_count, updated_at
            FROM tasks
            WHERE failure_count >= 3 AND updated_at >= ? AND updated_at < ?
            ORDER BY failure_count DESC, updated_at DESC
            """,
            (tr.start, tr.end),
        ).fetchall()
        failure_over_limit = [dict(row) for row in failure_over_limit_rows]

        stage_rows = self.conn.execute(
            """
            SELECT
              stage,
              status,
              COUNT(*) AS cnt,
              AVG(duration_ms) AS avg_duration_ms
            FROM stage_runs
            WHERE started_at >= ? AND started_at < ?
            GROUP BY stage, status
            ORDER BY stage, status
            """,
            (tr.start, tr.end),
        ).fetchall()

        stage_metrics: list[dict[str, Any]] = []
        for row in stage_rows:
            stage_metrics.append(
                {
                    "stage": str(row["stage"]),
                    "status": str(row["status"]),
                    "count": int(row["cnt"] or 0),
                    "avg_duration_ms": int(float(row["avg_duration_ms"] or 0.0)),
                }
            )

        return {
            "date": target_date.isoformat(),
            "task_counts": by_status,
            "task_pools": by_pool,
            "risk_overview": {
                "total_count": total_count,
                "high_risk_count": high_risk_count,
                "high_risk_ratio_pct": high_risk_ratio_pct,
            },
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
            "stage_metrics": stage_metrics,
            "escalated": escalated,
            "escalated_count": escalated_count,
            "failure_over_limit": failure_over_limit,
            "unresolved_count": len(self.unresolved_tasks()),
        }


def format_daily_summary_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Summary {summary['date']}")
    lines.append("")

    task_counts = summary.get("task_counts", {})
    task_pools = summary.get("task_pools", {})
    lines.append("## Tasks")
    if task_counts:
        for key in sorted(task_counts.keys()):
            lines.append(f"- {key}: {task_counts[key]}")
    else:
        lines.append("- no tasks")
    if task_pools:
        for key in sorted(task_pools.keys()):
            lines.append(f"- pool_{key}: {task_pools[key]}")
    lines.append("")

    risk_overview = summary.get("risk_overview", {})
    lines.append("## Risk")
    lines.append(f"- high_risk_count: {risk_overview.get('high_risk_count', 0)}")
    lines.append(f"- total_count: {risk_overview.get('total_count', 0)}")
    lines.append(f"- high_risk_ratio_pct: {risk_overview.get('high_risk_ratio_pct', 0)}")
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

    stage_metrics = summary.get("stage_metrics", [])
    lines.append("## Stage Metrics")
    if stage_metrics:
        for item in stage_metrics:
            lines.append(
                "- "
                + f"{item['stage']}/{item['status']}: count={item['count']}, "
                + f"avg_duration_ms={item['avg_duration_ms']}"
            )
    else:
        lines.append("- no stage runs")
    lines.append("")

    failure_over_limit = summary.get("failure_over_limit", [])
    lines.append("## Failure >= 3")
    if failure_over_limit:
        for item in failure_over_limit:
            lines.append(
                "- "
                + f"{item['task_id']}: failure_count={item['failure_count']}, "
                + f"status={item.get('status', '')}, assignee={item.get('assignee') or 'unassigned'}"
            )
    else:
        lines.append("- none")
    lines.append("")

    escalated = summary.get("escalated", [])
    lines.append("## Escalated Tasks")
    lines.append(f"- escalated_count: {summary.get('escalated_count', len(escalated))}")
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

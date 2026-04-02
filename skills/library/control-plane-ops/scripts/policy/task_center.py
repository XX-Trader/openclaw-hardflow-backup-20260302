#!/usr/bin/env python3
"""Task-Center atomic storage and reporting utilities.

Bridge contract:
- Python governance state lives here, not in vendor private runtime files.
- Official OpenClaw cron/hooks/webhook surfaces may trigger this layer.
- Callers should prefer structured JSON or NO_REPLY style outputs above this storage layer.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time as time_module
import uuid
from dataclass_compat import compat_dataclass as dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
BRIDGE_TRIGGER_SURFACES = ("cron", "hooks", "webhook")
BRIDGE_VENDOR_STATE_POLICY = "no-direct-vendor-private-state-writes"
BRIDGE_OUTPUT_CONTRACT = {
    "machine_output": "structured-json",
    "quiet_success": "NO_REPLY",
}

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
TASK_REVIEW_STATUSES = {"unreviewed", "in_review", "reviewed", "fix_required", "fix_verified"}
STAGE_RUN_STATUSES = {"running", "passed", "failed"}
MODULE_LOG_LEVELS = {"debug", "info", "warn", "error"}
MODULE_RUN_STATUSES = {"started", "running", "passed", "failed", "timeout", "skipped"}
COMMUNICATION_STATUSES = {"sent", "acked", "failed", "timeout"}
TASK_OUTPUT_AUDIENCES = {"human", "machine", "ops"}
TASK_OUTPUT_STATUSES = {"prepared", "sent", "suppressed", "failed"}
INCIDENT_SEVERITIES = {"info", "warning", "critical"}
INCIDENT_STATUSES = {"open", "acked", "resolved", "suppressed"}
BINDING_TARGET_KINDS = {"workflow", "skill", "capability", "binding"}
AGENT_REPORT_STATUSES = {"passed", "failed", "partial", "escalated"}
WORKFLOW_SELECTION_CHANNELS = {"", "stable", "candidate"}
SQLITE_LOCK_ERROR_SNIPPETS = ("database is locked", "database table is locked")
SQLITE_WRITE_RETRY_ATTEMPTS = 4
SQLITE_WRITE_RETRY_INITIAL_DELAY_SEC = 1.0
SQLITE_WRITE_RETRY_MAX_DELAY_SEC = 8.0
DISPLAY_TRACE_LABELS = {
    "context_payload": "留痕编号",
    "evidence": "留痕编号",
    "input_ref": "输入留痕编号",
    "output_ref": "输出留痕编号",
    "parsed_file": "解析留痕编号",
    "payload_ref": "留痕编号",
    "raw_file": "原始留痕编号",
    "report_file": "留痕编号",
}
DISPLAY_PATH_RE = re.compile(
    r"(?<!://)(?:"
    r"[A-Za-z]:\\[^\s,;:，；。]+"
    r"|(?<!:)/(?:[^/\s,;:，；。]+/)*[^/\s,;:，；。]+"
    r"|(?:\.\.?[/\\])(?:[^\\/\s,;:，；。]+[/\\])*[^\\/\s,;:，；。]+"
    r"|[\w.-]+\.(?:json|log|txt|md|png|jpg|jpeg|webp|csv|sqlite|db)"
    r")"
)


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


def normalize_review_status(value: Any, default: str = "unreviewed") -> str:
    raw = str(value or "").strip().lower()
    if raw in TASK_REVIEW_STATUSES:
        return raw
    return default if default in TASK_REVIEW_STATUSES else "unreviewed"


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


def parse_json_list(text: str | None) -> list[Any]:
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def ensure_json_list(data: Any) -> str:
    if isinstance(data, list):
        payload = data
    elif isinstance(data, tuple):
        payload = list(data)
    elif data in {None, ""}:
        payload = []
    else:
        payload = [data]
    return json.dumps(payload, ensure_ascii=False)


def display_trace_label(key_hint: str = "") -> str:
    normalized = str(key_hint or "").strip().lower()
    if normalized in DISPLAY_TRACE_LABELS:
        return DISPLAY_TRACE_LABELS[normalized]
    if "parsed" in normalized:
        return "解析留痕编号"
    if "raw" in normalized:
        return "原始留痕编号"
    if normalized.startswith("input") or "_input" in normalized:
        return "输入留痕编号"
    if normalized.startswith("output") or "_output" in normalized:
        return "输出留痕编号"
    if normalized.endswith(("_file", "_path", "_ref")):
        return "留痕编号"
    return "留痕编号"


def build_trace_token(value: str | Path) -> str:
    raw = str(value or "").strip().strip("'\"")
    if not raw:
        return "已归档"
    normalized = raw.replace("\\", "/").split("?", 1)[0].split("#", 1)[0].rstrip("/")
    tail = normalized.rsplit("/", 1)[-1] if normalized else raw
    token = Path(tail).stem or Path(normalized or raw).stem or tail or raw
    return str(token).strip() or "已归档"


def looks_like_trace_path(value: str) -> bool:
    raw = str(value or "").strip().strip("'\"")
    if not raw:
        return False
    if raw.startswith(("http://", "https://")):
        return False
    if DISPLAY_PATH_RE.fullmatch(raw):
        return True
    normalized = raw.replace("\\", "/")
    if normalized.startswith("file://"):
        return True
    return False


def sanitize_display_text(value: str, *, key_hint: str = "") -> str:
    text = str(value or "")
    if not text.strip():
        return text
    label = display_trace_label(key_hint)
    stripped = text.strip()
    if looks_like_trace_path(stripped):
        return f"{label}：{build_trace_token(stripped)}"

    def replace_match(match: re.Match[str]) -> str:
        matched = str(match.group(0) or "").strip().strip("'\"")
        if not matched or matched.startswith(("http://", "https://")):
            return matched
        return f"{label}：{build_trace_token(matched)}"

    return DISPLAY_PATH_RE.sub(replace_match, text)


def sanitize_display_payload(value: Any, *, key_hint: str = "") -> Any:
    if isinstance(value, dict):
        return {key: sanitize_display_payload(item, key_hint=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_display_payload(item, key_hint=key_hint) for item in value]
    if isinstance(value, tuple):
        return [sanitize_display_payload(item, key_hint=key_hint) for item in value]
    if isinstance(value, str):
        return sanitize_display_text(value, key_hint=key_hint)
    return value


def normalize_text_list(value: Any) -> str:
    items: list[str] = []
    if isinstance(value, str):
        items = [x.strip() for x in value.split(",") if x.strip()]
    elif isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
    elif isinstance(value, tuple):
        items = [str(x).strip() for x in value if str(x).strip()]

    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return ",".join(unique)


def split_text_list(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [x for x in (item.strip() for item in text.split(",")) if x]


def normalize_workflow_channel(value: Any, default: str = "") -> str:
    raw = str(value or "").strip().lower()
    if raw in WORKFLOW_SELECTION_CHANNELS:
        return raw
    return str(default or "").strip().lower()


def normalize_json_object_field(value: Any) -> str:
    if isinstance(value, dict):
        return ensure_json(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ensure_json({})
        parsed = parse_json(stripped)
        if parsed:
            return ensure_json(parsed)
        return ensure_json({"raw": stripped})
    if value is None:
        return ensure_json({})
    return ensure_json({"raw": str(value)})


def normalize_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        parsed = parse_json(stripped)
        if parsed:
            return parsed
        return {"raw": stripped}
    if value is None:
        return {}
    return {"raw": str(value)}


def build_trace_id() -> str:
    return f"trace-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def normalize_trace_id(value: Any, *, task_id: str = "") -> str:
    raw = str(value or "").strip()
    if raw:
        return raw
    normalized_task_id = str(task_id or "").strip()
    if normalized_task_id:
        return f"trace-{normalized_task_id}"
    return build_trace_id()


def normalize_attempt_id(value: Any, *, retry_count: int = 0) -> str:
    raw = str(value or "").strip()
    if raw:
        return raw
    return f"attempt-{max(1, int(retry_count or 0) + 1):03d}"


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
        self.conn = sqlite3.connect(self.db_path, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.conn.close()

    def _is_retryable_write_error(self, exc: Exception) -> bool:
        text = str(exc or "").strip().lower()
        return any(snippet in text for snippet in SQLITE_LOCK_ERROR_SNIPPETS)

    def _run_write_with_retry(self, operation: Any) -> Any:
        delay = SQLITE_WRITE_RETRY_INITIAL_DELAY_SEC
        last_exc: Exception | None = None
        for attempt in range(SQLITE_WRITE_RETRY_ATTEMPTS):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if (not self._is_retryable_write_error(exc)) or attempt >= SQLITE_WRITE_RETRY_ATTEMPTS - 1:
                    raise
                last_exc = exc
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                time_module.sleep(delay)
                delay = min(delay * 2.0, SQLITE_WRITE_RETRY_MAX_DELAY_SEC)
        if last_exc is not None:
            raise last_exc
        raise TaskCenterError("sqlite write retry exhausted without captured exception")

    def _run_transaction_with_retry(self, operation: Any) -> Any:
        if self.conn.in_transaction:
            return operation()

        def tx_op() -> Any:
            with self.conn:
                return operation()

        return self._run_write_with_retry(tx_op)

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
                trace_id TEXT NOT NULL DEFAULT '',
                attempt_id TEXT NOT NULL DEFAULT '',
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
                context_fields_recommended_missing TEXT NOT NULL DEFAULT '',
                context_payload TEXT NOT NULL DEFAULT '{}',
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                review_mode TEXT NOT NULL DEFAULT '',
                review_head TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '',
                change_id TEXT NOT NULL DEFAULT '',
                requirement TEXT NOT NULL,
                result_output TEXT NOT NULL,
                acceptance TEXT NOT NULL,
                observable_outputs TEXT NOT NULL DEFAULT '',
                acceptance_thresholds TEXT NOT NULL DEFAULT '',
                stage_id TEXT NOT NULL DEFAULT '',
                stage_score_gate TEXT NOT NULL DEFAULT '',
                stage_min_evidence_count INTEGER NOT NULL DEFAULT 0,
                stage_output_contract TEXT NOT NULL DEFAULT '{}',
                stage_verification_contract TEXT NOT NULL DEFAULT '{}',
                required_capabilities TEXT NOT NULL DEFAULT '',
                required_skills TEXT NOT NULL DEFAULT '',
                allowed_agents TEXT NOT NULL DEFAULT '',
                workflow_profile_id TEXT NOT NULL DEFAULT '',
                workflow_channel TEXT NOT NULL DEFAULT '',
                selection_reason TEXT NOT NULL DEFAULT '',
                selection_inputs TEXT NOT NULL DEFAULT '{}',
                score_raw REAL,
                score_normalized REAL,
                score_payload TEXT NOT NULL DEFAULT '{}',
                token_usage_summary TEXT NOT NULL DEFAULT '{}',
                cost_estimate_total REAL NOT NULL DEFAULT 0,
                action TEXT,
                scheduled_at TEXT,
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS module_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                ts TEXT NOT NULL,
                module_name TEXT NOT NULL,
                phase TEXT NOT NULL,
                level TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS module_communications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                ts TEXT NOT NULL,
                from_module TEXT NOT NULL,
                to_module TEXT NOT NULL,
                protocol TEXT NOT NULL,
                message_type TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                correlation_id TEXT NOT NULL DEFAULT '',
                payload_ref TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                output_type TEXT NOT NULL,
                audience TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                incident_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_run_id TEXT NOT NULL UNIQUE,
                task_id TEXT,
                ts TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                benchmark_suite_id TEXT NOT NULL,
                workflow_profile_id TEXT NOT NULL DEFAULT '',
                workflow_channel TEXT NOT NULL DEFAULT '',
                target_kind TEXT NOT NULL,
                target_id TEXT NOT NULL,
                baseline_run_ids TEXT NOT NULL DEFAULT '[]',
                candidate_run_ids TEXT NOT NULL DEFAULT '[]',
                summary_file TEXT NOT NULL DEFAULT '',
                scorecard_file TEXT NOT NULL DEFAULT '',
                decision_json TEXT NOT NULL DEFAULT '{}',
                details_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS agent_task_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                planner_id TEXT NOT NULL,
                status TEXT NOT NULL,
                solved INTEGER NOT NULL DEFAULT 0,
                resolved_issues TEXT NOT NULL DEFAULT '',
                resolution_summary TEXT NOT NULL DEFAULT '',
                resolution_steps TEXT NOT NULL DEFAULT '',
                failed_items TEXT NOT NULL DEFAULT '',
                failure_count INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                model_id TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                cost_estimate REAL NOT NULL DEFAULT 0,
                quality_score REAL,
                quality_grade TEXT NOT NULL DEFAULT '',
                notify_chat INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                UNIQUE(task_id, agent_id, planner_id)
            );

            CREATE TABLE IF NOT EXISTS agent_points_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                planner_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                solved INTEGER NOT NULL DEFAULT 0,
                points REAL NOT NULL DEFAULT 0,
                base_points REAL NOT NULL DEFAULT 0,
                quality_factor REAL NOT NULL DEFAULT 0,
                timeliness_factor REAL NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                UNIQUE(task_id, actor_type, actor_id, planner_id)
            );

            CREATE TABLE IF NOT EXISTS workflow_selection_records (
                selection_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                workflow_profile_id TEXT NOT NULL,
                workflow_channel TEXT NOT NULL DEFAULT '',
                selection_reason TEXT NOT NULL DEFAULT '',
                selection_inputs TEXT NOT NULL DEFAULT '{}',
                selected_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_task_id ON token_usage(task_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);
            CREATE INDEX IF NOT EXISTS idx_stage_runs_task_id ON stage_runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_stage_runs_started_at ON stage_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_module_logs_task_id ON module_logs(task_id);
            CREATE INDEX IF NOT EXISTS idx_module_logs_module_ts ON module_logs(module_name, ts);
            CREATE INDEX IF NOT EXISTS idx_module_communications_task_id ON module_communications(task_id);
            CREATE INDEX IF NOT EXISTS idx_module_communications_path_ts
                ON module_communications(from_module, to_module, ts);
            CREATE INDEX IF NOT EXISTS idx_task_outputs_task_id ON task_outputs(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_outputs_audience_ts ON task_outputs(audience, ts);
            CREATE INDEX IF NOT EXISTS idx_task_incidents_task_id ON task_incidents(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_incidents_status_ts ON task_incidents(status, ts);
            CREATE INDEX IF NOT EXISTS idx_benchmark_runs_suite_ts ON benchmark_runs(benchmark_suite_id, ts);
            CREATE INDEX IF NOT EXISTS idx_benchmark_runs_task_id ON benchmark_runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_agent_task_reports_task_id ON agent_task_reports(task_id);
            CREATE INDEX IF NOT EXISTS idx_agent_task_reports_planner_ts ON agent_task_reports(planner_id, ts);
            CREATE INDEX IF NOT EXISTS idx_agent_points_actor_ts ON agent_points_ledger(actor_type, actor_id, ts);
            CREATE INDEX IF NOT EXISTS idx_agent_points_task_id ON agent_points_ledger(task_id);
            CREATE INDEX IF NOT EXISTS idx_workflow_selection_profile
                ON workflow_selection_records(workflow_profile_id, workflow_channel);
            """
        )
        self._ensure_task_columns()
        self._ensure_auxiliary_columns()
        self.conn.commit()

    def _ensure_table_columns(self, table_name: str, required_columns: dict[str, str]) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row["name"]) for row in rows}
        for column, ddl in required_columns.items():
            if column in existing:
                continue
            try:
                self.conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl}")
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "duplicate column name" not in message:
                    raise

    def _ensure_task_columns(self) -> None:
        required_columns = {
            "request_source": "TEXT NOT NULL DEFAULT 'human'",
            "trace_id": "TEXT NOT NULL DEFAULT ''",
            "attempt_id": "TEXT NOT NULL DEFAULT ''",
            "needs_clarification": "INTEGER NOT NULL DEFAULT 0",
            "clarification_reason": "TEXT NOT NULL DEFAULT ''",
            "context_completeness": "REAL NOT NULL DEFAULT 0",
            "context_fields_missing": "TEXT NOT NULL DEFAULT ''",
            "context_fields_recommended_missing": "TEXT NOT NULL DEFAULT ''",
            "context_payload": "TEXT NOT NULL DEFAULT '{}'",
            "review_status": "TEXT NOT NULL DEFAULT 'unreviewed'",
            "review_mode": "TEXT NOT NULL DEFAULT ''",
            "review_head": "TEXT NOT NULL DEFAULT ''",
            "reviewed_at": "TEXT NOT NULL DEFAULT ''",
            "owner": "TEXT NOT NULL DEFAULT ''",
            "change_id": "TEXT NOT NULL DEFAULT ''",
            "observable_outputs": "TEXT NOT NULL DEFAULT ''",
            "acceptance_thresholds": "TEXT NOT NULL DEFAULT ''",
            "stage_id": "TEXT NOT NULL DEFAULT ''",
            "stage_score_gate": "TEXT NOT NULL DEFAULT ''",
            "stage_min_evidence_count": "INTEGER NOT NULL DEFAULT 0",
            "stage_output_contract": "TEXT NOT NULL DEFAULT '{}'",
            "stage_verification_contract": "TEXT NOT NULL DEFAULT '{}'",
            "required_capabilities": "TEXT NOT NULL DEFAULT ''",
            "required_skills": "TEXT NOT NULL DEFAULT ''",
            "allowed_agents": "TEXT NOT NULL DEFAULT ''",
            "workflow_profile_id": "TEXT NOT NULL DEFAULT ''",
            "workflow_channel": "TEXT NOT NULL DEFAULT ''",
            "selection_reason": "TEXT NOT NULL DEFAULT ''",
            "selection_inputs": "TEXT NOT NULL DEFAULT '{}'",
            "score_payload": "TEXT NOT NULL DEFAULT '{}'",
            "token_usage_summary": "TEXT NOT NULL DEFAULT '{}'",
            "cost_estimate_total": "REAL NOT NULL DEFAULT 0",
            "started_at": "TEXT NOT NULL DEFAULT ''",
            "completed_at": "TEXT NOT NULL DEFAULT ''",
        }
        self._ensure_table_columns("tasks", required_columns)

    def _ensure_auxiliary_columns(self) -> None:
        self._ensure_table_columns(
            "task_outputs",
            {"trace_id": "TEXT NOT NULL DEFAULT ''"},
        )
        self._ensure_table_columns(
            "task_incidents",
            {"trace_id": "TEXT NOT NULL DEFAULT ''"},
        )
        self._ensure_table_columns(
            "benchmark_runs",
            {"trace_id": "TEXT NOT NULL DEFAULT ''"},
        )

    def _deserialize_task_row(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["need_human_confirm"] = bool(data["need_human_confirm"])
        data["human_confirmed"] = bool(data["human_confirmed"])
        data["needs_clarification"] = bool(data.get("needs_clarification"))
        data["trace_id"] = normalize_trace_id(data.get("trace_id"), task_id=str(data.get("task_id", "")).strip())
        data["attempt_id"] = normalize_attempt_id(
            data.get("attempt_id"),
            retry_count=int(data.get("retry_count") or 0),
        )
        data["context_payload"] = parse_json(str(data.get("context_payload") or ""))
        data["review_status"] = normalize_review_status(data.get("review_status"), default="unreviewed")
        data["review_mode"] = str(data.get("review_mode") or "").strip()
        data["review_head"] = str(data.get("review_head") or "").strip()
        data["reviewed_at"] = str(data.get("reviewed_at") or "").strip()
        missing_fields = str(data.get("context_fields_missing") or "").strip()
        data["context_fields_missing"] = [x for x in missing_fields.split(",") if x]
        recommended_missing_fields = str(data.get("context_fields_recommended_missing") or "").strip()
        data["context_fields_recommended_missing"] = [x for x in recommended_missing_fields.split(",") if x]
        data["required_capabilities"] = split_text_list(data.get("required_capabilities"))
        data["required_skills"] = split_text_list(data.get("required_skills"))
        data["allowed_agents"] = split_text_list(data.get("allowed_agents"))
        data["stage_id"] = str(data.get("stage_id") or "").strip()
        data["stage_score_gate"] = str(data.get("stage_score_gate") or "").strip().lower()
        data["stage_min_evidence_count"] = max(0, int(data.get("stage_min_evidence_count") or 0))
        data["stage_output_contract"] = parse_json(str(data.get("stage_output_contract") or ""))
        data["stage_verification_contract"] = parse_json(str(data.get("stage_verification_contract") or ""))
        data["workflow_profile_id"] = str(data.get("workflow_profile_id") or "").strip()
        data["workflow_channel"] = normalize_workflow_channel(data.get("workflow_channel"), default="")
        data["selection_reason"] = str(data.get("selection_reason") or "").strip()
        data["selection_inputs"] = parse_json(str(data.get("selection_inputs") or ""))
        data["score_payload"] = parse_json(str(data.get("score_payload") or ""))
        data["token_usage_summary"] = parse_json(str(data.get("token_usage_summary") or ""))
        data["context_completeness"] = round(float(data.get("context_completeness") or 0.0), 2)
        data["cost_estimate_total"] = round(float(data.get("cost_estimate_total") or 0.0), 6)
        data["started_at"] = str(data.get("started_at") or "").strip()
        data["completed_at"] = str(data.get("completed_at") or "").strip()
        return data

    def _sync_workflow_selection_record(
        self,
        *,
        task_id: str,
        workflow_profile_id: Any,
        workflow_channel: Any,
        selection_reason: Any,
        selection_inputs: Any,
        actor: str,
    ) -> None:
        normalized_profile_id = str(workflow_profile_id or "").strip()
        if not normalized_profile_id:
            self.conn.execute("DELETE FROM workflow_selection_records WHERE task_id = ?", (task_id,))
            return
        self.upsert_workflow_selection_record(
            task_id=task_id,
            workflow_profile_id=normalized_profile_id,
            workflow_channel=workflow_channel,
            selection_reason=selection_reason,
            selection_inputs=selection_inputs,
            selected_by=actor,
        )

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
        context_fields_recommended_missing = normalize_context_missing_fields(
            task.get("context_fields_recommended_missing")
        )
        review_status = normalize_review_status(task.get("review_status"), default="unreviewed")
        review_mode = str(task.get("review_mode", "")).strip()
        review_head = str(task.get("review_head", "")).strip()
        reviewed_at = str(task.get("reviewed_at", "")).strip()
        if (not reviewed_at) and review_status in {"reviewed", "fix_verified"}:
            reviewed_at = now
        owner = str(task.get("owner", "")).strip()
        change_id = str(task.get("change_id", "")).strip()
        workflow_profile_id = str(task.get("workflow_profile_id", "")).strip()
        workflow_channel = normalize_workflow_channel(task.get("workflow_channel"), default="")
        selection_reason = str(task.get("selection_reason", "")).strip()
        normalized_task_id = str(task.get("task_id") or "").strip()
        retry_count = max(0, int(task.get("retry_count", 0) or 0))
        selection_inputs_payload = normalize_json_object(task.get("selection_inputs"))
        trace_id = normalize_trace_id(
            task.get("trace_id")
            or context_payload_raw.get("trace_id")
            or selection_inputs_payload.get("trace_id", ""),
            task_id=normalized_task_id,
        )
        attempt_id = normalize_attempt_id(
            task.get("attempt_id") or selection_inputs_payload.get("attempt_id", ""),
            retry_count=retry_count,
        )
        context_payload_raw["trace_id"] = trace_id
        context_payload_raw["attempt_id"] = attempt_id
        selection_inputs_payload["trace_id"] = trace_id
        selection_inputs_payload["attempt_id"] = attempt_id
        task_for_envelope = dict(task)
        task_for_envelope.update(
            {
                "task_id": normalized_task_id,
                "trace_id": trace_id,
                "attempt_id": attempt_id,
                "request_source": request_source,
                "selection_inputs": selection_inputs_payload,
                "context_payload": context_payload_raw,
                "workflow_profile_id": workflow_profile_id,
                "workflow_channel": workflow_channel,
                "selection_reason": selection_reason,
            }
        )
        selection_inputs_payload["execution_envelope"] = self._build_execution_envelope_snapshot(task_for_envelope)
        selection_inputs = ensure_json(selection_inputs_payload)

        normalized = {
            "task_id": normalized_task_id
            or f"task-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
            "pool": str(task.get("pool", "jobs")).lower(),
            "task_type": str(task.get("task_type", "workflow")).strip(),
            "reason": str(task.get("reason", "")).strip(),
            "source": str(task.get("source", "openclaw")).strip(),
            "request_source": request_source,
            "trace_id": trace_id,
            "attempt_id": attempt_id,
            "priority": str(task.get("priority", "medium")).lower(),
            "risk_level": str(task.get("risk_level", "low")).lower(),
            "assignee": str(task.get("assignee", "")).strip() or None,
            "status": str(task.get("status", "pending")).lower(),
            "retry_count": retry_count,
            "failure_count": int(task.get("failure_count", 0) or 0),
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "need_human_confirm": 1 if to_bool(task.get("need_human_confirm", False)) else 0,
            "human_confirmed": 1 if to_bool(task.get("human_confirmed", False)) else 0,
            "context_completeness": context_completeness,
            "context_fields_missing": context_fields_missing,
            "context_fields_recommended_missing": context_fields_recommended_missing,
            "context_payload": ensure_json(context_payload_raw),
            "review_status": review_status,
            "review_mode": review_mode,
            "review_head": review_head,
            "reviewed_at": reviewed_at,
            "owner": owner,
            "change_id": change_id,
            "requirement": str(task.get("requirement", "")).strip(),
            "result_output": str(task.get("result_output", "")).strip(),
            "acceptance": str(task.get("acceptance", "")).strip(),
            "observable_outputs": str(task.get("observable_outputs", "")).strip(),
            "acceptance_thresholds": str(task.get("acceptance_thresholds", "")).strip(),
            "stage_id": str(task.get("stage_id", "")).strip(),
            "stage_score_gate": str(task.get("stage_score_gate", "")).strip().lower(),
            "stage_min_evidence_count": max(0, int(task.get("stage_min_evidence_count", 0) or 0)),
            "stage_output_contract": normalize_json_object_field(task.get("stage_output_contract")),
            "stage_verification_contract": normalize_json_object_field(task.get("stage_verification_contract")),
            "required_capabilities": normalize_text_list(task.get("required_capabilities")),
            "required_skills": normalize_text_list(task.get("required_skills")),
            "allowed_agents": normalize_text_list(task.get("allowed_agents")),
            "workflow_profile_id": workflow_profile_id,
            "workflow_channel": workflow_channel,
            "selection_reason": selection_reason,
            "selection_inputs": selection_inputs,
            "score_raw": task.get("score_raw"),
            "score_normalized": task.get("score_normalized"),
            "score_payload": ensure_json(task.get("score_payload") or {}),
            "token_usage_summary": ensure_json(task.get("token_usage_summary") or {}),
            "cost_estimate_total": float(task.get("cost_estimate_total", 0) or 0),
            "action": str(task.get("action", "")).strip() or None,
            "scheduled_at": task.get("scheduled_at"),
            "started_at": str(task.get("started_at", "")).strip(),
            "completed_at": str(task.get("completed_at", "")).strip(),
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
        if normalized["review_status"] not in TASK_REVIEW_STATUSES:
            raise TaskCenterError(f"invalid review_status: {normalized['review_status']}")

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

    def _task_exists(self, task_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return bool(row)

    def _lookup_task_trace_id(self, task_id: str) -> str:
        row = self.conn.execute(
            "SELECT trace_id FROM tasks WHERE task_id = ?",
            (str(task_id or "").strip(),),
        ).fetchone()
        raw = str(row["trace_id"] or "").strip() if row else ""
        return normalize_trace_id(raw, task_id=str(task_id or "").strip())

    def _build_execution_envelope_snapshot(self, task: dict[str, Any]) -> dict[str, Any]:
        task_payload = dict(task or {})
        selection_inputs_payload = normalize_json_object(task_payload.get("selection_inputs"))
        context_payload = normalize_json_object(task_payload.get("context_payload"))
        envelope = normalize_json_object(selection_inputs_payload.get("execution_envelope"))
        task_id = str(task_payload.get("task_id", "")).strip()
        retry_count = max(0, int(task_payload.get("retry_count", 0) or 0))
        trace_id = normalize_trace_id(
            task_payload.get("trace_id") or selection_inputs_payload.get("trace_id", ""),
            task_id=task_id,
        )
        attempt_id = normalize_attempt_id(
            task_payload.get("attempt_id") or selection_inputs_payload.get("attempt_id", ""),
            retry_count=retry_count,
        )

        workflow_payload = normalize_json_object(envelope.get("workflow"))
        workflow_payload.update(
            {
                "profile_id": str(workflow_payload.get("profile_id") or task_payload.get("workflow_profile_id", "")).strip(),
                "channel": str(workflow_payload.get("channel") or task_payload.get("workflow_channel", "")).strip(),
                "stage_id": str(workflow_payload.get("stage_id") or task_payload.get("stage_id", "")).strip(),
                "score_gate": str(workflow_payload.get("score_gate") or task_payload.get("stage_score_gate", "")).strip(),
                "selection_reason": str(
                    workflow_payload.get("selection_reason") or task_payload.get("selection_reason", "")
                ).strip(),
            }
        )

        task_section = normalize_json_object(envelope.get("task"))
        task_section.update(
            {
                "task_type": str(task_section.get("task_type") or task_payload.get("task_type", "")).strip(),
                "request_source": str(
                    task_section.get("request_source") or task_payload.get("request_source", "")
                ).strip(),
                "reason": str(task_section.get("reason") or task_payload.get("reason", "")).strip(),
                "requirement": str(task_section.get("requirement") or task_payload.get("requirement", "")).strip(),
                "acceptance": str(task_section.get("acceptance") or task_payload.get("acceptance", "")).strip(),
                "observable_outputs": str(
                    task_section.get("observable_outputs") or task_payload.get("observable_outputs", "")
                ).strip(),
                "assignee": str(task_section.get("assignee") or task_payload.get("assignee", "")).strip(),
                "priority": str(task_section.get("priority") or task_payload.get("priority", "")).strip(),
                "risk_level": str(task_section.get("risk_level") or task_payload.get("risk_level", "")).strip(),
                "needs_clarification": bool(task_payload.get("needs_clarification", False)),
            }
        )

        routing_payload = normalize_json_object(envelope.get("routing"))
        allowed_agents = task_payload.get("allowed_agents", [])
        if not isinstance(allowed_agents, list):
            allowed_agents = []
        routing_payload.update(
            {
                "assignee": str(routing_payload.get("assignee") or task_payload.get("assignee", "")).strip(),
                "allowed_agents": [str(item).strip() for item in allowed_agents if str(item).strip()],
            }
        )

        capability_payload = normalize_json_object(envelope.get("capability_binding"))
        if not capability_payload:
            capability_payload = normalize_json_object(selection_inputs_payload.get("capability_binding"))

        contracts_payload = normalize_json_object(envelope.get("contracts"))
        output_contract = normalize_json_object(contracts_payload.get("output_contract"))
        if not output_contract:
            output_contract = normalize_json_object(task_payload.get("stage_output_contract"))
        verification_contract = normalize_json_object(contracts_payload.get("verification_contract"))
        if not verification_contract:
            verification_contract = normalize_json_object(task_payload.get("stage_verification_contract"))
        stage_context_gate = normalize_json_object(contracts_payload.get("stage_context_gate"))
        if not stage_context_gate:
            stage_context_gate = normalize_json_object(selection_inputs_payload.get("stage_context_gate"))
        requirement_package_gate = normalize_json_object(contracts_payload.get("requirement_package_gate"))
        if not requirement_package_gate:
            requirement_package_gate = normalize_json_object(selection_inputs_payload.get("requirement_package_gate"))
        context_contract = normalize_json_object(contracts_payload.get("context_contract"))
        if not context_contract:
            context_contract = normalize_json_object(
                context_payload.get("context_contract") or context_payload.get("requirement_package_contract")
            )
        contracts_payload.update(
            {
                "output_contract": output_contract,
                "verification_contract": verification_contract,
                "stage_context_gate": stage_context_gate,
                "requirement_package_gate": requirement_package_gate,
                "context_contract": context_contract,
            }
        )

        return {
            "schema_version": str(envelope.get("schema_version", "2026-03-24")).strip() or "2026-03-24",
            "trace_id": trace_id,
            "attempt_id": attempt_id,
            "task_id": task_id,
            "workflow": workflow_payload,
            "task": task_section,
            "routing": routing_payload,
            "capability_binding": capability_payload,
            "contracts": contracts_payload,
        }

    def _lookup_task_execution_context(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(str(task_id or "").strip(), display_safe=False)
        execution_envelope = self._build_execution_envelope_snapshot(task)
        return {
            "trace_id": str(execution_envelope.get("trace_id", "")).strip(),
            "attempt_id": str(execution_envelope.get("attempt_id", "")).strip(),
            "execution_envelope": execution_envelope,
        }

    def create_task(self, task: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        payload = self._normalize_task(task)

        def write_op() -> None:
            exists = self.conn.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?",
                (payload["task_id"],),
            ).fetchone()
            if exists:
                raise TaskCenterError(f"task_id already exists: {payload['task_id']}")

            self.conn.execute(
                """
                INSERT INTO tasks (
                    task_id, pool, task_type, reason, source, request_source, trace_id, attempt_id, priority, risk_level,
                    assignee, status, retry_count, failure_count,
                    needs_clarification, clarification_reason,
                    need_human_confirm, human_confirmed,
                    context_completeness, context_fields_missing, context_fields_recommended_missing, context_payload,
                    review_status, review_mode, review_head, reviewed_at,
                    owner, change_id,
                    requirement, result_output, acceptance,
                    observable_outputs, acceptance_thresholds,
                    stage_id, stage_score_gate, stage_min_evidence_count,
                    stage_output_contract, stage_verification_contract,
                    required_capabilities, required_skills, allowed_agents,
                    workflow_profile_id, workflow_channel, selection_reason, selection_inputs,
                    score_raw, score_normalized, score_payload,
                    token_usage_summary, cost_estimate_total, action,
                    scheduled_at, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    :task_id, :pool, :task_type, :reason, :source, :request_source, :trace_id, :attempt_id, :priority, :risk_level,
                    :assignee, :status, :retry_count, :failure_count,
                    :needs_clarification, :clarification_reason,
                    :need_human_confirm, :human_confirmed,
                    :context_completeness, :context_fields_missing, :context_fields_recommended_missing, :context_payload,
                    :review_status, :review_mode, :review_head, :reviewed_at,
                    :owner, :change_id,
                    :requirement, :result_output, :acceptance,
                    :observable_outputs, :acceptance_thresholds,
                    :stage_id, :stage_score_gate, :stage_min_evidence_count,
                    :stage_output_contract, :stage_verification_contract,
                    :required_capabilities, :required_skills, :allowed_agents,
                    :workflow_profile_id, :workflow_channel, :selection_reason, :selection_inputs,
                    :score_raw, :score_normalized, :score_payload,
                    :token_usage_summary, :cost_estimate_total, :action,
                    :scheduled_at, :started_at, :completed_at, :created_at, :updated_at
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
                    "trace_id": payload["trace_id"],
                    "attempt_id": payload["attempt_id"],
                    "needs_clarification": bool(payload["needs_clarification"]),
                    "review_status": payload.get("review_status", "unreviewed"),
                    "review_mode": payload.get("review_mode", ""),
                    "owner": payload.get("owner", ""),
                    "change_id": payload.get("change_id", ""),
                    "workflow_profile_id": payload.get("workflow_profile_id", ""),
                    "workflow_channel": payload.get("workflow_channel", ""),
                },
            )
            self._sync_workflow_selection_record(
                task_id=payload["task_id"],
                workflow_profile_id=payload.get("workflow_profile_id", ""),
                workflow_channel=payload.get("workflow_channel", ""),
                selection_reason=payload.get("selection_reason", ""),
                selection_inputs=payload.get("selection_inputs", "{}"),
                actor=actor,
            )

        self._run_transaction_with_retry(write_op)
        return self.get_task(payload["task_id"])

    def update_task(self, task_id: str, actor: str, fields: dict[str, Any]) -> dict[str, Any]:
        if not self._task_exists(task_id):
            raise TaskCenterError(f"task not found: {task_id}")
        if not isinstance(fields, dict) or not fields:
            raise TaskCenterError("fields must be non-empty object")

        allowed_fields = {
            "task_type",
            "reason",
            "source",
            "request_source",
            "trace_id",
            "attempt_id",
            "priority",
            "risk_level",
            "assignee",
            "status",
            "retry_count",
            "failure_count",
            "need_human_confirm",
            "human_confirmed",
            "needs_clarification",
            "clarification_reason",
            "context_completeness",
            "context_fields_missing",
            "context_fields_recommended_missing",
            "context_payload",
            "review_status",
            "review_mode",
            "review_head",
            "reviewed_at",
            "owner",
            "change_id",
            "requirement",
            "result_output",
            "acceptance",
            "observable_outputs",
            "acceptance_thresholds",
            "stage_id",
            "stage_score_gate",
            "stage_min_evidence_count",
            "stage_output_contract",
            "stage_verification_contract",
            "required_capabilities",
            "required_skills",
            "allowed_agents",
            "workflow_profile_id",
            "workflow_channel",
            "selection_reason",
            "selection_inputs",
            "score_raw",
            "score_normalized",
            "score_payload",
            "token_usage_summary",
            "cost_estimate_total",
            "action",
            "scheduled_at",
            "started_at",
            "completed_at",
        }

        updates: dict[str, Any] = {}
        for key, value in fields.items():
            name = str(key or "").strip()
            if not name:
                continue
            if name not in allowed_fields:
                raise TaskCenterError(f"field not allowed for update: {name}")
            updates[name] = value
        if not updates:
            raise TaskCenterError("no valid fields to update")

        if "priority" in updates:
            updates["priority"] = str(updates["priority"]).strip().lower()
            if updates["priority"] not in TASK_PRIORITIES:
                raise TaskCenterError(f"invalid priority: {updates['priority']}")
        if "risk_level" in updates:
            updates["risk_level"] = str(updates["risk_level"]).strip().lower()
            if updates["risk_level"] not in TASK_RISK_LEVELS:
                raise TaskCenterError(f"invalid risk_level: {updates['risk_level']}")
        if "status" in updates:
            updates["status"] = str(updates["status"]).strip().lower()
            if updates["status"] not in TASK_STATUSES:
                raise TaskCenterError(f"invalid status: {updates['status']}")
        if "retry_count" in updates:
            try:
                updates["retry_count"] = max(0, int(updates["retry_count"] or 0))
            except (TypeError, ValueError) as exc:
                raise TaskCenterError(f"invalid retry_count: {updates['retry_count']}") from exc
        if "failure_count" in updates:
            try:
                updates["failure_count"] = max(0, int(updates["failure_count"] or 0))
            except (TypeError, ValueError) as exc:
                raise TaskCenterError(f"invalid failure_count: {updates['failure_count']}") from exc
        if "review_status" in updates:
            updates["review_status"] = normalize_review_status(updates["review_status"], default="unreviewed")
        if "review_mode" in updates:
            updates["review_mode"] = str(updates["review_mode"] or "").strip()
        if "review_head" in updates:
            updates["review_head"] = str(updates["review_head"] or "").strip()
        if "reviewed_at" in updates:
            updates["reviewed_at"] = str(updates["reviewed_at"] or "").strip()
        if "request_source" in updates:
            updates["request_source"] = normalize_request_source(updates["request_source"], default="human")
        if "trace_id" in updates:
            updates["trace_id"] = normalize_trace_id(updates["trace_id"], task_id=task_id)
        if "attempt_id" in updates:
            retry_count_for_attempt = updates.get("retry_count", self.get_task(task_id, display_safe=False).get("retry_count", 0))
            updates["attempt_id"] = normalize_attempt_id(
                updates["attempt_id"],
                retry_count=int(retry_count_for_attempt or 0),
            )
        if "needs_clarification" in updates:
            updates["needs_clarification"] = 1 if to_bool(updates["needs_clarification"]) else 0
        if "need_human_confirm" in updates:
            updates["need_human_confirm"] = 1 if to_bool(updates["need_human_confirm"]) else 0
        if "human_confirmed" in updates:
            updates["human_confirmed"] = 1 if to_bool(updates["human_confirmed"]) else 0
        if "context_completeness" in updates:
            try:
                completeness = float(updates["context_completeness"] or 0.0)
            except (TypeError, ValueError):
                completeness = 0.0
            updates["context_completeness"] = max(0.0, min(100.0, completeness))
        if "context_fields_missing" in updates:
            updates["context_fields_missing"] = normalize_context_missing_fields(updates["context_fields_missing"])
        if "context_fields_recommended_missing" in updates:
            updates["context_fields_recommended_missing"] = normalize_context_missing_fields(
                updates["context_fields_recommended_missing"]
            )
        if "required_capabilities" in updates:
            updates["required_capabilities"] = normalize_text_list(updates["required_capabilities"])
        if "required_skills" in updates:
            updates["required_skills"] = normalize_text_list(updates["required_skills"])
        if "allowed_agents" in updates:
            updates["allowed_agents"] = normalize_text_list(updates["allowed_agents"])
        if "stage_id" in updates:
            updates["stage_id"] = str(updates["stage_id"] or "").strip()
        if "stage_score_gate" in updates:
            updates["stage_score_gate"] = str(updates["stage_score_gate"] or "").strip().lower()
        if "stage_min_evidence_count" in updates:
            try:
                updates["stage_min_evidence_count"] = max(0, int(updates["stage_min_evidence_count"] or 0))
            except (TypeError, ValueError) as exc:
                raise TaskCenterError(
                    f"invalid stage_min_evidence_count: {updates['stage_min_evidence_count']}"
                ) from exc
        if "stage_output_contract" in updates:
            updates["stage_output_contract"] = normalize_json_object_field(updates["stage_output_contract"])
        if "stage_verification_contract" in updates:
            updates["stage_verification_contract"] = normalize_json_object_field(
                updates["stage_verification_contract"]
            )
        if "workflow_profile_id" in updates:
            updates["workflow_profile_id"] = str(updates["workflow_profile_id"] or "").strip()
        if "workflow_channel" in updates:
            updates["workflow_channel"] = normalize_workflow_channel(updates["workflow_channel"], default="")
        if "selection_reason" in updates:
            updates["selection_reason"] = str(updates["selection_reason"] or "").strip()
        if "selection_inputs" in updates:
            updates["selection_inputs"] = normalize_json_object_field(updates["selection_inputs"])
        if "context_payload" in updates:
            payload = updates["context_payload"]
            if isinstance(payload, str):
                parsed = parse_json(payload)
                payload = parsed if parsed else {"raw": payload}
            if not isinstance(payload, dict):
                payload = {"raw": str(payload)}
            updates["context_payload"] = ensure_json(payload)
        if "score_payload" in updates:
            payload = updates["score_payload"]
            if isinstance(payload, str):
                payload = parse_json(payload) or {"raw": payload}
            updates["score_payload"] = ensure_json(payload if isinstance(payload, dict) else {"raw": str(payload)})
        if "token_usage_summary" in updates:
            payload = updates["token_usage_summary"]
            if isinstance(payload, str):
                payload = parse_json(payload) or {"raw": payload}
            updates["token_usage_summary"] = ensure_json(
                payload if isinstance(payload, dict) else {"raw": str(payload)}
            )
        if "assignee" in updates:
            assignee = str(updates["assignee"] or "").strip()
            updates["assignee"] = assignee or None
        if "started_at" in updates:
            updates["started_at"] = str(updates["started_at"] or "").strip()
        if "completed_at" in updates:
            updates["completed_at"] = str(updates["completed_at"] or "").strip()
        if (
            "review_status" in updates
            and "reviewed_at" not in updates
            and str(updates.get("review_status", "")).strip().lower() in {"reviewed", "fix_verified"}
        ):
            updates["reviewed_at"] = utc_now_iso()

        updates["updated_at"] = utc_now_iso()
        cols = [f"{name} = ?" for name in updates.keys()]
        vals = list(updates.values()) + [task_id]
        current_selection = self.conn.execute(
            """
            SELECT workflow_profile_id, workflow_channel, selection_reason, selection_inputs
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not current_selection:
            raise TaskCenterError(f"task not found: {task_id}")
        selection_payload = {
            "workflow_profile_id": str(current_selection["workflow_profile_id"] or "").strip(),
            "workflow_channel": normalize_workflow_channel(current_selection["workflow_channel"], default=""),
            "selection_reason": str(current_selection["selection_reason"] or "").strip(),
            "selection_inputs": str(current_selection["selection_inputs"] or "").strip(),
        }
        for key in ("workflow_profile_id", "workflow_channel", "selection_reason", "selection_inputs"):
            if key in updates:
                selection_payload[key] = updates[key]

        def write_op() -> None:
            self.conn.execute(
                f"UPDATE tasks SET {', '.join(cols)} WHERE task_id = ?",
                vals,
            )
            self._sync_workflow_selection_record(
                task_id=task_id,
                workflow_profile_id=selection_payload.get("workflow_profile_id", ""),
                workflow_channel=selection_payload.get("workflow_channel", ""),
                selection_reason=selection_payload.get("selection_reason", ""),
                selection_inputs=selection_payload.get("selection_inputs", "{}"),
                actor=actor,
            )
            self.add_event(
                task_id=task_id,
                actor=actor,
                event_type="task_updated",
                stage="task_update",
                details={"updated_fields": sorted(k for k in updates.keys() if k != "updated_at")},
            )

        self._run_transaction_with_retry(write_op)
        return self.get_task(task_id)

    def get_task(self, task_id: str, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise TaskCenterError(f"task not found: {task_id}")

        data = self._deserialize_task_row(row)
        return sanitize_display_payload(data) if display_safe else data

    def get_workflow_selection_record(self, task_id: str, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT *
            FROM workflow_selection_records
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            raise TaskCenterError(f"workflow selection record not found for task: {task_id}")
        item = dict(row)
        item["workflow_profile_id"] = str(item.get("workflow_profile_id") or "").strip()
        item["workflow_channel"] = normalize_workflow_channel(item.get("workflow_channel"), default="")
        item["selection_reason"] = str(item.get("selection_reason") or "").strip()
        item["selection_inputs"] = parse_json(str(item.get("selection_inputs") or ""))
        item["selected_by"] = str(item.get("selected_by") or "").strip()
        return sanitize_display_payload(item) if display_safe else item

    def upsert_workflow_selection_record(
        self,
        *,
        task_id: str,
        workflow_profile_id: str,
        workflow_channel: str = "",
        selection_reason: str = "",
        selection_inputs: Any = None,
        selected_by: str = "",
    ) -> dict[str, Any]:
        if not self._task_exists(task_id):
            raise TaskCenterError(f"task not found: {task_id}")
        profile_id = str(workflow_profile_id or "").strip()
        if not profile_id:
            raise TaskCenterError("workflow_profile_id cannot be empty")
        channel = normalize_workflow_channel(workflow_channel, default="")
        reason = str(selection_reason or "").strip()
        selected_by_text = str(selected_by or "").strip()
        inputs_json = normalize_json_object_field(selection_inputs)
        existing = self.conn.execute(
            """
            SELECT selection_id, created_at
            FROM workflow_selection_records
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        now = utc_now_iso()
        selection_id = (
            str(existing["selection_id"]).strip()
            if existing and str(existing["selection_id"]).strip()
            else f"selection-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )
        created_at = str(existing["created_at"]).strip() if existing else now
        payload = {
            "selection_id": selection_id,
            "task_id": task_id,
            "workflow_profile_id": profile_id,
            "workflow_channel": channel,
            "selection_reason": reason,
            "selection_inputs": inputs_json,
            "selected_by": selected_by_text,
            "created_at": created_at,
            "updated_at": now,
        }

        def write_op() -> None:
            self.conn.execute(
                """
                INSERT INTO workflow_selection_records (
                    selection_id, task_id, workflow_profile_id, workflow_channel,
                    selection_reason, selection_inputs, selected_by, created_at, updated_at
                ) VALUES (
                    :selection_id, :task_id, :workflow_profile_id, :workflow_channel,
                    :selection_reason, :selection_inputs, :selected_by, :created_at, :updated_at
                )
                ON CONFLICT(task_id) DO UPDATE SET
                    workflow_profile_id = excluded.workflow_profile_id,
                    workflow_channel = excluded.workflow_channel,
                    selection_reason = excluded.selection_reason,
                    selection_inputs = excluded.selection_inputs,
                    selected_by = excluded.selected_by,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            self.add_event(
                task_id=task_id,
                actor=selected_by_text or "workflow-selector",
                event_type="workflow_selected",
                stage="workflow_select",
                details={
                    "selection_id": selection_id,
                    "workflow_profile_id": profile_id,
                    "workflow_channel": channel,
                    "selection_reason": reason,
                },
            )

        self._run_transaction_with_retry(write_op)
        return self.get_workflow_selection_record(task_id)

    def add_event(
        self,
        task_id: str,
        actor: str,
        event_type: str,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        def write_op() -> None:
            self.conn.execute(
                """
                INSERT INTO task_events (task_id, ts, actor, event_type, stage, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, utc_now_iso(), actor, event_type, stage, ensure_json(details)),
            )

        self._run_transaction_with_retry(write_op)

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

        def write_op() -> int:
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
            return int(cursor.lastrowid)

        stage_run_id = int(self._run_transaction_with_retry(write_op))
        return self.get_stage_run(stage_run_id)

    def get_stage_run(self, stage_run_id: int, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM stage_runs WHERE id = ?", (int(stage_run_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"stage_run not found: {stage_run_id}")
        out = dict(row)
        out["details"] = parse_json(out.pop("details_json", ""))
        return sanitize_display_payload(out) if display_safe else out

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

        def write_op() -> None:
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

        self._run_transaction_with_retry(write_op)
        return self.get_stage_run(int(row["id"]))

    def list_stage_runs(self, task_id: str, display_safe: bool = True) -> list[dict[str, Any]]:
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
        return sanitize_display_payload(out) if display_safe else out

    def get_module_log(self, log_id: int, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM module_logs WHERE id = ?", (int(log_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"module_log not found: {log_id}")
        item = dict(row)
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def record_module_log(
        self,
        *,
        task_id: str = "",
        module_name: str,
        phase: str,
        level: str,
        status: str,
        message: str,
        duration_ms: int = 0,
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        module = str(module_name or "").strip()
        stage = str(phase or "").strip() or "runtime"
        normalized_level = str(level or "").strip().lower() or "info"
        normalized_status = str(status or "").strip().lower() or "running"
        note = str(message or "").strip()
        if not module:
            raise TaskCenterError("module_name cannot be empty")
        if not note:
            raise TaskCenterError("message cannot be empty")
        if normalized_level not in MODULE_LOG_LEVELS:
            raise TaskCenterError(f"invalid module log level: {normalized_level}")
        if normalized_status not in MODULE_RUN_STATUSES:
            raise TaskCenterError(f"invalid module run status: {normalized_status}")

        row_task_id = str(task_id or "").strip() or None
        if row_task_id and (not self._task_exists(row_task_id)):
            raise TaskCenterError(f"task not found: {row_task_id}")

        def write_op() -> int:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO module_logs (
                        task_id, ts, module_name, phase, level, status, message, duration_ms, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_task_id,
                        utc_now_iso(),
                        module,
                        stage,
                        normalized_level,
                        normalized_status,
                        note,
                        max(0, int(duration_ms or 0)),
                        ensure_json(details),
                    ),
                )
                log_id = int(cursor.lastrowid)
                if row_task_id:
                    self.add_event(
                        task_id=row_task_id,
                        actor=(str(actor or "").strip() or module),
                        event_type="module_log_recorded",
                        stage=stage,
                        details={
                            "module_name": module,
                            "level": normalized_level,
                            "status": normalized_status,
                            "message": note,
                            "duration_ms": max(0, int(duration_ms or 0)),
                        },
                    )
            return log_id

        log_id = int(self._run_write_with_retry(write_op))
        return self.get_module_log(log_id)

    def list_module_logs(self, task_id: str, limit: int = 200, display_safe: bool = True) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 2000))
        rows = self.conn.execute(
            """
            SELECT *
            FROM module_logs
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
        return sanitize_display_payload(out) if display_safe else out

    def get_module_communication(self, comm_id: int, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM module_communications WHERE id = ?", (int(comm_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"module_communication not found: {comm_id}")
        item = dict(row)
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def record_module_communication(
        self,
        *,
        task_id: str = "",
        from_module: str,
        to_module: str,
        protocol: str,
        message_type: str,
        status: str,
        latency_ms: int = 0,
        correlation_id: str = "",
        payload_ref: str = "",
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        src = str(from_module or "").strip()
        dst = str(to_module or "").strip()
        proto = str(protocol or "").strip() or "internal"
        msg_type = str(message_type or "").strip() or "handoff"
        normalized_status = str(status or "").strip().lower() or "sent"
        if not src:
            raise TaskCenterError("from_module cannot be empty")
        if not dst:
            raise TaskCenterError("to_module cannot be empty")
        if normalized_status not in COMMUNICATION_STATUSES:
            raise TaskCenterError(f"invalid communication status: {normalized_status}")

        row_task_id = str(task_id or "").strip() or None
        if row_task_id and (not self._task_exists(row_task_id)):
            raise TaskCenterError(f"task not found: {row_task_id}")

        def write_op() -> int:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO module_communications (
                        task_id, ts, from_module, to_module, protocol, message_type,
                        status, latency_ms, correlation_id, payload_ref, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_task_id,
                        utc_now_iso(),
                        src,
                        dst,
                        proto,
                        msg_type,
                        normalized_status,
                        max(0, int(latency_ms or 0)),
                        str(correlation_id or "").strip(),
                        str(payload_ref or "").strip(),
                        ensure_json(details),
                    ),
                )
                comm_id = int(cursor.lastrowid)
                if row_task_id:
                    self.add_event(
                        task_id=row_task_id,
                        actor=(str(actor or "").strip() or src),
                        event_type="module_communication_recorded",
                        stage="communication",
                        details={
                            "from_module": src,
                            "to_module": dst,
                            "protocol": proto,
                            "message_type": msg_type,
                            "status": normalized_status,
                            "latency_ms": max(0, int(latency_ms or 0)),
                            "correlation_id": str(correlation_id or "").strip(),
                        },
                    )
            return comm_id

        comm_id = int(self._run_write_with_retry(write_op))
        return self.get_module_communication(comm_id)

    def list_module_communications(
        self,
        task_id: str,
        limit: int = 200,
        display_safe: bool = True,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 2000))
        rows = self.conn.execute(
            """
            SELECT *
            FROM module_communications
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
        return sanitize_display_payload(out) if display_safe else out

    def get_task_output(self, output_id: int, display_safe: bool = True) -> dict[str, Any]:
        """Return a single standardized task output record."""
        row = self.conn.execute("SELECT * FROM task_outputs WHERE id = ?", (int(output_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"task_output not found: {output_id}")
        item = dict(row)
        item["payload"] = parse_json(item.pop("payload_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def record_task_output(
        self,
        *,
        task_id: str,
        output_type: str,
        audience: str,
        trace_id: str = "",
        channel: str = "",
        status: str,
        summary: str = "",
        payload: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        """Persist a standardized output packet for human or machine delivery."""
        row_task_id = str(task_id or "").strip()
        normalized_type = str(output_type or "").strip() or "task_report"
        normalized_audience = str(audience or "").strip().lower() or "human"
        normalized_status = str(status or "").strip().lower() or "prepared"
        normalized_channel = str(channel or "").strip().lower()
        normalized_summary = str(summary or "").strip()
        if not row_task_id:
            raise TaskCenterError("task_id cannot be empty")
        if not self._task_exists(row_task_id):
            raise TaskCenterError(f"task not found: {row_task_id}")
        execution_context = self._lookup_task_execution_context(row_task_id)
        normalized_trace_id = normalize_trace_id(
            trace_id or execution_context.get("trace_id", ""),
            task_id=row_task_id,
        )
        attempt_id = str(execution_context.get("attempt_id", "")).strip()
        execution_envelope = normalize_json_object(execution_context.get("execution_envelope"))
        if normalized_audience not in TASK_OUTPUT_AUDIENCES:
            raise TaskCenterError(f"invalid task output audience: {normalized_audience}")
        if normalized_status not in TASK_OUTPUT_STATUSES:
            raise TaskCenterError(f"invalid task output status: {normalized_status}")
        payload_object = normalize_json_object(payload)
        payload_object.setdefault("trace_id", normalized_trace_id)
        payload_object.setdefault("attempt_id", attempt_id)
        if execution_envelope:
            payload_object.setdefault("execution_envelope", execution_envelope)

        def write_op() -> int:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO task_outputs (
                        task_id, ts, trace_id, output_type, audience, channel, status, summary, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_task_id,
                        utc_now_iso(),
                        normalized_trace_id,
                        normalized_type,
                        normalized_audience,
                        normalized_channel,
                        normalized_status,
                        normalized_summary,
                        ensure_json(payload_object),
                    ),
                )
                output_id = int(cursor.lastrowid)
                self.add_event(
                    task_id=row_task_id,
                    actor=(str(actor or "").strip() or normalized_audience),
                    event_type="task_output_recorded",
                    stage="delivery",
                    details={
                        "output_type": normalized_type,
                        "audience": normalized_audience,
                        "channel": normalized_channel,
                        "status": normalized_status,
                        "summary": normalized_summary,
                        "trace_id": normalized_trace_id,
                    },
                )
            return output_id

        output_id = int(self._run_write_with_retry(write_op))
        return self.get_task_output(output_id)

    def list_task_outputs(self, task_id: str, limit: int = 200, display_safe: bool = True) -> list[dict[str, Any]]:
        """List standardized output packets for a task."""
        limit = max(1, min(int(limit or 200), 2000))
        rows = self.conn.execute(
            """
            SELECT *
            FROM task_outputs
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = parse_json(item.pop("payload_json", ""))
            out.append(item)
        out.reverse()
        return sanitize_display_payload(out) if display_safe else out

    def get_task_incident(self, incident_id: int, display_safe: bool = True) -> dict[str, Any]:
        """Return a single task incident record."""
        row = self.conn.execute("SELECT * FROM task_incidents WHERE id = ?", (int(incident_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"task_incident not found: {incident_id}")
        item = dict(row)
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def record_task_incident(
        self,
        *,
        task_id: str,
        incident_type: str,
        severity: str,
        trace_id: str = "",
        status: str = "open",
        reason: str = "",
        summary: str = "",
        owner: str = "",
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        """Persist a normalized incident or escalation record for a task."""
        row_task_id = str(task_id or "").strip()
        normalized_type = str(incident_type or "").strip() or "runtime_issue"
        normalized_severity = str(severity or "").strip().lower() or "warning"
        normalized_status = str(status or "").strip().lower() or "open"
        normalized_reason = str(reason or "").strip()
        normalized_summary = str(summary or "").strip()
        normalized_owner = str(owner or "").strip()
        if not row_task_id:
            raise TaskCenterError("task_id cannot be empty")
        if not self._task_exists(row_task_id):
            raise TaskCenterError(f"task not found: {row_task_id}")
        execution_context = self._lookup_task_execution_context(row_task_id)
        normalized_trace_id = normalize_trace_id(
            trace_id or execution_context.get("trace_id", ""),
            task_id=row_task_id,
        )
        attempt_id = str(execution_context.get("attempt_id", "")).strip()
        execution_envelope = normalize_json_object(execution_context.get("execution_envelope"))
        if normalized_severity not in INCIDENT_SEVERITIES:
            raise TaskCenterError(f"invalid incident severity: {normalized_severity}")
        if normalized_status not in INCIDENT_STATUSES:
            raise TaskCenterError(f"invalid incident status: {normalized_status}")
        details_object = normalize_json_object(details)
        details_object.setdefault("trace_id", normalized_trace_id)
        details_object.setdefault("attempt_id", attempt_id)
        if execution_envelope:
            details_object.setdefault("execution_envelope", execution_envelope)

        def write_op() -> int:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO task_incidents (
                        task_id, ts, trace_id, incident_type, severity, status, reason, summary, owner, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_task_id,
                        utc_now_iso(),
                        normalized_trace_id,
                        normalized_type,
                        normalized_severity,
                        normalized_status,
                        normalized_reason,
                        normalized_summary,
                        normalized_owner,
                        ensure_json(details_object),
                    ),
                )
                incident_id = int(cursor.lastrowid)
                self.add_event(
                    task_id=row_task_id,
                    actor=(str(actor or "").strip() or normalized_owner or normalized_type),
                    event_type="task_incident_recorded",
                    stage="incident",
                    details={
                        "incident_type": normalized_type,
                        "severity": normalized_severity,
                        "status": normalized_status,
                        "reason": normalized_reason,
                        "summary": normalized_summary,
                        "owner": normalized_owner,
                        "trace_id": normalized_trace_id,
                    },
                )
            return incident_id

        incident_id = int(self._run_write_with_retry(write_op))
        return self.get_task_incident(incident_id)

    def list_task_incidents(self, task_id: str, limit: int = 200, display_safe: bool = True) -> list[dict[str, Any]]:
        """List task incidents in chronological order."""
        limit = max(1, min(int(limit or 200), 2000))
        rows = self.conn.execute(
            """
            SELECT *
            FROM task_incidents
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
        return sanitize_display_payload(out) if display_safe else out

    def update_task_incident(
        self,
        incident_id: int,
        *,
        status: str = "",
        reason: str | None = None,
        summary: str | None = None,
        owner: str | None = None,
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        """Update one incident lifecycle record and append an audit event."""
        existing = self.get_task_incident(int(incident_id), display_safe=False)
        normalized_status = str(status or "").strip().lower()
        if normalized_status and normalized_status not in INCIDENT_STATUSES:
            raise TaskCenterError(f"invalid incident status: {normalized_status}")

        updates: dict[str, Any] = {}
        event_details: dict[str, Any] = {"incident_id": int(incident_id)}
        if normalized_status:
            updates["status"] = normalized_status
            event_details["status"] = normalized_status
        if reason is not None:
            updates["reason"] = str(reason or "").strip()
            event_details["reason"] = updates["reason"]
        if summary is not None:
            updates["summary"] = str(summary or "").strip()
            event_details["summary"] = updates["summary"]
        if owner is not None:
            updates["owner"] = str(owner or "").strip()
            event_details["owner"] = updates["owner"]
        if details is not None:
            merged_details = dict(existing.get("details", {}))
            merged_details.update(details)
            merged_details["last_status_updated_at"] = utc_now_iso()
            merged_details["last_status_updated_by"] = str(actor or "").strip()
            updates["details_json"] = ensure_json(merged_details)
            event_details["details_keys"] = sorted(merged_details.keys())
        elif updates:
            existing_details = dict(existing.get("details", {}))
            existing_details["last_status_updated_at"] = utc_now_iso()
            existing_details["last_status_updated_by"] = str(actor or "").strip()
            updates["details_json"] = ensure_json(existing_details)

        if not updates:
            raise TaskCenterError("incident update requires at least one field")

        updates["ts"] = utc_now_iso()
        assignments = ", ".join(f"{field} = :{field}" for field in updates.keys())
        payload = dict(updates)
        payload["incident_id"] = int(incident_id)

        def write_op() -> None:
            with self.conn:
                self.conn.execute(
                    f"""
                    UPDATE task_incidents
                    SET {assignments}
                    WHERE id = :incident_id
                    """,
                    payload,
                )
                self.add_event(
                    task_id=str(existing.get("task_id", "")).strip(),
                    actor=(str(actor or "").strip() or str(existing.get("owner", "")).strip() or "incident-manager"),
                    event_type="task_incident_updated",
                    stage="incident",
                    details=event_details,
                )

        self._run_transaction_with_retry(write_op)
        return self.get_task_incident(int(incident_id))

    def get_benchmark_run(self, benchmark_run_id: str, display_safe: bool = True) -> dict[str, Any]:
        """Return one persisted benchmark run record by its stable benchmark_run_id."""
        row = self.conn.execute(
            "SELECT * FROM benchmark_runs WHERE benchmark_run_id = ?",
            (str(benchmark_run_id or "").strip(),),
        ).fetchone()
        if not row:
            raise TaskCenterError(f"benchmark_run not found: {benchmark_run_id}")
        item = dict(row)
        item["baseline_run_ids"] = parse_json_list(item.pop("baseline_run_ids", ""))
        item["candidate_run_ids"] = parse_json_list(item.pop("candidate_run_ids", ""))
        item["decision"] = parse_json(item.pop("decision_json", ""))
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def record_benchmark_run(
        self,
        *,
        benchmark_run_id: str,
        benchmark_suite_id: str,
        trace_id: str = "",
        workflow_profile_id: str = "",
        workflow_channel: str = "",
        target_kind: str,
        target_id: str,
        baseline_run_ids: list[str] | tuple[str, ...] | str = (),
        candidate_run_ids: list[str] | tuple[str, ...] | str = (),
        summary_file: str = "",
        scorecard_file: str = "",
        decision: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        task_id: str = "",
        actor: str = "",
    ) -> dict[str, Any]:
        """Persist one benchmark suite execution result for later promotion/audit use."""
        benchmark_id = str(benchmark_run_id or "").strip()
        suite_id = str(benchmark_suite_id or "").strip()
        target_kind_norm = str(target_kind or "").strip().lower()
        target_name = str(target_id or "").strip()
        task_id_norm = str(task_id or "").strip() or None
        if not benchmark_id:
            raise TaskCenterError("benchmark_run_id cannot be empty")
        if not suite_id:
            raise TaskCenterError("benchmark_suite_id cannot be empty")
        if target_kind_norm not in BINDING_TARGET_KINDS:
            raise TaskCenterError(f"invalid benchmark target_kind: {target_kind_norm}")
        if not target_name:
            raise TaskCenterError("target_id cannot be empty")
        if task_id_norm and (not self._task_exists(task_id_norm)):
            raise TaskCenterError(f"task not found: {task_id_norm}")
        execution_context: dict[str, Any] = {}
        if task_id_norm:
            execution_context = self._lookup_task_execution_context(task_id_norm)
        normalized_trace_id = normalize_trace_id(
            trace_id or execution_context.get("trace_id", ""),
            task_id=task_id_norm or "",
        )
        attempt_id = str(execution_context.get("attempt_id", "")).strip()
        execution_envelope = normalize_json_object(execution_context.get("execution_envelope"))

        if isinstance(baseline_run_ids, str):
            baseline_ids = [item.strip() for item in baseline_run_ids.split(",") if item.strip()]
        else:
            baseline_ids = [str(item).strip() for item in baseline_run_ids if str(item).strip()]
        if isinstance(candidate_run_ids, str):
            candidate_ids = [item.strip() for item in candidate_run_ids.split(",") if item.strip()]
        else:
            candidate_ids = [str(item).strip() for item in candidate_run_ids if str(item).strip()]

        details_object = normalize_json_object(details)
        details_object.setdefault("trace_id", normalized_trace_id)
        details_object.setdefault("attempt_id", attempt_id)
        if execution_envelope:
            details_object.setdefault("execution_envelope", execution_envelope)

        payload = {
            "benchmark_run_id": benchmark_id,
            "task_id": task_id_norm,
            "ts": utc_now_iso(),
            "trace_id": normalized_trace_id,
            "benchmark_suite_id": suite_id,
            "workflow_profile_id": str(workflow_profile_id or "").strip(),
            "workflow_channel": str(workflow_channel or "").strip(),
            "target_kind": target_kind_norm,
            "target_id": target_name,
            "baseline_run_ids": ensure_json_list(baseline_ids),
            "candidate_run_ids": ensure_json_list(candidate_ids),
            "summary_file": str(summary_file or "").strip(),
            "scorecard_file": str(scorecard_file or "").strip(),
            "decision_json": ensure_json(decision),
            "details_json": ensure_json(details_object),
        }

        def write_op() -> None:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO benchmark_runs (
                        benchmark_run_id, task_id, ts, trace_id, benchmark_suite_id,
                        workflow_profile_id, workflow_channel, target_kind, target_id,
                        baseline_run_ids, candidate_run_ids, summary_file, scorecard_file,
                        decision_json, details_json
                    ) VALUES (
                        :benchmark_run_id, :task_id, :ts, :trace_id, :benchmark_suite_id,
                        :workflow_profile_id, :workflow_channel, :target_kind, :target_id,
                        :baseline_run_ids, :candidate_run_ids, :summary_file, :scorecard_file,
                        :decision_json, :details_json
                    )
                    ON CONFLICT(benchmark_run_id) DO UPDATE SET
                        task_id = excluded.task_id,
                        ts = excluded.ts,
                        trace_id = excluded.trace_id,
                        benchmark_suite_id = excluded.benchmark_suite_id,
                        workflow_profile_id = excluded.workflow_profile_id,
                        workflow_channel = excluded.workflow_channel,
                        target_kind = excluded.target_kind,
                        target_id = excluded.target_id,
                        baseline_run_ids = excluded.baseline_run_ids,
                        candidate_run_ids = excluded.candidate_run_ids,
                        summary_file = excluded.summary_file,
                        scorecard_file = excluded.scorecard_file,
                        decision_json = excluded.decision_json,
                        details_json = excluded.details_json
                    """,
                    payload,
                )
                if task_id_norm:
                    self.add_event(
                        task_id=task_id_norm,
                        actor=(str(actor or "").strip() or "benchmark-runner"),
                        event_type="benchmark_run_recorded",
                        stage="benchmark",
                        details={
                            "benchmark_run_id": benchmark_id,
                            "benchmark_suite_id": suite_id,
                            "target_kind": target_kind_norm,
                            "target_id": target_name,
                            "trace_id": normalized_trace_id,
                        },
                    )

        self._run_write_with_retry(write_op)
        return self.get_benchmark_run(benchmark_id)

    def list_benchmark_runs(
        self,
        task_id: str = "",
        *,
        benchmark_suite_id: str = "",
        limit: int = 200,
        display_safe: bool = True,
    ) -> list[dict[str, Any]]:
        """List benchmark runs filtered by task or suite."""
        limit = max(1, min(int(limit or 200), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        if str(task_id or "").strip():
            clauses.append("task_id = ?")
            params.append(str(task_id).strip())
        if str(benchmark_suite_id or "").strip():
            clauses.append("benchmark_suite_id = ?")
            params.append(str(benchmark_suite_id).strip())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM benchmark_runs
            {where_sql}
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["baseline_run_ids"] = parse_json_list(item.pop("baseline_run_ids", ""))
            item["candidate_run_ids"] = parse_json_list(item.pop("candidate_run_ids", ""))
            item["decision"] = parse_json(item.pop("decision_json", ""))
            item["details"] = parse_json(item.pop("details_json", ""))
            out.append(item)
        out.reverse()
        return sanitize_display_payload(out) if display_safe else out

    def list_benchmark_runs_by_suite(
        self,
        benchmark_suite_id: str,
        *,
        limit: int = 200,
        display_safe: bool = True,
    ) -> list[dict[str, Any]]:
        """Convenience wrapper for suite-scoped benchmark run queries."""
        return self.list_benchmark_runs(
            benchmark_suite_id=benchmark_suite_id,
            limit=limit,
            display_safe=display_safe,
        )

    def get_agent_task_report(self, report_id: int, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM agent_task_reports WHERE id = ?", (int(report_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"agent_task_report not found: {report_id}")
        item = dict(row)
        item["solved"] = bool(item.get("solved"))
        item["notify_chat"] = bool(item.get("notify_chat"))
        item["resolved_issues"] = split_text_list(item.get("resolved_issues"))
        item["resolution_steps"] = split_text_list(item.get("resolution_steps"))
        item["failed_items"] = split_text_list(item.get("failed_items"))
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def upsert_agent_task_report(
        self,
        *,
        task_id: str,
        agent_id: str,
        planner_id: str,
        status: str,
        solved: bool,
        resolved_issues: list[str] | str | tuple[str, ...] = (),
        resolution_summary: str = "",
        resolution_steps: list[str] | str | tuple[str, ...] = (),
        failed_items: list[str] | str | tuple[str, ...] = (),
        failure_count: int = 0,
        duration_ms: int = 0,
        model_id: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_estimate: float = 0.0,
        quality_score: float | None = None,
        quality_grade: str = "",
        notify_chat: bool = False,
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        if not self._task_exists(task_id):
            raise TaskCenterError(f"task not found: {task_id}")

        normalized_agent = str(agent_id or "").strip()
        normalized_planner = str(planner_id or "").strip()
        normalized_status = str(status or "").strip().lower()
        if not normalized_agent:
            raise TaskCenterError("agent_id cannot be empty")
        if not normalized_planner:
            raise TaskCenterError("planner_id cannot be empty")
        if normalized_status not in AGENT_REPORT_STATUSES:
            raise TaskCenterError(f"invalid agent report status: {normalized_status}")

        normalized_resolved_issues = normalize_text_list(resolved_issues)
        normalized_resolution_steps = normalize_text_list(resolution_steps)
        normalized_failed_items = normalize_text_list(failed_items)
        input_token_count = max(0, int(input_tokens or 0))
        output_token_count = max(0, int(output_tokens or 0))
        total_tokens = input_token_count + output_token_count
        duration = max(0, int(duration_ms or 0))
        fail_count = max(0, int(failure_count or 0))
        quality = float(quality_score) if quality_score is not None else None
        quality_level = str(quality_grade or "").strip().lower()
        ts = utc_now_iso()

        payload = {
            "task_id": task_id,
            "ts": ts,
            "agent_id": normalized_agent,
            "planner_id": normalized_planner,
            "status": normalized_status,
            "solved": 1 if solved else 0,
            "resolved_issues": normalized_resolved_issues,
            "resolution_summary": str(resolution_summary or "").strip(),
            "resolution_steps": normalized_resolution_steps,
            "failed_items": normalized_failed_items,
            "failure_count": fail_count,
            "duration_ms": duration,
            "model_id": str(model_id or "").strip(),
            "input_tokens": input_token_count,
            "output_tokens": output_token_count,
            "total_tokens": total_tokens,
            "cost_estimate": float(cost_estimate or 0.0),
            "quality_score": quality,
            "quality_grade": quality_level,
            "notify_chat": 1 if notify_chat else 0,
            "details_json": ensure_json(details),
        }

        def write_op() -> int:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO agent_task_reports (
                        task_id, ts, agent_id, planner_id, status, solved,
                        resolved_issues, resolution_summary, resolution_steps,
                        failed_items, failure_count, duration_ms, model_id,
                        input_tokens, output_tokens, total_tokens, cost_estimate,
                        quality_score, quality_grade, notify_chat, details_json
                    ) VALUES (
                        :task_id, :ts, :agent_id, :planner_id, :status, :solved,
                        :resolved_issues, :resolution_summary, :resolution_steps,
                        :failed_items, :failure_count, :duration_ms, :model_id,
                        :input_tokens, :output_tokens, :total_tokens, :cost_estimate,
                        :quality_score, :quality_grade, :notify_chat, :details_json
                    )
                    ON CONFLICT(task_id, agent_id, planner_id) DO UPDATE SET
                        ts = excluded.ts,
                        status = excluded.status,
                        solved = excluded.solved,
                        resolved_issues = excluded.resolved_issues,
                        resolution_summary = excluded.resolution_summary,
                        resolution_steps = excluded.resolution_steps,
                        failed_items = excluded.failed_items,
                        failure_count = excluded.failure_count,
                        duration_ms = excluded.duration_ms,
                        model_id = excluded.model_id,
                        input_tokens = excluded.input_tokens,
                        output_tokens = excluded.output_tokens,
                        total_tokens = excluded.total_tokens,
                        cost_estimate = excluded.cost_estimate,
                        quality_score = excluded.quality_score,
                        quality_grade = excluded.quality_grade,
                        notify_chat = excluded.notify_chat,
                        details_json = excluded.details_json
                    """,
                    payload,
                )

                report_row = self.conn.execute(
                    """
                    SELECT id
                    FROM agent_task_reports
                    WHERE task_id = ? AND agent_id = ? AND planner_id = ?
                    """,
                    (task_id, normalized_agent, normalized_planner),
                ).fetchone()
                if not report_row:
                    raise TaskCenterError("failed to locate upserted agent task report")
                report_id = int(report_row["id"])
                self.add_event(
                    task_id=task_id,
                    actor=(str(actor or "").strip() or normalized_agent),
                    event_type="agent_task_reported",
                    stage="report",
                    details={
                        "report_id": report_id,
                        "agent_id": normalized_agent,
                        "planner_id": normalized_planner,
                        "status": normalized_status,
                        "solved": bool(solved),
                        "failure_count": fail_count,
                        "duration_ms": duration,
                        "total_tokens": total_tokens,
                        "model_id": str(model_id or "").strip(),
                        "quality_score": quality,
                        "quality_grade": quality_level,
                        "notify_chat": bool(notify_chat),
                    },
                )
            return report_id

        report_id = int(self._run_write_with_retry(write_op))
        return self.get_agent_task_report(report_id)

    def list_agent_task_reports(
        self,
        *,
        task_id: str = "",
        planner_id: str = "",
        limit: int = 200,
        display_safe: bool = True,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        if str(task_id or "").strip():
            clauses.append("task_id = ?")
            params.append(str(task_id).strip())
        if str(planner_id or "").strip():
            clauses.append("planner_id = ?")
            params.append(str(planner_id).strip())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM agent_task_reports
            {where_sql}
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["solved"] = bool(item.get("solved"))
            item["notify_chat"] = bool(item.get("notify_chat"))
            item["resolved_issues"] = split_text_list(item.get("resolved_issues"))
            item["resolution_steps"] = split_text_list(item.get("resolution_steps"))
            item["failed_items"] = split_text_list(item.get("failed_items"))
            item["details"] = parse_json(item.pop("details_json", ""))
            out.append(item)
        return sanitize_display_payload(out) if display_safe else out

    def get_agent_points_record(self, record_id: int, display_safe: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM agent_points_ledger WHERE id = ?", (int(record_id),)).fetchone()
        if not row:
            raise TaskCenterError(f"agent_points_ledger not found: {record_id}")
        item = dict(row)
        item["solved"] = bool(item.get("solved"))
        item["details"] = parse_json(item.pop("details_json", ""))
        return sanitize_display_payload(item) if display_safe else item

    def upsert_agent_points(
        self,
        *,
        task_id: str,
        actor_type: str,
        actor_id: str,
        planner_id: str = "",
        status: str = "",
        solved: bool = False,
        points: float = 0.0,
        base_points: float = 0.0,
        quality_factor: float = 0.0,
        timeliness_factor: float = 0.0,
        details: dict[str, Any] | None = None,
        event_actor: str = "",
    ) -> dict[str, Any]:
        if not self._task_exists(task_id):
            raise TaskCenterError(f"task not found: {task_id}")

        actor_type_norm = str(actor_type or "").strip().lower()
        if actor_type_norm not in {"agent", "planner"}:
            raise TaskCenterError(f"invalid actor_type: {actor_type}")
        actor_id_norm = str(actor_id or "").strip()
        if not actor_id_norm:
            raise TaskCenterError("actor_id cannot be empty")
        planner_id_norm = str(planner_id or "").strip()
        status_norm = str(status or "").strip().lower()
        ts = utc_now_iso()
        payload = {
            "task_id": task_id,
            "ts": ts,
            "actor_type": actor_type_norm,
            "actor_id": actor_id_norm,
            "planner_id": planner_id_norm,
            "status": status_norm,
            "solved": 1 if solved else 0,
            "points": round(float(points or 0.0), 6),
            "base_points": round(float(base_points or 0.0), 6),
            "quality_factor": round(float(quality_factor or 0.0), 6),
            "timeliness_factor": round(float(timeliness_factor or 0.0), 6),
            "details_json": ensure_json(details),
        }

        def write_op() -> int:
            self.conn.execute(
                """
                INSERT INTO agent_points_ledger (
                    task_id, ts, actor_type, actor_id, planner_id, status, solved,
                    points, base_points, quality_factor, timeliness_factor, details_json
                ) VALUES (
                    :task_id, :ts, :actor_type, :actor_id, :planner_id, :status, :solved,
                    :points, :base_points, :quality_factor, :timeliness_factor, :details_json
                )
                ON CONFLICT(task_id, actor_type, actor_id, planner_id) DO UPDATE SET
                    ts = excluded.ts,
                    status = excluded.status,
                    solved = excluded.solved,
                    points = excluded.points,
                    base_points = excluded.base_points,
                    quality_factor = excluded.quality_factor,
                    timeliness_factor = excluded.timeliness_factor,
                    details_json = excluded.details_json
                """,
                payload,
            )
            row = self.conn.execute(
                """
                SELECT id
                FROM agent_points_ledger
                WHERE task_id = ? AND actor_type = ? AND actor_id = ? AND planner_id = ?
                """,
                (task_id, actor_type_norm, actor_id_norm, planner_id_norm),
            ).fetchone()
            if not row:
                raise TaskCenterError("failed to locate upserted agent points record")
            record_id = int(row["id"])
            self.add_event(
                task_id=task_id,
                actor=(str(event_actor or "").strip() or actor_id_norm),
                event_type="agent_points_recorded",
                stage="score",
                details={
                    "record_id": record_id,
                    "actor_type": actor_type_norm,
                    "actor_id": actor_id_norm,
                    "planner_id": planner_id_norm,
                    "status": status_norm,
                    "solved": bool(solved),
                    "points": payload["points"],
                    "base_points": payload["base_points"],
                    "quality_factor": payload["quality_factor"],
                    "timeliness_factor": payload["timeliness_factor"],
                },
            )
            return record_id

        record_id = int(self._run_transaction_with_retry(write_op))
        return self.get_agent_points_record(record_id)

    def list_agent_points(
        self,
        *,
        task_id: str = "",
        actor_type: str = "",
        actor_id: str = "",
        since: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 5000))
        clauses: list[str] = []
        params: list[Any] = []
        actor_type_norm = str(actor_type or "").strip().lower()
        if actor_type_norm:
            if actor_type_norm not in {"agent", "planner"}:
                raise TaskCenterError(f"invalid actor_type: {actor_type}")
            clauses.append("actor_type = ?")
            params.append(actor_type_norm)
        actor_id_norm = str(actor_id or "").strip()
        if actor_id_norm:
            clauses.append("actor_id = ?")
            params.append(actor_id_norm)
        task_id_norm = str(task_id or "").strip()
        if task_id_norm:
            clauses.append("task_id = ?")
            params.append(task_id_norm)
        since_norm = str(since or "").strip()
        if since_norm:
            parsed = parse_utc_iso(since_norm)
            if parsed is None:
                raise TaskCenterError(f"invalid since datetime: {since_norm}")
            clauses.append("ts >= ?")
            params.append(parsed.isoformat())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM agent_points_ledger
            {where_sql}
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["solved"] = bool(item.get("solved"))
            item["details"] = parse_json(item.pop("details_json", ""))
            out.append(item)
        return out

    def points_summary(
        self,
        *,
        actor_type: str = "agent",
        since: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        actor_type_norm = str(actor_type or "agent").strip().lower()
        if actor_type_norm not in {"agent", "planner"}:
            raise TaskCenterError(f"invalid actor_type: {actor_type}")
        since_norm = str(since or "").strip()
        params: list[Any] = [actor_type_norm]
        where_sql = "WHERE actor_type = ?"
        if since_norm:
            parsed = parse_utc_iso(since_norm)
            if parsed is None:
                raise TaskCenterError(f"invalid since datetime: {since_norm}")
            since_norm = parsed.isoformat()
            where_sql += " AND ts >= ?"
            params.append(since_norm)
        rows = self.conn.execute(
            f"""
            SELECT
                actor_id,
                COUNT(*) AS record_count,
                SUM(points) AS total_points,
                AVG(points) AS avg_points,
                SUM(CASE WHEN solved = 1 THEN 1 ELSE 0 END) AS solved_count
            FROM agent_points_ledger
            {where_sql}
            GROUP BY actor_id
            ORDER BY total_points DESC, solved_count DESC, actor_id ASC
            LIMIT ?
            """,
            [*params, max(1, min(int(limit or 200), 5000))],
        ).fetchall()
        leaders: list[dict[str, Any]] = []
        for row in rows:
            leaders.append(
                {
                    "actor_id": str(row["actor_id"]),
                    "record_count": int(row["record_count"] or 0),
                    "total_points": round(float(row["total_points"] or 0.0), 6),
                    "avg_points": round(float(row["avg_points"] or 0.0), 6),
                    "solved_count": int(row["solved_count"] or 0),
                }
            )
        return {
            "actor_type": actor_type_norm,
            "since": since_norm,
            "leaderboard": leaders,
            "actor_points": {item["actor_id"]: item["total_points"] for item in leaders},
        }

    def assign_task(self, task_id: str, assignee: str, actor: str) -> dict[str, Any]:
        assignee = assignee.strip()
        if not assignee:
            raise TaskCenterError("assignee cannot be empty")

        def write_op() -> None:
            self.conn.execute(
                "UPDATE tasks SET assignee = ?, updated_at = ? WHERE task_id = ?",
                (assignee, utc_now_iso(), task_id),
            )
            self.add_event(task_id, actor, "task_assigned", stage="assign", details={"assignee": assignee})

        self._run_transaction_with_retry(write_op)
        return self.get_task(task_id)

    def confirm_human(self, task_id: str, actor: str, confirmed: bool = True) -> dict[str, Any]:
        def write_op() -> None:
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

        self._run_transaction_with_retry(write_op)
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

        current = self.get_task(task_id, display_safe=False)
        current_status = str(current["status"])
        if allowed_from and current_status not in allowed_from:
            raise TaskCenterError(
                f"status transition blocked: {current_status} -> {normalized_status}, allowed: {sorted(allowed_from)}"
            )

        now_value = utc_now_iso()
        started_at = str(current.get("started_at", "") or "").strip()
        completed_at = str(current.get("completed_at", "") or "").strip()
        if normalized_status == "running" and not started_at:
            started_at = now_value
        if normalized_status in {"pending", "running"}:
            completed_at = ""
        elif normalized_status in {"passed", "failed", "escalated", "cancelled"}:
            completed_at = now_value

        def write_op() -> None:
            self.conn.execute(
                "UPDATE tasks SET status = ?, started_at = ?, completed_at = ?, updated_at = ? WHERE task_id = ?",
                (normalized_status, started_at, completed_at, now_value, task_id),
            )
            merged_details = {"from": current_status, "to": normalized_status}
            if details:
                merged_details.update(details)
            self.add_event(task_id, actor, "status_changed", stage=stage, details=merged_details)

        self._run_transaction_with_retry(write_op)
        return self.get_task(task_id)

    def increment_failure(
        self,
        task_id: str,
        actor: str,
        stage: str,
        max_failure_before_escalate: int,
        reason: str,
    ) -> dict[str, Any]:
        task = self.get_task(task_id, display_safe=False)
        next_failure = int(task["failure_count"]) + 1
        next_retry = int(task["retry_count"]) + 1

        if next_failure >= max_failure_before_escalate:
            next_status = "escalated"
            next_action = "escalate_human"
        else:
            next_status = "failed"
            next_action = "retry"

        now_value = utc_now_iso()
        completed_at = now_value if next_status in {"failed", "escalated"} else ""

        def write_op() -> None:
            self.conn.execute(
                """
                UPDATE tasks
                SET failure_count = ?, retry_count = ?, status = ?, action = ?, completed_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (next_failure, next_retry, next_status, next_action, completed_at, now_value, task_id),
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

        self._run_transaction_with_retry(write_op)
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
        def write_op() -> None:
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

        self._run_transaction_with_retry(write_op)
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
        context_fields_recommended_missing: list[str] | None = None,
    ) -> dict[str, Any]:
        current = self.get_task(task_id, display_safe=False)
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
        recommended_missing = (
            context_fields_recommended_missing
            if isinstance(context_fields_recommended_missing, list)
            else list(current.get("context_fields_recommended_missing") or [])
        )
        recommended_missing_text = normalize_context_missing_fields(recommended_missing)
        reason = str(clarification_reason or "").strip()
        if needs_clarification and not reason:
            reason = "context_incomplete"

        def write_op() -> None:
            self.conn.execute(
                """
                UPDATE tasks
                SET needs_clarification = ?,
                    clarification_reason = ?,
                    context_payload = ?,
                    context_completeness = ?,
                    context_fields_missing = ?,
                    context_fields_recommended_missing = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    1 if needs_clarification else 0,
                    reason,
                    ensure_json(payload),
                    completeness,
                    missing_text,
                    recommended_missing_text,
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
                    "context_fields_recommended_missing": [x for x in recommended_missing_text.split(",") if x],
                },
            )

        self._run_transaction_with_retry(write_op)
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
        summary: dict[str, Any] = {}

        def write_op() -> dict[str, Any]:
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
            current_summary = self.task_token_summary(task_id)
            self.conn.execute(
                """
                UPDATE tasks
                SET token_usage_summary = ?, cost_estimate_total = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    ensure_json(current_summary),
                    float(current_summary.get("cost_estimate", 0.0)),
                    utc_now_iso(),
                    task_id,
                ),
            )
            return current_summary

        summary = self._run_transaction_with_retry(write_op)

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

    def list_task_events(self, task_id: str, limit: int = 200, display_safe: bool = True) -> list[dict[str, Any]]:
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
        return sanitize_display_payload(out) if display_safe else out

    def task_timing_summary(self, task: dict[str, Any]) -> dict[str, Any]:
        created_text = str(task.get("created_at", "") or "").strip()
        started_text = str(task.get("started_at", "") or "").strip()
        completed_text = str(task.get("completed_at", "") or "").strip()
        created_dt = parse_utc_iso(created_text)
        started_dt = parse_utc_iso(started_text)
        completed_dt = parse_utc_iso(completed_text)
        now_dt = datetime.now(tz=UTC).replace(microsecond=0)

        age_ms: int | None = None
        if created_dt is not None:
            age_ms = max(0, int((now_dt - created_dt).total_seconds() * 1000))

        elapsed_ms: int | None = None
        if created_dt is not None and completed_dt is not None:
            elapsed_ms = max(0, int((completed_dt - created_dt).total_seconds() * 1000))

        execution_ms: int | None = None
        if started_dt is not None and completed_dt is not None:
            execution_ms = max(0, int((completed_dt - started_dt).total_seconds() * 1000))

        return {
            "created_at": created_text,
            "started_at": started_text,
            "completed_at": completed_text,
            "is_completed": bool(completed_text),
            "age_ms": age_ms,
            "age_min": round((age_ms / 60000.0), 2) if age_ms is not None else None,
            "elapsed_ms": elapsed_ms,
            "elapsed_min": round((elapsed_ms / 60000.0), 2) if elapsed_ms is not None else None,
            "execution_ms": execution_ms,
            "execution_min": round((execution_ms / 60000.0), 2) if execution_ms is not None else None,
        }

    def task_points_summary(self, task_id: str, display_safe: bool = True) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM agent_points_ledger
            WHERE task_id = ?
            ORDER BY points DESC, ts DESC, id DESC
            """,
            (task_id,),
        ).fetchall()
        records: list[dict[str, Any]] = []
        by_actor: dict[str, float] = {}
        by_actor_type: dict[str, float] = {"agent": 0.0, "planner": 0.0}
        for row in rows:
            item = dict(row)
            item["solved"] = bool(item.get("solved"))
            item["details"] = parse_json(item.pop("details_json", ""))
            records.append(item)
            key = f"{item.get('actor_type', '')}:{item.get('actor_id', '')}"
            by_actor[key] = round(by_actor.get(key, 0.0) + float(item.get("points") or 0.0), 6)
            actor_type = str(item.get("actor_type", "")).strip().lower()
            if actor_type in by_actor_type:
                by_actor_type[actor_type] = round(
                    by_actor_type.get(actor_type, 0.0) + float(item.get("points") or 0.0), 6
                )

        ranked_agent_rows = sorted(
            (
                {
                    "actor_id": str(key.split(":", 1)[1]),
                    "points": points,
                }
                for key, points in by_actor.items()
                if key.startswith("agent:")
            ),
            key=lambda item: item["points"],
            reverse=True,
        )
        top_agent = ranked_agent_rows[0] if ranked_agent_rows else None
        summary = {
            "record_count": len(records),
            "total_points": round(sum(float(item.get("points") or 0.0) for item in records), 6),
            "by_actor_type": by_actor_type,
            "by_actor": by_actor,
            "top_agent": top_agent,
            "records": records,
        }
        return sanitize_display_payload(summary) if display_safe else summary

    def task_report(self, task_id: str, event_limit: int = 200, display_safe: bool = True) -> dict[str, Any]:
        task = self.get_task(task_id, display_safe=False)
        token_usage = self.task_token_summary(task_id)
        timing = self.task_timing_summary(task)
        points = self.task_points_summary(task_id, display_safe=False)
        stage_runs = self.list_stage_runs(task_id, display_safe=False)
        task_outputs = self.list_task_outputs(task_id, limit=min(max(20, event_limit), 500), display_safe=False)
        task_incidents = self.list_task_incidents(task_id, limit=min(max(20, event_limit), 500), display_safe=False)
        benchmark_runs = self.list_benchmark_runs(task_id, limit=min(max(20, event_limit), 500), display_safe=False)
        module_logs = self.list_module_logs(task_id, limit=min(max(50, event_limit), 1000), display_safe=False)
        communications = self.list_module_communications(
            task_id,
            limit=min(max(50, event_limit), 1000),
            display_safe=False,
        )
        agent_reports = self.list_agent_task_reports(
            task_id=task_id,
            limit=min(max(50, event_limit), 1000),
            display_safe=False,
        )
        report_input_tokens = sum(int(row.get("input_tokens") or 0) for row in agent_reports)
        report_output_tokens = sum(int(row.get("output_tokens") or 0) for row in agent_reports)
        report_total_tokens = report_input_tokens + report_output_tokens
        report_cost = round(sum(float(row.get("cost_estimate") or 0.0) for row in agent_reports), 6)
        report_token_usage = {
            "input_tokens": report_input_tokens,
            "output_tokens": report_output_tokens,
            "total_tokens": report_total_tokens,
            "total_tokens_m": round(report_total_tokens / 1_000_000.0, 6),
            "cost_estimate": report_cost,
        }
        effective_token_usage = token_usage if int(token_usage.get("total_tokens") or 0) > 0 else report_token_usage
        module_failures = [
            row
            for row in module_logs
            if str(row.get("level", "")).lower() in {"error"}
            or str(row.get("status", "")).lower() in {"failed", "timeout"}
        ]
        communication_failures = [
            row for row in communications if str(row.get("status", "")).lower() in {"failed", "timeout"}
        ]
        stage_failures = [row for row in stage_runs if str(row.get("status", "")).lower() in {"failed"}]
        open_incidents = [
            row
            for row in task_incidents
            if str(row.get("status", "")).strip().lower() not in {"resolved", "suppressed"}
        ]
        critical_open_incidents = [
            row for row in open_incidents if str(row.get("severity", "")).strip().lower() == "critical"
        ]
        latest_output = task_outputs[-1] if task_outputs else {}
        latest_incident = task_incidents[-1] if task_incidents else {}
        latest_benchmark_run = benchmark_runs[-1] if benchmark_runs else {}
        latest_human_gate = latest_output.get("payload", {}).get("human_gate", {}) if isinstance(latest_output, dict) else {}
        if not isinstance(latest_human_gate, dict):
            latest_human_gate = {}
        execution_envelope = self._build_execution_envelope_snapshot(task)
        report = {
            "trace_id": str(task.get("trace_id", "")).strip(),
            "attempt_id": str(task.get("attempt_id", "")).strip(),
            "execution_envelope": execution_envelope,
            "task": task,
            "timing": timing,
            "token_usage": token_usage,
            "token_usage_from_agent_reports": report_token_usage,
            "token_usage_effective": effective_token_usage,
            "agent_points": points,
            "stage_runs": stage_runs,
            "task_outputs": task_outputs,
            "task_incidents": task_incidents,
            "benchmark_runs": benchmark_runs,
            "module_logs": module_logs,
            "module_communications": communications,
            "agent_reports": agent_reports,
            "events": self.list_task_events(task_id, limit=event_limit, display_safe=False),
            "control_plane": {
                "latest_output": latest_output,
                "latest_incident": latest_incident,
                "latest_benchmark_run": latest_benchmark_run,
                "open_incidents": open_incidents[:20],
                "open_incident_count": len(open_incidents),
                "critical_open_incident_count": len(critical_open_incidents),
                "requires_human_assistance": bool(latest_human_gate.get("requires_human_assistance", False)),
                "waiting_human_confirm": bool(latest_human_gate.get("need_human_confirm", False))
                and not bool(latest_human_gate.get("human_confirmed", False)),
                "needs_clarification": bool(latest_human_gate.get("needs_clarification", False)),
                "benchmark_suite_ids": sorted(
                    {
                        str(item.get("benchmark_suite_id", "")).strip()
                        for item in benchmark_runs
                        if str(item.get("benchmark_suite_id", "")).strip()
                    }
                ),
            },
            "diagnostics": {
                "module_failure_count": len(module_failures),
                "communication_failure_count": len(communication_failures),
                "flow_failure_count": len(stage_failures),
                "task_output_count": len(task_outputs),
                "incident_count": len(task_incidents),
                "open_incident_count": len(open_incidents),
                "critical_open_incident_count": len(critical_open_incidents),
                "benchmark_run_count": len(benchmark_runs),
                "module_failures": module_failures[:20],
                "communication_failures": communication_failures[:20],
                "flow_failures": stage_failures[:20],
            },
        }
        return sanitize_display_payload(report) if display_safe else report

    def unresolved_tasks(self, display_safe: bool = True) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE status IN ('pending', 'running', 'failed')
            ORDER BY
                CASE
                    WHEN scheduled_at IS NULL OR TRIM(scheduled_at) = '' OR scheduled_at <= ? THEN 0
                    ELSE 1
                END ASC,
                COALESCE(NULLIF(TRIM(scheduled_at), ''), created_at) ASC,
                created_at ASC
            """,
            (utc_now_iso(),),
        ).fetchall()
        tasks = [self._deserialize_task_row(row) for row in rows]
        return sanitize_display_payload(tasks) if display_safe else tasks

    def recent_control_plane_task_ids(
        self,
        *,
        since: str = "",
        limit: int = 50,
        display_safe: bool = True,
    ) -> list[dict[str, Any]]:
        """Return recent task ids that had control-plane activity since the given UTC timestamp.

        Args:
            since: UTC ISO timestamp. Empty means "now - 24 hours".
            limit: Max number of task ids to return. Must be >= 1.
            display_safe: When true, sanitize the returned payload for human display.

        Returns:
            A list of dicts containing `task_id`, `latest_ts`, and `sources`.

        Raises:
            TaskCenterError: If `since` is not a valid UTC ISO timestamp.
        """

        normalized_since = str(since or "").strip()
        if normalized_since:
            parsed_since = parse_utc_iso(normalized_since)
            if parsed_since is None:
                raise TaskCenterError(f"invalid since datetime: {normalized_since}")
            normalized_since = parsed_since.isoformat()
        else:
            normalized_since = (datetime.now(tz=UTC) - timedelta(hours=24)).replace(microsecond=0).isoformat()

        normalized_limit = max(1, min(int(limit or 50), 1000))
        rows = self.conn.execute(
            """
            WITH recent_control_plane AS (
                SELECT task_id, updated_at AS ts, 'task' AS source
                FROM tasks
                WHERE updated_at >= ?
                UNION ALL
                SELECT task_id, ts, 'output' AS source
                FROM task_outputs
                WHERE ts >= ?
                UNION ALL
                SELECT task_id, ts, 'incident' AS source
                FROM task_incidents
                WHERE ts >= ?
                UNION ALL
                SELECT task_id, ts, 'benchmark' AS source
                FROM benchmark_runs
                WHERE task_id IS NOT NULL AND TRIM(task_id) != '' AND ts >= ?
            )
            SELECT
                task_id,
                MAX(ts) AS latest_ts,
                GROUP_CONCAT(DISTINCT source) AS sources
            FROM recent_control_plane
            GROUP BY task_id
            ORDER BY latest_ts DESC, task_id DESC
            LIMIT ?
            """,
            (normalized_since, normalized_since, normalized_since, normalized_since, normalized_limit),
        ).fetchall()
        out = [
            {
                "task_id": str(row["task_id"]).strip(),
                "latest_ts": str(row["latest_ts"]).strip(),
                "sources": [item.strip() for item in str(row["sources"] or "").split(",") if item.strip()],
            }
            for row in rows
            if str(row["task_id"] or "").strip()
        ]
        return sanitize_display_payload(out) if display_safe else out

    def planner_summary(
        self,
        *,
        planner_id: str,
        since: str = "",
        limit: int = 100,
        display_safe: bool = True,
    ) -> dict[str, Any]:
        normalized_planner = str(planner_id or "").strip()
        if not normalized_planner:
            raise TaskCenterError("planner_id cannot be empty")

        normalized_since = str(since or "").strip()
        if normalized_since:
            parsed_since = parse_utc_iso(normalized_since)
            if parsed_since is None:
                raise TaskCenterError(f"invalid since datetime: {normalized_since}")
            normalized_since = parsed_since.isoformat()

        normalized_limit = max(1, min(int(limit or 100), 1000))
        filters = ["planner_id = ?"]
        params: list[Any] = [normalized_planner]
        if normalized_since:
            filters.append("ts >= ?")
            params.append(normalized_since)
        where_sql = " AND ".join(filters)

        report_rows = self.conn.execute(
            f"""
            SELECT *
            FROM agent_task_reports
            WHERE {where_sql}
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            [*params, normalized_limit],
        ).fetchall()

        reports: list[dict[str, Any]] = []
        by_status: dict[str, int] = {}
        total_tokens = 0
        total_cost = 0.0
        total_duration_ms = 0
        solved_count = 0
        quality_sum = 0.0
        quality_cnt = 0
        unique_tasks: set[str] = set()
        resolved_tasks: set[str] = set()
        failed_tasks: set[str] = set()

        for row in report_rows:
            item = dict(row)
            status = str(item.get("status", "")).lower()
            solved = bool(item.get("solved"))
            by_status[status] = by_status.get(status, 0) + 1
            if solved:
                solved_count += 1
            task_id = str(item.get("task_id", "")).strip()
            if task_id:
                unique_tasks.add(task_id)
                if solved and status in {"passed", "partial"}:
                    resolved_tasks.add(task_id)
                if (not solved) or status in {"failed", "escalated"}:
                    failed_tasks.add(task_id)
            total_tokens += int(item.get("total_tokens") or 0)
            total_cost += float(item.get("cost_estimate") or 0.0)
            total_duration_ms += int(item.get("duration_ms") or 0)
            q_score = item.get("quality_score")
            if q_score is not None:
                try:
                    quality_sum += float(q_score)
                    quality_cnt += 1
                except (TypeError, ValueError):
                    pass

            item["solved"] = solved
            item["notify_chat"] = bool(item.get("notify_chat"))
            item["resolved_issues"] = split_text_list(item.get("resolved_issues"))
            item["resolution_steps"] = split_text_list(item.get("resolution_steps"))
            item["failed_items"] = split_text_list(item.get("failed_items"))
            item["details"] = parse_json(item.pop("details_json", ""))
            reports.append(item)

        by_agent_rows = self.conn.execute(
            f"""
            SELECT
                agent_id,
                COUNT(*) AS report_count,
                SUM(CASE WHEN solved = 1 THEN 1 ELSE 0 END) AS solved_count,
                SUM(CASE WHEN solved = 0 OR status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS failed_count,
                SUM(total_tokens) AS total_tokens,
                SUM(cost_estimate) AS total_cost,
                SUM(duration_ms) AS total_duration_ms,
                AVG(quality_score) AS avg_quality_score
            FROM agent_task_reports
            WHERE {where_sql}
            GROUP BY agent_id
            ORDER BY report_count DESC, total_tokens DESC
            """,
            params,
        ).fetchall()
        by_agent = []
        for row in by_agent_rows:
            by_agent.append(
                {
                    "agent_id": str(row["agent_id"]),
                    "report_count": int(row["report_count"] or 0),
                    "solved_count": int(row["solved_count"] or 0),
                    "failed_count": int(row["failed_count"] or 0),
                    "total_tokens": int(row["total_tokens"] or 0),
                    "total_tokens_m": round(int(row["total_tokens"] or 0) / 1_000_000.0, 6),
                    "cost_estimate": round(float(row["total_cost"] or 0.0), 6),
                    "total_duration_ms": int(row["total_duration_ms"] or 0),
                    "avg_quality_score": (
                        round(float(row["avg_quality_score"]), 4) if row["avg_quality_score"] is not None else None
                    ),
                }
            )

        summary = {
            "planner_id": normalized_planner,
            "since": normalized_since,
            "report_count": len(reports),
            "task_count": len(unique_tasks),
            "resolved_task_count": len(resolved_tasks),
            "failed_task_count": len(failed_tasks),
            "solved_count": solved_count,
            "solved_ratio_pct": round((solved_count / len(reports)) * 100.0, 2) if reports else 0.0,
            "status_counts": by_status,
            "total_tokens": total_tokens,
            "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
            "total_cost_estimate": round(total_cost, 6),
            "total_duration_ms": total_duration_ms,
            "avg_duration_ms": round(total_duration_ms / len(reports), 2) if reports else 0.0,
            "avg_quality_score": round(quality_sum / quality_cnt, 4) if quality_cnt > 0 else None,
            "by_agent": by_agent,
            "reports": reports,
        }
        return sanitize_display_payload(summary) if display_safe else summary

    def task_capability_coverage(
        self,
        *,
        since: str = "",
        task_type: str = "",
        assignee: str = "",
        status: str = "",
        pool: str = "",
        display_safe: bool = True,
    ) -> dict[str, Any]:
        normalized_since = str(since or "").strip()
        if normalized_since:
            parsed_since = parse_utc_iso(normalized_since)
            if parsed_since is None:
                raise TaskCenterError(f"invalid since datetime: {normalized_since}")
            normalized_since = parsed_since.isoformat()

        normalized_task_type = str(task_type or "").strip()
        normalized_assignee = str(assignee or "").strip()
        normalized_status = str(status or "").strip()
        normalized_pool = str(pool or "").strip()
        filters = ["1 = 1"]
        params: list[Any] = []
        if normalized_since:
            filters.append("created_at >= ?")
            params.append(normalized_since)
        if normalized_task_type:
            filters.append("task_type = ?")
            params.append(normalized_task_type)
        if normalized_assignee:
            filters.append("assignee = ?")
            params.append(normalized_assignee)
        if normalized_status:
            filters.append("status = ?")
            params.append(normalized_status)
        if normalized_pool:
            filters.append("pool = ?")
            params.append(normalized_pool)
        where_sql = " AND ".join(filters)

        overview = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_tasks,
                SUM(
                    CASE
                        WHEN TRIM(required_capabilities) != ''
                          OR TRIM(required_skills) != ''
                          OR TRIM(allowed_agents) != ''
                        THEN 1 ELSE 0
                    END
                ) AS upgraded_tasks,
                SUM(CASE WHEN TRIM(required_capabilities) != '' THEN 1 ELSE 0 END) AS with_required_capabilities,
                SUM(CASE WHEN TRIM(required_skills) != '' THEN 1 ELSE 0 END) AS with_required_skills,
                SUM(CASE WHEN TRIM(allowed_agents) != '' THEN 1 ELSE 0 END) AS with_allowed_agents
            FROM tasks
            WHERE {where_sql}
            """,
            params,
        ).fetchone()

        by_task_type_rows = self.conn.execute(
            f"""
            SELECT
                task_type,
                COUNT(*) AS total_tasks,
                SUM(
                    CASE
                        WHEN TRIM(required_capabilities) != ''
                          OR TRIM(required_skills) != ''
                          OR TRIM(allowed_agents) != ''
                        THEN 1 ELSE 0
                    END
                ) AS upgraded_tasks
            FROM tasks
            WHERE {where_sql}
            GROUP BY task_type
            ORDER BY total_tasks DESC, task_type ASC
            """,
            params,
        ).fetchall()

        total_tasks = int((overview["total_tasks"] if overview else 0) or 0)
        upgraded_tasks = int((overview["upgraded_tasks"] if overview else 0) or 0)
        summary = {
            "since": normalized_since,
            "task_type_filter": normalized_task_type,
            "assignee_filter": normalized_assignee,
            "status_filter": normalized_status,
            "pool_filter": normalized_pool,
            "total_tasks": total_tasks,
            "upgraded_tasks": upgraded_tasks,
            "upgrade_ratio_pct": round((upgraded_tasks / total_tasks) * 100.0, 2) if total_tasks else 0.0,
            "with_required_capabilities": int((overview["with_required_capabilities"] if overview else 0) or 0),
            "with_required_skills": int((overview["with_required_skills"] if overview else 0) or 0),
            "with_allowed_agents": int((overview["with_allowed_agents"] if overview else 0) or 0),
            "by_task_type": [
                {
                    "task_type": str(row["task_type"] or ""),
                    "total_tasks": int(row["total_tasks"] or 0),
                    "upgraded_tasks": int(row["upgraded_tasks"] or 0),
                    "upgrade_ratio_pct": (
                        round((int(row["upgraded_tasks"] or 0) / int(row["total_tasks"] or 0)) * 100.0, 2)
                        if int(row["total_tasks"] or 0)
                        else 0.0
                    ),
                }
                for row in by_task_type_rows
            ],
        }
        return sanitize_display_payload(summary) if display_safe else summary

    def daily_summary(self, target_date: date, display_safe: bool = True) -> dict[str, Any]:
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

        report_token_rows = self.conn.execute(
            """
            SELECT
              agent_id,
              SUM(input_tokens) AS input_tokens,
              SUM(output_tokens) AS output_tokens,
              SUM(total_tokens) AS total_tokens,
              SUM(cost_estimate) AS cost_estimate
            FROM agent_task_reports
            WHERE ts >= ? AND ts < ?
            GROUP BY agent_id
            ORDER BY total_tokens DESC
            """,
            (tr.start, tr.end),
        ).fetchall()
        report_by_agent: list[dict[str, Any]] = []
        report_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0}
        for row in report_token_rows:
            input_tokens = int(row["input_tokens"] or 0)
            output_tokens = int(row["output_tokens"] or 0)
            total_tokens = int(row["total_tokens"] or 0)
            cost_estimate = float(row["cost_estimate"] or 0.0)
            report_by_agent.append(
                {
                    "agent_id": str(row["agent_id"]),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
                    "cost_estimate": round(cost_estimate, 6),
                }
            )
            report_totals["input_tokens"] += input_tokens
            report_totals["output_tokens"] += output_tokens
            report_totals["total_tokens"] += total_tokens
            report_totals["cost_estimate"] += cost_estimate

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

        module_log_rows = self.conn.execute(
            """
            SELECT
              module_name,
              level,
              status,
              COUNT(*) AS cnt
            FROM module_logs
            WHERE ts >= ? AND ts < ?
            GROUP BY module_name, level, status
            ORDER BY cnt DESC, module_name
            """,
            (tr.start, tr.end),
        ).fetchall()
        module_log_metrics: list[dict[str, Any]] = []
        module_failure_count = 0
        for row in module_log_rows:
            level = str(row["level"])
            status = str(row["status"])
            cnt = int(row["cnt"] or 0)
            if level == "error" or status in {"failed", "timeout"}:
                module_failure_count += cnt
            module_log_metrics.append(
                {
                    "module_name": str(row["module_name"]),
                    "level": level,
                    "status": status,
                    "count": cnt,
                }
            )

        communication_rows = self.conn.execute(
            """
            SELECT
              from_module,
              to_module,
              status,
              COUNT(*) AS cnt
            FROM module_communications
            WHERE ts >= ? AND ts < ?
            GROUP BY from_module, to_module, status
            ORDER BY cnt DESC, from_module, to_module
            """,
            (tr.start, tr.end),
        ).fetchall()
        communication_metrics: list[dict[str, Any]] = []
        communication_failure_count = 0
        for row in communication_rows:
            status = str(row["status"])
            cnt = int(row["cnt"] or 0)
            if status in {"failed", "timeout"}:
                communication_failure_count += cnt
            communication_metrics.append(
                {
                    "from_module": str(row["from_module"]),
                    "to_module": str(row["to_module"]),
                    "status": status,
                    "count": cnt,
                }
            )

        agent_report_rows = self.conn.execute(
            """
            SELECT
              planner_id,
              agent_id,
              status,
              COUNT(*) AS report_count,
              SUM(total_tokens) AS total_tokens,
              SUM(cost_estimate) AS total_cost,
              AVG(quality_score) AS avg_quality_score
            FROM agent_task_reports
            WHERE ts >= ? AND ts < ?
            GROUP BY planner_id, agent_id, status
            ORDER BY report_count DESC, planner_id, agent_id
            """,
            (tr.start, tr.end),
        ).fetchall()
        agent_report_metrics: list[dict[str, Any]] = []
        for row in agent_report_rows:
            agent_report_metrics.append(
                {
                    "planner_id": str(row["planner_id"]),
                    "agent_id": str(row["agent_id"]),
                    "status": str(row["status"]),
                    "report_count": int(row["report_count"] or 0),
                    "total_tokens": int(row["total_tokens"] or 0),
                    "cost_estimate": round(float(row["total_cost"] or 0.0), 6),
                    "avg_quality_score": (
                        round(float(row["avg_quality_score"]), 4) if row["avg_quality_score"] is not None else None
                    ),
                }
            )

        points_rows = self.conn.execute(
            """
            SELECT
              actor_type,
              actor_id,
              COUNT(*) AS record_count,
              SUM(points) AS total_points,
              AVG(points) AS avg_points,
              SUM(CASE WHEN solved = 1 THEN 1 ELSE 0 END) AS solved_count
            FROM agent_points_ledger
            WHERE ts >= ? AND ts < ?
            GROUP BY actor_type, actor_id
            ORDER BY total_points DESC, solved_count DESC, actor_type, actor_id
            """,
            (tr.start, tr.end),
        ).fetchall()
        agent_points: list[dict[str, Any]] = []
        for row in points_rows:
            agent_points.append(
                {
                    "actor_type": str(row["actor_type"]),
                    "actor_id": str(row["actor_id"]),
                    "record_count": int(row["record_count"] or 0),
                    "solved_count": int(row["solved_count"] or 0),
                    "total_points": round(float(row["total_points"] or 0.0), 6),
                    "avg_points": round(float(row["avg_points"] or 0.0), 6),
                }
            )

        summary = {
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
            "token_usage_from_agent_reports": {
                "totals": {
                    "input_tokens": report_totals["input_tokens"],
                    "output_tokens": report_totals["output_tokens"],
                    "total_tokens": report_totals["total_tokens"],
                    "total_tokens_m": round(report_totals["total_tokens"] / 1_000_000.0, 6),
                    "cost_estimate": round(report_totals["cost_estimate"], 6),
                },
                "by_agent": report_by_agent,
            },
            "token_usage_effective": {
                "source": "token_usage" if totals["total_tokens"] > 0 else "agent_task_reports",
                "totals": {
                    "input_tokens": totals["input_tokens"] if totals["total_tokens"] > 0 else report_totals["input_tokens"],
                    "output_tokens": (
                        totals["output_tokens"] if totals["total_tokens"] > 0 else report_totals["output_tokens"]
                    ),
                    "total_tokens": totals["total_tokens"] if totals["total_tokens"] > 0 else report_totals["total_tokens"],
                    "total_tokens_m": round(
                        (totals["total_tokens"] if totals["total_tokens"] > 0 else report_totals["total_tokens"])
                        / 1_000_000.0,
                        6,
                    ),
                    "cost_estimate": round(
                        totals["cost_estimate"] if totals["total_tokens"] > 0 else report_totals["cost_estimate"],
                        6,
                    ),
                },
            },
            "stage_metrics": stage_metrics,
            "module_observability": {
                "failure_count": module_failure_count,
                "rows": module_log_metrics,
            },
            "communication_observability": {
                "failure_count": communication_failure_count,
                "rows": communication_metrics,
            },
            "agent_report_metrics": agent_report_metrics,
            "agent_points": agent_points,
            "escalated": escalated,
            "escalated_count": escalated_count,
            "failure_over_limit": failure_over_limit,
            "unresolved_count": len(self.unresolved_tasks(display_safe=False)),
        }
        return sanitize_display_payload(summary) if display_safe else summary


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

    effective_usage = summary.get("token_usage_effective", {})
    effective_totals = effective_usage.get("totals", {})
    lines.append("## Token Usage Effective")
    lines.append(f"- source: {effective_usage.get('source', 'token_usage')}")
    lines.append(f"- total_tokens: {effective_totals.get('total_tokens', 0)}")
    lines.append(f"- total_tokens_m: {effective_totals.get('total_tokens_m', 0)}")
    lines.append(f"- cost_estimate: {effective_totals.get('cost_estimate', 0)}")
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

    module_observability = summary.get("module_observability", {})
    module_rows = module_observability.get("rows", [])
    lines.append("## Module Observability")
    lines.append(f"- module_failure_count: {module_observability.get('failure_count', 0)}")
    if module_rows:
        for item in module_rows[:20]:
            lines.append(
                "- "
                + f"{item.get('module_name', '-')}/{item.get('level', '-')}/{item.get('status', '-')}: "
                + f"count={item.get('count', 0)}"
            )
    else:
        lines.append("- no module logs")
    lines.append("")

    communication_observability = summary.get("communication_observability", {})
    communication_rows = communication_observability.get("rows", [])
    lines.append("## Communication Observability")
    lines.append(f"- communication_failure_count: {communication_observability.get('failure_count', 0)}")
    if communication_rows:
        for item in communication_rows[:20]:
            lines.append(
                "- "
                + f"{item.get('from_module', '-')}>{item.get('to_module', '-')}/{item.get('status', '-')}: "
                + f"count={item.get('count', 0)}"
            )
    else:
        lines.append("- no communication logs")
    lines.append("")

    agent_report_metrics = summary.get("agent_report_metrics", [])
    lines.append("## Agent Reports")
    if agent_report_metrics:
        for item in agent_report_metrics[:20]:
            lines.append(
                "- "
                + f"planner={item.get('planner_id', '-')}, agent={item.get('agent_id', '-')}, "
                + f"status={item.get('status', '-')}, count={item.get('report_count', 0)}, "
                + f"tokens={item.get('total_tokens', 0)}, cost={item.get('cost_estimate', 0)}, "
                + f"avg_quality={item.get('avg_quality_score', 'n/a')}"
            )
    else:
        lines.append("- no agent reports")
    lines.append("")

    agent_points = summary.get("agent_points", [])
    lines.append("## Agent Points")
    if agent_points:
        for item in agent_points[:30]:
            lines.append(
                "- "
                + f"{item.get('actor_type', '-')}/{item.get('actor_id', '-')}: "
                + f"total_points={item.get('total_points', 0)}, avg_points={item.get('avg_points', 0)}, "
                + f"solved_count={item.get('solved_count', 0)}, records={item.get('record_count', 0)}"
            )
    else:
        lines.append("- no points records")
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

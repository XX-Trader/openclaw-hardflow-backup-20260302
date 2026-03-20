#!/usr/bin/env python3
"""Unified OpenClaw ops cron runner with hard constraints.

Modes:
- incremental: read log increments with checkpoints and issue lifecycle tracking.
- full: run full-tail calibration scan to recover from incremental drift.
- daily: aggregate 24h run history and output daily summary.

Output contract:
- Print `NO_REPLY` when no major change should be announced.
- Otherwise print a concise markdown report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sqlite3
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from utf8_runtime import configure_process_utf8_stdio
from io_write_gateway import FileWriteError, append_text_atomic, write_json_atomic
from alert_dedupe import (
    WORKFLOW_FAILURE_BUCKET,
    build_workflow_failure_signature,
    check_and_record_signature,
    load_dedupe_state,
    resolve_shared_alert_state_path,
    save_dedupe_state,
    workflow_tokens_from_job_ids,
)
from task_capability_binding import extend_create_task_args_with_constraints
from workflow_views import build_follow_up_progress_lines, build_ops_scan_event, render_human_view

configure_process_utf8_stdio()

TZ = timezone(timedelta(hours=8))
UTC = timezone.utc
ERROR_KEYWORDS = (
    "error",
    "exception",
    "fatal",
    "panic",
    "traceback",
    "failed",
    "timeout",
    "\u9519\u8bef",
    "\u5f02\u5e38",
    "\u5931\u8d25",
    "\u8d85\u65f6",
    "\u544a\u8b66",
)
HIGH_KEYWORDS = ("fatal", "panic", "segfault", "oom", "critical", "database", "data_loss", "corruption")
VOLATILE_PATTERNS = (
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b",
    r"\b0x[0-9a-fA-F]+\b",
    r"\b[0-9a-fA-F]{10,}\b",
    r"\b\d{5,}\b",
)
DEFAULT_SENDER_PREFIX = "ops-agent/ops-cron-runner"
DEFAULT_WORKFLOW_MONITOR_IGNORED_JOB_NAMES = {
    "todo_patrol_15m",
    "project_index_maintainer_30m",
    "ops_conversation_evolution_incremental",
    "ops_governance_evolution_incremental",
    "ops_github_web_evolution_incremental",
    "ops_git_sync_push",
    "ops_auto_update_install_hourly",
    "task_retry_10m",
    "web_intel_collect_hourly",
    "web_intel_review_optimization_4h",
    "web_intel_review_project_docs_6h",
}


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    if mode in {"silent", "chat"}:
        return mode
    return default


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def compact_reason(reason: str) -> str:
    text = str(reason or "").strip()
    if "=" in text:
        return text.split("=", 1)[0].strip()
    return text


def humanize_risk_reason(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "\u672a\u77e5\u98ce\u9669"
    head, sep, tail = text.partition("=")
    num = tail if sep else ""
    mapping = {
        "new_high_issue": "\u51fa\u73b0\u65b0\u7684\u9ad8\u98ce\u9669\u95ee\u9898",
        "reopened_high_issue": "\u9ad8\u98ce\u9669\u95ee\u9898\u518d\u6b21\u51fa\u73b0",
        "scan_error": "\u65e5\u5fd7\u626b\u63cf\u5931\u8d25",
        "system_anomaly": "\u7cfb\u7edf\u6307\u6807\u5f02\u5e38",
        "service_monitor_error": "\u8fdb\u7a0b\u6216\u670d\u52a1\u76d1\u63a7\u5f02\u5e38",
        "runtime_process_missing": "\u9879\u76ee\u5e38\u9a7b\u8fdb\u7a0b\u6216\u670d\u52a1\u7f3a\u5931",
        "runtime_monitor_error": "\u9879\u76ee\u8fd0\u884c\u6001\u76d1\u63a7\u5f02\u5e38",
        "workflow_job_error": "\u5de5\u4f5c\u6d41\u4efb\u52a1\u5931\u8d25",
        "workflow_job_error_stale": "\u5de5\u4f5c\u6d41\u4efb\u52a1\u6301\u7eed\u5931\u8d25\uff08\u8d85\u65f6\u672a\u6062\u590d\uff09",
        "workflow_monitor_error": "\u5de5\u4f5c\u6d41\u76d1\u63a7\u6a21\u5757\u5f02\u5e38",
        "token_monitor_error": "Token \u7edf\u8ba1\u6a21\u5757\u5f02\u5e38",
        "app_usage_monitor_error": "\u7a7a\u95f4\u7edf\u8ba1\u6a21\u5757\u5f02\u5e38",
        "handoff_error": "\u544a\u8b66\u4ea4\u63a5\u5199\u5165\u5f02\u5e38",
        "failed_runs_24h": "24 \u5c0f\u65f6\u5931\u8d25\u4efb\u52a1\u6570\u5f02\u5e38",
        "open_high_issues": "\u5f53\u524d\u9ad8\u98ce\u9669\u672a\u95ed\u73af\u95ee\u9898\u8fc7\u591a",
        "app_storage_warn": "\u5e94\u7528\u76ee\u5f55\u7a7a\u95f4\u5360\u7528\u8d85\u9608\u503c",
        "app_storage_total_warn": "\u603b\u78c1\u76d8\u5360\u7528\u8d85\u9608\u503c",
    }
    label = mapping.get(head, text)
    if num and num.isdigit():
        return f"{label}\uff08{num}\uff09"
    return label




def safe_slug(value: str, max_len: int = 32) -> str:
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip())
    out = out.strip("-._")
    if not out:
        return "unknown"
    return out[:max_len]


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def iso_to_local_text(value: Any) -> str:
    dt = parse_iso(value)
    if not dt:
        return "-"
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S UTC+8")


def resolve_log_mode(mode: str, cfg: dict[str, Any], override: str) -> str:
    override_mode = normalize_log_mode(override, default="")
    if override_mode:
        return override_mode
    switches = cfg.get("skill_log_switches")
    if not isinstance(switches, dict):
        return "silent"
    item = switches.get(mode)
    if not isinstance(item, dict):
        return "silent"
    return normalize_log_mode(str(item.get("normal_log_mode", "silent")), default="silent")


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


def default_config() -> dict[str, Any]:
    home = Path(os.path.expanduser("~"))
    disk_paths = ["C:\\"] if os.name == "nt" else ["/", str(home / ".openclaw")]
    return {
        "schema_version": "2026-03-02",
        "log_roots": [
            str(home / ".openclaw" / "workspace-ops-agent" / "ops"),
            str(home / ".openclaw" / "workspace-ops-agent" / "ops" / "logs"),
            str(home / ".openclaw" / "workflows"),
            str(home / ".openclaw" / "logs"),
        ],
        "log_patterns": ["*.log", "**/*.log", "*.out", "**/*.out"],
        "exclude_path_substrings": ["node_modules", ".git", "__pycache__", ".venv", "/tmp/"],
        "max_log_files": 120,
        "incremental_max_bytes_per_file": 262144,
        "full_scan_tail_bytes_per_file": 1048576,
        "max_lines_per_file": 2000,
        "auto_resolve_after_missed_runs": 2,
        "keep_resolved_days": 7,
        "fallback_full_on_incremental_error": True,
        "incremental_full_backstop_runs": 96,
        "service_monitor": {
            "enabled": True,
            "list_command": "systemctl list-units --type=service --all --no-pager --no-legend",
            "include_regex": [
                "openclaw",
                "gateway",
                "subscription",
                "realtime",
                "nginx",
                "redis",
                "mysql",
                "postgres",
                "docker",
            ],
            "max_services": 120,
            "derive_log_paths": True,
        },
        "runtime_monitor": {
            "enabled": True,
            "project_registry": str(home / ".openclaw" / "ops" / "task-center" / "project-registry.json"),
            "max_projects": 24,
            "max_items_per_project": 12,
            "process_timeout_seconds": 15,
            "service_timeout_seconds": 10,
        },
        "system_monitor": {
            "enabled": True,
            "disk_paths": disk_paths,
            "disk_warn_percent": 85.0,
            "memory_warn_percent": 90.0,
            "cpu_warn_percent": 90.0,
            "process_cpu_warn_percent": 95.0,
            "top_n_processes": 5,
        },
        "app_usage_monitor": {
            "enabled": True,
            "paths": [
                {"name": "openclaw_home", "path": str(home / ".openclaw"), "warn_gb": 8.0},
                {
                    "name": "openclaw_workflow_repo",
                    "path": str(home / "openclaw-hardflow-backup-20260302"),
                    "warn_gb": 5.0,
                },
                {"name": "market_center", "path": str(home / "DabaiMarketCenter"), "warn_gb": 20.0},
                {
                    "name": "subscription_website",
                    "path": str(home / "Dabai-Polymarket-Subscription-Website"),
                    "warn_gb": 10.0,
                },
            ],
            "top_n": 5,
            "warn_total_gb": 60.0,
            "collect_timeout_seconds": 15,
            "python_walk_max_files": 200000,
        },
        "daily": {
            "major_only": True,
            "window_hours": 24,
            "top_issue_limit": 8,
        },
        "workflow_monitor": {
            "enabled": True,
            "jobs_file": str(home / ".openclaw" / "cron" / "jobs.json"),
            "max_report_jobs": 8,
            "stale_error_minutes": 30,
            "ignore_job_names": sorted(DEFAULT_WORKFLOW_MONITOR_IGNORED_JOB_NAMES),
        },
        "token_monitor": {
            "enabled": True,
            "task_center_db": str(home / ".openclaw" / "ops" / "task-center" / "task_center.db"),
            "cron_runs_dir": str(home / ".openclaw" / "cron" / "runs"),
            "jobs_file": str(home / ".openclaw" / "cron" / "jobs.json"),
            "window_hours": 24,
            "top_agents": 5,
        },
        "skill_log_switches": {
            "incremental": {"normal_log_mode": "silent", "risk_always_notify": True},
            "full": {"normal_log_mode": "silent", "risk_always_notify": True},
            "daily": {"normal_log_mode": "silent", "risk_always_notify": True},
        },
        # Only notify when errors are detected.
        "errors_only_notify": True,
        "notify_policy": {
            # In silent mode, only risk notifications should be sent.
            "silent_notify_on_change": False,
            # Chat mode can be enabled for change-only notifications when needed.
            "chat_notify_on_change": False,
            # Keep chat quiet by default when there is no risk/no change.
            "chat_notify_on_no_change": False,
            # Daily mode follows dedicated toggles.
            "daily_silent_notify_on_change": False,
            "daily_chat_notify_on_change": False,
            "daily_chat_notify_on_no_change": False,
            # Avoid repeated spam for unchanged high-risk incidents.
            "risk_repeat_cooldown_minutes": 60,
        },
        "incident_handoff": {
            "enabled": True,
            "mode": "todo_only",
            "todo_file": str(home / ".openclaw" / "workspace-coordinator" / "TODO.md"),
            "routing_file": str(home / ".openclaw" / "ops" / "policy" / "routing-rules.json"),
            "source": "ops-cron-runner",
            "default_assignee": "coordinator",
            "max_handoff_per_run": 6,
            "max_issue_items_per_run": 4,
            "max_workflow_jobs_per_run": 2,
            "high_risk_direct_human": True,
            "write_medium_risk_to_todo": False,
        },
        "workflow_follow_up": {
            "enabled": True,
            "task_center_db": str(home / ".openclaw" / "ops" / "task-center" / "task_center.db"),
            "task_type": "ops_workflow_repair",
            "source": "ops-agent/ops-cron-runner",
            "default_assignee": "optimization-agent",
            "pool": "jobs",
            "priority": "high",
            "risk_level": "low",
            "max_tasks_per_run": 2,
        },
    }


def default_state() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-02",
        "updated_at": "",
        "runs": {"incremental": 0, "full": 0, "daily": 0},
        "checkpoints": {},
        "issues": {},
        "services": {},
        "runtime_monitor": {},
        "known_logs": [],
        "last_full_scan_at": "",
        "last_run_record": "",
    }


def normalize_line(line: str) -> str:
    text = line.strip().lower()
    for pattern in VOLATILE_PATTERNS:
        text = re.sub(pattern, "<x>", text)
    text = re.sub(r"\s+", " ", text)
    return text[:320]


def issue_key(source: str, normalized: str) -> str:
    raw = f"{source}|{normalized}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def read_tail(path: Path, max_bytes: int) -> tuple[str, dict[str, Any]]:
    stat = path.stat()
    size = stat.st_size
    start = max(0, size - max(0, int(max_bytes)))
    with path.open("rb") as f:
        f.seek(start)
        payload = f.read(max(0, size - start))
    text = payload.decode("utf-8", errors="replace")
    return text, {
        "inode": str(getattr(stat, "st_ino", 0)),
        "size": size,
        "offset": size,
        "mtime": int(stat.st_mtime),
        "last_mode": "full",
        "bytes_read": len(payload),
    }


def read_incremental(path: Path, checkpoint: dict[str, Any], max_bytes: int) -> tuple[str, dict[str, Any], bool]:
    stat = path.stat()
    inode = str(getattr(stat, "st_ino", 0))
    size = stat.st_size
    prior_inode = str(checkpoint.get("inode", ""))
    prior_offset = int(checkpoint.get("offset", 0) or 0)

    fallback = prior_inode != inode or prior_offset > size
    if fallback:
        start = max(0, size - max(0, int(max_bytes)))
    else:
        start = max(0, prior_offset)
        if size - start > max_bytes:
            start = size - max_bytes
            fallback = True

    with path.open("rb") as f:
        f.seek(start)
        payload = f.read(max(0, size - start))
    text = payload.decode("utf-8", errors="replace")
    return text, {
        "inode": inode,
        "size": size,
        "offset": size,
        "mtime": int(stat.st_mtime),
        "last_mode": "incremental",
        "bytes_read": len(payload),
    }, fallback


def run_shell(command: str, timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            shell=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)


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
    return Path(__file__).resolve().parent / "policy" / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized_id = str(task_id or "").strip()
    if not normalized_id:
        return False
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized_id,)).fetchone()
        conn.close()
        return bool(row)
    except Exception:
        return False


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "ops-agent").strip() or "ops-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "ops-agent"
    source_name = str(source_module or "ops-agent/ops-cron-runner").strip() or "ops-agent/ops-cron-runner"
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
    attempts = 3
    delay_sec = 2
    for attempt in range(attempts):
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
        if proc.returncode == 0:
            if not isinstance(payload, dict):
                return False, {}, "policy_enforcer_invalid_json_output"
            if not bool(payload.get("ok", False)):
                return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
            return True, payload, ""

        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        retryable_lock = "database is locked" in err_text.lower()
        if retryable_lock and attempt < attempts - 1:
            time.sleep(delay_sec * (attempt + 1))
            continue
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    return False, {}, "policy_enforcer_failed:retry_exhausted"


def collect_services(cfg: dict[str, Any]) -> tuple[dict[str, dict[str, str]], str | None]:
    svc_cfg = cfg.get("service_monitor") or {}
    if not svc_cfg.get("enabled", True):
        return {}, None
    command = str(svc_cfg.get("list_command", "")).strip()
    if not command:
        return {}, None

    include_regex = [re.compile(x, re.IGNORECASE) for x in svc_cfg.get("include_regex", []) if str(x).strip()]
    rc, out, err = run_shell(command, timeout=20)
    if rc != 0:
        return {}, err or f"service list exit={rc}"

    services: dict[str, dict[str, str]] = {}
    max_services = max(1, int(svc_cfg.get("max_services", 120)))
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        unit, _load, active, sub = parts[:4]
        name = unit[:-8] if unit.endswith(".service") else unit
        if include_regex and not any(rx.search(name) for rx in include_regex):
            continue
        services[name] = {"unit": unit, "state": f"{active}/{sub}"}
        if len(services) >= max_services:
            break
    return services, None


def _project_registry_items(path: Path) -> list[dict[str, Any]]:
    raw = load_json(path, {})
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("projects", [])
    else:
        items = []
    return [dict(item) for item in items if isinstance(item, dict)]


def _safe_resolve_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except Exception:
        return path.expanduser()


def _normalize_runtime_log_paths(project_root: Path | None, value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if project_root is not None and not path.is_absolute():
            path = project_root / path
        resolved = str(_safe_resolve_path(path))
        if resolved in seen:
            continue
        seen.add(resolved)
        rows.append(resolved)
    return rows


def _process_probe(match: str, *, cwd: str, timeout: int) -> tuple[list[dict[str, str]], str]:
    pattern = str(match or "").strip()
    if not pattern:
        return [], "missing_process_match"
    command = f"pgrep -af -- {shlex.quote(pattern)}"
    rc, out, err = run_shell(command, timeout=max(3, int(timeout)))
    if rc not in {0, 1}:
        return [], err or out or f"pgrep_exit={rc}"
    rows: list[dict[str, str]] = []
    cwd_norm = str(cwd or "").strip().replace("\\", "/").lower()
    for line in out.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split(None, 1)
        pid = parts[0] if parts else ""
        command_line = parts[1] if len(parts) > 1 else ""
        if pattern and pattern not in command_line:
            continue
        if cwd_norm and cwd_norm not in command_line.replace("\\", "/").lower():
            continue
        rows.append({"pid": pid, "command": command_line})
    return rows, ""


def _service_probe(
    service_unit: str,
    *,
    service_snapshot: dict[str, dict[str, str]],
    timeout: int,
) -> tuple[str, str]:
    unit = str(service_unit or "").strip()
    if not unit:
        return "error", "missing_service_unit"
    aliases = [unit]
    if unit.endswith(".service"):
        aliases.append(unit[:-8])
    else:
        aliases.append(f"{unit}.service")
    for alias in aliases:
        row = service_snapshot.get(alias)
        if not isinstance(row, dict):
            continue
        state = str(row.get("state", "")).strip()
        if state.startswith("active/"):
            return "running", state
        return "stopped", state or "inactive"

    rc, out, err = run_shell(f"systemctl is-active {shlex.quote(unit)}", timeout=max(3, int(timeout)))
    state = str(out or err).strip().lower()
    if rc == 0 and state == "active":
        return "running", "active"
    if state in {"inactive", "failed", "deactivating"} or rc in {3, 4}:
        return "stopped", state or f"exit={rc}"
    if rc == 0:
        return "running", state or "active"
    return "error", state or f"systemctl_exit={rc}"


def collect_runtime_project_health(
    cfg: dict[str, Any],
    *,
    service_snapshot: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    monitor = cfg.get("runtime_monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    enabled = bool(monitor.get("enabled", True))
    registry_path = Path(
        str(monitor.get("project_registry", "")).strip()
        or str(Path.home() / ".openclaw" / "ops" / "task-center" / "project-registry.json")
    ).expanduser()
    result: dict[str, Any] = {
        "enabled": enabled,
        "project_registry": str(registry_path),
        "projects": [],
        "missing_required": [],
        "log_paths": [],
        "errors": [],
        "snapshot": {},
        "summary": {
            "project_count": 0,
            "item_count": 0,
            "required_missing_count": 0,
            "running_count": 0,
            "stopped_count": 0,
            "disabled_count": 0,
            "error_count": 0,
        },
    }
    if not enabled:
        return result
    if not registry_path.exists():
        result["errors"].append(f"project_registry_missing:{registry_path}")
        result["summary"]["error_count"] = 1
        return result

    projects = _project_registry_items(registry_path)
    max_projects = max(1, int(monitor.get("max_projects", 24) or 24))
    max_items_per_project = max(1, int(monitor.get("max_items_per_project", 12) or 12))
    process_timeout = max(3, int(monitor.get("process_timeout_seconds", 15) or 15))
    service_timeout = max(3, int(monitor.get("service_timeout_seconds", 10) or 10))
    known_services = service_snapshot if isinstance(service_snapshot, dict) else {}
    log_paths: set[str] = set()
    snapshot: dict[str, str] = {}

    for project in projects[:max_projects]:
        monitor_cfg = project.get("runtime_monitoring")
        if not isinstance(monitor_cfg, dict):
            continue
        project_enabled = bool(monitor_cfg.get("enabled", True))
        project_id = str(project.get("id", "")).strip() or safe_slug(str(project.get("name", "")))
        project_name = str(project.get("name", "")).strip() or project_id
        project_path_text = str(project.get("path", "")).strip()
        project_root = _safe_resolve_path(Path(project_path_text)) if project_path_text else None
        items_raw = monitor_cfg.get("items", [])
        if not isinstance(items_raw, list):
            items_raw = []

        project_row = {
            "id": project_id,
            "name": project_name,
            "path": str(project_root) if project_root else project_path_text,
            "enabled": project_enabled,
            "items": [],
        }
        item_rows: list[dict[str, Any]] = []

        for idx, raw in enumerate(items_raw[:max_items_per_project], start=1):
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id", "")).strip() or safe_slug(str(raw.get("name", "")) or f"item-{idx}")
            item_name = str(raw.get("name", "")).strip() or item_id
            item_type = str(raw.get("type", "process")).strip().lower() or "process"
            item_enabled = project_enabled and bool(raw.get("enabled", True))
            required = bool(raw.get("required", True))
            cwd = str(raw.get("cwd", "")).strip() or (str(project_root) if project_root else "")
            logs = _normalize_runtime_log_paths(project_root, raw.get("log_paths"))
            for path in logs:
                log_paths.add(path)
            row = {
                "id": item_id,
                "name": item_name,
                "type": item_type,
                "required": required,
                "enabled": item_enabled,
                "match": str(raw.get("match", "")).strip(),
                "service_unit": str(raw.get("service_unit", "")).strip(),
                "cwd": cwd,
                "status": "disabled",
                "message": "",
                "processes": [],
                "log_paths": logs,
                "stop_command": str(raw.get("stop_command", "")).strip(),
            }

            if not item_enabled:
                result["summary"]["disabled_count"] += 1
            elif item_type == "process":
                processes, error = _process_probe(row["match"], cwd=cwd, timeout=process_timeout)
                row["processes"] = processes
                if error:
                    row["status"] = "error"
                    row["message"] = error
                    result["summary"]["error_count"] += 1
                    result["errors"].append(f"{project_id}:{item_id}:{error}")
                elif processes:
                    row["status"] = "running"
                    row["message"] = f"matched={len(processes)}"
                    result["summary"]["running_count"] += 1
                else:
                    row["status"] = "missing"
                    row["message"] = "process_not_found"
                    result["summary"]["stopped_count"] += 1
            elif item_type == "service":
                status, message = _service_probe(
                    row["service_unit"] or item_name,
                    service_snapshot=known_services,
                    timeout=service_timeout,
                )
                row["status"] = status
                row["message"] = message
                if status == "running":
                    result["summary"]["running_count"] += 1
                elif status == "error":
                    result["summary"]["error_count"] += 1
                    result["errors"].append(f"{project_id}:{item_id}:{message}")
                else:
                    result["summary"]["stopped_count"] += 1
            else:
                row["status"] = "error"
                row["message"] = f"unsupported_type:{item_type}"
                result["summary"]["error_count"] += 1
                result["errors"].append(f"{project_id}:{item_id}:unsupported_type:{item_type}")

            result["summary"]["item_count"] += 1
            snapshot[f"{project_id}:{item_id}"] = row["status"]
            if item_enabled and required and row["status"] != "running":
                result["missing_required"].append(
                    {
                        "project_id": project_id,
                        "project_name": project_name,
                        "item_id": item_id,
                        "item_name": item_name,
                        "type": item_type,
                        "status": row["status"],
                        "message": row["message"],
                        "log_paths": logs,
                        "stop_command": row["stop_command"],
                    }
                )
            item_rows.append(row)

        if item_rows:
            project_row["items"] = item_rows
            result["projects"].append(project_row)

    result["summary"]["project_count"] = len(result["projects"])
    result["summary"]["required_missing_count"] = len(result["missing_required"])
    result["log_paths"] = sorted(log_paths)
    result["snapshot"] = snapshot
    return result


def discover_logs(cfg: dict[str, Any], service_names: list[str], extra_paths: list[str] | None = None) -> list[Path]:
    roots = [Path(str(x)).expanduser() for x in (cfg.get("log_roots") or [])]
    patterns = [str(x).strip() for x in (cfg.get("log_patterns") or ["*.log"]) if str(x).strip()]
    excludes = [str(x).lower() for x in (cfg.get("exclude_path_substrings") or []) if str(x).strip()]
    max_files = max(1, int(cfg.get("max_log_files", 120)))

    candidates: set[Path] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for pattern in patterns:
            for item in root.glob(pattern):
                if item.is_file():
                    candidates.add(item.resolve())

    svc_cfg = cfg.get("service_monitor") or {}
    if svc_cfg.get("derive_log_paths", True):
        extra_roots = [Path("/var/log"), Path.home() / ".openclaw" / "logs"]
        for svc in service_names:
            for root in extra_roots:
                f1 = root / f"{svc}.log"
                f2 = root / svc / "service.log"
                if f1.exists() and f1.is_file():
                    candidates.add(f1.resolve())
                if f2.exists() and f2.is_file():
                    candidates.add(f2.resolve())

    if isinstance(extra_paths, list):
        for raw in extra_paths:
            text = str(raw or "").strip()
            if not text:
                continue
            item = Path(text).expanduser()
            if item.exists() and item.is_file():
                candidates.add(_safe_resolve_path(item))

    kept: list[Path] = []
    for item in candidates:
        text = str(item).lower().replace("\\", "/")
        if any(block in text for block in excludes):
            continue
        kept.append(item)
    kept.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return kept[:max_files]


def extract_findings(path: Path, text: str, max_lines: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not text:
        return findings

    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    source = str(path)
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if not any(k in lower for k in ERROR_KEYWORDS):
            continue
        normalized = normalize_line(line)
        severity = "high" if any(k in lower for k in HIGH_KEYWORDS) else "medium"
        findings.append(
            {
                "key": issue_key(source, normalized),
                "source": source,
                "title": line[:220],
                "normalized": normalized,
                "severity": severity,
            }
        )
    return findings


def update_issues(state: dict[str, Any], findings: list[dict[str, Any]], resolve_after: int, keep_days: int) -> dict[str, int]:
    issues = state.setdefault("issues", {})
    ts = now_iso()
    seen: set[str] = set()
    created = 0
    reopened = 0
    resolved = 0
    created_high = 0
    reopened_high = 0

    for item in findings:
        key = item["key"]
        seen.add(key)
        rec = issues.get(key)
        if not isinstance(rec, dict):
            issues[key] = {
                "key": key,
                "title": item["title"],
                "source": item["source"],
                "severity": item["severity"],
                "first_seen": ts,
                "last_seen": ts,
                "status": "open",
                "occurrences": 1,
                "missed_runs": 0,
                "resolved_at": "",
            }
            created += 1
            if item.get("severity") == "high":
                created_high += 1
            continue
        if rec.get("status") == "resolved":
            rec["status"] = "open"
            rec["resolved_at"] = ""
            reopened += 1
            if item.get("severity") == "high":
                reopened_high += 1
        rec["title"] = item["title"]
        rec["source"] = item["source"]
        rec["severity"] = item["severity"] if rec.get("severity") != "high" else "high"
        rec["last_seen"] = ts
        rec["occurrences"] = int(rec.get("occurrences", 0)) + 1
        rec["missed_runs"] = 0

    for key, rec in list(issues.items()):
        if not isinstance(rec, dict) or rec.get("status") != "open":
            continue
        if key in seen:
            continue
        missed = int(rec.get("missed_runs", 0)) + 1
        rec["missed_runs"] = missed
        if missed >= max(1, resolve_after):
            rec["status"] = "resolved"
            rec["resolved_at"] = ts
            resolved += 1

    if keep_days > 0:
        cutoff = now() - timedelta(days=max(1, keep_days))
        for key, rec in list(issues.items()):
            if not isinstance(rec, dict):
                continue
            if rec.get("status") != "resolved":
                continue
            value = str(rec.get("resolved_at", "")).strip()
            if not value:
                continue
            try:
                resolved_at = datetime.fromisoformat(value)
            except Exception:
                continue
            if resolved_at < cutoff:
                issues.pop(key, None)

    open_total = sum(1 for x in issues.values() if isinstance(x, dict) and x.get("status") == "open")
    open_high_total = sum(
        1
        for x in issues.values()
        if isinstance(x, dict) and x.get("status") == "open" and str(x.get("severity")) == "high"
    )
    return {
        "new": created,
        "new_high": created_high,
        "reopened": reopened,
        "reopened_high": reopened_high,
        "resolved": resolved,
        "open_total": open_total,
        "open_high_total": open_high_total,
    }


def _default_app_usage_items() -> list[dict[str, Any]]:
    home = Path.home()
    return [
        {"name": "openclaw_home", "path": str(home / ".openclaw"), "warn_gb": 8.0},
        {"name": "openclaw_workflow_repo", "path": str(home / "openclaw-hardflow-backup-20260302"), "warn_gb": 5.0},
        {"name": "market_center", "path": str(home / "DabaiMarketCenter"), "warn_gb": 20.0},
        {"name": "subscription_website", "path": str(home / "Dabai-Polymarket-Subscription-Website"), "warn_gb": 10.0},
    ]


def _parse_app_usage_items(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return out
    for raw in value:
        if isinstance(raw, str):
            path = str(raw).strip()
            if not path:
                continue
            p = Path(path).expanduser()
            name = p.name or p.as_posix().rstrip("/").split("/")[-1] or "app"
            out.append({"name": safe_slug(name, 48), "path": str(p), "warn_gb": 0.0})
            continue
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path", "")).strip()
        if not path:
            continue
        p = Path(path).expanduser()
        name = str(raw.get("name", "")).strip() or (p.name or "app")
        try:
            warn_gb = float(raw.get("warn_gb", 0.0) or 0.0)
        except Exception:
            warn_gb = 0.0
        out.append({"name": safe_slug(name, 48), "path": str(p), "warn_gb": max(0.0, warn_gb)})
    return out


def _dir_size_bytes(path: Path, *, timeout: int, walk_max_files: int) -> tuple[int | None, str]:
    if not path.exists():
        return None, "path_missing"
    if path.is_file():
        try:
            return int(path.stat().st_size), ""
        except Exception as exc:
            return None, f"stat_failed:{exc}"

    if os.name != "nt":
        for cmd, scale in ((["du", "-sb", str(path)], 1), (["du", "-sk", str(path)], 1024)):
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(2, int(timeout)),
                    check=False,
                )
            except Exception:
                proc = None
            if proc is None or proc.returncode != 0:
                continue
            token = str(proc.stdout or "").strip().split()[0] if str(proc.stdout or "").strip() else ""
            if token.isdigit():
                return int(token) * scale, ""

    total = 0
    seen = 0
    try:
        for root, _dirs, files in os.walk(path):
            for fn in files:
                seen += 1
                if seen > max(1000, int(walk_max_files)):
                    return None, f"walk_file_limit_exceeded:{walk_max_files}"
                fp = Path(root) / fn
                try:
                    total += int(fp.stat().st_size)
                except Exception:
                    continue
    except Exception as exc:
        return None, f"walk_failed:{exc}"
    return total, ""


def collect_app_usage(cfg: dict[str, Any]) -> dict[str, Any]:
    monitor = cfg.get("app_usage_monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    enabled = bool(monitor.get("enabled", True))
    top_n = max(1, int(monitor.get("top_n", 5) or 5))
    warn_total_gb = max(0.0, float(monitor.get("warn_total_gb", 60.0) or 0.0))
    collect_timeout = max(2, int(monitor.get("collect_timeout_seconds", 15) or 15))
    walk_max_files = max(1000, int(monitor.get("python_walk_max_files", 200000) or 200000))

    items = _parse_app_usage_items(monitor.get("paths"))
    if not items:
        items = _default_app_usage_items()

    result: dict[str, Any] = {
        "enabled": enabled,
        "total_bytes": 0,
        "total_gb": 0.0,
        "warn_total_gb": warn_total_gb,
        "warn_total_exceeded": False,
        "items": [],
        "top": [],
        "warn_items": [],
        "errors": [],
    }
    if not enabled:
        return result

    total_bytes = 0
    rows: list[dict[str, Any]] = []
    warn_rows: list[dict[str, Any]] = []
    for item in items:
        path = Path(str(item.get("path", "")).strip()).expanduser()
        if not path.exists():
            continue
        size_bytes, err = _dir_size_bytes(path, timeout=collect_timeout, walk_max_files=walk_max_files)
        if err and size_bytes is None:
            result["errors"].append(f"{item.get('name')}:{path}:{err}")
            continue
        size_bytes = int(size_bytes or 0)
        size_gb = round(size_bytes / (1024.0 ** 3), 3)
        warn_gb = max(0.0, float(item.get("warn_gb", 0.0) or 0.0))
        warn_exceeded = warn_gb > 0 and size_gb >= warn_gb
        row = {
            "name": str(item.get("name", "")).strip() or path.name or "app",
            "path": str(path),
            "size_bytes": size_bytes,
            "size_gb": size_gb,
            "warn_gb": warn_gb,
            "warn_exceeded": warn_exceeded,
        }
        rows.append(row)
        total_bytes += size_bytes
        if warn_exceeded:
            warn_rows.append(row)

    rows.sort(key=lambda x: int(x.get("size_bytes", 0) or 0), reverse=True)
    warn_rows.sort(key=lambda x: float(x.get("size_gb", 0.0) or 0.0), reverse=True)
    total_gb = round(total_bytes / (1024.0 ** 3), 3)
    result["total_bytes"] = total_bytes
    result["total_gb"] = total_gb
    result["warn_total_exceeded"] = warn_total_gb > 0 and total_gb >= warn_total_gb
    result["items"] = rows
    result["top"] = rows[:top_n]
    result["warn_items"] = warn_rows
    return result


def collect_system_metrics(cfg: dict[str, Any]) -> dict[str, Any]:
    sys_cfg = cfg.get("system_monitor") or {}
    if not sys_cfg.get("enabled", True):
        return {"anomalies": []}

    disk_warn = float(sys_cfg.get("disk_warn_percent", 85.0))
    mem_warn = float(sys_cfg.get("memory_warn_percent", 90.0))
    cpu_warn = float(sys_cfg.get("cpu_warn_percent", 90.0))
    paths = [Path(str(x)).expanduser() for x in (sys_cfg.get("disk_paths") or [])]

    payload: dict[str, Any] = {"disk": [], "cpu_percent": None, "memory_percent": None, "anomalies": []}
    for path in paths:
        if not path.exists():
            continue
        usage = shutil.disk_usage(path)
        used_pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0.0
        payload["disk"].append({"path": str(path), "used_percent": round(used_pct, 2)})
        if used_pct >= disk_warn:
            payload["anomalies"].append(f"disk>{disk_warn}%:{path}={used_pct:.2f}%")

    try:
        import psutil  # type: ignore

        payload["cpu_percent"] = round(float(psutil.cpu_percent(interval=0.2)), 2)
        payload["memory_percent"] = round(float(psutil.virtual_memory().percent), 2)
        if payload["cpu_percent"] >= cpu_warn:
            payload["anomalies"].append(f"cpu>{cpu_warn}%:{payload['cpu_percent']:.2f}%")
        if payload["memory_percent"] >= mem_warn:
            payload["anomalies"].append(f"memory>{mem_warn}%:{payload['memory_percent']:.2f}%")
    except Exception:
        pass

    app_usage = collect_app_usage(cfg)
    payload["app_usage"] = app_usage
    warn_items = app_usage.get("warn_items", []) if isinstance(app_usage.get("warn_items", []), list) else []
    for row in warn_items[:6]:
        name = str((row or {}).get("name", "")).strip() or str((row or {}).get("path", "unknown"))
        warn_gb = float((row or {}).get("warn_gb", 0.0) or 0.0)
        size_gb = float((row or {}).get("size_gb", 0.0) or 0.0)
        payload["anomalies"].append(f"app_storage>{warn_gb:.1f}GB:{name}={size_gb:.2f}GB")
    if bool(app_usage.get("warn_total_exceeded", False)):
        warn_total_gb = float(app_usage.get("warn_total_gb", 0.0) or 0.0)
        total_gb = float(app_usage.get("total_gb", 0.0) or 0.0)
        payload["anomalies"].append(f"app_storage_total>{warn_total_gb:.1f}GB:{total_gb:.2f}GB")

    return payload


def _ms_to_iso(ms_value: Any) -> str:
    try:
        ms = int(ms_value or 0)
    except Exception:
        return ""
    if ms <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000.0, TZ).isoformat(timespec="seconds")
    except Exception:
        return ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_any_ts_to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        iv = int(value)
        if iv <= 0:
            return None
        # Heuristic: unix ms if value is large enough.
        if iv > 10_000_000_000:
            iv = iv / 1000.0
        return datetime.fromtimestamp(iv, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _collect_token_usage_from_cron_runs(
    monitor: dict[str, Any],
    *,
    window_hours: int,
    top_agents: int,
) -> dict[str, Any]:
    runs_dir = Path(
        str(monitor.get("cron_runs_dir", "")).strip() or str(Path.home() / ".openclaw" / "cron" / "runs")
    ).expanduser()
    jobs_file = Path(str(monitor.get("jobs_file", "")).strip() or str(Path.home() / ".openclaw" / "cron" / "jobs.json")).expanduser()
    start_utc = datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)
    errors: list[str] = []

    name_by_job_id: dict[str, str] = {}
    jobs_raw = load_json(jobs_file, {})
    jobs = jobs_raw.get("jobs", []) if isinstance(jobs_raw, dict) else []
    if isinstance(jobs, list):
        for item in jobs:
            if not isinstance(item, dict):
                continue
            jid = str(item.get("id", "")).strip()
            if not jid:
                continue
            name_by_job_id[jid] = str(item.get("name", "")).strip() or jid

    if not runs_dir.exists():
        return {
            "rows": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
            "by_agent": [],
            "runs_dir": str(runs_dir),
            "jobs_file": str(jobs_file),
            "errors": [f"cron_runs_dir_missing:{runs_dir}"],
        }

    rows = 0
    total_tokens = 0
    total_cost = 0.0
    by_agent: dict[str, dict[str, Any]] = {}

    for run_file in sorted(runs_dir.glob("*.jsonl")):
        job_id = run_file.stem
        agent_id = name_by_job_id.get(job_id, job_id)
        try:
            file_mtime_utc = datetime.fromtimestamp(run_file.stat().st_mtime, tz=timezone.utc)
        except Exception:
            file_mtime_utc = datetime.now(tz=timezone.utc)
        try:
            with run_file.open("r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    text = line.strip().lstrip("\ufeff")
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    usage = payload.get("usage")
                    if not isinstance(usage, dict):
                        continue

                    ts = (
                        _parse_any_ts_to_utc(payload.get("finishedAtMs"))
                        or _parse_any_ts_to_utc(payload.get("startedAtMs"))
                        or _parse_any_ts_to_utc(payload.get("finished_at"))
                        or _parse_any_ts_to_utc(payload.get("ended_at"))
                        or _parse_any_ts_to_utc(payload.get("started_at"))
                        or file_mtime_utc
                    )
                    if ts < start_utc:
                        continue

                    input_tokens = _safe_int(usage.get("input_tokens"), 0)
                    output_tokens = _safe_int(usage.get("output_tokens"), 0)
                    usage_total = _safe_int(usage.get("total_tokens"), 0)
                    if usage_total <= 0:
                        usage_total = max(0, input_tokens + output_tokens)
                    try:
                        usage_cost = float(usage.get("cost_estimate", 0.0) or 0.0)
                    except Exception:
                        usage_cost = 0.0

                    rows += 1
                    total_tokens += usage_total
                    total_cost += usage_cost
                    agg = by_agent.setdefault(
                        agent_id,
                        {
                            "agent_id": agent_id,
                            "total_tokens": 0,
                            "cost_estimate": 0.0,
                        },
                    )
                    agg["total_tokens"] = int(agg.get("total_tokens", 0) or 0) + usage_total
                    agg["cost_estimate"] = float(agg.get("cost_estimate", 0.0) or 0.0) + usage_cost
        except Exception as exc:
            errors.append(f"cron_runs_read_failed:{run_file}:{exc}")

    ranked = sorted(by_agent.values(), key=lambda x: int(x.get("total_tokens", 0) or 0), reverse=True)
    top = []
    for item in ranked[: max(1, top_agents)]:
        tok = int(item.get("total_tokens", 0) or 0)
        top.append(
            {
                "agent_id": str(item.get("agent_id", "")),
                "total_tokens": tok,
                "total_tokens_m": round(tok / 1_000_000.0, 6),
                "cost_estimate": round(float(item.get("cost_estimate", 0.0) or 0.0), 6),
            }
        )
    return {
        "rows": rows,
        "total_tokens": total_tokens,
        "cost_estimate": round(total_cost, 6),
        "by_agent": top,
        "runs_dir": str(runs_dir),
        "jobs_file": str(jobs_file),
        "errors": errors,
    }


def collect_workflow_health(cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    monitor = cfg.get("workflow_monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    if not bool(monitor.get("enabled", True)):
        return {
            "enabled": False,
            "jobs_file": "",
            "jobs_total": 0,
            "jobs_enabled": 0,
            "failed_count": 0,
            "stale_failed_count": 0,
            "new_failed_count": 0,
            "recovered_count": 0,
            "failed_jobs": [],
            "errors": [],
        }

    jobs_file = Path(str(monitor.get("jobs_file", "")).strip() or str(Path.home() / ".openclaw" / "cron" / "jobs.json"))
    jobs_file = jobs_file.expanduser()
    errors: list[str] = []
    raw = load_json(jobs_file, {})
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else []
    if not isinstance(jobs, list):
        jobs = []

    prev_status = state.get("workflow_job_status", {})
    if not isinstance(prev_status, dict):
        prev_status = {}

    current_status: dict[str, str] = {}
    failed_jobs: list[dict[str, Any]] = []
    jobs_total = 0
    jobs_enabled = 0
    now_ms = int(now().timestamp() * 1000)
    new_failed = 0
    recovered = 0
    ignored_failed = 0
    raw_ignored_job_names = monitor.get("ignore_job_names", [])
    if not isinstance(raw_ignored_job_names, list):
        raw_ignored_job_names = []
    raw_ignored_job_ids = monitor.get("ignore_job_ids", [])
    if not isinstance(raw_ignored_job_ids, list):
        raw_ignored_job_ids = []
    ignored_job_names = {str(item).strip() for item in raw_ignored_job_names if str(item).strip()}
    ignored_job_ids = {str(item).strip() for item in raw_ignored_job_ids if str(item).strip()}

    for item in jobs:
        if not isinstance(item, dict):
            continue
        jobs_total += 1
        jid = str(item.get("id", "")).strip() or f"job-{jobs_total}"
        name = str(item.get("name", "")).strip() or jid
        enabled = bool(item.get("enabled", False))
        ignored = jid in ignored_job_ids or name in ignored_job_names
        if enabled:
            jobs_enabled += 1

        st = item.get("state", {})
        if not isinstance(st, dict):
            st = {}
        last_status = str(st.get("lastStatus") or st.get("lastRunStatus") or "").strip().lower()
        current_status[jid] = last_status

        prev = str(prev_status.get(jid, "")).strip().lower()
        if enabled and (not ignored) and last_status in {"error", "failed"} and prev not in {"error", "failed"}:
            new_failed += 1
        if enabled and (not ignored) and last_status not in {"error", "failed"} and prev in {"error", "failed"}:
            recovered += 1

        if not enabled or last_status not in {"error", "failed"}:
            continue
        if ignored:
            ignored_failed += 1
            continue

        run_at_ms = _safe_int(st.get("lastRunAtMs"), 0)
        stale_minutes = 0.0
        if run_at_ms > 0:
            stale_minutes = max(0.0, (now_ms - run_at_ms) / 60000.0)
        failed_jobs.append(
            {
                "id": jid,
                "name": name,
                "agent_id": str(item.get("agentId", "")).strip(),
                "last_status": last_status,
                "consecutive_errors": _safe_int(st.get("consecutiveErrors"), 0),
                "last_run_at_ms": run_at_ms,
                "last_run_at": _ms_to_iso(run_at_ms),
                "stale_minutes": round(stale_minutes, 2),
                "last_error": str(st.get("lastError", "")).strip(),
            }
        )

    stale_error_minutes = max(1, _safe_int(monitor.get("stale_error_minutes"), 30))
    stale_failed_count = sum(1 for row in failed_jobs if float(row.get("stale_minutes", 0.0) or 0.0) >= stale_error_minutes)
    failed_jobs.sort(
        key=lambda x: (
            -float(x.get("stale_minutes", 0.0) or 0.0),
            -int(x.get("consecutive_errors", 0) or 0),
            str(x.get("name", "")),
        )
    )
    max_report_jobs = max(1, _safe_int(monitor.get("max_report_jobs"), 8))

    state["workflow_job_status"] = current_status
    state["workflow_monitor_meta"] = {
        "updated_at": now_iso(),
        "jobs_file": str(jobs_file),
        "jobs_total": jobs_total,
        "jobs_enabled": jobs_enabled,
        "failed_count": len(failed_jobs),
        "ignored_failed_count": ignored_failed,
    }

    if not jobs_file.exists():
        errors.append(f"jobs_file_missing:{jobs_file}")

    return {
        "enabled": True,
        "jobs_file": str(jobs_file),
        "jobs_total": jobs_total,
        "jobs_enabled": jobs_enabled,
        "failed_count": len(failed_jobs),
        "ignored_failed_count": ignored_failed,
        "stale_failed_count": stale_failed_count,
        "stale_error_minutes": stale_error_minutes,
        "new_failed_count": new_failed,
        "recovered_count": recovered,
        "failed_jobs": failed_jobs[:max_report_jobs],
        "errors": errors,
    }


def collect_token_usage_summary(cfg: dict[str, Any]) -> dict[str, Any]:
    monitor = cfg.get("token_monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    if not bool(monitor.get("enabled", True)):
        return {
            "enabled": False,
            "db_path": "",
            "window_hours": 0,
            "rows": 0,
            "total_tokens": 0,
            "total_tokens_m": 0.0,
            "cost_estimate": 0.0,
            "by_agent": [],
            "errors": [],
        }

    db_path = Path(
        str(monitor.get("task_center_db", "")).strip()
        or str(Path.home() / ".openclaw" / "ops" / "task-center" / "task_center.db")
    ).expanduser()
    window_hours = max(1, _safe_int(monitor.get("window_hours"), 24))
    top_agents = max(1, _safe_int(monitor.get("top_agents"), 5))

    result = {
        "enabled": True,
        "db_path": str(db_path),
        "source": "task_center_db",
        "window_hours": window_hours,
        "rows": 0,
        "total_tokens": 0,
        "total_tokens_m": 0.0,
        "cost_estimate": 0.0,
        "by_agent": [],
        "errors": [],
    }

    db_error = ""
    db_rows = 0

    if db_path.exists():
        start_iso = (datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)).replace(microsecond=0).isoformat()
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            totals = conn.execute(
                """
                SELECT
                  COUNT(1) AS rows,
                  COALESCE(SUM(total_tokens), 0) AS total_tokens,
                  COALESCE(SUM(cost_estimate), 0.0) AS total_cost
                FROM token_usage
                WHERE ts >= ?
                """,
                (start_iso,),
            ).fetchone()
            by_agent_rows = conn.execute(
                """
                SELECT
                  agent_id,
                  COALESCE(SUM(total_tokens), 0) AS total_tokens,
                  COALESCE(SUM(cost_estimate), 0.0) AS total_cost
                FROM token_usage
                WHERE ts >= ?
                GROUP BY agent_id
                ORDER BY total_tokens DESC
                LIMIT ?
                """,
                (start_iso, top_agents),
            ).fetchall()
            db_rows = int(totals["rows"] or 0) if totals else 0
            total_tokens = int(totals["total_tokens"] or 0) if totals else 0
            total_cost = float(totals["total_cost"] or 0.0) if totals else 0.0
            result["rows"] = db_rows
            result["total_tokens"] = total_tokens
            result["total_tokens_m"] = round(total_tokens / 1_000_000.0, 6)
            result["cost_estimate"] = round(total_cost, 6)
            result["by_agent"] = [
                {
                    "agent_id": str(row["agent_id"]),
                    "total_tokens": int(row["total_tokens"] or 0),
                    "total_tokens_m": round(int(row["total_tokens"] or 0) / 1_000_000.0, 6),
                    "cost_estimate": round(float(row["total_cost"] or 0.0), 6),
                }
                for row in by_agent_rows
            ]
        except Exception as exc:
            db_error = f"token_usage_query_failed:{exc}"
        finally:
            try:
                conn.close()
            except Exception:
                pass
    else:
        db_error = f"task_center_db_missing:{db_path}"

    # Fallback: if task_center has no token rows, aggregate usage from cron run logs.
    if db_rows <= 0:
        fallback = _collect_token_usage_from_cron_runs(
            monitor,
            window_hours=window_hours,
            top_agents=top_agents,
        )
        result["cron_runs_dir"] = str(fallback.get("runs_dir", ""))
        cron_rows = int(fallback.get("rows", 0) or 0)
        if cron_rows > 0:
            total_tokens = int(fallback.get("total_tokens", 0) or 0)
            total_cost = float(fallback.get("cost_estimate", 0.0) or 0.0)
            result["source"] = "cron_runs"
            result["rows"] = cron_rows
            result["total_tokens"] = total_tokens
            result["total_tokens_m"] = round(total_tokens / 1_000_000.0, 6)
            result["cost_estimate"] = round(total_cost, 6)
            result["by_agent"] = fallback.get("by_agent", [])
        else:
            if db_error:
                result["errors"].append(db_error)
            result["errors"].extend(list(fallback.get("errors", [])))
    elif db_error:
        result["errors"].append(db_error)

    return result


def sorted_open_issues(state: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    issues = state.get("issues", {})
    if not isinstance(issues, dict):
        return []
    rows = [x for x in issues.values() if isinstance(x, dict) and str(x.get("status", "")).strip() == "open"]
    rows.sort(
        key=lambda x: (
            0 if str(x.get("severity", "")).strip() == "high" else 1,
            -int(x.get("occurrences", 0) or 0),
            str(x.get("first_seen", "")),
        )
    )
    return rows[: max(1, int(limit))]


def route_assignee(text: str, dispatch_cfg: dict[str, Any], routing_rules: dict[str, Any]) -> tuple[str, str]:
    norm = str(text or "").strip().lower()
    rules = routing_rules.get("assignee_rules", [])
    if isinstance(rules, list):
        for item in rules:
            if not isinstance(item, dict):
                continue
            assignee = str(item.get("assignee", "")).strip()
            keywords = item.get("keywords", [])
            if not assignee or not isinstance(keywords, list):
                continue
            for kw in keywords:
                key = str(kw).strip().lower()
                if key and key in norm:
                    return assignee, key
    fallback = (
        str(dispatch_cfg.get("default_assignee", "")).strip()
        or str(routing_rules.get("default_assignee", "")).strip()
        or "coordinator"
    )
    return fallback, ""


def build_risk_signature(
    *,
    state: dict[str, Any],
    workflow_health: dict[str, Any],
    risk_reasons: list[str],
) -> str:
    issues = state.get("issues", {})
    open_high_keys: list[str] = []
    if isinstance(issues, dict):
        for key, rec in issues.items():
            if not isinstance(rec, dict):
                continue
            if str(rec.get("status", "")) != "open":
                continue
            if str(rec.get("severity", "")) != "high":
                continue
            open_high_keys.append(str(key))
    open_high_keys = sorted(set(open_high_keys))[:16]
    failed_jobs = workflow_health.get("failed_jobs", [])
    failed_job_ids: list[str] = []
    if isinstance(failed_jobs, list):
        for row in failed_jobs:
            if not isinstance(row, dict):
                continue
            jid = str(row.get("id", "")).strip()
            if jid:
                failed_job_ids.append(jid)
    payload = {
        "risk_labels": sorted({compact_reason(x) for x in risk_reasons if str(x).strip()}),
        "open_high_keys": open_high_keys,
        "workflow_failed_jobs": sorted(set(failed_job_ids))[:16],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_routing_rules(dispatch_cfg: dict[str, Any]) -> dict[str, Any]:
    routing_file = Path(str(dispatch_cfg.get("routing_file", "")).strip()).expanduser()
    data = load_json(routing_file, {})
    if not isinstance(data, dict):
        data = {}
    return data


def build_issue_todo_item(
    *,
    issue: dict[str, Any],
    mode: str,
    assignee: str,
    route_hit: str,
) -> dict[str, Any]:
    issue_key = str(issue.get("key", "")).strip() or hashlib.sha1(
        f"{issue.get('source', '')}|{issue.get('title', '')}".encode("utf-8")
    ).hexdigest()[:20]
    severity = str(issue.get("severity", "medium")).strip().lower()
    priority = "P0" if severity == "high" else "P2"
    risk = "high" if severity == "high" else "low"
    first_seen = iso_to_local_text(issue.get("first_seen"))
    last_seen = iso_to_local_text(issue.get("last_seen"))
    line = (
        f"- [ ] [OPS][{priority}][risk={risk}] key=issue:{issue_key} assignee={assignee} "
        f"mode={mode} occurrences={int(issue.get('occurrences', 0) or 0)} "
        f"first_seen={first_seen} last_seen={last_seen} "
        f"source={str(issue.get('source', '')).strip()} "
        f"evidence={str(issue.get('title', '')).strip()[:160]}"
    )
    return {
        "handoff_key": f"issue:{issue_key}",
        "entity": "issue",
        "priority": priority,
        "risk_level": risk,
        "assignee": assignee,
        "route_hit": route_hit,
        "line": line,
    }


def build_workflow_todo_item(
    *,
    job: dict[str, Any],
    mode: str,
    assignee: str,
    route_hit: str,
) -> dict[str, Any]:
    job_id = str(job.get("id", "")).strip() or "unknown"
    line = (
        f"- [ ] [OPS][P0][risk=high] key=workflow_job:{job_id} assignee={assignee} mode={mode} "
        f"job_name={str(job.get('name', '')).strip()} status={str(job.get('last_status', '')).strip()} "
        f"consecutive={int(job.get('consecutive_errors', 0) or 0)} "
        f"stale_min={float(job.get('stale_minutes', 0.0) or 0.0)} "
        f"last_error={str(job.get('last_error', '')).strip()[:160]}"
    )
    return {
        "handoff_key": f"workflow_job:{job_id}",
        "entity": "workflow_job",
        "priority": "P0",
        "risk_level": "high",
        "assignee": assignee,
        "route_hit": route_hit,
        "line": line,
    }


def handoff_incidents_to_todo(
    *,
    cfg: dict[str, Any],
    state: dict[str, Any],
    mode: str,
    workflow_health: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "enabled": False,
        "mode": "todo_only",
        "todo_file": "",
        "high_risk_direct_human": False,
        "todo_new": 0,
        "todo_items": [],
        "active_high_risk_items": 0,
        "errors": [],
    }
    handoff_cfg = cfg.get("incident_handoff")
    if not isinstance(handoff_cfg, dict):
        handoff_cfg = {}
    if not bool(handoff_cfg.get("enabled", False)):
        return summary
    summary["enabled"] = True
    summary["mode"] = str(handoff_cfg.get("mode", "todo_only")).strip() or "todo_only"
    if summary["mode"] != "todo_only":
        summary["errors"].append(f"unsupported_handoff_mode:{summary['mode']}")
        return summary

    todo_file = Path(
        str(handoff_cfg.get("todo_file", "")).strip()
        or str(Path.home() / ".openclaw" / "workspace-coordinator" / "TODO.md")
    ).expanduser()
    summary["todo_file"] = str(todo_file)
    routing_rules = load_routing_rules(handoff_cfg)
    write_medium = parse_bool(handoff_cfg.get("write_medium_risk_to_todo"), False)
    high_risk_direct_human = parse_bool(handoff_cfg.get("high_risk_direct_human"), True)
    summary["high_risk_direct_human"] = high_risk_direct_human

    max_total = max(1, int(handoff_cfg.get("max_handoff_per_run", 6) or 6))
    issue_limit = max(1, int(handoff_cfg.get("max_issue_items_per_run", 4) or 4))
    job_limit = max(0, int(handoff_cfg.get("max_workflow_jobs_per_run", 2) or 2))

    candidates: list[dict[str, Any]] = []
    open_items = sorted_open_issues(state, limit=issue_limit)
    for issue in open_items:
        severity = str(issue.get("severity", "")).strip().lower()
        if severity != "high" and not write_medium:
            continue
        text = f"{issue.get('title', '')}\n{issue.get('source', '')}"
        assignee, route_hit = route_assignee(text, handoff_cfg, routing_rules)
        if high_risk_direct_human and severity == "high":
            assignee = "coordinator"
            route_hit = "high_risk_direct_human"
        candidates.append(build_issue_todo_item(issue=issue, mode=mode, assignee=assignee, route_hit=route_hit))

    failed_jobs = workflow_health.get("failed_jobs", [])
    if isinstance(failed_jobs, list):
        for job in failed_jobs[:job_limit]:
            if not isinstance(job, dict):
                continue
            text = f"{job.get('name', '')}\n{job.get('last_error', '')}\n{job.get('id', '')}"
            assignee, route_hit = route_assignee(text, handoff_cfg, routing_rules)
            if high_risk_direct_human:
                assignee = "coordinator"
                route_hit = "high_risk_direct_human"
            candidates.append(build_workflow_todo_item(job=job, mode=mode, assignee=assignee, route_hit=route_hit))

    active_keys = {str(x.get("handoff_key", "")).strip() for x in candidates if str(x.get("handoff_key", "")).strip()}
    handoff_state = state.setdefault("incident_handoff", {})
    if not isinstance(handoff_state, dict):
        handoff_state = {}
        state["incident_handoff"] = handoff_state
    sent_keys = handoff_state.get("sent_keys")
    if not isinstance(sent_keys, dict):
        sent_keys = {}
    sent_keys = {str(k): str(v) for k, v in sent_keys.items() if str(k) in active_keys}

    pending_keys: list[str] = []
    new_lines: list[str] = []
    now_text = now().strftime("%Y-%m-%d %H:%M:%S UTC+8")
    for item in candidates[:max_total]:
        key = str(item.get("handoff_key", "")).strip()
        if not key:
            continue
        pending_keys.append(key)
        if key in sent_keys:
            continue
        new_lines.append(f"{item.get('line')} | detected_at={now_text}")
        sent_keys[key] = now_iso()
        summary["todo_items"].append(
            {
                "handoff_key": key,
                "entity": item.get("entity"),
                "priority": item.get("priority"),
                "risk_level": item.get("risk_level"),
                "assignee": item.get("assignee") or "coordinator",
            }
        )

    if new_lines:
        try:
            append_payload = "\n## OPS Incident Inbox\n" + "".join(f"{line.rstrip()}\n" for line in new_lines)
            append_text_atomic(
                todo_file,
                append_payload,
                create_with="# TODO\n\n",
                file_mode=0o640,
                dir_mode=0o750,
            )
        except Exception as exc:
            summary["errors"].append(f"todo_write_failed:{todo_file}:{exc}")
            for item in summary["todo_items"]:
                sent_keys.pop(str(item.get("handoff_key", "")), None)
            summary["todo_items"] = []
        else:
            summary["todo_new"] = len(new_lines)

    summary["active_high_risk_items"] = sum(
        1 for item in candidates if str(item.get("risk_level", "")).strip().lower() == "high"
    )
    handoff_state["sent_keys"] = sent_keys
    handoff_state["updated_at"] = now_iso()
    handoff_state["pending_keys"] = pending_keys[:100]
    return summary


def resolve_task_center_db_path(cfg: dict[str, Any], home: Path) -> Path:
    follow_up_cfg = cfg.get("workflow_follow_up") if isinstance(cfg.get("workflow_follow_up"), dict) else {}
    token_cfg = cfg.get("token_monitor") if isinstance(cfg.get("token_monitor"), dict) else {}
    raw = str(
        follow_up_cfg.get("task_center_db")
        or token_cfg.get("task_center_db")
        or (home / ".openclaw" / "ops" / "task-center" / "task_center.db")
    ).strip()
    return Path(raw).expanduser()


def workflow_follow_up_active_key(job: dict[str, Any]) -> str:
    job_id = str(job.get("id", "")).strip() or "unknown"
    error_text = str(job.get("last_error", "")).strip() or job_id
    error_sig = hashlib.sha1(normalize_line(error_text).encode("utf-8")).hexdigest()[:12]
    return f"workflow_job:{job_id}:{error_sig}"


def create_workflow_follow_up_tasks(
    *,
    cfg: dict[str, Any],
    state: dict[str, Any],
    db_path: Path,
    actor: str,
    run_file: Path,
    run_task_id: str,
    mode: str,
    started_at: str,
    workflow_health: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "enabled": False,
        "db": str(db_path),
        "created_count": 0,
        "existing_count": 0,
        "tasks": [],
        "errors": [],
    }
    if str(mode).strip().lower() == "daily":
        return summary

    follow_up_cfg = cfg.get("workflow_follow_up")
    if not isinstance(follow_up_cfg, dict):
        follow_up_cfg = {}
    if not bool(follow_up_cfg.get("enabled", True)):
        return summary
    summary["enabled"] = True

    if not db_path.exists():
        summary["errors"].append(f"task_center_db_missing:{db_path}")
        return summary

    failed_jobs = workflow_health.get("failed_jobs", [])
    if not isinstance(failed_jobs, list) or not failed_jobs:
        return summary

    max_tasks = max(1, int(follow_up_cfg.get("max_tasks_per_run", 2) or 2))
    default_assignee = (
        str(follow_up_cfg.get("default_assignee", "optimization-agent")).strip()
        or "optimization-agent"
    )
    task_type = str(follow_up_cfg.get("task_type", "ops_workflow_repair")).strip() or "ops_workflow_repair"
    pool = str(follow_up_cfg.get("pool", "jobs")).strip().lower() or "jobs"
    priority = str(follow_up_cfg.get("priority", "high")).strip().lower() or "high"
    risk_level = str(follow_up_cfg.get("risk_level", "low")).strip().lower() or "low"
    source_name = str(follow_up_cfg.get("source", "")).strip() or str(actor or "ops-agent/ops-cron-runner")

    active_keys = {
        workflow_follow_up_active_key(job)
        for job in failed_jobs
        if isinstance(job, dict) and str(job.get("id", "")).strip()
    }
    follow_up_state = state.setdefault("workflow_follow_up", {})
    if not isinstance(follow_up_state, dict):
        follow_up_state = {}
        state["workflow_follow_up"] = follow_up_state
    sent_keys_raw = follow_up_state.get("sent_keys")
    if not isinstance(sent_keys_raw, dict):
        sent_keys_raw = {}
    sent_keys = {}
    for raw_key, raw_value in sent_keys_raw.items():
        key = str(raw_key).strip()
        if key not in active_keys:
            continue
        if isinstance(raw_value, dict):
            sent_keys[key] = {
                "task_id": str(raw_value.get("task_id", "")).strip(),
                "sent_at": str(raw_value.get("sent_at", "")).strip(),
            }
        else:
            sent_keys[key] = {"task_id": str(raw_value).strip(), "sent_at": ""}

    for job in failed_jobs[:max_tasks]:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue
        active_key = workflow_follow_up_active_key(job)
        if active_key in sent_keys:
            continue

        job_name = str(job.get("name", "")).strip() or job_id
        last_status = str(job.get("last_status", "")).strip() or "error"
        last_error = str(job.get("last_error", "")).strip() or "workflow_failed"
        last_run_at = str(job.get("last_run_at", "")).strip() or str(started_at or now_iso())
        seen_dt = parse_iso(last_run_at) or parse_iso(started_at) or now()
        seen_token = seen_dt.astimezone(TZ).strftime("%Y%m%d%H%M%S")
        issue_sig = hashlib.sha1(f"{job_id}|{normalize_line(last_error)}|{seen_token}".encode("utf-8")).hexdigest()[:10]
        task_id = f"todo-ops-workflow-repair-{safe_slug(job_id, 24)}-{issue_sig}"
        acceptance = (
            "定位失败根因，完成最小修复，并通过重跑或状态核验确认该工作流 lastStatus 恢复为非 error/failed；"
            "若暂时无法自动修复，必须留下已验证的阻塞原因与后续建议。"
        )
        requirement = "\n".join(
            [
                f"ops workflow monitor task: {run_task_id or '-'}",
                f"workflow_job_id: {job_id}",
                f"workflow_job_name: {job_name}",
                f"last_status: {last_status}",
                f"last_run_at: {last_run_at}",
                f"consecutive_errors: {int(job.get('consecutive_errors', 0) or 0)}",
                f"stale_minutes: {float(job.get('stale_minutes', 0.0) or 0.0)}",
                f"last_error: {last_error}",
                f"evidence_file: {run_file}",
                "",
                "需要闭环处理，而不是只聊天告警。",
                "1. 检查 ~/.openclaw/cron/jobs.json 中该工作流的 state、payload 与最近错误。",
                "2. 复现失败命令或最小失败路径，定位根因。",
                "3. 在最小范围内修复脚本、配置、权限、路径或上下文问题。",
                "4. 修复后重新执行对应工作流，或验证其 lastStatus 已恢复为非 error/failed。",
            ]
        )
        context_payload = {
            "problem": f"workflow {job_name} failed: {last_error}",
            "location": f"~/.openclaw/cron/jobs.json job_id={job_id}",
            "first_seen_at": last_run_at,
            "impact": f"Scheduled workflow {job_name} is failing and has not recovered automatically.",
            "evidence": str(run_file),
            "current_state": last_error,
            "expected_state": f"Workflow {job_name} runs successfully and lastStatus is no longer error/failed.",
            "operation_path": f"ops_cron_runner::{job_id}",
            "reproduction_steps": f"Inspect {job_id} in ~/.openclaw/cron/jobs.json and rerun the underlying workflow command or script.",
            "scope": f"workflow job {job_name}",
            "constraints": "Prefer minimal, reversible fixes. Do not modify unrelated cron jobs or vendor runtime files.",
            "acceptance_criteria": acceptance,
            "full_background": requirement,
        }
        create_args = [
            "create-task",
            "--task-id",
            task_id,
            "--task-type",
            task_type,
            "--reason",
            f"[OPS_WORKFLOW] {job_name} failed",
            "--source",
            source_name,
            "--request-source",
            "ai",
            "--priority",
            priority,
            "--risk-level",
            risk_level,
            "--pool",
            pool,
            "--assignee",
            default_assignee,
            "--need-human-confirm",
            "false",
            "--human-confirmed",
            "true",
            "--context-json",
            json.dumps(context_payload, ensure_ascii=False),
            "--requirement",
            requirement,
            "--result-output",
            f"Workflow {job_name} recovers to non-error status, or task output clearly records the blocking reason and next action.",
            "--acceptance",
            acceptance,
            "--observable-outputs",
            f"run_file={run_file},workflow_job_id={job_id},workflow_job_name={job_name}",
            "--acceptance-thresholds",
            "Re-run evidence or recovered status is attached to the task report.",
            "--scheduled-at",
            now_iso(),
            "--actor",
            str(actor or "ops-agent/ops-cron-runner"),
        ]
        extend_create_task_args_with_constraints(create_args, default_assignee)
        ok, payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
        if ok:
            summary["created_count"] += 1
            sent_keys[active_key] = {"task_id": task_id, "sent_at": now_iso()}
            summary["tasks"].append(
                {
                    "task_id": task_id,
                    "assignee": default_assignee,
                    "status": "created",
                    "workflow_job_id": job_id,
                    "workflow_job_name": job_name,
                }
            )
            continue
        if "task_id already exists" in err:
            summary["existing_count"] += 1
            sent_keys[active_key] = {"task_id": task_id, "sent_at": now_iso()}
            summary["tasks"].append(
                {
                    "task_id": task_id,
                    "assignee": default_assignee,
                    "status": "existing",
                    "workflow_job_id": job_id,
                    "workflow_job_name": job_name,
                }
            )
            continue
        payload_error = str(payload.get("error", "")).strip() if isinstance(payload, dict) else ""
        summary["errors"].append(f"{job_id}:{err or payload_error or 'create_follow_up_task_failed'}")

    follow_up_state["sent_keys"] = sent_keys
    follow_up_state["updated_at"] = now_iso()
    follow_up_state["active_keys"] = sorted(active_keys)[:100]
    return summary


def append_workflow_follow_up_output(output: str, summary: dict[str, Any]) -> str:
    if str(output or "").strip() == "NO_REPLY":
        return output
    extra_lines = build_follow_up_progress_lines(summary)
    if not extra_lines:
        return output
    lines = [str(output).rstrip(), *extra_lines]
    return "\n".join(lines)


@dataclass(slots=True)
class RunResult:
    notify: bool
    output: str
    record: dict[str, Any]


def sender_identity_for_mode(mode: str) -> str:
    return f"{DEFAULT_SENDER_PREFIX}:{mode}"


def run_scan(
    mode: str,
    cfg: dict[str, Any],
    state: dict[str, Any],
    task_id: str,
    daily_major_only: bool,
    force_fallback: bool,
    normal_log_mode_override: str,
) -> RunResult:
    run_started_at = now()
    state.setdefault("runs", {"incremental": 0, "full": 0, "daily": 0})
    state["runs"][mode] = int(state["runs"].get(mode, 0)) + 1
    run_id = uuid.uuid4().hex[:12]
    service_snapshot, service_error = collect_services(cfg)
    runtime_health = collect_runtime_project_health(cfg, service_snapshot=service_snapshot)
    log_files = discover_logs(cfg, list(service_snapshot.keys()), extra_paths=list(runtime_health.get("log_paths", [])))

    checkpoints = state.setdefault("checkpoints", {})
    findings: list[dict[str, Any]] = []
    scan_errors: list[str] = []
    read_bytes = 0
    fallback_used = False
    fallback_reasons: list[str] = []

    full_mode = mode == "full"
    if mode == "incremental":
        backstop = max(0, int(cfg.get("incremental_full_backstop_runs", 0)))
        run_count = int(state["runs"].get("incremental", 0))
        if force_fallback:
            fallback_used = True
            fallback_reasons.append("force_fallback")
            full_mode = True
        elif backstop > 0 and run_count % backstop == 0:
            fallback_used = True
            fallback_reasons.append("periodic_full_backstop")
            full_mode = True

    max_lines = max(10, int(cfg.get("max_lines_per_file", 2000)))
    for path in log_files:
        key = str(path)
        prior = checkpoints.get(key, {}) if isinstance(checkpoints.get(key), dict) else {}
        try:
            if full_mode:
                text, cp = read_tail(path, int(cfg.get("full_scan_tail_bytes_per_file", 1048576)))
            else:
                text, cp, fallback = read_incremental(path, prior, int(cfg.get("incremental_max_bytes_per_file", 262144)))
                if fallback:
                    fallback_reasons.append(f"checkpoint_reset:{path.name}")
            checkpoints[key] = cp
            read_bytes += int(cp.get("bytes_read", 0))
            findings.extend(extract_findings(path, text, max_lines))
        except Exception as exc:
            scan_errors.append(f"{path}:{exc}")

    if mode == "incremental" and scan_errors and bool(cfg.get("fallback_full_on_incremental_error", True)):
        fallback_used = True
        fallback_reasons.append("incremental_scan_error")
        findings = []
        scan_errors = []
        full_mode = True
        for path in log_files:
            key = str(path)
            try:
                text, cp = read_tail(path, int(cfg.get("full_scan_tail_bytes_per_file", 1048576)))
                checkpoints[key] = cp
                read_bytes += int(cp.get("bytes_read", 0))
                findings.extend(extract_findings(path, text, max_lines))
            except Exception as exc:
                scan_errors.append(f"{path}:{exc}")

    state["known_logs"] = [str(p) for p in log_files]
    if full_mode:
        state["last_full_scan_at"] = now_iso()

    issue_stats = update_issues(
        state,
        findings=findings,
        resolve_after=int(cfg.get("auto_resolve_after_missed_runs", 2)),
        keep_days=int(cfg.get("keep_resolved_days", 7)),
    )

    prev_services = state.get("services", {})
    prev_services = prev_services if isinstance(prev_services, dict) else {}
    added = sorted(set(service_snapshot) - set(prev_services))
    removed = sorted(set(prev_services) - set(service_snapshot))
    changed = sorted(x for x in set(service_snapshot) & set(prev_services) if service_snapshot[x] != prev_services[x])
    state["services"] = service_snapshot
    prev_runtime = state.get("runtime_monitor", {})
    prev_runtime = prev_runtime if isinstance(prev_runtime, dict) else {}
    prev_runtime_snapshot = prev_runtime.get("item_status", {})
    prev_runtime_snapshot = prev_runtime_snapshot if isinstance(prev_runtime_snapshot, dict) else {}
    runtime_snapshot = runtime_health.get("snapshot", {})
    runtime_snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
    runtime_changed_count = 0
    for key in set(prev_runtime_snapshot) | set(runtime_snapshot):
        if str(prev_runtime_snapshot.get(key, "")) != str(runtime_snapshot.get(key, "")):
            runtime_changed_count += 1
    state["runtime_monitor"] = {
        "updated_at": now_iso(),
        "item_status": runtime_snapshot,
        "summary": runtime_health.get("summary", {}),
        "missing_required": runtime_health.get("missing_required", []),
    }

    metrics = collect_system_metrics(cfg)
    workflow_health = collect_workflow_health(cfg, state)
    token_usage_summary = collect_token_usage_summary(cfg)
    log_mode = resolve_log_mode(mode, cfg, normal_log_mode_override)
    sender_identity = sender_identity_for_mode(mode)

    risk_reasons: list[str] = []
    if issue_stats["new_high"] > 0:
        risk_reasons.append(f"new_high_issue={issue_stats['new_high']}")
    if issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"reopened_high_issue={issue_stats['reopened_high']}")
    if scan_errors:
        risk_reasons.append(f"scan_error={len(scan_errors)}")
    if (metrics.get("anomalies") or []):
        risk_reasons.append(f"system_anomaly={len(metrics.get('anomalies', []))}")
    if service_error and prev_services:
        risk_reasons.append("service_monitor_error")
    runtime_missing_count = int(((runtime_health.get("summary") or {}).get("required_missing_count", 0) or 0))
    if runtime_missing_count > 0:
        risk_reasons.append(f"runtime_process_missing={runtime_missing_count}")
    if runtime_health.get("errors"):
        risk_reasons.append(f"runtime_monitor_error={len(runtime_health.get('errors') or [])}")
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error={int(workflow_health.get('failed_count', 0) or 0)}")
    if int(workflow_health.get("stale_failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error_stale={int(workflow_health.get('stale_failed_count', 0) or 0)}")
    if workflow_health.get("errors"):
        risk_reasons.append(f"workflow_monitor_error={len(workflow_health.get('errors') or [])}")
    if token_usage_summary.get("errors"):
        risk_reasons.append(f"token_monitor_error={len(token_usage_summary.get('errors') or [])}")
    app_usage = metrics.get("app_usage") if isinstance(metrics.get("app_usage"), dict) else {}
    if app_usage.get("errors"):
        risk_reasons.append(f"app_usage_monitor_error={len(app_usage.get('errors') or [])}")

    change_reasons: list[str] = []
    if issue_stats["new"] > 0:
        change_reasons.append(f"new_issue={issue_stats['new']}")
    if issue_stats["reopened"] > 0:
        change_reasons.append(f"reopened_issue={issue_stats['reopened']}")
    if issue_stats["resolved"] > 0:
        change_reasons.append(f"resolved_issue={issue_stats['resolved']}")
    if added or removed or changed:
        change_reasons.append(f"service_change=+{len(added)}/-{len(removed)}/~{len(changed)}")
    if runtime_changed_count > 0:
        change_reasons.append(f"runtime_status_change={runtime_changed_count}")
    if fallback_used:
        change_reasons.append("fallback_full_scan")
    if int(workflow_health.get("new_failed_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_new_failed={int(workflow_health.get('new_failed_count', 0) or 0)}")
    if int(workflow_health.get("recovered_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_recovered={int(workflow_health.get('recovered_count', 0) or 0)}")

    handoff_summary = handoff_incidents_to_todo(
        cfg=cfg,
        state=state,
        mode=mode,
        workflow_health=workflow_health,
    )
    if int(handoff_summary.get("todo_new", 0) or 0) > 0:
        change_reasons.append(f"todo_handoff_new={int(handoff_summary.get('todo_new', 0) or 0)}")
    if handoff_summary.get("errors"):
        risk_reasons.append(f"handoff_error={len(handoff_summary.get('errors') or [])}")

    major_reasons = [*risk_reasons, *change_reasons]
    notify_policy = cfg.get("notify_policy")
    if not isinstance(notify_policy, dict):
        notify_policy = {}
    errors_only_notify = parse_bool(cfg.get("errors_only_notify"), True)
    silent_notify_on_change = parse_bool(notify_policy.get("silent_notify_on_change"), False)
    chat_notify_on_change = parse_bool(notify_policy.get("chat_notify_on_change"), False)
    chat_notify_on_no_change = parse_bool(notify_policy.get("chat_notify_on_no_change"), False)
    risk_repeat_cooldown_minutes = max(1, int(notify_policy.get("risk_repeat_cooldown_minutes", 60) or 60))

    risk_signature = ""
    risk_notify_suppressed = False
    risk_notify_suppressed_reason = ""
    if risk_reasons:
        risk_signature = build_risk_signature(
            state=state,
            workflow_health=workflow_health,
            risk_reasons=risk_reasons,
        )
        notify_state = state.get("notify_state", {})
        if not isinstance(notify_state, dict):
            notify_state = {}
        last_signature = str(notify_state.get(f"risk_signature_{mode}", "")).strip()
        last_notified = parse_iso(notify_state.get(f"risk_notified_at_{mode}"))
        if last_signature and risk_signature == last_signature and last_notified:
            elapsed = now() - last_notified.astimezone(TZ)
            if elapsed < timedelta(minutes=risk_repeat_cooldown_minutes):
                risk_notify_suppressed = True
                risk_notify_suppressed_reason = (
                    f"risk_repeat_within_cooldown:{risk_repeat_cooldown_minutes}m"
                )
        if not risk_notify_suppressed:
            notify_state[f"risk_signature_{mode}"] = risk_signature
            notify_state[f"risk_notified_at_{mode}"] = now_iso()
            state["notify_state"] = notify_state

    notify = bool(risk_reasons) and (not risk_notify_suppressed)
    if (not notify) and (not errors_only_notify) and change_reasons:
        if log_mode == "chat":
            notify = chat_notify_on_change
        else:
            notify = silent_notify_on_change
    elif (not notify) and (not errors_only_notify) and log_mode == "chat":
        notify = chat_notify_on_no_change

    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    job_name = str(task_id or "").split(":", 1)[-1] if ":" in str(task_id or "") else f"ops_{mode}"
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    open_issue_rows = sorted_open_issues(state, limit=3)
    workflow_failed_rows = list(workflow_health.get("failed_jobs", [])) if isinstance(workflow_health.get("failed_jobs"), list) else []
    shared_alert_suppressed = False
    shared_alert_suppressed_reason = ""
    shared_alert_signature = ""
    shared_alert_tokens: list[str] = []
    workflow_risk_labels = {compact_reason(x) for x in risk_reasons if str(x).strip()}
    workflow_only_risk = bool(workflow_failed_rows) and workflow_risk_labels.issubset(
        {"workflow_job_error", "workflow_job_error_stale"}
    )
    if notify and workflow_only_risk:
        shared_alert_tokens = workflow_tokens_from_job_ids(item.get("id", "") for item in workflow_failed_rows)
        shared_alert_signature = build_workflow_failure_signature(shared_alert_tokens)
        if shared_alert_signature:
            shared_state_path = resolve_shared_alert_state_path(notify_policy.get("shared_alert_state_file", ""))
            shared_state = load_dedupe_state(shared_state_path)
            shared_alert_suppressed, shared_alert_suppressed_reason = check_and_record_signature(
                shared_state,
                bucket=WORKFLOW_FAILURE_BUCKET,
                signature=shared_alert_signature,
                now_text=now_iso(),
                cooldown_minutes=risk_repeat_cooldown_minutes,
                meta={
                    "source": "ops_cron_runner",
                    "mode": mode,
                    "task_id": task_id,
                    "tokens": list(shared_alert_tokens),
                },
            )
            save_dedupe_state(shared_state_path, shared_state)
            if shared_alert_suppressed:
                notify = False

    output = "NO_REPLY"
    if notify:
        event = build_ops_scan_event(
            {
                "task_id": task_id,
                "mode": mode,
                "time": f"{now().strftime('%Y-%m-%d %H:%M:%S')} UTC+8",
                "run_id": run_id,
                "risk_reasons": risk_reasons,
                "runtime_health": runtime_health,
                "workflow_health": workflow_health,
                "workflow_follow_up_summary": {},
                "handoff_summary": handoff_summary,
                "scan_errors": scan_errors,
                "risk_notify_suppressed_reason": risk_notify_suppressed_reason if risk_notify_suppressed else "",
            }
        )
        output = render_human_view(event["views"]["human"])
        if open_issue_rows:
            lines = [str(output).rstrip(), "- 关键异常:"]
            for idx, item in enumerate(open_issue_rows[:3], start=1):
                lines.append(
                    f"  {idx}. [{item.get('severity')}] {str(item.get('title', ''))[:120]} "
                    f"(最近: {iso_to_local_text(item.get('last_seen'))})"
                )
            output = "\n".join(lines)
        if handoff_summary.get("errors"):
            lines = [str(output).rstrip(), "- 交接异常:"]
            for idx, err in enumerate(handoff_summary.get("errors", [])[:3], start=1):
                lines.append(f"  {idx}. {str(err)[:180]}")
            output = "\n".join(lines)


    record = {
        "run_id": run_id,
        "sender_identity": sender_identity,
        "task_id": task_id,
        "mode": mode,
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": log_mode,
        "errors_only_notify": bool(errors_only_notify),
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "major_reasons": major_reasons,
        "job_name": job_name,
        "risk_level": risk_level,
        "priority": priority,
        "run_duration_ms": run_duration_ms,
        "risk_signature": risk_signature,
        "risk_notify_suppressed": risk_notify_suppressed,
        "risk_notify_suppressed_reason": risk_notify_suppressed_reason,
        "shared_alert_signature": shared_alert_signature,
        "shared_alert_tokens": shared_alert_tokens,
        "shared_alert_suppressed": shared_alert_suppressed,
        "shared_alert_suppressed_reason": shared_alert_suppressed_reason,
        "full_mode": full_mode,
        "fallback_used": fallback_used,
        "fallback_reasons": sorted(set(fallback_reasons)),
        "logs_scanned": len(log_files),
        "bytes_read": read_bytes,
        "findings": len(findings),
        "scan_errors": scan_errors,
        "issue_stats": issue_stats,
        "service_delta": {
            "added": added[:30],
            "removed": removed[:30],
            "changed": changed[:30],
            "service_error": service_error or "",
        },
        "metrics": metrics,
        "runtime_health": runtime_health,
        "workflow_health": workflow_health,
        "token_usage": token_usage_summary,
        "handoff_summary": handoff_summary,
        "top_open_issues": open_issue_rows,
        "cost_estimate": float(token_usage_summary.get("cost_estimate", 0.0) or 0.0),
    }
    return RunResult(notify=notify, output=output, record=record)


def build_daily_report(
    history_dir: Path,
    cfg: dict[str, Any],
    state: dict[str, Any],
    major_only: bool,
    task_id: str,
    normal_log_mode: str,
) -> RunResult:
    run_started_at = now()
    window_start = now() - timedelta(hours=24)
    records: list[dict[str, Any]] = []
    for path in sorted(history_dir.glob("*.json")):
        data = load_json(path, {})
        if not isinstance(data, dict):
            continue
        stamp = str(data.get("time", "")).strip()
        if not stamp:
            continue
        try:
            ts = datetime.fromisoformat(stamp)
        except Exception:
            continue
        if ts >= window_start:
            records.append(data)

    total = len(records)
    major = sum(1 for x in records if bool(x.get("notify")))
    failed = sum(1 for x in records if x.get("scan_errors"))
    open_issues = sorted_open_issues(state, limit=100)
    top = open_issues[:8]
    open_high = [x for x in open_issues if str(x.get("severity")) == "high"]
    metrics = collect_system_metrics(cfg)
    runtime_health = collect_runtime_project_health(cfg)
    app_usage = metrics.get("app_usage") if isinstance(metrics.get("app_usage"), dict) else {}
    workflow_health = collect_workflow_health(cfg, state)
    token_usage_summary = collect_token_usage_summary(cfg)

    risk_reasons: list[str] = []
    if failed > 0:
        risk_reasons.append(f"failed_runs_24h={failed}")
    if open_high:
        risk_reasons.append(f"open_high_issues={len(open_high)}")
    runtime_missing_count = int(((runtime_health.get("summary") or {}).get("required_missing_count", 0) or 0))
    if runtime_missing_count > 0:
        risk_reasons.append(f"runtime_process_missing={runtime_missing_count}")
    if runtime_health.get("errors"):
        risk_reasons.append(f"runtime_monitor_error={len(runtime_health.get('errors') or [])}")
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error={int(workflow_health.get('failed_count', 0) or 0)}")
    if int(workflow_health.get("stale_failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error_stale={int(workflow_health.get('stale_failed_count', 0) or 0)}")
    if workflow_health.get("errors"):
        risk_reasons.append(f"workflow_monitor_error={len(workflow_health.get('errors') or [])}")
    if token_usage_summary.get("errors"):
        risk_reasons.append(f"token_monitor_error={len(token_usage_summary.get('errors') or [])}")
    if app_usage.get("errors"):
        risk_reasons.append(f"app_usage_monitor_error={len(app_usage.get('errors') or [])}")
    warn_items = app_usage.get("warn_items", []) if isinstance(app_usage.get("warn_items", []), list) else []
    if warn_items:
        risk_reasons.append(f"app_storage_warn={len(warn_items)}")
    if bool(app_usage.get("warn_total_exceeded", False)):
        risk_reasons.append("app_storage_total_warn")

    change_reasons: list[str] = []
    if major > 0:
        change_reasons.append(f"major_runs_24h={major}")
    if top:
        change_reasons.append(f"open_issues={len(top)}")
    if runtime_missing_count > 0:
        change_reasons.append(f"runtime_missing={runtime_missing_count}")
    if int(workflow_health.get("new_failed_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_new_failed={int(workflow_health.get('new_failed_count', 0) or 0)}")
    if int(workflow_health.get("recovered_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_recovered={int(workflow_health.get('recovered_count', 0) or 0)}")

    notify_policy = cfg.get("notify_policy")
    if not isinstance(notify_policy, dict):
        notify_policy = {}
    errors_only_notify = parse_bool(cfg.get("errors_only_notify"), True)
    daily_silent_notify_on_change = parse_bool(
        notify_policy.get("daily_silent_notify_on_change", notify_policy.get("silent_notify_on_change")),
        False,
    )
    daily_chat_notify_on_change = parse_bool(
        notify_policy.get("daily_chat_notify_on_change", notify_policy.get("chat_notify_on_change")),
        False,
    )
    daily_chat_notify_on_no_change = parse_bool(
        notify_policy.get("daily_chat_notify_on_no_change", notify_policy.get("chat_notify_on_no_change")),
        False,
    )

    notify = bool(risk_reasons)
    if (not notify) and (not errors_only_notify) and change_reasons:
        if normal_log_mode == "chat":
            notify = daily_chat_notify_on_change
        else:
            notify = daily_silent_notify_on_change
    elif (not notify) and (not errors_only_notify) and normal_log_mode == "chat":
        notify = daily_chat_notify_on_no_change

    if not notify:
        sender_identity = sender_identity_for_mode("daily")
        return RunResult(
            notify=False,
            output="NO_REPLY",
            record={
                "run_id": uuid.uuid4().hex[:12],
                "sender_identity": sender_identity,
                "task_id": task_id,
                "mode": "daily",
                "time": now_iso(),
                "notify": False,
                "normal_log_mode": normal_log_mode,
                "errors_only_notify": bool(errors_only_notify),
                "risk_reasons": [],
                "change_reasons": [],
                "major_reasons": [],
                "run_duration_ms": max(0, int((now() - run_started_at).total_seconds() * 1000)),
                "daily": {"total_runs_24h": total, "major_runs_24h": major, "failed_runs_24h": failed},
                "metrics": metrics,
                "runtime_health": runtime_health,
                "workflow_health": workflow_health,
                "token_usage": token_usage_summary,
            },
        )

    sender_identity = sender_identity_for_mode("daily")
    run_id = uuid.uuid4().hex[:12]
    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    todo_new_24h = sum(int((x.get("handoff_summary") or {}).get("todo_new", 0) or 0) for x in records if isinstance(x, dict))
    active_high_risk_24h = sum(
        int((x.get("handoff_summary") or {}).get("active_high_risk_items", 0) or 0) for x in records if isinstance(x, dict)
    )

    lines: list[str] = []
    lines.append(
        f"{now().strftime('%Y-%m-%d %H:%M:%S')} UTC+8 每日巡检：最近 24 小时共运行 {total} 次，"
        f"异常通知 {major} 次，扫描失败 {failed} 次。"
    )
    lines.append(f"- 任务：{task_id or '-'}")
    lines.append(f"- 运行编号：{run_id}")
    lines.append("- 窗口：最近 24 小时")
    if risk_reasons:
        lines.append("- \u98ce\u9669\u539f\u56e0:")
        for idx, reason in enumerate(risk_reasons[:10], start=1):
            lines.append(f"  {idx}. {humanize_risk_reason(reason)}")
    lines.append(f"- \u7edf\u8ba1: \u603b\u8fd0\u884c={total}\uff0c\u5f02\u5e38\u901a\u77e5={major}\uff0c\u626b\u63cf\u5931\u8d25={failed}")
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        lines.append("- \u5de5\u4f5c\u6d41\u5931\u8d25\u4efb\u52a1:")
        for idx, item in enumerate(list(workflow_health.get("failed_jobs", []))[:3], start=1):
            lines.append(
                f"  {idx}. {item.get('id')} / {item.get('name')} "
                f"(\u72b6\u6001: {item.get('last_status')}, \u8fde\u7eed\u5931\u8d25: {item.get('consecutive_errors')})"
            )
            if str(item.get("last_error", "")).strip():
                lines.append(f"     \u9519\u8bef: {str(item.get('last_error', ''))[:140]}")
    if top:
        lines.append("- \u672a\u95ed\u73af\u9ad8\u9891\u95ee\u9898:")
        for idx, item in enumerate(top[:5], start=1):
            lines.append(
                f"  {idx}. [{item.get('severity')}] {str(item.get('title', ''))[:120]} "
                f"(\u6700\u8fd1: {iso_to_local_text(item.get('last_seen'))})"
            )
    runtime_missing_rows = runtime_health.get("missing_required", [])
    if isinstance(runtime_missing_rows, list) and runtime_missing_rows:
        lines.append("- \u5f53\u524d\u7f3a\u5931\u7684\u5e38\u9a7b\u8fdb\u7a0b/\u670d\u52a1:")
        for idx, item in enumerate(runtime_missing_rows[:5], start=1):
            lines.append(
                f"  {idx}. {str(item.get('project_name', '-'))} / {str(item.get('item_name', '-'))} "
                f"({str(item.get('type', '-'))}) -> {str(item.get('status', '-'))}"
            )
    if warn_items:
        lines.append("- \u7a7a\u95f4\u9884\u8b66:")
        for idx, x in enumerate(warn_items[:3], start=1):
            lines.append(
                f"  {idx}. {str(x.get('name', 'app'))}: "
                f"{float(x.get('size_gb', 0.0) or 0.0):.2f}GB / "
                f"\u9608\u503c {float(x.get('warn_gb', 0.0) or 0.0):.2f}GB"
            )
    if todo_new_24h or active_high_risk_24h:
        lines.append(
            f"- \u5f85\u529e\u4ea4\u63a5: \u65b0\u589e\u5f85\u529e={todo_new_24h}\uff0c\u6d3b\u52a8\u9ad8\u98ce\u9669\u9879={active_high_risk_24h}"
        )
    return RunResult(
        notify=True,
        output="\n".join(lines),
        record={
            "run_id": run_id,
            "sender_identity": sender_identity,
            "task_id": task_id,
            "mode": "daily",
            "time": now_iso(),
            "notify": True,
            "normal_log_mode": normal_log_mode,
            "errors_only_notify": bool(errors_only_notify),
            "priority": priority,
            "risk_level": risk_level,
            "run_duration_ms": run_duration_ms,
            "risk_reasons": risk_reasons,
            "change_reasons": change_reasons,
            "major_reasons": [*risk_reasons, *change_reasons] or ["daily_summary"],
            "daily": {"total_runs_24h": total, "major_runs_24h": major, "failed_runs_24h": failed},
            "open_issue_count": len(open_issues),
            "handoff_24h": {"todo_new": todo_new_24h, "active_high_risk_items": active_high_risk_24h},
            "metrics": metrics,
            "runtime_health": runtime_health,
            "workflow_health": workflow_health,
            "token_usage": token_usage_summary,
            "cost_estimate": float(token_usage_summary.get("cost_estimate", 0.0) or 0.0),
        },
    )


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="OpenClaw unified ops cron runner")
    parser.add_argument("--mode", choices=["incremental", "full", "daily"], default="incremental")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--config", default=str(home / ".openclaw/ops/cron-monitor-config.json"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/cron-monitor-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/cron-runs"))
    parser.add_argument("--daily-major-only", action="store_true")
    parser.add_argument("--force-fallback", action="store_true")
    parser.add_argument("--normal-log-mode", default="", help="override: silent|chat")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    cfg_path = Path(args.config).expanduser()
    state_path = Path(args.state_file).expanduser()
    history_dir = Path(args.history_dir).expanduser()
    history_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_json(cfg_path, None)
    if not isinstance(cfg, dict):
        cfg = default_config()
        save_json(cfg_path, cfg)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    resolved_log_mode = resolve_log_mode(args.mode, cfg, args.normal_log_mode)

    if args.mode == "daily":
        result = build_daily_report(
            history_dir,
            cfg,
            state,
            major_only=bool(args.daily_major_only),
            task_id=args.task_id,
            normal_log_mode=resolved_log_mode,
        )
        state["runs"]["daily"] = int(state.get("runs", {}).get("daily", 0)) + 1
    else:
        result = run_scan(
            mode=args.mode,
            cfg=cfg,
            state=state,
            task_id=args.task_id,
            daily_major_only=bool(args.daily_major_only),
            force_fallback=bool(args.force_fallback),
            normal_log_mode_override=resolved_log_mode,
        )

    stamp = now().strftime("%Y%m%d_%H%M%S")
    run_file = history_dir / f"{stamp}_{result.record.get('mode', args.mode)}_{result.record.get('run_id', 'run')}.json"
    policy_db_path = resolve_task_center_db_path(cfg, home)
    workflow_follow_up_summary = create_workflow_follow_up_tasks(
        cfg=cfg,
        state=state,
        db_path=policy_db_path,
        actor=str(result.record.get("sender_identity", "")) or DEFAULT_SENDER_PREFIX,
        run_file=run_file,
        run_task_id=str(args.task_id or ""),
        mode=str(result.record.get("mode", args.mode)),
        started_at=str(result.record.get("time", now_iso())),
        workflow_health=result.record.get("workflow_health", {}) if isinstance(result.record.get("workflow_health"), dict) else {},
    )
    result.record["workflow_follow_up_summary"] = workflow_follow_up_summary
    result.output = append_workflow_follow_up_output(result.output, workflow_follow_up_summary)
    save_json(run_file, result.record)
    state["updated_at"] = now_iso()
    state["last_run_record"] = str(run_file)
    save_json(state_path, state)

    policy_observability: dict[str, Any] = {
        "enabled": False,
        "db": str(policy_db_path),
        "task_bound": False,
        "errors": [],
    }
    planner_summary_snapshot: dict[str, Any] = {}
    if policy_db_path.exists():
        policy_observability["enabled"] = True
        raw_task_id = str(args.task_id or "").strip()
        bound_task_id = ""
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                policy_db_path,
                raw_task_id,
                "ops-agent",
                "ops-agent/ops-cron-runner",
            )
            policy_observability["task_bound"] = bool(bound_task_id)
            if (not bound_task_id) and bind_err:
                policy_observability["errors"].append(bind_err)

        mode_name = str(result.record.get("mode", args.mode))
        run_duration_ms = int(result.record.get("run_duration_ms", 0) or 0)
        risk_reasons = [str(x).strip() for x in (result.record.get("risk_reasons") or []) if str(x).strip()]
        change_reasons = [str(x).strip() for x in (result.record.get("change_reasons") or []) if str(x).strip()]
        handoff_data = result.record.get("handoff_summary")
        if not isinstance(handoff_data, dict):
            handoff_data = result.record.get("handoff_24h")
        if not isinstance(handoff_data, dict):
            handoff_data = {}
        workflow_follow_up_data = result.record.get("workflow_follow_up_summary")
        if not isinstance(workflow_follow_up_data, dict):
            workflow_follow_up_data = {}

        module_details = {
            "mode": mode_name,
            "run_id": str(result.record.get("run_id", "")),
            "record_file": str(run_file),
            "notify": bool(result.record.get("notify")),
            "risk_reasons": risk_reasons,
            "change_reasons": change_reasons,
            "handoff": handoff_data,
            "workflow_follow_up": workflow_follow_up_data,
        }
        module_args = [
            "log-module",
            "--module-name",
            "ops-agent/ops-cron-runner",
            "--phase",
            mode_name,
            "--level",
            ("error" if risk_reasons else "info"),
            "--status",
            ("failed" if risk_reasons else "passed"),
            "--message",
            (
                f"ops-cron-runner mode={mode_name} risk={len(risk_reasons)} "
                + f"change={len(change_reasons)} notify={bool(result.record.get('notify'))}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(module_details, ensure_ascii=False),
            "--actor",
            str(result.record.get("sender_identity", "")) or "ops-agent/ops-cron-runner",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(policy_db_path, module_args, timeout=25)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_status = "acked"
        if risk_reasons:
            comm_status = "failed"
        elif int(handoff_data.get("todo_new", 0) or 0) == 0 and mode_name != "daily":
            comm_status = "sent"
        comm_args = [
            "log-communication",
            "--from-module",
            "ops-agent/ops-cron-runner",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "incident_handoff",
            "--status",
            comm_status,
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(result.record.get("run_id", "")),
            "--payload-ref",
            str(run_file),
            "--details-json",
            json.dumps({"handoff": handoff_data, "workflow_follow_up": workflow_follow_up_data, "mode": mode_name}, ensure_ascii=False),
            "--actor",
            str(result.record.get("sender_identity", "")) or "ops-agent/ops-cron-runner",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(policy_db_path, comm_args, timeout=25)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        if bound_task_id:
            report_status = "passed"
            if risk_reasons:
                report_status = "failed"
                if any("workflow_job_error" in x or "scan_error" in x for x in risk_reasons):
                    report_status = "escalated"
            resolved_items = [compact_reason(x) for x in change_reasons if compact_reason(x)]
            failed_items = [compact_reason(x) for x in risk_reasons if compact_reason(x)]
            quality_score = 96.0 if not risk_reasons else max(30.0, 80.0 - (len(risk_reasons) * 10.0))
            token_usage = result.record.get("token_usage", {})
            if not isinstance(token_usage, dict):
                token_usage = {}
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "ops-agent",
                "--planner-id",
                "coordinator",
                "--status",
                report_status,
                "--solved",
                ("false" if risk_reasons else "true"),
                "--resolved-issues",
                ",".join(resolved_items[:20]),
                "--resolution-summary",
                f"ops scan mode={mode_name} completed",
                "--resolution-steps",
                (
                    "scan,aggregate,handoff,create_follow_up_task"
                    if int(workflow_follow_up_data.get("created_count", 0) or 0) > 0
                    else "scan,aggregate,handoff"
                ),
                "--failed-items",
                ",".join(failed_items[:20]),
                "--failure-count",
                str(len(risk_reasons)),
                "--duration-ms",
                str(run_duration_ms),
                "--input-tokens",
                str(int(token_usage.get("total_tokens", 0) or 0)),
                "--output-tokens",
                "0",
                "--cost-estimate",
                str(float(result.record.get("cost_estimate", 0.0) or 0.0)),
                "--quality-score",
                str(round(float(quality_score), 4)),
                "--quality-grade",
                ("a" if not risk_reasons else "c"),
                "--notify-chat",
                ("true" if risk_reasons else "false"),
                "--details-json",
                json.dumps(
                    {
                        "mode": mode_name,
                        "run_id": str(result.record.get("run_id", "")),
                        "record_file": str(run_file),
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                str(result.record.get("sender_identity", "")) or "ops-agent/ops-cron-runner",
            ]
            ok_report, payload_report, err_report = invoke_policy_enforcer(policy_db_path, report_args, timeout=30)
            policy_observability["report_agent_result_ok"] = ok_report
            if ok_report and isinstance(payload_report, dict):
                result_payload = payload_report.get("result")
                if isinstance(result_payload, dict):
                    planner_payload = result_payload.get("planner_payload")
                    if isinstance(planner_payload, dict):
                        policy_observability["agent_report"] = {
                            "report_status": planner_payload.get("report_status"),
                            "notify_chat": planner_payload.get("notify_chat"),
                            "failure_count": planner_payload.get("failure_count"),
                        }
            if not ok_report and err_report:
                policy_observability["errors"].append(err_report)

        since_24h = (datetime.now(tz=UTC) - timedelta(hours=24)).replace(microsecond=0).isoformat()
        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            policy_db_path,
            [
                "planner-summary",
                "--planner-id",
                "coordinator",
                "--since",
                since_24h,
                "--limit",
                "60",
            ],
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
        if not ok_summary and err_summary:
            policy_observability["errors"].append(err_summary)

    result.record["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        result.record["planner_summary"] = planner_summary_snapshot
    exception_reasons = [str(x).strip() for x in policy_observability.get("errors", []) if str(x).strip()]
    if exception_reasons:
        result.notify = True
        if result.output == "NO_REPLY":
            lines = [
                "# \u7b56\u7565\u6a21\u5757\u8fd0\u884c\u5f02\u5e38",
                f"- \u53d1\u9001\u65b9: {result.record.get('sender_identity', DEFAULT_SENDER_PREFIX)}",
                f"- \u4efb\u52a1: {args.task_id or '-'}",
                f"- \u65f6\u95f4: {now_iso()}",
                f"- \u6a21\u5f0f: {result.record.get('mode', args.mode)}",
                f"- \u5f02\u5e38\u6570: {len(exception_reasons)}",
            ]
            result.output = "\n".join(lines)
        else:
            result.output = f"{result.output}\n- \u7b56\u7565\u6a21\u5757\u5f02\u5e38\u6570: {len(exception_reasons)}"
        for reason in exception_reasons[:12]:
            result.output = f"{result.output}\n- \u5f02\u5e38: {reason}"
    if not result.notify:
        result.output = "NO_REPLY"
    result.record["notify"] = bool(result.notify)
    if exception_reasons:
        result.record["exception_reasons"] = exception_reasons[:50]
    save_json(run_file, result.record)

    if args.emit_json:
        print(json.dumps({"notify": result.notify, "output": result.output, "record": str(run_file)}, ensure_ascii=False))
    else:
        if result.notify:
            print(f"{result.output}\n- \u8fd0\u884c\u8bb0\u5f55: {run_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import sqlite3
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
ERROR_KEYWORDS = (
    "error",
    "exception",
    "fatal",
    "panic",
    "traceback",
    "failed",
    "timeout",
    "拒绝",
    "异常",
    "错误",
    "失败",
    "超时",
)
HIGH_KEYWORDS = ("fatal", "panic", "segfault", "oom", "critical", "数据库", "数据丢失")
VOLATILE_PATTERNS = (
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b",
    r"\b0x[0-9a-fA-F]+\b",
    r"\b[0-9a-fA-F]{10,}\b",
    r"\b\d{5,}\b",
)
DEFAULT_SENDER_PREFIX = "ops-agent/ops-cron-runner"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    if mode in {"silent", "chat"}:
        return mode
    return default


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        "system_monitor": {
            "enabled": True,
            "disk_paths": disk_paths,
            "disk_warn_percent": 85.0,
            "memory_warn_percent": 90.0,
            "cpu_warn_percent": 90.0,
            "process_cpu_warn_percent": 95.0,
            "top_n_processes": 5,
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
    }


def default_state() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-02",
        "updated_at": "",
        "runs": {"incremental": 0, "full": 0, "daily": 0},
        "checkpoints": {},
        "issues": {},
        "services": {},
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


def discover_logs(cfg: dict[str, Any], service_names: list[str]) -> list[Path]:
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

    for item in jobs:
        if not isinstance(item, dict):
            continue
        jobs_total += 1
        jid = str(item.get("id", "")).strip() or f"job-{jobs_total}"
        name = str(item.get("name", "")).strip() or jid
        enabled = bool(item.get("enabled", False))
        if enabled:
            jobs_enabled += 1

        st = item.get("state", {})
        if not isinstance(st, dict):
            st = {}
        last_status = str(st.get("lastStatus") or st.get("lastRunStatus") or "").strip().lower()
        current_status[jid] = last_status

        prev = str(prev_status.get(jid, "")).strip().lower()
        if enabled and last_status in {"error", "failed"} and prev not in {"error", "failed"}:
            new_failed += 1
        if enabled and last_status not in {"error", "failed"} and prev in {"error", "failed"}:
            recovered += 1

        if not enabled or last_status not in {"error", "failed"}:
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
    }

    if not jobs_file.exists():
        errors.append(f"jobs_file_missing:{jobs_file}")

    return {
        "enabled": True,
        "jobs_file": str(jobs_file),
        "jobs_total": jobs_total,
        "jobs_enabled": jobs_enabled,
        "failed_count": len(failed_jobs),
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
    state.setdefault("runs", {"incremental": 0, "full": 0, "daily": 0})
    state["runs"][mode] = int(state["runs"].get(mode, 0)) + 1
    run_id = uuid.uuid4().hex[:12]
    service_snapshot, service_error = collect_services(cfg)
    log_files = discover_logs(cfg, list(service_snapshot.keys()))

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
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error={int(workflow_health.get('failed_count', 0) or 0)}")
    if int(workflow_health.get("stale_failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error_stale={int(workflow_health.get('stale_failed_count', 0) or 0)}")
    if workflow_health.get("errors"):
        risk_reasons.append(f"workflow_monitor_error={len(workflow_health.get('errors') or [])}")
    if token_usage_summary.get("errors"):
        risk_reasons.append(f"token_monitor_error={len(token_usage_summary.get('errors') or [])}")

    change_reasons: list[str] = []
    if issue_stats["new"] > 0:
        change_reasons.append(f"new_issue={issue_stats['new']}")
    if issue_stats["reopened"] > 0:
        change_reasons.append(f"reopened_issue={issue_stats['reopened']}")
    if issue_stats["resolved"] > 0:
        change_reasons.append(f"resolved_issue={issue_stats['resolved']}")
    if added or removed or changed:
        change_reasons.append(f"service_change=+{len(added)}/-{len(removed)}/~{len(changed)}")
    if fallback_used:
        change_reasons.append("fallback_full_scan")
    if int(workflow_health.get("new_failed_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_new_failed={int(workflow_health.get('new_failed_count', 0) or 0)}")
    if int(workflow_health.get("recovered_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_recovered={int(workflow_health.get('recovered_count', 0) or 0)}")

    major_reasons = [*risk_reasons, *change_reasons]
    notify = bool(risk_reasons)
    if not notify and log_mode == "chat":
        notify = True

    output = "NO_REPLY"
    if notify:
        lines: list[str] = []
        lines.append(f"# ops-cron {mode}")
        lines.append(f"- sender_identity: {sender_identity}")
        lines.append(f"- task: {task_id or '-'}")
        lines.append(f"- time: {now_iso()}")
        lines.append(f"- normal_log_mode: {log_mode}")
        if risk_reasons:
            lines.append(f"- risk_reasons: {', '.join(risk_reasons)}")
        if change_reasons:
            lines.append(f"- change_reasons: {', '.join(change_reasons)}")
        lines.append(
            f"- issue: new={issue_stats['new']}, reopened={issue_stats['reopened']}, "
            f"resolved={issue_stats['resolved']}, open={issue_stats['open_total']}, "
            f"open_high={issue_stats['open_high_total']}"
        )
        lines.append(f"- logs_scanned: {len(log_files)}, bytes_read={read_bytes}, findings={len(findings)}")
        if fallback_used:
            lines.append(f"- fallback: true ({', '.join(sorted(set(fallback_reasons)))})")
        if added or removed or changed:
            lines.append(f"- service_delta: added={len(added)}, removed={len(removed)}, changed={len(changed)}")
        if metrics.get("anomalies"):
            lines.append(f"- anomalies: {'; '.join(metrics['anomalies'][:5])}")
        if int(workflow_health.get("failed_count", 0) or 0) > 0:
            lines.append(
                f"- workflow_health: failed={workflow_health.get('failed_count', 0)}, "
                f"stale_failed={workflow_health.get('stale_failed_count', 0)}, "
                f"recovered={workflow_health.get('recovered_count', 0)}"
            )
            for item in list(workflow_health.get("failed_jobs", []))[:3]:
                lines.append(
                    f"  - job[{item.get('id')}|{item.get('name')}]: status={item.get('last_status')} "
                    f"stale_min={item.get('stale_minutes')} consecutive={item.get('consecutive_errors')}"
                )
        lines.append(
            f"- token_24h: total_tokens={token_usage_summary.get('total_tokens', 0)}, "
            f"total_m={token_usage_summary.get('total_tokens_m', 0)}, "
            f"cost={token_usage_summary.get('cost_estimate', 0)} "
            f"(rows={token_usage_summary.get('rows', 0)})"
        )
        top_agents = token_usage_summary.get("by_agent") or []
        if isinstance(top_agents, list) and top_agents:
            top = top_agents[0]
            lines.append(
                f"- token_top_agent: {top.get('agent_id')} "
                f"tokens={top.get('total_tokens', 0)} cost={top.get('cost_estimate', 0)}"
            )
        output = "\n".join(lines)

    record = {
        "run_id": run_id,
        "sender_identity": sender_identity,
        "task_id": task_id,
        "mode": mode,
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": log_mode,
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "major_reasons": major_reasons,
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
        "workflow_health": workflow_health,
        "token_usage": token_usage_summary,
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
    open_issues = [
        item for item in (state.get("issues") or {}).values() if isinstance(item, dict) and item.get("status") == "open"
    ]
    open_issues.sort(key=lambda x: (0 if x.get("severity") == "high" else 1, -int(x.get("occurrences", 0))))
    top = open_issues[:8]
    open_high = [x for x in open_issues if str(x.get("severity")) == "high"]
    workflow_health = collect_workflow_health(cfg, state)
    token_usage_summary = collect_token_usage_summary(cfg)

    risk_reasons: list[str] = []
    if failed > 0:
        risk_reasons.append(f"failed_runs_24h={failed}")
    if open_high:
        risk_reasons.append(f"open_high_issues={len(open_high)}")
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error={int(workflow_health.get('failed_count', 0) or 0)}")
    if int(workflow_health.get("stale_failed_count", 0) or 0) > 0:
        risk_reasons.append(f"workflow_job_error_stale={int(workflow_health.get('stale_failed_count', 0) or 0)}")
    if workflow_health.get("errors"):
        risk_reasons.append(f"workflow_monitor_error={len(workflow_health.get('errors') or [])}")
    if token_usage_summary.get("errors"):
        risk_reasons.append(f"token_monitor_error={len(token_usage_summary.get('errors') or [])}")

    change_reasons: list[str] = []
    if major > 0:
        change_reasons.append(f"major_runs_24h={major}")
    if top:
        change_reasons.append(f"open_issues={len(top)}")
    if int(workflow_health.get("new_failed_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_new_failed={int(workflow_health.get('new_failed_count', 0) or 0)}")
    if int(workflow_health.get("recovered_count", 0) or 0) > 0:
        change_reasons.append(f"workflow_recovered={int(workflow_health.get('recovered_count', 0) or 0)}")

    notify = bool(risk_reasons)
    if not notify and major_only:
        notify = bool(change_reasons)
    elif not notify and normal_log_mode == "chat":
        notify = True
    elif not notify:
        notify = bool(change_reasons)

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
                "risk_reasons": [],
                "change_reasons": [],
                "major_reasons": [],
                "daily": {"total_runs_24h": total, "major_runs_24h": major, "failed_runs_24h": failed},
                "workflow_health": workflow_health,
                "token_usage": token_usage_summary,
            },
        )

    sender_identity = sender_identity_for_mode("daily")
    lines: list[str] = []
    lines.append("# ops-cron daily")
    lines.append(f"- sender_identity: {sender_identity}")
    lines.append(f"- task: {task_id or '-'}")
    lines.append(f"- window: last 24h")
    lines.append(f"- normal_log_mode: {normal_log_mode}")
    if risk_reasons:
        lines.append(f"- risk_reasons: {', '.join(risk_reasons)}")
    if change_reasons:
        lines.append(f"- change_reasons: {', '.join(change_reasons)}")
    lines.append(f"- runs: total={total}, major={major}, failed={failed}")
    lines.append(f"- open_issues: {len(open_issues)}")
    lines.append(
        f"- token_24h: total_tokens={token_usage_summary.get('total_tokens', 0)}, "
        f"total_m={token_usage_summary.get('total_tokens_m', 0)}, "
        f"cost={token_usage_summary.get('cost_estimate', 0)} "
        f"(rows={token_usage_summary.get('rows', 0)})"
    )
    if int(workflow_health.get("failed_count", 0) or 0) > 0:
        lines.append(
            f"- workflow_health: failed={workflow_health.get('failed_count', 0)}, "
            f"stale_failed={workflow_health.get('stale_failed_count', 0)}, "
            f"recovered={workflow_health.get('recovered_count', 0)}"
        )
        for item in list(workflow_health.get("failed_jobs", []))[:3]:
            lines.append(
                f"- workflow_job[{item.get('id')}|{item.get('name')}]: "
                f"status={item.get('last_status')} stale_min={item.get('stale_minutes')} "
                f"consecutive={item.get('consecutive_errors')}"
            )
    for item in top[:5]:
        lines.append(
            f"- issue[{item.get('severity')}|{item.get('occurrences', 0)}]: "
            f"{item.get('title', '')[:120]} @ {item.get('source', '')[:80]}"
        )
    return RunResult(
        notify=True,
        output="\n".join(lines),
        record={
            "run_id": uuid.uuid4().hex[:12],
            "sender_identity": sender_identity,
            "task_id": task_id,
            "mode": "daily",
            "time": now_iso(),
            "notify": True,
            "normal_log_mode": normal_log_mode,
            "risk_reasons": risk_reasons,
            "change_reasons": change_reasons,
            "major_reasons": [*risk_reasons, *change_reasons] or ["daily_summary"],
            "daily": {"total_runs_24h": total, "major_runs_24h": major, "failed_runs_24h": failed},
            "open_issue_count": len(open_issues),
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
    save_json(run_file, result.record)
    state["updated_at"] = now_iso()
    state["last_run_record"] = str(run_file)
    save_json(state_path, state)

    if args.emit_json:
        print(json.dumps({"notify": result.notify, "output": result.output, "record": str(run_file)}, ensure_ascii=False))
    else:
        if result.notify:
            print(f"{result.output}\n- evidence: {run_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

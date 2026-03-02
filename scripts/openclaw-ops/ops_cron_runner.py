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
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_estimate": 0.0,
    }
    return RunResult(notify=notify, output=output, record=record)


def build_daily_report(
    history_dir: Path,
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

    risk_reasons: list[str] = []
    if failed > 0:
        risk_reasons.append(f"failed_runs_24h={failed}")
    if open_high:
        risk_reasons.append(f"open_high_issues={len(open_high)}")

    change_reasons: list[str] = []
    if major > 0:
        change_reasons.append(f"major_runs_24h={major}")
    if top:
        change_reasons.append(f"open_issues={len(top)}")

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

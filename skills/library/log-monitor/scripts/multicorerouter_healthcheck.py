#!/usr/bin/env python3
"""Health check for the local multicorerouter Hermes workflow profile.

The script is intentionally read-only. It inspects the live profile directory,
recent gateway logs, pipeline run artifacts, and process/screen evidence, then
emits a small JSON or Markdown report that operators can paste into Discord.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_HOME = Path("/home/ubuntu/.hermes/profiles/multicorerouter")
DEFAULT_REPO_ROOT = Path("/home/ubuntu/projects/openclaw-hardflow-backup-20260302")
ERROR_PATTERNS = (
    "Traceback",
    "ERROR ",
    " CRITICAL ",
    "ClientConnectorDNSError",
    "Temporary failure in name resolution",
    "Command Approval Required",
    "confusable",
)
REDACT_PATTERNS = (
    re.compile(r"([A-Za-z0-9_-]{35,})"),
    re.compile(r"(?i)(token|secret|password|api[_-]?key|app[_-]?secret)([\s:=]+)([^\s\"',}]+)"),
)


@dataclass(frozen=True)
class HealthConfig:
    profile_home: Path = DEFAULT_PROFILE_HOME
    repo_root: Path = DEFAULT_REPO_ROOT
    log_tail_lines: int = 240


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(text: str) -> str:
    out = text
    out = REDACT_PATTERNS[1].sub(r"\1\2[REDACTED]", out)
    out = REDACT_PATTERNS[0].sub("[REDACTED]", out)
    return out


def tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max(1, limit):]


def check_required_paths(profile_home: Path, repo_root: Path) -> dict[str, Any]:
    paths = {
        "profile_home": profile_home,
        "workspace": profile_home / "workspace",
        "workflow_state": profile_home / ".workflow" / "pipeline-runs",
        "config": profile_home / "config.yaml",
        "start_gateway": profile_home / "start-gateway.sh",
        "startup_log": profile_home / "logs" / "startup.log",
        "errors_log": profile_home / "logs" / "errors.log",
        "repo_root": repo_root,
    }
    items = {name: {"path": str(path), "exists": path.exists()} for name, path in paths.items()}
    missing = [name for name, item in items.items() if not item["exists"]]
    return {"ok": not missing, "items": items, "missing": missing}


def parse_config_summary(config_file: Path) -> dict[str, Any]:
    if not config_file.exists():
        return {"ok": False, "reason": "missing_config"}
    text = config_file.read_text(encoding="utf-8", errors="replace")
    summary: dict[str, Any] = {"ok": True}
    for key in ("DISCORD_HOME_CHANNEL", "allowed_channels", "free_response_channels", "require_mention"):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*['\"]?([^'\"\n]+)", text, re.M)
        if m:
            summary[key] = redact(m.group(1).strip())
    cwd = re.search(r"^\s*cwd\s*:\s*(.+)$", text, re.M)
    if cwd:
        summary["terminal_cwd"] = redact(cwd.group(1).strip())
    return summary


def scan_logs(profile_home: Path, tail_limit: int) -> dict[str, Any]:
    log_files = [profile_home / "logs" / "startup.log", profile_home / "logs" / "errors.log"]
    findings: list[dict[str, str]] = []
    for log_file in log_files:
        for line in tail_lines(log_file, tail_limit):
            if any(pattern in line for pattern in ERROR_PATTERNS):
                findings.append({"file": str(log_file), "line": redact(line)[-500:]})
    dns_markers = (
        "Temporary failure in name resolution",
        "ClientConnectorDNSError",
        "gateway-us-east1-d.discord.gg",
        "socket.gaierror",
    )
    dns_hits = [f for f in findings if any(marker in f["line"] for marker in dns_markers)]
    dns_context_present = bool(dns_hits)
    hard_errors: list[dict[str, str]] = []
    for finding in findings:
        line = finding["line"]
        if any(marker in line for marker in dns_markers):
            continue
        if dns_context_present and ("Traceback" in line or "discord.client: Attempting a reconnect" in line):
            continue
        if any(token in line for token in ("Traceback", "ERROR ", " CRITICAL ", "Command Approval Required", "confusable")):
            hard_errors.append(finding)
    return {
        "ok": not hard_errors,
        "finding_count": len(findings),
        "hard_error_count": len(hard_errors),
        "dns_warning_count": len(dns_hits),
        "findings_tail": findings[-20:],
    }


def latest_pipeline_runs(profile_home: Path, limit: int = 5) -> dict[str, Any]:
    state_dir = profile_home / ".workflow" / "pipeline-runs"
    if not state_dir.exists():
        return {"ok": False, "reason": "missing_pipeline_runs_dir", "runs": []}
    dirs = sorted([p for p in state_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    runs: list[dict[str, Any]] = []
    for run_dir in dirs:
        state_file = run_dir / "pipeline_state.json"
        meta_file = run_dir / "run_meta.json"
        item: dict[str, Any] = {"run_dir": str(run_dir), "name": run_dir.name}
        for file_name, path in (("pipeline_state", state_file), ("run_meta", meta_file)):
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                item[file_name + "_error"] = str(exc)
                continue
            if isinstance(data, dict):
                item["project_key"] = data.get("project_key", item.get("project_key"))
                item["run_id"] = data.get("run_id", item.get("run_id"))
                item["status"] = data.get("status", item.get("status"))
                item["current_stage"] = data.get("current_stage", item.get("current_stage"))
                item["runtime_home"] = (data.get("runtime") or {}).get("runtime_home", item.get("runtime_home"))
        runs.append(item)
    return {"ok": True, "runs": runs}


def command_output(command: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return proc.returncode, redact((proc.stdout or "") + (proc.stderr or ""))
    except Exception as exc:  # pragma: no cover - defensive for odd hosts
        return 999, str(exc)


def process_status() -> dict[str, Any]:
    rc, ps_out = command_output(["ps", "-eo", "pid,ppid,cmd"])
    gateway_lines = [line for line in ps_out.splitlines() if "hermes -p multicorerouter gateway run" in line]
    screen_rc, screen_out = command_output(["screen", "-ls"])
    screen_present = "hermes-multicorerouter-gateway" in screen_out
    return {
        "ok": bool(gateway_lines) and screen_present,
        "gateway_process_count": len(gateway_lines),
        "gateway_processes": gateway_lines[:5],
        "screen_rc": screen_rc,
        "screen_present": screen_present,
    }


def git_status(repo_root: Path) -> dict[str, Any]:
    if not (repo_root / ".git").exists():
        return {"ok": False, "reason": "not_a_git_repo", "path": str(repo_root)}
    rc_branch, branch = command_output(["git", "-C", str(repo_root), "branch", "--show-current"])
    rc_status, status = command_output(["git", "-C", str(repo_root), "status", "--short", "--branch"])
    rc_remote, remote = command_output(["git", "-C", str(repo_root), "remote", "get-url", "origin"])
    return {
        "ok": rc_branch == 0 and rc_status == 0,
        "branch": branch.strip(),
        "status": status.strip().splitlines()[:20],
        "remote": remote.strip(),
        "remote_ok": rc_remote == 0,
    }


def run_healthcheck(config: HealthConfig) -> dict[str, Any]:
    required = check_required_paths(config.profile_home, config.repo_root)
    config_summary = parse_config_summary(config.profile_home / "config.yaml")
    logs = scan_logs(config.profile_home, config.log_tail_lines)
    processes = process_status()
    pipelines = latest_pipeline_runs(config.profile_home)
    repo = git_status(config.repo_root)
    checks = {
        "required_paths": required,
        "config": config_summary,
        "logs": logs,
        "processes": processes,
        "pipeline_runs": pipelines,
        "repo": repo,
    }
    ok = all(check.get("ok", False) for check in checks.values())
    return {
        "ok": ok,
        "checked_at": utc_now(),
        "profile_home": str(config.profile_home),
        "repo_root": str(config.repo_root),
        "install_target_runtime_home": "/home/ubuntu/.hermes",
        "install_target_ops_dir": "/home/ubuntu/.hermes/ops",
        "checks": checks,
    }


def to_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    lines = [
        "# multicorerouter 工作流健康检查",
        "",
        f"- 总状态: {'OK' if report['ok'] else 'ATTENTION'}",
        f"- 检查时间: `{report['checked_at']}`",
        f"- profile: `{report['profile_home']}`",
        f"- repo: `{report['repo_root']}`",
        f"- 安装目标 runtime: `{report['install_target_runtime_home']}`",
        f"- 安装目标 ops: `{report['install_target_ops_dir']}`",
        "",
        "## 检查项",
    ]
    for name, payload in checks.items():
        lines.append(f"- {name}: {'OK' if payload.get('ok') else 'ATTENTION'}")
    log_check = checks["logs"]
    lines.extend([
        "",
        "## 日志摘要",
        f"- hard_error_count: `{log_check.get('hard_error_count')}`",
        f"- dns_warning_count: `{log_check.get('dns_warning_count')}`",
        f"- finding_count: `{log_check.get('finding_count')}`",
    ])
    if log_check.get("findings_tail"):
        lines.append("- 最近命中:")
        for item in log_check["findings_tail"][-8:]:
            lines.append(f"  - `{item['file']}`: {item['line']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only multicorerouter workflow health check")
    parser.add_argument("--profile-home", default=str(DEFAULT_PROFILE_HOME))
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--log-tail-lines", type=int, default=240)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_healthcheck(
        HealthConfig(
            profile_home=Path(args.profile_home).expanduser(),
            repo_root=Path(args.repo_root).expanduser(),
            log_tail_lines=args.log_tail_lines,
        )
    )
    if args.format == "markdown":
        print(to_markdown(report), end="")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

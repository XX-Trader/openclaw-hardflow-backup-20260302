#!/usr/bin/env python3
"""Read-only health check for a configurable workflow runtime.

The checker reports filesystem, log, process, pipeline-run, and Git evidence.
It deliberately has no built-in host, profile, process manager, or repository
name; callers supply environment-specific checks through arguments.
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


DEFAULT_RUNTIME_HOME = Path(
    os.environ.get("HARDFLOW_RUNTIME_HOME", str(Path.home() / ".hardflow-runtime"))
).expanduser()
DEFAULT_REPO_ROOT = Path(
    os.environ.get("HARDFLOW_WORKFLOW_REPO", str(Path.cwd()))
).expanduser()
DEFAULT_LOG_FILES = ("logs/startup.log", "logs/errors.log")
ERROR_PATTERNS = (
    "Traceback",
    "ERROR ",
    " CRITICAL ",
    "Temporary failure in name resolution",
    "Command Approval Required",
)
REDACT_PATTERNS = (
    re.compile(r"([A-Za-z0-9_-]{35,})"),
    re.compile(r"(?i)(token|secret|password|api[_-]?key|app[_-]?secret)([\s:=]+)([^\s\"',}]+)"),
)


@dataclass(frozen=True)
class HealthConfig:
    runtime_home: Path = DEFAULT_RUNTIME_HOME
    repo_root: Path = DEFAULT_REPO_ROOT
    log_tail_lines: int = 240
    log_files: tuple[str, ...] = DEFAULT_LOG_FILES
    required_paths: tuple[str, ...] = ()
    process_match: str = ""


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
    return lines[-max(1, limit) :]


def resolve_runtime_path(runtime_home: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else runtime_home / candidate


def check_required_paths(
    runtime_home: Path,
    repo_root: Path,
    required_paths: tuple[str, ...] = (),
) -> dict[str, Any]:
    paths: dict[str, Path] = {
        "runtime_home": runtime_home,
        "repo_root": repo_root,
    }
    for index, value in enumerate(required_paths, start=1):
        paths[f"required_{index}"] = resolve_runtime_path(runtime_home, value)
    items = {name: {"path": str(path), "exists": path.exists()} for name, path in paths.items()}
    missing = [name for name, item in items.items() if not item["exists"]]
    return {"ok": not missing, "items": items, "missing": missing}


def parse_config_summary(config_file: Path) -> dict[str, Any]:
    if not config_file.exists():
        return {"ok": True, "skipped": True, "reason": "missing_optional_config"}
    text = config_file.read_text(encoding="utf-8", errors="replace")
    summary: dict[str, Any] = {"ok": True, "path": str(config_file)}
    for key in ("runtime_name", "profile", "connector", "require_mention", "cwd"):
        match = re.search(rf"^\s*{re.escape(key)}\s*:\s*['\"]?([^'\"\n]+)", text, re.M)
        if match:
            summary[key] = redact(match.group(1).strip())
    return summary


def scan_logs(runtime_home: Path, log_files: tuple[str, ...], tail_limit: int) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    existing_files = 0
    for value in log_files:
        log_file = resolve_runtime_path(runtime_home, value)
        if log_file.is_file():
            existing_files += 1
        for line in tail_lines(log_file, tail_limit):
            if any(pattern in line for pattern in ERROR_PATTERNS):
                findings.append({"file": str(log_file), "line": redact(line)[-500:]})
    dns_markers = (
        "Temporary failure in name resolution",
        "ClientConnectorDNSError",
        "socket.gaierror",
    )
    dns_hits = [item for item in findings if any(marker in item["line"] for marker in dns_markers)]
    hard_errors = [
        item
        for item in findings
        if not any(marker in item["line"] for marker in dns_markers)
    ]
    return {
        "ok": not hard_errors,
        "skipped": existing_files == 0,
        "log_file_count": existing_files,
        "finding_count": len(findings),
        "hard_error_count": len(hard_errors),
        "dns_warning_count": len(dns_hits),
        "findings_tail": findings[-20:],
    }


def latest_pipeline_runs(runtime_home: Path, limit: int = 5) -> dict[str, Any]:
    state_dir = runtime_home / ".workflow" / "pipeline-runs"
    if not state_dir.exists():
        return {"ok": True, "skipped": True, "reason": "missing_optional_pipeline_runs_dir", "runs": []}
    dirs = sorted(
        [path for path in state_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    runs: list[dict[str, Any]] = []
    for run_dir in dirs:
        item: dict[str, Any] = {"run_dir": str(run_dir), "name": run_dir.name}
        for file_name in ("pipeline_state.json", "run_meta.json"):
            path = run_dir / file_name
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                item[file_name + "_error"] = str(exc)
                continue
            if isinstance(data, dict):
                for key in ("project_key", "run_id", "status", "current_stage"):
                    item[key] = data.get(key, item.get(key))
                item["runtime_home"] = (data.get("runtime") or {}).get(
                    "runtime_home", item.get("runtime_home")
                )
        runs.append(item)
    return {"ok": True, "runs": runs}


def command_output(command: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, redact((proc.stdout or "") + (proc.stderr or ""))
    except (OSError, subprocess.SubprocessError) as exc:
        return 999, str(exc)


def process_status(process_match: str) -> dict[str, Any]:
    match = process_match.strip()
    if not match:
        return {"ok": True, "skipped": True, "reason": "process_match_not_configured"}
    rc, output = command_output(["ps", "-eo", "pid,ppid,cmd"])
    processes = [line for line in output.splitlines() if match in line]
    return {
        "ok": rc == 0 and bool(processes),
        "process_match": redact(match),
        "process_count": len(processes),
        "processes": processes[:5],
        "command_exit_code": rc,
    }


def git_status(repo_root: Path) -> dict[str, Any]:
    rc_repo, repo_check = command_output(["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"])
    if rc_repo != 0 or repo_check.strip().lower() != "true":
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
    checks = {
        "required_paths": check_required_paths(
            config.runtime_home, config.repo_root, config.required_paths
        ),
        "config": parse_config_summary(config.runtime_home / "config.yaml"),
        "logs": scan_logs(config.runtime_home, config.log_files, config.log_tail_lines),
        "processes": process_status(config.process_match),
        "pipeline_runs": latest_pipeline_runs(config.runtime_home),
        "repo": git_status(config.repo_root),
    }
    return {
        "ok": all(check.get("ok", False) for check in checks.values()),
        "checked_at": utc_now(),
        "runtime_home": str(config.runtime_home),
        "repo_root": str(config.repo_root),
        "ops_dir": str(config.runtime_home / "ops"),
        "checks": checks,
    }


def to_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    lines = [
        "# 工作流 Runtime 健康检查",
        "",
        f"- 总状态: {'OK' if report['ok'] else 'ATTENTION'}",
        f"- 检查时间: `{report['checked_at']}`",
        f"- runtime: `{report['runtime_home']}`",
        f"- repo: `{report['repo_root']}`",
        f"- ops: `{report['ops_dir']}`",
        "",
        "## 检查项",
    ]
    for name, payload in checks.items():
        suffix = " (SKIPPED)" if payload.get("skipped") else ""
        lines.append(f"- {name}: {'OK' if payload.get('ok') else 'ATTENTION'}{suffix}")
    log_check = checks["logs"]
    lines.extend(
        [
            "",
            "## 日志摘要",
            f"- hard_error_count: `{log_check.get('hard_error_count')}`",
            f"- dns_warning_count: `{log_check.get('dns_warning_count')}`",
            f"- finding_count: `{log_check.get('finding_count')}`",
        ]
    )
    if log_check.get("findings_tail"):
        lines.append("- 最近命中:")
        for item in log_check["findings_tail"][-8:]:
            lines.append(f"  - `{item['file']}`: {item['line']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only workflow runtime health check")
    parser.add_argument("--runtime-home", default=str(DEFAULT_RUNTIME_HOME))
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--log-tail-lines", type=int, default=240)
    parser.add_argument("--log-file", action="append", default=[])
    parser.add_argument("--required-path", action="append", default=[])
    parser.add_argument("--process-match", default=os.environ.get("HARDFLOW_PROCESS_MATCH", ""))
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_healthcheck(
        HealthConfig(
            runtime_home=Path(args.runtime_home).expanduser(),
            repo_root=Path(args.repo_root).expanduser(),
            log_tail_lines=args.log_tail_lines,
            log_files=tuple(args.log_file or DEFAULT_LOG_FILES),
            required_paths=tuple(args.required_path or ()),
            process_match=str(args.process_match),
        )
    )
    if args.format == "markdown":
        print(to_markdown(report), end="")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

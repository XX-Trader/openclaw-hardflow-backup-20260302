#!/usr/bin/env python3
"""Install or update one auto-update-install job in OpenClaw jobs.json."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from scheduled_runner_prompt import build_scheduled_runner_message
from io_write_gateway import write_json_atomic

DEFAULT_JOB_ID = "a4d0b6fb-e1a0-40e4-8ae9-f5b5ebf43d09"
DEFAULT_JOB_NAME = "ops_auto_update_install_hourly"
DEFAULT_DESCRIPTION = "Hourly pull workflow repo and run installer (log-only on failure)"


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs file must be JSON object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def build_message(command: str) -> str:
    return build_scheduled_runner_message(
        str(command or "").strip(),
        role="auto update install scheduled runner",
        forbid_file_inspection=True,
    )


def normalize_shell_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return os.path.expanduser(raw).replace("\\", "/")


def scoped_job_id(base_id: str, scope: str) -> str:
    scope_text = str(scope or "").strip()
    if not scope_text:
        return str(base_id)
    return str(uuid.uuid5(uuid.UUID(str(base_id)), scope_text))


def scoped_job_name(base_name: str, scope: str) -> str:
    scope_text = str(scope or "").strip()
    if not scope_text:
        return str(base_name)
    return f"{str(base_name).strip()}:{scope_text}"


def scoped_description(base_description: str, scope: str, repo_id: str) -> str:
    tags = [text for text in (str(scope or "").strip(), str(repo_id or "").strip()) if text]
    if not tags:
        return str(base_description)
    return f"{str(base_description).strip()} [{' / '.join(tags)}]"


def build_runner_command(
    *,
    script_py: str,
    repo_path: str,
    task_id: str,
    normal_log_mode: str,
    notify_on: str,
    remote: str,
    branch: str,
    install_cmd: str,
    install_on_no_change: bool,
    git_timeout: int,
    install_timeout: int,
    report_dir: str,
    required_remote_urls: list[str],
) -> str:
    def q(value: Any) -> str:
        return str(value or "").replace("\"", "\\\"")

    cmd = (
        f"python3 \"{q(script_py)}\" --repo-path \"{q(repo_path)}\" --task-id \"{q(task_id)}\" "
        f"--normal-log-mode {q(normal_log_mode)} --notify-on {q(notify_on)} "
        f"--remote \"{q(str(remote or 'origin').strip() or 'origin')}\" "
        f"--git-timeout {max(30, int(git_timeout))} --install-timeout {max(30, int(install_timeout))} "
        f"--report-dir \"{q(report_dir)}\" --install-cmd \"{q(str(install_cmd or '').strip())}\" --auto-pull"
    )
    if str(branch).strip():
        cmd += f" --branch \"{q(str(branch).strip())}\""
    cmd += " --install-on-no-change" if install_on_no_change else " --no-install-on-no-change"
    for url in required_remote_urls:
        text = str(url or "").strip()
        if text:
            cmd += f" --require-remote-url \"{q(text)}\""
    return cmd


def upsert_job(jobs: list[dict[str, Any]], payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    job_id = str(payload.get("id", "")).strip()
    existed = False
    out: list[dict[str, Any]] = []
    for item in jobs:
        if str(item.get("id", "")).strip() == job_id:
            existed = True
            state = item.get("state") if isinstance(item.get("state"), dict) else {}
            payload["createdAtMs"] = int(item.get("createdAtMs", payload.get("createdAtMs", now_ms())))
            payload["state"] = state
            out.append(payload)
        else:
            out.append(item)
    if not existed:
        payload["state"] = {}
        out.append(payload)
    return out, existed


def main() -> None:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Install one auto-update-install job")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--job-id", default=DEFAULT_JOB_ID)
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--job-scope", default="")
    parser.add_argument("--every-ms", type=int, default=3600000)
    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/auto_update_install_runner.py"))
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--repo-id", default="")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--notify-on", default="error", choices=["error", "all"])
    parser.add_argument("--install-cmd", default="")
    parser.add_argument("--install-on-no-change", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--git-timeout", type=int, default=240)
    parser.add_argument("--install-timeout", type=int, default=2400)
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/update-install-runs"))
    parser.add_argument("--require-remote-url", action="append", default=[])
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    if not str(args.install_cmd).strip():
        raise SystemExit("--install-cmd is required")

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data["jobs"]
    scope = str(args.job_scope).strip()
    repo_id = str(args.repo_id).strip() or Path(str(args.repo_path or ".")).expanduser().name
    job_id = scoped_job_id(str(args.job_id).strip() or DEFAULT_JOB_ID, scope or repo_id)
    job_name = scoped_job_name(str(args.job_name).strip() or DEFAULT_JOB_NAME, scope or repo_id)
    report_dir = normalize_shell_path(args.report_dir)
    task_id = f"cron:{job_name}"
    ts = now_ms()
    payload = {
        "id": job_id,
        "agentId": "ops-agent",
        "name": job_name,
        "description": scoped_description(DEFAULT_DESCRIPTION, scope, repo_id),
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": max(600000, int(args.every_ms)), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": build_message(
                build_runner_command(
                    script_py=normalize_shell_path(args.runner_py),
                    repo_path=normalize_shell_path(args.repo_path),
                    task_id=task_id,
                    normal_log_mode=str(args.normal_log_mode).strip() or "silent",
                    notify_on=str(args.notify_on).strip() or "error",
                    remote=str(args.remote).strip() or "origin",
                    branch=str(args.branch).strip(),
                    install_cmd=str(args.install_cmd).strip(),
                    install_on_no_change=bool(args.install_on_no_change),
                    git_timeout=int(args.git_timeout),
                    install_timeout=int(args.install_timeout),
                    report_dir=report_dir,
                    required_remote_urls=list(args.require_remote_url or []),
                )
            ),
            "timeoutSeconds": 3000,
        },
        "delivery": {"mode": "none"},
    }

    backup_file = ""
    if jobs_path.exists():
        backup = jobs_path.with_name(f"{jobs_path.name}.bak.{stamp()}")
        shutil.copy2(jobs_path, backup)
        backup_file = str(backup)

    updated_jobs, existed = upsert_job(jobs, payload)
    data["jobs"] = updated_jobs
    write_json_atomic(jobs_path, data, ensure_ascii=False, indent=2, file_mode=0o640, dir_mode=0o750)

    result = {
        "ok": True,
        "backup": backup_file,
        "jobs_file": str(jobs_path),
        "job_id": job_id,
        "job_name": job_name,
        "job_scope": scope,
        "repo_id": repo_id,
        "repo_path": normalize_shell_path(args.repo_path),
        "report_dir": report_dir,
        "status": "updated" if existed else "created",
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return
    if backup_file:
        print(f"backup={backup_file}")
    print(f"jobs_file={jobs_path}")
    print(f"job_id={job_id}")
    print(f"job_name={job_name}")
    print(f"job_scope={scope}")
    print(f"repo_id={repo_id}")
    print(f"repo_path={normalize_shell_path(args.repo_path)}")
    print(f"report_dir={report_dir}")
    print(f"status={result['status']}")


if __name__ == "__main__":
    main()

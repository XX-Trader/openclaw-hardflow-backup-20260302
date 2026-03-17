#!/usr/bin/env python3
"""Install or update one governance evolution job in OpenClaw jobs.json."""

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

DEFAULT_JOB_ID = "4f53f7b7-2c3e-4bb1-9aab-6a62f34d4b71"
DEFAULT_JOB_NAME = "ops_governance_evolution_incremental"
DEFAULT_DESCRIPTION = "治理进化增量扫描：产出优化/审查任务，可选自动PR"


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
        role="governance evolution scheduled runner",
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
    db_file: str,
    state_file: str,
    report_dir: str,
    repo_path: str,
    openclaw_config: str,
    project_registry: str,
    repo_id: str,
    repo_name: str,
    auto_git_update: bool,
    git_update_strategy: str,
    git_fetch_timeout: int,
    max_files: int,
    min_interval_minutes: int,
    task_clarity: str,
    project_context_gate: bool,
    project_context_assignee: str,
    create_review_task: bool,
    auto_pr: bool,
    pr_base: str,
    reviewer_gh_user: str,
    push_before_pr: bool,
    normal_log_mode: str,
    task_id: str,
) -> str:
    cmd = (
        f"python3 {script_py} --db {db_file} --state-file {state_file} --report-dir {report_dir} "
        f"--mode incremental --task-id {task_id} --normal-log-mode {normal_log_mode} "
        f"--max-files {max(10, int(max_files))} --min-interval-minutes {max(1, int(min_interval_minutes))} "
        f"--task-clarity {str(task_clarity).strip() or 'ambiguous'} "
        f"--git-update-strategy {str(git_update_strategy).strip() or 'fetch'} "
        f"--git-fetch-timeout {max(30, int(git_fetch_timeout))}"
    )
    if str(repo_path).strip():
        cmd += f" --repo-path \"{str(repo_path).strip()}\""
    if str(openclaw_config).strip():
        cmd += f" --openclaw-config \"{str(openclaw_config).strip()}\""
    if str(project_registry).strip():
        cmd += f" --project-registry \"{str(project_registry).strip()}\""
    if str(repo_id).strip():
        cmd += f" --repo-id \"{str(repo_id).strip()}\""
    if str(repo_name).strip():
        cmd += f" --repo-name \"{str(repo_name).strip()}\""
    cmd += " --auto-git-update" if auto_git_update else " --no-auto-git-update"
    cmd += " --project-context-gate" if project_context_gate else " --no-project-context-gate"
    if str(project_context_assignee).strip():
        cmd += f" --project-context-assignee \"{str(project_context_assignee).strip()}\""
    if create_review_task:
        cmd += " --create-review-task"
    if auto_pr:
        cmd += f" --auto-pr --pr-base \"{str(pr_base).strip() or 'main'}\""
        if str(reviewer_gh_user).strip():
            cmd += f" --reviewer-gh-user \"{str(reviewer_gh_user).strip()}\""
        if push_before_pr:
            cmd += " --push-before-pr"
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
    parser = argparse.ArgumentParser(description="Install one governance evolution job")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--job-id", default=DEFAULT_JOB_ID)
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--job-scope", default="")
    parser.add_argument("--every-ms", type=int, default=21600000)
    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/governance_evolution_runner.py"))
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/governance-evolution/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/governance-evolution/reports"))
    parser.add_argument("--repo-path", default="")
    parser.add_argument("--openclaw-config", default=str(home / ".openclaw/openclaw.json"))
    parser.add_argument("--project-registry", default=str(home / ".openclaw/ops/task-center/project-registry.json"))
    parser.add_argument("--repo-id", default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--auto-git-update", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--git-update-strategy", default="fetch")
    parser.add_argument("--git-fetch-timeout", type=int, default=120)
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--min-interval-minutes", type=int, default=180)
    parser.add_argument("--task-clarity", default="ambiguous")
    parser.add_argument("--project-context-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project-context-assignee", default="project-agent")
    parser.add_argument("--create-review-task", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--auto-pr", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--pr-base", default="main")
    parser.add_argument("--reviewer-gh-user", default="")
    parser.add_argument("--push-before-pr", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_path = Path(args.jobs_file).expanduser()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_jobs(jobs_path)
    jobs = data["jobs"]
    scope = str(args.job_scope).strip()
    repo_id = str(args.repo_id).strip() or (Path(str(args.repo_path).strip()).name if str(args.repo_path).strip() else "")
    job_id = scoped_job_id(str(args.job_id).strip() or DEFAULT_JOB_ID, scope or repo_id)
    job_name = scoped_job_name(str(args.job_name).strip() or DEFAULT_JOB_NAME, scope or repo_id)
    state_file = normalize_shell_path(args.state_file)
    report_dir = normalize_shell_path(args.report_dir)
    task_id = f"cron:{job_name}"
    ts = now_ms()
    payload = {
        "id": job_id,
        "agentId": "optimization-agent",
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
                    db_file=normalize_shell_path(args.db),
                    state_file=state_file,
                    report_dir=report_dir,
                    repo_path=normalize_shell_path(args.repo_path),
                    openclaw_config=normalize_shell_path(args.openclaw_config),
                    project_registry=normalize_shell_path(args.project_registry),
                    repo_id=repo_id,
                    repo_name=str(args.repo_name).strip() or repo_id,
                    auto_git_update=bool(args.auto_git_update),
                    git_update_strategy=str(args.git_update_strategy),
                    git_fetch_timeout=int(args.git_fetch_timeout),
                    max_files=int(args.max_files),
                    min_interval_minutes=int(args.min_interval_minutes),
                    task_clarity=str(args.task_clarity),
                    project_context_gate=bool(args.project_context_gate),
                    project_context_assignee=str(args.project_context_assignee),
                    create_review_task=bool(args.create_review_task),
                    auto_pr=bool(args.auto_pr),
                    pr_base=str(args.pr_base),
                    reviewer_gh_user=str(args.reviewer_gh_user),
                    push_before_pr=bool(args.push_before_pr),
                    normal_log_mode=str(args.normal_log_mode),
                    task_id=task_id,
                )
            ),
            "timeoutSeconds": 2400,
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
        "state_file": state_file,
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
    print(f"state_file={state_file}")
    print(f"report_dir={report_dir}")
    print(f"status={result['status']}")


if __name__ == "__main__":
    main()

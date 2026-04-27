#!/usr/bin/env python3
"""Task Center backlog runner for controlled continuous delivery.

The runner turns eligible Task Center backlog rows into real
``smart-arb-pipeline`` executions. It deliberately skips high-risk or
human-gated work unless explicitly allowed, so cron can keep momentum without
silently bypassing safety gates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_RUNTIME_HOME = (
    os.environ.get("HARDFLOW_RUNTIME_HOME")
    or os.environ.get("OPENCLAW_HOME")
    or os.environ.get("HERMES_HOME")
    or str(Path.home() / ".hardflow-runtime")
)
RUNTIME_HOME = Path(DEFAULT_RUNTIME_HOME).expanduser()
POLICY_DIR_CANDIDATES = [
    SCRIPT_PATH.parent / "policy",
    RUNTIME_HOME / "ops" / "policy",
    Path.home() / ".openclaw" / "ops" / "policy",
    SCRIPT_PATH.parents[2] / "skills" / "library" / "control-plane-ops" / "scripts" / "policy",
]
for candidate in POLICY_DIR_CANDIDATES:
    if (candidate / "task_center.py").exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from task_center import TaskCenter, TaskCenterError, utc_now_iso  # type: ignore  # noqa: E402


DEFAULT_PIPELINE_COMMAND = str(Path.home() / ".local" / "bin" / "smart-arb-pipeline")
DEFAULT_ALLOWED_SOURCES = ("todo_patrol", "todo-deadline-bridge", "repo_hygiene_reviewer")
DEFAULT_FAILED_SOURCES = ("hermes", "todo_patrol")
DEFAULT_NEXT_ACTIONS = (
    "return_to_code_execution",
    "return_to_deployment",
    "run_external_research",
    "fix_memory_writeback",
    "fix_git_publish",
)
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
NEXT_ACTION_RE = re.compile(r"next_action=([A-Za-z0-9_-]+)")


@dataclass(frozen=True)
class BacklogCandidate:
    task_id: str
    source: str
    status: str
    priority: str
    risk_level: str
    requirement: str
    next_action: str = ""


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def compact(text: Any, limit: int = 900) -> str:
    raw = " ".join(str(text or "").replace("\r", " ").split())
    return raw[:limit] + ("..." if len(raw) > limit else "")


def parse_csv(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(value, (tuple, list)):
        parts = [str(item).strip() for item in value]
    else:
        parts = [item.strip() for item in str(value or "").split(",")]
    return tuple(item for item in parts if item)


def task_attempt_count(center: TaskCenter, task_id: str) -> int:
    outputs = center.list_task_outputs(task_id, display_safe=False)
    return sum(1 for item in outputs if str(item.get("output_type") or "") == "backlog_runner_attempt")


def latest_next_action(center: TaskCenter, task_id: str) -> str:
    outputs = center.list_task_outputs(task_id, display_safe=False)
    for item in reversed(outputs):
        summary = str(item.get("summary") or "")
        match = NEXT_ACTION_RE.search(summary)
        if match:
            return match.group(1)
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        value = str(payload.get("next_action") or "").strip()
        if value:
            return value
    incidents = center.list_task_incidents(task_id, display_safe=False)
    for item in reversed(incidents):
        summary = str(item.get("summary") or "")
        match = NEXT_ACTION_RE.search(summary)
        if match:
            return match.group(1)
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        value = str(details.get("next_action") or "").strip()
        if value:
            return value
    return ""


def is_human_blocked(task: dict[str, Any]) -> bool:
    if truthy(task.get("needs_clarification")):
        return True
    if truthy(task.get("need_human_confirm")) and not truthy(task.get("human_confirmed")):
        return True
    if str(task.get("status") or "").strip().lower() == "escalated":
        return True
    if str(task.get("action") or "").strip().lower() == "escalate_human":
        return True
    return False


def task_requirement(task: dict[str, Any], *, next_action: str = "") -> str:
    base = compact(task.get("requirement") or task.get("reason") or task.get("task_id"), 2400)
    acceptance = compact(task.get("acceptance"), 700)
    next_line = f"\n- 上次阻塞动作: {next_action}" if next_action else ""
    return (
        "持续推进 Task Center 待办，必须走 coordinator pipeline，不得绕过验证、代码审查、部署边界、记忆回写和 Git 发布门禁。\n"
        f"- Task ID: {task.get('task_id')}\n"
        f"- 来源: {task.get('source')}\n"
        f"- 原状态: {task.get('status')}\n"
        f"- 风险: {task.get('risk_level')} / 优先级: {task.get('priority')}{next_line}\n"
        f"- 需求: {base}\n"
        f"- 验收: {acceptance or '按项目事实源、测试结果、Task Center 证据和安全边界验收。'}\n"
        "安全边界：不读取、打印、提交或记录任何凭证；不启动真实交易；不下单、不撤单、不划转；"
        "遇到凭证、资金、生产破坏性操作或需求不清，必须停止并进入 human inbox。"
    )


def load_candidate_tasks(
    center: TaskCenter,
    *,
    allowed_sources: tuple[str, ...],
    failed_sources: tuple[str, ...],
    allowed_next_actions: tuple[str, ...],
    include_failed: bool,
    allow_confirmed_high_risk: bool,
    max_attempts_per_task: int,
    scan_limit: int,
) -> tuple[list[BacklogCandidate], list[dict[str, str]]]:
    rows = center.conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE status IN ('pending', 'failed')
        ORDER BY
            CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            created_at ASC
        LIMIT ?
        """,
        (max(1, min(int(scan_limit or 100), 1000)),),
    ).fetchall()
    selected: list[BacklogCandidate] = []
    skipped: list[dict[str, str]] = []
    allowed_sources_set = set(allowed_sources)
    failed_sources_set = set(failed_sources)
    allowed_next_set = set(allowed_next_actions)

    for row in rows:
        task = center._deserialize_task_row(row)
        task_id = str(task.get("task_id") or "").strip()
        source = str(task.get("source") or "").strip()
        status = str(task.get("status") or "").strip().lower()
        risk = str(task.get("risk_level") or "").strip().lower()
        next_action = ""

        if is_human_blocked(task):
            skipped.append({"task_id": task_id, "reason": "human_or_clarification_gate"})
            continue
        if risk == "high" and not (allow_confirmed_high_risk and truthy(task.get("human_confirmed"))):
            skipped.append({"task_id": task_id, "reason": "high_risk_requires_explicit_runner_flag"})
            continue
        if task_attempt_count(center, task_id) >= max(1, int(max_attempts_per_task or 1)):
            skipped.append({"task_id": task_id, "reason": "max_attempts_reached"})
            continue

        if status == "pending":
            if source not in allowed_sources_set and not task_id.startswith("todo-"):
                skipped.append({"task_id": task_id, "reason": "source_not_allowed"})
                continue
        elif status == "failed" and include_failed:
            next_action = latest_next_action(center, task_id)
            if source not in failed_sources_set:
                skipped.append({"task_id": task_id, "reason": "failed_source_not_allowed"})
                continue
            if allowed_next_set and next_action not in allowed_next_set:
                skipped.append({"task_id": task_id, "reason": f"next_action_not_allowed:{next_action or '-'}"})
                continue
        else:
            skipped.append({"task_id": task_id, "reason": "status_not_selected"})
            continue

        selected.append(
            BacklogCandidate(
                task_id=task_id,
                source=source,
                status=status,
                priority=str(task.get("priority") or "low"),
                risk_level=risk,
                requirement=task_requirement(task, next_action=next_action),
                next_action=next_action,
            )
        )
    selected.sort(key=lambda item: (PRIORITY_ORDER.get(item.priority, 3), item.task_id))
    return selected, skipped


def parse_pipeline_state(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, flags=re.S)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(1))
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def pipeline_command_parts(command: str) -> list[str]:
    raw = str(command or "").strip() or DEFAULT_PIPELINE_COMMAND
    return shlex.split(raw, posix=os.name != "nt")


def redact_requirement_arg(cmd: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for part in cmd:
        if skip_next:
            redacted.append("[omitted]")
            skip_next = False
            continue
        redacted.append(part)
        if part == "--requirement":
            skip_next = True
    return redacted


def run_candidate(
    center: TaskCenter,
    candidate: BacklogCandidate,
    *,
    pipeline_command: str,
    profile: str,
    source: str,
    timeout_seconds: int,
    actor: str,
) -> dict[str, Any]:
    center.transition_status(
        candidate.task_id,
        "running",
        actor=actor,
        stage="backlog_runner",
        details={"source": candidate.source, "next_action": candidate.next_action},
    )
    cmd = [
        *pipeline_command_parts(pipeline_command),
        "--live",
        "--profile",
        profile,
        "--source",
        source,
        "--emit-json",
        "--requirement",
        candidate.requirement,
    ]
    started_at = utc_now_iso()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(1, int(timeout_seconds or 1)),
            check=False,
        )
        state = parse_pipeline_state(proc.stdout)
        completed = int(proc.returncode) == 0 and str(state.get("status") or "").lower() in {"completed", "passed"}
        summary = (
            f"backlog runner {'completed' if completed else 'blocked'}; "
            f"pipeline_run_id={state.get('run_id') or '-'}; next_action={state.get('next_action') or '-'}"
        )
        center.record_task_output(
            task_id=candidate.task_id,
            output_type="backlog_runner_attempt",
            audience="machine",
            channel="backlog_runner",
            status="prepared",
            summary=summary,
            payload={
                "command": redact_requirement_arg(cmd),
                "returncode": int(proc.returncode),
                "pipeline_state": state,
                "stdout_excerpt": compact(proc.stdout, 1200),
                "stderr_excerpt": compact(proc.stderr, 1200),
                "started_at": started_at,
                "finished_at": utc_now_iso(),
            },
            actor=actor,
        )
        if completed:
            center.transition_status(
                candidate.task_id,
                "passed",
                actor=actor,
                stage="backlog_runner",
                details={"pipeline_run_id": state.get("run_id"), "next_action": state.get("next_action")},
            )
            for incident in center.list_task_incidents(candidate.task_id, display_safe=False):
                if str(incident.get("status") or "") == "open":
                    center.update_task_incident(
                        int(incident["id"]),
                        status="resolved",
                        summary="Resolved by backlog runner continuation.",
                        actor=actor,
                    )
        else:
            center.transition_status(
                candidate.task_id,
                "failed",
                actor=actor,
                stage="backlog_runner",
                details={"pipeline_run_id": state.get("run_id"), "next_action": state.get("next_action")},
        )
        return {
            "task_id": candidate.task_id,
            "returncode": int(proc.returncode),
            "status": "passed" if completed else "failed",
            "pipeline_run_id": state.get("run_id", ""),
            "next_action": state.get("next_action", ""),
        }
    except subprocess.TimeoutExpired as exc:
        center.record_task_output(
            task_id=candidate.task_id,
            output_type="backlog_runner_attempt",
            audience="machine",
            channel="backlog_runner",
            status="failed",
            summary="backlog runner timed out",
            payload={
                "timeout_seconds": int(timeout_seconds or 0),
                "stdout_excerpt": compact(exc.stdout, 1200),
                "stderr_excerpt": compact(exc.stderr, 1200),
                "started_at": started_at,
                "finished_at": utc_now_iso(),
            },
            actor=actor,
        )
        center.transition_status(
            candidate.task_id,
            "failed",
            actor=actor,
            stage="backlog_runner",
            details={"error": "timeout"},
        )
        return {"task_id": candidate.task_id, "returncode": -1, "status": "failed", "error": "timeout"}
    except OSError as exc:
        next_action = "fix_backlog_runner_pipeline_command"
        center.record_task_output(
            task_id=candidate.task_id,
            output_type="backlog_runner_attempt",
            audience="machine",
            channel="backlog_runner",
            status="failed",
            summary=f"backlog runner launch failed; next_action={next_action}",
            payload={
                "command": redact_requirement_arg(cmd),
                "error_type": type(exc).__name__,
                "error": compact(exc, 1200),
                "started_at": started_at,
                "finished_at": utc_now_iso(),
            },
            actor=actor,
        )
        center.transition_status(
            candidate.task_id,
            "failed",
            actor=actor,
            stage="backlog_runner",
            details={
                "error": "pipeline_launch_failed",
                "error_type": type(exc).__name__,
                "next_action": next_action,
            },
        )
        return {
            "task_id": candidate.task_id,
            "returncode": -1,
            "status": "failed",
            "error": "pipeline_launch_failed",
            "next_action": next_action,
        }


def run_backlog(config: argparse.Namespace) -> dict[str, Any]:
    center = TaskCenter(Path(config.task_db).expanduser())
    try:
        center.init_schema()
        candidates, skipped = load_candidate_tasks(
            center,
            allowed_sources=parse_csv(config.allowed_source),
            failed_sources=parse_csv(config.failed_source),
            allowed_next_actions=parse_csv(config.allowed_next_action),
            include_failed=bool(config.include_failed),
            allow_confirmed_high_risk=bool(config.allow_confirmed_high_risk),
            max_attempts_per_task=int(config.max_attempts_per_task),
            scan_limit=int(config.scan_limit),
        )
        selected = candidates[: max(1, int(config.max_items or 1))]
        report: dict[str, Any] = {
            "selected": [
                {
                    "task_id": item.task_id,
                    "source": item.source,
                    "status": item.status,
                    "priority": item.priority,
                    "risk_level": item.risk_level,
                    "next_action": item.next_action,
                }
                for item in selected
            ],
            "skipped": skipped[:50],
            "executed": [],
            "dry_run": bool(config.dry_run),
        }
        if config.dry_run:
            return report
        for candidate in selected:
            report["executed"].append(
                run_candidate(
                    center,
                    candidate,
                    pipeline_command=str(config.pipeline_command),
                    profile=str(config.profile),
                    source=str(config.source),
                    timeout_seconds=int(config.pipeline_timeout_seconds),
                    actor=str(config.actor),
                )
            )
        return report
    finally:
        center.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuously advance eligible Task Center backlog items.")
    parser.add_argument("--task-db", default=str(RUNTIME_HOME / "ops" / "task-center" / "task_center.db"))
    parser.add_argument("--pipeline-command", default=DEFAULT_PIPELINE_COMMAND)
    parser.add_argument("--profile", default=os.environ.get("SMART_ARB_BACKLOG_PROFILE", "spreadagent"))
    parser.add_argument("--source", default="backlog-runner")
    parser.add_argument("--actor", default="backlog-runner")
    parser.add_argument("--max-items", type=int, default=1)
    parser.add_argument("--scan-limit", type=int, default=100)
    parser.add_argument("--max-attempts-per-task", type=int, default=1)
    parser.add_argument("--pipeline-timeout-seconds", type=int, default=int(os.environ.get("BACKLOG_RUNNER_PIPELINE_TIMEOUT_SECONDS", "3600")))
    parser.add_argument("--allowed-source", default=",".join(DEFAULT_ALLOWED_SOURCES))
    parser.add_argument("--failed-source", default=",".join(DEFAULT_FAILED_SOURCES))
    parser.add_argument("--allowed-next-action", default=",".join(DEFAULT_NEXT_ACTIONS))
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--allow-confirmed-high-risk", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_backlog(args)
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"FAILED backlog_runner: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not report.get("selected"):
        print("NO_REPLY")
    else:
        executed = report.get("executed") or []
        print(
            "backlog_runner selected={selected} executed={executed}".format(
                selected=len(report.get("selected") or []),
                executed=len(executed),
            )
        )
        for item in executed:
            print(
                "- task_id={task_id} status={status} pipeline_run_id={pipeline_run_id} next_action={next_action}".format(
                    **{key: str(item.get(key, "")) for key in ["task_id", "status", "pipeline_run_id", "next_action"]}
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

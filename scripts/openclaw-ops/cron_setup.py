#!/usr/bin/env python3
"""Install OpenClaw hardflow cron jobs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ops_cron_runner import default_config as runner_default_config
except Exception:  # pragma: no cover
    runner_default_config = None

LOG_MODES = {"silent", "chat"}
API_ENGINES = {"http", "playwright", "selenium"}


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_api_engine(value: str, default: str = "playwright") -> str:
    engine = str(value or "").strip().lower()
    return engine if engine in API_ENGINES else default


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "jobs": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("jobs file must be a JSON object")
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    if "version" not in data:
        data["version"] = 1
    return data


def infer_delivery(jobs: list[dict[str, Any]], preferred_agents: list[str]) -> tuple[str, str]:
    for aid in preferred_agents:
        for job in jobs:
            if str(job.get("agentId", "")).strip() != aid:
                continue
            delivery = job.get("delivery") or {}
            channel = str(delivery.get("channel", "")).strip()
            target = str(delivery.get("to", "")).strip()
            if channel and target:
                return channel, target
    return "telegram", ""


def ensure_monitor_config(config_file: Path, overwrite: bool, switches: dict[str, str]) -> dict[str, Any]:
    if config_file.exists() and not overwrite:
        data = json.loads(config_file.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            data = {}
    else:
        base = runner_default_config() if callable(runner_default_config) else {}
        if isinstance(base, dict):
            data = base
        else:
            home = Path(os.path.expanduser("~"))
            data = {
                "schema_version": "2026-03-02",
                "log_roots": [
                    str(home / ".openclaw/workspace-ops-agent/ops"),
                    str(home / ".openclaw/workspace-ops-agent/ops/logs"),
                    str(home / ".openclaw/workflows"),
                ],
                "log_patterns": ["*.log", "**/*.log", "*.out", "**/*.out"],
                "max_log_files": 120,
                "incremental_max_bytes_per_file": 262144,
                "full_scan_tail_bytes_per_file": 1048576,
                "auto_resolve_after_missed_runs": 2,
                "fallback_full_on_incremental_error": True,
                "incremental_full_backstop_runs": 96,
                "daily": {"major_only": True, "window_hours": 24, "top_issue_limit": 8},
            }

    current = data.get("skill_log_switches")
    if not isinstance(current, dict):
        current = {}
    for skill, mode in switches.items():
        node = current.get(skill)
        if not isinstance(node, dict):
            node = {}
        node["normal_log_mode"] = normalize_log_mode(mode, default="silent")
        node["risk_always_notify"] = True
        current[skill] = node
    data["skill_log_switches"] = current

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def build_message(command: str) -> str:
    return (
        "你是 ops-agent 定时任务执行器。"
        "只执行以下命令，不要执行其他命令，也不要改写命令参数："
        f"{command}。"
        "将命令标准输出原样作为唯一回复；若输出为 NO_REPLY，则只回复 NO_REPLY。"
    )


def build_core_jobs(
    *,
    runner_py: str,
    config_file: str,
    state_file: str,
    history_dir: str,
    every_ms: int,
    full_expr: str,
    daily_expr: str,
    tz_name: str,
    daily_major_only: bool,
    incremental_log_mode: str,
    full_log_mode: str,
    daily_log_mode: str,
) -> list[dict[str, Any]]:
    ts = now_ms()
    cmd_base = f"python3 {runner_py} --config {config_file} --state-file {state_file} --history-dir {history_dir}"
    cmd_inc = (
        f"{cmd_base} --mode incremental --task-id cron:ops-incremental-monitor "
        f"--normal-log-mode {normalize_log_mode(incremental_log_mode)}"
    )
    cmd_full = (
        f"{cmd_base} --mode full --task-id cron:ops-full-calibration "
        f"--normal-log-mode {normalize_log_mode(full_log_mode)}"
    )
    cmd_daily = (
        f"{cmd_base} --mode daily --task-id cron:ops-daily-summary "
        f"--normal-log-mode {normalize_log_mode(daily_log_mode)}"
    )
    if daily_major_only:
        cmd_daily += " --daily-major-only"

    return [
        {
            "id": "c9a4f4c4-4f47-4da3-a571-6bc7c3fbd2f8",
            "agentId": "ops-agent",
            "name": "ops_incremental_monitor",
            "description": "增量日志巡检与问题闭环（可配置日志开关）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_inc), "timeoutSeconds": 1800},
        },
        {
            "id": "9bd05850-bca8-4a0a-af67-67e2d5d2af9f",
            "agentId": "ops-agent",
            "name": "ops_full_calibration",
            "description": "全量校准扫描（增量异常自动回退兜底）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": full_expr, "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_full), "timeoutSeconds": 2400},
        },
        {
            "id": "621ee42b-efef-4ac7-88db-4971bb9a7f86",
            "agentId": "ops-agent",
            "name": "ops_daily_summary",
            "description": "每日日报汇总（可配置日志开关）",
            "enabled": True,
            "createdAtMs": ts,
            "updatedAtMs": ts,
            "schedule": {"kind": "cron", "expr": daily_expr, "tz": tz_name},
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn", "message": build_message(cmd_daily), "timeoutSeconds": 1800},
        },
    ]


def build_system_schedule_job(
    *,
    script_py: str,
    output_dir: str,
    state_file: str,
    every_ms: int,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --output-dir {output_dir} --state-file {state_file} "
        f"--task-id cron:ops-system-schedule-audit --normal-log-mode {normalize_log_mode(log_mode)}"
    )
    return {
        "id": "f603d2ac-2dcf-4f7a-9efe-26f0e0f8d24e",
        "agentId": "ops-agent",
        "name": "ops_system_schedule_audit",
        "description": "系统定时+OpenClaw定时快照审计（高风险强制提醒）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "every", "everyMs": int(every_ms), "anchorMs": ts},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1200},
    }


def build_api_test_job(
    *,
    script_py: str,
    config_file: str,
    state_file: str,
    history_dir: str,
    expr: str,
    tz_name: str,
    engine: str,
    log_mode: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --config-file {config_file} --state-file {state_file} --history-dir {history_dir} "
        f"--task-id cron:ops-api-test --engine {normalize_api_engine(engine)} "
        f"--normal-log-mode {normalize_log_mode(log_mode)}"
    )
    return {
        "id": "1a45d6d8-8dde-4fc7-b25e-45c3f57ec31e",
        "agentId": "ops-agent",
        "name": "ops_api_test_audit",
        "description": "接口全量测试（一次执行，无重复重测），空返回/旧数据高风险",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1800},
    }


def build_daily_work_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    report_dir: str,
    expr: str,
    tz_name: str,
    log_mode: str,
    webhook_env: str,
    secret_env: str,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --db {db_file} --state-file {state_file} --report-dir {report_dir} "
        f"--task-id cron:ops-daily-work-report --normal-log-mode {normalize_log_mode(log_mode)} "
        f"--dingtalk-webhook-env {webhook_env} --dingtalk-secret-env {secret_env}"
    )
    return {
        "id": "9873ab34-c4af-4db0-8cd5-40df68f92efd",
        "agentId": "ops-agent",
        "name": "ops_daily_work_report_dingtalk",
        "description": "每日工作报告（todo/done 增量去重，仅新增记录推送钉钉）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1200},
    }


def build_self_evolution_job(
    *,
    script_py: str,
    db_file: str,
    state_file: str,
    report_dir: str,
    expr: str,
    tz_name: str,
    log_mode: str,
    min_review_interval_days: int,
    max_tasks_per_run: int,
) -> dict[str, Any]:
    ts = now_ms()
    cmd = (
        f"python3 {script_py} --db {db_file} --state-file {state_file} --report-dir {report_dir} "
        f"--task-id cron:ops-self-evolution --normal-log-mode {normalize_log_mode(log_mode)} "
        f"--min-review-interval-days {max(1, int(min_review_interval_days))} "
        f"--max-tasks-per-run {max(1, int(max_tasks_per_run))}"
    )
    return {
        "id": "9cf2677f-0ea1-4f07-a8cb-7dff4ff7c52b",
        "agentId": "ops-agent",
        "name": "ops_self_evolution_weekly_todo",
        "description": "周度自我进化复盘（只产出建议任务包到TODO，低优先级，人工确认）",
        "enabled": True,
        "createdAtMs": ts,
        "updatedAtMs": ts,
        "schedule": {"kind": "cron", "expr": expr, "tz": tz_name},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": build_message(cmd), "timeoutSeconds": 1800},
    }


def upsert_jobs(
    jobs: list[dict[str, Any]],
    fresh_jobs: list[dict[str, Any]],
    channel: str,
    target: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ts = now_ms()
    by_id = {str(item.get("id", "")): item for item in jobs if isinstance(item, dict)}
    status: dict[str, str] = {}

    for item in fresh_jobs:
        jid = str(item.get("id", "")).strip()
        old = by_id.get(jid)
        if isinstance(old, dict):
            item["createdAtMs"] = int(old.get("createdAtMs", item.get("createdAtMs", ts)))
            old_state = old.get("state") if isinstance(old.get("state"), dict) else {}
            item["state"] = old_state
            item["updatedAtMs"] = ts
            status[jid] = "updated"
        else:
            item["state"] = {}
            status[jid] = "created"

        item["delivery"] = {"mode": "announce", "channel": channel, "to": target}
        if item.get("schedule", {}).get("kind") == "every":
            item["state"]["nextRunAtMs"] = ts + int(item["schedule"].get("everyMs", 0))
        by_id[jid] = item

    ordered: list[dict[str, Any]] = []
    replaced = set(status)
    for old in jobs:
        jid = str(old.get("id", ""))
        if jid in replaced:
            ordered.append(by_id[jid])
            replaced.remove(jid)
        else:
            ordered.append(old)
    for jid in status:
        if all(str(x.get("id", "")) != jid for x in ordered):
            ordered.append(by_id[jid])
    return ordered, status


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Install OpenClaw hardflow cron jobs")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))

    parser.add_argument("--runner-py", default=str(home / ".openclaw/ops/ops_cron_runner.py"))
    parser.add_argument("--config-file", default=str(home / ".openclaw/ops/cron-monitor-config.json"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/cron-monitor-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/cron-runs"))
    parser.add_argument("--incremental-every-ms", type=int, default=900000)
    parser.add_argument("--full-expr", default="23 */6 * * *")
    parser.add_argument("--daily-expr", default="5 0 * * *")
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--daily-major-only", action="store_true")
    parser.add_argument("--incremental-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--full-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--daily-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-system-schedule-job", action="store_true")
    parser.add_argument("--system-schedule-py", default=str(home / ".openclaw/ops/system_schedule_snapshot.py"))
    parser.add_argument("--system-snapshot-dir", default=str(home / ".openclaw/ops/system-schedule/snapshots"))
    parser.add_argument("--system-state-file", default=str(home / ".openclaw/ops/system-schedule/state.json"))
    parser.add_argument("--system-every-ms", type=int, default=1800000)
    parser.add_argument("--system-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-api-test-job", action="store_true")
    parser.add_argument("--api-test-py", default=str(home / ".openclaw/ops/api_test_audit.py"))
    parser.add_argument("--api-test-config", default=str(home / ".openclaw/ops/api-test-config.json"))
    parser.add_argument("--api-test-state", default=str(home / ".openclaw/ops/api-test-state.json"))
    parser.add_argument("--api-test-history-dir", default=str(home / ".openclaw/ops/api-test-runs"))
    parser.add_argument("--api-test-expr", default="*/15 * * * *")
    parser.add_argument("--api-test-engine", default="playwright", choices=sorted(API_ENGINES))
    parser.add_argument("--api-test-log-mode", default="silent", choices=sorted(LOG_MODES))

    parser.add_argument("--install-daily-work-job", action="store_true")
    parser.add_argument("--daily-work-py", default=str(home / ".openclaw/ops/daily_work_report.py"))
    parser.add_argument("--daily-work-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--daily-work-state", default=str(home / ".openclaw/ops/daily-work/state.json"))
    parser.add_argument("--daily-work-report-dir", default=str(home / ".openclaw/ops/daily-work/reports"))
    parser.add_argument("--daily-work-expr", default="15 0 * * *")
    parser.add_argument("--daily-work-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--dingtalk-webhook-env", default="DINGTALK_WEBHOOK_URL")
    parser.add_argument("--dingtalk-secret-env", default="DINGTALK_SECRET")

    parser.add_argument("--install-self-evolution-job", action="store_true")
    parser.add_argument("--self-evolution-py", default=str(home / ".openclaw/ops/self_evolution_todo.py"))
    parser.add_argument("--self-evolution-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--self-evolution-state", default=str(home / ".openclaw/ops/self-evolution/state.json"))
    parser.add_argument("--self-evolution-report-dir", default=str(home / ".openclaw/ops/self-evolution/reports"))
    parser.add_argument("--self-evolution-expr", default="30 3 * * 1")
    parser.add_argument("--self-evolution-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--self-evolution-min-interval-days", type=int, default=7)
    parser.add_argument("--self-evolution-max-tasks-per-run", type=int, default=3)

    parser.add_argument("--channel", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--overwrite-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_file = Path(args.jobs_file).expanduser()
    config_file = Path(args.config_file).expanduser()
    jobs_file.parent.mkdir(parents=True, exist_ok=True)

    data = load_jobs(jobs_file)
    jobs = data.get("jobs", [])

    channel = str(args.channel or "").strip()
    target = str(args.to or "").strip()
    if not channel or not target:
        got_channel, got_target = infer_delivery(jobs, ["ops-agent", "coordinator", "project-agent"])
        channel = channel or got_channel
        target = target or got_target
    if not target:
        raise SystemExit("missing delivery target: pass --to or keep existing delivery target")

    cfg = ensure_monitor_config(
        config_file=config_file,
        overwrite=bool(args.overwrite_config),
        switches={
            "incremental": args.incremental_log_mode,
            "full": args.full_log_mode,
            "daily": args.daily_log_mode,
            "api_test": args.api_test_log_mode,
            "system_schedule": args.system_log_mode,
            "daily_work": args.daily_work_log_mode,
            "self_evolution": args.self_evolution_log_mode,
        },
    )

    fresh_jobs = build_core_jobs(
        runner_py=str(Path(args.runner_py).expanduser()),
        config_file=str(config_file),
        state_file=str(Path(args.state_file).expanduser()),
        history_dir=str(Path(args.history_dir).expanduser()),
        every_ms=int(args.incremental_every_ms),
        full_expr=str(args.full_expr),
        daily_expr=str(args.daily_expr),
        tz_name=str(args.tz),
        daily_major_only=bool(args.daily_major_only),
        incremental_log_mode=args.incremental_log_mode,
        full_log_mode=args.full_log_mode,
        daily_log_mode=args.daily_log_mode,
    )
    if bool(args.install_system_schedule_job):
        fresh_jobs.append(
            build_system_schedule_job(
                script_py=str(Path(args.system_schedule_py).expanduser()),
                output_dir=str(Path(args.system_snapshot_dir).expanduser()),
                state_file=str(Path(args.system_state_file).expanduser()),
                every_ms=int(args.system_every_ms),
                log_mode=args.system_log_mode,
            )
        )
    if bool(args.install_api_test_job):
        fresh_jobs.append(
            build_api_test_job(
                script_py=str(Path(args.api_test_py).expanduser()),
                config_file=str(Path(args.api_test_config).expanduser()),
                state_file=str(Path(args.api_test_state).expanduser()),
                history_dir=str(Path(args.api_test_history_dir).expanduser()),
                expr=str(args.api_test_expr),
                tz_name=str(args.tz),
                engine=str(args.api_test_engine),
                log_mode=args.api_test_log_mode,
            )
        )
    if bool(args.install_daily_work_job):
        fresh_jobs.append(
            build_daily_work_job(
                script_py=str(Path(args.daily_work_py).expanduser()),
                db_file=str(Path(args.daily_work_db).expanduser()),
                state_file=str(Path(args.daily_work_state).expanduser()),
                report_dir=str(Path(args.daily_work_report_dir).expanduser()),
                expr=str(args.daily_work_expr),
                tz_name=str(args.tz),
                log_mode=args.daily_work_log_mode,
                webhook_env=str(args.dingtalk_webhook_env),
                secret_env=str(args.dingtalk_secret_env),
            )
        )
    if bool(args.install_self_evolution_job):
        fresh_jobs.append(
            build_self_evolution_job(
                script_py=str(Path(args.self_evolution_py).expanduser()),
                db_file=str(Path(args.self_evolution_db).expanduser()),
                state_file=str(Path(args.self_evolution_state).expanduser()),
                report_dir=str(Path(args.self_evolution_report_dir).expanduser()),
                expr=str(args.self_evolution_expr),
                tz_name=str(args.tz),
                log_mode=args.self_evolution_log_mode,
                min_review_interval_days=int(args.self_evolution_min_interval_days),
                max_tasks_per_run=int(args.self_evolution_max_tasks_per_run),
            )
        )

    merged_jobs, status = upsert_jobs(jobs=jobs, fresh_jobs=fresh_jobs, channel=channel, target=target)
    data["jobs"] = merged_jobs

    backup_file = ""
    if jobs_file.exists() and not args.dry_run:
        backup = jobs_file.with_name(f"{jobs_file.name}.bak.{stamp()}")
        shutil.copy2(jobs_file, backup)
        backup_file = str(backup)
    if not args.dry_run:
        jobs_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "jobs_file": str(jobs_file),
        "backup": backup_file,
        "config_file": str(config_file),
        "delivery": {"channel": channel, "to": target},
        "job_status": status,
        "job_ids": [item["id"] for item in fresh_jobs],
        "skill_log_switches": cfg.get("skill_log_switches", {}),
        "installed": {
            "core_jobs": True,
            "system_schedule_job": bool(args.install_system_schedule_job),
            "api_test_job": bool(args.install_api_test_job),
            "daily_work_job": bool(args.install_daily_work_job),
            "self_evolution_job": bool(args.install_self_evolution_job),
        },
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if backup_file:
            print(f"backup={backup_file}")
        print(f"jobs_file={jobs_file}")
        print(f"config_file={config_file}")
        for jid in result["job_ids"]:
            print(f"{jid}={status.get(jid, 'unknown')}")
        print(f"delivery={channel}:{target}")
        print(json.dumps(result["installed"], ensure_ascii=False))
        if args.dry_run:
            print("dry_run=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

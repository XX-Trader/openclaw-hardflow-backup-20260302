#!/usr/bin/env python3
"""Export a unified workflow schedule registry snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TZ = timezone(timedelta(hours=8))
SURFACE_TYPES = {
    "openclaw_cron",
    "systemd_timer",
    "user_crontab",
    "root_crontab",
    "cron_d",
    "saas_scheduler",
}

KNOWN_SCHEDULE_METADATA: dict[str, dict[str, Any]] = {
    "TODO 巡检（15分钟）": {
        "owner_agent": "ops-agent",
        "executor_agent": "ops-agent",
        "capability": "todo_dispatch",
        "purpose": "巡检 TODO 并派发未分配任务",
        "flow_summary": "todo_patrol.py -> 扫描 TODO -> 去重 -> 请求 coordinator 分配",
        "required_skills_or_runtime": ["task_center.db", "todo_patrol.py", "coordinator-routing"],
        "outputs": ["任务摘要", "派发请求", "巡检事件"],
        "human_visibility": "仅异常或有新增时可见",
        "delivery_mode": "none",
        "health_signals": ["去重正常", "任务派发成功", "状态更新成功"],
        "failure_signals": ["解析 TODO 失败", "调度超时", "分配失败"],
        "maintenance_entry": "install_todo_patrol_job.py / todo_patrol.py",
    },
    "task_executor_10m": {
        "owner_agent": "ops-agent",
        "executor_agent": "assignee-router",
        "capability": "task_execution_orchestration",
        "purpose": "按 assignee 执行待办修复任务",
        "flow_summary": "task_executor_runner.py -> next-todo -> agent adapter -> report-agent-result",
        "required_skills_or_runtime": ["task_center.db", "policy_enforcer.py", "openclaw gateway", "lightContext"],
        "outputs": ["执行报告", "任务状态回写", "修复证据"],
        "human_visibility": "默认仅异常时可见",
        "delivery_mode": "announce",
        "health_signals": ["任务选择成功", "agent 调用成功", "report-agent-result 成功"],
        "failure_signals": ["partial", "failed", "cron timeout", "gateway error"],
        "maintenance_entry": "install_task_executor_job.py / policy/task_executor_runner.py",
    },
    "project_index_maintainer_30m": {
        "owner_agent": "project-agent",
        "executor_agent": "project-agent",
        "capability": "maintain_project_index",
        "purpose": "维护项目索引与上下文入口，记录上次已索引的 git HEAD",
        "flow_summary": "project_index_maintainer.py -> 比对已索引 git HEAD -> 有变更再刷新索引 -> 回写 task-center",
        "required_skills_or_runtime": ["project-registry.json", "task_center.db"],
        "outputs": ["项目索引", "项目索引状态", "上下文任务"],
        "human_visibility": "默认静默",
        "delivery_mode": "none",
        "health_signals": ["索引文件可写", "项目发现正常", "git HEAD 留痕可追踪"],
        "failure_signals": ["network_error", "git pull 失败", "索引回写失败"],
        "maintenance_entry": "install_project_index_job.py / policy/project_index_maintainer.py",
    },
    "ops_git_sync_push": {
        "owner_agent": "optimization-agent",
        "executor_agent": "optimization-agent",
        "capability": "workflow_git_sync",
        "purpose": "自动同步 workflow 仓库并推送",
        "flow_summary": "git_sync_push_runner.py -> pull/fetch -> commit -> push",
        "required_skills_or_runtime": ["git", "remote origin", "repo policy"],
        "outputs": ["git 同步报告", "commit/push 结果"],
        "human_visibility": "默认静默",
        "delivery_mode": "none",
        "health_signals": ["push 成功", "变更集受控"],
        "failure_signals": ["冲突", "push 失败", "远端不匹配"],
        "maintenance_entry": "cron_setup.py / git_sync_push_runner.py",
    },
    "ops_governance_evolution_incremental": {
        "owner_agent": "optimization-agent",
        "executor_agent": "optimization-agent",
        "capability": "governance_evolution",
        "purpose": "扫描治理问题、生成优化任务，并可选创建/更新 auto-pr",
        "flow_summary": "governance_evolution_runner.py -> 扫描 hooks/plugins/workflows -> 派生任务 -> 可选 create/update PR",
        "required_skills_or_runtime": ["project-registry.json", "task_center.db", "git"],
        "outputs": ["治理报告", "优化任务"],
        "human_visibility": "默认静默",
        "delivery_mode": "none",
        "health_signals": ["扫描成功", "任务派生成功"],
        "failure_signals": ["git 失败", "超时", "质量阈值不足"],
        "maintenance_entry": "cron_setup.py / governance_evolution_runner.py",
    },
    "ops_self_evolution_weekly_todo": {
        "owner_agent": "ops-agent",
        "executor_agent": "ops-agent",
        "capability": "self_reflection_packaging",
        "purpose": "周度复盘并生成自进化任务包",
        "flow_summary": "self_evolution_todo.py -> 评分 -> build TODO package",
        "required_skills_or_runtime": ["task_center.db", "history reports"],
        "outputs": ["TODO 建议包", "复盘报告"],
        "human_visibility": "默认静默",
        "delivery_mode": "none",
        "health_signals": ["评分链完整", "建议包生成成功"],
        "failure_signals": ["统计缺失", "超时"],
        "maintenance_entry": "cron_setup.py / self_evolution_todo.py",
    },
    "reviewer_git_update_hourly": {
        "owner_agent": "reviewer",
        "executor_agent": "reviewer",
        "capability": "pr_review_gate",
        "purpose": "小时级 PR 审查与自动合并 gate",
        "flow_summary": "reviewer_cron_runner.py --mode hourly_git --check-pr [--pr-gate-only] -> review open PR -> approval-gated merge",
        "required_skills_or_runtime": ["workspace", "reviewer profile", "lightContext"],
        "outputs": ["审查结果", "PR 检查记录"],
        "human_visibility": "有发现或失败时可见",
        "delivery_mode": "announce",
        "health_signals": ["扫描完成", "审查报告生成"],
        "failure_signals": ["git 读取失败", "超时"],
        "maintenance_entry": "install_reviewer_scan_jobs.py / reviewer_cron_runner.py",
    },
    "reviewer_incremental_daily_4am": {
        "owner_agent": "reviewer",
        "executor_agent": "reviewer",
        "capability": "daily_incremental_review",
        "purpose": "每日增量技术债审查",
        "flow_summary": "reviewer_cron_runner.py --mode daily_incremental --fix",
        "required_skills_or_runtime": ["workspace", "project context gate", "lightContext"],
        "outputs": ["技术债报告", "修复建议", "可选 fix 调用"],
        "human_visibility": "每日可见；无内容时应静默",
        "delivery_mode": "announce",
        "health_signals": ["报告产出", "去重生效"],
        "failure_signals": ["cron timeout", "上下文门失败"],
        "maintenance_entry": "install_reviewer_scan_jobs.py / reviewer_cron_runner.py",
    },
    "reviewer_recurring_bi_daily": {
        "owner_agent": "reviewer",
        "executor_agent": "reviewer",
        "capability": "recurring_issue_review",
        "purpose": "双日 recurring issue 扫描",
        "flow_summary": "reviewer_cron_runner.py --mode bi_daily_recurring",
        "required_skills_or_runtime": ["workspace", "review history"],
        "outputs": ["recurring issue 报告"],
        "human_visibility": "有发现时可见",
        "delivery_mode": "announce",
        "health_signals": ["去重稳定"],
        "failure_signals": ["重复告警失控", "超时"],
        "maintenance_entry": "install_reviewer_scan_jobs.py / reviewer_cron_runner.py",
    },
    "reviewer_weekly_structure_review": {
        "owner_agent": "reviewer",
        "executor_agent": "reviewer",
        "capability": "weekly_structure_review",
        "purpose": "周级结构审查",
        "flow_summary": "reviewer_cron_runner.py --mode weekly_structure",
        "required_skills_or_runtime": ["workspace", "project context gate", "lightContext"],
        "outputs": ["结构问题清单", "周报"],
        "human_visibility": "周级可见",
        "delivery_mode": "announce",
        "health_signals": ["结构问题可聚合", "历史对比稳定"],
        "failure_signals": ["超时", "空报告未静默"],
        "maintenance_entry": "install_reviewer_scan_jobs.py / reviewer_cron_runner.py",
    },
    "agent-factory 自动创建(P1/P2)": {
        "owner_agent": "agent-factory",
        "executor_agent": "agent-factory",
        "capability": "auto_create_high_priority_agents",
        "purpose": "扫描 agent 缺口并自动创建高优先级 agent",
        "flow_summary": "agent_gap_queue.py -> auto_create_agents_from_queue.py",
        "required_skills_or_runtime": ["agent factory workspace", "gap queue"],
        "outputs": ["创建结果", "缺口队列状态"],
        "human_visibility": "默认静默",
        "delivery_mode": "none",
        "health_signals": ["队列消耗正常", "创建成功"],
        "failure_signals": ["队列堆积", "创建失败"],
        "maintenance_entry": "legacy cron/jobs.json / agent-factory scripts",
    },
}

EXTERNAL_SCHEDULES = [
    {
        "schedule_name": "Host systemd timers",
        "surface_type": "systemd_timer",
        "owner_agent": "ops-agent",
        "executor_agent": "systemd",
        "purpose": "纳管主机级 timer/service 调度面",
        "trigger": "system timer fire + snapshot poll",
        "flow_summary": "systemd 执行 -> system_schedule_snapshot.py 采样 -> 指纹对比 -> 事件化",
        "required_skills_or_runtime": ["systemctl", "system_schedule_snapshot.py"],
        "outputs": ["system schedule snapshots", "风险事件"],
        "human_visibility": "仅变更或高风险时可见",
        "delivery_mode": "ops_system_schedule_audit",
        "health_signals": ["关键 timer 不丢失", "快照可写"],
        "failure_signals": ["critical_timer_missing", "systemctl exit", "snapshot 写入失败"],
        "maintenance_entry": "system_schedule_snapshot.py / cron_setup.py",
    },
    {
        "schedule_name": "Attached user crontab",
        "surface_type": "user_crontab",
        "owner_agent": "ops-agent",
        "executor_agent": "host user cron",
        "purpose": "纳管用户级 crontab 任务",
        "trigger": "crontab fire + snapshot poll",
        "flow_summary": "user crontab 执行外部脚本 -> 快照 -> 指纹变化生成事件",
        "required_skills_or_runtime": ["crontab -l", "snapshot store"],
        "outputs": ["user crontab 行集合", "变化事件"],
        "human_visibility": "仅变更或风险时可见",
        "delivery_mode": "ops_system_schedule_audit",
        "health_signals": ["行集稳定", "来源可追踪"],
        "failure_signals": ["unknown crontab entry", "snapshot drift"],
        "maintenance_entry": "system_schedule_snapshot.py",
    },
    {
        "schedule_name": "Attached root crontab",
        "surface_type": "root_crontab",
        "owner_agent": "ops-agent",
        "executor_agent": "root cron",
        "purpose": "纳管 root 级 privileged cron 面",
        "trigger": "root cron fire + snapshot poll",
        "flow_summary": "sudo -n crontab -l 采样 -> 对比 -> 事件化",
        "required_skills_or_runtime": ["sudo -n", "crontab -l"],
        "outputs": ["root crontab 行集合", "风险原因"],
        "human_visibility": "仅高风险时可见",
        "delivery_mode": "ops_system_schedule_audit",
        "health_signals": ["root 行集合稳定", "权限检查通过"],
        "failure_signals": ["sudo denied", "unknown root task"],
        "maintenance_entry": "system_schedule_snapshot.py",
    },
    {
        "schedule_name": "Attached /etc/cron.d entries",
        "surface_type": "cron_d",
        "owner_agent": "ops-agent",
        "executor_agent": "cron daemon",
        "purpose": "纳管 /etc/cron.d 中的项目调度",
        "trigger": "cron.d entry fire + snapshot poll",
        "flow_summary": "读取 /etc/cron.d -> 文件指纹对比 -> 事件化",
        "required_skills_or_runtime": ["filesystem access", "snapshot store"],
        "outputs": ["cron_d 文件列表", "内容摘要"],
        "human_visibility": "仅变更或风险时可见",
        "delivery_mode": "ops_system_schedule_audit",
        "health_signals": ["目录存在", "文件集稳定"],
        "failure_signals": ["目录缺失", "未知条目新增"],
        "maintenance_entry": "system_schedule_snapshot.py",
    },
    {
        "schedule_name": "Attached SaaS schedulers",
        "surface_type": "saas_scheduler",
        "owner_agent": "ops-agent",
        "executor_agent": "external SaaS",
        "purpose": "把第三方机器人/SaaS 平台内部调度纳入统一登记与审计",
        "trigger": "vendor scheduler fire",
        "flow_summary": "SaaS 调度 -> webhook/bridge -> WorkflowRun -> 统一事件/状态/证据",
        "required_skills_or_runtime": ["webhook/gateway", "auth", "external run id mapping"],
        "outputs": ["外部 run 映射", "DeliveryRecord", "回执证据"],
        "human_visibility": "按策略展示",
        "delivery_mode": "delivery_center",
        "health_signals": ["外部 run id 可映射", "回执完整"],
        "failure_signals": ["未登记上线", "认证失败", "孤儿 run"],
        "maintenance_entry": "Schedule Registry / Delivery Center",
    },
]


def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_mapping_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw.startswith("- "):
            continue
        parts = [part.strip() for part in raw[2:].split("|")]
        if len(parts) < 3:
            continue
        schedule_id = parts[0]
        schedule_name = parts[1]
        agent_part = next((part for part in parts if part.startswith("agent=")), "")
        agent_name = agent_part.split("=", 1)[1].strip() if "=" in agent_part else ""
        if schedule_id and agent_name:
            mapping[schedule_id] = agent_name
        if schedule_name and agent_name:
            mapping[schedule_name] = agent_name
    return mapping


def normalize_trigger(job: dict[str, Any]) -> str:
    schedule = job.get("schedule")
    if not isinstance(schedule, dict):
        return "-"
    if str(schedule.get("cron", "")).strip():
        return str(schedule.get("cron", "")).strip()
    every_ms = schedule.get("everyMs")
    if every_ms:
        return str(every_ms)
    if str(schedule.get("expr", "")).strip():
        return str(schedule.get("expr", "")).strip()
    return "-"


def normalize_payload(job: dict[str, Any]) -> str:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "command", "kind"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return ""


def fallback_capability(agent_name: str, schedule_name: str) -> str:
    normalized = str(schedule_name or "").strip().lower().replace(" ", "_")
    if normalized:
        return normalized
    return str(agent_name or "generic").strip().lower().replace("-", "_") or "generic"


def metadata_for_job(job: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    schedule_name = str(job.get("name", "")).strip()
    schedule_id = str(job.get("id", "")).strip()
    metadata = dict(KNOWN_SCHEDULE_METADATA.get(schedule_name, {}))
    agent_name = (
        metadata.get("owner_agent")
        or str(job.get("agentId", "")).strip()
        or mapping.get(schedule_id)
        or mapping.get(schedule_name)
        or "ops-agent"
    )
    metadata.setdefault("owner_agent", agent_name)
    metadata.setdefault("executor_agent", agent_name)
    metadata.setdefault("capability", fallback_capability(agent_name, schedule_name))
    metadata.setdefault("purpose", str(job.get("description", "")).strip() or schedule_name or schedule_id or "未命名任务")
    metadata.setdefault("flow_summary", normalize_payload(job) or "由统一调度中心触发")
    metadata.setdefault("required_skills_or_runtime", [])
    metadata.setdefault("outputs", [])
    metadata.setdefault("human_visibility", "默认静默")
    metadata.setdefault("delivery_mode", str(((job.get("delivery") or {}).get("mode", ""))).strip() or "none")
    metadata.setdefault("health_signals", [])
    metadata.setdefault("failure_signals", [])
    metadata.setdefault("maintenance_entry", "cron/jobs.json")
    return metadata


def build_openclaw_entry(job: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    metadata = metadata_for_job(job, mapping)
    return {
        "schedule_id": str(job.get("id", "")).strip(),
        "schedule_name": str(job.get("name", "")).strip(),
        "surface_type": "openclaw_cron",
        "owner_agent": str(metadata["owner_agent"]).strip(),
        "executor_agent": str(metadata["executor_agent"]).strip(),
        "capability": str(metadata["capability"]).strip(),
        "trigger_definition": normalize_trigger(job),
        "trigger": normalize_trigger(job),
        "source_of_truth": "cron/jobs.json",
        "job_payload_or_command": normalize_payload(job),
        "required_skills": list(metadata.get("required_skills_or_runtime", [])),
        "required_runtime": list(metadata.get("required_skills_or_runtime", [])),
        "required_skills_or_runtime": list(metadata.get("required_skills_or_runtime", [])),
        "purpose": str(metadata["purpose"]).strip(),
        "flow_summary": str(metadata["flow_summary"]).strip(),
        "outputs": list(metadata.get("outputs", [])),
        "human_visibility": str(metadata["human_visibility"]).strip(),
        "delivery_policy": str(metadata["delivery_mode"]).strip(),
        "delivery_mode": str(metadata["delivery_mode"]).strip(),
        "health_signals": list(metadata.get("health_signals", [])),
        "common_failures": list(metadata.get("failure_signals", [])),
        "failure_signals": list(metadata.get("failure_signals", [])),
        "maintenance_entry": str(metadata["maintenance_entry"]).strip(),
        "upgrade_notes": "新增或修改任务时必须先更新 Schedule Registry。",
        "enabled": bool(job.get("enabled", False)),
    }


def build_agent_summary(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agents: dict[str, dict[str, Any]] = {}
    for entry in entries:
        owner = str(entry.get("owner_agent", "")).strip()
        if owner:
            info = agents.setdefault(
                owner,
                {
                    "agent_name": owner,
                    "owned_schedules": [],
                    "executed_schedules": [],
                    "capabilities": [],
                    "required_runtime": [],
                    "outputs": [],
                    "maintenance_entries": [],
                },
            )
            info["owned_schedules"].append(str(entry.get("schedule_name", "")).strip())
            capability = str(entry.get("capability", "")).strip()
            if capability:
                info["capabilities"].append(capability)
            for item in entry.get("required_skills_or_runtime", []):
                text = str(item).strip()
                if text:
                    info["required_runtime"].append(text)
            for item in entry.get("outputs", []):
                text = str(item).strip()
                if text:
                    info["outputs"].append(text)
            maintenance = str(entry.get("maintenance_entry", "")).strip()
            if maintenance:
                info["maintenance_entries"].append(maintenance)

        executor = str(entry.get("executor_agent", "")).strip()
        if executor:
            info = agents.setdefault(
                executor,
                {
                    "agent_name": executor,
                    "owned_schedules": [],
                    "executed_schedules": [],
                    "capabilities": [],
                    "required_runtime": [],
                    "outputs": [],
                    "maintenance_entries": [],
                },
            )
            info["executed_schedules"].append(str(entry.get("schedule_name", "")).strip())

    result: list[dict[str, Any]] = []
    for name in sorted(agents):
        item = agents[name]
        item["owned_schedules"] = sorted(set(x for x in item["owned_schedules"] if x))
        item["executed_schedules"] = sorted(set(x for x in item["executed_schedules"] if x))
        item["capabilities"] = sorted(set(x for x in item["capabilities"] if x))
        item["required_runtime"] = sorted(set(x for x in item["required_runtime"] if x))
        item["outputs"] = sorted(set(x for x in item["outputs"] if x))
        item["maintenance_entries"] = sorted(set(x for x in item["maintenance_entries"] if x))
        result.append(item)
    return result


def build_schedule_registry(*, jobs_file: Path, mapping_file: Path, profile: str) -> dict[str, Any]:
    payload = load_json(jobs_file)
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(jobs, list):
        jobs = []
    mapping = parse_mapping_file(mapping_file)

    openclaw_managed = [
        build_openclaw_entry(job, mapping)
        for job in jobs
        if isinstance(job, dict)
    ]
    openclaw_managed.sort(key=lambda item: (item["schedule_name"], item["schedule_id"]))
    agents = build_agent_summary(openclaw_managed)

    return {
        "schema_version": "2026-03-13",
        "generated_at": now_iso(),
        "profile": str(profile or "all").strip().lower() or "all",
        "sources": {
            "jobs_file": str(jobs_file),
            "mapping_file": str(mapping_file),
        },
        "openclaw_managed": openclaw_managed,
        "external_attached": EXTERNAL_SCHEDULES,
        "agents": agents,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    home = Path.home()
    parser = argparse.ArgumentParser(description="Export workflow schedule registry")
    parser.add_argument("--jobs-file", default=str(root / "cron" / "jobs.json"))
    parser.add_argument("--mapping-file", default=str(root / "cron" / "jobs_agent_mapping.md"))
    parser.add_argument("--output-file", default=str(home / ".openclaw" / "ops" / "workflow" / "schedule-registry.json"))
    parser.add_argument("--profile", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_file = Path(args.jobs_file).expanduser()
    mapping_file = Path(args.mapping_file).expanduser()
    output_file = Path(args.output_file).expanduser()

    registry = build_schedule_registry(
        jobs_file=jobs_file,
        mapping_file=mapping_file,
        profile=str(args.profile),
    )
    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "jobs_file": str(jobs_file),
        "mapping_file": str(mapping_file),
        "output_file": str(output_file),
        "profile": registry["profile"],
        "openclaw_count": len(registry["openclaw_managed"]),
        "external_count": len(registry["external_attached"]),
        "agent_count": len(registry["agents"]),
        "written": False,
    }

    if not args.dry_run:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["written"] = True

    if args.emit_json:
        print(json.dumps({**result, "registry": registry}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

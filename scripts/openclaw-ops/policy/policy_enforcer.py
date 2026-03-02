#!/usr/bin/env python3
"""Policy-Enforcer: fail-close policy checks for OpenClaw workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from task_center import (
    TASK_STATUSES,
    TaskCenter,
    TaskCenterError,
    estimate_cost,
    format_daily_summary_markdown,
    load_pricing,
)

UTC = timezone.utc

DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": "2026-03-02",
    "primary_model": "kimicode/Doubao-Seed-2.0-Code",
    "fallback_models": ["glmcode/glm-5"],
    "allowed_models": ["kimicode/Doubao-Seed-2.0-Code", "glmcode/glm-5", "glmcode/glm-4.7"],
    "allowed_entry_agents": ["coordinator"],
    "dispatcher_agent": "coordinator",
    "blocked_direct_code_agents": ["coordinator", "project-agent"],
    "code_execution_stages": ["implement", "fix", "deploy"],
    "required_task_fields": [
        "reason",
        "requirement",
        "result_output",
        "acceptance",
        "observable_outputs",
        "acceptance_thresholds"
    ],
    "high_risk_requires_human_confirm": True,
    "require_token_usage_before_done": True,
    "max_failure_before_escalate": 3,
    "pass_line_raw": 75.0,
    "status_flow": {
        "pending": ["running", "cancelled", "escalated"],
        "running": ["running", "passed", "failed", "escalated", "cancelled"],
        "failed": ["running", "escalated", "cancelled"],
        "escalated": ["running", "cancelled", "passed"],
        "passed": [],
        "cancelled": []
    }
}

DEFAULT_ROUTING_RULES: dict[str, Any] = {
    "version": "2026-03-02",
    "high_risk_keywords": [
        "生产",
        "部署",
        "支付",
        "安全",
        "密钥",
        "权限",
        "数据库",
        "迁移",
        "删除",
        "回滚",
        "配置",
        "测试失败",
        "cron异常",
        "事故",
        "中断",
        "outage",
        "security",
        "payment",
        "rollback"
    ],
    "low_risk_keywords": ["文档", "索引", "注释", "整理", "汇总", "排版", "readme", "index"],
    "priority_keywords": {
        "high": ["紧急", "立刻", "故障", "异常", "失败", "告警", "中断", "不可用", "urgent", "p0", "p1"],
        "low": ["后续", "延后", "慢慢", "优化", "观察", "待办", "backlog"]
    },
    "assignee_rules": [
        {"assignee": "ops-agent", "keywords": ["cron", "日志", "监控", "运维", "服务", "网关", "infra"]},
        {"assignee": "backend-dev", "keywords": ["api", "后端", "数据库", "模型", "接口", "backend"]},
        {"assignee": "frontend-dev", "keywords": ["前端", "页面", "ui", "交互", "样式", "frontend"]},
        {"assignee": "tester", "keywords": ["测试", "验收", "回归", "qa"]},
        {"assignee": "project-agent", "keywords": ["项目索引", "readme", "文档同步", "模块说明"]}
    ],
    "default_assignee": "coordinator"
}
DEFAULT_TOKEN_PRICING: dict[str, Any] = {
    "version": "2026-03-02",
    "currency": "CNY",
    "unit": "per_1m_tokens",
    "models": {
        "glmcode/glm-5": {"input": 0, "output": 0},
        "kimicode/Doubao-Seed-2.0-Code": {"input": 0, "output": 0},
        "glmcode/glm-4.7": {"input": 0, "output": 0},
    },
}


class PolicyError(RuntimeError):
    """Raised on policy violations."""


@dataclass(slots=True)
class RuntimePaths:
    db: Path
    policy_file: Path
    routing_file: Path
    pricing_file: Path


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    norm = str(value).strip().lower()
    if norm == "":
        return default
    return norm in {"1", "true", "yes", "y", "on"}


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def runtime_defaults() -> dict[str, str]:
    script_policy_dir = Path(__file__).resolve().parent
    openclaw_home = Path(
        os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw"))
    ).expanduser()

    default_task_center_dir = Path(".workflow/task-center")
    if "TASK_CENTER_DIR" in os.environ:
        task_center_dir = Path(os.environ["TASK_CENTER_DIR"]).expanduser()
    elif default_task_center_dir.exists():
        task_center_dir = default_task_center_dir
    else:
        task_center_dir = Path(openclaw_home / "ops" / "task-center")

    if "OPENCLAW_POLICY_ROOT" in os.environ:
        policy_runtime_dir = Path(os.environ["OPENCLAW_POLICY_ROOT"]).expanduser()
    elif (script_policy_dir / "policy-config.json").exists():
        policy_runtime_dir = script_policy_dir
    else:
        policy_runtime_dir = Path(openclaw_home / "ops" / "policy")

    pricing_file = (
        os.environ.get("POLICY_PRICING_FILE")
        or os.environ.get("TOKEN_PRICING_FILE")
        or str(policy_runtime_dir / "token-pricing.json")
    )
    return {
        "db": os.environ.get("POLICY_DB_FILE", str(task_center_dir / "task_center.db")),
        "policy_file": os.environ.get("POLICY_FILE", str(policy_runtime_dir / "policy-config.json")),
        "routing_file": os.environ.get("POLICY_ROUTING_FILE", str(policy_runtime_dir / "routing-rules.json")),
        "pricing_file": pricing_file,
        "openclaw_config": os.environ.get("OPENCLAW_CONFIG", str(openclaw_home / "openclaw.json")),
        "project_registry": os.environ.get("PROJECT_REGISTRY", str(task_center_dir / "project-registry.json")),
    }


def read_json(path: Path, default: dict[str, Any] | None = None, write_if_missing: bool = False) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise PolicyError(f"json object expected: {path}")
        return data

    if default is None:
        raise PolicyError(f"missing file: {path}")

    data = json.loads(json.dumps(default))
    if write_if_missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def merge_missing_keys(base: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in defaults.items():
        if key not in out:
            out[key] = json.loads(json.dumps(value))
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_missing_keys(out[key], value)
    return out


class PolicyEnforcer:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self.db = TaskCenter(paths.db)
        self.db.init_schema()
        self.policy = merge_missing_keys(
            read_json(paths.policy_file, DEFAULT_POLICY, write_if_missing=False),
            DEFAULT_POLICY,
        )
        self.routing = merge_missing_keys(
            read_json(paths.routing_file, DEFAULT_ROUTING_RULES, write_if_missing=False),
            DEFAULT_ROUTING_RULES,
        )

    def close(self) -> None:
        self.db.close()

    def required_task_fields(self) -> list[str]:
        fields = self.policy.get("required_task_fields", [])
        if not isinstance(fields, list):
            raise PolicyError("policy.required_task_fields must be a list")
        return [str(x) for x in fields]

    def allowed_models(self) -> set[str]:
        models = self.policy.get("allowed_models", [])
        if not isinstance(models, list):
            raise PolicyError("policy.allowed_models must be a list")
        return {str(m) for m in models}

    def allowed_entry_agents(self) -> set[str]:
        agents = self.policy.get("allowed_entry_agents", [])
        if not isinstance(agents, list):
            raise PolicyError("policy.allowed_entry_agents must be a list")
        return {str(a).strip() for a in agents if str(a).strip()}

    def dispatcher_agent(self) -> str:
        value = str(self.policy.get("dispatcher_agent", "coordinator")).strip()
        if not value:
            raise PolicyError("policy.dispatcher_agent must not be empty")
        return value

    def require_token_usage_before_done(self) -> bool:
        return parse_bool(self.policy.get("require_token_usage_before_done", True), True)

    def max_failure_before_escalate(self) -> int:
        value = int(self.policy.get("max_failure_before_escalate", 3) or 3)
        if value < 1:
            raise PolicyError("policy.max_failure_before_escalate must be >= 1")
        return value

    def pass_line_raw(self) -> float:
        return float(self.policy.get("pass_line_raw", 75.0) or 75.0)

    def status_flow(self) -> dict[str, set[str]]:
        flow_raw = self.policy.get("status_flow", {})
        if not isinstance(flow_raw, dict):
            raise PolicyError("policy.status_flow must be an object")
        out: dict[str, set[str]] = {}
        for key, value in flow_raw.items():
            if key not in TASK_STATUSES:
                continue
            if not isinstance(value, list):
                raise PolicyError(f"status_flow.{key} must be a list")
            out[key] = {str(v) for v in value}
        return out

    def assert_required_fields(self, task: dict[str, Any]) -> None:
        for field in self.required_task_fields():
            value = str(task.get(field, "")).strip()
            if not value:
                raise PolicyError(f"task missing required field: {field}")

    def assert_model_allowed(self, model: str) -> None:
        if model not in self.allowed_models():
            raise PolicyError(f"model blocked by policy: {model}")

    def assert_entry_agent_allowed(self, entry_agent: str) -> None:
        allowed = self.allowed_entry_agents()
        if not allowed:
            raise PolicyError("policy.allowed_entry_agents is empty")
        if entry_agent not in allowed:
            raise PolicyError(f"entry agent blocked by policy: {entry_agent}")

    def assert_dispatcher_actor(self, actor: str) -> None:
        dispatcher = self.dispatcher_agent()
        if actor != dispatcher:
            raise PolicyError(f"only dispatcher can assign task: actor={actor}, required={dispatcher}")

    def assert_risk_confirmed(self, task: dict[str, Any]) -> None:
        if not parse_bool(self.policy.get("high_risk_requires_human_confirm", True), True):
            return
        if str(task.get("risk_level")) != "high":
            return

        need_human = bool(task.get("need_human_confirm"))
        confirmed = bool(task.get("human_confirmed"))
        if need_human and not confirmed:
            raise PolicyError("high-risk task requires human confirmation")

    def assert_agent_stage_allowed(self, agent_id: str, stage: str) -> None:
        blocked_agents = self.policy.get("blocked_direct_code_agents", [])
        code_stages = self.policy.get("code_execution_stages", [])
        if not isinstance(blocked_agents, list) or not isinstance(code_stages, list):
            raise PolicyError("policy blocked_direct_code_agents/code_execution_stages must be lists")

        if agent_id in {str(x) for x in blocked_agents} and stage in {str(x) for x in code_stages}:
            raise PolicyError(f"agent {agent_id} is not allowed to execute code stage {stage}")

    def assert_transition_allowed(self, from_status: str, to_status: str) -> None:
        flow = self.status_flow()
        allowed = flow.get(from_status)
        if allowed is None:
            raise PolicyError(f"unknown from_status in policy flow: {from_status}")
        if to_status not in allowed:
            raise PolicyError(f"status transition blocked by policy: {from_status} -> {to_status}")

    def create_task(self, args: argparse.Namespace) -> dict[str, Any]:
        priority = args.priority
        if priority not in {"low", "medium", "high"}:
            raise PolicyError("priority must be low|medium|high")

        pool = args.pool
        if not pool:
            pool = "jobs" if priority == "high" else "todo"
        if pool not in {"todo", "jobs"}:
            raise PolicyError("pool must be todo|jobs")

        risk_level = args.risk_level
        if risk_level not in {"low", "high"}:
            raise PolicyError("risk_level must be low|high")

        entry_agent = str(args.entry_agent or "").strip()
        if entry_agent:
            self.assert_entry_agent_allowed(entry_agent)

        need_human_confirm = parse_bool(args.need_human_confirm, risk_level == "high")

        payload = {
            "task_id": args.task_id,
            "pool": pool,
            "task_type": args.task_type,
            "reason": args.reason,
            "source": args.source,
            "priority": priority,
            "risk_level": risk_level,
            "assignee": args.assignee or self.dispatcher_agent(),
            "status": "pending",
            "need_human_confirm": need_human_confirm,
            "human_confirmed": parse_bool(args.human_confirmed, False),
            "requirement": args.requirement,
            "result_output": args.result_output,
            "acceptance": args.acceptance,
            "observable_outputs": args.observable_outputs,
            "acceptance_thresholds": args.acceptance_thresholds,
            "scheduled_at": args.scheduled_at,
        }

        created = self.db.create_task(payload, actor=args.actor)
        self.assert_required_fields(created)
        if entry_agent:
            self.db.add_event(
                task_id=created["task_id"],
                actor=args.actor,
                event_type="entry_agent_checked",
                stage="intake",
                details={"entry_agent": entry_agent, "allowed": True},
            )
        return created

    def assign_task(self, args: argparse.Namespace) -> dict[str, Any]:
        self.assert_dispatcher_actor(args.actor)
        return self.db.assign_task(task_id=args.task_id, assignee=args.assignee, actor=args.actor)

    def confirm_risk(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.db.confirm_human(task_id=args.task_id, actor=args.actor, confirmed=parse_bool(args.confirmed, True))

    def pre_stage(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)
        self.assert_required_fields(task)
        self.assert_model_allowed(args.model)
        self.assert_agent_stage_allowed(args.agent_id, args.stage)
        self.assert_risk_confirmed(task)

        from_status = str(task["status"])
        self.assert_transition_allowed(from_status, "running")

        details = {
            "stage": args.stage,
            "agent_id": args.agent_id,
            "model": args.model,
            "at": now_iso(),
        }
        updated = self.db.transition_status(
            task_id=args.task_id,
            new_status="running",
            actor=args.actor,
            stage=args.stage,
            details=details,
            allowed_from={from_status},
        )
        stage_run = self.db.start_stage_run(
            task_id=args.task_id,
            stage=args.stage,
            agent_id=args.agent_id,
            model_id=args.model,
            input_ref=str(args.input_ref or "").strip(),
            details={"status_from": from_status},
        )
        self.db.add_event(
            task_id=args.task_id,
            actor=args.actor,
            event_type="stage_started",
            stage=args.stage,
            details={
                "stage_run_id": stage_run["id"],
                "agent_id": args.agent_id,
                "model": args.model,
                "input_ref": str(args.input_ref or "").strip(),
            },
        )
        return updated

    def post_stage(self, args: argparse.Namespace) -> dict[str, Any]:
        exit_code = int(args.exit_code)
        output_ref = str(args.output_ref or "").strip()
        reason = str(args.reason or "").strip()

        if exit_code == 0:
            stage_run: dict[str, Any] | None = None
            try:
                stage_run = self.db.finish_stage_run(
                    task_id=args.task_id,
                    stage=args.stage,
                    status="passed",
                    exit_code=exit_code,
                    output_ref=output_ref,
                    details={"reason": reason},
                )
            except TaskCenterError as exc:
                self.db.add_event(
                    task_id=args.task_id,
                    actor=args.actor,
                    event_type="stage_run_finish_warning",
                    stage=args.stage,
                    details={"warning": str(exc)},
                )
            self.db.add_event(
                task_id=args.task_id,
                actor=args.actor,
                event_type="stage_passed",
                stage=args.stage,
                details={
                    "exit_code": exit_code,
                    "output_ref": output_ref,
                    "stage_run_id": stage_run["id"] if stage_run else None,
                    "duration_ms": stage_run["duration_ms"] if stage_run else None,
                },
            )
            return self.db.get_task(args.task_id)

        try:
            self.db.finish_stage_run(
                task_id=args.task_id,
                stage=args.stage,
                status="failed",
                exit_code=exit_code,
                error_reason=reason or f"stage {args.stage} failed with exit_code={exit_code}",
                output_ref=output_ref,
                details={"reason": reason},
            )
        except TaskCenterError as exc:
            self.db.add_event(
                task_id=args.task_id,
                actor=args.actor,
                event_type="stage_run_finish_warning",
                stage=args.stage,
                details={"warning": str(exc)},
            )

        updated = self.db.increment_failure(
            task_id=args.task_id,
            actor=args.actor,
            stage=args.stage,
            max_failure_before_escalate=self.max_failure_before_escalate(),
            reason=reason or f"stage {args.stage} failed with exit_code={exit_code}",
        )
        return updated

    def complete_task(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)

        if self.require_token_usage_before_done() and not self.db.has_token_usage(args.task_id):
            raise PolicyError("token/cost usage missing: record-token required before complete-task")

        result_score = float(args.result_score)
        stability_score = float(args.stability_score)
        critical_pass = parse_bool(args.critical_pass, True)

        raw_score = result_score * 0.70 + stability_score * 0.30
        normalized_score = (raw_score / 100.0) * 100.0

        if critical_pass and raw_score >= self.pass_line_raw():
            action = "pass"
            target_status = "passed"
        else:
            if int(task["failure_count"]) >= self.max_failure_before_escalate():
                action = "escalate_human"
                target_status = "escalated"
            else:
                action = "retry"
                target_status = "failed"

        from_status = str(task["status"])
        self.assert_transition_allowed(from_status, target_status)

        self.db.upsert_score(
            task_id=args.task_id,
            actor=args.actor,
            raw_score=round(raw_score, 4),
            normalized_score=round(normalized_score, 4),
            action=action,
            score_payload={
                "result_score": result_score,
                "stability_score": stability_score,
                "result_weight": 0.70,
                "stability_weight": 0.30,
                "raw_score": round(raw_score, 4),
                "normalized_score": round(normalized_score, 4),
                "critical_pass": critical_pass,
                "action": action,
            },
        )
        updated = self.db.transition_status(
            task_id=args.task_id,
            new_status=target_status,
            actor=args.actor,
            stage="complete",
            details={
                "result_score": result_score,
                "stability_score": stability_score,
                "raw_score": round(raw_score, 4),
                "normalized_score": round(normalized_score, 4),
                "critical_pass": critical_pass,
                "action": action,
            },
            allowed_from={from_status},
        )
        return updated

    def record_token(self, args: argparse.Namespace) -> dict[str, Any]:
        self.assert_model_allowed(args.model)
        pricing = load_pricing(args.pricing_file)
        input_tokens = int(args.input_tokens)
        output_tokens = int(args.output_tokens)
        cost = estimate_cost(pricing, args.model, input_tokens, output_tokens)

        result = self.db.record_token_usage(
            task_id=args.task_id,
            agent_id=args.agent_id,
            model_id=args.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost,
            details={"pricing_file": str(args.pricing_file)},
        )
        result["pricing_currency"] = pricing.get("currency", "CNY")
        return result

    def daily_summary(self, args: argparse.Namespace) -> dict[str, Any]:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(tz=UTC).date()
        summary = self.db.daily_summary(target_date)

        if args.output:
            out = Path(args.output).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(format_daily_summary_markdown(summary), encoding="utf-8")

        return summary

    def task_report(self, args: argparse.Namespace) -> dict[str, Any]:
        report = self.db.task_report(task_id=args.task_id, event_limit=int(args.event_limit))
        if args.output:
            out = Path(args.output).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    def assert_entry(self, args: argparse.Namespace) -> dict[str, Any]:
        entry_agent = str(args.entry_agent or "").strip()
        if not entry_agent:
            raise PolicyError("entry_agent is required")
        self.assert_entry_agent_allowed(entry_agent)
        return {"ok": True, "entry_agent": entry_agent, "allowed_entry_agents": sorted(self.allowed_entry_agents())}

    def route_task(self, args: argparse.Namespace) -> dict[str, Any]:
        text = args.description.strip()
        if not text:
            raise PolicyError("description cannot be empty")
        norm = text.lower()

        high_risk_hits = [k for k in self.routing.get("high_risk_keywords", []) if str(k).lower() in norm]
        low_risk_hits = [k for k in self.routing.get("low_risk_keywords", []) if str(k).lower() in norm]

        risk_level = "high" if high_risk_hits else "low"

        priority = "medium"
        high_priority_hits = [
            k
            for k in self.routing.get("priority_keywords", {}).get("high", [])
            if str(k).lower() in norm
        ]
        low_priority_hits = [
            k
            for k in self.routing.get("priority_keywords", {}).get("low", [])
            if str(k).lower() in norm
        ]
        if high_priority_hits or risk_level == "high":
            priority = "high"
        elif low_priority_hits:
            priority = "low"

        assignee = str(self.routing.get("default_assignee", "backend-dev"))
        assignee_hit = None
        for rule in self.routing.get("assignee_rules", []):
            if not isinstance(rule, dict):
                continue
            candidate = str(rule.get("assignee", "")).strip()
            keywords = rule.get("keywords", [])
            if not candidate or not isinstance(keywords, list):
                continue
            for keyword in keywords:
                if str(keyword).lower() in norm:
                    assignee = candidate
                    assignee_hit = str(keyword)
                    break
            if assignee_hit:
                break

        pool = "jobs" if priority == "high" else "todo"
        need_human_confirm = risk_level == "high" and parse_bool(
            self.policy.get("high_risk_requires_human_confirm", True),
            True,
        )

        return {
            "description": text,
            "source": args.source,
            "entry_agent": sorted(self.allowed_entry_agents())[0] if self.allowed_entry_agents() else "",
            "dispatcher_agent": self.dispatcher_agent(),
            "priority": priority,
            "risk_level": risk_level,
            "pool": pool,
            "assignee": assignee,
            "need_human_confirm": need_human_confirm,
            "hits": {
                "high_risk": high_risk_hits,
                "low_risk": low_risk_hits,
                "priority_high": high_priority_hits,
                "priority_low": low_priority_hits,
                "assignee_hit": assignee_hit,
            },
        }

    def update_routing(self, args: argparse.Namespace) -> dict[str, Any]:
        routing = self.routing

        def add_unique(lst: list[Any], items: list[str]) -> None:
            lower_set = {str(x).lower() for x in lst}
            for item in items:
                key = item.strip()
                if not key:
                    continue
                if key.lower() in lower_set:
                    continue
                lst.append(key)
                lower_set.add(key.lower())

        add_unique(routing.setdefault("high_risk_keywords", []), args.add_high_risk)
        add_unique(routing.setdefault("low_risk_keywords", []), args.add_low_risk)
        add_unique(routing.setdefault("priority_keywords", {}).setdefault("high", []), args.add_priority_high)
        add_unique(routing.setdefault("priority_keywords", {}).setdefault("low", []), args.add_priority_low)

        for raw in args.add_assignee_rule:
            left, sep, right = raw.partition(":")
            assignee = left.strip()
            keywords = [x.strip() for x in right.split(",") if x.strip()]
            if not sep or not assignee or not keywords:
                raise PolicyError(
                    "add-assignee-rule format must be 'assignee:keyword1,keyword2'"
                )

            rules = routing.setdefault("assignee_rules", [])
            match = None
            for rule in rules:
                if isinstance(rule, dict) and str(rule.get("assignee", "")).strip() == assignee:
                    match = rule
                    break
            if not match:
                match = {"assignee": assignee, "keywords": []}
                rules.append(match)
            add_unique(match.setdefault("keywords", []), keywords)

        if args.default_assignee:
            routing["default_assignee"] = args.default_assignee

        self.paths.routing_file.write_text(
            json.dumps(routing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.routing = routing
        return {"routing_file": str(self.paths.routing_file), "updated": True}

    def assert_stop_safe(self, args: argparse.Namespace) -> dict[str, Any]:
        unresolved = self.db.unresolved_tasks()
        if unresolved:
            raise PolicyError(
                "unresolved tasks exist: "
                + ", ".join(f"{x['task_id']}[{x['status']}]" for x in unresolved[:20])
            )
        return {"ok": True, "unresolved_count": 0}

    def validate_runtime(self, args: argparse.Namespace) -> dict[str, Any]:
        missing = []
        for path in [self.paths.policy_file, self.paths.routing_file, self.paths.pricing_file]:
            if not path.exists():
                missing.append(str(path))
        if missing:
            raise PolicyError("missing runtime files: " + ", ".join(missing))

        models = self.allowed_models()
        if self.policy.get("primary_model") not in models:
            raise PolicyError("primary_model must be in allowed_models")
        if not self.allowed_entry_agents():
            raise PolicyError("allowed_entry_agents must not be empty")
        _ = self.dispatcher_agent()

        pricing = load_pricing(self.paths.pricing_file)
        pricing_models = pricing.get("models", {})
        if not isinstance(pricing_models, dict):
            raise PolicyError("pricing.models must be an object")

        for model_id in models:
            if model_id not in pricing_models:
                raise PolicyError(f"pricing missing model: {model_id}")

        return {
            "ok": True,
            "db": str(self.paths.db),
            "policy_file": str(self.paths.policy_file),
            "routing_file": str(self.paths.routing_file),
            "pricing_file": str(self.paths.pricing_file),
        }

    def check_config(self, args: argparse.Namespace) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add_check(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        add_check(
            "allowed_entry_agents_contains_coordinator",
            "coordinator" in self.allowed_entry_agents(),
            f"allowed_entry_agents={sorted(self.allowed_entry_agents())}",
        )
        add_check(
            "dispatcher_is_coordinator",
            self.dispatcher_agent() == "coordinator",
            f"dispatcher_agent={self.dispatcher_agent()}",
        )

        pricing = load_pricing(self.paths.pricing_file)
        pricing_models = pricing.get("models", {})
        add_check(
            "pricing_parseable",
            isinstance(pricing_models, dict),
            f"pricing_file={self.paths.pricing_file}",
        )
        if isinstance(pricing_models, dict):
            missing_models = sorted(model for model in self.allowed_models() if model not in pricing_models)
            add_check(
                "pricing_models_cover_allowed_models",
                not missing_models,
                "missing_models=" + ",".join(missing_models) if missing_models else "ok",
            )

        openclaw_path = Path(args.openclaw_config).expanduser()
        if not openclaw_path.exists():
            add_check("openclaw_config_exists", False, str(openclaw_path))
            openclaw_obj: dict[str, Any] = {}
        else:
            add_check("openclaw_config_exists", True, str(openclaw_path))
            try:
                openclaw_obj = read_json(openclaw_path, default=None, write_if_missing=False)
                add_check("openclaw_config_parseable", True, "ok")
            except Exception as exc:
                openclaw_obj = {}
                add_check("openclaw_config_parseable", False, str(exc))

        bindings = openclaw_obj.get("bindings", [])
        binding_ok = False
        if isinstance(bindings, list):
            for item in bindings:
                if not isinstance(item, dict):
                    continue
                if str(item.get("agentId", "")).strip() == "coordinator":
                    binding_ok = True
                    break
        add_check("binding_coordinator", binding_ok, f"bindings_count={len(bindings) if isinstance(bindings, list) else 0}")

        agents = openclaw_obj.get("agents", {}).get("list", [])
        agent_ids = [str(item.get("id", "")).strip() for item in agents if isinstance(item, dict)]
        add_check("project_agent_exists", "project-agent" in agent_ids, f"agent_count={len(agent_ids)}")
        add_check("secretary_agent_removed", "secretary-agent" not in agent_ids, "secretary-agent must not exist")

        a2a_allow = (
            openclaw_obj.get("tools", {})
            .get("agentToAgent", {})
            .get("allow", [])
        )
        add_check(
            "agent_to_agent_allow_project_agent",
            isinstance(a2a_allow, list) and "project-agent" in {str(x).strip() for x in a2a_allow},
            f"allow_count={len(a2a_allow) if isinstance(a2a_allow, list) else 0}",
        )

        registry_path = Path(args.project_registry).expanduser()
        if not registry_path.exists():
            add_check("project_registry_exists", False, str(registry_path))
        else:
            try:
                with registry_path.open("r", encoding="utf-8-sig") as fh:
                    registry_raw = json.load(fh)
            except Exception as exc:
                add_check("project_registry_exists", True, str(registry_path))
                add_check("project_registry_parseable", False, str(exc))
            else:
                add_check("project_registry_exists", True, str(registry_path))
                add_check("project_registry_parseable", True, "ok")
                if isinstance(registry_raw, list):
                    projects = registry_raw
                elif isinstance(registry_raw, dict):
                    projects = registry_raw.get("projects", [])
                else:
                    projects = []
                if isinstance(projects, list) and projects:
                    missing_paths: list[str] = []
                    for item in projects:
                        if not isinstance(item, dict):
                            continue
                        project_path = str(item.get("path", "")).strip()
                        if not project_path:
                            continue
                        if not Path(project_path).expanduser().exists():
                            missing_paths.append(project_path)
                    add_check(
                        "project_registry_paths_valid",
                        len(missing_paths) == 0,
                        "missing_paths=" + ",".join(missing_paths) if missing_paths else f"projects={len(projects)}",
                    )
                else:
                    add_check("project_registry_paths_valid", False, "registry.projects empty or invalid")

        ok = all(bool(item.get("ok")) for item in checks)
        if args.strict and not ok:
            failed = [item["name"] for item in checks if not item["ok"]]
            raise PolicyError("check-config failed: " + ", ".join(failed))

        return {
            "ok": ok,
            "checks": checks,
            "openclaw_config": str(openclaw_path),
            "project_registry": str(registry_path),
        }


def build_parser() -> argparse.ArgumentParser:
    defaults = runtime_defaults()
    parser = argparse.ArgumentParser(description="Policy-Enforcer CLI")
    parser.add_argument(
        "--db",
        default=defaults["db"],
        help="sqlite database path",
    )
    parser.add_argument(
        "--policy-file",
        default=defaults["policy_file"],
    )
    parser.add_argument(
        "--routing-file",
        default=defaults["routing_file"],
    )
    parser.add_argument(
        "--pricing-file",
        default=defaults["pricing_file"],
    )
    parser.add_argument(
        "--openclaw-config",
        default=defaults["openclaw_config"],
    )
    parser.add_argument(
        "--project-registry",
        default=defaults["project_registry"],
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="initialize db and default config files")
    init_cmd.add_argument("--force", action="store_true")

    create = sub.add_parser("create-task", help="create task")
    create.add_argument("--task-id", default="")
    create.add_argument("--task-type", default="workflow")
    create.add_argument("--reason", required=True)
    create.add_argument("--source", default="openclaw")
    create.add_argument("--priority", default="medium")
    create.add_argument("--risk-level", default="low")
    create.add_argument("--pool", default="")
    create.add_argument("--assignee", default="")
    create.add_argument("--entry-agent", default="")
    create.add_argument("--need-human-confirm", default="")
    create.add_argument("--human-confirmed", default="false")
    create.add_argument("--requirement", required=True)
    create.add_argument("--result-output", required=True)
    create.add_argument("--acceptance", required=True)
    create.add_argument("--observable-outputs", required=True)
    create.add_argument("--acceptance-thresholds", required=True)
    create.add_argument("--scheduled-at", default="")
    create.add_argument("--actor", default="policy-enforcer")

    assign = sub.add_parser("assign-task", help="assign task")
    assign.add_argument("--task-id", required=True)
    assign.add_argument("--assignee", required=True)
    assign.add_argument("--actor", default="coordinator")

    confirm = sub.add_parser("confirm-risk", help="confirm high-risk task")
    confirm.add_argument("--task-id", required=True)
    confirm.add_argument("--confirmed", default="true")
    confirm.add_argument("--actor", default="human")

    pre_stage = sub.add_parser("pre-stage", help="policy check before stage")
    pre_stage.add_argument("--task-id", required=True)
    pre_stage.add_argument("--stage", required=True)
    pre_stage.add_argument("--agent-id", required=True)
    pre_stage.add_argument("--model", required=True)
    pre_stage.add_argument("--input-ref", default="")
    pre_stage.add_argument("--actor", default="policy-enforcer")

    post_stage = sub.add_parser("post-stage", help="policy record after stage")
    post_stage.add_argument("--task-id", required=True)
    post_stage.add_argument("--stage", required=True)
    post_stage.add_argument("--exit-code", required=True)
    post_stage.add_argument("--output-ref", default="")
    post_stage.add_argument("--reason", default="")
    post_stage.add_argument("--actor", default="policy-enforcer")

    complete = sub.add_parser("complete-task", help="set score and final action")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--result-score", required=True)
    complete.add_argument("--stability-score", required=True)
    complete.add_argument("--critical-pass", default="true")
    complete.add_argument("--actor", default="tester")

    record_token = sub.add_parser("record-token", help="record token usage")
    record_token.add_argument("--task-id", required=True)
    record_token.add_argument("--agent-id", required=True)
    record_token.add_argument("--model", required=True)
    record_token.add_argument("--input-tokens", required=True)
    record_token.add_argument("--output-tokens", required=True)

    daily = sub.add_parser("daily-summary", help="generate daily summary")
    daily.add_argument("--date", default="")
    daily.add_argument("--output", default="")

    task_report = sub.add_parser("task-report", help="task observability report")
    task_report.add_argument("--task-id", required=True)
    task_report.add_argument("--event-limit", default="200")
    task_report.add_argument("--output", default="")

    assert_entry = sub.add_parser("assert-entry", help="validate entry agent")
    assert_entry.add_argument("--entry-agent", required=True)

    route = sub.add_parser("route-task", help="route task by routing rules")
    route.add_argument("--description", required=True)
    route.add_argument("--source", default="openclaw")

    update = sub.add_parser("update-routing", help="update routing rules")
    update.add_argument("--add-high-risk", action="append", default=[])
    update.add_argument("--add-low-risk", action="append", default=[])
    update.add_argument("--add-priority-high", action="append", default=[])
    update.add_argument("--add-priority-low", action="append", default=[])
    update.add_argument("--add-assignee-rule", action="append", default=[])
    update.add_argument("--default-assignee", default="")

    stop_safe = sub.add_parser("assert-stop-safe", help="fail when unresolved tasks exist")
    _ = stop_safe

    validate = sub.add_parser("validate-runtime", help="validate policy runtime files")
    _ = validate

    check_config = sub.add_parser("check-config", help="run hardflow config checklist")
    check_config.add_argument("--openclaw-config", default=defaults["openclaw_config"])
    check_config.add_argument("--project-registry", default=defaults["project_registry"])
    check_config.add_argument("--strict", action="store_true", help="return non-zero when any check fails")
    _ = check_config

    return parser


def cmd_init(paths: RuntimePaths, force: bool) -> dict[str, Any]:
    paths.db.parent.mkdir(parents=True, exist_ok=True)

    for file_path, defaults in [
        (paths.policy_file, DEFAULT_POLICY),
        (paths.routing_file, DEFAULT_ROUTING_RULES),
        (paths.pricing_file, DEFAULT_TOKEN_PRICING),
    ]:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not file_path.exists():
            file_path.write_text(
                json.dumps(defaults, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    db = TaskCenter(paths.db)
    db.init_schema()
    db.close()

    return {
        "ok": True,
        "db": str(paths.db),
        "policy_file": str(paths.policy_file),
        "routing_file": str(paths.routing_file),
        "pricing_file": str(paths.pricing_file),
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    paths = RuntimePaths(
        db=Path(args.db).expanduser(),
        policy_file=Path(args.policy_file).expanduser(),
        routing_file=Path(args.routing_file).expanduser(),
        pricing_file=Path(args.pricing_file).expanduser(),
    )

    try:
        if args.command == "init":
            emit_json(cmd_init(paths=paths, force=args.force))
            return 0

        enforcer = PolicyEnforcer(paths)
        try:
            if args.command == "create-task":
                emit_json({"ok": True, "task": enforcer.create_task(args)})
            elif args.command == "assign-task":
                emit_json({"ok": True, "task": enforcer.assign_task(args)})
            elif args.command == "confirm-risk":
                emit_json({"ok": True, "task": enforcer.confirm_risk(args)})
            elif args.command == "pre-stage":
                emit_json({"ok": True, "task": enforcer.pre_stage(args)})
            elif args.command == "post-stage":
                emit_json({"ok": True, "task": enforcer.post_stage(args)})
            elif args.command == "complete-task":
                emit_json({"ok": True, "task": enforcer.complete_task(args)})
            elif args.command == "record-token":
                emit_json({"ok": True, "usage": enforcer.record_token(args)})
            elif args.command == "daily-summary":
                emit_json({"ok": True, "summary": enforcer.daily_summary(args)})
            elif args.command == "task-report":
                emit_json({"ok": True, "report": enforcer.task_report(args)})
            elif args.command == "route-task":
                emit_json({"ok": True, "route": enforcer.route_task(args)})
            elif args.command == "update-routing":
                emit_json({"ok": True, "result": enforcer.update_routing(args)})
            elif args.command == "assert-entry":
                emit_json(enforcer.assert_entry(args))
            elif args.command == "assert-stop-safe":
                emit_json(enforcer.assert_stop_safe(args))
            elif args.command == "validate-runtime":
                emit_json(enforcer.validate_runtime(args))
            elif args.command == "check-config":
                emit_json(enforcer.check_config(args))
            else:
                raise PolicyError(f"unsupported command: {args.command}")
            return 0
        finally:
            enforcer.close()
    except (PolicyError, TaskCenterError, ValueError) as exc:
        emit_json({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())

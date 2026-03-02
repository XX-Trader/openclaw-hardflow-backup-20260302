#!/usr/bin/env python3
"""Policy-Enforcer: fail-close policy checks for OpenClaw workflows."""

from __future__ import annotations

import argparse
import json
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
    "primary_model": "glmcode/glm-5",
    "fallback_models": ["kimicode/kimi-k2.5", "glmcode/glm-4.7"],
    "allowed_models": ["glmcode/glm-5", "kimicode/kimi-k2.5", "glmcode/glm-4.7"],
    "allowed_entry_agents": ["coordinator"],
    "blocked_direct_code_agents": ["coordinator", "project-agent"],
    "code_execution_stages": ["implement", "fix", "deploy"],
    "required_task_fields": ["reason", "requirement", "result_output", "acceptance"],
    "high_risk_requires_human_confirm": True,
    "max_failure_before_escalate": 3,
    "pass_line_raw": 75.0,
    "status_flow": {
        "pending": ["running", "cancelled", "escalated"],
        "running": ["running", "passed", "failed", "escalated", "cancelled"],
        "failed": ["running", "escalated", "cancelled"],
        "escalated": ["running", "cancelled", "passed"],
        "passed": [],
        "cancelled": [],
    },
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
    ],
    "low_risk_keywords": ["文档", "索引", "注释", "整理", "汇总", "排版"],
    "priority_keywords": {
        "high": ["紧急", "立即", "故障", "异常", "失败", "告警", "中断", "不可用"],
        "low": ["后续", "延后", "慢慢", "优化", "观察", "待办"],
    },
    "assignee_rules": [
        {"assignee": "ops-agent", "keywords": ["cron", "日志", "监控", "运维", "服务", "网关"]},
        {"assignee": "backend-dev", "keywords": ["api", "后端", "数据库", "模型", "接口"]},
        {"assignee": "frontend-dev", "keywords": ["前端", "页面", "ui", "交互", "样式"]},
        {"assignee": "tester", "keywords": ["测试", "验收", "回归"]},
        {"assignee": "project-agent", "keywords": ["项目索引", "readme", "文档同步", "模块说明"]},
    ],
    "default_assignee": "backend-dev",
}

DEFAULT_TOKEN_PRICING: dict[str, Any] = {
    "version": "2026-03-02",
    "currency": "CNY",
    "unit": "per_1m_tokens",
    "models": {
        "glmcode/glm-5": {"input": 0, "output": 0},
        "kimicode/kimi-k2.5": {"input": 0, "output": 0},
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


def read_json(path: Path, default: dict[str, Any] | None = None, write_if_missing: bool = False) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
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

        need_human_confirm = parse_bool(args.need_human_confirm, risk_level == "high")

        payload = {
            "task_id": args.task_id,
            "pool": pool,
            "task_type": args.task_type,
            "reason": args.reason,
            "source": args.source,
            "priority": priority,
            "risk_level": risk_level,
            "assignee": args.assignee,
            "status": "pending",
            "need_human_confirm": need_human_confirm,
            "human_confirmed": parse_bool(args.human_confirmed, False),
            "requirement": args.requirement,
            "result_output": args.result_output,
            "acceptance": args.acceptance,
            "scheduled_at": args.scheduled_at,
        }

        created = self.db.create_task(payload, actor=args.actor)
        self.assert_required_fields(created)
        return created

    def assign_task(self, args: argparse.Namespace) -> dict[str, Any]:
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
        return updated

    def post_stage(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)
        exit_code = int(args.exit_code)

        if exit_code == 0:
            self.db.add_event(
                task_id=args.task_id,
                actor=args.actor,
                event_type="stage_passed",
                stage=args.stage,
                details={"exit_code": exit_code},
            )
            return self.db.get_task(args.task_id)

        updated = self.db.increment_failure(
            task_id=args.task_id,
            actor=args.actor,
            stage=args.stage,
            max_failure_before_escalate=self.max_failure_before_escalate(),
            reason=args.reason or f"stage {args.stage} failed with exit_code={exit_code}",
        )
        return updated

    def complete_task(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)

        result_score = float(args.result_score)
        stability_score = float(args.stability_score)
        critical_pass = parse_bool(args.critical_pass, True)

        raw_score = result_score * 0.70 + stability_score * 0.35
        normalized_score = (raw_score / 105.0) * 100.0

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Policy-Enforcer CLI")
    parser.add_argument(
        "--db",
        default=".workflow/task-center/task_center.db",
        help="sqlite database path",
    )
    parser.add_argument(
        "--policy-file",
        default="scripts/openclaw-ops/policy/policy-config.json",
    )
    parser.add_argument(
        "--routing-file",
        default="scripts/openclaw-ops/policy/routing-rules.json",
    )
    parser.add_argument(
        "--pricing-file",
        default="scripts/openclaw-ops/policy/token-pricing.json",
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
    create.add_argument("--need-human-confirm", default="")
    create.add_argument("--human-confirmed", default="false")
    create.add_argument("--requirement", required=True)
    create.add_argument("--result-output", required=True)
    create.add_argument("--acceptance", required=True)
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
    pre_stage.add_argument("--actor", default="policy-enforcer")

    post_stage = sub.add_parser("post-stage", help="policy record after stage")
    post_stage.add_argument("--task-id", required=True)
    post_stage.add_argument("--stage", required=True)
    post_stage.add_argument("--exit-code", required=True)
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
            elif args.command == "route-task":
                emit_json({"ok": True, "route": enforcer.route_task(args)})
            elif args.command == "update-routing":
                emit_json({"ok": True, "result": enforcer.update_routing(args)})
            elif args.command == "assert-stop-safe":
                emit_json(enforcer.assert_stop_safe(args))
            elif args.command == "validate-runtime":
                emit_json(enforcer.validate_runtime(args))
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

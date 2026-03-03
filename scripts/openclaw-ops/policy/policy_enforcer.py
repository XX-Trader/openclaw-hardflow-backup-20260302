#!/usr/bin/env python3
"""Policy-Enforcer: fail-close policy checks for OpenClaw workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
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
    "allow_project_agent_alias_entry": True,
    "project_agent_alias_prefixes": ["产品经理", "项目经理", "pm", "PM"],
    "dispatcher_agent": "coordinator",
    "dispatcher_fallback_self_execute": True,
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
    "context_policy": {
        "enabled": True,
        "ai_required_fields": [
            "problem",
            "location",
            "first_seen_at",
            "duration",
            "impact",
            "evidence",
            "target_state",
            "scope",
        ],
        "ai_min_completeness_pct": 100.0,
        "clarification_assignee": "project-agent",
        "human_project_keywords": [
            "项目",
            "项目规划",
            "项目说明",
            "项目索引",
            "模块",
            "readme",
            "api文档",
            "接口文档",
            "产品经理",
            "项目经理",
            "workflow",
            "架构",
        ],
    },
    "high_risk_requires_human_confirm": True,
    "require_token_usage_before_done": True,
    "max_failure_before_escalate": 3,
    "pass_line_raw": 75.0,
    "todo_queue_policy": {
        "require_scheduled_at": True,
        "fifo": True,
        "max_dispatch_per_run": 3,
    },
    "self_evolution_policy": {
        "enabled": True,
        "weekly_full_review": True,
        "min_review_interval_days": 7,
        "default_pool": "todo",
        "default_priority": "low",
        "default_risk_level": "high",
        "require_human_confirm": True,
        "max_tasks_per_run": 3,
        "schedule_gap_minutes": 120,
    },
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
    "version": "2026-03-03",
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
        "api变更",
        "接口变更",
        "参数变更",
        "逻辑变更",
        "流程变更",
        "结构变更",
        "schema变更",
        "cron异常",
        "事故",
        "中断",
        "outage",
        "security",
        "payment",
        "rollback",
    ],
    "low_risk_keywords": [
        "代码bug",
        "bug修复",
        "配置错误",
        "网络失败",
        "网络抖动",
        "cpu过高",
        "资源使用率高",
        "磁盘不足",
        "内存不足",
        "重复进程",
        "文档",
        "索引",
        "注释",
        "整理",
        "readme",
        "index",
    ],
    "priority_keywords": {
        "high": ["紧急", "立刻", "故障", "异常", "失败", "告警", "中断", "不可用", "urgent", "p0", "p1"],
        "low": ["后续", "延后", "慢慢", "优化", "观察", "待办", "backlog"],
    },
    "direct_route_prefixes": [
        {
            "prefixes": ["产品经理", "项目经理", "pm", "PM"],
            "entry_agent": "project-agent",
            "assignee": "project-agent",
            "bypass_dispatcher": True,
            "pool": "todo",
            "priority": "low",
        }
    ],
    "assignee_rules": [
        {
            "assignee": "ops-agent",
            "keywords": ["cron", "日志", "监控", "运维", "服务", "网关", "infra", "资源", "磁盘", "内存", "cpu"],
        },
        {
            "assignee": "backend-dev",
            "keywords": ["api", "后端", "数据库", "模型", "接口", "backend", "参数"],
        },
        {
            "assignee": "frontend-dev",
            "keywords": ["前端", "页面", "ui", "交互", "样式", "frontend"],
        },
        {
            "assignee": "tester",
            "keywords": ["测试", "验收", "回归", "qa", "selenium", "playwright"],
        },
        {
            "assignee": "project-agent",
            "keywords": [
                "项目",
                "项目优化",
                "功能优化",
                "项目耦合",
                "代码耦合",
                "项目配置规范",
                "业务配置规范",
                "可维护性优化",
                "重复实现治理",
                "模块解耦",
                "项目结构优化",
                "项目重构",
                "项目索引",
                "项目规划",
                "需求沟通",
            ],
        },
        {
            "assignee": "optimization-agent",
            "keywords": [
                "优化agent",
                "agent优化",
                "工作流优化",
                "workflow优化",
                "技能优化",
                "技能治理",
                "skill治理",
                "路由优化",
                "cron策略",
                "hooks优化",
                "policy优化",
                "流程优化",
                "经验维护",
                "频率策略",
                "全量校准",
            ],
        },
        {
            "assignee": "self-evolution-agent",
            "keywords": ["自我进化", "经验沉淀", "历史会话复盘", "经验库", "规律总结"],
        },
    ],
    "default_assignee": "coordinator",
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

    def allow_project_agent_alias_entry(self) -> bool:
        return parse_bool(self.policy.get("allow_project_agent_alias_entry", True), True)

    def project_agent_alias_prefixes(self) -> list[str]:
        raw = self.policy.get("project_agent_alias_prefixes", [])
        if not isinstance(raw, list):
            return []
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out or ["产品经理", "项目经理", "pm", "PM"]

    def dispatcher_fallback_self_execute(self) -> bool:
        return parse_bool(self.policy.get("dispatcher_fallback_self_execute", True), True)

    def todo_queue_max_dispatch(self) -> int:
        cfg = self.policy.get("todo_queue_policy", {})
        if not isinstance(cfg, dict):
            return 3
        value = int(cfg.get("max_dispatch_per_run", 3) or 3)
        return max(1, value)

    def todo_require_scheduled_at(self) -> bool:
        cfg = self.policy.get("todo_queue_policy", {})
        if not isinstance(cfg, dict):
            return True
        return parse_bool(cfg.get("require_scheduled_at", True), True)

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

    def context_policy(self) -> dict[str, Any]:
        raw = self.policy.get("context_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("context_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)

    def normalize_request_source(self, request_source: str | None, source_hint: str | None = None) -> str:
        raw = str(request_source or "").strip().lower()
        if raw in {"human", "user", "manual", "chat"}:
            return "human"
        if raw in {"ai", "agent", "bot", "automation", "auto", "cron", "system"}:
            return "ai"
        if any(token in raw for token in {"human", "manual", "user", "chat"}):
            return "human"
        if any(token in raw for token in {"agent", "bot", "cron", "auto", "automation", "patrol", "audit", "ops"}):
            return "ai"

        hint = str(source_hint or "").strip().lower()
        if hint in {"human", "user", "manual", "chat"}:
            return "human"
        if hint in {"ai", "agent", "bot", "cron", "audit", "patrol", "ops", "system", "automation", "auto"}:
            return "ai"
        if any(token in hint for token in {"human", "manual", "user", "chat"}):
            return "human"
        if any(token in hint for token in {"agent", "bot", "cron", "auto", "automation", "patrol", "audit", "ops"}):
            return "ai"
        return "human"

    def parse_context_json_arg(self, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"context-json is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyError("context-json must be a JSON object")
        return data

    def parse_context_payload(self, context_json: str, context_file: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {}
        path_text = str(context_file or "").strip()
        if path_text:
            path = Path(path_text).expanduser()
            if not path.exists():
                raise PolicyError(f"context-file not found: {path}")
            try:
                file_data = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise PolicyError(f"context-file is not valid JSON: {exc}") from exc
            if not isinstance(file_data, dict):
                raise PolicyError("context-file must be a JSON object")
            payload.update(file_data)
        payload.update(self.parse_context_json_arg(context_json))
        return payload

    def extract_context_from_text(self, text: str) -> dict[str, str]:
        raw = str(text or "").strip()
        location = ""
        first_seen = ""
        duration = ""
        impact = ""
        evidence = ""
        target_state = ""

        location_match = re.search(
            r"(https?://\S+|/[A-Za-z0-9._/\-]+(?:\?[^\s]+)?|[A-Za-z]:\\[^\s]+|[\w./-]+\.(?:py|js|ts|tsx|json|ya?ml|md|sql|sh|log))",
            raw,
        )
        if location_match:
            location = location_match.group(1)

        first_seen_match = re.search(r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", raw)
        if first_seen_match:
            first_seen = first_seen_match.group(0)

        duration_match = re.search(r"(持续[^，。；;\s]{1,24}|[0-9]+(?:分钟|小时|天|周))", raw)
        if duration_match:
            duration = duration_match.group(1)

        impact_keywords = ["影响", "阻塞", "不可用", "失败", "报错", "错误", "超时", "404", "500", "延迟", "回退"]
        for kw in impact_keywords:
            if kw in raw:
                impact = f"contains:{kw}"
                break

        evidence_match = re.search(
            r"(证据路径[:：]?\s*[^\s，。；;]+|/home/[^\s，。；;]+|[A-Za-z]:\\[^\s，。；;]+|[\w./-]+\.(?:json|log|txt))",
            raw,
        )
        if evidence_match:
            evidence = evidence_match.group(1)

        target_match = re.search(r"(修复[^，。；;\n]{1,40}|恢复[^，。；;\n]{1,40}|目标[^，。；;\n]{1,40}|需要[^，。；;\n]{1,40})", raw)
        if target_match:
            target_state = target_match.group(1)

        return {
            "problem": raw,
            "location": location,
            "first_seen_at": first_seen,
            "duration": duration,
            "impact": impact,
            "evidence": evidence,
            "target_state": target_state,
            "scope": "task_description",
        }

    def evaluate_context_gate(
        self,
        request_source: str,
        context_payload: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self.context_policy()
        if not parse_bool(cfg.get("enabled", True), True):
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "required_fields": [],
            }

        if request_source != "ai":
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "required_fields": [],
            }

        required_raw = cfg.get("ai_required_fields", [])
        if not isinstance(required_raw, list):
            raise PolicyError("context_policy.ai_required_fields must be a list")
        required_fields = [str(x).strip() for x in required_raw if str(x).strip()]
        if not required_fields:
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "required_fields": [],
            }

        missing_fields = [field for field in required_fields if not str(context_payload.get(field, "")).strip()]
        completeness = round(((len(required_fields) - len(missing_fields)) / len(required_fields)) * 100.0, 2)
        min_pct = float(cfg.get("ai_min_completeness_pct", 100.0) or 100.0)
        needs_clarification = completeness < min_pct or bool(missing_fields)
        reason = ""
        if needs_clarification:
            reason = (
                f"ai_context_incomplete: completeness={completeness:.2f}, "
                f"required={len(required_fields)}, missing={','.join(missing_fields)}"
            )
        return {
            "needs_clarification": needs_clarification,
            "clarification_reason": reason,
            "context_completeness": completeness,
            "missing_fields": missing_fields,
            "required_fields": required_fields,
        }

    def clarification_assignee(self) -> str:
        cfg = self.context_policy()
        value = str(cfg.get("clarification_assignee", "project-agent")).strip()
        return value or "project-agent"

    def is_human_project_requirement(self, text: str) -> tuple[bool, list[str]]:
        cfg = self.context_policy()
        keywords_raw = cfg.get("human_project_keywords", [])
        if not isinstance(keywords_raw, list):
            keywords_raw = []
        norm = str(text or "").lower()
        hits = [str(x) for x in keywords_raw if str(x).strip() and str(x).lower() in norm]
        return bool(hits), hits

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
        if entry_agent == "project-agent" and self.allow_project_agent_alias_entry():
            return
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

        request_source = self.normalize_request_source(
            getattr(args, "request_source", ""),
            getattr(args, "source", ""),
        )
        context_payload = self.parse_context_payload(
            getattr(args, "context_json", ""),
            getattr(args, "context_file", ""),
        )
        if not context_payload:
            context_payload = self.extract_context_from_text(args.reason)
        if not str(context_payload.get("problem", "")).strip():
            context_payload["problem"] = str(args.reason).strip()
        if not str(context_payload.get("target_state", "")).strip():
            context_payload["target_state"] = str(args.result_output).strip()
        if not str(context_payload.get("scope", "")).strip():
            context_payload["scope"] = str(args.requirement).strip()
        if not str(context_payload.get("acceptance", "")).strip():
            context_payload["acceptance"] = str(args.acceptance).strip()
        if not str(context_payload.get("evidence", "")).strip():
            context_payload["evidence"] = str(args.observable_outputs).strip()

        context_eval = self.evaluate_context_gate(request_source, context_payload)
        force_needs_clarification = parse_bool(getattr(args, "force_needs_clarification", ""), False)
        needs_clarification = force_needs_clarification or bool(context_eval["needs_clarification"])
        clarification_reason = str(getattr(args, "clarification_reason", "") or "").strip()
        if not clarification_reason:
            clarification_reason = str(context_eval.get("clarification_reason", "")).strip()

        need_human_confirm = parse_bool(args.need_human_confirm, risk_level == "high")
        scheduled_at = str(args.scheduled_at or "").strip()
        if pool == "todo" and self.todo_require_scheduled_at() and not scheduled_at:
            scheduled_at = now_iso()

        assignee = str(args.assignee or "").strip() or self.dispatcher_agent()
        task_type = str(args.task_type or "workflow").strip()
        if needs_clarification:
            assignee = self.clarification_assignee()
            pool = "todo"
            if priority == "low":
                priority = "medium"
            if task_type == "workflow":
                task_type = "clarification_required"

        payload = {
            "task_id": args.task_id,
            "pool": pool,
            "task_type": task_type,
            "reason": args.reason,
            "source": args.source,
            "request_source": request_source,
            "priority": priority,
            "risk_level": risk_level,
            "assignee": assignee,
            "status": "pending",
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "need_human_confirm": need_human_confirm,
            "human_confirmed": parse_bool(args.human_confirmed, False),
            "context_completeness": float(context_eval.get("context_completeness", 0.0) or 0.0),
            "context_fields_missing": context_eval.get("missing_fields", []),
            "context_payload": context_payload,
            "requirement": args.requirement,
            "result_output": args.result_output,
            "acceptance": args.acceptance,
            "observable_outputs": args.observable_outputs,
            "acceptance_thresholds": args.acceptance_thresholds,
            "scheduled_at": scheduled_at,
        }

        created = self.db.create_task(payload, actor=args.actor)
        self.assert_required_fields(created)
        self.db.add_event(
            task_id=created["task_id"],
            actor=args.actor,
            event_type="context_gate_evaluated",
            stage="intake",
            details={
                "request_source": request_source,
                "needs_clarification": bool(created.get("needs_clarification")),
                "context_completeness": created.get("context_completeness"),
                "missing_fields": created.get("context_fields_missing", []),
            },
        )
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
        assignee = str(args.assignee or "").strip()
        fallback_used = False
        if assignee.lower() in {"", "none", "null", "unassigned"}:
            if not self.dispatcher_fallback_self_execute():
                raise PolicyError("assignee empty and dispatcher_fallback_self_execute is disabled")
            assignee = self.dispatcher_agent()
            fallback_used = True

        assigned = self.db.assign_task(task_id=args.task_id, assignee=assignee, actor=args.actor)
        if fallback_used:
            with self.db.conn:
                self.db.add_event(
                    task_id=args.task_id,
                    actor=args.actor,
                    event_type="assign_fallback_self_execute",
                    stage="assign",
                    details={
                        "fallback_assignee": assignee,
                        "requested_assignee": str(args.assignee or "").strip(),
                        "reason": str(args.reason or "dispatcher_unable_to_route").strip(),
                    },
                )
        return assigned

    def confirm_risk(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.db.confirm_human(task_id=args.task_id, actor=args.actor, confirmed=parse_bool(args.confirmed, True))

    def resolve_clarification(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)
        request_source = self.normalize_request_source(str(task.get("request_source", "")), str(task.get("source", "")))
        current_context = task.get("context_payload", {})
        if not isinstance(current_context, dict):
            current_context = {}

        patch_context = self.parse_context_payload(
            getattr(args, "context_json", ""),
            getattr(args, "context_file", ""),
        )
        if not patch_context:
            raise PolicyError("resolve-clarification requires --context-json or --context-file")
        merged_context = dict(current_context)
        merged_context.update(patch_context)

        context_eval = self.evaluate_context_gate(request_source, merged_context)
        if bool(context_eval.get("needs_clarification")):
            return self.db.update_clarification(
                task_id=args.task_id,
                actor=args.actor,
                needs_clarification=True,
                clarification_reason=str(context_eval.get("clarification_reason", "")).strip() or "context_incomplete",
                context_payload=merged_context,
                context_completeness=float(context_eval.get("context_completeness", 0.0) or 0.0),
                context_fields_missing=list(context_eval.get("missing_fields", [])),
            )

        return self.db.update_clarification(
            task_id=args.task_id,
            actor=args.actor,
            needs_clarification=False,
            clarification_reason="",
            context_payload=merged_context,
            context_completeness=float(context_eval.get("context_completeness", 100.0) or 100.0),
            context_fields_missing=[],
        )

    def pre_stage(self, args: argparse.Namespace) -> dict[str, Any]:
        task = self.db.get_task(args.task_id)
        self.assert_required_fields(task)
        if bool(task.get("needs_clarification")):
            missing = task.get("context_fields_missing", [])
            reason = str(task.get("clarification_reason", "")).strip() or "context_incomplete"
            raise PolicyError(
                f"task requires clarification before execution: task_id={args.task_id}, "
                f"reason={reason}, missing={','.join(missing)}"
            )
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
        request_source = self.normalize_request_source(
            getattr(args, "request_source", ""),
            getattr(args, "source", ""),
        )

        def try_direct_project_route(raw_text: str) -> tuple[dict[str, Any] | None, str]:
            route_rules = self.routing.get("direct_route_prefixes", [])
            direct_aliases: list[dict[str, Any]] = []
            if isinstance(route_rules, list):
                for item in route_rules:
                    if isinstance(item, dict):
                        direct_aliases.append(item)
            if not direct_aliases:
                direct_aliases = [
                    {
                        "prefixes": self.project_agent_alias_prefixes(),
                        "entry_agent": "project-agent",
                        "assignee": "project-agent",
                        "bypass_dispatcher": True,
                        "pool": "todo",
                        "priority": "low",
                    }
                ]

            for rule in direct_aliases:
                prefixes = rule.get("prefixes", [])
                if not isinstance(prefixes, list):
                    continue
                for prefix in prefixes:
                    prefix_text = str(prefix).strip()
                    if not prefix_text:
                        continue
                    pattern = rf"^\s*{re.escape(prefix_text)}(?:[\s:：,\-，]+)?(?P<body>.*)$"
                    m = re.match(pattern, raw_text, flags=re.IGNORECASE)
                    if not m:
                        continue
                    if not self.allow_project_agent_alias_entry():
                        break
                    stripped = str(m.group("body") or "").strip() or raw_text.strip()
                    return (
                        {
                            "alias_prefix": prefix_text,
                            "entry_agent": str(rule.get("entry_agent", "project-agent")).strip() or "project-agent",
                            "assignee": str(rule.get("assignee", "project-agent")).strip() or "project-agent",
                            "bypass_dispatcher": bool(rule.get("bypass_dispatcher", True)),
                            "pool": str(rule.get("pool", "todo")).strip() or "todo",
                            "priority": str(rule.get("priority", "low")).strip() or "low",
                        },
                        stripped,
                    )
            return None, raw_text

        direct_route, effective_text = try_direct_project_route(text)
        effective_norm = effective_text.lower()

        high_risk_hits = [k for k in self.routing.get("high_risk_keywords", []) if str(k).lower() in effective_norm]
        low_risk_hits = [k for k in self.routing.get("low_risk_keywords", []) if str(k).lower() in effective_norm]

        risk_level = "high" if high_risk_hits else "low"

        priority = "low"
        high_priority_hits = [
            k
            for k in self.routing.get("priority_keywords", {}).get("high", [])
            if str(k).lower() in effective_norm
        ]
        low_priority_hits = [
            k
            for k in self.routing.get("priority_keywords", {}).get("low", [])
            if str(k).lower() in effective_norm
        ]
        if high_priority_hits:
            priority = "high"
        elif risk_level == "high":
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
                if str(keyword).lower() in effective_norm:
                    assignee = candidate
                    assignee_hit = str(keyword)
                    break
            if assignee_hit:
                break

        entry_agent = sorted(self.allowed_entry_agents())[0] if self.allowed_entry_agents() else ""
        bypass_dispatcher = False
        if direct_route:
            entry_agent = str(direct_route.get("entry_agent", entry_agent)).strip() or entry_agent
            assignee = str(direct_route.get("assignee", assignee)).strip() or assignee
            bypass_dispatcher = bool(direct_route.get("bypass_dispatcher", False))
            priority = str(direct_route.get("priority", priority)).strip() or priority
            pool = str(direct_route.get("pool", "todo")).strip() or "todo"
        else:
            pool = "jobs" if priority == "high" else "todo"

        project_requirement = False
        project_hits: list[str] = []
        if request_source == "human":
            project_requirement, project_hits = self.is_human_project_requirement(effective_text)
            if project_requirement and not direct_route:
                entry_agent = "project-agent"
                assignee = "project-agent"
                bypass_dispatcher = True
                pool = "todo"
                if priority == "low":
                    priority = "medium"

        context_payload = self.extract_context_from_text(effective_text)
        context_patch = self.parse_context_payload(
            getattr(args, "context_json", ""),
            getattr(args, "context_file", ""),
        )
        context_payload.update(context_patch)
        context_eval = self.evaluate_context_gate(request_source, context_payload)
        needs_clarification = bool(context_eval.get("needs_clarification"))
        clarification_reason = str(context_eval.get("clarification_reason", "")).strip()
        if needs_clarification:
            entry_agent = "project-agent"
            assignee = self.clarification_assignee()
            bypass_dispatcher = True
            pool = "todo"
            if priority == "low":
                priority = "medium"

        need_human_confirm = risk_level == "high" and parse_bool(
            self.policy.get("high_risk_requires_human_confirm", True),
            True,
        )

        return {
            "description": effective_text,
            "raw_description": text,
            "source": args.source,
            "request_source": request_source,
            "entry_agent": entry_agent,
            "dispatcher_agent": self.dispatcher_agent(),
            "bypass_dispatcher": bypass_dispatcher,
            "priority": priority,
            "risk_level": risk_level,
            "pool": pool,
            "assignee": assignee,
            "need_human_confirm": need_human_confirm,
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "context_completeness": float(context_eval.get("context_completeness", 100.0) or 100.0),
            "context_fields_missing": list(context_eval.get("missing_fields", [])),
            "context_payload": context_payload,
            "hits": {
                "high_risk": high_risk_hits,
                "low_risk": low_risk_hits,
                "priority_high": high_priority_hits,
                "priority_low": low_priority_hits,
                "assignee_hit": assignee_hit,
                "project_requirement": project_requirement,
                "project_hits": project_hits,
                "direct_route_prefix": str(direct_route.get("alias_prefix", "")) if direct_route else "",
            },
        }

    def next_todo(self, args: argparse.Namespace) -> dict[str, Any]:
        limit_raw = int(args.limit or 0)
        limit = self.todo_queue_max_dispatch() if limit_raw <= 0 else max(1, limit_raw)
        now_value = now_iso()
        rows = self.db.conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE pool = 'todo'
              AND status = 'pending'
              AND (scheduled_at IS NULL OR scheduled_at <= ?)
            ORDER BY COALESCE(scheduled_at, created_at) ASC, created_at ASC
            LIMIT ?
            """,
            (now_value, limit),
        ).fetchall()
        tasks = []
        for row in rows:
            item = dict(row)
            item["need_human_confirm"] = bool(item.get("need_human_confirm"))
            item["human_confirmed"] = bool(item.get("human_confirmed"))
            tasks.append(item)
        return {
            "policy_limit": self.todo_queue_max_dispatch(),
            "requested_limit": limit_raw,
            "effective_limit": limit,
            "now": now_value,
            "tasks": tasks,
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
        add_check(
            "project_agent_alias_entry_enabled",
            self.allow_project_agent_alias_entry(),
            f"allow_project_agent_alias_entry={self.allow_project_agent_alias_entry()}",
        )
        add_check(
            "dispatcher_fallback_self_execute_enabled",
            self.dispatcher_fallback_self_execute(),
            f"dispatcher_fallback_self_execute={self.dispatcher_fallback_self_execute()}",
        )
        ctx = self.context_policy()
        add_check(
            "context_policy_enabled",
            parse_bool(ctx.get("enabled", True), True),
            f"enabled={parse_bool(ctx.get('enabled', True), True)}",
        )
        add_check(
            "context_policy_clarification_assignee",
            bool(str(ctx.get("clarification_assignee", "")).strip()),
            f"clarification_assignee={ctx.get('clarification_assignee', '')}",
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
    create.add_argument("--request-source", default="")
    create.add_argument("--priority", default="low")
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
    create.add_argument("--context-json", default="")
    create.add_argument("--context-file", default="")
    create.add_argument("--force-needs-clarification", default="false")
    create.add_argument("--clarification-reason", default="")
    create.add_argument("--scheduled-at", default="")
    create.add_argument("--actor", default="policy-enforcer")

    assign = sub.add_parser("assign-task", help="assign task")
    assign.add_argument("--task-id", required=True)
    assign.add_argument("--assignee", default="")
    assign.add_argument("--reason", default="dispatcher_unable_to_route")
    assign.add_argument("--actor", default="coordinator")

    confirm = sub.add_parser("confirm-risk", help="confirm high-risk task")
    confirm.add_argument("--task-id", required=True)
    confirm.add_argument("--confirmed", default="true")
    confirm.add_argument("--actor", default="human")

    resolve = sub.add_parser("resolve-clarification", help="append context and resolve clarification gate")
    resolve.add_argument("--task-id", required=True)
    resolve.add_argument("--context-json", default="")
    resolve.add_argument("--context-file", default="")
    resolve.add_argument("--actor", default="project-agent")

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
    route.add_argument("--request-source", default="")
    route.add_argument("--context-json", default="")
    route.add_argument("--context-file", default="")

    next_todo = sub.add_parser("next-todo", help="get FIFO todo batch by policy limit")
    next_todo.add_argument("--limit", default="0")

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
            elif args.command == "resolve-clarification":
                emit_json({"ok": True, "task": enforcer.resolve_clarification(args)})
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
            elif args.command == "next-todo":
                emit_json({"ok": True, "result": enforcer.next_todo(args)})
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


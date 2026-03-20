#!/usr/bin/env python3
"""Policy-Enforcer: fail-close policy checks for OpenClaw workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utf8_runtime import configure_process_utf8_stdio
from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic
from task_capability_binding import infer_task_capability_constraints
from task_center import (
    TASK_STATUSES,
    TaskCenter,
    TaskCenterError,
    estimate_cost,
    format_daily_summary_markdown,
    load_pricing,
)

configure_process_utf8_stdio()

UTC = timezone.utc
GOVERNANCE_BRIDGE_EPILOG = (
    "Bridge contract: keep governance logic in Python, trigger it via official "
    "OpenClaw cron/hooks/webhook surfaces, return structured JSON or NO_REPLY, "
    "and do not mutate vendor private runtime state files directly."
)

DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": "2026-03-08",
    "primary_model": "kimicode/doubao-seed-2.0-pro",
    "fallback_models": [
        "openai-codex/gpt-5.3-codex",
        "glmcode/glm-5",
        "glmcode/glm-4.7",
    ],
    "allowed_models": [
        "openai-codex/gpt-5.4",
        "openai-codex/gpt-5.3-codex",
        "glmcode/glm-5",
        "glmcode/glm-4.7",
        "kimicode/doubao-seed-2.0-pro",
        "kimicode/Doubao-Seed-2.0-Code",
        "volcengine/kimi-k2.5",
    ],
    "agent_model_overrides": {
        "main": "kimicode/doubao-seed-2.0-pro",
        "coordinator": "kimicode/doubao-seed-2.0-pro",
        "reviewer": "kimicode/doubao-seed-2.0-pro",
        "agent-factory": "openai-codex/gpt-5.3-codex",
        "backend-dev": "openai-codex/gpt-5.3-codex",
        "frontend-dev": "openai-codex/gpt-5.3-codex",
        "optimization-agent": "openai-codex/gpt-5.3-codex",
        "project-agent": "openai-codex/gpt-5.3-codex",
        "doc-writer": "glmcode/glm-4.7",
        "deployer": "glmcode/glm-4.7",
        "ops-agent": "glmcode/glm-4.7",
        "tester": "glmcode/glm-4.7",
        "web-agent": "glmcode/glm-4.7",
    },
    "model_thinking_overrides": {
        "openai-codex/gpt-5.4": "xhigh",
        "openai-codex/gpt-5.3-codex": "xhigh",
        "glmcode/glm-5": "high",
        "glmcode/glm-4.7": "high",
        "kimicode/doubao-seed-2.0-pro": "high",
        "kimicode/Doubao-Seed-2.0-Code": "high",
    },
    "allowed_entry_agents": ["coordinator"],
    "allow_project_agent_alias_entry": True,
    "project_agent_alias_prefixes": ["产品经理", "项目经理", "pm", "PM"],
    "dispatcher_agent": "coordinator",
    "dispatcher_fallback_self_execute": True,
    "blocked_direct_code_agents": ["coordinator", "project-agent"],
    "code_execution_stages": ["implement", "fix", "deploy"],
    "project_dispatch_policy": {
        "enabled": True,
        "force_dispatch_code_tasks": True,
        "code_task_keywords": [
            "write code",
            "coding",
            "implement",
            "bugfix",
            "fix bug",
            "refactor",
            "开发",
            "写代码",
            "修复",
            "实现",
            "代码",
        ],
        "frontend_keywords": [
            "frontend",
            "ui",
            "页面",
            "前端",
            "样式",
            "交互",
        ],
        "backend_keywords": [
            "backend",
            "api",
            "服务端",
            "后端",
            "数据库",
            "接口",
        ],
        "tester_keywords": [
            "test",
            "qa",
            "测试",
            "回归",
            "验收",
            "playwright",
        ],
        "default_code_assignee": "backend-dev",
    },
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
            "impact",
            "evidence",
            "current_state",
            "expected_state",
            "operation_path",
            "reproduction_steps",
            "scope",
            "constraints",
            "acceptance_criteria",
            "full_background",
        ],
        "ai_recommended_fields": [
            "duration",
            "trigger_conditions",
            "dependencies",
            "history_changes",
            "deliverables",
            "owner",
            "change_id",
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
    "agent_points_policy": {
        "enabled": True,
        "leaderboard_lookback_days": 14,
        "quality_weight": 0.75,
        "timeliness_weight": 0.25,
        "planner_share": 0.35,
        "planner_scoring_mode": "dispatch_count",
        "planner_dispatch_points_by_priority": {
            "low": 1.0,
            "medium": 1.5,
            "high": 2.0,
        },
        "planner_dispatch_risk_multiplier": {
            "low": 1.0,
            "high": 1.1,
        },
        "minimum_quality_for_positive": 70.0,
        "base_points_by_priority": {
            "low": 4.0,
            "medium": 8.0,
            "high": 12.0,
        },
        "risk_multiplier": {
            "low": 1.0,
            "high": 1.15,
        },
        "timeliness_sla_ms_by_priority": {
            "low": 14_400_000,
            "medium": 7_200_000,
            "high": 3_600_000,
        },
    },
    "todo_queue_policy": {
        "require_scheduled_at": True,
        "fifo": True,
        "max_dispatch_per_run": 3,
        "agent_guarantee": {
            "enabled": True,
            "min_tasks_per_agent": 1,
            "low_score_threshold": 12.0,
            "lookback_days": 7,
        },
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
    "post_deploy_test_policy": {
        "enabled": True,
        "deploy_stage_names": ["deploy"],
        "post_test_stage_names": ["post-test", "post_test", "postdeploy-test", "postdeploy_test"],
        "require_post_test_after_deploy": True,
        "missing_post_test_action": "post_deploy_test_required",
        "failed_post_test_action": "retry_fix_after_post_deploy_test",
    },
    "agent_output_policy": {
        "default_language": "zh-CN",
        "require_chinese_output": True,
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
        "生产", "部署", "支付", "安全", "密钥", "权限", "数据库", "迁移", "删除", "回滚",
        "api变更", "接口变更", "参数变更", "逻辑变更", "流程变更", "结构变更", "schema变更",
        "cron异常", "事故", "中断", "outage", "security", "payment", "rollback",
    ],
    "low_risk_keywords": [
        "代码bug", "bug修复", "配置错误", "网络失败", "网络抖动", "cpu过高", "资源使用率高",
        "磁盘不足", "内存不足", "重复进程", "文档", "索引", "注释", "整理", "readme", "index",
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
                "项目", "项目优化", "功能优化", "项目耦合", "代码耦合", "项目配置规范", "业务配置规范",
                "可维护性优化", "重复实现治理", "模块解耦", "项目结构优化", "项目重构", "项目索引", "项目规划", "需求沟通",
            ],
        },
        {
            "assignee": "optimization-agent",
            "keywords": [
                "增量审查", "增量巡检", "workflow审查", "技能审查", "hooks审查", "agent审查",
                "优化agent", "agent优化", "工作流优化", "workflow优化", "技能优化", "技能治理",
                "skill治理", "路由优化", "cron策略", "hooks优化", "policy优化", "流程优化", "经验维护", "频率策略", "全量校准",
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
        "kimicode/doubao-seed-2.0-pro": {"input": 0, "output": 0},
        "kimicode/Doubao-Seed-2.0-Code": {"input": 0, "output": 0},
        "openai-codex/gpt-5.4": {"input": 0, "output": 0},
        "openai-codex/gpt-5.3-codex": {"input": 0, "output": 0},
        "glmcode/glm-4.7": {"input": 0, "output": 0},
        "volcengine/kimi-k2.5": {"input": 0, "output": 0},
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


def has_context_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(has_context_value(v) for v in value)
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"none", "n/a", "na", "unknown", "-", "未提供", "待补充"}:
        return False
    return True


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
        write_json_atomic(
            path,
            data,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
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
        return out or ["浜у搧缁忕悊", "椤圭洰缁忕悊", "pm", "PM"]

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

    def project_dispatch_policy(self) -> dict[str, Any]:
        raw = self.policy.get("project_dispatch_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("project_dispatch_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)

    def post_deploy_test_policy(self) -> dict[str, Any]:
        raw = self.policy.get("post_deploy_test_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("post_deploy_test_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)

    @staticmethod
    def _keyword_hits(text_norm: str, keywords_raw: Any) -> list[str]:
        if not isinstance(keywords_raw, list):
            return []
        hits: list[str] = []
        for item in keywords_raw:
            token = str(item or "").strip().lower()
            if token and token in text_norm:
                hits.append(token)
        return hits

    @staticmethod
    def _normalize_stage_names(stage_names_raw: Any, fallback: list[str]) -> set[str]:
        values = stage_names_raw if isinstance(stage_names_raw, list) else fallback
        names = {str(x or "").strip().lower() for x in values if str(x or "").strip()}
        return names or {str(x).strip().lower() for x in fallback if str(x).strip()}

    def evaluate_post_deploy_test_state(self, task_id: str) -> dict[str, Any]:
        cfg = self.post_deploy_test_policy()
        enabled = parse_bool(cfg.get("enabled", True), True)
        require_after_deploy = parse_bool(cfg.get("require_post_test_after_deploy", True), True)
        if not enabled or not require_after_deploy:
            return {
                "enabled": enabled,
                "required": False,
                "state": "disabled",
                "reason": "policy_disabled",
            }

        deploy_names = self._normalize_stage_names(cfg.get("deploy_stage_names"), ["deploy"])
        post_test_names = self._normalize_stage_names(
            cfg.get("post_test_stage_names"),
            ["post-test", "post_test", "postdeploy-test", "postdeploy_test"],
        )
        stage_runs = self.db.list_stage_runs(task_id)
        deploy_passed = [
            row
            for row in stage_runs
            if str(row.get("stage", "")).strip().lower() in deploy_names
            and str(row.get("status", "")).strip().lower() == "passed"
        ]
        if not deploy_passed:
            return {
                "enabled": enabled,
                "required": False,
                "state": "not_deployed",
                "reason": "deploy_passed_stage_not_found",
            }

        latest_deploy = deploy_passed[-1]
        latest_deploy_id = int(latest_deploy.get("id", 0) or 0)
        post_after_deploy = [
            row
            for row in stage_runs
            if str(row.get("stage", "")).strip().lower() in post_test_names
            and int(row.get("id", 0) or 0) > latest_deploy_id
        ]
        if not post_after_deploy:
            return {
                "enabled": enabled,
                "required": True,
                "state": "missing",
                "reason": "post_deploy_test_missing",
                "latest_deploy_stage_run_id": latest_deploy_id,
            }

        latest_post = post_after_deploy[-1]
        post_status = str(latest_post.get("status", "")).strip().lower()
        if post_status == "passed":
            state = "passed"
            reason = "post_deploy_test_passed"
        elif post_status == "failed":
            state = "failed"
            reason = "post_deploy_test_failed"
        else:
            state = "running"
            reason = "post_deploy_test_running"
        return {
            "enabled": enabled,
            "required": True,
            "state": state,
            "reason": reason,
            "latest_deploy_stage_run_id": latest_deploy_id,
            "latest_post_test_stage_run_id": int(latest_post.get("id", 0) or 0),
        }

    def points_policy(self) -> dict[str, Any]:
        raw = self.policy.get("agent_points_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("agent_points_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)

    def points_enabled(self) -> bool:
        return parse_bool(self.points_policy().get("enabled", True), True)

    def todo_agent_guarantee_policy(self) -> dict[str, Any]:
        todo_cfg = self.policy.get("todo_queue_policy", {})
        if not isinstance(todo_cfg, dict):
            todo_cfg = {}
        raw = todo_cfg.get("agent_guarantee", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = (
            DEFAULT_POLICY.get("todo_queue_policy", {}).get("agent_guarantee", {})
            if isinstance(DEFAULT_POLICY.get("todo_queue_policy", {}), dict)
            else {}
        )
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)

    def _priority_sla_ms(self, priority: str) -> int:
        policy = self.points_policy()
        sla_cfg = policy.get("timeliness_sla_ms_by_priority", {})
        if not isinstance(sla_cfg, dict):
            sla_cfg = {}
        value = int(sla_cfg.get(priority, 0) or 0)
        if value <= 0:
            if priority == "high":
                return 3_600_000
            if priority == "medium":
                return 7_200_000
            return 14_400_000
        return value

    def _base_points(self, priority: str, risk_level: str) -> float:
        policy = self.points_policy()
        base_map = policy.get("base_points_by_priority", {})
        if not isinstance(base_map, dict):
            base_map = {}
        risk_map = policy.get("risk_multiplier", {})
        if not isinstance(risk_map, dict):
            risk_map = {}
        base = float(base_map.get(priority, 6.0) or 6.0)
        multiplier = float(risk_map.get(risk_level, 1.0) or 1.0)
        return max(0.0, base * multiplier)

    def _planner_dispatch_points(self, priority: str, risk_level: str) -> float:
        policy = self.points_policy()
        base_map = policy.get("planner_dispatch_points_by_priority", {})
        if not isinstance(base_map, dict):
            base_map = {}
        risk_map = policy.get("planner_dispatch_risk_multiplier", {})
        if not isinstance(risk_map, dict):
            risk_map = {}
        base = float(base_map.get(priority, 1.0) or 1.0)
        multiplier = float(risk_map.get(risk_level, 1.0) or 1.0)
        return round(max(0.0, base * multiplier), 6)

    def _quality_factor(
        self,
        quality_score: float | None,
        solved: bool,
        status: str,
        minimum_quality: float,
    ) -> float:
        if quality_score is None:
            return 0.72 if solved and status in {"passed", "partial"} else 0.45
        q = max(0.0, min(100.0, float(quality_score)))
        factor = q / 100.0
        if solved and q < minimum_quality:
            factor *= 0.75
        return max(0.0, min(1.0, factor))

    def _timeliness_factor(self, duration_ms: int, priority: str) -> float:
        duration = max(0, int(duration_ms or 0))
        sla = self._priority_sla_ms(priority)
        if duration <= 0:
            return 0.9
        if duration <= sla:
            return 1.0
        if duration <= 2 * sla:
            ratio = (duration - sla) / max(1, sla)
            return max(0.6, 1.0 - ratio * 0.4)
        if duration <= 4 * sla:
            ratio = (duration - 2 * sla) / max(1, 2 * sla)
            return max(0.3, 0.6 - ratio * 0.3)
        return 0.2

    def _status_multiplier(self, status: str, solved: bool) -> float:
        if status == "passed":
            return 1.0 if solved else 0.8
        if status == "partial":
            return 0.72 if solved else 0.5
        if status == "failed":
            return -0.35
        if status == "escalated":
            return -0.5
        return -0.2

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

    def suggest_task_id(self, prefix: str = "task") -> str:
        raw_prefix = str(prefix or "task").strip().lower()
        normalized_prefix = re.sub(r"[^a-z0-9_-]+", "-", raw_prefix).strip("-")
        if not normalized_prefix:
            normalized_prefix = "task"
        return f"{normalized_prefix}-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def default_need_human_confirm(self, *, request_source: str, risk_level: str) -> bool:
        if str(request_source or "").strip().lower() == "human":
            return True
        if str(risk_level or "").strip().lower() != "high":
            return False
        return parse_bool(self.policy.get("high_risk_requires_human_confirm", True), True)

    def _task_confirmation_reason(self, task: dict[str, Any]) -> str:
        if bool(task.get("needs_clarification")):
            return "clarification_required"
        if not bool(task.get("need_human_confirm")):
            return "none"
        request_source = self.normalize_request_source(
            str(task.get("request_source", "")),
            str(task.get("source", "")),
        )
        if request_source == "human":
            return "human_intent_confirmation"
        if str(task.get("risk_level", "")).strip().lower() == "high":
            return "high_risk_confirmation"
        return "manual_confirmation_required"

    def task_confirmation_snapshot(self, task: dict[str, Any]) -> dict[str, Any]:
        reason_code = self._task_confirmation_reason(task)
        need_human_confirm = bool(task.get("need_human_confirm"))
        human_confirmed = bool(task.get("human_confirmed"))
        needs_clarification = bool(task.get("needs_clarification"))
        state = "ready"
        if needs_clarification:
            state = "blocked_clarification"
        elif need_human_confirm and not human_confirmed:
            state = "waiting_human_confirm"
        return {
            "state": state,
            "reason_code": reason_code,
            "need_human_confirm": need_human_confirm,
            "human_confirmed": human_confirmed,
            "needs_clarification": needs_clarification,
            "task_id": str(task.get("task_id", "")).strip(),
            "confirm_command": (
                "python3 scripts/openclaw-ops/policy/policy_enforcer.py "
                + f"confirm-risk --task-id {str(task.get('task_id', '')).strip()} --confirmed true --actor human"
                if need_human_confirm and (not human_confirmed)
                else ""
            ),
        }

    def task_tracking_snapshot(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(task.get("task_id", "")).strip(),
            "status": str(task.get("status", "")).strip(),
            "pool": str(task.get("pool", "")).strip(),
            "assignee": str(task.get("assignee", "")).strip(),
            "request_source": self.normalize_request_source(
                str(task.get("request_source", "")),
                str(task.get("source", "")),
            ),
            "created_at": str(task.get("created_at", "")).strip(),
            "scheduled_at": str(task.get("scheduled_at", "")).strip(),
            "started_at": str(task.get("started_at", "")).strip(),
            "completed_at": str(task.get("completed_at", "")).strip(),
        }

    def task_timing_snapshot(self, task: dict[str, Any]) -> dict[str, Any]:
        created_at_text = str(task.get("created_at", "")).strip()
        started_at_text = str(task.get("started_at", "")).strip()
        completed_at_text = str(task.get("completed_at", "")).strip()

        def parse_optional_iso(text: str) -> datetime | None:
            if not text:
                return None
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                return None

        created_dt = parse_optional_iso(created_at_text)
        started_dt = parse_optional_iso(started_at_text)
        completed_dt = parse_optional_iso(completed_at_text)

        elapsed_ms: int | None = None
        execution_ms: int | None = None
        if created_dt and completed_dt:
            elapsed_ms = max(0, int((completed_dt - created_dt).total_seconds() * 1000))
        if started_dt and completed_dt:
            execution_ms = max(0, int((completed_dt - started_dt).total_seconds() * 1000))

        return {
            "created_at": created_at_text,
            "started_at": started_at_text,
            "completed_at": completed_at_text,
            "elapsed_ms": elapsed_ms,
            "elapsed_min": round((elapsed_ms / 60000.0), 2) if elapsed_ms is not None else None,
            "execution_ms": execution_ms,
            "execution_min": round((execution_ms / 60000.0), 2) if execution_ms is not None else None,
        }

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

    def parse_optional_json_arg(self, raw: str, field_name: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"{field_name} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyError(f"{field_name} must be a JSON object")
        return data

    def parse_text_list_arg(self, raw: str) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in text.split(","):
            value = item.strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(value)
        return out

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

        duration_match = re.search(r"(持续[^，。；;\s]{1,24}|[0-9]+(?:分钟|小时|天|day|hour|min))", raw, flags=re.IGNORECASE)
        if duration_match:
            duration = duration_match.group(1)

        impact_keywords = ["影响", "阻塞", "不可用", "失败", "报错", "错误", "超时", "404", "500", "延迟", "回退"]
        for kw in impact_keywords:
            if kw in raw:
                impact = f"contains:{kw}"
                break

        evidence_match = re.search(
            r"(evidence[:：]?\s*[^\s，。；;]+|证据路径[:：]?\s*[^\s，。；;]+|/home/[^\s，。；;]+|[A-Za-z]:\\[^\s，。；;]+|[\w./-]+\.(?:json|log|txt))",
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
            "current_state": raw,
            "expected_state": target_state,
            "operation_path": location,
            "reproduction_steps": raw,
            "scope": "task_description",
            "constraints": "",
            "acceptance_criteria": "",
            "full_background": raw,
            "owner": "",
            "change_id": "",
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
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": [],
            }

        if request_source != "ai":
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": [],
            }

        required_raw = cfg.get("ai_required_fields", [])
        if not isinstance(required_raw, list):
            raise PolicyError("context_policy.ai_required_fields must be a list")
        required_fields = [str(x).strip() for x in required_raw if str(x).strip()]

        recommended_raw = cfg.get("ai_recommended_fields", [])
        if not isinstance(recommended_raw, list):
            raise PolicyError("context_policy.ai_recommended_fields must be a list")
        recommended_fields = [str(x).strip() for x in recommended_raw if str(x).strip()]

        if not required_fields:
            return {
                "needs_clarification": False,
                "clarification_reason": "",
                "context_completeness": 100.0,
                "missing_fields": [],
                "missing_recommended_fields": [],
                "required_fields": [],
                "recommended_fields": recommended_fields,
            }

        missing_fields = [field for field in required_fields if not has_context_value(context_payload.get(field))]
        missing_recommended_fields = [field for field in recommended_fields if not has_context_value(context_payload.get(field))]
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
            "missing_recommended_fields": missing_recommended_fields,
            "required_fields": required_fields,
            "recommended_fields": recommended_fields,
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
        need_human = bool(task.get("need_human_confirm"))
        confirmed = bool(task.get("human_confirmed"))
        if (not need_human) or confirmed:
            return

        request_source = self.normalize_request_source(
            str(task.get("request_source", "")),
            str(task.get("source", "")),
        )
        risk_level = str(task.get("risk_level", "")).strip().lower()
        if request_source == "human":
            raise PolicyError("human-submitted task requires confirmation before execution")
        if risk_level == "high" and parse_bool(self.policy.get("high_risk_requires_human_confirm", True), True):
            raise PolicyError("high-risk task requires human confirmation")
        raise PolicyError("task requires human confirmation before execution")

    def assert_agent_stage_allowed(self, agent_id: str, stage: str) -> None:
        blocked_agents = self.policy.get("blocked_direct_code_agents", [])
        code_stages = self.policy.get("code_execution_stages", [])
        if not isinstance(blocked_agents, list) or not isinstance(code_stages, list):
            raise PolicyError("policy blocked_direct_code_agents/code_execution_stages must be lists")

        if agent_id in {str(x) for x in blocked_agents} and stage in {str(x) for x in code_stages}:
            raise PolicyError(f"agent {agent_id} is not allowed to execute code stage {stage}")

    def agent_write_scope(self) -> dict[str, list[str]]:
        raw = self.policy.get("agent_write_scope", {})
        if not isinstance(raw, dict):
            raise PolicyError("policy.agent_write_scope must be an object")
        out: dict[str, list[str]] = {}
        for agent_id, prefixes_raw in raw.items():
            aid = str(agent_id).strip()
            if not aid:
                continue
            prefixes: list[str] = []
            if isinstance(prefixes_raw, list):
                for item in prefixes_raw:
                    value = str(item).strip().replace("\\", "/")
                    if not value:
                        continue
                    prefixes.append(value)
            out[aid] = prefixes
        return out

    def assert_agent_write_scope(self, agent_id: str, changed_files: list[str]) -> dict[str, Any]:
        scopes = self.agent_write_scope()
        allowed_prefixes = scopes.get(str(agent_id).strip(), [])
        normalized_files = [str(x).strip().replace("\\", "/") for x in changed_files if str(x).strip()]
        normalized_files = [x for x in normalized_files if x]

        if not allowed_prefixes:
            return {
                "ok": True,
                "agent_id": agent_id,
                "scope_enabled": False,
                "allowed_prefixes": [],
                "checked_files": normalized_files,
                "violations": [],
            }

        violations: list[str] = []
        for rel in normalized_files:
            if rel.startswith(".workflow/"):
                continue
            if any(rel.startswith(prefix) for prefix in allowed_prefixes):
                continue
            violations.append(rel)

        if violations:
            raise PolicyError(
                f"write scope violation: agent={agent_id}, "
                f"allowed={allowed_prefixes}, violations={','.join(violations)}"
            )
        return {
            "ok": True,
            "agent_id": agent_id,
            "scope_enabled": True,
            "allowed_prefixes": allowed_prefixes,
            "checked_files": normalized_files,
            "violations": [],
        }

    def assert_transition_allowed(self, from_status: str, to_status: str) -> None:
        flow = self.status_flow()
        allowed = flow.get(from_status)
        if allowed is None:
            raise PolicyError(f"unknown from_status in policy flow: {from_status}")
        if to_status not in allowed:
            raise PolicyError(f"status transition blocked by policy: {from_status} -> {to_status}")

    def derive_task_status_from_agent_report(
        self,
        report_status: str,
        solved: bool,
        failure_count: int,
    ) -> tuple[str, str]:
        normalized_status = str(report_status or "").strip().lower()
        normalized_failure = max(0, int(failure_count or 0))

        if normalized_status == "escalated":
            return "escalated", "escalate_human"
        if normalized_status == "failed":
            if normalized_failure >= self.max_failure_before_escalate():
                return "escalated", "escalate_human"
            return "failed", "retry"
        if normalized_status == "partial":
            return "running", "retry"

        if solved and normalized_failure == 0:
            return "passed", "pass"
        return "running", "retry"

    def sync_task_status_from_agent_report(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        report_status: str,
        solved: bool,
        failure_count: int,
        actor: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current_status = str(task.get("status", "pending")).strip().lower() or "pending"
        current_action = str(task.get("action", "") or "").strip()
        target_status, target_action = self.derive_task_status_from_agent_report(
            report_status=report_status,
            solved=solved,
            failure_count=failure_count,
        )
        post_deploy_guard = self.evaluate_post_deploy_test_state(task_id)
        if bool(post_deploy_guard.get("required")):
            post_cfg = self.post_deploy_test_policy()
            missing_action = str(
                post_cfg.get("missing_post_test_action", "post_deploy_test_required")
            ).strip() or "post_deploy_test_required"
            failed_action = str(
                post_cfg.get("failed_post_test_action", "retry_fix_after_post_deploy_test")
            ).strip() or "retry_fix_after_post_deploy_test"
            guard_state = str(post_deploy_guard.get("state", "")).strip().lower()
            if guard_state in {"missing", "running"}:
                target_status = "running"
                target_action = missing_action
            elif guard_state == "failed":
                if max(0, int(failure_count or 0)) >= self.max_failure_before_escalate():
                    target_status = "escalated"
                    target_action = "escalate_human"
                else:
                    target_status = "failed"
                    target_action = failed_action

        sync_info: dict[str, Any] = {
            "task_status_before": current_status,
            "task_status_target": target_status,
            "task_status_after": current_status,
            "task_action_before": current_action,
            "task_action_target": target_action,
            "task_action_after": current_action,
            "task_status_updated": False,
            "task_action_updated": False,
            "sync_skipped_reason": "",
            "post_deploy_guard": post_deploy_guard,
        }

        # Keep terminal statuses stable unless report agrees with current status.
        if current_status in {"passed", "cancelled"} and current_status != target_status:
            sync_info["sync_skipped_reason"] = f"terminal_status_locked:{current_status}"
            return task, sync_info

        updated_task = task
        if current_status != target_status:
            updated_task = self.db.transition_status(
                task_id=task_id,
                new_status=target_status,
                actor=actor,
                stage="agent_report",
                details={
                    "report_status": report_status,
                    "solved": bool(solved),
                    "failure_count": int(failure_count or 0),
                },
            )
            sync_info["task_status_updated"] = True

        latest_action = str(updated_task.get("action", "") or "").strip()
        if target_action and latest_action != target_action:
            updated_task = self.db.update_task(
                task_id=task_id,
                actor=actor,
                fields={"action": target_action},
            )
            sync_info["task_action_updated"] = True

        sync_info["task_status_after"] = str(updated_task.get("status", "") or "").strip().lower()
        sync_info["task_action_after"] = str(updated_task.get("action", "") or "").strip()
        return updated_task, sync_info

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
        task_type = str(args.task_type or "workflow").strip()
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
        if not str(context_payload.get("current_state", "")).strip():
            context_payload["current_state"] = str(context_payload.get("problem", "")).strip()
        if not str(context_payload.get("expected_state", "")).strip():
            context_payload["expected_state"] = str(context_payload.get("target_state", "")).strip()
        if not str(context_payload.get("operation_path", "")).strip():
            context_payload["operation_path"] = str(context_payload.get("location", "")).strip()
        if not str(context_payload.get("reproduction_steps", "")).strip():
            context_payload["reproduction_steps"] = str(context_payload.get("problem", "")).strip()
        if not str(context_payload.get("scope", "")).strip():
            context_payload["scope"] = str(args.requirement).strip()
        if not str(context_payload.get("constraints", "")).strip():
            context_payload["constraints"] = ""
        if not str(context_payload.get("acceptance_criteria", "")).strip():
            context_payload["acceptance_criteria"] = str(args.acceptance).strip()
        if not str(context_payload.get("full_background", "")).strip():
            context_payload["full_background"] = str(context_payload.get("problem", "")).strip()
        if not str(context_payload.get("acceptance", "")).strip():
            context_payload["acceptance"] = str(args.acceptance).strip()
        if not str(context_payload.get("evidence", "")).strip():
            context_payload["evidence"] = str(args.observable_outputs).strip()
        runtime_binding_seen_at = ""
        if task_type == "ops_runtime_cron":
            runtime_ref = str(args.source or "").strip() or str(args.task_id or "").strip()
            runtime_binding_seen_at = str(args.scheduled_at or "").strip() or now_iso()
            if not str(context_payload.get("location", "")).strip():
                context_payload["location"] = runtime_ref
            if not str(context_payload.get("first_seen_at", "")).strip():
                context_payload["first_seen_at"] = runtime_binding_seen_at
            if not str(context_payload.get("impact", "")).strip():
                context_payload["impact"] = "Runtime observability and status tracking would be lost if this binding task is missing."
            if not str(context_payload.get("operation_path", "")).strip():
                context_payload["operation_path"] = runtime_ref
            if not str(context_payload.get("constraints", "")).strip():
                context_payload["constraints"] = "Internal runtime binding only; do not mutate vendor private runtime files."

        owner = str(getattr(args, "owner", "") or context_payload.get("owner", "")).strip()
        change_id = str(getattr(args, "change_id", "") or context_payload.get("change_id", "")).strip()
        context_payload["owner"] = owner
        context_payload["change_id"] = change_id
        context_eval = self.evaluate_context_gate(request_source, context_payload)
        context_payload["context_contract"] = {
            "required_fields": list(context_eval.get("required_fields", [])),
            "recommended_fields": list(context_eval.get("recommended_fields", [])),
        }
        force_needs_clarification = parse_bool(getattr(args, "force_needs_clarification", ""), False)
        needs_clarification = force_needs_clarification or bool(context_eval["needs_clarification"])
        clarification_reason = str(getattr(args, "clarification_reason", "") or "").strip()
        if not clarification_reason:
            clarification_reason = str(context_eval.get("clarification_reason", "")).strip()

        default_need_confirm = self.default_need_human_confirm(
            request_source=request_source,
            risk_level=risk_level,
        )
        need_human_confirm = parse_bool(args.need_human_confirm, default_need_confirm)
        scheduled_at = str(args.scheduled_at or "").strip()
        if pool == "todo" and self.todo_require_scheduled_at() and not scheduled_at:
            scheduled_at = now_iso()

        assignee = str(args.assignee or "").strip() or self.dispatcher_agent()
        if needs_clarification:
            assignee = self.clarification_assignee()
            pool = "todo"
            if priority == "low":
                priority = "medium"
            if task_type == "workflow":
                task_type = "clarification_required"

        initial_status = "pending"
        initial_action = ""
        completed_at = ""
        if task_type == "ops_runtime_cron":
            # Runtime binding tasks are observability anchors, not executable backlog items.
            initial_status = "passed"
            initial_action = "runtime_binding"
            completed_at = runtime_binding_seen_at or now_iso()

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
            "owner": owner,
            "change_id": change_id,
            "status": initial_status,
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "need_human_confirm": need_human_confirm,
            "human_confirmed": parse_bool(args.human_confirmed, False),
            "context_completeness": float(context_eval.get("context_completeness", 0.0) or 0.0),
            "context_fields_missing": context_eval.get("missing_fields", []),
            "context_fields_recommended_missing": context_eval.get("missing_recommended_fields", []),
            "context_payload": context_payload,
            "requirement": args.requirement,
            "result_output": args.result_output,
            "acceptance": args.acceptance,
            "observable_outputs": args.observable_outputs,
            "acceptance_thresholds": args.acceptance_thresholds,
            "required_capabilities": getattr(args, "required_capabilities", ""),
            "required_skills": getattr(args, "required_skills", ""),
            "allowed_agents": getattr(args, "allowed_agents", ""),
            "action": initial_action,
            "scheduled_at": scheduled_at,
            "completed_at": completed_at,
        }
        inferred_constraints = infer_task_capability_constraints(assignee)
        if not str(payload["required_capabilities"] or "").strip():
            payload["required_capabilities"] = inferred_constraints["required_capabilities"]
        if not str(payload["required_skills"] or "").strip():
            payload["required_skills"] = inferred_constraints["required_skills"]
        if not str(payload["allowed_agents"] or "").strip():
            payload["allowed_agents"] = inferred_constraints["allowed_agents"]

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
                "missing_recommended_fields": created.get("context_fields_recommended_missing", []),
                "owner": created.get("owner", ""),
                "change_id": created.get("change_id", ""),
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
        created["confirmation"] = self.task_confirmation_snapshot(created)
        created["tracking"] = self.task_tracking_snapshot(created)
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
        planner_points_info: dict[str, Any] = {"enabled": False}
        if self.points_enabled():
            task_priority = str(assigned.get("priority", "medium") or "medium").strip().lower()
            if task_priority not in {"low", "medium", "high"}:
                task_priority = "medium"
            task_risk = str(assigned.get("risk_level", "low") or "low").strip().lower()
            if task_risk not in {"low", "high"}:
                task_risk = "low"
            dispatch_points = self._planner_dispatch_points(task_priority, task_risk)
            planner_record = self.db.upsert_agent_points(
                task_id=args.task_id,
                actor_type="planner",
                actor_id=str(args.actor),
                planner_id=str(args.actor),
                status="dispatched",
                solved=True,
                points=dispatch_points,
                base_points=dispatch_points,
                quality_factor=1.0,
                timeliness_factor=1.0,
                details={
                    "scoring_mode": "dispatch_count",
                    "task_priority": task_priority,
                    "task_risk_level": task_risk,
                    "assignee": assignee,
                    "fallback_used": bool(fallback_used),
                },
                event_actor=str(args.actor),
            )
            planner_points_info = {
                "enabled": True,
                "scoring_mode": "dispatch_count",
                "dispatch_points": dispatch_points,
                "planner_record_id": planner_record.get("id"),
            }
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
        assigned["planner_points"] = planner_points_info
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
                context_fields_recommended_missing=list(context_eval.get("missing_recommended_fields", [])),
            )

        return self.db.update_clarification(
            task_id=args.task_id,
            actor=args.actor,
            needs_clarification=False,
            clarification_reason="",
            context_payload=merged_context,
            context_completeness=float(context_eval.get("context_completeness", 100.0) or 100.0),
            context_fields_missing=[],
            context_fields_recommended_missing=list(context_eval.get("missing_recommended_fields", [])),
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

    def log_module(self, args: argparse.Namespace) -> dict[str, Any]:
        details = self.parse_optional_json_arg(getattr(args, "details_json", ""), "details-json")
        task_id = str(getattr(args, "task_id", "") or "").strip()
        return self.db.record_module_log(
            task_id=task_id,
            module_name=str(args.module_name),
            phase=str(args.phase or "runtime"),
            level=str(args.level or "info"),
            status=str(args.status or "running"),
            message=str(args.message),
            duration_ms=int(args.duration_ms or 0),
            details=details,
            actor=str(args.actor or ""),
        )

    def log_communication(self, args: argparse.Namespace) -> dict[str, Any]:
        details = self.parse_optional_json_arg(getattr(args, "details_json", ""), "details-json")
        task_id = str(getattr(args, "task_id", "") or "").strip()
        return self.db.record_module_communication(
            task_id=task_id,
            from_module=str(args.from_module),
            to_module=str(args.to_module),
            protocol=str(args.protocol or "internal"),
            message_type=str(args.message_type or "handoff"),
            status=str(args.status or "sent"),
            latency_ms=int(args.latency_ms or 0),
            correlation_id=str(args.correlation_id or ""),
            payload_ref=str(args.payload_ref or ""),
            details=details,
            actor=str(args.actor or ""),
        )

    def report_agent_result(self, args: argparse.Namespace) -> dict[str, Any]:
        task_id = str(args.task_id or "").strip()
        if not task_id:
            raise PolicyError("task-id is required")
        task_before = self.db.get_task(task_id)

        status = str(args.status or "").strip().lower() or "passed"
        if status not in {"passed", "failed", "partial", "escalated"}:
            raise PolicyError("status must be passed|failed|partial|escalated")

        resolved_issues = self.parse_text_list_arg(str(args.resolved_issues or ""))
        resolution_steps = self.parse_text_list_arg(str(args.resolution_steps or ""))
        failed_items = self.parse_text_list_arg(str(args.failed_items or ""))
        details = self.parse_optional_json_arg(getattr(args, "details_json", ""), "details-json")

        solved_default = status in {"passed", "partial"}
        solved = parse_bool(getattr(args, "solved", ""), solved_default)
        failure_count = max(0, int(args.failure_count or 0))

        manual_notify_raw = str(getattr(args, "notify_chat", "") or "").strip().lower()
        if manual_notify_raw in {"true", "false", "1", "0", "yes", "no"}:
            notify_chat = parse_bool(manual_notify_raw, False)
        else:
            notify_chat = (status in {"failed", "escalated"}) or (not solved) or failure_count > 0

        quality_score_raw = str(getattr(args, "quality_score", "") or "").strip()
        quality_score: float | None = None
        if quality_score_raw:
            quality_score = float(quality_score_raw)
            quality_score = max(0.0, min(100.0, quality_score))

        input_tokens = max(0, int(args.input_tokens or 0))
        output_tokens = max(0, int(args.output_tokens or 0))
        total_tokens = input_tokens + output_tokens
        duration_ms = max(0, int(args.duration_ms or 0))
        cost_estimate = float(args.cost_estimate or 0.0)
        model_id = str(args.model or "").strip()
        if model_id:
            self.assert_model_allowed(model_id)

        report = self.db.upsert_agent_task_report(
            task_id=task_id,
            agent_id=str(args.agent_id),
            planner_id=str(args.planner_id or "coordinator"),
            status=status,
            solved=solved,
            resolved_issues=resolved_issues,
            resolution_summary=str(args.resolution_summary or ""),
            resolution_steps=resolution_steps,
            failed_items=failed_items,
            failure_count=failure_count,
            duration_ms=duration_ms,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost_estimate,
            quality_score=quality_score,
            quality_grade=str(args.quality_grade or ""),
            notify_chat=notify_chat,
            details=details,
            actor=str(args.actor or ""),
        )

        task_actor = str(args.actor or args.agent_id or "agent").strip()
        task_after, status_sync = self.sync_task_status_from_agent_report(
            task=task_before,
            task_id=task_id,
            report_status=status,
            solved=solved,
            failure_count=failure_count,
            actor=task_actor,
        )

        planner_payload = {
            "task_id": task_id,
            "task_status": str(task_after.get("status", "")),
            "task_status_before": status_sync.get("task_status_before", ""),
            "task_status_target": status_sync.get("task_status_target", ""),
            "task_status_after": status_sync.get("task_status_after", ""),
            "task_action": str(task_after.get("action", "")),
            "task_action_before": status_sync.get("task_action_before", ""),
            "task_action_target": status_sync.get("task_action_target", ""),
            "task_action_after": status_sync.get("task_action_after", ""),
            "task_status_updated": bool(status_sync.get("task_status_updated")),
            "task_action_updated": bool(status_sync.get("task_action_updated")),
            "task_sync_skipped_reason": str(status_sync.get("sync_skipped_reason", "")),
            "post_deploy_guard": status_sync.get("post_deploy_guard", {}),
            "task_reason": str(task_after.get("reason", "")),
            "agent_id": str(args.agent_id),
            "planner_id": str(args.planner_id or "coordinator"),
            "report_status": status,
            "solved": solved,
            "resolved_issues": resolved_issues,
            "resolution_summary": str(args.resolution_summary or ""),
            "resolution_steps": resolution_steps,
            "failed_items": failed_items,
            "failure_count": failure_count,
            "duration_ms": duration_ms,
            "model_id": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "total_tokens_m": round(total_tokens / 1_000_000.0, 6),
            "cost_estimate": round(cost_estimate, 6),
            "quality_score": quality_score,
            "quality_grade": str(args.quality_grade or ""),
            "notify_chat": notify_chat,
            "report_id": report.get("id"),
            "report_ts": report.get("ts"),
        }
        planner_payload["task_token_usage"] = self.db.task_token_summary(task_id)
        planner_payload["task_timing"] = self.task_timing_snapshot(task_after)
        planner_payload["confirmation"] = self.task_confirmation_snapshot(task_after)
        planner_payload["tracking"] = self.task_tracking_snapshot(task_after)

        points_result: dict[str, Any] = {}
        if self.points_enabled():
            policy = self.points_policy()
            quality_weight = float(policy.get("quality_weight", 0.75) or 0.75)
            timeliness_weight = float(policy.get("timeliness_weight", 0.25) or 0.25)
            total_weight = quality_weight + timeliness_weight
            if total_weight <= 0:
                quality_weight, timeliness_weight, total_weight = 0.75, 0.25, 1.0
            quality_weight /= total_weight
            timeliness_weight /= total_weight
            minimum_quality = float(policy.get("minimum_quality_for_positive", 70.0) or 70.0)

            task_priority = str(task_after.get("priority", "medium") or "medium").strip().lower()
            if task_priority not in {"low", "medium", "high"}:
                task_priority = "medium"
            task_risk = str(task_after.get("risk_level", "low") or "low").strip().lower()
            if task_risk not in {"low", "high"}:
                task_risk = "low"

            base_points = self._base_points(task_priority, task_risk)
            quality_factor = self._quality_factor(quality_score, solved, status, minimum_quality)
            timeliness_factor = self._timeliness_factor(duration_ms, task_priority)
            performance_factor = quality_weight * quality_factor + timeliness_weight * timeliness_factor
            status_multiplier = self._status_multiplier(status, solved)
            agent_points = round(base_points * performance_factor * status_multiplier, 6)

            agent_points_record = self.db.upsert_agent_points(
                task_id=task_id,
                actor_type="agent",
                actor_id=str(args.agent_id),
                planner_id=str(args.planner_id or "coordinator"),
                status=status,
                solved=solved,
                points=agent_points,
                base_points=base_points,
                quality_factor=quality_factor,
                timeliness_factor=timeliness_factor,
                details={
                    "task_priority": task_priority,
                    "task_risk_level": task_risk,
                    "quality_weight": round(quality_weight, 6),
                    "timeliness_weight": round(timeliness_weight, 6),
                    "performance_factor": round(performance_factor, 6),
                    "status_multiplier": round(status_multiplier, 6),
                    "quality_score": quality_score,
                    "duration_ms": duration_ms,
                },
                event_actor=task_actor,
            )
            points_result = {
                "enabled": True,
                "scoring_mode": {
                    "agent": "completion_based",
                    "planner": "dispatch_count_based",
                },
                "base_points": round(base_points, 6),
                "quality_factor": round(quality_factor, 6),
                "timeliness_factor": round(timeliness_factor, 6),
                "performance_factor": round(performance_factor, 6),
                "status_multiplier": round(status_multiplier, 6),
                "agent_points": agent_points,
                "planner_points": None,
                "agent_record_id": agent_points_record.get("id"),
                "planner_record_id": None,
            }
        else:
            points_result = {"enabled": False}

        planner_payload["points"] = points_result

        chat_output = "NO_REPLY"
        if notify_chat:
            lines = [
                f"# Agent异常回报 {task_id}",
                f"- planner: {planner_payload['planner_id']}",
                f"- agent: {planner_payload['agent_id']}",
                f"- status: {planner_payload['report_status']}",
                f"- solved: {str(planner_payload['solved']).lower()}",
                f"- failure_count: {planner_payload['failure_count']}",
                f"- duration_ms: {planner_payload['duration_ms']}",
                f"- model: {planner_payload['model_id'] or '-'}",
                f"- tokens: in={planner_payload['input_tokens']}, out={planner_payload['output_tokens']}, "
                + f"total={planner_payload['total_tokens']} ({planner_payload['total_tokens_m']}M)",
                f"- cost_estimate: {planner_payload['cost_estimate']}",
                f"- quality_score: {planner_payload['quality_score'] if planner_payload['quality_score'] is not None else 'n/a'}",
                f"- quality_grade: {planner_payload['quality_grade'] or 'n/a'}",
                f"- resolution_summary: {planner_payload['resolution_summary'] or '-'}",
            ]
            if planner_payload["resolved_issues"]:
                lines.append(f"- resolved_issues: {', '.join(planner_payload['resolved_issues'])}")
            if planner_payload["failed_items"]:
                lines.append(f"- failed_items: {', '.join(planner_payload['failed_items'])}")
            chat_output = "\n".join(lines)

        return {
            "report": report,
            "planner_payload": planner_payload,
            "task_status_sync": status_sync,
            "points": points_result,
            "notify_chat": notify_chat,
            "chat_output": chat_output,
        }

    def reconcile_task_statuses(self, args: argparse.Namespace) -> dict[str, Any]:
        limit = max(1, int(getattr(args, "limit", 2000) or 2000))
        dry_run = bool(getattr(args, "dry_run", False))
        actor = str(getattr(args, "actor", "") or "coordinator").strip() or "coordinator"

        unresolved = self.db.unresolved_tasks()
        tasks = unresolved[:limit]
        scanned = len(tasks)

        stats: dict[str, int] = {
            "scanned": scanned,
            "updated": 0,
            "status_updated": 0,
            "action_updated": 0,
            "skipped_no_report": 0,
            "skipped_terminal_locked": 0,
            "no_change": 0,
        }
        details: list[dict[str, Any]] = []

        for task in tasks:
            task_id = str(task.get("task_id", "")).strip()
            if not task_id:
                continue

            reports = self.db.list_agent_task_reports(task_id=task_id, limit=1)
            if not reports:
                stats["skipped_no_report"] += 1
                continue

            latest_report = reports[0]
            report_status = str(latest_report.get("status", "")).strip().lower() or "passed"
            solved = bool(latest_report.get("solved"))
            failure_count = int(latest_report.get("failure_count") or 0)
            target_status, target_action = self.derive_task_status_from_agent_report(
                report_status=report_status,
                solved=solved,
                failure_count=failure_count,
            )
            current_status = str(task.get("status", "")).strip().lower()
            current_action = str(task.get("action", "") or "").strip()

            if current_status in {"passed", "cancelled"} and current_status != target_status:
                stats["skipped_terminal_locked"] += 1
                details.append(
                    {
                        "task_id": task_id,
                        "state": "skipped_terminal_locked",
                        "current_status": current_status,
                        "target_status": target_status,
                        "report_status": report_status,
                    }
                )
                continue

            need_status_update = current_status != target_status
            need_action_update = bool(target_action) and current_action != target_action
            if not need_status_update and not need_action_update:
                stats["no_change"] += 1
                continue

            if dry_run:
                if need_status_update:
                    stats["status_updated"] += 1
                if need_action_update:
                    stats["action_updated"] += 1
                stats["updated"] += 1
                details.append(
                    {
                        "task_id": task_id,
                        "state": "would_update",
                        "current_status": current_status,
                        "target_status": target_status,
                        "current_action": current_action,
                        "target_action": target_action,
                        "report_status": report_status,
                        "failure_count": failure_count,
                    }
                )
                continue

            _task_after, sync_info = self.sync_task_status_from_agent_report(
                task=task,
                task_id=task_id,
                report_status=report_status,
                solved=solved,
                failure_count=failure_count,
                actor=actor,
            )
            changed_status = bool(sync_info.get("task_status_updated"))
            changed_action = bool(sync_info.get("task_action_updated"))
            if changed_status or changed_action:
                if changed_status:
                    stats["status_updated"] += 1
                if changed_action:
                    stats["action_updated"] += 1
                stats["updated"] += 1
                details.append(
                    {
                        "task_id": task_id,
                        "state": "updated",
                        "current_status": sync_info.get("task_status_before"),
                        "target_status": sync_info.get("task_status_target"),
                        "current_action": sync_info.get("task_action_before"),
                        "target_action": sync_info.get("task_action_target"),
                        "report_status": report_status,
                        "failure_count": failure_count,
                    }
                )
            else:
                stats["no_change"] += 1

        return {
            "dry_run": dry_run,
            "limit": limit,
            "scanned_total_unresolved": len(unresolved),
            "stats": stats,
            "updated_tasks": details[:200],
        }

    def planner_summary(self, args: argparse.Namespace) -> dict[str, Any]:
        planner_id = str(args.planner_id or "coordinator").strip()
        if not planner_id:
            raise PolicyError("planner-id cannot be empty")
        since = str(getattr(args, "since", "") or "").strip()
        limit = max(1, int(getattr(args, "limit", 100) or 100))
        summary = self.db.planner_summary(planner_id=planner_id, since=since, limit=limit)
        summary["task_capability_coverage"] = self.db.task_capability_coverage(since=since)
        if self.points_enabled():
            policy = self.points_policy()
            lookback_days = max(1, int(policy.get("leaderboard_lookback_days", 14) or 14))
            points_since = since
            if not points_since:
                points_since = (
                    datetime.now(tz=UTC).replace(microsecond=0) - timedelta(days=lookback_days)
                ).isoformat()
            summary["points_agent"] = self.db.points_summary(
                actor_type="agent",
                since=points_since,
                limit=500,
            )
            summary["points_planner"] = self.db.points_summary(
                actor_type="planner",
                since=points_since,
                limit=200,
            )
            summary["points_since"] = points_since
            agent_points_map = summary.get("points_agent", {}).get("actor_points", {})
            by_agent_rows = summary.get("by_agent", [])
            if isinstance(by_agent_rows, list):
                for item in by_agent_rows:
                    if not isinstance(item, dict):
                        continue
                    agent_id = str(item.get("agent_id", "")).strip()
                    item["score_points"] = round(float(agent_points_map.get(agent_id, 0.0) or 0.0), 6)
        return summary

    def task_capability_coverage(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.db.task_capability_coverage(
            since=str(getattr(args, "since", "") or "").strip(),
            task_type=str(getattr(args, "task_type", "") or "").strip(),
            assignee=str(getattr(args, "assignee", "") or "").strip(),
            status=str(getattr(args, "status", "") or "").strip(),
            pool=str(getattr(args, "pool", "") or "").strip(),
        )

    def daily_summary(self, args: argparse.Namespace) -> dict[str, Any]:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(tz=UTC).date()
        summary = self.db.daily_summary(target_date)

        if args.output:
            out = Path(args.output).expanduser()
            atomic_write_text(
                out,
                format_daily_summary_markdown(summary),
                file_mode=0o644,
                dir_mode=0o755,
            )

        return summary

    def task_report(self, args: argparse.Namespace) -> dict[str, Any]:
        report = self.db.task_report(task_id=args.task_id, event_limit=int(args.event_limit))
        if args.output:
            out = Path(args.output).expanduser()
            write_json_atomic(
                out,
                report,
                ensure_ascii=False,
                indent=2,
                file_mode=0o644,
                dir_mode=0o755,
            )
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
                    pattern = rf"^\s*{re.escape(prefix_text)}(?:[\s:\-]+)?(?P<body>.*)$"
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
        owner = str(context_payload.get("owner", "")).strip()
        change_id = str(context_payload.get("change_id", "")).strip()
        needs_clarification = bool(context_eval.get("needs_clarification"))
        clarification_reason = str(context_eval.get("clarification_reason", "")).strip()
        code_task_hits: list[str] = []
        code_dispatch_forced = False
        code_dispatch_target = ""
        code_dispatch_reason = ""
        if needs_clarification:
            entry_agent = "project-agent"
            assignee = self.clarification_assignee()
            bypass_dispatcher = True
            pool = "todo"
            if priority == "low":
                priority = "medium"
        else:
            project_dispatch = self.project_dispatch_policy()
            if (
                assignee == "project-agent"
                and parse_bool(project_dispatch.get("enabled", True), True)
                and parse_bool(project_dispatch.get("force_dispatch_code_tasks", True), True)
            ):
                code_task_hits = self._keyword_hits(
                    effective_norm,
                    project_dispatch.get("code_task_keywords", []),
                )
                if code_task_hits:
                    frontend_hits = self._keyword_hits(
                        effective_norm,
                        project_dispatch.get("frontend_keywords", []),
                    )
                    backend_hits = self._keyword_hits(
                        effective_norm,
                        project_dispatch.get("backend_keywords", []),
                    )
                    tester_hits = self._keyword_hits(
                        effective_norm,
                        project_dispatch.get("tester_keywords", []),
                    )
                    target = str(
                        project_dispatch.get("default_code_assignee", "backend-dev")
                    ).strip() or "backend-dev"
                    if backend_hits:
                        target = "backend-dev"
                        code_dispatch_reason = "code_task_dispatch:backend"
                    elif frontend_hits and not backend_hits:
                        target = "frontend-dev"
                        code_dispatch_reason = "code_task_dispatch:frontend"
                    elif tester_hits:
                        target = "tester"
                        code_dispatch_reason = "code_task_dispatch:tester"
                    elif frontend_hits:
                        target = "frontend-dev"
                        code_dispatch_reason = "code_task_dispatch:frontend"
                    else:
                        code_dispatch_reason = "code_task_dispatch:default"

                    assignee = target
                    code_dispatch_target = target
                    code_dispatch_forced = True
                    bypass_dispatcher = False
                    pool = "jobs" if priority == "high" else "todo"
                    if priority == "low":
                        priority = "medium"

        need_human_confirm = self.default_need_human_confirm(
            request_source=request_source,
            risk_level=risk_level,
        )
        confirmation_reason = "none"
        if needs_clarification:
            confirmation_reason = "clarification_required"
        elif need_human_confirm:
            confirmation_reason = "human_intent_confirmation" if request_source == "human" else "high_risk_confirmation"
        task_id_suggested = self.suggest_task_id(
            "human-task" if request_source == "human" else "ai-task"
        )

        return {
            "task_id_suggested": task_id_suggested,
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
            "owner": owner,
            "change_id": change_id,
            "need_human_confirm": need_human_confirm,
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "execution_strategy": {
                "mode": (
                    "clarify_then_confirm"
                    if needs_clarification
                    else (
                        "confirm_before_execute"
                        if need_human_confirm
                        else "direct_low_risk_execution"
                    )
                ),
                "confirmation_required": bool(need_human_confirm),
                "confirmation_reason": confirmation_reason,
                "clarification_required": bool(needs_clarification),
                "confirm_command_after_create": (
                    "python3 scripts/openclaw-ops/policy/policy_enforcer.py "
                    + "confirm-risk --task-id <task_id> --confirmed true --actor human"
                    if need_human_confirm
                    else ""
                ),
            },
            "code_dispatch_forced": code_dispatch_forced,
            "code_dispatch_target": code_dispatch_target,
            "code_dispatch_reason": code_dispatch_reason,
            "context_completeness": float(context_eval.get("context_completeness", 100.0) or 100.0),
            "context_fields_missing": list(context_eval.get("missing_fields", [])),
            "context_fields_recommended_missing": list(context_eval.get("missing_recommended_fields", [])),
            "context_payload": context_payload,
            "hits": {
                "high_risk": high_risk_hits,
                "low_risk": low_risk_hits,
                "priority_high": high_priority_hits,
                "priority_low": low_priority_hits,
                "assignee_hit": assignee_hit,
                "project_requirement": project_requirement,
                "project_hits": project_hits,
                "code_task_hits": code_task_hits,
                "direct_route_prefix": str(direct_route.get("alias_prefix", "")) if direct_route else "",
            },
        }

    def next_todo(self, args: argparse.Namespace) -> dict[str, Any]:
        limit_raw = int(args.limit or 0)
        limit = self.todo_queue_max_dispatch() if limit_raw <= 0 else max(1, limit_raw)
        now_value = now_iso()
        scan_limit = max(limit * 8, 80)
        rows = self.db.conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE pool = 'todo'
              AND status = 'pending'
            ORDER BY
                CASE
                    WHEN scheduled_at IS NULL OR TRIM(scheduled_at) = '' OR scheduled_at <= ? THEN 0
                    ELSE 1
                END ASC,
                COALESCE(NULLIF(TRIM(scheduled_at), ''), created_at) ASC,
                created_at ASC
            LIMIT ?
            """,
            (now_value, scan_limit),
        ).fetchall()
        tasks: list[dict[str, Any]] = []
        ready_count = 0
        for row in rows:
            item = dict(row)
            item["need_human_confirm"] = bool(item.get("need_human_confirm"))
            item["human_confirmed"] = bool(item.get("human_confirmed"))
            # no-time or due-time tasks should be dispatched first
            scheduled_at = str(item.get("scheduled_at", "") or "").strip()
            item["is_ready"] = (not scheduled_at) or scheduled_at <= now_value
            if item["is_ready"]:
                ready_count += 1
            assignee = str(item.get("assignee") or "").strip()
            item["assignee"] = assignee or None
            item["dispatch_reason"] = "fifo"
            item["guarantee_hit"] = False
            tasks.append(item)

        guarantee_cfg = self.todo_agent_guarantee_policy()
        guarantee_enabled = bool(
            self.points_enabled() and parse_bool(guarantee_cfg.get("enabled", True), True)
        )
        min_tasks_per_agent = max(1, int(guarantee_cfg.get("min_tasks_per_agent", 1) or 1))
        low_score_threshold = float(guarantee_cfg.get("low_score_threshold", 12.0) or 12.0)
        lookback_days = max(1, int(guarantee_cfg.get("lookback_days", 7) or 7))
        points_since = (
            datetime.now(tz=UTC).replace(microsecond=0) - timedelta(days=lookback_days)
        ).isoformat()
        points_map: dict[str, float] = {}
        low_score_agents: set[str] = set()
        if guarantee_enabled:
            points_summary = self.db.points_summary(
                actor_type="agent",
                since=points_since,
                limit=2000,
            )
            points_map = {
                str(k): float(v)
                for k, v in (points_summary.get("actor_points", {}) or {}).items()
            }
            for task in tasks:
                assignee = str(task.get("assignee") or "").strip()
                if not assignee:
                    continue
                score = float(points_map.get(assignee, 0.0))
                if score <= low_score_threshold:
                    low_score_agents.add(assignee)

        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        guarantee_count: dict[str, int] = {}
        guarantee_hits = 0

        if guarantee_enabled and low_score_agents:
            for task in tasks:
                if len(selected) >= limit:
                    break
                if not bool(task.get("is_ready")):
                    continue
                task_id = str(task.get("task_id", "")).strip()
                assignee = str(task.get("assignee") or "").strip()
                if not task_id or not assignee:
                    continue
                if assignee not in low_score_agents:
                    continue
                if guarantee_count.get(assignee, 0) >= min_tasks_per_agent:
                    continue
                if task_id in selected_ids:
                    continue
                task["dispatch_reason"] = "guarantee_low_score_agent"
                task["guarantee_hit"] = True
                selected.append(task)
                selected_ids.add(task_id)
                guarantee_count[assignee] = guarantee_count.get(assignee, 0) + 1
                guarantee_hits += 1

        for task in tasks:
            if len(selected) >= limit:
                break
            task_id = str(task.get("task_id", "")).strip()
            if not task_id or task_id in selected_ids:
                continue
            selected.append(task)
            selected_ids.add(task_id)

        tasks = selected[:limit]
        selected_ready_count = sum(1 for item in tasks if bool(item.get("is_ready")))
        return {
            "policy_limit": self.todo_queue_max_dispatch(),
            "requested_limit": limit_raw,
            "effective_limit": limit,
            "now": now_value,
            "ready_count": selected_ready_count,
            "future_count": max(0, len(tasks) - selected_ready_count),
            "scanned_ready_count": ready_count,
            "guarantee_policy": {
                "enabled": guarantee_enabled,
                "min_tasks_per_agent": min_tasks_per_agent,
                "low_score_threshold": low_score_threshold,
                "lookback_days": lookback_days,
                "points_since": points_since if guarantee_enabled else "",
                "guarantee_hits": guarantee_hits,
                "low_score_agents": sorted(low_score_agents),
            },
            "tasks": tasks,
        }

    def assert_write_scope(self, args: argparse.Namespace) -> dict[str, Any]:
        files: list[str] = []
        changed_file_args = getattr(args, "changed_file", [])
        if isinstance(changed_file_args, list):
            files.extend(str(x) for x in changed_file_args if str(x).strip())

        files_file = str(getattr(args, "changed_files_file", "") or "").strip()
        if files_file:
            path = Path(files_file).expanduser()
            if not path.exists():
                raise PolicyError(f"changed-files-file not found: {path}")
            lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
            files.extend(line for line in lines if line)

        # preserve input order while removing duplicates
        dedup: list[str] = []
        seen: set[str] = set()
        for item in files:
            norm = str(item).strip().replace("\\", "/")
            if not norm or norm in seen:
                continue
            seen.add(norm)
            dedup.append(norm)

        return self.assert_agent_write_scope(agent_id=str(args.agent_id).strip(), changed_files=dedup)

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

        write_json_atomic(
            self.paths.routing_file,
            routing,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
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
        required_ctx = ctx.get("ai_required_fields", [])
        recommended_ctx = ctx.get("ai_recommended_fields", [])
        add_check(
            "context_policy_required_fields_configured",
            isinstance(required_ctx, list) and bool([x for x in required_ctx if str(x).strip()]),
            f"required_fields_count={len(required_ctx) if isinstance(required_ctx, list) else 0}",
        )
        add_check(
            "context_policy_recommended_fields_parseable",
            isinstance(recommended_ctx, list),
            f"recommended_fields_count={len(recommended_ctx) if isinstance(recommended_ctx, list) else 0}",
        )
        write_scope_raw = self.policy.get("agent_write_scope", {})
        write_scope_ok = isinstance(write_scope_raw, dict)
        scope_agents = sorted(write_scope_raw.keys()) if isinstance(write_scope_raw, dict) else []
        add_check(
            "agent_write_scope_optional",
            write_scope_ok,
            f"enabled={bool(scope_agents)} agents_with_scope={scope_agents}",
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
    parser = argparse.ArgumentParser(
        description="Policy-Enforcer CLI",
        epilog=GOVERNANCE_BRIDGE_EPILOG,
    )
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
    create.add_argument("--owner", default="")
    create.add_argument("--change-id", default="")
    create.add_argument("--entry-agent", default="")
    create.add_argument("--need-human-confirm", default="")
    create.add_argument("--human-confirmed", default="false")
    create.add_argument("--requirement", required=True)
    create.add_argument("--result-output", required=True)
    create.add_argument("--acceptance", required=True)
    create.add_argument("--observable-outputs", required=True)
    create.add_argument("--acceptance-thresholds", required=True)
    create.add_argument("--required-capabilities", default="")
    create.add_argument("--required-skills", default="")
    create.add_argument("--allowed-agents", default="")
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

    log_module = sub.add_parser("log-module", help="record standardized module runtime log")
    log_module.add_argument("--task-id", default="")
    log_module.add_argument("--module-name", required=True)
    log_module.add_argument("--phase", default="runtime")
    log_module.add_argument("--level", default="info")
    log_module.add_argument("--status", default="running")
    log_module.add_argument("--message", required=True)
    log_module.add_argument("--duration-ms", default="0")
    log_module.add_argument("--details-json", default="")
    log_module.add_argument("--actor", default="")

    log_communication = sub.add_parser("log-communication", help="record module-to-module communication log")
    log_communication.add_argument("--task-id", default="")
    log_communication.add_argument("--from-module", required=True)
    log_communication.add_argument("--to-module", required=True)
    log_communication.add_argument("--protocol", default="internal")
    log_communication.add_argument("--message-type", default="handoff")
    log_communication.add_argument("--status", default="sent")
    log_communication.add_argument("--latency-ms", default="0")
    log_communication.add_argument("--correlation-id", default="")
    log_communication.add_argument("--payload-ref", default="")
    log_communication.add_argument("--details-json", default="")
    log_communication.add_argument("--actor", default="")

    report_agent = sub.add_parser("report-agent-result", help="agent result report to planner with exception-only chat")
    report_agent.add_argument("--task-id", required=True)
    report_agent.add_argument("--agent-id", required=True)
    report_agent.add_argument("--planner-id", default="coordinator")
    report_agent.add_argument("--status", default="passed")
    report_agent.add_argument("--solved", default="")
    report_agent.add_argument("--resolved-issues", default="")
    report_agent.add_argument("--resolution-summary", default="")
    report_agent.add_argument("--resolution-steps", default="")
    report_agent.add_argument("--failed-items", default="")
    report_agent.add_argument("--failure-count", default="0")
    report_agent.add_argument("--duration-ms", default="0")
    report_agent.add_argument("--model", default="")
    report_agent.add_argument("--input-tokens", default="0")
    report_agent.add_argument("--output-tokens", default="0")
    report_agent.add_argument("--cost-estimate", default="0")
    report_agent.add_argument("--quality-score", default="")
    report_agent.add_argument("--quality-grade", default="")
    report_agent.add_argument("--notify-chat", default="")
    report_agent.add_argument("--details-json", default="")
    report_agent.add_argument("--actor", default="")

    reconcile_status = sub.add_parser(
        "reconcile-task-status",
        help="backfill tasks.status/tasks.action from latest agent reports",
    )
    reconcile_status.add_argument("--limit", default="2000")
    reconcile_status.add_argument("--dry-run", action="store_true")
    reconcile_status.add_argument("--actor", default="coordinator")

    planner_summary = sub.add_parser("planner-summary", help="planner task completion statistics")
    planner_summary.add_argument("--planner-id", default="coordinator")
    planner_summary.add_argument("--since", default="")
    planner_summary.add_argument("--limit", default="100")

    capability_coverage = sub.add_parser("task-capability-coverage", help="summarize task schema upgrade coverage")
    capability_coverage.add_argument("--since", default="")
    capability_coverage.add_argument("--task-type", default="")
    capability_coverage.add_argument("--assignee", default="")
    capability_coverage.add_argument("--status", default="")
    capability_coverage.add_argument("--pool", default="")

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

    write_scope = sub.add_parser("assert-write-scope", help="validate changed files against agent write scope")
    write_scope.add_argument("--agent-id", required=True)
    write_scope.add_argument("--changed-file", action="append", default=[])
    write_scope.add_argument("--changed-files-file", default="")
    _ = write_scope

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
        if force or not file_path.exists():
            write_json_atomic(
                file_path,
                defaults,
                ensure_ascii=False,
                indent=2,
                file_mode=0o640,
                dir_mode=0o750,
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
            elif args.command == "log-module":
                emit_json({"ok": True, "log": enforcer.log_module(args)})
            elif args.command == "log-communication":
                emit_json({"ok": True, "log": enforcer.log_communication(args)})
            elif args.command == "report-agent-result":
                emit_json({"ok": True, "result": enforcer.report_agent_result(args)})
            elif args.command == "reconcile-task-status":
                emit_json({"ok": True, "result": enforcer.reconcile_task_statuses(args)})
            elif args.command == "planner-summary":
                emit_json({"ok": True, "summary": enforcer.planner_summary(args)})
            elif args.command == "task-capability-coverage":
                emit_json({"ok": True, "summary": enforcer.task_capability_coverage(args)})
            elif args.command == "daily-summary":
                emit_json({"ok": True, "summary": enforcer.daily_summary(args)})
            elif args.command == "task-report":
                emit_json({"ok": True, "report": enforcer.task_report(args)})
            elif args.command == "route-task":
                emit_json({"ok": True, "route": enforcer.route_task(args)})
            elif args.command == "next-todo":
                emit_json({"ok": True, "result": enforcer.next_todo(args)})
            elif args.command == "assert-write-scope":
                emit_json({"ok": True, "result": enforcer.assert_write_scope(args)})
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
    except (PolicyError, TaskCenterError, FileWriteError, ValueError) as exc:
        emit_json({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Policy-Enforcer: fail-close policy checks for OpenClaw workflows."""

from __future__ import annotations

import json
import sys
from datetime import timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
POLICY_DIR = Path(__file__).resolve().parent
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))
REPO_ROOT = Path(__file__).resolve().parents[5]
SHARED_DIR = REPO_ROOT / "scripts" / "openclaw-ops" / "shared"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from utf8_runtime import configure_process_utf8_stdio
from task_center import TaskCenter, TASK_STATUSES

configure_process_utf8_stdio()

UTC = timezone.utc

# ── Extracted modules ──────────────────────────────────────────────────
from policy_defaults import DEFAULT_POLICY, DEFAULT_ROUTING_RULES  # noqa: E402
from policy_utils import (  # noqa: E402
    PolicyError,
    RuntimePaths,
    parse_bool,
    merge_missing_keys,
    read_json,
)
from policy_scoring import ScoringMixin  # noqa: E402
from policy_workflow import WorkflowMixin  # noqa: E402
from policy_context import ContextMixin  # noqa: E402
from policy_task import TaskLifecycleMixin  # noqa: E402
from policy_observe import ObservabilityMixin  # noqa: E402


class PolicyEnforcer(
    ScoringMixin,
    WorkflowMixin,
    ContextMixin,
    TaskLifecycleMixin,
    ObservabilityMixin,
):
    """Fail-close policy enforcement for OpenClaw workflows.

    Composed from 5 Mixin modules:
      - ScoringMixin:        agent points, SLA, quality factors
      - WorkflowMixin:       workflow profile loading, selection, stage resolution
      - ContextMixin:        context extraction, gate validation, requirement packages
      - TaskLifecycleMixin:  task CRUD, status machine, agent result reporting
      - ObservabilityMixin:  routing, assertions, validation, reporting
    """

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self.db = TaskCenter(paths.db)
        self.db.init_schema()
        self._score_policy_cache: dict[str, dict[str, Any]] = {}
        self.policy = merge_missing_keys(
            read_json(paths.policy_file, DEFAULT_POLICY, write_if_missing=False),
            DEFAULT_POLICY,
        )
        self.routing = merge_missing_keys(
            read_json(paths.routing_file, DEFAULT_ROUTING_RULES, write_if_missing=False),
            DEFAULT_ROUTING_RULES,
        )
        self.capability_registry = self.load_capability_registry()
        self.workflow_profile_registry = self.load_workflow_profile_registry()


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


    def project_dispatch_policy(self) -> dict[str, Any]:
        raw = self.policy.get("project_dispatch_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        defaults = DEFAULT_POLICY.get("project_dispatch_policy", {})
        if not isinstance(defaults, dict):
            defaults = {}
        return merge_missing_keys(raw, defaults)


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



from policy_cli import cmd_init  # noqa: E402


# ── CLI entry point (extracted to policy_cli.py) ──────────────────────
if __name__ == "__main__":
    from policy_cli import main  # noqa: E402
    sys.exit(main())

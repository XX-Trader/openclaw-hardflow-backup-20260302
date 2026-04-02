"""Policy Enforcer — ScoringMixin."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

from policy_defaults import DEFAULT_POLICY
from policy_utils import parse_bool, merge_missing_keys

class ScoringMixin:
    """Mixin providing Scoring methods for PolicyEnforcer."""

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


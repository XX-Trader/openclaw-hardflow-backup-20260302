"""Policy Enforcer — TaskLifecycleMixin."""

from __future__ import annotations

import sys
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parent
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

import argparse
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

from policy_defaults import DEFAULT_POLICY
from policy_utils import PolicyError, parse_bool, merge_missing_keys, now_iso, emit_json
from io_write_gateway import atomic_write_text, write_json_atomic
from task_center import TaskCenterError, TASK_STATUSES, estimate_cost, load_pricing, format_daily_summary_markdown
from task_capability_binding import (
    infer_task_capability_constraints,
    resolve_task_capability_binding,
    validate_task_capability_constraints,
)
from policy_route_selection import (
    AWAIT_ROUTE_SELECTION_ACTION,
    PIPELINE_ROUTE_CHOICES,
    VALID_ROUTE_CHOICES,
    build_route_selection,
    route_choice_action,
)

class TaskLifecycleMixin:
    """Mixin providing TaskLifecycle methods for PolicyEnforcer."""

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


    def _normalize_trace_id(self, value: Any, *, task_id: str = "") -> str:
        text = str(value or "").strip()
        if text:
            return text
        normalized_task_id = str(task_id or "").strip()
        if normalized_task_id:
            return f"trace-{normalized_task_id}"
        return self.suggest_task_id("trace")


    def _normalize_attempt_id(self, value: Any, *, retry_count: Any = 0) -> str:
        text = str(value or "").strip()
        if text:
            return text
        try:
            normalized_retry_count = max(0, int(retry_count or 0))
        except (TypeError, ValueError):
            normalized_retry_count = 0
        return f"attempt-{normalized_retry_count + 1:03d}"


    def _build_execution_envelope(
        self,
        *,
        base: dict[str, Any] | None = None,
        trace_id: str,
        attempt_id: str,
        task_id: str,
        task_type: str,
        request_source: str,
        reason: str,
        requirement: str,
        acceptance: str,
        observable_outputs: str,
        assignee: str,
        workflow_profile_id: str,
        workflow_channel: str,
        stage_id: str,
        selection_reason: str,
        required_capabilities: list[str],
        required_skills: list[str],
        required_runtime: list[str],
        tool_requirements: list[str],
        allowed_agents: list[str],
        capability_binding_snapshot: dict[str, Any] | None = None,
        stage_output_contract: dict[str, Any] | None = None,
        stage_verification_contract: dict[str, Any] | None = None,
        stage_context_gate: dict[str, Any] | None = None,
        context_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        envelope = dict(base or {})
        workflow_payload = envelope.get("workflow", {})
        if not isinstance(workflow_payload, dict):
            workflow_payload = {}
        workflow_payload.update(
            {
                "profile_id": str(workflow_profile_id or "").strip(),
                "channel": str(workflow_channel or "").strip().lower(),
                "stage_id": str(stage_id or "").strip(),
                "selection_reason": str(selection_reason or "").strip(),
            }
        )

        task_payload = envelope.get("task", {})
        if not isinstance(task_payload, dict):
            task_payload = {}
        task_payload.update(
            {
                "task_type": str(task_type or "").strip(),
                "request_source": str(request_source or "").strip(),
                "reason": str(reason or "").strip(),
                "requirement": str(requirement or "").strip(),
                "acceptance": str(acceptance or "").strip(),
                "observable_outputs": str(observable_outputs or "").strip(),
            }
        )

        routing_payload = envelope.get("routing", {})
        if not isinstance(routing_payload, dict):
            routing_payload = {}
        routing_payload.update(
            {
                "assignee": str(assignee or "").strip(),
                "allowed_agents": list(allowed_agents or []),
            }
        )

        capability_payload = envelope.get("capability_binding", {})
        if not isinstance(capability_payload, dict):
            capability_payload = {}
        if isinstance(capability_binding_snapshot, dict):
            capability_payload.update(capability_binding_snapshot)
        capability_payload.update(
            {
                "required_capabilities": list(required_capabilities or []),
                "required_skills": list(required_skills or []),
                "required_runtime": list(required_runtime or []),
                "tool_requirements": list(tool_requirements or []),
            }
        )

        contracts_payload = envelope.get("contracts", {})
        if not isinstance(contracts_payload, dict):
            contracts_payload = {}
        contracts_payload.update(
            {
                "output_contract": dict(stage_output_contract or {}),
                "verification_contract": dict(stage_verification_contract or {}),
                "stage_context_gate": dict(stage_context_gate or {}),
                "context_contract": dict(context_contract or {}),
            }
        )

        envelope.update(
            {
                "schema_version": "2026-03-23",
                "trace_id": str(trace_id or "").strip(),
                "attempt_id": str(attempt_id or "").strip(),
                "task_id": str(task_id or "").strip(),
                "workflow": workflow_payload,
                "task": task_payload,
                "routing": routing_payload,
                "capability_binding": capability_payload,
                "contracts": contracts_payload,
            }
        )
        return envelope


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
        task_id = str(task.get("task_id", "")).strip()
        context_payload = task.get("context_payload")
        if not isinstance(context_payload, dict):
            context_payload = {}
        route_selection = context_payload.get("route_selection")
        if not isinstance(route_selection, dict):
            route_selection = {}
        route_selection_required = bool(route_selection.get("required")) and not str(
            route_selection.get("selected_route") or ""
        ).strip()
        if route_selection_required:
            confirm_command = (
                "python3 skills/library/control-plane-ops/scripts/policy/human_inbox.py "
                + f"confirm --task-id {task_id} --route-choice recommended --actor human"
            )
        elif need_human_confirm and (not human_confirmed):
            confirm_command = (
                "python3 skills/library/control-plane-ops/scripts/policy/policy_enforcer.py "
                + f"confirm-risk --task-id {task_id} --confirmed true --actor human"
            )
        else:
            confirm_command = ""
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
            "task_id": task_id,
            "confirm_command": confirm_command,
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


    def clarification_assignee(self) -> str:
        cfg = self.context_policy()
        value = str(cfg.get("clarification_assignee", "project-agent")).strip()
        return value or "project-agent"


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
        workflow_selection_inputs = self.parse_workflow_selection_inputs(
            getattr(args, "workflow_selection_inputs_json", ""),
            getattr(args, "workflow_selection_inputs_file", ""),
        )
        task_id = str(args.task_id or "").strip()
        trace_id = self._normalize_trace_id(
            getattr(args, "trace_id", "")
            or context_payload.get("trace_id", "")
            or workflow_selection_inputs.get("trace_id", ""),
            task_id=task_id,
        )
        attempt_id = self._normalize_attempt_id(
            getattr(args, "attempt_id", "")
            or context_payload.get("attempt_id", "")
            or workflow_selection_inputs.get("attempt_id", ""),
            retry_count=getattr(args, "retry_count", 0),
        )
        if not context_payload:
            context_payload = self.extract_context_from_text(args.reason)
        context_payload["trace_id"] = trace_id
        context_payload["attempt_id"] = attempt_id
        workflow_selection_inputs["trace_id"] = trace_id
        workflow_selection_inputs["attempt_id"] = attempt_id
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
        workflow_description = "\n".join(
            part
            for part in [
                str(args.reason or "").strip(),
                str(args.requirement or "").strip(),
                str(args.acceptance or "").strip(),
                str(args.observable_outputs or "").strip(),
            ]
            if part
        )
        project_requirement = False
        if request_source == "human":
            project_requirement, _ = self.is_human_project_requirement(workflow_description)
        requirement_package_gate = self.evaluate_requirement_package_gate(
            request_source=request_source,
            task_type=task_type,
            context_payload=context_payload,
            project_requirement=project_requirement,
        )
        context_payload["requirement_package_contract"] = {
            "required": bool(requirement_package_gate.get("required")),
            "required_fields": list(requirement_package_gate.get("required_fields", [])),
            "recommended_fields": list(requirement_package_gate.get("recommended_fields", [])),
            "missing_fields": list(requirement_package_gate.get("missing_fields", [])),
            "missing_recommended_fields": list(requirement_package_gate.get("missing_recommended_fields", [])),
            "triggered_by": str(requirement_package_gate.get("triggered_by", "")).strip(),
        }
        force_needs_clarification = parse_bool(getattr(args, "force_needs_clarification", ""), False)
        needs_clarification = force_needs_clarification or bool(context_eval["needs_clarification"])
        if bool(requirement_package_gate.get("needs_clarification")):
            needs_clarification = True
        clarification_reason = str(getattr(args, "clarification_reason", "") or "").strip()
        if not clarification_reason:
            clarification_reason = str(context_eval.get("clarification_reason", "")).strip()
        clarification_reason = "; ".join(
            self._merge_text_lists(
                clarification_reason,
                requirement_package_gate.get("clarification_reason", ""),
            )
        ).strip()

        default_need_confirm = self.default_need_human_confirm(
            request_source=request_source,
            risk_level=risk_level,
        )
        need_human_confirm = parse_bool(args.need_human_confirm, default_need_confirm)
        human_confirmed = parse_bool(args.human_confirmed, False)
        scheduled_at = str(args.scheduled_at or "").strip()
        if pool == "todo" and self.todo_require_scheduled_at() and not scheduled_at:
            scheduled_at = now_iso()

        explicit_assignee = str(args.assignee or "").strip()
        assignee = explicit_assignee or self.dispatcher_agent()
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
        workflow_selection = self.select_workflow_for_request(
            description=workflow_description,
            task_type=task_type,
            request_source=request_source,
            source=args.source,
            assignee=assignee,
            needs_clarification=needs_clarification,
            context_payload=context_payload,
            workflow_profile_id=getattr(args, "workflow_profile_id", ""),
            workflow_channel=getattr(args, "workflow_channel", ""),
            selection_reason=getattr(args, "workflow_selection_reason", ""),
            selection_inputs=workflow_selection_inputs,
        )
        explicit_stage_id = str(getattr(args, "stage_id", "") or "").strip()
        workflow_stage_entry: dict[str, Any] = {}
        if workflow_selection["workflow_profile_id"]:
            workflow_stage_entry = self.resolve_workflow_stage_entry(
                profile_id=workflow_selection["workflow_profile_id"],
                channel=workflow_selection["workflow_channel"],
                task_type=task_type,
                stage_id=explicit_stage_id,
            )
        elif explicit_stage_id:
            raise PolicyError("stage_id requires a resolved workflow profile")

        stage_context_gate = self.evaluate_stage_context_gate(context_payload, workflow_stage_entry)
        if stage_context_gate["needs_clarification"] and not needs_clarification:
            needs_clarification = True
            assignee = self.clarification_assignee()
            pool = "todo"
            if priority == "low":
                priority = "medium"
            if task_type == "workflow":
                task_type = "clarification_required"
            stage_context_gate["rerouted_task_type"] = task_type
            clarification_reason = "; ".join(
                self._merge_text_lists(
                    clarification_reason,
                    stage_context_gate.get("clarification_reason", ""),
                )
            ).strip()
            workflow_selection = self.select_workflow_for_request(
                description=workflow_description,
                task_type=task_type,
                request_source=request_source,
                source=args.source,
                assignee=assignee,
                needs_clarification=needs_clarification,
                context_payload=context_payload,
                workflow_profile_id=getattr(args, "workflow_profile_id", ""),
                workflow_channel=getattr(args, "workflow_channel", ""),
                selection_reason=getattr(args, "workflow_selection_reason", ""),
                selection_inputs=workflow_selection_inputs,
            )
            workflow_stage_entry = {}
            if workflow_selection["workflow_profile_id"]:
                workflow_stage_entry = self.resolve_workflow_stage_entry(
                    profile_id=workflow_selection["workflow_profile_id"],
                    channel=workflow_selection["workflow_channel"],
                    task_type=task_type,
                    stage_id="",
                )
        selection_inputs_payload = self.apply_stage_selection_inputs(
            dict(workflow_selection["selection_inputs"]),
            workflow_stage_entry,
            stage_context_gate,
        )
        selection_inputs_payload["trace_id"] = trace_id
        selection_inputs_payload["attempt_id"] = attempt_id
        selection_inputs_payload["requirement_package_gate"] = {
            "required": bool(requirement_package_gate.get("required")),
            "package_ready": bool(requirement_package_gate.get("package_ready", True)),
            "triggered_by": str(requirement_package_gate.get("triggered_by", "")).strip(),
            "required_fields": list(requirement_package_gate.get("required_fields", [])),
            "recommended_fields": list(requirement_package_gate.get("recommended_fields", [])),
            "missing_fields": list(requirement_package_gate.get("missing_fields", [])),
            "missing_recommended_fields": list(requirement_package_gate.get("missing_recommended_fields", [])),
            "clarification_reason": str(requirement_package_gate.get("clarification_reason", "")).strip(),
        }
        merged_context_missing_fields = self._merge_text_lists(
            context_eval.get("missing_fields", []),
            stage_context_gate.get("missing_fields", []),
            requirement_package_gate.get("missing_fields", []),
        )
        context_payload["context_contract"] = {
            "required_fields": list(context_eval.get("required_fields", [])),
            "recommended_fields": list(context_eval.get("recommended_fields", [])),
            "stage_required_fields": list(stage_context_gate.get("required_fields", [])),
            "stage_missing_fields": list(stage_context_gate.get("missing_fields", [])),
            "stage_gate_evaluated_stage_id": str(stage_context_gate.get("evaluated_stage_id", "")).strip(),
        }

        route_selection = context_payload.get("route_selection")
        if not isinstance(route_selection, dict):
            route_selection = {}
        selected_route = str(route_selection.get("selected_route") or "").strip().lower()
        verified_route_selected = bool(human_confirmed) and selected_route in VALID_ROUTE_CHOICES
        route_selection_applies = initial_status == "pending" and task_type != "ops_runtime_cron"
        if route_selection_applies:
            recommended_route_selection = build_route_selection(
                risk_level=risk_level,
                needs_clarification=needs_clarification,
                workflow_profile_id=workflow_selection["workflow_profile_id"],
                task_type=task_type,
                require_manual=True,
            )
            recommended_route_selection.update(route_selection)
            context_payload["route_selection"] = recommended_route_selection
            need_human_confirm = True
            if verified_route_selected:
                initial_action = route_choice_action(selected_route)
                if selected_route == "requirement_discussion" and not explicit_assignee:
                    assignee = self.clarification_assignee()
                elif selected_route in PIPELINE_ROUTE_CHOICES and not explicit_assignee:
                    assignee = self.dispatcher_agent()
            else:
                human_confirmed = False
                initial_action = AWAIT_ROUTE_SELECTION_ACTION
                assignee = "human-inbox"

        explicit_required_capabilities = self.parse_text_list_arg(getattr(args, "required_capabilities", ""))
        explicit_required_skills = self.parse_text_list_arg(getattr(args, "required_skills", ""))
        explicit_allowed_agents = self.parse_text_list_arg(getattr(args, "allowed_agents", ""))
        stage_required_capabilities = list(workflow_stage_entry.get("required_capabilities", []))
        stage_required_skills = list(workflow_stage_entry.get("required_skills", []))
        requested_required_capabilities = self._merge_text_lists(
            explicit_required_capabilities,
            stage_required_capabilities,
        )
        requested_required_skills = self._merge_text_lists(
            explicit_required_skills,
            stage_required_skills,
        )
        capability_binding = resolve_task_capability_binding(
            explicit_assignee if explicit_assignee or needs_clarification else "",
            required_capabilities=requested_required_capabilities,
            required_skills=requested_required_skills,
            allowed_agents=explicit_allowed_agents,
            registry=self.capability_registry,
        )
        if not explicit_assignee and not needs_clarification and capability_binding["assignee"]:
            assignee = capability_binding["assignee"]
        selection_inputs_payload["capability_binding"] = {
            "resolved_assignee": capability_binding["assignee"],
            "resolution_reason": capability_binding["resolution_reason"],
            "requested_required_capabilities": requested_required_capabilities,
            "requested_required_skills": requested_required_skills,
            "required_capabilities": capability_binding["required_capabilities"],
            "required_skills": capability_binding["required_skills"],
            "allowed_agents": capability_binding["allowed_agents"],
            "required_runtime": capability_binding["required_runtime"],
            "tool_requirements": capability_binding["tool_requirements"],
            "capability_default_agents": capability_binding["capability_default_agents"],
            "skill_matched_agents": capability_binding["skill_matched_agents"],
            "capability_declarations": capability_binding["capability_declarations"],
            "capability_contracts": capability_binding["capability_contracts"],
            "resolved_agent_profile": capability_binding["resolved_agent_profile"],
        }

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
            "human_confirmed": human_confirmed,
            "context_completeness": float(context_eval.get("context_completeness", 0.0) or 0.0),
            "context_fields_missing": merged_context_missing_fields,
            "context_fields_recommended_missing": context_eval.get("missing_recommended_fields", []),
            "context_payload": context_payload,
            "requirement": args.requirement,
            "result_output": args.result_output,
            "acceptance": args.acceptance,
            "observable_outputs": args.observable_outputs,
            "acceptance_thresholds": args.acceptance_thresholds,
            "stage_id": str(workflow_stage_entry.get("stage_id", "") or explicit_stage_id).strip(),
            "stage_score_gate": str(workflow_stage_entry.get("score_gate", "")).strip().lower(),
            "stage_min_evidence_count": int(workflow_stage_entry.get("min_evidence_count", 0) or 0),
            "stage_output_contract": dict(workflow_stage_entry.get("output_contract", {})),
            "stage_verification_contract": dict(workflow_stage_entry.get("verification_contract", {})),
            "required_capabilities": requested_required_capabilities,
            "required_skills": requested_required_skills,
            "allowed_agents": explicit_allowed_agents,
            "workflow_profile_id": workflow_selection["workflow_profile_id"],
            "workflow_channel": workflow_selection["workflow_channel"],
            "selection_reason": workflow_selection["selection_reason"],
            "selection_inputs": selection_inputs_payload,
            "action": initial_action,
            "scheduled_at": scheduled_at,
            "completed_at": completed_at,
        }
        inferred_constraints = infer_task_capability_constraints(assignee, registry=self.capability_registry)
        payload["required_capabilities"] = self._merge_text_lists(
            capability_binding["required_capabilities"],
            inferred_constraints["required_capabilities"],
        )
        payload["required_skills"] = self._merge_text_lists(
            capability_binding["required_skills"],
            inferred_constraints["required_skills"],
        )
        payload["allowed_agents"] = self._merge_text_lists(
            explicit_allowed_agents or capability_binding["allowed_agents"],
            inferred_constraints["allowed_agents"],
        )
        try:
            normalized_constraints = validate_task_capability_constraints(
                payload["required_capabilities"],
                payload["required_skills"],
                payload["allowed_agents"],
                registry=self.capability_registry,
            )
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc
        payload["required_capabilities"] = normalized_constraints["required_capabilities"]
        payload["required_skills"] = normalized_constraints["required_skills"]
        payload["allowed_agents"] = normalized_constraints["allowed_agents"]
        selection_inputs_payload["execution_envelope"] = self._build_execution_envelope(
            base=selection_inputs_payload.get("execution_envelope", {})
            if isinstance(selection_inputs_payload.get("execution_envelope", {}), dict)
            else {},
            trace_id=trace_id,
            attempt_id=attempt_id,
            task_id=task_id,
            task_type=task_type,
            request_source=request_source,
            reason=str(args.reason or "").strip(),
            requirement=str(args.requirement or "").strip(),
            acceptance=str(args.acceptance or "").strip(),
            observable_outputs=str(args.observable_outputs or "").strip(),
            assignee=assignee,
            workflow_profile_id=payload["workflow_profile_id"],
            workflow_channel=payload["workflow_channel"],
            stage_id=payload["stage_id"],
            selection_reason=payload["selection_reason"],
            required_capabilities=payload["required_capabilities"],
            required_skills=payload["required_skills"],
            required_runtime=capability_binding["required_runtime"],
            tool_requirements=capability_binding["tool_requirements"],
            allowed_agents=payload["allowed_agents"],
            capability_binding_snapshot=selection_inputs_payload["capability_binding"],
            stage_output_contract=payload["stage_output_contract"],
            stage_verification_contract=payload["stage_verification_contract"],
            stage_context_gate=selection_inputs_payload.get("stage_context_gate", {}),
            context_contract=context_payload.get("context_contract", {}),
        )
        payload["selection_inputs"] = selection_inputs_payload
        payload["trace_id"] = trace_id
        payload["attempt_id"] = attempt_id

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
                "workflow_profile_id": created.get("workflow_profile_id", ""),
                "workflow_channel": created.get("workflow_channel", ""),
                "selection_reason": created.get("selection_reason", ""),
                "trace_id": created.get("trace_id", ""),
                "attempt_id": created.get("attempt_id", ""),
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
        task = self.db.get_task(args.task_id, display_safe=False)
        context_payload = task.get("context_payload")
        if not isinstance(context_payload, dict):
            context_payload = {}
        route_selection = context_payload.get("route_selection")
        if not isinstance(route_selection, dict):
            route_selection = {}
        if (
            parse_bool(args.confirmed, True)
            and bool(route_selection.get("required"))
            and not str(route_selection.get("selected_route") or "").strip()
        ):
            raise PolicyError(
                "task requires route selection; use human_inbox.py confirm "
                f"--task-id {args.task_id} --route-choice recommended"
            )
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
        extra_details = self.parse_optional_json_arg(getattr(args, "details_json", ""), "details-json")
        stage_details = {"reason": reason}
        if extra_details:
            stage_details.update(extra_details)

        if exit_code == 0:
            stage_run: dict[str, Any] | None = None
            try:
                stage_run = self.db.finish_stage_run(
                    task_id=args.task_id,
                    stage=args.stage,
                    status="passed",
                    exit_code=exit_code,
                    output_ref=output_ref,
                    details=stage_details,
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
                details=stage_details,
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
        requested_critical_pass = parse_bool(args.critical_pass, True)
        control_plane_gate = self.evaluate_completion_control_plane_gate(args.task_id)
        critical_pass = requested_critical_pass and (not bool(control_plane_gate["hard_blocked"]))

        raw_score = result_score * 0.70 + stability_score * 0.30
        normalized_score = (raw_score / 100.0) * 100.0

        if bool(control_plane_gate["hard_blocked"]):
            if bool(control_plane_gate["should_escalate"]):
                action = "escalate_human"
                target_status = "escalated"
            elif int(task["failure_count"]) >= self.max_failure_before_escalate():
                action = "escalate_human"
                target_status = "escalated"
            else:
                action = "retry"
                target_status = "failed"
        elif critical_pass and raw_score >= self.pass_line_raw():
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
                "critical_pass_requested": requested_critical_pass,
                "critical_pass": critical_pass,
                "action": action,
                "control_plane_gate": control_plane_gate,
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
                "critical_pass_requested": requested_critical_pass,
                "critical_pass": critical_pass,
                "action": action,
                "control_plane_gate": control_plane_gate,
            },
            allowed_from={from_status},
        )
        return updated


    def evaluate_completion_control_plane_gate(self, task_id: str) -> dict[str, Any]:
        """Derive completion-time hard gates from unified outputs and incidents."""
        task_outputs = self.db.list_task_outputs(task_id, limit=20, display_safe=False)
        task_incidents = self.db.list_task_incidents(task_id, limit=20, display_safe=False)

        latest_output_payload: dict[str, Any] = {}
        for item in reversed(task_outputs):
            if str(item.get("output_type", "")).strip() != "agent_report":
                continue
            payload = item.get("payload", {})
            if isinstance(payload, dict):
                latest_output_payload = payload
                break

        human_gate = latest_output_payload.get("human_gate", {}) if isinstance(latest_output_payload, dict) else {}
        if not isinstance(human_gate, dict):
            human_gate = {}

        open_incidents = [
            item
            for item in task_incidents
            if str(item.get("status", "")).strip().lower() not in {"resolved", "suppressed"}
        ]
        critical_open_incidents = [
            item for item in open_incidents if str(item.get("severity", "")).strip().lower() == "critical"
        ]
        waiting_human_confirm = bool(human_gate.get("need_human_confirm", False)) and (not bool(human_gate.get("human_confirmed", False)))
        needs_clarification = bool(human_gate.get("needs_clarification", False))
        requires_human_assistance = bool(human_gate.get("requires_human_assistance", False))
        hard_blocked = requires_human_assistance or bool(open_incidents)
        should_escalate = bool(critical_open_incidents) or waiting_human_confirm or needs_clarification
        return {
            "hard_blocked": hard_blocked,
            "requires_human_assistance": requires_human_assistance,
            "need_human_confirm": bool(human_gate.get("need_human_confirm", False)),
            "human_confirmed": bool(human_gate.get("human_confirmed", False)),
            "needs_clarification": needs_clarification,
            "waiting_human_confirm": waiting_human_confirm,
            "open_incident_count": len(open_incidents),
            "critical_open_incident_count": len(critical_open_incidents),
            "open_incident_types": [
                str(item.get("incident_type", "")).strip()
                for item in open_incidents
                if str(item.get("incident_type", "")).strip()
            ],
            "should_escalate": should_escalate,
        }


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


    def _normalize_detail_text_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            out: list[str] = []
            seen: set[str] = set()
            for item in value:
                text = str(item or "").strip()
                if not text:
                    continue
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                out.append(text)
            return out
        return self.parse_text_list_arg(str(value or ""))


    def apply_stage_contract_gate(
        self,
        *,
        report_status: str,
        solved: bool,
        failure_count: int,
        failed_items: list[str],
        quality_score: float | None,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        stage_contract = details.get("stage_contract", {})
        if not isinstance(stage_contract, dict):
            return {
                "report_status": report_status,
                "solved": solved,
                "failure_count": failure_count,
                "failed_items": failed_items,
                "quality_score": quality_score,
                "details": details,
            }
        if bool(stage_contract.get("contract_passed", True)):
            return {
                "report_status": report_status,
                "solved": solved,
                "failure_count": failure_count,
                "failed_items": failed_items,
                "quality_score": quality_score,
                "details": details,
            }

        merged_failed_items = list(failed_items)
        merged_failed_items.extend(
            f"stage_contract_missing_deliverable:{item}"
            for item in self._normalize_detail_text_list(stage_contract.get("missing_deliverables", []))
        )
        merged_failed_items.extend(
            f"stage_contract_failed_check:{item}"
            for item in self._normalize_detail_text_list(stage_contract.get("failed_checks", []))
        )
        if "stage_contract_failed" not in {item.lower() for item in merged_failed_items}:
            merged_failed_items.append("stage_contract_failed")

        merged_details = dict(details)
        merged_details["stage_contract_gate"] = {
            "enforced": True,
            "normalized_report_status": "partial" if str(report_status or "").strip().lower() not in {"failed", "escalated"} else str(report_status or "").strip().lower(),
            "reason": "stage_contract_failed",
        }
        normalized_status = str(report_status or "").strip().lower()
        if normalized_status not in {"failed", "escalated"}:
            normalized_status = "partial"
        adjusted_quality = min(float(quality_score), 69.0) if quality_score is not None else quality_score
        return {
            "report_status": normalized_status,
            "solved": False,
            "failure_count": max(1, int(failure_count or 0)),
            "failed_items": merged_failed_items,
            "quality_score": adjusted_quality,
            "details": merged_details,
        }


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
        manual_notify_set = manual_notify_raw in {"true", "false", "1", "0", "yes", "no"}
        notify_chat = parse_bool(manual_notify_raw, False) if manual_notify_set else False

        quality_score_raw = str(getattr(args, "quality_score", "") or "").strip()
        quality_score: float | None = None
        if quality_score_raw:
            quality_score = float(quality_score_raw)
            quality_score = max(0.0, min(100.0, quality_score))

        stage_gate = self.apply_stage_contract_gate(
            report_status=status,
            solved=solved,
            failure_count=failure_count,
            failed_items=failed_items,
            quality_score=quality_score,
            details=details,
        )
        status = str(stage_gate.get("report_status", status)).strip().lower() or status
        solved = bool(stage_gate.get("solved", solved))
        failure_count = max(0, int(stage_gate.get("failure_count", failure_count) or 0))
        failed_items = list(stage_gate.get("failed_items", failed_items))
        quality_score = stage_gate.get("quality_score", quality_score)
        details = stage_gate.get("details", details)
        if not manual_notify_set:
            notify_chat = (status in {"failed", "escalated"}) or (not solved) or failure_count > 0

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

        standard_output = self.build_standard_output_packet(
            task_before=task_before,
            task_after=task_after,
            planner_payload=planner_payload,
            status_sync=status_sync,
            chat_output=chat_output,
            notify_chat=notify_chat,
            details=details,
        )
        output_record = self.db.record_task_output(
            task_id=task_id,
            output_type="agent_report",
            audience="human",
            channel=str(standard_output.get("delivery", {}).get("channel", "")).strip(),
            status=str(standard_output.get("delivery", {}).get("status", "")).strip() or "prepared",
            summary=str(standard_output.get("delivery", {}).get("human_summary", "")).strip(),
            payload=standard_output,
            actor=task_actor,
        )
        incident_packet = self.build_task_incident_packet(
            task_before=task_before,
            task_after=task_after,
            planner_payload=planner_payload,
            status_sync=status_sync,
            standard_output=standard_output,
        )
        incident_record = None
        if incident_packet:
            incident_record = self.db.record_task_incident(
                task_id=task_id,
                incident_type=str(incident_packet.get("incident_type", "")).strip(),
                severity=str(incident_packet.get("severity", "")).strip(),
                status=str(incident_packet.get("status", "")).strip() or "open",
                reason=str(incident_packet.get("reason", "")).strip(),
                summary=str(incident_packet.get("summary", "")).strip(),
                owner=str(incident_packet.get("owner", "")).strip(),
                details=dict(incident_packet.get("details", {})),
                actor=task_actor,
            )

        planner_payload["delivery"] = {
            "channel": standard_output["delivery"]["channel"],
            "status": standard_output["delivery"]["status"],
            "output_record_id": output_record.get("id"),
        }
        planner_payload["human_gate"] = dict(standard_output.get("human_gate", {}))
        planner_payload["telemetry_snapshot"] = dict(standard_output.get("telemetry", {}))
        planner_payload["incident"] = (
            {
                "recorded": True,
                "incident_id": incident_record.get("id"),
                "incident_type": incident_record.get("incident_type"),
                "severity": incident_record.get("severity"),
                "status": incident_record.get("status"),
            }
            if incident_record
            else {"recorded": False}
        )

        return {
            "report": report,
            "planner_payload": planner_payload,
            "task_status_sync": status_sync,
            "points": points_result,
            "notify_chat": notify_chat,
            "chat_output": chat_output,
            "standard_output": standard_output,
            "output_record": output_record,
            "incident": incident_record,
        }


    def build_standard_output_packet(
        self,
        *,
        task_before: dict[str, Any],
        task_after: dict[str, Any],
        planner_payload: dict[str, Any],
        status_sync: dict[str, Any],
        chat_output: str,
        notify_chat: bool,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a normalized delivery packet for human and machine consumers."""
        failed_items = [str(item).strip() for item in planner_payload.get("failed_items", []) if str(item).strip()]
        failed_item_keys = {item.lower() for item in failed_items}
        needs_clarification = bool(task_after.get("needs_clarification"))
        need_human_confirm = bool(task_after.get("need_human_confirm"))
        human_confirmed = bool(task_after.get("human_confirmed"))
        task_status_after = str(status_sync.get("task_status_after", task_after.get("status", "")) or "").strip().lower()
        requires_human_assistance = (
            needs_clarification
            or (need_human_confirm and not human_confirmed)
            or task_status_after == "escalated"
            or "stage_contract_failed" in failed_item_keys
            or str(planner_payload.get("report_status", "")).strip().lower() in {"failed", "escalated"}
        )
        resolution_summary = str(planner_payload.get("resolution_summary", "")).strip()
        human_summary = chat_output if notify_chat and chat_output != "NO_REPLY" else resolution_summary
        if not human_summary:
            human_summary = str(task_after.get("reason", "")).strip() or str(task_before.get("reason", "")).strip()
        selection_inputs = task_after.get("selection_inputs", {})
        if not isinstance(selection_inputs, dict):
            selection_inputs = {}
        execution_envelope = selection_inputs.get("execution_envelope", {})
        if not isinstance(execution_envelope, dict):
            execution_envelope = {}
        trace_id = str(
            task_after.get("trace_id", "")
            or task_before.get("trace_id", "")
            or execution_envelope.get("trace_id", "")
        ).strip()
        attempt_id = str(
            task_after.get("attempt_id", "")
            or task_before.get("attempt_id", "")
            or execution_envelope.get("attempt_id", "")
        ).strip()
        return {
            "schema_version": "2026-03-22",
            "trace_id": trace_id,
            "attempt_id": attempt_id,
            "task_id": str(task_after.get("task_id", task_before.get("task_id", ""))).strip(),
            "execution_envelope": dict(execution_envelope),
            "workflow": {
                "profile_id": str(task_after.get("workflow_profile_id", "")).strip(),
                "channel": str(task_after.get("workflow_channel", "")).strip(),
                "stage_id": str(task_after.get("stage_id", "")).strip(),
                "score_gate": str(task_after.get("stage_score_gate", "")).strip(),
            },
            "outcome": {
                "report_status": str(planner_payload.get("report_status", "")).strip(),
                "task_status_before": str(status_sync.get("task_status_before", "")).strip(),
                "task_status_after": task_status_after,
                "task_action_after": str(status_sync.get("task_action_after", task_after.get("action", ""))).strip(),
                "solved": bool(planner_payload.get("solved", False)),
                "failure_count": max(0, int(planner_payload.get("failure_count", 0) or 0)),
                "failed_items": failed_items,
                "quality_score": planner_payload.get("quality_score"),
                "quality_grade": str(planner_payload.get("quality_grade", "")).strip(),
            },
            "human_gate": {
                "need_human_confirm": need_human_confirm,
                "human_confirmed": human_confirmed,
                "needs_clarification": needs_clarification,
                "clarification_reason": str(task_after.get("clarification_reason", "")).strip(),
                "requires_human_assistance": requires_human_assistance,
                "notify_chat": bool(notify_chat),
            },
            "telemetry": {
                "duration_ms": max(0, int(planner_payload.get("duration_ms", 0) or 0)),
                "model_id": str(planner_payload.get("model_id", "")).strip(),
                "input_tokens": max(0, int(planner_payload.get("input_tokens", 0) or 0)),
                "output_tokens": max(0, int(planner_payload.get("output_tokens", 0) or 0)),
                "total_tokens": max(0, int(planner_payload.get("total_tokens", 0) or 0)),
                "cost_estimate": round(float(planner_payload.get("cost_estimate", 0.0) or 0.0), 6),
                "task_token_usage": dict(planner_payload.get("task_token_usage", {})),
                "task_timing": dict(planner_payload.get("task_timing", {})),
            },
            "contracts": {
                "stage_output_contract": dict(task_after.get("stage_output_contract", {})),
                "stage_verification_contract": dict(task_after.get("stage_verification_contract", {})),
                "stage_contract": dict(details.get("stage_contract", {})) if isinstance(details, dict) else {},
                "stage_contract_gate": dict(details.get("stage_contract_gate", {})) if isinstance(details, dict) else {},
            },
            "delivery": {
                "channel": "chat" if notify_chat else "none",
                "status": "prepared" if notify_chat else "suppressed",
                "human_summary": human_summary,
                "machine_summary": {
                    "report_id": planner_payload.get("report_id"),
                    "report_ts": planner_payload.get("report_ts"),
                },
            },
        }


    def build_task_incident_packet(
        self,
        *,
        task_before: dict[str, Any],
        task_after: dict[str, Any],
        planner_payload: dict[str, Any],
        status_sync: dict[str, Any],
        standard_output: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build a normalized incident packet when the task needs human follow-up."""
        failed_items = [str(item).strip() for item in planner_payload.get("failed_items", []) if str(item).strip()]
        failed_item_keys = {item.lower() for item in failed_items}
        triggers: list[str] = []
        task_status_after = str(status_sync.get("task_status_after", task_after.get("status", "")) or "").strip().lower()
        report_status = str(planner_payload.get("report_status", "")).strip().lower()
        if task_status_after == "escalated":
            triggers.append("task_escalated")
        if bool(task_after.get("needs_clarification")):
            triggers.append("needs_clarification")
        if bool(task_after.get("need_human_confirm")) and not bool(task_after.get("human_confirmed")):
            triggers.append("waiting_human_confirm")
        if "stage_contract_failed" in failed_item_keys:
            triggers.append("stage_contract_failed")
        if report_status == "failed":
            triggers.append("agent_failed")
        elif report_status == "partial" and bool(failed_items):
            triggers.append("task_partial")
        if not triggers:
            return None

        incident_type = triggers[0]
        severity = "warning"
        if incident_type in {"task_escalated", "agent_failed"}:
            severity = "critical"
        reason = str(status_sync.get("task_action_after", "")).strip() or incident_type
        summary = str(standard_output.get("delivery", {}).get("human_summary", "")).strip()
        if not summary:
            summary = str(task_after.get("reason", "")).strip() or str(task_before.get("reason", "")).strip()
        return {
            "incident_type": incident_type,
            "severity": severity,
            "status": "open",
            "reason": reason,
            "summary": summary,
            "owner": str(task_after.get("assignee", "")).strip(),
            "details": {
                "schema_version": "2026-03-22",
                "triggers": triggers,
                "task_status_after": task_status_after,
                "report_status": report_status,
                "workflow_profile_id": str(task_after.get("workflow_profile_id", "")).strip(),
                "stage_id": str(task_after.get("stage_id", "")).strip(),
                "failed_items": failed_items,
                "human_gate": dict(standard_output.get("human_gate", {})),
                "telemetry": dict(standard_output.get("telemetry", {})),
            },
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

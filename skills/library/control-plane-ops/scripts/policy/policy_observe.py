"""Policy Enforcer — ObservabilityMixin."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

from policy_defaults import DEFAULT_POLICY, DEFAULT_ROUTING_RULES
from policy_utils import PolicyError, RuntimePaths, parse_bool, merge_missing_keys, emit_json, read_json, now_iso
from io_write_gateway import atomic_write_text, write_json_atomic
from task_center import TASK_STATUSES, load_pricing, format_daily_summary_markdown
from policy_route_selection import build_route_selection

class ObservabilityMixin:
    """Mixin providing Observability methods for PolicyEnforcer."""

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


    def update_task_incident(self, args: argparse.Namespace) -> dict[str, Any]:
        details: dict[str, Any] | None = None
        raw_details = str(getattr(args, "details_json", "") or "").strip()
        if raw_details:
            details = self.parse_optional_json_arg(raw_details, "details-json")
        return self.db.update_task_incident(
            int(args.incident_id),
            status=str(getattr(args, "status", "") or "").strip(),
            reason=getattr(args, "reason", None),
            summary=getattr(args, "summary", None),
            owner=getattr(args, "owner", None),
            details=details,
            actor=str(getattr(args, "actor", "") or "").strip(),
        )


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
        task_type = str(getattr(args, "task_type", "workflow") or "workflow").strip() or "workflow"
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
        requirement_package_gate = self.evaluate_requirement_package_gate(
            request_source=request_source,
            task_type=task_type,
            context_payload=context_payload,
            project_requirement=project_requirement,
        )
        owner = str(context_payload.get("owner", "")).strip()
        change_id = str(context_payload.get("change_id", "")).strip()
        needs_clarification = bool(context_eval.get("needs_clarification"))
        if bool(requirement_package_gate.get("needs_clarification")):
            needs_clarification = True
        clarification_reason = "; ".join(
            self._merge_text_lists(
                str(context_eval.get("clarification_reason", "")).strip(),
                requirement_package_gate.get("clarification_reason", ""),
            )
        ).strip()
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
        workflow_selection = self.select_workflow_for_request(
            description=effective_text,
            task_type=task_type,
            request_source=request_source,
            source=args.source,
            assignee=assignee,
            needs_clarification=needs_clarification,
            context_payload=context_payload,
        )
        selected_profile = str(workflow_selection.get("workflow_profile_id") or "").strip()
        route_selection_required = True
        route_selection = build_route_selection(
            risk_level=risk_level,
            needs_clarification=needs_clarification,
            workflow_profile_id=selected_profile,
            task_type=task_type,
            require_manual=True,
        )
        execution_mode = "manual_route_selection"

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
                "mode": execution_mode,
                "confirmation_required": bool(need_human_confirm),
                "confirmation_reason": confirmation_reason,
                "clarification_required": bool(needs_clarification),
                "route_selection_required": route_selection_required,
                "recommended_route": route_selection["recommended_route"],
                "confirm_command_after_create": (
                    "python3 skills/library/control-plane-ops/scripts/policy/human_inbox.py "
                    + "confirm --task-id <task_id> --route-choice recommended --actor human"
                ),
            },
            "code_dispatch_forced": code_dispatch_forced,
            "code_dispatch_target": code_dispatch_target,
            "code_dispatch_reason": code_dispatch_reason,
            "context_completeness": float(context_eval.get("context_completeness", 100.0) or 100.0),
            "context_fields_missing": list(context_eval.get("missing_fields", [])),
            "context_fields_recommended_missing": list(context_eval.get("missing_recommended_fields", [])),
            "requirement_package_gate": requirement_package_gate,
            "context_payload": context_payload,
            "workflow_selection": workflow_selection,
            "route_selection": route_selection,
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
        capability_registry_file = self.capability_registry_file()
        workflow_profile_registry_file = self.workflow_profile_registry_file()
        for path in [
            self.paths.policy_file,
            self.paths.routing_file,
            self.paths.pricing_file,
            capability_registry_file,
            workflow_profile_registry_file,
        ]:
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

        registry = self.workflow_profile_registry
        default_profile_id = str(registry.get("default_profile_id", "") or "").strip()
        default_channel = str(registry.get("default_channel", "") or "").strip().lower()
        _ = self.resolve_workflow_profile_entry(default_profile_id, default_channel)

        for profile_entry in registry.get("profiles", []):
            promotion_target_channel = str(profile_entry.get("promotion_target_channel", "") or "").strip().lower()
            if promotion_target_channel:
                _ = self.resolve_workflow_profile_entry(profile_entry["profile_id"], promotion_target_channel)

        return {
            "ok": True,
            "db": str(self.paths.db),
            "policy_file": str(self.paths.policy_file),
            "routing_file": str(self.paths.routing_file),
            "pricing_file": str(self.paths.pricing_file),
            "capability_registry_file": str(capability_registry_file),
            "workflow_profile_registry_file": str(workflow_profile_registry_file),
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


    def resolve_entry_route(self, args: argparse.Namespace) -> dict[str, Any]:
        """根据消息长度和关键字判断入口路由层级，输出 guidance 和技能列表。

        读取 routing-rules.json 的 entry_routing 配置，将请求分为
        light/medium/major 三级，返回对应的起始阶段、所需技能和指引文本。

        Args:
            args: 需包含 --message-hint (请求文本片段, 最多200字)
                  和 --entry-agent (入口 Agent ID)。

        Returns:
            dict 包含 tier, start_stage, required_skills, guidance 等字段。

        Raises:
            PolicyError: 当 entry_routing 未配置或 enabled=false 时。
        """
        entry_routing = self.routing.get("entry_routing", {})
        if not entry_routing or not parse_bool(entry_routing.get("enabled", False), False):
            return {
                "tier": "disabled",
                "guidance": "",
                "required_skills": [],
                "start_stage": "execute",
                "workflow_profile_id": str(entry_routing.get("default_workflow_profile_id", "coding-default")),
            }

        message_hint = str(getattr(args, "message_hint", "") or "").strip()
        entry_agent = str(getattr(args, "entry_agent", "") or "").strip() or "coordinator"
        msg_len = len(message_hint)

        tiers_cfg = entry_routing.get("tiers", {})
        stages_cfg = entry_routing.get("stages", [])
        default_profile = str(entry_routing.get("default_workflow_profile_id", "coding-default"))

        # tier 判定：major > light > medium（优先匹配强制关键字）
        resolved_tier = "medium"
        major_cfg = tiers_cfg.get("major", {})
        light_cfg = tiers_cfg.get("light", {})
        medium_cfg = tiers_cfg.get("medium", {})

        major_keywords = [str(k).lower() for k in major_cfg.get("force_keywords", [])]
        light_keywords = [str(k).lower() for k in light_cfg.get("match_keywords", [])]
        msg_lower = message_hint.lower()

        if any(kw in msg_lower for kw in major_keywords):
            resolved_tier = "major"
        elif msg_len <= int(light_cfg.get("max_message_length", 30)) and any(kw in msg_lower for kw in light_keywords):
            resolved_tier = "light"
        elif msg_len <= int(light_cfg.get("max_message_length", 30)):
            resolved_tier = "light"
        elif msg_len <= int(medium_cfg.get("max_message_length", 100)):
            resolved_tier = "medium"
        else:
            resolved_tier = "major"

        tier_cfg = tiers_cfg.get(resolved_tier, {})
        skip_stages = set(str(s).strip() for s in tier_cfg.get("skip_stages", []))
        required_skills = [str(s).strip() for s in tier_cfg.get("required_skills", []) if str(s).strip()]
        alt_skill = str(tier_cfg.get("alternative_skill", "")).strip()

        active_stages = [s for s in stages_cfg if str(s.get("id", "")) not in skip_stages]
        start_stage = str(active_stages[0]["id"]) if active_stages else "execute"

        # 构建 guidance 文本
        guidance_lines = [f"[Entry Router] tier={resolved_tier}"]
        if resolved_tier == "light":
            guidance_lines.append("快速任务，跳过澄清直接执行。")
        elif resolved_tier == "medium":
            guidance_lines.append("建议拆分后执行：")
        else:
            guidance_lines.append("强制完整流程：")

        for idx, stage in enumerate(active_stages, 1):
            skill_name = str(stage.get("skill", ""))
            display = str(stage.get("display", ""))
            guidance_lines.append(f"{idx}. [{skill_name}] {display}")

        if alt_skill:
            guidance_lines.append(f"或: 直接触发 [{alt_skill}] 一站式编排")
        guidance_lines.append(f"workflow: {default_profile}@stable")

        return {
            "tier": resolved_tier,
            "start_stage": start_stage,
            "required_skills": required_skills,
            "active_stages": [str(s.get("id", "")) for s in active_stages],
            "alternative_skill": alt_skill,
            "workflow_profile_id": default_profile,
            "entry_agent": entry_agent,
            "message_length": msg_len,
            "guidance": "\n".join(guidance_lines),
        }


# ── CLI entry point (extracted to policy_cli.py) ──────────────────────
if __name__ == "__main__":
    from policy_cli import main  # noqa: E402
    sys.exit(main())

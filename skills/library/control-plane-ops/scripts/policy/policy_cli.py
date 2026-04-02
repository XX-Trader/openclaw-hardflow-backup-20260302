"""CLI entry point for the Policy Enforcer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Add parent dir to sys.path for sibling imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from policy_utils import (
    PolicyError,
    RuntimePaths,
    emit_json,
    runtime_defaults,
    GOVERNANCE_BRIDGE_EPILOG,
    read_json,
)
from policy_defaults import (
    DEFAULT_POLICY,
    DEFAULT_ROUTING_RULES,
    DEFAULT_TOKEN_PRICING,
    DEFAULT_WORKFLOW_PROFILE_REGISTRY,
    DEFAULT_BENCHMARK_SUITE_REGISTRY,
)
from io_write_gateway import FileWriteError, write_json_atomic
from task_center import TaskCenter, TaskCenterError
from task_capability_binding import DEFAULT_CAPABILITY_REGISTRY

from policy_utils import parse_bool  # used in build_parser


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
    create.add_argument("--stage-id", default="")
    create.add_argument("--workflow-profile-id", default="")
    create.add_argument("--workflow-channel", default="")
    create.add_argument("--workflow-selection-reason", default="")
    create.add_argument("--workflow-selection-inputs-json", default="")
    create.add_argument("--workflow-selection-inputs-file", default="")
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

    update_incident = sub.add_parser("update-task-incident", help="update task incident lifecycle state")
    update_incident.add_argument("--incident-id", required=True)
    update_incident.add_argument("--status", default="")
    update_incident.add_argument("--reason", default=None)
    update_incident.add_argument("--summary", default=None)
    update_incident.add_argument("--owner", default=None)
    update_incident.add_argument("--details-json", default="")
    update_incident.add_argument("--actor", default="")

    assert_entry = sub.add_parser("assert-entry", help="validate entry agent")
    assert_entry.add_argument("--entry-agent", required=True)

    select_workflow = sub.add_parser("select-workflow", help="select workflow profile for a request")
    select_workflow.add_argument("--description", required=True)
    select_workflow.add_argument("--task-type", default="workflow")
    select_workflow.add_argument("--source", default="openclaw")
    select_workflow.add_argument("--request-source", default="")
    select_workflow.add_argument("--assignee", default="")
    select_workflow.add_argument("--needs-clarification", default="false")
    select_workflow.add_argument("--workflow-profile-id", default="")
    select_workflow.add_argument("--workflow-channel", default="")
    select_workflow.add_argument("--workflow-selection-reason", default="")
    select_workflow.add_argument("--workflow-selection-inputs-json", default="")
    select_workflow.add_argument("--workflow-selection-inputs-file", default="")
    select_workflow.add_argument("--context-json", default="")
    select_workflow.add_argument("--context-file", default="")

    route = sub.add_parser("route-task", help="route task by routing rules")
    route.add_argument("--description", required=True)
    route.add_argument("--task-type", default="workflow")
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

    entry_route = sub.add_parser("resolve-entry-route", help="classify entry tier and output routing guidance")
    entry_route.add_argument("--entry-agent", default="coordinator")
    entry_route.add_argument("--message-hint", default="")
    _ = entry_route

    return parser


def cmd_init(paths: RuntimePaths, force: bool) -> dict[str, Any]:
    paths.db.parent.mkdir(parents=True, exist_ok=True)
    capability_registry_file = paths.policy_file.parent / "capability-registry.json"
    workflow_profile_registry_file = paths.policy_file.parent / "workflow-profile-registry.json"
    benchmark_suite_registry_file = paths.policy_file.parent / "benchmark-suite-registry.json"

    for file_path, defaults in [
        (paths.policy_file, DEFAULT_POLICY),
        (paths.routing_file, DEFAULT_ROUTING_RULES),
        (paths.pricing_file, DEFAULT_TOKEN_PRICING),
        (capability_registry_file, DEFAULT_CAPABILITY_REGISTRY),
        (workflow_profile_registry_file, DEFAULT_WORKFLOW_PROFILE_REGISTRY),
        (benchmark_suite_registry_file, DEFAULT_BENCHMARK_SUITE_REGISTRY),
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
        "capability_registry_file": str(capability_registry_file),
        "workflow_profile_registry_file": str(workflow_profile_registry_file),
        "benchmark_suite_registry_file": str(benchmark_suite_registry_file),
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

        from policy_enforcer import PolicyEnforcer  # lazy import to avoid circular
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
            elif args.command == "update-task-incident":
                emit_json({"ok": True, "incident": enforcer.update_task_incident(args)})
            elif args.command == "select-workflow":
                emit_json({"ok": True, "selection": enforcer.select_workflow(args)})
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
            elif args.command == "resolve-entry-route":
                emit_json({"ok": True, "route": enforcer.resolve_entry_route(args)})
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

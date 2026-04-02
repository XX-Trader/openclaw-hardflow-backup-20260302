# TODO Patrol Policy Flow

## Purpose
- Keep monitoring/incident ingestion decoupled from task execution.
- Force TODO -> task-center writes through `policy_enforcer` (fail-close gate).
- Keep OPS incidents in TODO for manual/A2A handoff by `coordinator`.

## Current Flow
1. `ops_cron_runner` writes high-risk incidents to `TODO.md` (`OPS Incident Inbox`).
2. `todo_patrol` scans TODO:
   - default `--skip-ops-incidents=true`
   - non-OPS items are routed and dispatched.
3. `todo_patrol` calls `policy_enforcer` (`create_task` / `assign_task`) instead of direct DB writes.
4. `TaskCenter` records:
   - unique `task_id`
   - status/retry/failure/escalation
   - events and context payload
   - token/cost/score lifecycle.

## Information Packet (for AI execution)
`context_payload.information_flow` includes:
- `task_definition`: `current_state` vs `expected_target`
- `bug_scenario`: `operation_path`, `trigger_conditions`, `reproduction_steps`
- `requirement_boundary`: `functional_scope`, `constraints`, `acceptance_criteria`
- `assignment_packet`: `status_snapshot`, `full_background`, `deliverables`, `dependencies`, `history_changes`
- `assignment_packet.status_snapshot` also carries `owner` and `change_id` when available.

### Context Contract
- Required (AI source must provide): `problem`, `location`, `first_seen_at`, `impact`, `evidence`, `current_state`, `expected_state`, `operation_path`, `reproduction_steps`, `scope`, `constraints`, `acceptance_criteria`, `full_background`.
- Recommended (tracked as warnings): `duration`, `trigger_conditions`, `dependencies`, `history_changes`, `deliverables`, `owner`, `change_id`.
- If required fields are missing, task is forced to `clarification_required` and routed to clarification assignee before execution.

## Human Review Summary
`todo_patrol` output includes concise fields:
- `human_summary`
- `risk_points`
- `priority/risk/assignee`
- `dependencies/history_changes/deliverables`

## Operational Notes
- Failure threshold and escalation are still enforced by policy/task-center (`>=3` -> escalate human).
- High-risk execution still requires human confirmation before running code stages.

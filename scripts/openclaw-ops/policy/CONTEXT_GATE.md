# Context Gate (Human vs AI)

This document describes the hard constraints added for task intake.

## Goal

- Keep human quick requests fast.
- Force AI-generated tasks to include complete context.
- Route human project-level requests to `project-agent` first.

## Data Fields (task_center.tasks)

- `request_source`: `human|ai`
- `needs_clarification`: `0|1`
- `clarification_reason`: why execution is blocked
- `context_completeness`: `0~100`
- `context_fields_missing`: comma-separated missing fields
- `context_payload`: JSON context package

## Policy Rules

- `request_source=human`
  - Small operational tasks can go through normal dispatch.
  - Project requirements are routed to `project-agent` first.
- `request_source=ai`
  - Must pass context gate (`context_policy.ai_required_fields`).
  - If incomplete, task is marked `needs_clarification=true`,
    assignee becomes `project-agent`, and stage execution is blocked.

## CLI Changes

- `create-task`:
  - `--request-source`
  - `--context-json`
  - `--context-file`
  - `--force-needs-clarification`
  - `--clarification-reason`
- `route-task`:
  - `--request-source`
  - `--context-json`
  - `--context-file`
- New command:
  - `resolve-clarification --task-id ... --context-json ...`
  - `resolve-clarification --task-id ... --context-file ./context.json`

## Execution Guard

- `pre-stage` now fails when `needs_clarification=true`.
- This prevents agents from executing code before context is complete.

## TODO Patrol Behavior

- Adds source-aware dispatch:
  - AI items: context gate required
  - Human project items: routed to `project-agent`
- TODO line tags:
  - `AUTO_DISPATCHED`
  - `AUTO_CLARIFY_REQUIRED`

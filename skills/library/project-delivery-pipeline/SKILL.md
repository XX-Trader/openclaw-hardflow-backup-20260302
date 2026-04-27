---
name: project-delivery-pipeline
description: >
  End-to-end coding delivery pipeline. It turns one user requirement into a
  reviewed requirement package, researched solution, coding handoff, tests,
  score, code review, acceptance evidence, repair loop, memory writeback, and
  optional controlled Git publish.
metadata:
  runtime:
    hosts: ["generic", "hermes", "openclaw", "custom"]
  entrypoints:
    runner: "scripts/pipeline_runner.py"
    installer: "scripts/runtime_installer.py"
---

# Project Delivery Pipeline

## Purpose

Use this skill when the user gives a product or coding requirement and expects the
system to carry it through the whole delivery lifecycle:

- requirement exploration and normalization
- multi-AI requirement review
- external solution research before coding
- solution review
- coding agent execution
- tests, scoring, and acceptance
- code review
- repair loops
- project memory writeback
- optional Git publish after all gates pass

OpenClaw and Hermes are runtime host examples only. The workflow must stay the
same and host-specific paths belong in the runtime adapter or installer config.

## Current Capability

The included runner is a deterministic state-machine MVP. It can generate and
verify all orchestration artifacts in `--dry-run` mode. In live mode it can run
trusted runtime commands for research, coding, verification, code review,
project memory writeback, and controlled Git publish; if a required live command
or artifact is missing, it blocks at the correct stage instead of pretending
completion.

It also bootstraps the project memory module for the selected `project_key` and
can mirror the run into the existing SQLite Task Center. The `.workflow` run
directory is the evidence store; Task Center is the control-plane view for
status, stage runs, communications, outputs, and incidents.

It includes a Hermes profile smoke harness. The harness still calls the same
runner and does not fork the workflow: `echo` mode is deterministic, `hybrid`
mode uses one real `hermes chat` call to bundle research/code/review plus
deterministic local verification, and `hermes-chat` mode uses Hermes chat for
every stage as a provider diagnostic path.

## Standard Command

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key openclaw-hardflow \
  --runtime-host generic \
  --dry-run \
  --requirement "Build the full coding delivery pipeline" \
  --emit-json
```

Install into any runtime home:

```bash
python setup.py --runtime-home ~/.hardflow-runtime --runtime-name local-agent
```

Record the same run into Task Center:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key openclaw-hardflow \
  --runtime-host generic \
  --dry-run \
  --record-task-center \
  --task-center-db ~/.hardflow-runtime/ops/task-center/task_center.db \
  --requirement "Build the full coding delivery pipeline"
```

Run live with explicit runtime commands:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key openclaw-hardflow \
  --requirement "Build the full coding delivery pipeline" \
  --research-command "<research-agent-command>" \
  --code-command "<hardflow-or-agent-code-command>" \
  --verification-command "<lint/typecheck/unit-command>" \
  --verification-command "<smoke-command>" \
  --requirements-review-command "<reviewer-a-command>" \
  --requirements-review-command "<reviewer-b-command>" \
  --solution-review-command "<reviewer-a-command>" \
  --solution-review-command "<reviewer-b-command>" \
  --code-review-command "<reviewer-a-command>" \
  --code-review-command "<reviewer-b-command>" \
  --git-publish-command "<safe-git-publish-command>" \
  --write-project-memory
```

Run a Hermes profile smoke:

```bash
python skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py \
  --runtime-home ~/.hermes \
  --agent-mode hybrid \
  --provider zai \
  --emit-json
```

Inspect the latest run or a specific run:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py view \
  --workspace-root .workflow/pipeline-runs \
  --run-id <run_id>
```

Useful failure-route checks:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key demo \
  --runtime-host generic \
  --dry-run \
  --requirement "ambiguous feature" \
  --simulate-failure-stage requirements \
  --emit-json
```

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key demo \
  --runtime-host generic \
  --dry-run \
  --requirement "feature with wrong acceptance criteria" \
  --simulate-failure-stage acceptance_requirement \
  --emit-json
```

## Execution Protocol

1. Intake the user requirement and create `run_meta.json`.
2. Snapshot repository/runtime context.
3. Load or bootstrap the project memory module and write `project_memory_context.md`.
4. Require project-agent to identify likely change locations before coding.
5. Perform or require external research before solution design.
6. Produce `requirements.md`.
7. Run two independent reviewers and require `ready_for_solution`; both command
   reports must come from distinct commands and distinct `reviewer_role` values
   (`reviewer-a` / `reviewer-b`).
8. Produce `solution.md`.
9. Run two independent reviewers and require `ready_for_implement`; both command
   reports must come from distinct commands and distinct `reviewer_role` values
   (`reviewer-a` / `reviewer-b`).
10. Dispatch coding agents. In dry-run this is simulated; in live mode provide
   `--code-command` or `--patch-summary-file`.
11. Run tests and verification. In live mode provide one or more
   `--verification-command` values or attach `--verification-report-file`.
12. Run code review and require `pass`. In live mode provide at least two
   `--code-review-command` values with distinct `reviewer_role` values, or attach
   `--code-review-file`.
13. Run acceptance. Route requirement-caused failures to requirement revision and
    implementation-caused failures to coding agents.
14. Write final `delivery_evidence.md`, `pipeline_state.json`, and execute
    `--write-project-memory` or `--memory-write-command` for live runs.
15. If `--git-publish-command` is supplied, publish only after verification,
    code review, optional deployment, acceptance, and memory writeback pass.
    Commit messages and publish notes must be Chinese; force push and
    secret-bearing diffs are forbidden.
16. If enabled, mirror the run into Task Center with stage runs, communications,
    final output, and incidents.

## Project Memory Gate

Each `project_key` gets a project memory module:

- `PROJECT_PROFILE.md`
- `DECISIONS.md`
- `DELIVERY_RULES.md`
- `API_REGISTRY.json`
- `SOURCE_REGISTRY.json`
- `IMPACT_MAP.json`
- `RETRIEVAL_MANIFEST.json`

The default retrieval policy is hybrid local-first: structured project memory,
keyword/symbol search, optional vector search, and GraphRAG only when the task is
cross-module or multi-hop. This keeps the system maintainable and prevents the
coding agent from choosing a local optimum without knowing the global module
boundary.

## Failure Routing

| Failure source | Next action |
| --- | --- |
| Requirement ambiguity or wrong success criteria | `revise_requirements` |
| Solution is too complex or ignores mature options | `revise_solution` |
| Tests fail | `return_to_code_execution` |
| Code review fails | `return_to_code_execution` |
| Acceptance fails because requirement is wrong | `revise_requirements` |
| Acceptance fails because implementation is wrong | `return_to_code_execution` |
| Git publish fails | `fix_git_publish` |

When `git_publish` is enabled, the publish command must receive the accepted
writeback-aware patch. Prefer the `memory_writeback` workspace patch; fall back
to the accepted `code_execution` workspace patch only when memory writeback
produced no workspace patch. Never publish arbitrary dirty files from
`command_cwd`.

## External Research Rule

Before implementation, the coordinator must check whether official docs, existing
runtime skills, SDKs, or mature open-source code already solve the problem. If
research changes the requirement or solution, update those artifacts and rerun
the relevant review gate before coding.

The runner records source URLs through repeated `--source-url` flags. It does not
perform web browsing itself; the coordinator or researcher agent owns live
research.

## Live Runtime Integration Contract

Any host runtime should treat this skill as the workflow state surface:

- install with `python setup.py --runtime-home <runtime_home> --runtime-name <runtime_name>`
- call the runner with `--runtime-host <runtime_name> --runtime-home <runtime_home>`
- store run artifacts under `.workflow/pipeline-runs/<run_id>/`
- store project memory under `.workflow/project-memory/<project_key>/` or an
  adapter-provided runtime memory path
- pass `--record-task-center --task-center-db <db>` when Task Center is available
- let runtime agents fill the implementation and review artifacts
- when enabled, let a dedicated publish command handle safe commit/push after
  all gates pass
- re-run the state machine after each repaired artifact
- never fork the workflow just because the runtime host changes

## References

- `references/state-machine.md`
- `references/runtime-adapter.md`
- `templates/`

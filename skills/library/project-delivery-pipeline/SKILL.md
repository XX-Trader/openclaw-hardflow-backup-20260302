---
name: project-delivery-pipeline
description: >
  End-to-end coding delivery pipeline. It turns one user requirement into a
  reviewed requirement package, researched solution, coding handoff, tests,
  score, code review, acceptance evidence, repair loop, and memory writeback.
metadata:
  runtime:
    hosts: ["hermes", "openclaw"]
  entrypoints:
    runner: "scripts/pipeline_runner.py"
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

OpenClaw and Hermes are runtime hosts only. The workflow must stay the same and
host-specific paths belong in the runtime adapter.

## Current Capability

The included runner is a deterministic state-machine MVP. It can generate and
verify all orchestration artifacts in `--dry-run` mode and can block live runs
until coding, verification, or review artifacts are supplied by a real agent
runtime.

It does not directly launch Hermes agents yet. Hermes integration should call
the same runner before and after each real agent stage.

## Standard Command

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key openclaw-hardflow \
  --runtime-host hermes \
  --dry-run \
  --requirement "Build the full coding delivery pipeline" \
  --emit-json
```

Useful failure-route checks:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key demo \
  --runtime-host hermes \
  --dry-run \
  --requirement "ambiguous feature" \
  --simulate-failure-stage requirements \
  --emit-json
```

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --project-key demo \
  --runtime-host hermes \
  --dry-run \
  --requirement "feature with wrong acceptance criteria" \
  --simulate-failure-stage acceptance_requirement \
  --emit-json
```

## Execution Protocol

1. Intake the user requirement and create `run_meta.json`.
2. Snapshot repository/runtime context.
3. Perform or require external research before solution design.
4. Produce `requirements.md`.
5. Run two independent reviewers and require `ready_for_solution`.
6. Produce `solution.md`.
7. Run two independent reviewers and require `ready_for_implement`.
8. Dispatch coding agents. In dry-run this is simulated; in live mode the runner
   requires `--patch-summary-file`.
9. Run tests and verification. In live mode attach `--verification-report-file`.
10. Run code review and require `pass`. In live mode attach `--code-review-file`
    or let the coordinator create it.
11. Run acceptance. Route requirement-caused failures to requirement revision and
    implementation-caused failures to coding agents.
12. Write final `delivery_evidence.md`, `pipeline_state.json`, and a memory
    writeback recommendation.

## Failure Routing

| Failure source | Next action |
| --- | --- |
| Requirement ambiguity or wrong success criteria | `revise_requirements` |
| Solution is too complex or ignores mature options | `revise_solution` |
| Tests fail | `return_to_code_execution` |
| Code review fails | `return_to_code_execution` |
| Acceptance fails because requirement is wrong | `revise_requirements` |
| Acceptance fails because implementation is wrong | `return_to_code_execution` |

## External Research Rule

Before implementation, the coordinator must check whether official docs, existing
runtime skills, SDKs, or mature open-source code already solve the problem. If
research changes the requirement or solution, update those artifacts and rerun
the relevant review gate before coding.

The runner records source URLs through repeated `--source-url` flags. It does not
perform web browsing itself; the coordinator or researcher agent owns live
research.

## Live Hermes Integration Contract

Hermes should treat this skill as the workflow state surface:

- call the runner with `--runtime-host hermes`
- store run artifacts under `.workflow/pipeline-runs/<run_id>/`
- let Hermes agents fill the implementation and review artifacts
- re-run the state machine after each repaired artifact
- never fork the workflow just because the runtime host changes

## References

- `references/state-machine.md`
- `references/runtime-adapter.md`
- `templates/`

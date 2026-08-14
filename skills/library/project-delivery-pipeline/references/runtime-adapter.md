# Runtime Adapter Contract

## Principle

OpenClaw and Hermes are runtime host examples, not hard boundaries. Any runtime
home can host the same pipeline when the installer is given an explicit
`--runtime-home` and `--runtime-name`. The adapter only resolves paths, job
payloads, state directories, and agent dispatch mechanics.

Dual review hooks are treated as real A/B evidence: use two distinct commands
and make each command report expose a distinct `reviewer_role`
(`reviewer-a` / `reviewer-b`), either in command arguments or stdout.

## Host Defaults

| Host | Default runtime home | Pipeline state directory |
| --- | --- | --- |
| `generic` | `~/.hardflow-runtime` | `~/.hardflow-runtime/.workflow/pipeline-runs` |
| `hermes` | `~/.hermes` | `~/.hermes/.workflow/pipeline-runs` |
| `openclaw` | `~/.openclaw` | `~/.openclaw/.workflow/pipeline-runs` |
| custom | explicit `--runtime-home` | `<runtime-home>/.workflow/pipeline-runs` |

The local repository may also keep development dry-run artifacts under
`.workflow/pipeline-runs/<run_id>/`.

Project memory should live beside the run state unless the runtime adapter
provides a stronger project-memory path:

| Host | Default project memory directory |
| --- | --- |
| `generic` | `~/.hardflow-runtime/.workflow/project-memory/<project_key>` |
| `hermes` | `~/.hermes/.workflow/project-memory/<project_key>` |
| `openclaw` | `~/.openclaw/.workflow/project-memory/<project_key>` |
| custom | `<runtime-home>/.workflow/project-memory/<project_key>` |
| local dry-run | `.workflow/project-memory/<project_key>` |

## Installation Mapping

Use the new generic installer:

```bash
python setup.py --runtime-home <runtime_home> --runtime-name <runtime_name>
```

Examples:

```bash
python setup.py --runtime-home ~/.hardflow-runtime --runtime-name local-agent
python setup.py --runtime-home ~/.openclaw --runtime-name openclaw
python setup.py --runtime-home ~/.hermes --runtime-name hermes
```

The installer syncs the required skills, flat ops scripts, policy scripts, cron
jobs, and an install manifest. Each changed install records a managed-file
snapshot; an unchanged repeat keeps the existing snapshot. Restore the state
before the latest changed install with:

```bash
python setup.py rollback --runtime-home <runtime_home> --runtime-name <runtime_name>
```

Rollback restores or removes only paths recorded in that snapshot, so unrelated
runtime files remain in place. The installer replaces the old `workflow_setup.py`,
`install_workflow_profile.py`, `cron_setup.py`, and `install_*_job.py` chain.

## Hermes Mapping

Hermes should call:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file> \
  --record-task-center \
  --task-center-db ~/.hermes/ops/task-center/task_center.db
```

For live stages, Hermes should attach agent-produced artifacts:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file> \
  --patch-summary-file <patch_summary> \
  --verification-report-file <verification_report> \
  --code-review-file <code_review> \
  --record-task-center \
  --task-center-db ~/.hermes/ops/task-center/task_center.db
```

Or provide runtime commands directly:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --runtime-home ~/.hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file> \
  --research-command "<hermes research agent command>" \
  --code-command "<hermes/hardflow coding command>" \
  --verification-command "<test command>" \
  --requirements-review-command "<reviewer-a command>" \
  --requirements-review-command "<reviewer-b command>" \
  --solution-review-command "<reviewer-a command>" \
  --solution-review-command "<reviewer-b command>" \
  --code-review-command "<reviewer-a command>" \
  --code-review-command "<reviewer-b command>" \
  --write-project-memory
```

Each command is treated as trusted runtime code and writes a JSON evidence file
under `command-runs/`.

### Agent Workspace Isolation

Live command adapters run in per-agent Git worktrees:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --runtime-home ~/.hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file> \
  --code-command "<backend-dev command>" \
  --verification-command "<tester command>" \
  --code-review-command "<reviewer-a command>" \
  --code-review-command "<reviewer-b command>"
```

The runner always creates `agent-workspaces/<stage>/<agent>/repo` using
`git worktree add --detach HEAD`. `--command-cwd` must therefore be a Git
repository with a valid `HEAD`, and the agent workspace root must be outside
that repository. Use `--agent-workspace-root` only to choose a different
external location; it is not a mode switch.

The runner injects these variables into every stage command:

- `PIPELINE_AGENT_ID`
- `PIPELINE_AGENT_WORKSPACE`
- `PIPELINE_AGENT_REPO_DIR`
- `PIPELINE_AGENT_WORKSPACES_JSON`
- `PIPELINE_AGENT_WORKSPACE_MODE`

For isolated `code_execution`, the runner exports the agent workspace diff to
`command-runs/code_execution-1.patch`, applies it back to `--command-cwd`, and
then applies the same patch to later verification, review, deployment, and
publish workspaces. Command reports and Task Center details must record the
workspace and patch refs. A runtime still needs native session/run ids to claim
true host-level multi-agent fan-out.

### Hermes Profile Smoke

Use the smoke harness to verify the profile without creating a second workflow:

```bash
python skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py \
  --runtime-home ~/.hermes \
  --agent-mode hybrid \
  --provider zai \
  --emit-json
```

Smoke modes:

| Mode | Behavior |
| --- | --- |
| `echo` | Deterministic local stage commands; validates non-dry-run runner, Task Center, command evidence, and memory writeback without external AI calls. |
| `hybrid` | One real `hermes chat` call creates a research/code/review bundle; deterministic local verification remains a repeatable command. This is the recommended native profile smoke. |
| `hermes-chat` | Real `hermes chat` for every stage; useful for provider debugging, but intentionally not the default because each stage cold-starts Hermes. |

Latest local evidence: WSL Hermes profile `/home/runtime-user/.hermes`, run
`hermes-profile-smoke-20260424T135014Z`, `agent_mode=hybrid`,
`ai_bundle_mode=hybrid-single-chat`, status `completed`, Task Center task
`project-delivery:hermes-profile-smoke-20260424T135014Z`.

## OpenClaw Mapping

OpenClaw uses the same runner with `--runtime-host openclaw`. Legacy install
chains must not be restored.

## Custom Runtime Mapping

Custom hosts use the same runner with an explicit host label and runtime home:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host my-runtime \
  --runtime-home /srv/my-runtime \
  --project-key <project_key> \
  --requirement-file <requirement_file>
```

## WSL / Windows Boundary

When a runtime runs in WSL or Linux, prefer the Linux runtime path as the live
workdir. Windows paths are acceptable for local repository maintenance and
dry-run tests, but they must not leak into live job payloads unless explicitly
provided by the adapter or installer.

## Adapter Output

The adapter must write this runtime context into `run_meta.json` and
`pipeline_state.json`:

```json
{
  "host": "hermes",
  "runtime_home": "~/.hermes",
  "state_dir": "~/.hermes/.workflow/pipeline-runs",
  "skill_entry": "skills/library/project-delivery-pipeline/SKILL.md",
  "adapter_contract": "references/runtime-adapter.md"
}
```

## Task Center Contract

When a host has Task Center available, it should pass `--record-task-center`.
The runner mirrors the same workflow into:

- `tasks`: one `project_delivery_pipeline` task
- `stage_runs`: one row per state-machine stage
- `module_communications`: coordinator-to-agent stage handoffs
- `task_outputs`: final human/machine output
- `task_incidents`: blocked runs and repair routing

The host must not create a second task ledger for the same pipeline. If a host
already has a task id, pass it through `--task-center-task-id`.

## Retrieval Backend Contract

Runtime adapters may provide stronger retrieval backends, but they cannot change
the workflow order:

- local structured memory and keyword/symbol search are always available
- vector RAG is optional and should be declared in `RETRIEVAL_MANIFEST.json`
- GraphRAG is optional and only for global or multi-hop architecture questions
- MCP resources/tools may expose runtime state, but must respect workspace roots

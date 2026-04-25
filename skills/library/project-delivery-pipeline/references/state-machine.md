# Project Delivery Pipeline State Machine

## State Order

| State | Required artifact | Pass signal |
| --- | --- | --- |
| `intake` | `run_meta.json` | run metadata written |
| `context_snapshot` | `context_snapshot.md` | repository/runtime context captured |
| `project_memory_context` | `project_memory_context.md` | project memory module loaded and change-localization gate recorded |
| `external_research` | `research_report.md` | source URLs, report file, or `--research-command` evidence present |
| `requirements_package` | `requirements.md` | acceptance criteria and non-goals present |
| `requirements_discussion -> requirements_review` | `requirements_discussion -> requirements_review.md` | `Final verdict: ready_for_solution` |
| `solution_package` | `solution.md` | implementation and verification plan present |
| `solution_review` | `solution_review.md` | `Final verdict: ready_for_implement` |
| `code_execution` | `patch_summary.md` | implementation artifact or `--code-command` evidence present |
| `verification` | `verification_report.md` | `--verification-command` / report status `pass` and acceptable score |
| `code_review` | `code_review.md` | `Final verdict: pass` from file or `--code-review-command` |
| `acceptance` | `delivery_evidence.md` | acceptance status `pass` |
| `writeback` | `writeback_report.md` | live memory writeback completed or dry-run recommendation present |

## Gate Rules

- Do not design a solution until requirements review passes.
- Do not design or code until project memory has been checked for module
  boundaries, prior decisions, delivery rules, API/source registries, and likely
  change locations.
- Do not code until solution review passes.
- In live mode, do not proceed without research, coding, verification, code
  review, and memory-writeback evidence.
- Do not accept until tests and code review pass.
- If acceptance proves the requirement was wrong, return to `requirements_package`.
- If acceptance proves implementation was wrong, return to `code_execution`.
- If project-agent cannot identify a likely owning module/file, return to
  `requirements_package` or `solution_package` instead of guessing.

## Project Memory Contract

Each project memory module contains:

- `PROJECT_PROFILE.md`: project purpose, architecture, runtime entrypoints
- `DECISIONS.md`: durable decisions and rejected alternatives
- `DELIVERY_RULES.md`: coding, testing, and acceptance rules
- `API_REGISTRY.json`: third-party API ownership and docs
- `SOURCE_REGISTRY.json`: official docs, changelog, and repo sources
- `IMPACT_MAP.json`: modules, owners, entrypoints, tests, docs, related files
- `RETRIEVAL_MANIFEST.json`: retrieval policy and optional RAG backend metadata

Default retrieval is hybrid local-first. Use structured memory and code search
first; add vector search when docs exceed prompt budget; use GraphRAG only for
global architecture or multi-hop cross-module questions.

## Task Center Mirror

Task Center is the single control-plane view. When `--record-task-center` is
enabled, the runner mirrors one `project_delivery_pipeline` task into SQLite and
records:

- task status, next action, failed stage, and run directory
- one `stage_runs` row per pipeline stage
- one `module_communications` row per coordinator-to-agent stage handoff
- one final `task_outputs` row
- one `task_incidents` row when the pipeline blocks

## Live Command Adapter

The state machine exposes trusted command hooks instead of hardcoding a single
runtime:

- `--research-command`: researcher/web agent or official-doc lookup command.
- `--code-command`: HardFlow Core / ACP / backend-dev command.
- `--verification-command`: repeatable lint, typecheck, unit, integration,
  smoke, or deployment verification commands.
- `--code-review-command`: reviewer command that must emit `Final verdict: pass`.
- `--memory-write-command`: custom project memory writeback command.
- `--write-project-memory`: built-in `project_memory_writer.py` writeback.

Every command writes `command-runs/<stage>-<n>.json` with command, cwd,
timestamps, return code, stdout, and stderr. Non-zero exit routes to the owning
stage instead of marking the pipeline completed.

Each stage owner gets a dedicated Git worktree under
`agent-workspaces/<stage>/<agent>/repo`. The command
report also records `agent_id`, `agent_workspace`, `agent_workspaces`, and
`dispatch_mode`. For code execution, the runner exports the implementation diff
from the coding workspace and applies it back to the configured command cwd
before tester/reviewer/deployer workspaces are prepared.

Hermes profile smoke uses the same hooks through `hermes_profile_smoke.py`.
Recommended mode is `hybrid`: one `hermes chat` call creates a
research/code/review bundle while verification remains a deterministic local
command. This avoids per-stage Hermes cold starts and keeps smoke runs bounded.

## Scoring

The runner records scores in verification and acceptance artifacts. A live
runtime may replace the dry-run score with a stronger score-gate artifact, but
the route must remain deterministic:

- score >= 90 and code review pass: continue
- score < 90 from implementation evidence: `return_to_code_execution`
- score < 90 from wrong requirement or missing acceptance criteria: `revise_requirements`

## External Pattern Alignment

The design follows the same broad shape as mature coding-agent workflows:

- repository research before code changes
- implementation planning before execution
- isolated agent execution environment
- tests and logs as completion evidence
- review and iteration before final acceptance
- persistent project memory and scoped retrieval before editing
- task/control-plane observability for each run

External references checked during design:

- GitHub Copilot cloud agent docs: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- OpenAI Codex web docs: https://developers.openai.com/codex/cloud
- OpenAI file search/vector store docs: https://platform.openai.com/docs/guides/tools-file-search
- Model Context Protocol specification: https://modelcontextprotocol.io/specification/draft
- Microsoft GraphRAG docs: https://microsoft.github.io/graphrag/

## Known MVP Boundary

The current runner owns state, artifacts, command evidence, and optional memory
writeback. The Hermes smoke harness verifies a profile, but product-specific
implementation logic still belongs in stage commands or attached artifacts and
then feeds back into the same state machine.

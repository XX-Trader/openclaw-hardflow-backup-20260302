# Project Delivery Pipeline State Machine

## State Order

| State | Required artifact | Pass signal |
| --- | --- | --- |
| `intake` | `run_meta.json` | run metadata written |
| `context_snapshot` | `context_snapshot.md` | repository/runtime context captured |
| `external_research` | `research_report.md` | sources checked or explicit live-research gap recorded |
| `requirements_package` | `requirements.md` | acceptance criteria and non-goals present |
| `requirements_review` | `requirements_review.md` | `Final verdict: ready_for_solution` |
| `solution_package` | `solution.md` | implementation and verification plan present |
| `solution_review` | `solution_review.md` | `Final verdict: ready_for_implement` |
| `code_execution` | `patch_summary.md` | implementation artifact present |
| `verification` | `verification_report.md` | status `pass` and acceptable score |
| `code_review` | `code_review.md` | `Final verdict: pass` |
| `acceptance` | `delivery_evidence.md` | acceptance status `pass` |
| `writeback` | `writeback_report.md` | memory writeback recommendation present |

## Gate Rules

- Do not design a solution until requirements review passes.
- Do not code until solution review passes.
- Do not accept until tests and code review pass.
- If acceptance proves the requirement was wrong, return to `requirements_package`.
- If acceptance proves implementation was wrong, return to `code_execution`.

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

External references checked during design:

- GitHub Copilot cloud agent docs: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- OpenAI Codex web docs: https://developers.openai.com/codex/cloud

## Known MVP Boundary

The current runner owns state and artifacts. It does not itself browse the web,
launch Hermes agents, or edit product code. Those side effects belong to the
coordinator/Hermes runtime and must feed artifacts back into the same state
machine.

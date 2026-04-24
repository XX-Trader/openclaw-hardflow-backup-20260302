# Runtime Adapter Contract

## Principle

OpenClaw and Hermes are runtime hosts. They must not create separate business
workflows. The adapter only resolves paths, job payloads, state directories, and
agent dispatch mechanics.

## Host Defaults

| Host | Default runtime home | Pipeline state directory |
| --- | --- | --- |
| `hermes` | `~/.hermes` | `~/.hermes/.workflow/pipeline-runs` |
| `openclaw` | `~/.openclaw` | `~/.openclaw/.workflow/pipeline-runs` |

The local repository may also keep development dry-run artifacts under
`.workflow/pipeline-runs/<run_id>/`.

## Hermes Mapping

Hermes should call:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file>
```

For live stages, Hermes should attach agent-produced artifacts:

```bash
python skills/library/project-delivery-pipeline/scripts/pipeline_runner.py run \
  --runtime-host hermes \
  --project-key <project_key> \
  --requirement-file <requirement_file> \
  --patch-summary-file <patch_summary> \
  --verification-report-file <verification_report> \
  --code-review-file <code_review>
```

## OpenClaw Mapping

OpenClaw uses the same runner with `--runtime-host openclaw`. Legacy
`install_workflow_profile.py`, `cron_setup.py`, and `install_*_job.py` chains
must not be restored as the primary install path.

## WSL / Windows Boundary

When Hermes runs in WSL or Linux, prefer the Linux runtime path as the live
workdir. Windows paths are acceptable for local repository maintenance and
dry-run tests, but they must not leak into Hermes job payloads unless explicitly
provided by the adapter.

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

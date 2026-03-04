# openclaw-hardflow Project Index

- generated_at: 2026-03-04T00:57:07+00:00
- root: d:\学习资料\量化交易\openclaw-hardflow-backup-20260302
- git_repo: True
- git_branch: main
- git_remote: https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git
- dirty_files: 19

## Workflow
1. coordinator intake and requirement alignment
2. project-agent provides project context and index lookup
3. coordinator planning and risk dispatch
4. execution agents implement -> tester validates -> feedback loop
5. policy-enforcer records status/time/token/cost

## Module Files
- none

## API Related Files
- scripts/openclaw-ops/api_test_audit.py
- scripts/openclaw-ops/init_api_test_config.py
- skills/library/deployment-test/scripts/test-api.py

## Run / Change Scripts
- scripts/hardflow/EXPERIENCE_EVOLUTION.md
- scripts/hardflow/ISSUE_SCHEMA.md
- scripts/hardflow/PROCESS_OPTIMIZATION.md
- scripts/hardflow/README.md
- scripts/hardflow/ROLLBACK.md
- scripts/hardflow/SCORECARD_SCHEMA.md
- scripts/hardflow/atomic_task_guard.py
- scripts/hardflow/check-api-doc-gate.sh
- scripts/hardflow/check-review-test-gate.sh
- scripts/hardflow/check-score-gate.mjs
- scripts/hardflow/deploy-evolution-hooks.sh
- scripts/hardflow/experience-maintain-cron.sh
- scripts/hardflow/experience-maintain.mjs
- scripts/hardflow/hardflow-run.sh
- scripts/hardflow/hardflow-tmux-runner.sh
- scripts/hardflow/hardflow-v1.lobster.yaml
- scripts/hardflow/hardflow.env.example
- scripts/hardflow/hook-selftest.mjs
- scripts/hardflow/improve-gate.sh
- scripts/hardflow/preview-action.sh
- scripts/hardflow/process-optimize-cron.sh
- scripts/hardflow/process-optimize.mjs
- scripts/hardflow/remote-enable-evolution-hooks.py
- scripts/hardflow/remote-install-maintenance-cron.sh
- scripts/hardflow/score-gate.sh
- scripts/hardflow/score-policy.json
- scripts/hardflow/score-report.mjs
- scripts/openclaw-ops/MODEL_TIER_SWITCH.md
- scripts/openclaw-ops/README.md
- scripts/openclaw-ops/SETUP_WORKFLOW.md
- scripts/openclaw-ops/api_test_audit.py
- scripts/openclaw-ops/configure_runtime_env.py
- scripts/openclaw-ops/conversation_evolution_runner.py
- scripts/openclaw-ops/cron_setup.py
- scripts/openclaw-ops/cron_switch.py
- scripts/openclaw-ops/daily_todo_digest.py
- scripts/openclaw-ops/daily_work_report.py
- scripts/openclaw-ops/detect_openclaw_installations.py
- scripts/openclaw-ops/experience_maintain.py
- scripts/openclaw-ops/github_web_evolution_runner.py
- scripts/openclaw-ops/governance_evolution_runner.py
- scripts/openclaw-ops/init_api_test_config.py
- scripts/openclaw-ops/install_project_index_job.py
- scripts/openclaw-ops/install_reviewer_scan_jobs.py
- scripts/openclaw-ops/install_todo_patrol_job.py
- scripts/openclaw-ops/model_tier_profiles.json
- scripts/openclaw-ops/ops_cron_runner.py
- scripts/openclaw-ops/restore_openclaw_memory.py
- scripts/openclaw-ops/reviewer_cron_runner.py
- scripts/openclaw-ops/self_evolution_todo.py

## Update Rules
- API/parameters/process changes must update this index in the same commit.
- project-agent maintains this index; coordinator consumes it for planning.
- Dynamic doc knowledge is maintained in DOC_KNOWLEDGE.md and doc-knowledge.json.

# openclaw-hardflow-backup-20260302 Project Index

- generated_at: 2026-03-04T15:32:14+00:00
- root: .
- git_repo: True
- git_branch: main
- git_remote: https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git
- dirty_files: 14

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
- scripts/openclaw-ops/TODO_PATROL_POLICY_FLOW.md
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
- scripts/openclaw-ops/policy/CONTEXT_GATE.md
- scripts/openclaw-ops/policy/FIELD_DICTIONARY.md
- scripts/openclaw-ops/policy/MULTI_PROJECT_INSTALL.md
- scripts/openclaw-ops/policy/README.md
- scripts/openclaw-ops/policy/bootstrap_multi_project.py
- scripts/openclaw-ops/policy/io_write_gateway.py
- scripts/openclaw-ops/policy/policy-config.json
- scripts/openclaw-ops/policy/policy_enforcer.py
- scripts/openclaw-ops/policy/project-registry.example.json
- scripts/openclaw-ops/policy/project_index_maintainer.py
- scripts/openclaw-ops/policy/project_registry_runtime.py
- scripts/openclaw-ops/policy/projects.example.json
- scripts/openclaw-ops/policy/risk_rule_sync.py
- scripts/openclaw-ops/policy/routing-rules.json
- scripts/openclaw-ops/policy/runtime.env.example
- scripts/openclaw-ops/policy/runtime/file_write_audit.jsonl
- scripts/openclaw-ops/policy/task_center.py
- scripts/openclaw-ops/policy/token-pricing.json
- scripts/openclaw-ops/policy/workflow_setup.py
- scripts/openclaw-ops/restore_openclaw_memory.py
- scripts/openclaw-ops/reviewer_cron_runner.py
- scripts/openclaw-ops/self_evolution_todo.py
- scripts/openclaw-ops/switch_model_tier.ps1
- scripts/openclaw-ops/switch_model_tier.py
- scripts/openclaw-ops/switch_model_tier.sh
- scripts/openclaw-ops/sync_agents_12_to_servers.sh
- scripts/openclaw-ops/sync_model_to_doubao_servers.ps1
- scripts/openclaw-ops/sync_model_to_doubao_servers.sh
- scripts/openclaw-ops/sync_openclaw_ops_files.py
- scripts/openclaw-ops/sync_policy_enforcer_to_servers.ps1
- scripts/openclaw-ops/sync_policy_enforcer_to_servers.sh
- scripts/openclaw-ops/sync_todo_patrol_to_servers.ps1
- scripts/openclaw-ops/sync_todo_patrol_to_servers.sh
- scripts/openclaw-ops/system_schedule_snapshot.py
- scripts/openclaw-ops/todo_patrol.py
- scripts/openclaw-ops/verify_job_payload_paths.py

## Update Rules
- API/parameters/process changes must update this index in the same commit.
- project-agent maintains this index; coordinator consumes it for planning.
- Dynamic doc knowledge is maintained in DOC_KNOWLEDGE.md and doc-knowledge.json.

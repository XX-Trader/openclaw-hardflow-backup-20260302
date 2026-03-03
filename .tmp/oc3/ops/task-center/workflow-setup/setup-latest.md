# OpenClaw Workflow Init Report

- generated_at: 2026-03-03T14:43:42+00:00
- openclaw_home: .tmp\oc3
- strict_git_remote: False
- dry_run: False
- project_count: 1
- openclaw_selection: cli-arg

## openclaw-hardflow-backup-20260302
- path: D:\学习资料\量化交易\openclaw-hardflow-backup-20260302
- writable: True (ok)
- git_repo: True
- branch: main
- remote: https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git
- remote_read_ok: True
- remote_push_ok: True
- deploy_strategy: manual
- deploy_reason: no standard deployment marker detected
- deploy_commands:
  - add project-specific deploy command
  - verify health and rollback strategy
  - bash scripts/hardflow/hardflow-run.sh deploy

## Apply Result
- bootstrap_ok: True
- bootstrap_report_json: .tmp\oc3\ops\task-center\workflow-setup\bootstrap-report.json
- bootstrap_report_md: .tmp\oc3\ops\task-center\workflow-setup\bootstrap-report.md
- install_job: skipped
- cron_setup_ok: False
- cron_setup_note: script/path validation failed: runner_py_missing:.tmp\oc3\ops\ops_cron_runner.py, conversation_evolution_py_missing:C:\Users\superma\.openclaw\ops\conversation_evolution_runner.py; fix paths or pass --skip-script-path-check
- cron_audit_before: compliant=0,drifted=0,missing=0
- cron_audit_after: compliant=0,drifted=0,missing=0
- memory_restore: skipped

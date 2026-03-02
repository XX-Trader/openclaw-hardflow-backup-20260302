# OpenClaw Workflow Init Report

- generated_at: 2026-03-02T15:59:43+00:00
- openclaw_home: .tmp\openclaw-home
- strict_git_remote: False
- dry_run: True
- project_count: 1
- openclaw_selection: cli-arg
- openclaw_detect_ok: True
- openclaw_detect_count: 6
- openclaw_detect_valid_count: 1
- sync_ok: True
- sync_dry_run: True
- sync_added: 37
- sync_updated: 0
- sync_deleted: 0

## openclaw-hardflow-backup-20260302
- path: D:\学习资料\量化交易\openclaw-hardflow-backup-20260302
- writable: True (ok)
- git_repo: True
- branch: main
- remote: https://github.com/XX-Trader/openclaw-hardflow-backup-20260302.git
- remote_read_ok: False
- remote_push_ok: False
- deploy_strategy: manual
- deploy_reason: no standard deployment marker detected
- deploy_commands:
  - add project-specific deploy command
  - verify health and rollback strategy
  - bash scripts/hardflow/hardflow-run.sh deploy
- hints:
  - Git remote read failed: check SSH key/token/network.
  - Git push dry-run failed: verify write permission/deploy key.

## Apply Result
- bootstrap: skipped
- install_job: skipped
- cron_setup: skipped

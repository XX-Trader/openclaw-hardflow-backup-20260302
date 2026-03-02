# OpenClaw TODO Patrol Sync

This folder provides a standardized way to sync and install the
`TODO 巡检（15分钟）` job across multiple OpenClaw servers.

## Files

- `todo_patrol.py`
  - Reads coordinator TODO and execution board.
  - Requests assignment only for `UNASSIGNED`.
  - Merges tester failures into TODO with de-dup.
- `install_todo_patrol_job.py`
  - Upserts the todo-patrol job in `~/.openclaw/cron/jobs.json`.
  - Reuses existing `ops-agent` delivery target automatically.
- `sync_todo_patrol_to_servers.sh`
  - Uploads the two files to remote `~/.openclaw/workspace-ops-agent/ops/`.
  - Installs/updates the job on each server.
  - Runs a remote `--dry-run` smoke check.

## One-click sync

```bash
bash scripts/openclaw-ops/sync_todo_patrol_to_servers.sh
```

Optional targets:

```bash
bash scripts/openclaw-ops/sync_todo_patrol_to_servers.sh pm-website coingod
```

Optional env:

```bash
SSH_CONFIG=/mnt/d/学习资料/ssh_keys/ssh_config \
TODO_PATROL_EVERY_MS=900000 \
TODO_PATROL_DELIVERY_TO=-1003333097130 \
bash scripts/openclaw-ops/sync_todo_patrol_to_servers.sh
```

Dry run (no remote changes):

```bash
DRY_RUN=1 bash scripts/openclaw-ops/sync_todo_patrol_to_servers.sh
```

## Notes

- Default remote script path:
  `~/.openclaw/workspace-ops-agent/ops/todo_patrol.py`
- Default job id:
  `16cb8d03-beb9-4697-927d-35952353bf8e`
- The installer writes backup:
  `~/.openclaw/cron/jobs.json.bak.YYYYmmdd_HHMMSS`

## Policy Enforcer Sync

Use these scripts to deploy fail-close policy controls:

- `sync_policy_enforcer_to_servers.sh`
- `sync_policy_enforcer_to_servers.ps1`

They upload:

1. `scripts/openclaw-ops/policy/*`
2. hooks `hardflow-policy-enforcer` and `hardflow-command-guard`

And then initialize:

1. task-center sqlite database
2. policy/routing/pricing files
3. OpenClaw hook entries and extraDirs

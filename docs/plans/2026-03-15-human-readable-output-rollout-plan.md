# Human-Readable Output Rollout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将所有核心人类可见输出统一为“任务 / 要求 / 状态 / 失败信息 / 执行概况 / 值得做”风格，并发布到所有已安装且正在运行 OpenClaw 的服务器上，逐台验证通过。

**Architecture:** 只改展示层，不改任务中心和策略存储协议。优先复用 `chat_output.py`、`workflow_views.py`、各 runner 的 `build_chat_output` / human view 入口；失败指标统一从 `tasks` + 最新 `agent_task_reports` 聚合，正常任务保持精简。发布时复用仓库已有 `sync_openclaw_ops_files.py`、`install_workflow_profile.py` 和远程 shell 包装脚本。

**Tech Stack:** Python 3, SQLite, OpenClaw cron/profile installer, Git, SSH shell wrappers, tmux remote helpers.

---

### Task 1: Freeze Scope And Output Contract

**Files:**
- Modify: `scripts/openclaw-ops/README.md`
- Modify: `docs/plans/2026-03-15-human-readable-output-rollout-plan.md`

**Step 1: Write the failing test**

Add one summary-scope test checklist to identify every human-facing entry that should adopt the new contract.

**Step 2: Run test to verify it fails**

Run: not applicable for this documentation-only task
Expected: manual review shows missing scope list

**Step 3: Write minimal implementation**

Document rollout scope:
- `daily_work_report.py`
- `daily_todo_digest.py`
- `ops_cron_runner.py`
- `system_schedule_snapshot.py`
- `api_test_audit.py`
- `policy/task_executor_runner.py`
- `reviewer_cron_runner.py`
- `workflow_views.py`
- `web_intel_collect_runner.py`
- `web_intel_review_runner.py`
- `conversation_evolution_runner.py`
- `governance_evolution_runner.py`
- `github_web_evolution_runner.py`
- `self_evolution_todo.py`
- `todo_patrol.py`

**Step 4: Run test to verify it passes**

Run: manual check of plan + README
Expected: scope list exists and excludes non-human internal-only scripts

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/README.md docs/plans/2026-03-15-human-readable-output-rollout-plan.md
git commit -m "docs: define human-readable output rollout scope"
```

### Task 2: Build Shared Output Formatter Helpers

**Files:**
- Modify: `scripts/openclaw-ops/daily_work_report.py`
- Modify: `scripts/openclaw-ops/chat_output.py`
- Test: `tests/scripts_openclaw_ops/test_daily_work_report_quiet_modes.py`
- Test: `scripts/openclaw-ops/tests/test_human_output_format.py`

**Step 1: Write the failing test**

Add tests proving the shared format can render:
- task
- requirement
- status
- failure info
- execution metrics
- why it matters

**Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_work_report_quiet_modes.py scripts/openclaw-ops/tests/test_human_output_format.py -q`
Expected: FAIL because shared formatter/helpers do not cover all fields consistently

**Step 3: Write minimal implementation**

Extract and stabilize helpers for:
- status humanization
- failure reason condensation
- duration/token/cost formatting
- safe model display
- “why worth doing” text selection

**Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_work_report_quiet_modes.py scripts/openclaw-ops/tests/test_human_output_format.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/daily_work_report.py scripts/openclaw-ops/chat_output.py tests/scripts_openclaw_ops/test_daily_work_report_quiet_modes.py scripts/openclaw-ops/tests/test_human_output_format.py
git commit -m "feat: add shared human-readable task summary helpers"
```

### Task 3: Migrate Core Chat Outputs

**Files:**
- Modify: `scripts/openclaw-ops/daily_todo_digest.py`
- Modify: `scripts/openclaw-ops/ops_cron_runner.py`
- Modify: `scripts/openclaw-ops/system_schedule_snapshot.py`
- Modify: `scripts/openclaw-ops/api_test_audit.py`
- Test: `tests/scripts_openclaw_ops/test_daily_todo_digest_output.py`
- Test: `tests/scripts_openclaw_ops/test_cron_quiet_modes.py`

**Step 1: Write the failing test**

For each entrypoint, add at least one test asserting:
- no raw task id-only summaries for key tasks
- failures include condensed reason/count/duration when available
- no raw path / json / stack leaks

**Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_todo_digest_output.py tests/scripts_openclaw_ops/test_cron_quiet_modes.py -q`
Expected: FAIL in outputs still using mechanical summaries

**Step 3: Write minimal implementation**

Apply the shared formatter to these core chat outputs.

**Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_todo_digest_output.py tests/scripts_openclaw_ops/test_cron_quiet_modes.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/daily_todo_digest.py scripts/openclaw-ops/ops_cron_runner.py scripts/openclaw-ops/system_schedule_snapshot.py scripts/openclaw-ops/api_test_audit.py tests/scripts_openclaw_ops/test_daily_todo_digest_output.py tests/scripts_openclaw_ops/test_cron_quiet_modes.py
git commit -m "feat: humanize core ops chat outputs"
```

### Task 4: Migrate Executor And Human Views

**Files:**
- Modify: `scripts/openclaw-ops/policy/task_executor_runner.py`
- Modify: `scripts/openclaw-ops/workflow_views.py`
- Modify: `scripts/openclaw-ops/reviewer_cron_runner.py`
- Test: `tests/scripts_openclaw_ops/test_workflow_views.py`
- Test: `tests/scripts_openclaw_ops/test_task_executor_output_contract.py`

**Step 1: Write the failing test**

Add tests for failed/skipped/executed tasks showing readable task purpose and execution metrics without internal path noise.

**Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_workflow_views.py tests/scripts_openclaw_ops/test_task_executor_output_contract.py -q`
Expected: FAIL where outputs still center on IDs or raw reason codes

**Step 3: Write minimal implementation**

Adopt the shared formatter for executor and human-view rendering.

**Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/scripts_openclaw_ops/test_workflow_views.py tests/scripts_openclaw_ops/test_task_executor_output_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/policy/task_executor_runner.py scripts/openclaw-ops/workflow_views.py scripts/openclaw-ops/reviewer_cron_runner.py tests/scripts_openclaw_ops/test_workflow_views.py tests/scripts_openclaw_ops/test_task_executor_output_contract.py
git commit -m "feat: humanize executor and human-view summaries"
```

### Task 5: Migrate Secondary Human-Facing Runners

**Files:**
- Modify: `scripts/openclaw-ops/web_intel_collect_runner.py`
- Modify: `scripts/openclaw-ops/web_intel_review_runner.py`
- Modify: `scripts/openclaw-ops/conversation_evolution_runner.py`
- Modify: `scripts/openclaw-ops/governance_evolution_runner.py`
- Modify: `scripts/openclaw-ops/github_web_evolution_runner.py`
- Modify: `scripts/openclaw-ops/self_evolution_todo.py`
- Modify: `scripts/openclaw-ops/todo_patrol.py`
- Relevant tests under `tests/scripts_openclaw_ops/`

**Step 1: Write the failing test**

Add one focused failing test per runner for its main human-facing summary.

**Step 2: Run test to verify it fails**

Run: targeted `pytest` commands per updated module
Expected: FAIL on old summary shape

**Step 3: Write minimal implementation**

Replace local summary strings with shared style, keeping each module’s domain language.

**Step 4: Run test to verify it passes**

Run: targeted `pytest` commands per updated module
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/web_intel_collect_runner.py scripts/openclaw-ops/web_intel_review_runner.py scripts/openclaw-ops/conversation_evolution_runner.py scripts/openclaw-ops/governance_evolution_runner.py scripts/openclaw-ops/github_web_evolution_runner.py scripts/openclaw-ops/self_evolution_todo.py scripts/openclaw-ops/todo_patrol.py tests/scripts_openclaw_ops/
git commit -m "feat: humanize secondary runner summaries"
```

### Task 6: Full Local Verification

**Files:**
- Modify: `scripts/openclaw-ops/README.md`
- Modify: `todo.md`
- Modify: `done.md`

**Step 1: Write the failing test**

Create a verification checklist covering all updated test suites.

**Step 2: Run test to verify it fails**

Run:
- `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_work_report_quiet_modes.py -q`
- `py -3 -m pytest tests/scripts_openclaw_ops/test_daily_todo_digest_output.py -q`
- `py -3 -m pytest tests/scripts_openclaw_ops/test_cron_quiet_modes.py -q`
- `py -3 -m pytest tests/scripts_openclaw_ops/test_workflow_views.py -q`
- `py -3 -m pytest tests/scripts_openclaw_ops/test_task_executor_output_contract.py -q`
Expected: any regression blocks rollout

**Step 3: Write minimal implementation**

Fix regressions and sync docs/changelog-style task records.

**Step 4: Run test to verify it passes**

Run the same commands plus a combined smoke run if practical.
Expected: all PASS

**Step 5: Commit**

```bash
git add scripts/openclaw-ops/README.md todo.md done.md
git commit -m "docs: record human-readable output rollout verification"
```

### Task 7: Push Code To Git

**Files:**
- No source changes required

**Step 1: Write the failing test**

Verify working tree is clean enough for a controlled push.

**Step 2: Run test to verify it fails**

Run:
- `git status --short`
- `git log --oneline -n 5`
Expected: no unresolved rollout edits

**Step 3: Write minimal implementation**

Push rollout commits to the intended remote branch.

**Step 4: Run test to verify it passes**

Run:
- `git push origin main`
- `git rev-parse HEAD`
Expected: push success, HEAD on remote branch

**Step 5: Commit**

No commit in this task; push only.

### Task 8: Deploy To OpenClaw Servers

**Files:**
- Modify if needed: `D:/ssh_keys/tmp-*-sync-and-install.sh`
- Reuse: `scripts/openclaw-ops/sync_openclaw_ops_files.py`
- Reuse: `scripts/openclaw-ops/install_workflow_profile.py`

**Step 1: Write the failing test**

Document exact deployment targets:
- `pm-website`
- `大白pm`
- `nofx`
- `coingod`
- `tokyo-claw`

**Step 2: Run test to verify it fails**

Run remote preflight per server:
- repo dir exists
- `~/.openclaw` exists
- `openclaw cron status --json` returns

Expected: any missing runtime blocks that server rollout

**Step 3: Write minimal implementation**

Per server:
1. upload/pull latest repo
2. sync `scripts/openclaw-ops` into `~/.openclaw/ops`
3. run `install_workflow_profile.py --profile core`
4. keep existing delivery target intact unless a server-specific installer requires override

**Step 4: Run test to verify it passes**

Run existing remote scripts or equivalent:
- sync result JSON
- install result JSON
- `openclaw cron status --json`
- repo `HEAD`

Expected: sync/install success on each server

**Step 5: Commit**

No commit in this task; deployment only.

### Task 9: Verify Every Server After Install

**Files:**
- Reuse: `D:/ssh_keys/tmp-verify-dabai.sh`
- Reuse: `D:/ssh_keys/tmp-verify-coingod-post.sh`
- Reuse: `D:/ssh_keys/tmp-verify-nofx-post.sh`
- Reuse: `D:/ssh_keys/tmp-verify-tokyo-post.sh`
- Add/modify missing verification helper for `pm-website`

**Step 1: Write the failing test**

Define per-server acceptance:
- repo HEAD matches pushed commit
- required cron jobs exist
- OpenClaw cron is enabled
- no install error in current run
- updated human-readable prompt snippets present in deployed files

**Step 2: Run test to verify it fails**

Run verification helper on each server.
Expected: any mismatch identifies the server and failing condition

**Step 3: Write minimal implementation**

Patch or add verification helper scripts for missing checks, especially `pm-website`.

**Step 4: Run test to verify it passes**

Run all per-server verification helpers and capture outputs into deployment notes.
Expected: all target servers PASS

**Step 5: Commit**

```bash
git add D:/ssh_keys/tmp-verify-*.sh
git commit -m "chore: add rollout verification helpers"
```

### Task 10: Final Rollout Report

**Files:**
- Create: `docs/2026-03-15-人类摘要输出统一改造与多机部署记录.md`
- Modify: `done.md`

**Step 1: Write the failing test**

Create a checklist template for final rollout evidence.

**Step 2: Run test to verify it fails**

Manual review shows missing per-server evidence table

**Step 3: Write minimal implementation**

Record:
- changed modules
- test commands and results
- pushed commit
- each server alias
- install result
- verification result
- residual risks

**Step 4: Run test to verify it passes**

Manual review confirms no missing server/evidence entry

**Step 5: Commit**

```bash
git add docs/2026-03-15-人类摘要输出统一改造与多机部署记录.md done.md
git commit -m "docs: record human-readable rollout deployment"
```

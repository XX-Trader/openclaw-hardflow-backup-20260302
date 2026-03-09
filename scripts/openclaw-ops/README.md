# OpenClaw Ops Scripts

这个目录用于维护 OpenClaw 工作流、定时任务和运维巡检脚本。

所有自动消息输出与运行记录统一包含 `sender_identity` 字段，便于排查是谁发送、链路是否正常。

## TODO 巡检

- `todo_patrol.py`
  - 读取 coordinator 的 TODO 与执行看板。
  - 仅对 `UNASSIGNED` 项请求分配。
  - 自动合并 tester 失败项（去重）。
- `install_todo_patrol_job.py`
  - 安装/更新 `TODO 巡检（15分钟）` 到 `~/.openclaw/cron/jobs.json`。

## Web Intel

- `web_intel_collect_runner.py`
  - HTTP 优先，浏览器兜底支持 `playwright -> selenium`。
  - 会识别 `403/429/503` 与 `Cloudflare/captcha/turnstile/checking your browser` 反爬页面。
  - 采集失败不再只聊天告警，会自动写入 task-center 修复任务，后续由 `task_executor_runner.py` 消费。
- `web_intel_review_runner.py`
  - 对解析后的网页情报做 optimization/project-doc 两种复核。
  - 发现变化后会自动打包 follow-up 任务到 task-center，而不是只输出摘要。
- `install_web_intel_jobs.py`
  - 安装 web-intel cron 时会显式带上 `--db ~/.openclaw/ops/task-center/task_center.db`，接入统一闭环。

## Cron 工作流

- `ops_cron_runner.py`
  - 统一执行 `incremental/full/daily` 三种模式。
  - 记录增量读取位置（checkpoint）、问题次数、open/resolved/reopened 状态。
  - 增量异常可自动回退全量扫描。
  - 对失败工作流不再只写 `TODO.md`；会同时自动派生指派给 `optimization-agent` 的 `task-center` 修复任务，后续由 `task_executor_runner.py` 消费。
  - 支持每个技能日志开关：`silent`（静默）/`chat`（发聊天）。
  - 高风险始终提醒，不受普通日志开关影响。
- `cron_setup.py`
  - 一键安装 OpenClaw cron jobs（增量监控/全量校准/每日日报）。
  - 可选安装系统定时审计 job（系统 cron + systemd timer + openclaw jobs）。
  - 自动推断 delivery channel/to。
  - 内部维护型 job 默认走官方 `delivery.mode=none`，避免 isolated run 文本直接投递到聊天框；执行失败则保留 `failureAlert` 通道。
  - 自动写入 `~/.openclaw/ops/cron-monitor-config.json` 的技能日志开关。
- `system_schedule_snapshot.py`
  - 采集系统定时与 OpenClaw 定时快照。
  - 对比历史状态，识别变更与高风险项。
  - 输出 `NO_REPLY` 或告警摘要（附证据路径）。
- `api_test_audit.py`
  - 接口巡检采用单次执行，不做重复重测循环。
  - 支持 `http/playwright/selenium` 模式（浏览器检查可用 playwright/selenium）。
  - 检查接口是否有返回值、必填字段、JSON 合法性、数据时效（旧数据自动高风险）。
  - 空返回值和旧数据都会归类为高风险并落盘证据。
- `daily_work_report.py`
  - 每日从任务中心提取 TODO/DONE。
  - 仅发送新增记录，不重复发送历史 TODO/DONE。
  - 支持钉钉 webhook 通知（无新增记录时输出 `NO_REPLY`）。
- `daily_todo_digest.py`
  - 每日 TODO/DONE 摘要（仅聊天输出，不做外部 webhook 推送）。
  - 用于替代历史 `workspace/scripts/daily_todo_digest.py` 的不稳定路径依赖。
- `experience_maintain.py`
  - 每日/每周/每月经验维护稳定执行器（纯 Python、无外部 Node 依赖）。
  - 自动维护 `workspace/MEMORY.md` 与 `workspace/memory/YYYY-MM-DD.md`。
- `self_evolution_todo.py`
  - 周度全量复盘历史任务/流程指标。
  - 只产出“建议与任务包”，禁止自动修改工作流与技能。
  - 任务统一写入 TODO（低优先级、高风险、需人工确认），并带 `scheduled_at`。
  - 按 FIFO 时间顺序入队，且每次运行限制最大产出数量，避免批量风险。
- `governance_evolution_runner.py`
  - 工作流仓库增量扫描（默认关注 `scripts/openclaw-ops/`、`hooks/`、`openclaw/`、`setup.py`）。
  - 支持通过 `openclaw.json + project-registry` 自动定位本地 git 仓库（`--repo-path` 可选）。
  - 扫描前可自动执行本地 git 更新（`--auto-git-update` + `--git-update-strategy`）。
  - 支持任务清晰度分流（`--task-clarity auto/clear/ambiguous`）。
  - 需求不明确时可启用 `project-agent` 前置上下文门（`--project-context-gate`）。
  - 自动创建 `optimization-agent` 优化任务，支持可选创建 `reviewer` 审查任务。
  - 可选自动 PR（需要 `gh auth` 与干净工作区），并输出报告与状态。
  - 默认排除记忆/会话文件（`openclaw-memory/`、`.workflow/experience/`、`.workflow/sessions/`、`memory/`、`MEMORY.md`）。
- `github_web_evolution_runner.py`
  - 定时搜索 GitHub 高质量仓库并沉淀到 `~/.openclaw/web/github/`。
  - 自动落盘仓库元数据、README、方法片段、运行报告与目录索引（`CATALOG.md`）。
  - 按增量变化打包 `github_web_evolution` TODO 任务，支持质量阈值、去重与分批建单。
  - 仅产出任务包，不直接执行高风险改动。
- `reviewer_cron_runner.py`
  - Reviewer 定时审查执行器，支持 `hourly_git / daily_incremental / bi_daily_recurring / weekly_structure` 四种模式。
  - 内置问题去重与生命周期：`open / resolved / reopened`。
  - 每次执行落盘历史证据，支持 `NO_REPLY` 降噪输出。
- `install_reviewer_scan_jobs.py`
  - 一键安装 Reviewer 四层审查任务（1小时、每日4点、每2天、每周）。
  - 自动推断 delivery channel/to 并写入 `~/.openclaw/cron/jobs.json`。

## 风险动态更新

- `policy/risk_rule_sync.py`
  - 支持聊天驱动的高低风险关键词更新。
  - 典型高风险：`api变更/参数变更/逻辑变更/流程变更/结构变更`。
  - 典型低风险：`代码bug/配置错误/网络失败/资源告警/重复进程`。

## Policy Enforcer 同步

- `sync_policy_enforcer_to_servers.sh`
- `sync_policy_enforcer_to_servers.ps1`

## 远程安全更新

- `remote_safe_update.py`
  - 远程检查或同步 `openclaw-hardflow-backup-20260302`
  - 默认排除 `google-us`
  - 支持三种冲突策略：`runtime-reset`、`stash-nonvolatile`、`snapshot-branch`
- `remote_safe_update.ps1`
- `remote_safe_update.sh`

## 常用命令

```bash
# 安装 cron 工作流（含系统定时审计技能）
python3 scripts/openclaw-ops/cron_setup.py \
  --install-system-schedule-job \
  --install-api-test-job \
  --api-test-engine playwright \
  --api-test-expr "*/15 * * * *" \
  --install-daily-work-job \
  --daily-work-expr "15 0 * * *" \
  --install-self-evolution-job \
  --self-evolution-expr "30 3 * * 1" \
  --self-evolution-lookback-days 30 \
  --self-evolution-min-interval-days 7 \
  --self-evolution-max-tasks-per-run 3 \
  --self-evolution-agent-score-threshold 70 \
  --self-evolution-agent-score-min-reports 3 \
  --self-evolution-agent-score-top-n 12 \
  --install-governance-evolution-job \
  --governance-evolution-openclaw-config ~/.openclaw/openclaw.json \
  --governance-evolution-project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --governance-evolution-repo-id openclaw-hardflow-backup-20260302 \
  --governance-evolution-auto-git-update \
  --governance-evolution-git-update-strategy fetch \
  --governance-evolution-git-fetch-timeout 120 \
  --governance-evolution-every-ms 21600000 \
  --governance-evolution-log-mode silent \
  --governance-evolution-max-files 120 \
  --governance-evolution-min-interval-minutes 180 \
  --governance-evolution-task-clarity ambiguous \
  --governance-evolution-project-context-gate \
  --governance-evolution-project-context-assignee project-agent \
  --governance-evolution-create-review-task \
  --no-governance-evolution-auto-pr \
  --install-github-web-evolution-job \
  --github-web-evolution-openclaw-home ~/.openclaw \
  --github-web-evolution-web-root ~/.openclaw/web/github \
  --github-web-evolution-every-ms 43200000 \
  --github-web-evolution-min-interval-minutes 360 \
  --github-web-evolution-max-queries 5 \
  --github-web-evolution-max-repos-per-query 20 \
  --github-web-evolution-max-total-repos 40 \
  --github-web-evolution-min-stars 80 \
  --github-web-evolution-min-quality-score 45 \
  --github-web-evolution-min-new-or-updated 2 \
  --github-web-evolution-recent-dedupe-days 14 \
  --github-web-evolution-max-tasks-per-run 2 \
  --github-web-evolution-schedule-gap-minutes 90 \
  --github-web-evolution-assignee optimization-agent \
  --github-web-evolution-github-token-env GITHUB_TOKEN \
  --dingtalk-webhook-env DINGTALK_WEBHOOK_URL \
  --dingtalk-secret-env DINGTALK_SECRET \
  --incremental-log-mode silent \
  --full-log-mode silent \
  --daily-log-mode silent \
  --system-log-mode silent \
  --api-test-log-mode silent \
  --daily-work-log-mode silent \
  --self-evolution-log-mode silent \
  --github-web-evolution-log-mode silent

# 手动执行一次增量巡检
python3 scripts/openclaw-ops/ops_cron_runner.py --mode incremental

# 手动执行一次接口单次全量巡检
python3 scripts/openclaw-ops/api_test_audit.py \
  --config-file ~/.openclaw/ops/api-test-config.json \
  --engine playwright-real \
  --normal-log-mode silent

# 动态调整风险规则（示例）
python3 scripts/openclaw-ops/policy/risk_rule_sync.py batch \
  --apply-default-preset \
  --add-high "api契约升级" \
  --add-low "临时网络抖动"

# 先检查远程仓库冲突
python3 scripts/openclaw-ops/remote_safe_update.py --mode inspect

# 只清理运行态冲突再同步
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy runtime-reset

# 非运行态改动先 stash 再同步
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy stash-nonvolatile

# 手动执行一次每日工作钉钉报告（仅新增 todo/done）
python3 scripts/openclaw-ops/daily_work_report.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --normal-log-mode silent

# 手动执行一次周度自我进化复盘（只产出 TODO 任务包）
python3 scripts/openclaw-ops/self_evolution_todo.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --lookback-days 30 \
  --min-review-interval-days 7 \
  --max-tasks-per-run 3 \
  --agent-score-threshold 70 \
  --agent-score-min-reports 3 \
  --agent-score-top-n 12 \
  --normal-log-mode silent

# 手动执行一次治理进化增量扫描（可选创建 reviewer 任务）
python3 scripts/openclaw-ops/governance_evolution_runner.py \
  --openclaw-config ~/.openclaw/openclaw.json \
  --project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --repo-id openclaw-hardflow-backup-20260302 \
  --auto-git-update \
  --git-update-strategy fetch \
  --git-fetch-timeout 120 \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --state-file ~/.openclaw/ops/governance-evolution/state.json \
  --report-dir ~/.openclaw/ops/governance-evolution/reports \
  --task-clarity ambiguous \
  --project-context-gate \
  --project-context-assignee project-agent \
  --create-review-task \
  --normal-log-mode silent

# 手动执行一次 GitHub 网络资源进化扫描（只沉淀 + 打包 TODO）
python3 scripts/openclaw-ops/github_web_evolution_runner.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --openclaw-home ~/.openclaw \
  --web-root ~/.openclaw/web/github \
  --state-file ~/.openclaw/ops/github-web-evolution/state.json \
  --report-dir ~/.openclaw/ops/github-web-evolution/reports \
  --min-interval-minutes 360 \
  --max-queries 5 \
  --max-repos-per-query 20 \
  --max-total-repos 40 \
  --min-stars 80 \
  --min-quality-score 45 \
  --min-new-or-updated 2 \
  --recent-dedupe-days 14 \
  --max-tasks-per-run 2 \
  --schedule-gap-minutes 90 \
  --assignee optimization-agent \
  --github-token-env GITHUB_TOKEN \
  --normal-log-mode silent

# 手动执行一次系统定时快照审计
python3 scripts/openclaw-ops/system_schedule_snapshot.py --normal-log-mode silent

# 安装 Reviewer 四层定时审查任务
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/reviewer_cron_runner.py \
  --workspace ~/.openclaw/workspace \
  --state-file ~/.openclaw/ops/reviewer-scan-state.json \
  --history-dir ~/.openclaw/ops/reviewer-scan-runs \
  --normal-log-mode silent \
  --daily-fix-command "python3 ~/.openclaw/ops/policy_enforcer.py next-todo --limit 5"
```

## New Docs

- Context gate and source split: scripts/openclaw-ops/policy/CONTEXT_GATE.md


## Reviewer Scheduler Update (2026-03-03)

`install_reviewer_scan_jobs.py` now supports hourly git fetch / PR scan / approved merge flow:

```bash
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/reviewer_cron_runner.py \
  --workspace ~/.openclaw/workspace \
  --state-file ~/.openclaw/ops/reviewer-scan-state.json \
  --history-dir ~/.openclaw/ops/reviewer-scan-runs \
  --normal-log-mode silent \
  --daily-fix-command "python3 ~/.openclaw/ops/policy_enforcer.py next-todo --limit 5" \
  --hourly-git-fetch \
  --hourly-check-pr \
  --no-hourly-allow-merge
```

To enable approved auto merge:

```bash
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  ... \
  --hourly-allow-merge \
  --hourly-merge-approval-file ~/.openclaw/ops/reviewer-merge-approval.json
```

`reviewer_cron_runner.py` modes:
- `hourly_git`: branch sync + PR check + optional approved merge
- `daily_incremental`: incremental scan + optional fix command
- `bi_daily_recurring`: recurring issue scan with dedupe
- `weekly_structure`: coupling/duplication/config/I-O contract audit
- built-in security heuristics: hardcoded secret / eval-exec / shell=True / verify=False / unsafe JS exec & DOM writes

## Guardrail Upgrades (2026-03-03)

1. `api_test_audit.py` now supports `playwright-real` engine.
2. `api_test_audit.py` supports browser `steps` for click/fill/press/wait E2E flows.
3. Browser checks always produce screenshots and mark `visual_review_mode=native_ai_vision`.
4. Config supports:
   - `forbid_http_engine=true` (block curl-only fake-pass checks)
   - `require_browser_checks=true`
   - `endpoint_engine=http` (API contract checks can stay HTTP while UI uses real browser)
   - `freshness_auto_detect=true` + `freshness_candidate_fields=[...]`
   - endpoint `freshness_required=true` to fail when no valid freshness timestamp is available
   - `real_browser.user_data_dir/profile_directory/channel/headless`
5. `init_api_test_config.py` now generates real-browser defaults and click-step templates.
6. `project_index_maintainer.py` now maintains runtime index artifacts under `.workflow/project-index-local/` by default:
   - `doc-knowledge.json`
   - `doc-search-index.json`
   - `DOC_KNOWLEDGE.md`
   - docs update-check state in `doc-knowledge-state.json`
   - direct-fetch cache under `doc-source-cache/*.txt`
   - `reviewer_cron_runner.py` prefers `project-index-local/project-index.json` and falls back to legacy `.workflow/project-index/project-index.json`
   - both `.workflow/project-index-local/` and `.workflow/project-index/` are runtime-only and should stay out of Git tracking
7. Browser checks now export DevTools-like evidence:
   - `history/devtools/<run>/check-id.json` includes console/network/xhr-fetch response excerpts
   - scoring fields: `min_score`, `require_api_output`, `api_expectations`, `expect_selectors`
   - high-risk output includes screenshot path + devtools log path for manual F12-style audit

## Memory Restore (2026-03-03)

- 新增脚本：`scripts/openclaw-ops/restore_openclaw_memory.py`
- 作用：把项目内记忆目录（默认 `openclaw-memory/`）复制恢复到 OpenClaw workspace。
- source 缺失不会直接失败，会在输出里给 warning（用于提醒“memory 尚未同步”）。

```bash
python3 scripts/openclaw-ops/restore_openclaw_memory.py \
  --project-root /path/to/project \
  --openclaw-home ~/.openclaw \
  --emit-json
```

## Cron Global Switch (2026-03-03)

- 新增脚本：`scripts/openclaw-ops/cron_switch.py`
- 用途：运行期一键暂停/恢复定时任务，减少 token 消耗与消息推送。

```bash
# 查看状态
python3 scripts/openclaw-ops/cron_switch.py status --emit-json

# 关闭全部定时任务
python3 scripts/openclaw-ops/cron_switch.py off --scope all --emit-json

# 恢复定时任务（默认只恢复由 switch 关闭的任务）
python3 scripts/openclaw-ops/cron_switch.py on --scope all --emit-json
```

## Reviewer Scan Scope (2026-03-03)

- `reviewer_cron_runner.py` 已排除记忆相关路径，不再审查这些文件：
  - `.workflow/experience/`
  - `.workflow/sessions/`
  - `openclaw-memory/`
  - `MEMORY.md`

## Reviewer Context Gate (2026-03-03)

- `reviewer_cron_runner.py` 在 `daily_incremental / bi_daily_recurring / weekly_structure` 模式下默认开启项目上下文门：
  - 审查前会先创建 `project-agent` 上下文任务（`reviewer_project_context_preflight`）。
  - 上下文未就绪时，reviewer 全量审查会被阻断并提示人工处理。
- 可通过参数关闭（不推荐）：`--no-project-context-gate`

## Conversation Evolution Channel (2026-03-03)

新增脚本：`scripts/openclaw-ops/conversation_evolution_runner.py`

作用：定时扫描近期对话/会话/记忆记录，提炼以下信号并打包为 TODO 任务：
- bug / 异常 / 失败线索
- 工作流与路由问题
- 未闭环事项（pending/todo/blocked）
- 优化机会（稳定性/成本/token）

`cron_setup.py` 新增参数：
- `--install-conversation-evolution-job`
- `--conversation-evolution-openclaw-home`
- `--conversation-evolution-every-ms`
- `--conversation-evolution-log-mode`
- `--conversation-evolution-lookback-hours`
- `--conversation-evolution-min-interval-minutes`
- `--conversation-evolution-max-files`
- `--conversation-evolution-max-tasks-per-run`
- `--conversation-evolution-schedule-gap-minutes`
- `--conversation-evolution-assignee`

示例（安装时开启该通道）：
```bash
python3 scripts/openclaw-ops/cron_setup.py \
  --install-conversation-evolution-job \
  --conversation-evolution-openclaw-home ~/.openclaw \
  --conversation-evolution-every-ms 21600000 \
  --conversation-evolution-lookback-hours 72 \
  --conversation-evolution-min-interval-minutes 180 \
  --conversation-evolution-max-files 120 \
  --conversation-evolution-max-tasks-per-run 3 \
  --conversation-evolution-schedule-gap-minutes 90 \
  --conversation-evolution-assignee optimization-agent
```

示例（手动执行一次）：
```bash
python3 scripts/openclaw-ops/conversation_evolution_runner.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --openclaw-home ~/.openclaw \
  --state-file ~/.openclaw/ops/conversation-evolution/state.json \
  --report-dir ~/.openclaw/ops/conversation-evolution/reports \
  --lookback-hours 72 \
  --min-interval-minutes 180 \
  --max-files 120 \
  --max-tasks-per-run 3 \
  --assignee optimization-agent \
  --normal-log-mode silent
```

## Conversation Evolution Quality Gate (2026-03-03)

为减少“低质量建议/重复建议/需求漂移”，`conversation_evolution_runner.py` 已增加硬门禁：

- 质量门禁：候选建议必须同时满足
  - `min_evidence_lines`
  - `min_unique_files`
  - `min_quality_score`
- 去重门禁：写入 `[dedupe_key:...]`，并按 `recent_dedupe_days` 防止短期重复创建同类 TODO。

`cron_setup.py` 新增参数：

- `--conversation-evolution-max-evidence-per-candidate` (default: `24`)
- `--conversation-evolution-min-evidence-lines` (default: `3`)
- `--conversation-evolution-min-unique-files` (default: `1`)
- `--conversation-evolution-min-quality-score` (default: `55`)
- `--conversation-evolution-recent-dedupe-days` (default: `14`)

示例（更严格）：

```bash
python3 scripts/openclaw-ops/cron_setup.py \
  --install-conversation-evolution-job \
  --conversation-evolution-openclaw-home ~/.openclaw \
  --conversation-evolution-lookback-hours 72 \
  --conversation-evolution-min-interval-minutes 180 \
  --conversation-evolution-max-files 120 \
  --conversation-evolution-max-evidence-per-candidate 30 \
  --conversation-evolution-min-evidence-lines 4 \
  --conversation-evolution-min-unique-files 2 \
  --conversation-evolution-min-quality-score 65 \
  --conversation-evolution-recent-dedupe-days 21 \
  --conversation-evolution-max-tasks-per-run 3 \
  --conversation-evolution-assignee optimization-agent
```

## GitHub Web Evolution Channel (2026-03-04)

新增脚本：`scripts/openclaw-ops/github_web_evolution_runner.py`

用途：定时从 GitHub 搜索与你工作流相关的高信号仓库，沉淀知识并触发“人工审核后再优化”的任务链路。

落盘目录（默认）：
- `~/.openclaw/web/github/repos/*.json`：仓库元数据
- `~/.openclaw/web/github/readmes/*.md`：README 原文快照
- `~/.openclaw/web/github/methods/*.md`：抽取的方法片段
- `~/.openclaw/web/github/runs/<timestamp_runid>/`：单次运行明细
- `~/.openclaw/web/github/index.json` / `CATALOG.md`：累计索引与目录

任务策略：
- 只对新增/更新仓库建 TODO（`task_type=github_web_evolution`）。
- 默认 `source=github-web-evolution-agent`，`need_human_confirm=true`。
- 去重维度：`fingerprint` + `dedupe_key`，避免短期重复建单。
- 支持 `max_tasks_per_run` 分批建单；单批仍受 `min_new_or_updated` 门槛控制。

`cron_setup.py` 新增参数：
- `--install-github-web-evolution-job`
- `--github-web-evolution-openclaw-home`
- `--github-web-evolution-web-root`
- `--github-web-evolution-every-ms`
- `--github-web-evolution-log-mode`
- `--github-web-evolution-min-interval-minutes`
- `--github-web-evolution-max-queries`
- `--github-web-evolution-max-repos-per-query`
- `--github-web-evolution-max-total-repos`
- `--github-web-evolution-min-stars`
- `--github-web-evolution-min-quality-score`
- `--github-web-evolution-min-new-or-updated`
- `--github-web-evolution-recent-dedupe-days`
- `--github-web-evolution-max-tasks-per-run`
- `--github-web-evolution-schedule-gap-minutes`
- `--github-web-evolution-assignee`
- `--github-web-evolution-github-token-env`

建议：
- 设置环境变量 `GITHUB_TOKEN` 提升 GitHub API 速率上限。
- 网络侧建议默认“先沉淀再审核”，不要直接自动改代码。

## Cron/Reviewer 安装策略更新（2026-03-04）

### 1) `cron_setup.py` 新增安装策略与去重治理

- `--install-profile {legacy,minimal,standard,aggressive}`
  - `legacy`：保持历史行为（默认）
  - `minimal`：降频并优先启用本仓库进化主链（自进化 + 治理进化，条件满足时）
  - `standard`：在 `minimal` 基础上可启用对话进化
  - `aggressive`：尽量启用全部进化任务（前提路径可用）
- `--legacy-optimize-jobs-mode {auto,keep,disable,remove}`
  - 默认 `auto`：`legacy` 保留，其他 profile 自动禁用旧 `optimize_*` 任务
- `--daily-report-dedupe-mode {auto,keep,disable-digest,disable-daily-work}`
  - 默认 `auto`：非 `legacy` 且检测到日总结任务时，自动禁用 `daily_todo_digest`，避免重复提醒

### 2) `cron_setup.py` 默认进化脚本路径优先级

以下参数默认优先使用当前仓库 `scripts/openclaw-ops/` 下脚本，缺失时回退到 `~/.openclaw/ops/`：

- `--self-evolution-py`
- `--conversation-evolution-py`
- `--governance-evolution-py`
- `--github-web-evolution-py`

### 3) `install_reviewer_scan_jobs.py` 新增 reviewer profile

- `--reviewer-profile {legacy,minimal,standard,aggressive}`（默认 `legacy`）
- 新增可调度参数：
  - `--hourly-every-ms`
  - `--daily-expr`
  - `--bi-daily-expr`
  - `--weekly-expr`
  - `--enable-hourly/--no-enable-hourly`
  - `--enable-daily/--no-enable-daily`
  - `--enable-bi-daily/--no-enable-bi-daily`
  - `--enable-weekly/--no-enable-weekly`
- `minimal` 默认关闭 bi-daily 并降低 hourly 频率，减少定时任务噪音。

## 本地 OpenClaw Git 备份（仅本地提交，不推远程）

新增脚本：
- `scripts/openclaw-ops/local_git_backup_runner.py`
- `scripts/openclaw-ops/install_local_openclaw_backup_job.py`

用途：
- 将 `~/.openclaw` 作为本地 git 仓库维护。
- 定时执行 `git add/commit`，不执行任何 `push`。
- 默认过滤高频日志与会话目录，避免仓库膨胀过快。

安装定时任务：

```bash
python3 scripts/openclaw-ops/install_local_openclaw_backup_job.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/local_git_backup_runner.py \
  --openclaw-home ~/.openclaw \
  --every-ms 3600000
```

手动执行一次（用于首轮初始化）：

```bash
python3 scripts/openclaw-ops/local_git_backup_runner.py \
  --repo-path ~/.openclaw \
  --task-id manual:openclaw-local-backup \
  --normal-log-mode silent
```

## Upstream Runtime Boundary (2026-03-06)

- `install_workflow_profile.py` 现在会把仓库 overlay 配置合并到 `~/.openclaw/openclaw.json`，并把仓库 `hooks/`、`skills/` 动态注入官方 loader。
- `uninstall_workflow_profile.py` 按“精确删除已知安装产物”的方式卸载 runtime workflow，只清理受安装器管理的 cron jobs、runtime bridge 注入项和 `ops` manifest 文件。
- `sync_openclaw_ops_files.py` 的职责明确为 `ops-only`，不再负责 hooks runtime 同步。
- `cron_setup.py`、`install_project_index_job.py`、`install_reviewer_scan_jobs.py`、`install_task_executor_job.py` 会显式输出官方 `openclaw cron` 验证命令；业务定义仍保留在 `jobs.json`。
- Python 治理逻辑继续留在 `scripts/openclaw-ops/policy/*`，通过官方 cron/hooks/webhook surface 触发。

桥接文档：

- `integration/openclaw-bridge/runtime-boundary.md`
- `integration/openclaw-bridge/hooks-install.md`
- `integration/openclaw-bridge/governance-bridge.md`
- `integration/openclaw-bridge/plugin-policy.md`

## Cron Quiet Defaults (2026-03-06)

- `install_task_executor_job.py` 现在默认写入 `--notify-on error`，不再让 `task_executor_runner.py` 的常规 JSON 结果直接刷到群里。
- `task_executor_runner.py` 保留 `--emit-json` 机器输出模式；非 `--emit-json` 模式新增 `--notify-on {error,activity,always}`，静默成功时输出 `NO_REPLY`。
- `task_executor_runner.py` 遇到明确的模型限流/`429` 会做有限次退避重试；可用 `--agent-max-retries` 与 `--agent-retry-delay-sec` 调整。
- `task_executor_runner.py` 现在按 assignee 读取 `policy-config.json` 里的 `agent_model_overrides`，并按 `model_thinking_overrides` 对 Codex 显式使用 `xhigh`，其他模型统一走 `high`。
- cron 安装器写入的 scheduled-runner 提示词现在要求：首次只允许一个 `exec`；如果工具返回 `Command still running`，只能对同一 session 使用 `process poll/log` 等到进程退出，禁止再开第二个 `exec`，避免后台悬挂命令继续占用 `task_center.db`。
- `install_project_index_job.py` 安装的 cron 任务默认不再追加 `--git-pull`。仓库拉取由 `ops_auto_update_install_hourly` 统一负责；如需人工排障，可显式传 `--git-pull`。
- `web_intel_collect_runner.py` 与 `web_intel_review_runner.py` 新增 `--notify-on`，可选 `error/change/always`。
- `install_web_intel_jobs.py` 新增 `--collect-notify-on` 与 `--review-notify-on`，在只想保留异常告警时传 `error`。
- `integration/openclaw-bridge/acceptance-checklist.md`

推荐验证命令：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path . --dry-run --emit-json
python scripts/openclaw-ops/uninstall_workflow_profile.py --profile all --workflow-repo-path . --dry-run --emit-json
openclaw hooks list --json
openclaw hooks check --json
openclaw plugins list
openclaw config get channels.telegram
```

如果要验证官方 cron surface，请先运行：

```bash
openclaw gateway run
```

## Scrapling Integration Update (2026-03-07)

- `web_intel_collect_runner.py` now uses browser fallback in this order: `scrapling-stealth -> playwright -> selenium`.
- `api_test_audit.py` now supports `http/playwright/playwright-real/selenium/scrapling/scrapling-stealth`.
- `scrapling` is treated as an optional dependency for anti-bot and lightweight browser fetching. If it is unavailable, the workflow still falls back to Playwright/Selenium instead of failing the whole job.
- To enable the new path explicitly, install `scrapling` in the runtime environment: `pip install scrapling`.
- `github_web_evolution_runner.py` now keeps the search scope on project-relevant third-party repositories and libraries, and excludes infrastructure repositories such as `python/cpython`, `nodejs/node`, `golang/go`, and similar runtime/compiler foundations.
- Repositories such as `microsoft/playwright`, `D4Vinci/Scrapling`, and your own project-related third-party dependencies remain in scope.

## Project Doc And Skill Evolution Update (2026-03-09)

- `web_intel_collect_runner.py` now merges three source layers at runtime:
  - `web/sources.json`
  - `web/project_docs_sources.json`
  - `project-registry.json` dynamic `doc_sources`, vendor hints, and per-project `doc-knowledge.json`
- `project-registry.json` now supports a top-level `discovery` block. If enabled, runtime will auto-discover additional local git projects under configured scan roots and merge them with explicit registry entries, while skipping internal repos such as `.openclaw/skills` and runner worktrees.
- Auto-discovered and explicit projects are normalized with a `project_role` plus `vendor_monitoring.enabled`. Only `business` projects participate in vendor doc / repo monitoring by default; `workflow-ops`, `openclaw-runtime`, and upstream reference repos stay indexed but do not trigger vendor scans unless explicitly overridden.
- `project_index_maintainer.py` now extracts external API URLs from actual project source files and writes vendor-aware `doc_sources` plus `repo_sources` into `.workflow/project-index-local/doc-knowledge.json`.
- `project-registry.example.json` now documents `doc_sources` and `integrations`. If a project declares `binance`, runtime sources automatically include official Binance Spot API docs and changelog. If the code itself contains `https://api.binance.com/...`, the project index will infer the same vendor sources automatically even without manual `doc_sources`.
- `github_web_evolution_runner.py` default queries now prioritize `openclaw` / `skills` / `hooks` / `plugins` / `workflow` instead of generic OpenAI-adjacent terms.
- `github_web_evolution_runner.py` now also reads project-derived `repo_sources`, appends vendor repo queries, and directly scans official repositories such as Binance connectors/docs repos.
- If `skill4agent` exists in PATH, `github_web_evolution_runner.py` will additionally search skill catalogs and fold new/updated skills into the same evolution report/catalog/task packaging flow.
- Runtime install command for the optional provider:

```bash
npm install -g @skill4agent/cli
```

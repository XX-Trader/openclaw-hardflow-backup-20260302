# OpenClaw Setup/Init 增强说明

本次增强把 `workflow_setup.py` 和 `cron_setup.py` 升级为“先检测、再同步、再审计纠偏”流程。

## 1. 新增能力

1. OpenClaw 安装探测  
脚本：`scripts/openclaw-ops/detect_openclaw_installations.py`  
输出：安装路径、版本、marker 完整性、jobs 数量、推荐目标。

2. OpenClaw ops 文件同步  
脚本：`scripts/openclaw-ops/sync_openclaw_ops_files.py`  
输出：`added/updated/deleted/moved` 清单 + manifest。

3. Cron 任务审计与纠偏  
脚本：`scripts/openclaw-ops/cron_setup.py`  
输出：`audit.before` 与 `audit.after`（`compliant/drifted/missing` 统计）。

4. Workflow 一体化安装  
脚本：`scripts/openclaw-ops/policy/workflow_setup.py`  
流程：探测 OpenClaw -> 选择目标 -> 同步脚本 -> bootstrap -> cron setup（含审计）。

## 2. 常用命令

```bash
# 1) 探测 openclaw 安装
python scripts/openclaw-ops/detect_openclaw_installations.py --emit-json

# 2) 预演同步（不落地）
python scripts/openclaw-ops/sync_openclaw_ops_files.py \
  --source-dir scripts/openclaw-ops \
  --target-ops-dir ~/.openclaw/ops \
  --dry-run \
  --emit-json

# 2.1) 初始化 API 测试配置（避免默认 example.com 噪音）
python scripts/openclaw-ops/init_api_test_config.py \
  --output-file ~/.openclaw/ops/api-test-config.json \
  --base-url http://127.0.0.1:8845 \
  --emit-json

# 2.2) 配置 runtime.env（命令化设置钉钉与其他变量）
python scripts/openclaw-ops/configure_runtime_env.py \
  --env-file ~/.openclaw/ops/runtime.env \
  --dingtalk-webhook-url "<your-webhook>" \
  --dingtalk-secret "<your-secret>" \
  --set OPENCLAW_ENV=prod \
  --emit-json

# 3) 仅执行 cron 审计+纠偏（不落地）
python scripts/openclaw-ops/cron_setup.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --channel telegram \
  --to <target> \
  --dry-run \
  --emit-json

# 4) 一体化 setup（可直接落地）
python scripts/openclaw-ops/policy/workflow_setup.py init \
  --openclaw-home ~/.openclaw \
  --scan-root . \
  --install-cron-setup \
  --cron-install-github-web-evolution-job \
  --cron-github-web-evolution-openclaw-home ~/.openclaw \
  --cron-github-web-evolution-web-root ~/.openclaw/web/github \
  --cron-github-web-evolution-every-ms 43200000 \
  --cron-github-web-evolution-min-interval-minutes 360 \
  --cron-github-web-evolution-min-stars 80 \
  --cron-github-web-evolution-min-quality-score 45 \
  --cron-github-web-evolution-min-new-or-updated 2 \
  --cron-github-web-evolution-recent-dedupe-days 14 \
  --cron-github-web-evolution-max-tasks-per-run 2 \
  --cron-github-web-evolution-assignee optimization-agent \
  --cron-github-web-evolution-github-token-env GITHUB_TOKEN \
  --cron-channel telegram \
  --cron-to <target> \
  --emit-json

# 5) 校验 jobs payload 里的脚本路径是否存在
python scripts/openclaw-ops/verify_job_payload_paths.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --strict \
  --emit-json
```

## 3. workflow_setup 新参数

- `--skip-openclaw-detect`
- `--openclaw-detect-scan-root`
- `--openclaw-detect-max-depth`
- `--openclaw-detect-max-results`
- `--skip-ops-sync`
- `--sync-source-dir`
- `--sync-manifest-file`
- `--sync-keep-stale-files`
- `--allow-nonstandard-sync-source`
- `--skip-init-api-test-config`
- `--api-test-config-file`
- `--api-test-base-url`
- `--configure-runtime-env`
- `--runtime-env-file`
- `--dingtalk-webhook-url`
- `--dingtalk-secret`
- `--set-runtime-env`
- `--skip-job-path-verify`
- `--skip-memory-restore`
- `--memory-restore-check-only`
- `--memory-source-dirname`
- `--memory-workspace`
- `--disable-memory-legacy-source`
- `--cron-install-governance-evolution-job`
- `--cron-governance-evolution-repo-path`
- `--cron-governance-evolution-openclaw-config`
- `--cron-governance-evolution-project-registry`
- `--cron-governance-evolution-repo-id`
- `--cron-governance-evolution-repo-name`
- `--cron-governance-evolution-auto-git-update / --no-cron-governance-evolution-auto-git-update`
- `--cron-governance-evolution-git-update-strategy`
- `--cron-governance-evolution-git-fetch-timeout`
- `--cron-governance-evolution-every-ms`
- `--cron-governance-evolution-log-mode`
- `--cron-governance-evolution-max-files`
- `--cron-governance-evolution-min-interval-minutes`
- `--cron-governance-evolution-task-clarity`
- `--cron-governance-evolution-project-context-gate / --no-cron-governance-evolution-project-context-gate`
- `--cron-governance-evolution-project-context-assignee`
- `--cron-governance-evolution-create-review-task / --no-cron-governance-evolution-create-review-task`
- `--cron-governance-evolution-auto-pr / --no-cron-governance-evolution-auto-pr`
- `--cron-governance-evolution-pr-base`
- `--cron-governance-evolution-reviewer-gh-user`
- `--cron-governance-evolution-push-before-pr / --no-cron-governance-evolution-push-before-pr`
- `--cron-install-github-web-evolution-job`
- `--cron-github-web-evolution-openclaw-home`
- `--cron-github-web-evolution-web-root`
- `--cron-github-web-evolution-every-ms`
- `--cron-github-web-evolution-log-mode`
- `--cron-github-web-evolution-min-interval-minutes`
- `--cron-github-web-evolution-max-queries`
- `--cron-github-web-evolution-max-repos-per-query`
- `--cron-github-web-evolution-max-total-repos`
- `--cron-github-web-evolution-min-stars`
- `--cron-github-web-evolution-min-quality-score`
- `--cron-github-web-evolution-min-new-or-updated`
- `--cron-github-web-evolution-recent-dedupe-days`
- `--cron-github-web-evolution-max-tasks-per-run`
- `--cron-github-web-evolution-schedule-gap-minutes`
- `--cron-github-web-evolution-assignee`
- `--cron-github-web-evolution-github-token-env`

## 4. 关键输出字段

- `openclaw_selection`: 目标选择来源（`cli-arg` / `interactive-select` / `detected-recommended` / `default`）
- `openclaw_detection`: 探测结果原始结构
- `ops_sync`: 文件同步结果（含新增、删除、移动）
- `install_cron_setup.detail.audit`: cron 审计前后对比

## 5. Memory Restore（2026-03-03）

- `workflow_setup.py` 现在默认执行项目记忆恢复（copy 模式）。
- 默认源目录：`<project>/openclaw-memory/`。
- 兼容旧目录：`<project>/.workflow/openclaw-memory/`（可通过 `--disable-memory-legacy-source` 关闭）。
- setup 输出新增 `memory_restore` 字段：
  - `warning_projects > 0` 代表存在“项目未同步记忆源目录”等待补齐。

## 6. Governance Evolution（2026-03-03）

- 新增可选 job：`ops_governance_evolution_incremental`（agent: `optimization-agent`）。
- 能力：
  - 增量扫描工作流仓库代码变更；
  - 自动创建 `optimization-agent` 优化任务；
  - 可选创建 `reviewer` 审查任务；
  - 可选自动 PR（需要 `gh auth`、本地工作区干净）。
- 默认排除记忆/会话路径，不会把记忆文件纳入进化审查。

## 7. Governance Git Sync（2026-03-03）
- 支持按 `openclaw.json + project-registry` 自动解析治理进化目标仓库（`repo-path` 可不填）。
- 支持扫描前自动更新本地 git：`--cron-governance-evolution-auto-git-update`。
- 支持更新策略：`--cron-governance-evolution-git-update-strategy fetch|pull-ff-only`。
- 支持 git 超时配置：`--cron-governance-evolution-git-fetch-timeout`（秒）。
- 治理报告会输出增量变更统计（added/modified/deleted/renamed）用于更精准自我进化。

## 8. Conversation Evolution（2026-03-03）
- 可选 job：`ops_conversation_evolution_incremental`（agent: `ops-agent`）。
- 用途：定时扫描近期对话/会话/记忆记录，识别 bug/流程问题/未闭环项/优化机会，打包 TODO。
- 该通道只产出任务包，不直接执行高风险改动。
- 在当前“三方记忆插件 / 官方默认记忆”模式下，该任务默认不自动安装；只有明确需要时才手工开启。

`workflow_setup.py` / `cron_setup.py` 相关参数：
- `--cron-install-conversation-evolution-job`
- `--cron-conversation-evolution-openclaw-home`
- `--cron-conversation-evolution-every-ms`
- `--cron-conversation-evolution-log-mode`
- `--cron-conversation-evolution-lookback-hours`
- `--cron-conversation-evolution-min-interval-minutes`
- `--cron-conversation-evolution-max-files`
- `--cron-conversation-evolution-max-tasks-per-run`
- `--cron-conversation-evolution-schedule-gap-minutes`
- `--cron-conversation-evolution-assignee`
- --cron-conversation-evolution-assignee 默认建议值：optimization-agent。

## 9. Conversation Evolution 质量门禁与去重（2026-03-03）

新增可配置项（`workflow_setup.py`）：

- `--cron-conversation-evolution-max-evidence-per-candidate`（默认 `24`）
- `--cron-conversation-evolution-min-evidence-lines`（默认 `3`）
- `--cron-conversation-evolution-min-unique-files`（默认 `1`）
- `--cron-conversation-evolution-min-quality-score`（默认 `55`）
- `--cron-conversation-evolution-recent-dedupe-days`（默认 `14`）

对应 `cron_setup.py` 参数：

- `--conversation-evolution-max-evidence-per-candidate`
- `--conversation-evolution-min-evidence-lines`
- `--conversation-evolution-min-unique-files`
- `--conversation-evolution-min-quality-score`
- `--conversation-evolution-recent-dedupe-days`

说明：

- 质量不足的候选会进入 `candidates_rejected`，不会创建 TODO。
- 已创建任务会写入 `dedupe_key`，在去重窗口内不重复创建同类建议。

## 10. GitHub Web Evolution（2026-03-04）

- 新增 job：`ops_github_web_evolution_incremental`（agent: `optimization-agent`）。
- 用途：从 GitHub 定时搜索高信号仓库，沉淀到 `~/.openclaw/web/github/`，并仅在增量命中时创建 TODO 任务包。
- 默认沉淀目录：
  - `repos/*.json`（仓库元数据）
  - `readmes/*.md`（README 快照）
  - `methods/*.md`（方法片段）
  - `runs/<timestamp_runid>/`（单次运行记录）
  - `index.json` 与 `CATALOG.md`（目录索引）
- 任务策略：
  - `task_type=github_web_evolution`
  - `source=github-web-evolution-agent`
  - `need_human_confirm=true`
  - 去重键：`fingerprint` + `dedupe_key`
  - 支持 `max_tasks_per_run` 分批建单（每批受 `min_new_or_updated` 门槛约束）
- 运行建议：
  - 推荐配置 `GITHUB_TOKEN`（由 `--cron-github-web-evolution-github-token-env` 读取）以减少 API 限流影响。

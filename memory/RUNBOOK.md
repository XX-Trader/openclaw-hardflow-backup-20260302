# RUNBOOK

## nofx 项目交付入口排障

常用事实源：

- nofx hardflow 仓库：`/home/arbops/projects/openclaw-hardflow-backup-20260302`
- nofx SmartMultiPlatformArbitrage 仓库：`/home/arbops/projects/SmartMultiPlatformArbitrage`
- Hermes runtime：`/home/arbops/.hermes`
- 标准入口：`/home/arbops/.local/bin/smart-arb-pipeline`（固定 live）
- pipeline runs：`/home/arbops/.hermes/pipeline-runs`
- Task Center DB：`/home/arbops/.hermes/ops/task-center/task_center.db`
- nofx profile SOUL 模板：`config/nofx-hermes-profiles/<profile>/SOUL.md`

排障顺序：

1. 查 `tmux ls`，确认 `hermes-tg`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-api` 是否存在。
2. 查 Hermes profile gateway state，确认 Discord 是否 connected。
3. 查最近 `pipeline_state.json` 和 `command-runs/*.json`，确认是否进入 live pipeline，以及每个阶段实际 command。
4. 查 `agent-workspaces/manifest.json`，确认每个阶段 owner 是否有独立 workspace。
5. 查 `command-runs/code_execution-1.patch` 是否生成并成功应用回主项目目录。
6. 查 `smart_arb_pipeline_entry.py` 和 `smart_arb_live_bridge.py` 的安装态版本，确认是否与本仓库 HEAD 对齐。
7. 若用户关心“是否转发到其他 agent”，必须检查是否有独立 agent session/run id，而不是只看 Task Center 的 `agent_id` 字段。

注意：当前 live bridge 已证明 workspace 隔离和阶段命令执行；2026-04-25 22:06 的 nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 里，命令阶段均记录为 `runtime-agent-workspace` / `isolated-agent-workspace`。native 多 agent fan-out 仍需以独立宿主 session/run id 为准。

## 2026-04-27 - nofx agent/model 实时口径

类型：runbook
范围：`/home/arbops/.hermes/profiles`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、项目交付优先工作流阶段 owner
事实：nofx 当前不是 14 个常驻 agent。服务器 live 入口是两个 Hermes Discord profile：`arbitrageagent` 和 `spreadagent`；两者均为 `model.provider=openai-codex`、`model.default=gpt-5.5`，且 `gateway_state=running`。服务器没有可作为 14 个常驻 agent 注册表解释的 `/home/arbops/.hermes/agents`、`/home/arbops/.openclaw/agents`、`/root/.openclaw/agents`、`/home/arbops/.codex/agents`、`/root/.codex/agents` 目录。真正执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`，阶段为 `research -> 需求讨论 -> 方案 -> 编码 -> 测试 -> review -> deployment -> memory_writeback`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`；cron / Task Center 定时任务只挂 `coordinator/project-agent`。`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
证据：2026-04-27 通过 nofx 远程核对：`tmux ls` 包含 `hermes-discord-arbitrage`、`hermes-discord-spread`、`hermes-tg`、`smart-arb-api`；两个 profile 的 `config.yaml` 均显示 `openai-codex/gpt-5.5`；`gateway_state.json` 均为 `running`。同时复核 nofx hardflow 仓库 `HEAD=44b4dae`，安装态 `/home/arbops/.hermes/ops/repo_hygiene_reviewer.py` 尚不存在，cron 仍有 11 个 job，其中 `source_registry_watcher` 仍是每周日运行。
最后验证：2026-04-27 10:30
复用建议：以后回答“服务器上有多少 agent、什么模型”时按四层区分：入口层是两个 live Hermes profile 与模型；工作流层是 `smart-arb-pipeline -> pipeline_runner.py`；逻辑 owner 层是 9 个 active owner 标签；定时任务层只允许 active owner 承载，当前为 `coordinator/project-agent`。不要把 2026-03 OpenClaw 14 Agent 注册表当成 nofx 当前运行态。若要把本仓库最新 2 天巡检和 Git 发布门禁同步到 nofx，先拉取最新 `main`，再运行 runtime installer。

## nofx hardflow 拉取与安装记录

### 2026-04-27 15:01 - 最新 runtime installer 同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`
事实：nofx hardflow 仓库已从 `44b4dae` fast-forward 到 `578b3f0`，本次 `git status --porcelain` 为空，`STASH_NAME=none`。runtime installer 返回 `ok=true`、`changed=true`，已安装 `repo_hygiene_reviewer.py`、`backlog_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 等 ops 脚本；runtime cron 已包含 `backlog_runner_30m（持续推进待办）`、`repo_hygiene_reviewer_2d（仓库精简巡检）` 和 `source_registry_watcher（API来源监控）`。
证据：`python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol` 通过；定向单测 `test_backlog_runner`、`test_project_delivery_runtime_installer`、`test_repo_hygiene_and_source_watcher`、`test_active_agent_registry`、`test_smart_arb_pipeline_entry`、`test_smart_arb_live_bridge` 共 53 项 OK；两个 Discord gateway 重启后 `gateway_state=running`、`discord=connected`；`curl http://127.0.0.1:18080/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`，`/api/strategy/status` 返回 `{"running":false,"pid":null}`；echo smoke run `install-smoke-arbitrageagent-20260427T065537Z` 为 `ok=true`、Task Center `passed`；受控 backlog runner smoke 任务 `todo-hardflow-install-smoke-20260427T070123Z` 被标记 `passed`，并写入 1 条 `backlog_runner_attempt`。
最后验证：2026-04-27 15:01
复用建议：安装完成后要额外核对 `smart-arb-api` tmux pane cwd，确认仍为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`，避免 live bridge deployment 单测或手工 smoke 把内控 API 留在临时目录。

### 2026-04-26 17:03 - Discord pipeline evidence 修复安装

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`
事实：本机提交 `edd05e23` 已推送到 `origin/main`，nofx 仓库已 fast-forward 到 `edd05e2` 并运行 runtime installer；`smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py` 已安装到 `/home/arbops/.hermes/ops`，`/home/arbops/.local/bin/smart-arb-pipeline` 指向新入口。拉取前服务器上已有上一轮手动同步的同批脏改动，已先保存为 `stash@{0}: pre-pull-hardflow-discord-pipeline-20260426`，再执行 `git pull --ff-only origin main`。
证据：runtime installer 返回 `ok=true`、`changed=true`、manifest 为 `/home/arbops/.hermes/ops/install/project-delivery-runtime-install.json`；`py_compile` 通过；nofx 相关单测 `tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 与 `tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 共 37 项 OK；`curl http://127.0.0.1:18080/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`，`/api/strategy/status` 返回 `{"running":false,"pid":null}`；echo smoke run `cli-arbitrageagent-20260426T090250542271Z` 为 14/14 阶段 completed，中文状态卡包含 agent 分工、agent 输出摘要和证据目录。
最后验证：2026-04-26 17:03
复用建议：以后 hardflow 代码推送后，nofx 安装按 `git fetch -> stash dirty tracked changes -> git pull --ff-only -> runtime_installer.py install -> py_compile -> gateway restart -> API smoke -> echo smart-arb-pipeline smoke` 顺序执行；若服务器仓库因手动同步变脏，先保留 stash，不要直接 reset。

## nofx profile SOUL 刷新

本仓库维护两个 UTF-8 模板：

- `config/nofx-hermes-profiles/arbitrageagent/SOUL.md`
- `config/nofx-hermes-profiles/spreadagent/SOUL.md`
- `config/nofx-hermes-profiles/arbitrageagent/config.yaml`
- `config/nofx-hermes-profiles/spreadagent/config.yaml`

刷新步骤：

1. 上传模板到 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 和 `config.yaml`，上传前备份原文件。
2. 避免通过 PowerShell 内联中文重写远程文件；用 SFTP 或 scp 按字节上传。
3. 确认 `SOUL.md` 内入口是绝对路径 `/home/arbops/.local/bin/smart-arb-pipeline`，不要依赖 gateway 的 `PATH`；确认 `config.yaml` 为 `approvals.mode: 'off'`、`security.tirith_enabled: false`。
4. 重启 tmux 会话：
   - `hermes-discord-arbitrage` 通过 `/home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh`
   - `hermes-discord-spread` 通过 `/home/arbops/.hermes/profiles/spreadagent/start-gateway.sh`
5. profile `.env` 和 `config.yaml` 必须保持 `arbops:arbops` 且 `0600`；如果通过 root/SFTP 写回，必须再 `chown arbops:arbops`，否则 gateway 或 Discord slash command 会因读写 profile 配置失败。
6. 验证：
   - `tmux ls`
   - `cat /home/arbops/.hermes/profiles/<profile>/gateway_state.json`
   - 读取 `SOUL.md` 前 10 行确认中文不是问号乱码。

## nofx live verification 门禁

Discord live pipeline 的 verification 阶段不再默认跑全量 `unittest discover`，因为 nofx 上该命令曾在 async/zmq 相关测试中长时间挂起。当前安全默认是：

```bash
git diff --check
/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime
```

profile `.env` 显式配置：

```bash
SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS=180
SMART_ARB_LIVE_BRIDGE_TEST_COMMAND='/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime'
```

`smart-arb-pipeline --live` 会把单命令超时写入 verification bridge 命令，例如 `--verification-command-timeout-seconds 180`。排障时查：

1. `command-runs/verification-1.json` 的 `command` 是否包含 timeout 参数。
2. `verification_report.md` 是否记录实际验证命令和 returncode。
3. 如果需要全量 unittest，只能在人工排障或 CI 中单独跑，不要作为 Discord live 默认门禁。

## nofx Hermes profile 审批配置

本机 WSL 的有效做法是 profile 级配置，而不是只看全局 `~/.hermes/config.yaml`：`/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml` 中有顶层 `approvals.mode: 'off'`。

nofx 上没有 `/home/arbops/.hermes/config.yaml` 全局配置；Discord agent 需要分别看 profile：

- `/home/arbops/.hermes/profiles/arbitrageagent/config.yaml`
- `/home/arbops/.hermes/profiles/spreadagent/config.yaml`

若出现 `Command Approval Required`，先确认两个 profile 都有顶层配置：

```yaml
approvals:
  mode: 'off'
```

修改后重启两个 tmux gateway：

```bash
runuser -u arbops -- tmux kill-session -t hermes-discord-arbitrage
runuser -u arbops -- tmux kill-session -t hermes-discord-spread
runuser -u arbops -- tmux new-session -d -s hermes-discord-arbitrage /home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh
runuser -u arbops -- tmux new-session -d -s hermes-discord-spread /home/arbops/.hermes/profiles/spreadagent/start-gateway.sh
```

验收顺序：

1. 读两个 profile 的 `config.yaml`，确认顶层 `approvals.mode: 'off'`。
2. 读 `/home/arbops/.hermes/profiles/<profile>/gateway_state.json`，确认 `gateway_state=running` 且 `updated_at` 是重启后的时间。
3. 扫描 `/home/arbops/.hermes/profiles/<profile>/logs/*.log` 尾部，确认没有新的 `Command Approval Required` / `confusable` 记录。

## nofx smart-arb-pipeline 默认 live

`/home/arbops/.local/bin/smart-arb-pipeline` 固定真实执行 live coordinator pipeline，会注入 external research、需求讨论、编码、验证、代码审查、内部部署和记忆写回命令证据。该入口不再提供 simulation/dry-run 模式。

注意：这里的 live 指真实改代码、验证、文档/记忆写回和内部 FastAPI smoke；仍不等于解除 `PRODUCTION_TRADING_ENABLED=false`，也不允许真实下单。

如果需求明确是 memory/docs-only、只写长期事实、no service control、no deployment 或 no restart，entry 会跳过 deployment command，不重启 `smart-arb-api`。如果同一需求后续明确要求 restart/deploy/重启/部署，正向 deployment 动作优先；普通 API/服务代码改动仍会注入 deployment bridge，重启内控 FastAPI 并做 `/health` 与 `/api/strategy/status` smoke。

### 2026-04-27 - Git 发布门禁

类型：runbook
范围：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：默认 live 入口会注入 `git_publish` 命令。runner 只在 verification、code review、deployment（如有）、acceptance 和 memory writeback 全部通过后执行该阶段；`git_publish` 优先接收 `memory_writeback` 隔离工作区 patch，缺失时只回退到已验收的 `code_execution` patch，确保不发布 `command_cwd` 的未验收脏改动；失败时阻塞为 `failed_stage=git_publish`、`next_action=fix_git_publish`。
证据：`pipeline_runner.py` 会写入 `git_publish_input_patch_report`；`smart_arb_live_bridge.py --stage git_publish` 会先执行 `git diff --check`，再 `git add -A`，随后执行 `git diff --cached --check`，打印 staged diff 统计，不打印完整 diff；随后扫描 staged diff 中的密钥形态，确认安全后生成脱敏中文提交说明并执行 `git push <remote> HEAD:<branch>`。该阶段不使用 force push。
最后验证：2026-04-27 相关单元测试 62 项 OK
复用建议：如远端冲突、认证失败、疑似密钥或 push 失败，先处理 `command-runs/git_publish-*.json` 与 `git_publish_report.md`，不要绕过 reviewer 或直接 force push。需要临时关闭发布时使用 `--skip-git-publish-command` 或 `SMART_ARB_SKIP_GIT_PUBLISH_COMMAND=1`。

## 定时仓库治理

### 2026-04-27 - Task Center 待办持续推进

类型：runbook
范围：`cron/jobs.json`、`scripts/openclaw-ops/backlog_runner.py`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`
事实：新增 `backlog_runner.py`，并注册 `backlog_runner_30m（持续推进待办）`。该 job 每 30 分钟最多选择 1 个 Task Center 中低风险、无需人工确认、无需澄清的 pending 待办，或显式允许 `next_action` 的 failed 项，调用 runtime 内安装的 `python3 <runtime_home>/ops/smart_arb_pipeline_entry.py --live --profile spreadagent --source backlog-runner` 继续推进。高风险、需确认、需澄清、`escalate_human` 任务会被跳过，继续由 `human_inbox.py` 处理；每个任务默认只记录 1 次 `backlog_runner_attempt`，避免无限重复续跑。若 pipeline 命令启动失败，runner 会记录 failed 输出并把任务转为 `failed`，不会卡在 `running`。
证据：`scripts/openclaw-ops/backlog_runner.py` 实现安全选择、失败项 next_action allowlist、防循环、pipeline 调用和启动失败兜底；`cron/jobs.json` 新增 `b9c8d7e6-backlog-runner-0030`，`--pipeline-command` 指向 runtime `ops/smart_arb_pipeline_entry.py`，不再从 runtime home 反推 `~/.local/bin`；`runtime_installer.py` 会把脚本安装到 runtime `ops/backlog_runner.py`；本地测试 `python -m unittest tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_project_delivery_runtime_installer tests.scripts_openclaw_ops.test_repo_hygiene_and_source_watcher` 共 9 项 OK。
最后验证：2026-04-27 12:00
复用建议：以后排查“很多 TODO 只有用户催才推进”时，先查 nofx 是否已安装 `ops/backlog_runner.py`，再查 `cron/jobs.json` 是否有 `backlog_runner_30m`，最后查 Task Center 中被跳过任务的 `need_human_confirm`、`needs_clarification`、`risk_level`、`source`、`next_action` 和 `backlog_runner_attempt` 输出。

### 2026-04-27 - 两天一次来源监控与仓库精简巡检

类型：runbook
范围：`cron/jobs.json`、`source_registry_watcher.py`、`repo_hygiene_reviewer.py`
事实：`source_registry_watcher（API来源监控）` 与 `repo_hygiene_reviewer_2d（仓库精简巡检）` 默认每 2 天执行一次。来源监控只检查项目记忆中声明过的官方来源；仓库精简巡检由 `coordinator` 执行，只读生成报告并创建 `repo_hygiene_candidate` 人工确认任务。
证据：`cron/jobs.json` 中两项任务均为 `kind=every`、`everyMs=172800000`；`source_registry_watcher.py` 会按传入 `--base-path` 读取 runtime 项目记忆目录；`repo_hygiene_reviewer.py` 只扫描并写报告，不删除、不提交、不推送。
最后验证：2026-04-27 相关单元测试 62 项 OK
复用建议：仓库精简候选必须先人工确认，再进入正常项目交付流水线；涉及删除、合并或修复冲突的改动仍需测试、code reviewer 和 `git_publish` 门禁。

## nofx Discord 输出与自动修复

Discord 入口默认输出中文状态卡，不只是 `failed_stage` / `next_action`：

1. `agent 分工与完成情况` 展示每个阶段对应 owner、状态、verdict、score 和证据文件。
2. `agent 输出摘要` 从 `command-runs/*.json` 读取 stdout/stderr/error，展示每个 stage command 的 agent、returncode 和关键输出。
3. `阻塞原因` 展示失败阶段、stage detail、命令输出和 artifact 摘要。
4. `自动修复判断` 记录是否回流、回流次数、风险分类和每次结果。

默认自动修复策略：

- `run_external_research`、`return_to_code_execution`、`return_to_deployment`、`fix_memory_writeback`：最多自动回流 2 次。
- 自动回流仍重新执行 `/home/arbops/.local/bin/smart-arb-pipeline`，每次使用 `<原 run_id>-repair<n>` 独立 run id，避免覆盖上一轮 `command-runs/*.json`。
- 自动回流会把上一轮失败证据写入上一轮失败 run 目录的 `auto_repair_context_<n>.md`，并同时通过内联 `PIPELINE_REPAIR_CONTEXT` 注入后续 Hermes stage prompt；即使文件写入失败，也不会丢失失败上下文。
- 状态卡默认展开最多 24 条 `command-runs/*.json` 摘要；需要更多可设置 `SMART_ARB_CHAT_COMMAND_LIMIT` 或传 `--chat-command-limit`。profile SOUL 要求把完整中文状态卡分段回传到聊天频道，不允许只回 run id、失败阶段和证据目录。
- 如果 Hermes CLI stdout/stderr 只有 `session_id: ...`，但对应 profile session 文件已有 assistant 输出，live bridge 会从 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json` 恢复最新 assistant 内容，先做脱敏，再用于 `external_research` local-only pass 判定和状态卡输出。
- 非代码 Hermes 阶段只返回 stdout/final answer 证据，不直接编辑 `research_report.md`、`requirements_discussion.md`、`patch_summary.md` 等 pipeline artifacts；bridge 会在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，这些文件由 runner 负责持久化。
- `external_research` 如果不需要互联网检索，必须在输出里写明 `NO_EXTERNAL_LOOKUP_NEEDED`、原因和本地证据；这属于有效 research evidence，不应因缺少 browser lookup 被判失败。
- 高风险内容不自动继续：正向要求读取/输出/使用凭证、API key、token、private key、session_id，或要求启用真实交易、下单、资金转移、提现、破坏性数据操作、force push 等。`不得泄露凭证`、`不启动真实交易`、`不下单不划转` 这类纯否定式安全边界不应被当成高风险阻断；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]` 仍是 high，`No need for ...` / `Do not need ...` 这类否定式预脱敏噪音可回流；如果同一段同时出现“但需要资金操作 / but needs credentials”等正向子句，仍按高风险停人工确认。
- bridge 会在前序 artifact 注入后续 prompt 前脱敏常见 header、assignment、长 token 和 GitHub PAT / OpenAI `sk-` / Slack / HF / Google / AWS access key 等短格式 secret；排障时不要把原始 token 放进 artifact。
- 排障时优先看最终状态卡，再看原 run 与 `-repair<n>` run 各自的 `command-runs/*.json`，以及原 run 下的 `auto_repair_context_<n>.md`。

### 2026-04-27 - 工作流自修与未通过 review 补丁清理

类型：runbook
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、nofx Discord profile `SOUL.md`、SmartMultiPlatformArbitrage 主工作区
事实：工作流自身修复不能继续通过同一个 Discord profile 无限启动 `smart-arb-pipeline`。两个 nofx profile 模板已增加“工作流自修例外”：用户明确说“不要走工作流”，或目标是修复 pipeline/bridge/profile/dual-review/auto-repair/git_publish 时，profile 只做只读诊断和状态回传，提示外部 operator/Codex 通过 SSH 修复 hardflow 并重新安装 runtime。`pipeline_runner.py` 会在 requirements review 通过后写 `resolved_requirement.md`，并让 `solution.md` 消费该 handoff。应用 code workspace patch 前会检查主工作区脏路径是否与补丁路径重叠，重叠则拒绝应用；`verification` 或 `code_review` 阻塞时对已应用到主项目目录的 patch 执行 `git apply -R` 并写入 `command-runs/rollback-<reason>.json`；如果回滚失败，pipeline 以 `failed_stage=rollback_cleanup`、`next_action=manual_cleanup_required` 阻塞，避免假装只是普通实现失败。
证据：本地测试 `python -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 共 68 项 OK；新增测试覆盖 requirement/solution artifact 保留具体用户请求、resolved requirement handoff、code review 失败回滚、verification 失败回滚、主工作区重叠脏路径拒绝应用、回滚失败升级为 manual cleanup。nofx 上旧业务漂移已保存到 `stash@{0}: pre-workflow-fix-rejected-business-drift-20260427T075431Z`，包含 `_close_position` / `execution_orchestration` 相关未通过 review 改动、`.workflow/` 和 `memory/smart-arb/`。
最后验证：2026-04-27 15:54
复用建议：遇到“修工作流本身”“不要走工作流”时，不要再让 Discord profile 自己调用 pipeline；先 SSH 到 nofx 停活跃 self-repair run，再改 hardflow 仓库、跑测试、安装 runtime。遇到 SmartMulti 主仓库残留未通过 review 的业务改动，优先 `git stash push -u -m pre-workflow-fix-rejected-business-drift-<timestamp>` 隔离，不要直接删除。

## nofx workflow 服务器级权限

早期不做细粒度权限划分时，nofx 采用高信任配置：

- Hermes profile：`approvals.mode: 'off'`
- Hermes security scan：profile 内 `security.tirith_enabled: false`
- Linux sudo：`/etc/sudoers.d/90-arbops-hermes` 允许 `arbops ALL=(ALL) NOPASSWD:ALL`

验收：

```bash
runuser -u arbops -- sudo -n true
runuser -u arbops -- sudo -n id
```

后期要收紧时，先把 sudoers 改成命令 allowlist，再重新打开 profile security scan。

## 2026-04-27 - 本机 WSL `trend-backtest` 接入 Discord 多核电脑 bot

类型：runbook
范围：`/home/ubuntu/.hermes/profiles/trend-backtest/{config.yaml,.env,SOUL.md,start-gateway.sh,memories/,sessions/}`、tmux `trend-backtest-gateway`
事实：本机 WSL `trend-backtest` profile 已从旧 Discord bot 切到用户新建的“多核电脑”bot，但该入口的语义不是“趋势回测专职 agent”，而是旧 Telegram 群“全自动策略研发回测”的 Discord 替代入口。2026-04-27 16:13 已把 profile `SOUL.md` 改为继承全局旧 TG `~/.hermes/SOUL.md`，并把 `~/.hermes/memories/{MEMORY.md,USER.md}` 合并进 profile memories；原 `trend-backtest` 回测专项记忆作为次级上下文保留。profile 级配置仍固定为 `approvals.mode: 'off'`、`security.tirith_enabled: false`、`discord.auto_thread: false`；为避免 bot 在所有可见频道无条件响应，采用 `discord.require_mention: true` + `discord.free_response_channels: '1498225531923988562'`，即 `本地项目 / #常规` 频道免 @，其它频道仍需 @。敏感 token 只写入 profile `.env`，不得写入仓库、记忆或聊天摘要。
证据：迁移备份位于 `/home/ubuntu/.hermes/profiles/trend-backtest/backups/tg-inherit-20260427161320` 与 `encoding-fix-20260427161441`；已删除新 Discord 频道在旧趋势回测 SOUL 下生成的 session `20260427_160858_715e39ff`，下条消息会重建 session。重启后 `gateway_state.json` 显示 PID `56155`、`gateway_state=running`、`platforms.discord.state=connected`；`/proc/56155/cwd` 为 `/home/ubuntu`，不再是 `/home/ubuntu/projects/SmartTrendTracker`。`SOUL.md` 头部明确禁止自称 trend backtest agent，且禁止声明 SmartTrendTracker 是唯一默认工作目录。
最后验证：2026-04-27 16:15
复用建议：后续若用户说“这个 Discord bot 是替代 TG 的”，不要只改 Discord token 或 profile `.env`；必须同时核对 `SOUL.md`、profile memories、`start-gateway.sh`、`terminal.cwd` 和新频道 session 是否由旧 prompt 污染。若 bot 在线但不回复，再查频道权限与 Message Content Intent。

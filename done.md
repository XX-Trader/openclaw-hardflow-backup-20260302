# DONE — 已完成功能清单

> 所有已完成并上线的功能记录在此。每项包含：完成时间、功能描述、关键实现细节。
> 与 `todo.md` 配合使用，形成完整的项目进度管理视图。

---

## 2026-04-28 已完成

- [x] [2026-04-28] **nofx Discord 回复状态标识**
  - `smart-arb-pipeline` 启动卡和运行中进度卡新增 `回答状态: 正在回复/执行中`，最终状态卡新增 `回答状态: 已回答完毕` 或 `未回答完毕...`，让 Discord channel 能直接判断任务是否仍在回复。
  - 两个 nofx profile SOUL 要求只读直接回复末尾补 `回答状态: 已回答完毕`，长只读查询可先发 `回答状态: 正在回复/查询中`。
  - 验证：本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 39 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`python -B -m py_compile scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`git diff --check` 通过。

- [x] [2026-04-28] **DeliveryPlan 结构化方案契约与 revise_solution 自动回流**
  - `solution_package` 新增 `delivery_plan.json` 结构化交付契约，字段覆盖任务类型、切片、目标文件/定位策略、实施步骤、验证命令、发布/回滚门禁、人工阻塞条件和安全边界。
  - `solution.md` 改为由契约渲染的人工展示层；`solution_review`、`code_execution` 和后续阶段上下文都读取 `delivery_plan.json`，不再靠润色 Markdown 通过审查。
  - `revise_solution` 纳入低风险自动回流；“do not set PRODUCTION_TRADING_ENABLED=true”等否定式安全边界不再误判，正向启用实盘、下单、资金操作、凭证仍 hard block。
  - 验证：本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 96 项 OK；nofx 已安装 runtime 代码批次 `3a44f0b0`，远端 `compileall` 与 67 项定向单测 OK。

- [x] [2026-04-28] **nofx Discord 证据短标签与 cron 群投递**
  - `smart-arb-pipeline` 状态卡的证据项改为 20 字以内中文短说明，例如“方案评审报告”“代码执行命令1”，完整证据文件仍保留在 run 目录。
  - `cron/jobs.json` 的 `delivery` 与 `failureAlert` 从旧 Telegram 群切到 spreadagent Discord 群 `1494595527181078578`，定时任务结果和失败告警默认输出到群里。
  - 两个 nofx Discord profile SOUL 同步要求证据短说明；安装器测试校验 selected cron job 安装后的 Discord 投递目标。
  - 后续部署已把包含该变更的 runtime 代码批次 `3a44f0b0` 安装到 nofx live runtime；两个 live profile `SOUL.md` 已同步仓库模板并重启，gateway 均为 `running/connected`。
  - 验证：本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 36 项 OK；`python -B -m json.tool cron/jobs.json`、`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过。

- [x] [2026-04-28] **nofx 拉取并安装 runtime 代码批次 `3a44f0b0`**
  - 本机 runtime 代码批次 `3a44f0b0` 已推送到 `origin/main`；nofx 仓库已安装该代码批次，安装时工作树 clean，`HEAD...origin/main=0 0`。后续文档/记忆记录提交可继续 fast-forward 到 `origin/main`，不改变本批 runtime artifact。
  - `runtime_installer.py install` 返回 `ok=true`、`changed=true`，安装态 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 与仓库源码 SHA256 对齐。
  - 两个 live profile `SOUL.md` 已同步仓库模板，备份为 `SOUL.md.bak-20260428T143343`，并重启 `hermes-discord-arbitrage`、`hermes-discord-spread`。
  - 验证：远端 `compileall` 通过；定向单测 67 项 OK；`smart-arb-pipeline --help` 正常；两个 gateway `running/connected`；内控 API `127.0.0.1:18080/health` 与 `127.0.0.1:18080/api/strategy/status` 通过。

## 2026-04-27 已完成

- [x] [2026-04-27] **nofx 拉取并安装 `067fbc43` hardflow runtime**
  - 绕开 Discord workflow 自修，通过外部 SSH/operator 路径把 nofx hardflow 仓库拉到 `067fbc43`，并运行 `runtime_installer.py install` 同步到 `/home/arbops/.hermes`。
  - 安装前备份 runtime 目标文件到 `/home/arbops/.hermes/ops/install/backups/pre-hardflow-install-20260427T151242Z`；安装后 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 与仓库源码 SHA256 对齐。
  - 验证：远端 `py_compile`、`compileall`、98 项定向单测、`smart-arb-pipeline --help`、cron 检查、gateway state、内控 API smoke 均通过；echo smoke `install-smoke-arbitrageagent-20260427T151733781612Z` 写入 Task Center 且 `passed`；`smart-arb-api` cwd 已核对为真实 SmartMulti 目录。

- [x] [2026-04-27] **nofx Discord 输出降噪与工作流状态卡**
  - `smart-arb-pipeline` 默认不再只等子进程结束后输出最终状态；入口会轮询 `pipeline_state.json`，每 60 秒输出 `# nofx 任务执行进度`，展示已完成阶段、当前阶段、最近命令状态和证据目录。
  - 聊天状态卡默认不展开 reviewer/tester/terminal stdout/stderr，也不额外发送“关键证据”列表；需要调试时才用 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` / `--chat-include-command-output` 展开脱敏摘要。
  - 两个 nofx profile 模板关闭 Hermes 通用 `Still working...` 心跳、tool progress 和 `[Background process ...]` wrapper，长任务反馈由 pipeline 中文状态卡负责。
  - `pipeline_runner.py` 在长命令启动前写入 `running` stage，阶段完成后刷新状态，避免 Discord 只显示 Hermes 通用心跳。
  - 进度卡和 live bridge 输出脱敏覆盖普通赋值、header、JSON/TOML quoted sensitive key、长 token 和常见短 secret；`api_key=[REDACTED]` 等需要凭证的失败上下文仍保持 high-risk，不会自动回流。
  - 验证：`python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 32 项 OK；`python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；`git diff --check` 通过。本轮尚未部署到 nofx。

- [x] [2026-04-27] **nofx Git 发布门禁分级与 fix_git_publish 自动回流**
  - `git_publish` secret scan 改为结构化 findings：只扫描 staged diff 新增行，并输出脱敏文件、行号、规则、风险等级和片段。
  - 真实 token/header/cookie/高熵值、hardcoded fallback secret、PEM private key 继续 hard block；环境变量名、测试假值、文档占位和 Basic Auth 说明不再误阻断。
  - `fix_git_publish` 纳入自动回流白名单；含真实 secret、凭证、资金、真实交易、破坏性操作或 secret scan high/blocking finding 时仍停人工确认。
  - 验证：`python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 59 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过。

- [x] [2026-04-27] **本机 WSL 两个 Discord agent 独立 profile / workspace**
  - `trend-backtest` 已恢复为旧 Discord bot“趋势回测机器人”与旧频道 `趋势回测测试`，SOUL 为趋势回测专职 agent，cwd 为 `/home/ubuntu/projects/SmartTrendTracker`。
  - 新增 `multicore` profile 承接新 Discord bot“多核电脑”与 `本地项目/#常规`，SOUL 继承旧 Telegram 全局 Hermes 记忆，cwd 为 `/home/ubuntu/.hermes/profiles/multicore/workspace`。
  - 两个 profile 都配置 `DISCORD_ALLOWED_CHANNELS=<各自频道>`、`DISCORD_ALLOW_DMS=false`，各自频道免 @，但不会跨频道或 DM 抢消息。
  - `trend-backtest-gateway` 与 `multicore-gateway` 均已在 tmux 中运行，Discord API 与 Hermes `gateway_state` 均验证 connected。

- [x] [2026-04-27] **nofx 拉取并安装最新 hardflow runtime**
  - nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302` 已从 `44b4dae` fast-forward 到 `578b3f0`，本次远端工作区无脏改动，未创建 stash。
  - `runtime_installer.py install` 已把最新 ops 脚本与 cron jobs 安装到 `/home/arbops/.hermes`，包括 `backlog_runner.py`、`repo_hygiene_reviewer.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`backlog_runner_30m` 和 `repo_hygiene_reviewer_2d`。
  - 验证：远端 `compileall` 通过；定向单测 53 项 OK；两个 Discord gateway 为 `running/connected`；内控 API `/health` 与 `/api/strategy/status` 通过；echo smoke `install-smoke-arbitrageagent-20260427T065537Z` 写入 Task Center 且 `passed`；受控 backlog runner smoke `todo-hardflow-install-smoke-20260427T070123Z` 写入 1 条 `backlog_runner_attempt`。

- [x] [2026-04-27] **工作流合规收敛：低风险自动推进、9 个 active owner、双 reviewer 门禁**
  - `deadline_to_task_bridge.py` 改为按 TODO 文本和优先级推断风险：低风险到期项直接创建 `dispatch_pipeline` 候选并交给 `coordinator/backlog_runner`，高风险、部署、资金、凭证、删除、生产操作等仍进入 `human_inbox.py` 等待人工确认。
  - `pipeline_runner.py` 的需求审查、方案审查、代码审查均要求至少两条独立 reviewer command report，且各自输出预期 `Final verdict` 后才放行；live entry 默认注入 `reviewer-a/reviewer-b` 两条命令。
  - `openclaw.json` 与 `openclaw/openclaw.json` active agent 清单收敛为 9 个 workflow owner；`cron/jobs.json` 的定时任务 owner 改为 `coordinator/project-agent`，不再注册 `ops-agent/optimization-agent`。
  - 新增/更新测试覆盖低风险 TODO 自动队列、高风险 TODO 人工确认、双 reviewer 数量门禁、重复 reviewer role/command 阻断、live bridge review verdict、Hermes smoke 同步、active agent registry 和 cron owner 合规。

- [x] [2026-04-27] **Task Center 待办持续推进 runner**
  - 新增 `scripts/openclaw-ops/backlog_runner.py`：每次从 Task Center 选择最多 1 个低风险、无需人工确认、无需澄清的 pending 待办，或允许 `next_action` 的 failed 项，调用 `smart-arb-pipeline` 继续推进。
  - 注册 `backlog_runner_30m（持续推进待办）` cron，每 30 分钟运行一次；高风险、需确认、需澄清和人工升级任务仍停在 `human_inbox.py`。
  - `runtime_installer.py` 已同步安装 `ops/backlog_runner.py`；新增测试覆盖安全选择、pipeline 执行、任务状态回写和安装器同步。
  - 同步文档：项目交付 README/架构/实施规划、docs 索引、Cron 索引、项目记忆、todo。

- [x] [2026-04-27] **nofx agent/model 口径修正**
  - 远程复核 nofx 当前运行态：`arbitrageagent` 与 `spreadagent` 两个 Hermes Discord profile 均为 `openai-codex/gpt-5.5`，gateway running。
  - 修正“14 个 agent”误导口径：2026-03 的 14 Agent 文档仅保留为历史 OpenClaw 注册表快照；nofx 当前项目交付链路中的 `coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` 是阶段 owner / workspace / Task Center 标签，不是独立常驻 agent；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
  - 保留 `frontend-dev` 作为前端/UI/页面/交互代码执行 owner；入口脚本支持 `--code-agent frontend-dev`，也会按前端关键词自动推断。
  - 同步 `memory/`、项目交付工作流文档、基础设施索引和 `todo.md` 的模型配置说明。

- [x] [2026-04-27] **仓库精简巡检与 Git 发布门禁**
  - 新增 `repo_hygiene_reviewer.py`，由 `coordinator` 每 2 天只读扫描冗余文件、失效缓存、冲突残留、重复文件和测试残留；只生成报告和 Task Center 人工确认候选，不自动删除、不自动推送。
  - `source_registry_watcher（API来源监控）` 调整为每 2 天执行，并修复 `--base-path`，确保安装态读取 runtime 项目记忆目录。
  - 修复仓库精简巡检对内联冲突标记示例的误报；删除已跟踪的 `cron/jobs.json.bak.20260422220950` 备份文件。
  - 项目交付流水线新增 `git_publish` 阶段：验证、代码审查、deployment（如有）、验收和记忆回写通过后才执行；提交说明、备注和变更描述必须中文；疑似密钥、远端冲突、认证失败或 push 失败会阻塞为 `fix_git_publish`。
  - `smart_arb_pipeline_entry.py` 默认注入 Git 发布命令，也支持 `--skip-git-publish-command` / `SMART_ARB_SKIP_GIT_PUBLISH_COMMAND=1` 临时关闭。
  - 同步文档：项目交付 README/架构设计、nofx live evidence bridge、Cron 索引、治理清单、项目记忆和 todo。

## 2026-04-26 已完成

- [x] [2026-04-26] **nofx 拉取最新 hardflow 代码并安装**
  - 本机提交 `edd05e23` 已推送到 `origin/main`；nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302` 已 fast-forward 到 `edd05e2`。
  - 拉取前 nofx 仓库存在上一轮手动同步留下的 13 个脏改动，已保存为 `stash@{0}: pre-pull-hardflow-discord-pipeline-20260426` 后再 `git pull --ff-only origin main`。
  - 运行 `runtime_installer.py install` 成功，返回 `ok=true`、`changed=true`，并安装 `smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py` 到 `/home/arbops/.hermes/ops`。
  - 两个 Discord Hermes gateway 已重启，`arbitrageagent` 与 `spreadagent` 的 `platforms.discord.state=connected`。
  - 验证：远端 `py_compile` 通过；相关单测 37 项 OK；`/health` 与 `/api/strategy/status` smoke 通过；echo pipeline run `cli-arbitrageagent-20260426T090250542271Z` 14/14 completed 并返回中文状态卡。

- [x] [2026-04-26] **nofx Discord 状态卡、session 输出恢复与 P0 写回门禁修复**
  - `smart_arb_pipeline_entry.py` 将状态卡命令摘要上限改为可配置，默认展示 24 条 `command-runs/*.json`；两个 nofx profile `SOUL.md` 要求失败时把完整中文状态卡回传聊天频道。
  - `smart_arb_live_bridge.py` 在 Hermes CLI 只返回 `session_id` 时，从 profile session 文件恢复最新 assistant 输出并脱敏；`external_research` 的 `NO_EXTERNAL_LOOKUP_NEEDED` 可据此通过 live gate。
  - 风险扫描保留正向高风险：`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]`、真实 credential assignment、真实交易/资金/破坏性操作仍停人工确认。
  - 风险扫描放行安全否定噪音：`不得泄露凭证`、`不下单不划转`、普通 `session_id=[REDACTED]`、`No need for ...`、`Do not need ...` 可自动回流。
  - memory/docs-only、no service control、no deployment、no restart 需求不再注入 deployment command，避免纯记忆/文档写回任务重启 `smart-arb-api`；混合需求里如后续明确要求重启/部署，则正向 deployment 动作优先，普通 API/服务改动也保留 deployment smoke。
  - nofx 已完成 P0-1 写回 run `discord-spreadagent-20260426T075133316811Z`，15 个阶段 completed，verification/code_review/acceptance 均 pass。

- [x] [2026-04-26] **nofx external_research 自动回流与安全边界误判修复**
  - `smart_arb_pipeline_entry.py` 将 `run_external_research` 纳入自动修复白名单，并在高风险扫描前剥离“不得泄露凭证 / 不启动真实交易 / 不下单不划转”等否定式安全约束。
  - 高风险扫描改为分句级处理；混合句里出现 `but needs credentials`、`但需要资金操作` 等正向凭证/资金操作仍会停人工确认。
  - `smart_arb_live_bridge.py` 要求非代码 Hermes 阶段只通过 stdout/final answer 返回证据，不直接编辑 pipeline artifact；`external_research` 可用 `NO_EXTERNAL_LOOKUP_NEEDED` 表示本地事实已足够。
  - 非代码 Hermes 子进程环境会剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，避免 agent 直接覆盖 `research_report.md` 等 runner 管理的产物。
  - `code_execution` prompt 会读取前序 `research_report.md`、需求、方案和 review artifacts，避免 P0 记忆/环境任务漂移到后续 S1 策略重构。
  - 前序 artifact 注入后续 prompt 前会脱敏常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack/HF/Google/AWS key。
  - 新增回归测试覆盖 local-only external research、否定式安全边界、混合句正向高风险、正向凭证/真实交易高风险、前序上下文注入和上下文脱敏。

- [x] [2026-04-26] **nofx Discord pipeline 状态卡与自动修复**
  - `smart_arb_pipeline_entry.py` 状态卡新增 `agent 输出摘要`、`阻塞原因` 和 `自动修复判断`，会读取 `command-runs/*.json` 的 stdout/stderr/error，而不再只回 `failed_stage` / `next_action`。
  - 低/中风险阻塞会按 `return_to_code_execution`、`return_to_deployment`、`fix_memory_writeback` 自动回流最多 2 次；每次回流使用 `<原 run_id>-repair<n>` 独立 run id，写入 `auto_repair_context_<n>.md`，并重新走完整 coordinator pipeline。
  - `smart_arb_live_bridge.py` 会把上一轮失败上下文注入后续 Hermes stage prompt，便于执行 agent 自行修复根因。
  - 高风险凭证、真实交易、资金转移、提现、破坏性数据操作和 force push 仍停人工确认。

- [x] [2026-04-26] **nofx Discord pipeline 默认 live 与 profile 写权限修复**
  - `smart_arb_pipeline_entry.py` 改为固定 live coordinator pipeline；项目入口不再提供 simulation/dry-run 模式。
  - 两个 nofx Discord profile 提示词改为“执行类需求默认真实执行”，并新增仓库级 `config.yaml` 模板，关闭命令审批和 security scan。
  - nofx `spreadagent/config.yaml`、`arbitrageagent/config.yaml` 从 `root:root 0600` 修回 `arbops:arbops 0600`，解决 `/sethome` 写 profile 配置失败。
  - nofx 写入 `/etc/sudoers.d/90-arbops-hermes`，允许 `arbops` 无密码 sudo，满足早期 workflow 服务器级执行权限。
  - 同步 runbook、pitfalls 和 nofx live bridge 文档，保留 `PRODUCTION_TRADING_ENABLED=false` 与真实交易禁止边界。

## 2026-04-25 已完成

- [x] [2026-04-25] **nofx live bridge per-agent workspace 隔离**
  - `pipeline_runner.py` 固定使用 Git worktree 隔离，新增 `agent-workspaces/manifest.json`、`PIPELINE_AGENT_*` 环境变量注入、command report workspace 留痕和 Task Center `agent_execution` 详情；不再暴露 `shared` / `copy` 模式。
  - `code_execution` 默认在 `backend-dev` 独立 workspace 内执行；前端/UI/页面/交互类需求可切到 `frontend-dev` workspace；成功后导出 `command-runs/code_execution-1.patch`，应用回主项目目录，并注入后续 `tester`、`reviewer`、`deployer` workspace。
  - `smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为 Hermes 阶段项目目录。
  - workspace root 若被配置到项目目录内部，会直接报错要求移到 `--command-cwd` 外部，不再静默降级。
  - 新增回归测试覆盖 worktree 隔离、diff 回流、两条 verification 命令共享 workspace 时不重复 apply patch、后续 reviewer workspace 注入、嵌套 workspace 拒绝和 nofx entry 不再传 workspace mode；nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 已通过。

- [x] [2026-04-25] **nofx Hermes profile 提示词修复与 fan-out 边界澄清**
  - 复核 nofx 发现 `spreadagent` 19:10 Discord 会话没有创建新的 `smart-arb-pipeline` run，而是在 Hermes profile 会话里直接规划任务；同时两个 profile 的 `SOUL.md` 主体为问号乱码，coordinator pipeline 约束不稳定。
  - 新增仓库模板 `config/nofx-hermes-profiles/arbitrageagent/SOUL.md` 与 `config/nofx-hermes-profiles/spreadagent/SOUL.md`，按字节上传到 nofx 并备份原文件，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
  - 验证两个 profile 均为 `gateway_state=running`、`discord=connected`，且 `SOUL.md` 中文可读；标准入口 dry-run smoke `codex-prompt-smoke-spreadagent-20260425T112013223220Z` 返回 `completed`。
  - 同步文档和项目记忆，明确当前 live bridge 是 Hermes 单会话 stage bridge，不是真实 native 多 agent fan-out；真实 fan-out 已记录到 `todo.md`。

## 2026-04-24 已完成

- [x] [2026-04-24] **Hermes profile 非 dry-run smoke 验收**
  - 新增 `hermes_profile_smoke.py`，支持 `echo`、`hybrid`、`hermes-chat` 三种 smoke 模式
  - 修复原 `hybrid` 每阶段冷启动 `hermes chat` 导致的 3-10 分钟耗时；现在一次 `hermes chat` 生成 research/code/review bundle，再由本地 stage command 读取缓存
  - WSL `/home/ubuntu/.hermes` 已完成 `hybrid-single-chat` smoke：真实 `hermes chat --provider zai` 50 秒完成 bundle，verification 走确定性本地命令
  - 验收证据：run_id=`hermes-profile-smoke-20260424T135014Z`，Task Center task=`project-delivery:hermes-profile-smoke-20260424T135014Z`，状态 `completed`
  - `hermes-chat` 全阶段模式保留为 provider 诊断入口，不作为默认 smoke 门禁

- [x] [2026-04-24] **Project Delivery Pipeline live 命令适配层**
  - `pipeline_runner.py` 新增 `--research-command`、`--code-command`、`--verification-command`、`--code-review-command`、`--memory-write-command`、`--write-project-memory`
  - live 模式会把每个命令的 cwd、退出码、stdout/stderr 写入 `command-runs/*.json`，失败时按阶段回退
  - `--write-project-memory` 已调用 `project_memory_writer.py` 写入项目记忆；安装器同步 `project_memory_writer.py` 与 `project_memory_injector.py`
  - 新增单元测试覆盖完整 live command adapter happy path

- [x] [2026-04-24] **运营事件入任务中心 + 人工队列闭环**
  - 新增 `deadline_to_task_bridge.py`：到期/超期 TODO 自动生成 `todo_deadline_candidate`；2026-04-27 起按风险分流，低风险自动进入 coordinator pipeline，高风险才 `need_human_confirm=true` 等待用户确认
  - 新增 `exception_to_task_bridge.py`：增量扫描日志异常，按 fingerprint 去重创建 `ops_exception` 运维任务，并写入 `task_incidents`
  - 新增 `human_inbox.py`：统一列出、确认、拒绝、澄清 `need_human_confirm`、`needs_clarification`、`escalated`、`escalate_human` 任务
  - 更新 `cron/jobs.json`：注册 `todo_deadline_to_task_bridge_daily` 与 `system_exception_to_task_bridge`
  - 新增单元测试：`test_deadline_to_task_bridge.py`、`test_exception_to_task_bridge.py`、`test_human_inbox.py`

- [x] [2026-04-24] **Project Delivery Pipeline 可控性收口**
  - `pipeline_runner.py` 新增项目记忆定位门禁，自动生成 `.workflow/project-memory/<project_key>/PROJECT_PROFILE.md`、`DECISIONS.md`、`DELIVERY_RULES.md`、`API_REGISTRY.json`、`SOURCE_REGISTRY.json`、`IMPACT_MAP.json`、`RETRIEVAL_MANIFEST.json`
  - 新增 `--record-task-center` / `--task-center-db` / `--task-center-task-id`，将流水线镜像到 Task Center 的 `tasks`、`stage_runs`、`module_communications`、`task_outputs`、`task_incidents`
  - 新增 `pipeline_runner.py view` 查看入口，快速定位 run 状态、下一步、失败阶段、关键产物和 Task Center 引用
  - 修复技能化迁移后的任务查看工具 import path：`task_output_consumer.py`、`task_output_broadcast_runner.py`、`policy_enforcer.py`
  - 技术裁决：默认 hybrid local-first 项目记忆 + keyword/symbol 检索；向量 RAG 与 GraphRAG 做可插拔增强，不默认引入重服务

- [x] [2026-04-24] **Project Delivery Pipeline Phase 6 MVP**
  - 新增 `skills/library/project-delivery-pipeline/`：Skill 入口、状态机 runner、模板、state-machine 与 runtime-adapter 参考文档
  - `pipeline_runner.py` 支持需求输入、外部 research 产物、需求/方案/代码 review gate、dry-run 编码交付、测试验收、失败回退、writeback 报告
  - 明确 Hermes/OpenClaw 只是 runtime host 示例；默认通用 runtime 为 `~/.hardflow-runtime`，也支持任意 `--runtime-home`
  - 新增 `runtime_installer.py` 并将根目录 `setup.py` 切换到新入口，旧 `workflow_setup.py` / `install_workflow_profile.py` 不再保留兼容入口
  - 新增测试 `tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`，覆盖 happy path、需求失败回退、验收需求失败回退、Hermes runtime home

- [x] [2026-04-24] **项目交付优先工作流收束为端到端编码交付流水线**
  - 明确真实目标：自动探索需求、需求包、方案包、编码、测试、代码审核、修复、验收、文档/记忆回写
  - 新增 Phase 6：`project-delivery-pipeline` 状态机与 runtime adapter
  - 明确不用做：不恢复 `cron_setup.py`，不恢复 `install_*_job.py`，不维护多套 runtime 业务流程，不新增平行编码引擎，不恢复默认自进化链
  - 删除旧 `install_workflow_profile.py` 主体逻辑，不保留兼容入口
  - 删除旧 Hermes 适配测试、`SETUP_WORKFLOW.md`、旧控制面 live acceptance runner、失效 root CLI 入口测试和旧 shared human output 测试
  - 同步文档：`docs/核心主工作流/项目交付优先工作流/`、`docs/INDEX.md`、`docs/核心主工作流/README.md`、`todo.md`

---

## 2026-04-23 已完成

- [x] [2026-04-23] **Multica Managed Agents 平台调研**
  - 核对 `multica-ai/multica` 最新 GitHub 仓库、release 资产、CLI/daemon、自部署、桌面端和 Web 控制台结构
  - 明确 `exe` 分为 CLI 二进制与 Desktop 安装包，GitHub 仓库才是完整源码
  - 结论：不迁移 OpenClaw 手机/Discord 主链；仅借鉴 runtime registry、任务状态机、transcript、Skill 绑定、daemon 健康检查和 Autopilot 触发模型
  - 文档路径：`docs/研究参考/multica-managed-agents-平台研究.md`

---

## 2026-03-29 已完成

### 配置自动进化体系搭建（阶段四 4.2/4.3）

- [x] [2026-03-29] **B 层 Clone 修复**
  - 服务器 `git clone` 创建 `/root/openclaw-hardflow-backup-20260302/`
  - 验证 hooks/skills 目录可达，GitHub SSH 认证正常

- [x] [2026-03-29] **C 层同步通道确认**
  - 确认 `ops_git_sync_push`、`governance_evolution`、`auto_update_daily` 三个 cron 的 `repo-path` 均已指向 B 层
  - C 层 `.gitignore` 已有基础排除规则

- [x] [2026-03-29] **每小时本地快照** — `local_snapshot_runner.py`（新建）
  - 白名单同步：`openclaw.json`、`hooks/`、`skills/`、`agents/`、`cron/`、`ops/`
  - 排除列表：`sessions/`、`auth-profiles`、`.bak`、`skills/library/`、`exception-reports/`
  - 仅内容变化时复制，支持 dry-run 和 JSON 输出
  - 注册 `local_config_snapshot` cron（每小时，id=`70a5f20a`）
  - 脚本路径：`scripts/openclaw-ops/local_snapshot_runner.py`

- [x] [2026-03-29] **auto_update_daily 安装修复**
  - 发现 cron 只执行 `git pull` 但缺少 `--install-cmd`，pull 后不安装
  - 确认 `workflow_setup.py` 已支持 `--yes` 非交互模式（第 1382 行）
  - Patch cron：添加 `--install-cmd "python3 setup.py --yes ..."` 参数
  - 现在 pull 后自动执行 `setup.py --yes` 安装到 `.openclaw/`

### Cron 任务批量修复

- [x] [2026-03-29] **Telegram 群 ID 批量替换**
  - 25 处旧群 ID (`-1003333097130`) → 新 ID (`-1003758974925`)
  - 清除 5 条过期 `lastError` 记录

### Agent 模型配置同步

- [x] [2026-03-29] **模型绑定更新**（同步 `openclaw.json` 和 `openclaw/openclaw.json`）
  - coordinator → `gpt-5.4`
  - tester → `Doubao-Seed-2.0-pro`
  - doc-writer → `Doubao-Seed-2.0-pro`
  - explorer → 新增 `gpt-5.4-mini`

### 文档体系重构

- [x] [2026-03-29] **多层级文档目录结构**
  - 建立 `docs/INDEX.md` 顶层功能索引
  - 创建 `docs/自动进化/` 父级目录 + `配置自动进化/` 子功能目录
  - 功能文件夹标准三件套：`README.md` + `architecture.md` + `implementation-plan.md`
  - 固化文档编写规范（每个功能一个文件夹，索引只写目录引用）

- [x] [2026-03-29] **Telegram 输出规范文档化**
  - `docs/telegram-output-format-spec.md`：多列表格格式标准

### OpenClaw 启动修复

- [x] [2026-03-29] **Gateway 守护进程排查**
  - 确认正确启动命令为 `openclaw gateway`（而非 `openclaw daemon`）
  - 通过 tmux 会话在 nofx 服务器正常运行

### 任务执行器 Bugfix（3项）

- [x] [2026-03-29] **失败原因输出修复** — `workflow_views.py`
  - 问题：`humanize_executor_reason()` 在 `reason` 为空时，兜底返回泛化的"任务执行失败"，丢失真实错误
  - 修复：增加 `resolution_summary` 回退读取，自动识别 Gateway 连接失败、执行超时、网络错误
  - 效果：NOFX-bot 通知现在展示 `Gateway 连接失败` 而非 `任务执行失败`

- [x] [2026-03-29] **异常日志巡检 Auto-Discover** — `unified_exception_logger.py`
  - 问题：ops-agent 调用时自行推理 `--log-dirs /root/.openclaw/sessions/`，该目录不存在
  - 修复：新增 `--auto-discover` 参数 + `discover_log_dirs()` 函数
  - 自动扫描 7 类目录：`agents/*/sessions`、`ops/task-center/executor-runs`、`logs` 等
  - Agent 只需传 `--auto-discover`，不需要猜测路径

- [x] [2026-03-29] **TASK_STATUSES 未定义** — `policy_enforcer.py`
  - 问题：`from task_center import TASK_STATUSES` 在 gateway 异常时 import 失败
  - 状态：gateway 重启后自愈，已确认最近 4 轮执行均正常

---

## 2026-03-28 已完成

### 阶段 6.5：PolicyEnforcer 二次深度拆分（Mixin 架构）

- **目标**: 将 4,526 行单体 `PolicyEnforcer` 拆分为 5 个 Mixin + 1 个组合类
- **结果**:
  - `policy_scoring.py` (ScoringMixin, 234行/8方法)
  - `policy_workflow.py` (WorkflowMixin, 848行/14方法)
  - `policy_context.py` (ContextMixin, 514行/11方法)
  - `policy_task.py` (TaskLifecycleMixin, 2029行/35方法)
  - `policy_observe.py` (ObservabilityMixin, 951行/21方法)
  - `policy_enforcer.py` (组合类, 180行/24属性)
- **验证**: 9/9 语法通过 + CLI 28 子命令 + validate-runtime 正常执行
- **提交**: `13887bc9` → `02ed03e1` → `28d66869` → `10f6af92`

### 阶段一～五：自进化系统全面优化（部署完成）

- [x] [2026-03-28] **Cron Job 清理**：删除 12 个冗余/禁用 Job（原 33 → 21）
  - 删除 9 个冗余 Job + 3 个禁用 Job（agent-factory 自动、治理巡检、全量校准）
  - 删除废弃脚本：`benchmark_orchestrator.py` + `benchmark_output_consumer.py`
  - 启用 `daily_todo_digest_daily`，降频 `algo_micro_optimizer` → 24h

- [x] [2026-03-28] **安全加固**：`git_sync_push_runner.py` 三层审核
  - 第一层：路径过滤（已有）
  - 第二层：6 类敏感信息内容正则扫描（API Key / Token / Private Key / Password / Bearer / Generic Token）
  - 第三层：Agent 审核摘要（`.workflow/sync-reviews/` 异步复查）

- [x] [2026-03-28] **外部进化通道**：注册 3 个每日 Cron Job
  - `auto_update_daily`（上游社区，03:00）
  - `web_intel_collect_daily`（情报采集，03:30）  
  - `github_web_evolution_daily`（开源项目，04:00）

- [x] [2026-03-28] **异常巡检增强**：`unified_exception_logger.py`
  - 新增第 7 类异常分类：`path_validation_error`（路径校验错误）
  - `--abnormal-dir`：统一归档到 `/root/.openclaw/logs/abnormal/`
  - `--cleanup`：7 天 gzip 压缩 / 30 天自动删除

- [x] [2026-03-28] **advisor→TODO 自动写入**：`control_plane_optimization_advisor.py`
  - `--todo-file` 参数：自动追加建议到 TODO.md
  - MD5 指纹去重（重复建议不重复写入）
  - 风险标记：🔴高/🟡中/🟢低 + `🚨需人工审核`

- [x] [2026-03-28] **新增脚本**
  - `memory_to_skill_extractor.py`：记忆→Skill/Hook 自动封装（draft 模式，需人工激活）
  - `todo_deadline_checker.py`：截止时间解析 + 超期自动标记（`[截止:YYYY-MM-DD]` 格式）

- [x] [2026-03-28] **新增 Cron Job**
  - `advisor_todo_daily`（每日 04:15，自动派发优化建议→TODO）
  - `todo_deadline_checker_daily`（每日 00:00，截止时间检测）

- [x] [2026-03-28] **协议文档化**
  - `docs/trace_id_protocol.md`：trace_id 全链路注入协议
  - `docs/task_dispatch_protocol.md`：任务派发 5 要素确认协议
  - `docs/error_driven_evolution.md`：错误驱动进化协议 + fault_kb 结构
  - `docs/execution-roadmap.md`：6 阶段执行路线图

- [x] [2026-03-28] **索引重建**
  - `CRON_TASK_INDEX.md`：5 功能大类完整索引
  - `jobs_agent_mapping.md`：4 Agent 分组映射

- [x] [2026-03-28] **Agent 模型配置更新**
  - coordinator：`gpt-5.4-mini` → `gpt-5.4`
  - tester：`gpt-5.4-mini` → `Doubao-Seed-2.0-pro`
  - doc-writer：`gpt-5.4-mini` → `Doubao-Seed-2.0-pro`
  - explorer：新增 `gpt-5.4-mini`

- [x] [2026-03-28] **policy_enforcer.py 模块拆分**（阶段 6.4）
  - 5970 行巨型单体 → 4 个独立模块（总计减少 24%）
  - `policy_defaults.py`（946行）：DEFAULT_* 配置常量
  - `policy_utils.py`（129行）：工具函数和数据类
  - `policy_cli.py`（429行）：CLI 解析器和 main() 入口
  - `policy_enforcer.py`（4526行）：PolicyEnforcer 类核心逻辑
  - 零功能变更，完全向后兼容

---

## 2026-03 已完成

### 核心自进化闭环（4 层循环）

- [x] [2026-03-25] **`ops_governance_evolution_incremental`** — 经验提取引擎
  - 每 6 小时自动扫描运行日志 / 记忆 / 错误记录
  - 提取可优化的通用流程、BUG、最佳实践
  - 脚本：`governance_evolution_runner.py`（69KB）

- [x] [2026-03-25] **`optimize_self_evolution_summary`** — 行为蒸馏器
  - 每天凌晨 4:37 自动执行
  - 仅有新增优化项时才产出通知（NO_REPLY 机制）

- [x] [2026-03-25] **`reviewer_incremental_daily_4am`** — 评审落地器

- [x] [2026-03-25] **`ops_git_sync_push`** — 仓库同步器
  - 路径过滤（第一层审核）：排除 sessions/experience/memory/runtime 等目录

### 任务管理系统

- [x] [2026-03-25] **`todo_patrol`** — TODO 巡检与自动派发
- [x] [2026-03-25] **`task_center`** — 任务中心数据库（SQLite，4 张核心表含 trace_id）

### 异常巡检

- [x] [2026-03-25] **`unified_exception_logger`** — 系统异常分类巡检（6 类分类 + MD5 指纹去重）

### HardFlow 多角色工作流

- [x] [2026-03-25] **多角色 Agent 体系** — 13 个专业 Agent
- [x] [2026-03-25] **HardFlow 门禁系统** — G0-G6 七道门禁
- [x] [2026-03-25] **PUA 行为执行器** — Pressure/Urgency/Agency 机制

### 可观测性基础设施

- [x] [2026-03-25] **`chat_output` 通知框架** — 统一消息输出 + NO_REPLY 机制
- [x] [2026-03-25] **`workflow_views`** — 工作流可视化视图

### 安全与治理

- [x] [2026-03-25] **仓库隔离架构** — `.openclaw`（本地）与 backup（同步）严格分离
- [x] [2026-03-25] **`claim_verification_auditor`** — 反幻觉审计器

### 反馈与进化

- [x] [2026-03-25] **`upgrade_feedback_runner`** — 升级反馈收集器
- [x] [2026-03-27] **`fault_knowledge_base`** — 故障知识库
- [x] [2026-03-27] **`workflow_builder`** — 工作流模板生成器

### 外部进化

- [x] [2026-03-25] **`auto_update_install_runner.py`** — 上游社区更新检测脚本
- [x] [2026-03-25] **`web_intel_collect_runner.py`** — 情报采集脚本
- [x] [2026-03-25] **`github_web_evolution_runner.py`** — 开源项目进化脚本

---

## 参考

- 待办事项 → [todo.md](todo.md)
- 定时任务索引 → [scripts/openclaw-ops/CRON_TASK_INDEX.md](scripts/openclaw-ops/CRON_TASK_INDEX.md)
- Agent 映射 → [cron/jobs_agent_mapping.md](cron/jobs_agent_mapping.md)
- 执行路线图 → [docs/execution-roadmap.md](docs/execution-roadmap.md)
- 2026-04-24: 修复 project delivery runtime 安装器的 ops 根目录 runner 命名兼容；`runtime_installer.py` 现在同时安装 `pipeline_runner.py` 与 `project_delivery_pipeline.py`，`pipeline_runner.py` 会在安装态优先解析同级 `ops/policy`，确保安装到 Hermes runtime 后的 `ops/hermes_profile_smoke.py` 可以按同目录加载 runner 并完成 echo smoke，新增回归断言覆盖两个入口文件与安装态 smoke。
- 2026-04-25: 将 SmartMultiPlatformArbitrage nofx Discord live evidence bridge 的归属文档迁入 hardflow：新增 `docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`，明确工作流代码归 hardflow、套利业务代码归 SmartMultiPlatformArbitrage，并记录 nofx runtime 路径、live 阶段证据、deployment 边界和验收 run id。
- 2026-04-25: 修复 nofx Discord Hermes live pipeline 卡顿与入口不稳：profile SOUL 改为绝对 `/home/arbops/.local/bin/smart-arb-pipeline`，`smart_arb_live_bridge.py` verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，新增显式 `--verification-command-timeout-seconds`，并在 nofx 安装态通过 echo live smoke `codex-spreadagent-20260425T154609125415Z` 与真实 verification smoke。
- 2026-04-27: 修复 nofx Discord 工作流自修循环和未验收业务补丁残留，并已部署到 nofx：需求/方案 artifact 保留用户具体目标，不再泛化为通用 pipeline 模板；`verification` / `code_review` 阻塞时自动反向撤回已应用到主项目目录的 code workspace patch；两个 nofx profile SOUL 增加并安装“工作流自修例外”，用户明确说“不要走工作流”或目标是修 pipeline/bridge/profile 时只做只读诊断并提示外部 SSH/operator 修复；远端 75 项定向测试、gateway connected 和内控 API smoke 已通过。

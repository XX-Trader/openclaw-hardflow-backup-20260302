# SmartMultiPlatformArbitrage nofx live evidence bridge

> 最后验证：2026-04-27 10:30 Asia/Shanghai
> 适用范围：nofx 上 SmartMultiPlatformArbitrage 的 Discord 需求入口、Hermes runtime、项目交付优先工作流 live 证据桥。

## 归属边界

- 工作流代码、runtime installer、pipeline runner、live evidence bridge 归属本仓库 `openclaw-hardflow-backup-20260302`。
- 套利业务代码、策略脚本、FastAPI 和项目记忆归属 `SmartMultiPlatformArbitrage`。
- Discord token、模型 API key、auth 文件、SQLite 运行库等只允许存在运行环境，不写入本仓库。

## nofx 运行路径

| 项 | 路径 / 值 |
|----|-----------|
| 服务器 | `nofx` / `43.153.157.46` |
| 运行用户 | `arbops` |
| hardflow 仓库 | `/home/arbops/projects/openclaw-hardflow-backup-20260302` |
| SmartMultiPlatformArbitrage 仓库 | `/home/arbops/projects/SmartMultiPlatformArbitrage` |
| Hermes runtime | `/home/arbops/.hermes` |
| 标准入口 | `/home/arbops/.local/bin/smart-arb-pipeline` |
| 内控 FastAPI | `tmux` 会话 `smart-arb-api`，监听 `127.0.0.1:18080` |
| nofx profile SOUL 模板 | `config/nofx-hermes-profiles/<profile>/SOUL.md` |

## 当前 agent/model 口径

2026-04-27 远程核对后，nofx 当前运行态按三层理解：

1. **live 入口**：只有两个 Hermes Discord profile，`arbitrageagent` 与 `spreadagent`。
2. **workflow 层**：`/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`，主阶段为 `research -> 需求讨论 -> 方案 -> 编码 -> 测试 -> review -> deployment -> memory_writeback`。
3. **逻辑 owner 层**：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` 用于阶段分工、隔离 workspace 和 Task Center 留痕，不是独立常驻 agent 进程。
4. **cron 责任标签**：`ops-agent`、`project-agent`、`optimization-agent` 等用于定时任务归属；是否真的有运行中的 agent，要继续看具体 profile、tmux、session/run id 或命令证据。

| profile | 入口类型 | 模型 provider | 默认模型 | gateway |
|---------|----------|---------------|----------|---------|
| `arbitrageagent` | Hermes Discord profile | `openai-codex` | `gpt-5.5` | `running` |
| `spreadagent` | Hermes Discord profile | `openai-codex` | `gpt-5.5` | `running` |

服务器当前还没有可解释为“14 个常驻 agent”的注册目录：`/home/arbops/.hermes/agents`、`/home/arbops/.openclaw/agents`、`/root/.openclaw/agents`、`/home/arbops/.codex/agents`、`/root/.codex/agents` 均未作为 live agent 注册表存在。2026-03 的 14 Agent 文档仅保留为历史 OpenClaw 注册表快照，不代表 nofx 当前 Hermes workflow runtime。

安装态版本也要分层：2026-04-27 核对时 nofx hardflow 仓库仍在 `44b4dae`，安装态 `/home/arbops/.hermes/ops/repo_hygiene_reviewer.py` 尚不存在，`source_registry_watcher` cron 仍是每周日；本仓库最新 `e45e0af` 的 2 天来源监控、仓库精简巡检和 `git_publish` 需要再次 pull + runtime installer 后才会成为服务器运行态。

## 安装产物

runtime installer 会把以下 hardflow 脚本安装到 Hermes ops 目录：

- `/home/arbops/.hermes/ops/smart_arb_live_bridge.py`
- `/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py`
- `/home/arbops/.hermes/ops/pipeline_runner.py`
- `/home/arbops/.hermes/ops/project_delivery_pipeline.py`
- `/home/arbops/.hermes/ops/runtime_installer.py`

`/home/arbops/.local/bin/smart-arb-pipeline` 是指向 `/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py` 的软链接。

## live 流程

Discord 入口默认就是真实执行：

```bash
/home/arbops/.local/bin/smart-arb-pipeline --profile arbitrageagent --source discord --requirement "<需求文本>"
```

默认输出面向聊天频道：`smart-arb-pipeline` 会把 runner JSON 转成中文状态卡，展示 run id、总状态、Task Center 任务、每个阶段对应的 agent、完成/阻塞情况、agent 输出摘要、阻塞证据、自动修复判断和关键证据。需要机器读取原始状态时，加 `--emit-json`；排障时需要原始 runner 输出时，加 `--no-chat-summary`。

live 默认注入以下命令证据：

| 阶段 | 责任 | 证据 |
|------|------|------|
| `external_research` | Hermes / web-agent 查外部资料和项目事实 | `command_external_research_*` |
| `requirements_discussion` | project-agent 与 reviewer 双 AI 讨论需求 | `command_requirements_discussion_*` |
| `code_execution` | Hermes headless 执行代码改动 | `command_code_execution_*` |
| `verification` | 固定命令验证，默认 `git diff --check` 与 `compileall -q scripts strategy_runtime`，单命令超时默认 300 秒 | `command_verification_*` |
| `code_review` | reviewer 做代码审查 | `command_code_review_*` |
| `deployment` | 普通服务/API 改动时重启内控 FastAPI 并做状态接口 smoke；memory/docs-only 或 no service control/no deployment/no restart 需求会跳过该命令 | `command_deployment_*` |
| `memory_writeback` | 写项目记忆 changelog | `command_memory_writeback_*` |
| `git_publish` | 在验证、代码审查、deployment、验收和 memory writeback 通过后，使用中文提交说明执行受控 commit/push；禁止 force push 和含密钥 diff | `command_git_publish_*` |

缺少任一关键阶段真实命令证据时，pipeline runner 会阻断并写入 `failed_stage` 与 `next_action`。

### Discord 状态卡与自动修复

Discord 状态卡必须回答三个问题：

1. 本轮哪些 agent / stage 做了什么。
2. 达到了什么结果，关键输出是什么。
3. 如果卡住，具体因为什么卡住，系统是否已自行回流修复。

当前入口会读取 `command-runs/*.json`，从 stage command 的 stdout、stderr、error 中抽取摘要写入 `agent 输出摘要`。如果 pipeline 进入 `blocked`，状态卡会追加 `阻塞原因`，包含失败阶段、stage detail、命令输出或 artifact 摘要。

自动修复策略：

- `run_external_research`、`return_to_code_execution`、`return_to_deployment`、`fix_memory_writeback` 默认自动回流，最多 2 次，可用 `--auto-repair-attempts` 或 `SMART_ARB_AUTO_REPAIR_ATTEMPTS` 调整。
- 每次回流使用 `<原 run_id>-repair<n>` 独立 run id，避免覆盖上一轮 `command-runs/*.json`。
- 每次回流前，入口把上一轮失败证据写入上一轮失败 run 目录的 `auto_repair_context_<n>.md`，并通过 `PIPELINE_REPAIR_CONTEXT_FILE` / `SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE` 或内联 `PIPELINE_REPAIR_CONTEXT` 传给 live bridge；后续 Hermes stage prompt 会看到上一轮失败原因。
- 自动回流仍重新走完整 coordinator pipeline，不允许直接绕过验证、代码审查、部署、记忆写回或 Git 发布。
- 状态卡默认展开最多 24 条命令摘要，可用 `SMART_ARB_CHAT_COMMAND_LIMIT` 或 `--chat-command-limit` 调整；Discord profile 必须把中文状态卡回传到聊天频道，长消息分段发送，不能只给 run id、失败阶段和证据目录。
- 非代码 Hermes 阶段不允许直接编辑 `research_report.md`、`requirements_discussion.md`、`verification_report.md` 等 pipeline artifacts；stage evidence 必须通过 stdout/final answer 返回，由 runner 持久化。bridge 会在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，避免 agent 通过环境变量直接定位并覆盖 artifact。
- `external_research` 对本地记忆蒸馏、环境基线、权限修复这类不依赖互联网的问题，可以输出 `NO_EXTERNAL_LOOKUP_NEEDED`、原因和本地证据，作为有效 research evidence。
- 如果 Hermes CLI stdout/stderr 只输出 `session_id: ...`，bridge 会在 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json` 恢复最新 assistant 内容并先脱敏，再用于 stage pass 判定和状态卡输出。
- 检测到正向要求读取/输出/使用凭证、API key、token/private key、session_id，或启用真实交易、下单、资金转移、提现、破坏性数据操作或 force push 等高风险内容时，不自动继续，状态卡显示需要人工确认。`不得泄露凭证`、`不启动真实交易`、`不下单不划转` 这类纯否定式安全约束不会单独触发高风险阻断；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]` 仍是 high，`No need for ...` / `Do not need ...` 可作为否定式预脱敏噪音回流；如果同一段里还有 `but needs credentials`、`但需要资金操作` 等正向子句，仍按高风险处理。
- 前序 artifact 注入后续 Hermes prompt 前会脱敏常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack token、HF token、Google OAuth/API key 和 AWS access key，避免修复上下文扩散短格式 secret。

### 当前 fan-out 与 workspace 边界

当前 nofx `smart-arb-pipeline --live` 已经具备 **每 agent 独立 workspace 与命令证据留痕**，但还不是严格意义上的宿主 native 并发 agent fan-out。

- `pipeline_runner.py` 固定按阶段 owner 创建 Git worktree：`agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_ID`、`PIPELINE_AGENT_WORKSPACE`、`PIPELINE_AGENT_REPO_DIR`、`PIPELINE_AGENT_WORKSPACES_JSON` 注入 stage command。
- `--command-cwd` 必须是有 `HEAD` 的 Git 仓库，agent workspace root 必须在该仓库外部；不再提供 `shared` / `copy` 模式。
- `smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为 Hermes 阶段项目目录，避免所有阶段都在主项目目录里运行。
- `code_execution` 阶段默认在 `backend-dev` workspace 中修改代码；前端/UI/页面/交互类需求可通过 `--code-agent frontend-dev` 或入口推断切到 `frontend-dev` workspace。成功后 runner 导出 `command-runs/code_execution-1.patch`，再应用回主项目目录，然后把同一 patch 注入后续 `tester`、`reviewer`、`deployer` workspace。`git_publish` 不再对应独立 `git-master` agent，而是由 `coordinator` 负责的发布门禁。
- `git_publish` 只在前序门禁通过后执行，发布输入优先使用 `memory_writeback` 隔离工作区 patch，缺失时只回退到已验收的 `code_execution` patch，确保代码变更和写回变更一起进入发布工作区且不夹带未验收脏改动；默认提交信息为中文并脱敏，提交前运行 `git diff --check` 与 `git diff --cached --check`，并扫描 staged diff 中的密钥形态；远端冲突、认证失败、疑似密钥或 push 失败都会阻塞为 `fix_git_publish`，不做 force push。
- `command-runs/*.json`、`agent-workspaces/manifest.json`、Task Center `stage_runs.details_json` / `module_communications.details_json` 会记录 agent id、workspace、repo dir、dispatch mode 和 patch 文件。
- Task Center 中的 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester` 等字段仍然是阶段 owner 与交接记录；是否真正启动多个宿主 native session，要以 command evidence 中的独立 session/run id 为准。

因此，如果用户观察到“Hermes 在工作，但任务没有转发到其他 agent”，现在要分两层判断：第一层检查 `agent-workspaces/manifest.json` 和 `command-runs/*.json`，确认是否进入了独立 workspace；第二层检查 command evidence 中是否出现宿主 native session/run id。workspace 隔离已经落地，宿主级 native 多 agent spawn 仍需要继续接 runtime agent dispatch 能力，并把独立 session id / run id 写入 `command-runs`、Task Center 和最终状态卡。

### Discord profile 提示词规则

nofx 两个 Discord Hermes profile 的 `SOUL.md` 使用本仓库模板维护：

- `config/nofx-hermes-profiles/arbitrageagent/SOUL.md`
- `config/nofx-hermes-profiles/spreadagent/SOUL.md`

提示词必须把以下规则放在最前面：

1. 执行类请求先创建 `smart-arb-pipeline` run。
2. 不允许在 profile 会话里直接实现、部署、安装依赖、修改代码或提交 Git。
3. 只有只读状态查询、简单解释或监控数据查询可以直接处理。
4. 不允许把 Task Center 的阶段 owner 标签说成真实 native agent fan-out。

2026-04-25 19:20 已按上述模板刷新 nofx 两个 profile，并重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。2026-04-25 23:45 再次刷新为绝对入口命令，并改用 profile `start-gateway.sh` 加载 `.env` 后启动。验证结果：

- 两个 `SOUL.md` 前 10 行中文可读，不再是问号乱码。
- 两个 `SOUL.md` 中的入口均为 `/home/arbops/.local/bin/smart-arb-pipeline`，不依赖 gateway PATH。
- 两个 profile 的 `gateway_state.json` 均为 `gateway_state=running`、`discord=connected`、`last_error=null`。
- 标准入口 dry-run smoke 通过：`codex-prompt-smoke-spreadagent-20260425T112013223220Z`，状态 `completed`。
- 安装态 echo live smoke 通过：`codex-spreadagent-20260425T154609125415Z`，15 个阶段全部 completed，`verification-1.json` 的命令包含 `--verification-command-timeout-seconds 180`。
- 安装态真实 verification smoke 通过：`git diff --check` 与 `/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime` 均 returncode 0。

## 部署边界

deployment 阶段只做：

1. 重启 `smart-arb-api` tmux 会话。
2. 启动：
   ```bash
   /home/arbops/.venvs/smart-arbitrage/bin/uvicorn api.main:app --host 127.0.0.1 --port 18080
   ```
3. 检查：
   - `GET http://127.0.0.1:18080/health`
   - `GET http://127.0.0.1:18080/api/strategy/status`

deployment 阶段不会启动真实策略交易进程，不会绑定公网地址，也不会执行资金操作。

如果需求明确“不触碰服务控制 / no service control / no deployment / no restart”或属于 memory/docs-only 写回，`smart_arb_pipeline_entry.py` 不会注入 deployment command；该类任务只走验证、代码审查、acceptance 和 memory_writeback，不重启 `smart-arb-api`。如果同一需求后续明确要求 restart/deploy/重启/部署，正向 deployment 动作优先，仍会执行内控 FastAPI restart/smoke。

## 验收证据

- hardflow 提交：`8f0c1b2f Make installed ops scripts executable`
- SmartMultiPlatformArbitrage 运行代码基线：`ffc620f Add dashboard test httpx dependency`
- live echo run：`discord-arbitrageagent-20260425T075149Z`
- task-center：`project-delivery:discord-arbitrageagent-20260425T075149Z` 为 `passed`
- 真实 Hermes 只读 smoke：`external_research` 返回 `LIVE_BRIDGE_STATUS: pass`，session `20260425_155252_1a56f9`
- workspace 隔离 echo smoke：`codex-arbitrageagent-20260425T140605083467Z`，Task Center `project-delivery:codex-arbitrageagent-20260425T140605083467Z` 为 `passed`
- 该 run 的 `agent-workspaces/manifest.json` 显示 `external_research/web-agent`、`requirements_discussion/project-agent`、`requirements_discussion/reviewer`、`code_execution/backend-dev`、`verification/tester`、`code_review/reviewer`、`deployment/deployer`、`memory_writeback/coordinator` 均为独立 `worktree`；前端类任务可将 `code_execution` owner 切为 `frontend-dev`
- 该 run 的 Task Center `stage_runs.details_json` 显示命令阶段 `model_id=runtime-agent-workspace`、`dispatch_mode=isolated-agent-workspace`
- nofx dashboard/API 测试：37 项 OK
- nofx API smoke：
  - `/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`
  - `/api/strategy/status` 返回 `{"running":false,"pid":null}`
- P0-1 OpenClaw 历史蒸馏写回：`discord-spreadagent-20260426T075133316811Z`，15 个阶段 completed，verification/code_review/acceptance 均 pass；原始误阻塞 run `discord-spreadagent-20260426T065131327963Z` 现在被风险扫描判为 medium 可回流。

## 常用运维命令

安装或刷新 runtime：

```bash
python3 /home/arbops/projects/openclaw-hardflow-backup-20260302/skills/library/project-delivery-pipeline/scripts/runtime_installer.py install \
  --runtime-home /home/arbops/.hermes \
  --runtime-name hermes \
  --repo-root /home/arbops/projects/openclaw-hardflow-backup-20260302 \
  --project-memory-dir /home/arbops/projects/SmartMultiPlatformArbitrage/memory \
  --task-center-db /home/arbops/.hermes/ops/task-center/task_center.db \
  --emit-json
```

无改动 smoke：

```bash
SMART_ARB_LIVE_BRIDGE_AGENT_MODE=echo smart-arb-pipeline --live \
  --profile arbitrageagent \
  --source discord \
  --requirement "live bridge echo smoke"
```

profile 启动脚本：

```bash
/home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh
/home/arbops/.hermes/profiles/spreadagent/start-gateway.sh
```

两个脚本会设置 `HOME=/home/arbops`、`HERMES_HOME=/home/arbops/.hermes/profiles/<profile>`，加载 profile `.env`，再执行 `hermes gateway run --replace`。`.env` 必须保持 `arbops:arbops` 且 `0600`，否则 gateway 会因无法读取 profile 环境而立即退出。

verification 配置：

```bash
SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS=180
SMART_ARB_LIVE_BRIDGE_TEST_COMMAND='/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime'
```

如果没有显式 `SMART_ARB_LIVE_BRIDGE_TEST_COMMAND`，新版 bridge 默认也只做 compile smoke，不再跑全量 `unittest discover`；全量测试应放到离线 CI 或人工排障，不作为 Discord live pipeline 默认门禁。

只读 Hermes 阶段 smoke：

```bash
smart_arb_live_bridge.py --stage external_research \
  --profile arbitrageagent \
  --agent-mode hermes \
  --max-turns 4
```

本地事实足够时，`external_research` 输出必须包含 `NO_EXTERNAL_LOOKUP_NEEDED` 和本地证据；如果 Hermes 试图修改 `research_report.md` 等 artifact 并因此返回 review diff，应视为 bridge/prompt 问题，而不是 research 证据缺失。

检查内控 API：

```bash
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/api/strategy/status
```

## 安全要求

- 不把 Discord token、模型 key、auth JSON、SQLite 运行库提交到 Git。
- Git 发布阶段的提交说明、备注和变更描述必须使用中文；如需跳过 Git 发布，可传 `--skip-git-publish-command` 或设置 `SMART_ARB_SKIP_GIT_PUBLISH_COMMAND=1`。
- `--live-bridge-no-yolo` 可关闭 headless 代码执行的 yolo 模式。
- profile 配置必须归属运行用户 `arbops`；如果 `config.yaml` 被 root 写成 `0600`，Discord `/sethome` 会因为无法写入 profile 配置而失败。
- nofx 当前按早期高信任模式配置：两个 Discord profile 关闭命令审批和 security scan，`arbops` 通过 `/etc/sudoers.d/90-arbops-hermes` 获得无密码 sudo，用于服务器级修复和部署。
- 真实交易启动必须另走 SmartMultiPlatformArbitrage 的策略运行手册；本 bridge 的 deployment 只负责内控 API。

# SmartMultiPlatformArbitrage nofx live evidence bridge

> 最后验证：2026-04-25 22:06 Asia/Shanghai
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

只有明确要求只验证流程、不改代码时，才追加 `--dry-run`。`SMART_ARB_PIPELINE_DEFAULT_LIVE=0` 可临时恢复旧的默认模拟模式。

默认输出面向聊天频道：`smart-arb-pipeline` 会把 runner JSON 转成中文状态卡，展示 run id、总状态、Task Center 任务、每个阶段对应的 agent、完成/阻塞情况和关键证据。需要机器读取原始状态时，加 `--emit-json`；排障时需要原始 runner 输出时，加 `--no-chat-summary`。

live 默认注入以下命令证据：

| 阶段 | 责任 | 证据 |
|------|------|------|
| `external_research` | Hermes / web-agent 查外部资料和项目事实 | `command_external_research_*` |
| `requirements_discussion` | project-agent 与 reviewer 双 AI 讨论需求 | `command_requirements_discussion_*` |
| `code_execution` | Hermes headless 执行代码改动 | `command_code_execution_*` |
| `verification` | 固定命令验证，默认 `git diff --check` 与 `compileall -q scripts strategy_runtime`，单命令超时默认 300 秒 | `command_verification_*` |
| `code_review` | reviewer 做代码审查 | `command_code_review_*` |
| `deployment` | 只重启内控 FastAPI 并做状态接口 smoke | `command_deployment_*` |
| `memory_writeback` | 写项目记忆 changelog | `command_memory_writeback_*` |

缺少任一关键阶段真实命令证据时，pipeline runner 会阻断并写入 `failed_stage` 与 `next_action`。

### 当前 fan-out 与 workspace 边界

当前 nofx `smart-arb-pipeline --live` 已经具备 **每 agent 独立 workspace 与命令证据留痕**，但还不是严格意义上的宿主 native 并发 agent fan-out。

- `pipeline_runner.py` 固定按阶段 owner 创建 Git worktree：`agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_ID`、`PIPELINE_AGENT_WORKSPACE`、`PIPELINE_AGENT_REPO_DIR`、`PIPELINE_AGENT_WORKSPACES_JSON` 注入 stage command。
- `--command-cwd` 必须是有 `HEAD` 的 Git 仓库，agent workspace root 必须在该仓库外部；不再提供 `shared` / `copy` 模式。
- `smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为 Hermes 阶段项目目录，避免所有阶段都在主项目目录里运行。
- `code_execution` 阶段在 `backend-dev` workspace 中修改代码；成功后 runner 导出 `command-runs/code_execution-1.patch`，再应用回主项目目录，然后把同一 patch 注入后续 `tester`、`reviewer`、`deployer` workspace。
- `command-runs/*.json`、`agent-workspaces/manifest.json`、Task Center `stage_runs.details_json` / `module_communications.details_json` 会记录 agent id、workspace、repo dir、dispatch mode 和 patch 文件。
- Task Center 中的 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`tester` 等字段仍然是阶段 owner 与交接记录；是否真正启动多个宿主 native session，要以 command evidence 中的独立 session/run id 为准。

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

## 验收证据

- hardflow 提交：`8f0c1b2f Make installed ops scripts executable`
- SmartMultiPlatformArbitrage 运行代码基线：`ffc620f Add dashboard test httpx dependency`
- live echo run：`discord-arbitrageagent-20260425T075149Z`
- task-center：`project-delivery:discord-arbitrageagent-20260425T075149Z` 为 `passed`
- 真实 Hermes 只读 smoke：`external_research` 返回 `LIVE_BRIDGE_STATUS: pass`，session `20260425_155252_1a56f9`
- workspace 隔离 echo smoke：`codex-arbitrageagent-20260425T140605083467Z`，Task Center `project-delivery:codex-arbitrageagent-20260425T140605083467Z` 为 `passed`
- 该 run 的 `agent-workspaces/manifest.json` 显示 `external_research/web-agent`、`requirements_discussion/project-agent`、`requirements_discussion/reviewer`、`code_execution/backend-dev`、`verification/tester`、`code_review/reviewer`、`deployment/deployer`、`memory_writeback/coordinator` 均为独立 `worktree`
- 该 run 的 Task Center `stage_runs.details_json` 显示命令阶段 `model_id=runtime-agent-workspace`、`dispatch_mode=isolated-agent-workspace`
- nofx dashboard/API 测试：37 项 OK
- nofx API smoke：
  - `/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`
  - `/api/strategy/status` 返回 `{"running":false,"pid":null}`

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

检查内控 API：

```bash
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/api/strategy/status
```

## 安全要求

- 不把 Discord token、模型 key、auth JSON、SQLite 运行库提交到 Git。
- `--live-bridge-no-yolo` 可关闭 headless 代码执行的 yolo 模式。
- profile 配置必须归属运行用户 `arbops`；如果 `config.yaml` 被 root 写成 `0600`，Discord `/sethome` 会因为无法写入 profile 配置而失败。
- 真实交易启动必须另走 SmartMultiPlatformArbitrage 的策略运行手册；本 bridge 的 deployment 只负责内控 API。

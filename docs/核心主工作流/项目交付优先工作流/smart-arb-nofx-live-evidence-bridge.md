# SmartMultiPlatformArbitrage nofx live evidence bridge

> 最后验证：2026-04-25 16:09 Asia/Shanghai  
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

## 安装产物

runtime installer 会把以下 hardflow 脚本安装到 Hermes ops 目录：

- `/home/arbops/.hermes/ops/smart_arb_live_bridge.py`
- `/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py`
- `/home/arbops/.hermes/ops/pipeline_runner.py`
- `/home/arbops/.hermes/ops/project_delivery_pipeline.py`
- `/home/arbops/.hermes/ops/runtime_installer.py`

`/home/arbops/.local/bin/smart-arb-pipeline` 是指向 `/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py` 的软链接。

## live 流程

Discord 入口使用：

```bash
smart-arb-pipeline --live --profile arbitrageagent --source discord --requirement "<需求文本>"
```

`--live` 默认注入以下命令证据：

| 阶段 | 责任 | 证据 |
|------|------|------|
| `external_research` | Hermes / web-agent 查外部资料和项目事实 | `command_external_research_*` |
| `requirements_discussion` | project-agent 与 reviewer 双 AI 讨论需求 | `command_requirements_discussion_*` |
| `code_execution` | Hermes headless 执行代码改动 | `command_code_execution_*` |
| `verification` | 固定命令验证，默认 `git diff --check` 与 unittest | `command_verification_*` |
| `code_review` | reviewer 做代码审查 | `command_code_review_*` |
| `deployment` | 只重启内控 FastAPI 并做状态接口 smoke | `command_deployment_*` |
| `memory_writeback` | 写项目记忆 changelog | `command_memory_writeback_*` |

缺少任一关键阶段真实命令证据时，pipeline runner 会阻断并写入 `failed_stage` 与 `next_action`。

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
- 真实交易启动必须另走 SmartMultiPlatformArbitrage 的策略运行手册；本 bridge 的 deployment 只负责内控 API。

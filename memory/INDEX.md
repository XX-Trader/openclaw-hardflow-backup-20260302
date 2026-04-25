# 项目记忆索引

最后更新：2026-04-25

## 阅读顺序

1. `RUNBOOK.md`：本仓库工作流、runtime 安装和远程巡检命令。
2. `PITFALLS.md`：已确认的排障结论、历史坑和避免误判的边界。
3. `../docs/INDEX.md`：长期文档导航与工作流事实源。
4. `../todo.md` / `../done.md`：当前任务盘和完成记录。

## 当前重点

- nofx 上 SmartMultiPlatformArbitrage 的项目交付入口由本仓库提供：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py` 和 runtime installer。
- nofx 当前 live bridge 固定使用每阶段 owner 的独立 Git worktree：runner 会创建 `agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_REPO_DIR` 注入 Hermes bridge；不再暴露 `shared` / `copy` 模式。
- `code_execution` 在 `backend-dev` workspace 产出 diff，runner 会把 diff 应用回主项目目录，并注入后续 tester/reviewer/deployer workspace。
- 最后远端 smoke：`codex-arbitrageagent-20260425T140605083467Z`，Task Center 为 `passed`；命令阶段 `model_id=runtime-agent-workspace`，`dispatch_mode=isolated-agent-workspace`。
- Task Center 中的 agent 字段仍表示责任标签和交接记录；要声称真正 native fan-out，仍需 command evidence 中出现独立宿主 session/run id。
- 如果要让任务真正转发到 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`tester` 等宿主 native agent，需要继续在 runtime adapter 增加 session dispatch 能力，而不是只修改 stage prompt。
- nofx SSH 曾出现原生 `ssh` 空退和 Paramiko banner 被拒；远程排障需要低频单连接重试，避免并发连接触发服务端临时拒绝。

## 安全边界

- 不记录 Discord token、模型 API key、OAuth auth、Cookie、私钥或交易所凭证。
- 远程事实以 nofx 实时命令、Hermes profile 状态、Task Center DB、pipeline run artifacts 和服务日志为准。

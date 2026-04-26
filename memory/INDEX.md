# 项目记忆索引

最后更新：2026-04-26

## 阅读顺序

1. `RUNBOOK.md`：本仓库工作流、runtime 安装和远程巡检命令。
2. `PITFALLS.md`：已确认的排障结论、历史坑和避免误判的边界。
3. `../docs/INDEX.md`：长期文档导航与工作流事实源。
4. `../todo.md` / `../done.md`：当前任务盘和完成记录。

## 当前重点

- nofx 上 SmartMultiPlatformArbitrage 的项目交付入口由本仓库提供：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py` 和 runtime installer。
- nofx 两个 Discord Hermes profile 已按本机 WSL 的有效模式改为 profile 级 `approvals.mode: 'off'`；遇到 `Command Approval Required` 先查 `/home/arbops/.hermes/profiles/<profile>/config.yaml`，不要只看全局配置。
- nofx Discord profile 的 SOUL 现在使用绝对入口 `/home/arbops/.local/bin/smart-arb-pipeline`；gateway 通过 profile `start-gateway.sh` 加载 `.env`，`.env` 必须是 `arbops:arbops` 且 `0600`。
- nofx live verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，并通过 `--verification-command-timeout-seconds` 显式记录单命令超时；不要再把全量 `unittest discover` 当 Discord live 默认门禁。
- nofx 当前 live bridge 固定使用每阶段 owner 的独立 Git worktree：runner 会创建 `agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_REPO_DIR` 注入 Hermes bridge；不再暴露 `shared` / `copy` 模式。
- nofx Discord 状态卡会读取 `command-runs/*.json`，展示 agent 输出摘要、阻塞证据和自动修复判断；`run_external_research` / `return_to_code_execution` / `return_to_deployment` / `fix_memory_writeback` 会自动回流最多 2 次，高风险凭证、真实交易、资金或破坏性数据操作仍停人工确认。
- 状态卡默认展开最多 24 条 command report，可用 `SMART_ARB_CHAT_COMMAND_LIMIT` / `--chat-command-limit` 调整；profile SOUL 要求失败时把完整中文状态卡发回聊天频道，不能只回 run id、失败阶段和证据目录。
- Hermes CLI 有时只在 stdout/stderr 返回 `session_id`，实际 assistant 内容落在 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json`；live bridge 会在固定 profile session 目录内恢复最新 assistant 输出并先脱敏，再用于 stage pass 判定和状态卡摘要。
- nofx live bridge 的非代码 Hermes 阶段只允许在 stdout/final answer 返回证据，不允许直接写 `research_report.md` 等 pipeline artifacts；Hermes 子进程环境会剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，`external_research` 可用 `NO_EXTERNAL_LOOKUP_NEEDED` 表示本地事实已足够，不能因此被 live gate 判失败。
- 自动修复风险扫描按分句剥离“不得泄露凭证 / 不启动真实交易 / 不下单不划转”等纯否定式安全边界；已脱敏字段如果表达 `Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]` 或 `Need session_id=[REDACTED]` 仍按高风险停人工确认，`No need for ...` / `Do not need ...` 这类否定噪音可自动回流。混合句里只要仍有正向要求读取凭证、启用实盘、资金操作或破坏性命令，就会停人工确认。
- 需求明确 memory/docs-only、no service control、no deployment 或 no restart 时，entry 不注入 deployment command；如果同一需求后续明确要求重启/部署，正向 deployment 动作优先，普通 API/服务改动也会注入 deployment bridge 做内控 FastAPI smoke。
- 前序 artifact 注入后续 Hermes prompt 前会做敏感信息脱敏，覆盖常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack token、HF token、Google OAuth/API key、AWS access key 等形态。
- `code_execution` 在 `backend-dev` workspace 产出 diff，runner 会把 diff 应用回主项目目录，并注入后续 tester/reviewer/deployer workspace。
- 最后远端 smoke：`codex-arbitrageagent-20260425T140605083467Z`，Task Center 为 `passed`；命令阶段 `model_id=runtime-agent-workspace`，`dispatch_mode=isolated-agent-workspace`。
- Task Center 中的 agent 字段仍表示责任标签和交接记录；要声称真正 native fan-out，仍需 command evidence 中出现独立宿主 session/run id。
- 如果要让任务真正转发到 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`tester` 等宿主 native agent，需要继续在 runtime adapter 增加 session dispatch 能力，而不是只修改 stage prompt。
- nofx SSH 曾出现原生 `ssh` 空退和 Paramiko banner 被拒；远程排障需要低频单连接重试，避免并发连接触发服务端临时拒绝。

## 安全边界

- 不记录 Discord token、模型 API key、OAuth auth、Cookie、私钥或交易所凭证。
- 远程事实以 nofx 实时命令、Hermes profile 状态、Task Center DB、pipeline run artifacts 和服务日志为准。

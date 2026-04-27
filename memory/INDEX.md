# 项目记忆索引

最后更新：2026-04-27

## 阅读顺序

1. `RUNBOOK.md`：本仓库工作流、runtime 安装和远程巡检命令。
2. `PITFALLS.md`：已确认的排障结论、历史坑和避免误判的边界。
3. `DECISIONS.md`：近期架构裁决和被拒方案。
4. `TASK_HISTORY.md`：重要任务完成记录、验证证据和关联文件。
5. `../docs/INDEX.md`：长期文档导航与工作流事实源。
6. `../todo.md` / `../done.md`：当前任务盘和完成记录。

## 当前重点

- nofx 上 SmartMultiPlatformArbitrage 的项目交付入口由本仓库提供：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py` 和 runtime installer。
- nofx 当前 agent/model 口径已修正：live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`；2026-04-27 服务器实测两者均为 `model.provider=openai-codex`、`model.default=gpt-5.5`、`gateway_state=running`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`；cron / Task Center 定时任务只挂 `coordinator/project-agent`，不再注册 `ops-agent/optimization-agent`。以上都不是 nofx 上 14 个常驻 agent 进程；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
- nofx 两个 Discord Hermes profile 已按本机 WSL 的有效模式改为 profile 级 `approvals.mode: 'off'`；遇到 `Command Approval Required` 先查 `/home/arbops/.hermes/profiles/<profile>/config.yaml`，不要只看全局配置。
- nofx Discord profile 的 SOUL 现在使用绝对入口 `/home/arbops/.local/bin/smart-arb-pipeline`；gateway 通过 profile `start-gateway.sh` 加载 `.env`，`.env` 必须是 `arbops:arbops` 且 `0600`。
- nofx live verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，并通过 `--verification-command-timeout-seconds` 显式记录单命令超时；不要再把全量 `unittest discover` 当 Discord live 默认门禁。
- nofx 当前 live bridge 固定使用每阶段 owner 的独立 Git worktree：runner 会创建 `agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_REPO_DIR` 注入 Hermes bridge；不再暴露 `shared` / `copy` 模式。
- nofx Discord 状态卡会读取 `command-runs/*.json`，展示 agent 输出摘要、阻塞证据和自动修复判断；`run_external_research` / `return_to_code_execution` / `return_to_deployment` / `fix_memory_writeback` 会自动回流最多 2 次，高风险凭证、真实交易、资金或破坏性数据操作仍停人工确认。
- 本仓库已新增 `backlog_runner.py` 与 `backlog_runner_30m` cron，用于从 Task Center 自动挑选低风险、无需人工确认或澄清的待办继续调用 `smart-arb-pipeline`。该能力解决“任务只有用户在聊天里触发才继续推进”的断点；高风险、需确认、需澄清任务仍必须停在 `human_inbox.py`。
- 状态卡默认展开最多 24 条 command report，可用 `SMART_ARB_CHAT_COMMAND_LIMIT` / `--chat-command-limit` 调整；profile SOUL 要求失败时把完整中文状态卡发回聊天频道，不能只回 run id、失败阶段和证据目录。
- Hermes CLI 有时只在 stdout/stderr 返回 `session_id`，实际 assistant 内容落在 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json`；live bridge 会在固定 profile session 目录内恢复最新 assistant 输出并先脱敏，再用于 stage pass 判定和状态卡摘要。
- nofx live bridge 的非代码 Hermes 阶段只允许在 stdout/final answer 返回证据，不允许直接写 `research_report.md` 等 pipeline artifacts；Hermes 子进程环境会剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，`external_research` 可用 `NO_EXTERNAL_LOOKUP_NEEDED` 表示本地事实已足够，不能因此被 live gate 判失败。
- 自动修复风险扫描按分句剥离“不得泄露凭证 / 不启动真实交易 / 不下单不划转”等纯否定式安全边界；已脱敏字段如果表达 `Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]` 或 `Need session_id=[REDACTED]` 仍按高风险停人工确认，`No need for ...` / `Do not need ...` 这类否定噪音可自动回流。混合句里只要仍有正向要求读取凭证、启用实盘、资金操作或破坏性命令，就会停人工确认。
- 需求明确 memory/docs-only、no service control、no deployment 或 no restart 时，entry 不注入 deployment command；如果同一需求后续明确要求重启/部署，正向 deployment 动作优先，普通 API/服务改动也会注入 deployment bridge 做内控 FastAPI smoke。
- 最新 nofx 安装记录：2026-04-26 17:03 已把提交 `edd05e23` 拉到 `/home/arbops/projects/openclaw-hardflow-backup-20260302` 并运行 runtime installer；安装态入口 smoke `cli-arbitrageagent-20260426T090250542271Z` 14/14 completed，详见 `RUNBOOK.md`。
- 2026-04-27 服务器复核：nofx hardflow 仓库当前仍在 `44b4dae`，安装态 `/home/arbops/.hermes/ops` 还没有 `repo_hygiene_reviewer.py` / `backlog_runner.py`，cron 中 `source_registry_watcher` 仍是每周日；本仓库最新 `e45e0af` 之后的 `git_publish`、2 天 `source_registry_watcher`、`repo_hygiene_reviewer_2d` 和 `backlog_runner_30m` 需要再次 pull + runtime installer 后才会成为 nofx 运行态。
- 前序 artifact 注入后续 Hermes prompt 前会做敏感信息脱敏，覆盖常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack token、HF token、Google OAuth/API key、AWS access key 等形态。
- `code_execution` 默认在 `backend-dev` workspace 产出 diff；前端/UI/页面/交互类需求可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。runner 会把 diff 应用回主项目目录，并注入后续 tester/reviewer/deployer workspace。
- `git_publish` 是可选发布门禁，只在验证、代码审查、deployment（如有）、验收和记忆回写通过后执行；提交说明、备注和变更描述必须使用中文，提交前运行 `git diff --check` 与 `git diff --cached --check`，并扫描 staged diff 中的密钥形态，失败回流为 `fix_git_publish`。
- `source_registry_watcher` 与 `repo_hygiene_reviewer` 默认每 2 天执行一次；前者只检查已注册来源，后者由 `coordinator` 只读扫描冗余、冲突、缓存、重复文件并创建人工确认候选，不自动删除、不自动推送。
- 到期 TODO 已改为风险分流：低风险进入 `dispatch_pipeline` 自动候选并由 backlog runner 推进；高风险、生产、部署、资金、凭证、删除等候选仍停 `human_inbox.py` 等待人工确认。
- 双 AI 审核现在有真实产物门禁：需求、方案、代码三个 review 阶段都需要两条不同命令、不同 `reviewer_role`（`reviewer-a`/`reviewer-b`）的 reviewer command report，且都输出对应 `Final verdict` 才放行。
- 最后远端 smoke：`codex-arbitrageagent-20260425T140605083467Z`，Task Center 为 `passed`；命令阶段 `model_id=runtime-agent-workspace`，`dispatch_mode=isolated-agent-workspace`。
- Task Center 中的 agent 字段仍表示责任标签和交接记录；要声称真正 native fan-out，仍需 command evidence 中出现独立宿主 session/run id。
- 如果要让任务真正转发到 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester` 等宿主 native agent，需要继续在 runtime adapter 增加 session dispatch 能力，而不是只修改 stage prompt。
- nofx SSH 曾出现原生 `ssh` 空退和 Paramiko banner 被拒；远程排障需要低频单连接重试，避免并发连接触发服务端临时拒绝。

## 安全边界

- 不记录 Discord token、模型 API key、OAuth auth、Cookie、私钥或交易所凭证。
- 远程事实以 nofx 实时命令、Hermes profile 状态、Task Center DB、pipeline run artifacts 和服务日志为准。

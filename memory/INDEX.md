# 项目记忆索引

最后更新：2026-04-28

## 阅读顺序

1. `RUNBOOK.md`：本仓库工作流、runtime 安装和远程巡检命令。
2. `DEPLOYMENT.md`：nofx 部署目标、安装命令、当前安装态和验收记录。
3. `PITFALLS.md`：已确认的排障结论、历史坑和避免误判的边界。
4. `DECISIONS.md`：近期架构裁决和被拒方案。
5. `TASK_HISTORY.md`：重要任务完成记录、验证证据和关联文件。
6. `../docs/INDEX.md`：长期文档导航与工作流事实源。
7. `../todo.md` / `../done.md`：当前任务盘和完成记录。

## 当前重点

- nofx 上 SmartMultiPlatformArbitrage 的项目交付入口由本仓库提供：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py` 和 runtime installer。
- nofx 当前 agent/model 口径已修正：live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`；2026-04-27 服务器实测两者均为 `model.provider=openai-codex`、`model.default=gpt-5.5`、`gateway_state=running`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`；cron / Task Center 定时任务只挂 `coordinator/project-agent`，不再注册 `ops-agent/optimization-agent`。以上都不是 nofx 上 14 个常驻 agent 进程；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
- nofx 两个 Discord Hermes profile 已按本机 WSL 的有效模式改为 profile 级 `approvals.mode: 'off'`；遇到 `Command Approval Required` 先查 `/home/arbops/.hermes/profiles/<profile>/config.yaml`，不要只看全局配置。
- nofx Discord profile 的 SOUL 现在使用绝对入口 `/home/arbops/.local/bin/smart-arb-pipeline`；gateway 通过 profile `start-gateway.sh` 加载 `.env`，`.env` 必须是 `arbops:arbops` 且 `0600`。
- nofx live verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，并通过 `--verification-command-timeout-seconds` 显式记录单命令超时；不要再把全量 `unittest discover` 当 Discord live 默认门禁。
- nofx 当前 live bridge 固定使用每阶段 owner 的独立 Git worktree：runner 会创建 `agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_REPO_DIR` 注入 Hermes bridge；不再暴露 `shared` / `copy` 模式。
- nofx Discord 状态卡会读取 `command-runs/*.json`，展示阶段命令状态、阻塞证据和自动修复判断；证据项默认转换为 20 字以内中文短说明，完整文件仍保留在证据目录；默认只显示 stage/agent/returncode/证据短说明，不展开 reviewer/tester/terminal stdout/stderr；`run_external_research` / `revise_solution` / `return_to_code_execution` / `return_to_deployment` / `fix_memory_writeback` / `fix_git_publish` 会自动回流最多 2 次，高风险凭证、真实交易、资金或破坏性数据操作仍停人工确认。
- nofx Discord 入口默认每 60 秒输出 `# nofx 任务执行进度`，从 `pipeline_state.json` 和最近 `command-runs/*.json` 展示已完成阶段、当前阶段、最近命令状态和证据目录；`--emit-json` / `--no-chat-summary` 会关闭该进度卡，保持机器输出原样。
- 本仓库已新增 `backlog_runner.py` 与 `backlog_runner_30m` cron，用于从 Task Center 自动挑选低风险、无需人工确认或澄清的待办继续调用 `smart-arb-pipeline`。该能力解决“任务只有用户在聊天里触发才继续推进”的断点；高风险、需确认、需澄清任务仍必须停在 `human_inbox.py`。`cron/jobs.json` 的 announce / failureAlert 默认投递到 spreadagent Discord 群 `1494595527181078578`。
- 状态卡默认展示最多 24 条 command report 状态行，可用 `SMART_ARB_CHAT_COMMAND_LIMIT` / `--chat-command-limit` 调整；命令输出摘要需要显式开启 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` / `--chat-include-command-output`，旧版关键证据列表需要显式开启 `SMART_ARB_CHAT_SHOW_KEY_ARTIFACTS=1` / `--chat-show-key-artifacts`。
- Hermes CLI 有时只在 stdout/stderr 返回 `session_id`，实际 assistant 内容落在 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json`；live bridge 会在固定 profile session 目录内恢复最新 assistant 输出并先脱敏，再用于 stage pass 判定和 command artifact，不作为聊天卡默认展开内容。
- nofx live bridge 的非代码 Hermes 阶段只允许在 stdout/final answer 返回证据，不允许直接写 `research_report.md` 等 pipeline artifacts；Hermes 子进程环境会剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，`external_research` 可用 `NO_EXTERNAL_LOOKUP_NEEDED` 表示本地事实已足够，不能因此被 live gate 判失败。
- 自动修复风险扫描按分句剥离“不得泄露凭证 / 不启动真实交易 / 不下单不划转”等纯否定式安全边界；已脱敏字段如果表达 `Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]` 或 `Need session_id=[REDACTED]` 仍按高风险停人工确认，`No need for ...` / `Do not need ...` 这类否定噪音可自动回流。混合句里只要仍有正向要求读取凭证、启用实盘、资金操作或破坏性命令，就会停人工确认。
- 需求明确 memory/docs-only、no service control、no deployment 或 no restart 时，entry 不注入 deployment command；如果同一需求后续明确要求重启/部署，正向 deployment 动作优先，普通 API/服务改动也会注入 deployment bridge 做内控 FastAPI smoke。
- 最新 nofx 安装记录：2026-04-28 16:27 已把回答状态代码批次 `f94c2284` 安装到 `/home/arbops/.hermes/ops`，远端 hardflow 仓库 HEAD 为 `f94c228`。安装态 `smart_arb_pipeline_entry.py` 包含 `回答状态` 进度/最终状态卡逻辑；两个 live profile `SOUL.md` 已同步仓库模板，备份为 `SOUL.md.bak-answer-status-20260428T082523Z`，并重启 `hermes-discord-arbitrage`、`hermes-discord-spread`。远端 `compileall`、39 项定向单测、`smart-arb-pipeline --help`、gateway state、内控 API `127.0.0.1:18080` smoke 和 echo run `deploy-smoke-spreadagent-20260428T082751163478Z` 均通过，详见 `RUNBOOK.md` / `TASK_HISTORY.md`。
- 前序 artifact 注入后续 Hermes prompt 前会做敏感信息脱敏，覆盖常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack token、HF token、Google OAuth/API key、AWS access key 等形态。
- `code_execution` 默认在 `backend-dev` workspace 产出 diff；前端/UI/页面/交互类需求可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。runner 会把 diff 应用回主项目目录，并注入后续 tester/reviewer/deployer workspace。
- `git_publish` 是可选发布门禁，只在验证、代码审查、deployment（如有）、验收和记忆回写通过后执行；提交说明、备注和变更描述必须使用中文，提交前运行 `git diff --check` 与 `git diff --cached --check`，并扫描 staged diff 中的密钥形态。secret scan 会输出脱敏的文件、行号、规则和风险等级；真实 secret、hardcoded fallback secret、PEM private key hard block，测试/文档占位不阻塞，非密钥类发布失败回流为 `fix_git_publish`。
- `source_registry_watcher` 与 `repo_hygiene_reviewer` 默认每 2 天执行一次；前者只检查已注册来源，后者由 `coordinator` 只读扫描冗余、冲突、缓存、重复文件并创建人工确认候选，不自动删除、不自动推送。
- 到期 TODO 已改为风险分流：低风险进入 `dispatch_pipeline` 自动候选并由 backlog runner 推进；高风险、生产、部署、资金、凭证、删除等候选仍停 `human_inbox.py` 等待人工确认。
- 双 AI 审核现在有真实产物门禁：需求、方案、代码三个 review 阶段都需要两条不同命令、不同 `reviewer_role`（`reviewer-a`/`reviewer-b`）的 reviewer command report，且都输出对应 `Final verdict` 才放行。
- `solution_package` 当前以 `delivery_plan.json` 作为结构化交付契约，`solution.md` 只是人工展示层；`solution_review` 与 `code_execution` 都优先读取该契约。遇到“方案太泛 / 不是 implementation plan”的阻塞，优先修 `delivery_plan.json` 字段或走 `revise_solution` 自动回流，不要通过放松 reviewer 或润色 Markdown 绕过。
- 2026-04-27 工作流自修修复：`requirements.md` / `solution.md` 不再回落到通用流水线模板，必须保留用户本轮具体目标、禁止范围和安全边界；requirements review 通过后会生成 `resolved_requirement.md` 作为下游 handoff。应用 code workspace patch 前会检查主工作区脏路径是否与补丁路径重叠，重叠则拒绝应用；`verification` 或 `code_review` 阻塞时会对已应用到主项目目录的 code workspace patch 执行反向回滚并写入 `rollback_*` artifact，回滚失败会阻塞为 `rollback_cleanup/manual_cleanup_required`。nofx 两个 Discord profile 的 SOUL 已部署“工作流自修例外”：用户明确说“不要走工作流”或目标是修复 pipeline/bridge/profile/dual-review/auto-repair/git_publish 时，不再启动新的 `smart-arb-pipeline` 自修 run，只做只读诊断并提示外部 operator/Codex 通过 SSH 修复。
- 最后远端安装态 smoke：`install-smoke-arbitrageagent-20260427T151733781612Z`，Task Center 为 `passed`；该 smoke 为 deterministic echo 模式，用于验证安装态入口和 Task Center 写入，不触发真实 Hermes chat，不重启服务，不执行 git publish。
- Task Center 中的 agent 字段仍表示责任标签和交接记录；要声称真正 native fan-out，仍需 command evidence 中出现独立宿主 session/run id。
- 如果要让任务真正转发到 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester` 等宿主 native agent，需要继续在 runtime adapter 增加 session dispatch 能力，而不是只修改 stage prompt。
- nofx SSH 曾出现原生 `ssh` 空退和 Paramiko banner 被拒；远程排障需要低频单连接重试，避免并发连接触发服务端临时拒绝。

## 安全边界

- 不记录 Discord token、模型 API key、OAuth auth、Cookie、私钥或交易所凭证。
- 远程事实以 nofx 实时命令、Hermes profile 状态、Task Center DB、pipeline run artifacts 和服务日志为准。

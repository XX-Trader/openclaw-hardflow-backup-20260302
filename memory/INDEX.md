# 项目记忆索引

最后更新：2026-05-07

## 阅读顺序

1. `RUNBOOK.md`：本仓库工作流、runtime 安装和远程巡检命令。
2. `DEPLOYMENT.md`：nofx 部署目标、安装命令、当前安装态和验收记录。
3. `PITFALLS.md`：已确认的排障结论、历史坑和避免误判的边界。
4. `DECISIONS.md`：近期架构裁决和被拒方案。
5. `TASK_HISTORY.md`：重要任务完成记录、验证证据和关联文件。
6. `../docs/INDEX.md`：长期文档导航与工作流事实源。
7. `../todo.md` / `../done.md`：当前任务盘和完成记录。

## 当前重点

- 本机 WSL 现在有独立 `multicorerouter` Hermes profile，对应 Discord bot `多agent路由`，作为本地多 agent 默认规划者/路由入口。当前 hardflow 工作流已通过 `runtime_installer.py` 安装到 `/home/ubuntu/.hermes/profiles/multicorerouter`，本机 wrapper 为 `/home/ubuntu/.local/bin/multicorerouter-workflow`；2026-04-30 已先 `git fetch origin main` 并确认 `HEAD...origin/main=0 0`，再重新同步当前仓库到该 profile，安装 manifest 显示 5 个 workflow skills、21 个 ops 脚本、12 个 cron jobs 且 `missing_sources=[]`。`multicore` 历史 profile 已还原并保持独立，不继承、不覆盖、不清理它的 memories/sessions。最新 Discord 服务器 `大白量化社群管理群` 的频道级策略是：两个 bot 在 `总群` 必须 @，其它频道免 @；排查这条链路先看 `RUNBOOK.md` 和 `TASK_HISTORY.md` 的 2026-04-29/2026-04-30 记录。
- nofx 上 SmartMultiPlatformArbitrage 的项目交付入口由本仓库提供：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py` 和 runtime installer。
- nofx 当前 agent/model 口径已修正：live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`；2026-04-27 服务器实测两者均为 `model.provider=openai-codex`、`model.default=gpt-5.5`、`gateway_state=running`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`；cron / Task Center 定时任务只挂 `coordinator/project-agent`，不再注册 `ops-agent/optimization-agent`。以上都不是 nofx 上 14 个常驻 agent 进程；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
- nofx 两个 Discord Hermes profile 已按本机 WSL 的有效模式改为 profile 级 `approvals.mode: 'off'`；遇到 `Command Approval Required` 先查 `/home/arbops/.hermes/profiles/<profile>/config.yaml`，不要只看全局配置。
- nofx Discord profile 的 SOUL 现在使用绝对入口 `/home/arbops/.local/bin/smart-arb-pipeline`；gateway 通过 profile `start-gateway.sh` 加载 `.env`，`.env` 必须是 `arbops:arbops` 且 `0600`。
- 2026-04-29 本仓 nofx Discord profile 模板和 `smart_arb_pipeline_entry.py` 已升级并安装为“所有任务先执行链路选择 + Discord profile 最高权限调度入口 + route-choice 入口硬门禁 + specified_agent 真实执行 + session/run-id 状态卡”：只读查询、普通沟通、方案讨论、安全仓库同步、业务代码修改、部署排障、TODO 推进和 hardflow workflow/runtime/profile 自修都必须先发“执行链路选择”卡；用户选择 `direct_run` 后由当前 Discord profile 作为最高权限 operator 直接处理，选择 `coding_workflow` / `todo_auto_candidate` 后才启动 coordinator pipeline。入口脚本现在要求 Discord source 携带有效 `--route-choice`：缺失时只返回选择卡；`specified_agent` 必须带 `--assignee <agent-id>`，并创建 Task Center 任务调用指定 agent；nofx 没有 `openclaw` CLI 时自动使用当前 Hermes profile 的 `hermes chat` 执行指定 agent，并把 Hermes `session_id` 回写为 session/run 证据；`coding_workflow` 会把真实 agent session/run id 写入 command-runs、Task Center 和状态卡。代码批次 `22cecab` 已安装，后续文档/记忆提交已拉到 nofx 且 `HEAD...origin/main=0 0`，指定 agent live smoke 已返回 Task Center、executor run id、agent session id、agent run id、session key 和 `回答状态: 已回答完毕`。
- nofx live verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，并通过 `--verification-command-timeout-seconds` 显式记录单命令超时；不要再把全量 `unittest discover` 当 Discord live 默认门禁。
- nofx 当前 live bridge 固定使用每阶段 owner 的独立 Git worktree：runner 会创建 `agent-workspaces/<stage>/<agent>/repo`，并把 `PIPELINE_AGENT_REPO_DIR` 注入 Hermes bridge；不再暴露 `shared` / `copy` 模式。
- nofx Discord 状态卡会读取 `command-runs/*.json`，展示阶段命令状态、阻塞证据和自动修复判断；证据项默认转换为 20 字以内中文短说明，完整文件仍保留在证据目录；默认只显示 stage/agent/returncode/证据短说明，不展开 reviewer/tester/terminal stdout/stderr；`run_external_research` / `revise_solution` / `return_to_code_execution` / `return_to_deployment` / `fix_memory_writeback` / `fix_git_publish` 会自动回流最多 2 次。高风险凭证、破坏性数据操作和 force push 仍停人工确认；SmartMulti 策略类真实交易、下单、划转、提现和资金项在用户明确确认后可携带 `--human-risk-confirmed` 继续，但后续测试、双 reviewer、部署、写回和 git publish 门禁不变。
- nofx Discord 入口默认每 60 秒输出 `# nofx 任务执行进度`，从 `pipeline_state.json` 和最近 `command-runs/*.json` 展示已完成阶段、当前阶段、最近命令状态和证据目录；`--emit-json` / `--no-chat-summary` 会关闭该进度卡，保持机器输出原样。
- 本仓库已新增 `backlog_runner.py` 与 `backlog_runner_30m` cron，但 2026-04-28 起默认进入“手动链路选择”阶段：系统只推荐直接运行、需求探讨、指定 agent、编码工作流或 TODO 自动候选，用户确认后才执行。到期 TODO 即使低风险，也先进入 `human_inbox.py` 路线选择；Discord 入口也同样所有新任务先走选择，只有选择为 `coding_workflow` / `todo_auto_candidate` 等 pipeline 动作后，backlog runner 或 profile 才会调用 `smart-arb-pipeline`。2026-05-06 起 cron 默认带 `--allow-confirmed-high-risk`，runner 对已确认高风险任务会向入口传 `--human-risk-confirmed`，避免用户确认后仍卡在 `risk_gate`。`cron/jobs.json` 的 announce / failureAlert 默认投递到 spreadagent Discord 群 `1494595527181078578`。
- 2026-04-28 用户确认：Hermes 已有记忆整理能力，本仓 `memtidy_runner` 退役，不再安装 `memtidy` skill、`memtidy_runner.py` 或 `config/memtidy_rules.json`，也不再注册每日 03:00 记忆整理 cron。待办自动推进链继续保留。
- `delivery_plan.json` 现在承担任务拆分职责：多事项需求会拆成 `scope_slices`，第一块为本轮 `current`，其余标记 `deferred`，避免 backlog runner 或人工入口一次执行过重任务；需要核对的凭证、资金、生产破坏、需求不清和高风险事项仍停 human inbox 或回问用户。
- `delivery_plan.json.target_files` 现在只把用户原始需求/修复上下文中的显式路径作为高可信目标；review / research / project memory 仅作低信任补充并过滤 `.workflow`、runtime host、Task Center、agent workspace、command report 和项目记忆控制文件，简单任务没有可靠业务文件时保持 `discovery_required=true`。被过滤的异常候选会写入 `plan_findings.filtered_target_candidates` 并展示在 `solution.md`。
- 状态卡默认展示最多 24 条 command report 状态行，可用 `SMART_ARB_CHAT_COMMAND_LIMIT` / `--chat-command-limit` 调整；命令输出摘要需要显式开启 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` / `--chat-include-command-output`，旧版关键证据列表需要显式开启 `SMART_ARB_CHAT_SHOW_KEY_ARTIFACTS=1` / `--chat-show-key-artifacts`。
- Hermes CLI 有时只在 stdout/stderr 返回 `session_id`，实际 assistant 内容落在 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json`；live bridge 会在固定 profile session 目录内恢复最新 assistant 输出并先脱敏，再用于 stage pass 判定和 command artifact，不作为聊天卡默认展开内容。
- nofx live bridge 的非代码 Hermes 阶段只允许在 stdout/final answer 返回证据，不允许直接写 `research_report.md` 等 pipeline artifacts；Hermes 子进程环境会剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，`external_research` 可用 `NO_EXTERNAL_LOOKUP_NEEDED` 表示本地事实已足够，不能因此被 live gate 判失败。
- 自动修复与 pre-execution 风险扫描都按子句剥离“不得泄露凭证 / 不启动真实交易 / 不下单不划转”等纯否定式安全边界；已脱敏字段如果表达 `Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]` 或 `Need session_id=[REDACTED]` 仍按高风险停人工确认，`No need for ...` / `Do not need ...` 这类否定噪音可自动回流。混合句里只要仍有正向要求读取凭证、启用实盘、真实下单、资金操作或破坏性命令，就会保持 high-risk；如已人工确认则进入 `confirmed_execute`，否则停人工确认。
- 需求明确 memory/docs-only、no service control、no deployment 或 no restart 时，entry 不注入 deployment command；如果同一需求后续明确要求重启/部署，正向 deployment 动作优先，普通 API/服务改动也会注入 deployment bridge 做内控 FastAPI smoke。
- 最新 nofx 安装记录：2026-05-07 01:05 已安装 reviewer fallback 降级批次，远端 hardflow 仓库 `HEAD=8255a65`、`HEAD...origin/main=0 0`。runtime installer 返回 `ok=true`、`changed=true`；远端 `compileall` 与 6 项 reviewer fallback 定向 unittest OK；`smart-arb-pipeline --help` 已显示 `--reviewer-fallback-models`；两个 Discord gateway 均为 `running/connected`。上一批 2026-05-06 23:40 的高风险确认 echo smoke `cli-spreadagent-20260506T153935576001Z` 仍是策略高风险确认链路的最新 live smoke。详见 `DEPLOYMENT.md`、`RUNBOOK.md`、`TASK_HISTORY.md`。
- 前序 artifact 注入后续 Hermes prompt 前会做敏感信息脱敏，覆盖常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack token、HF token、Google OAuth/API key、AWS access key 等形态。
- `code_execution` 默认在 `backend-dev` workspace 产出 diff；前端/UI/页面/交互类需求可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。runner 会把 diff 应用回主项目目录，并注入后续 tester/reviewer/deployer workspace。
- `git_publish` 是可选发布门禁，只在验证、代码审查、deployment（如有）、验收和记忆回写通过后执行；提交说明、备注和变更描述必须使用中文，提交前运行 `git diff --check` 与 `git diff --cached --check`，并扫描 staged diff 中的密钥形态。secret scan 会输出脱敏的文件、行号、规则和风险等级；真实 secret、hardcoded fallback secret、PEM private key hard block，测试/文档占位不阻塞，非密钥类发布失败回流为 `fix_git_publish`。
- `source_registry_watcher` 与 `repo_hygiene_reviewer` 默认每 2 天执行一次；前者只检查已注册来源，后者由 `coordinator` 只读扫描冗余、冲突、缓存、重复文件并创建人工确认候选，不自动删除、不自动推送。
- 到期 TODO 与通用 `create-task` 已改为手动链路选择：任务先写入 `route_selection.mode=manual_selection`，由人工选择直接运行、需求探讨、指定 agent、编码工作流或 TODO 自动候选；backlog runner 只正向推进已确认的 `coding_workflow` / `todo_auto_candidate`，会跳过未选择路线和非 pipeline 选择。
- 双 AI 审核现在采用“优先双模型、允许运行时降级”的真实产物门禁：需求、方案、代码三个 review 阶段优先收集 reviewer-a/reviewer-b 两路不同模型输出；若某一路 provider/model 不可用、HTTP 404、命令失败或缺 verdict，入口按 `zai/glm-5.1 -> zhipu/glm-5.1 -> openai-codex/gpt-5.5` fallback。最终至少一个 reviewer 输出阶段期望 `Final verdict` 且无明确 blocker 时可按 `degraded_single_valid` 放行；任一有效 reviewer 明确要求修订仍阻断。
- `solution_package` 当前以 `delivery_plan.json` 作为结构化交付契约，`solution.md` 只是人工展示层；`solution_review` 与 `code_execution` 都优先读取该契约。遇到“方案太泛 / 不是 implementation plan”的阻塞，优先修 `delivery_plan.json` 字段或走 `revise_solution` 自动回流，不要通过放松 reviewer 或润色 Markdown 绕过。
- 2026-04-27 工作流自修修复：`requirements.md` / `solution.md` 不再回落到通用流水线模板，必须保留用户本轮具体目标、禁止范围和安全边界；requirements review 通过后会生成 `resolved_requirement.md` 作为下游 handoff。应用 code workspace patch 前会检查主工作区脏路径是否与补丁路径重叠，重叠则拒绝应用；`verification` 或 `code_review` 阻塞时会对已应用到主项目目录的 code workspace patch 执行反向回滚并写入 `rollback_*` artifact，回滚失败会阻塞为 `rollback_cleanup/manual_cleanup_required`。2026-04-28 起 profile 的“工作流自修例外”升级为高权限工作流维护模式：仍不允许用同一条 pipeline 递归修自己，但可由 Discord profile 直接维护 hardflow 宿主、测试并安装 runtime。
- 最后远端安装态 smoke：`install-smoke-arbitrageagent-20260428T151514657470Z`，15/15 阶段完成，Task Center 为 `passed`；该 smoke 为 deterministic echo 模式，用于验证安装态入口和 Task Center 写入，不触发真实 Hermes chat，不执行 deployment 或 git publish。
- Task Center 中的 agent 字段仍表示责任标签和交接记录；要声称真正 native fan-out，仍需 command evidence 中出现独立宿主 session/run id。
- 如果要让任务真正转发到 `web-agent`、`project-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester` 等宿主 native agent，需要继续在 runtime adapter 增加 session dispatch 能力，而不是只修改 stage prompt。
- nofx SSH 曾出现原生 `ssh` 空退和 Paramiko banner 被拒；远程排障需要低频单连接重试，避免并发连接触发服务端临时拒绝。

## 安全边界

- 不记录 Discord token、模型 API key、OAuth auth、Cookie、私钥或交易所凭证。
- 远程事实以 nofx 实时命令、Hermes profile 状态、Task Center DB、pipeline run artifacts 和服务日志为准。

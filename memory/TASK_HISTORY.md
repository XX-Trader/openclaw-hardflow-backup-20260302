# TASK_HISTORY

## 2026-04-28 - nofx 安装 workflow runtime d2e530b7

类型：deploy
范围：nofx hardflow 仓库、`/home/arbops/.hermes/ops`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、Discord gateways、Task Center smoke
事实：已把本仓最新提交 `d2e530b7` 推送到 `origin/main` 并安装到 nofx。服务器仓库从 `17d9b36` fast-forward 到 `d2e530b`，`HEAD...origin/main=0 0`，最终工作树 clean；runtime installer 返回 `ok=true`、`changed=true`，安装态包含新增 `policy_route_selection.py`。两个 live profile `SOUL.md` 已同步高权限工作流维护模式，备份后缀为 `manual-route-20260428T151420Z`，并重启两个 Discord gateway。
证据：本地验证通过 19 项定向单测、7 个脚本 `py_compile`、`compileall`、`git diff --check`、`git diff --cached --check` 和 staged secret scan；独立 code-reviewer 审查 0 findings / APPROVE。远端验证通过 `git diff --check`、7 个脚本 `py_compile`、`compileall`、19 项定向单测、`smart-arb-pipeline --help`、gateway `running/connected`、内控 API `/health` 与 `/api/strategy/status`、cron job 数 12 / `memtidy_hits=0`，echo smoke `install-smoke-arbitrageagent-20260428T151514657470Z` 完成 15/15 且 Task Center `passed`。
最后验证：2026-04-28 23:15
复用建议：以后“上传到 git 并去 nofx 拉取测试”按本次顺序执行：本地测试和 reviewer 通过 -> push -> nofx `git pull --ff-only` -> runtime installer -> 远端定向测试/help/API -> 如 profile 变更则同步 live SOUL 并重启 gateway -> echo smoke -> 清理 `file_write_audit.jsonl` 测试副作用 -> 记录记忆。

## 2026-04-28 - 执行链路手动选择模式

类型：feature
范围：`skills/library/control-plane-ops/scripts/policy/policy_route_selection.py`、`skills/library/todo-patrol/scripts/deadline_to_task_bridge.py`、`skills/library/control-plane-ops/scripts/policy/policy_task.py`、`skills/library/control-plane-ops/scripts/policy/human_inbox.py`、`scripts/openclaw-ops/backlog_runner.py`、`skills/library/control-plane-ops/scripts/policy/policy_observe.py`、`docs/核心主工作流/项目交付优先工作流/README.md`
事实：根据用户确认，当前不把推荐链路直接全自动执行。路由层会输出推荐链路和选项；到期 TODO 和通用 `create-task` 默认创建 `manual_selection` 人工问题，用户可选择直接运行、需求探讨、指定 agent、编码工作流或 TODO 自动候选。`human_inbox confirm --route-choice` 会记录 `selected_route` 并设置 action；`backlog_runner` 只正向推进已人工确认且选择为 `coding_workflow`/`todo_auto_candidate` 的 pipeline 任务，未选择路线或选择直接运行、需求探讨、指定 agent 的任务不会被自动执行。旧 `confirm-risk` 对未选择路线的任务会 fail-close，避免任务从人工队列消失但没有 `selected_route`；`specified_agent` 选择必须显式带 `--assignee <agent-id>`，否则任务继续留在人工队列。
证据：新增/调整单测覆盖低风险到期 TODO 进入人工路线选择、高风险 TODO 推荐编码工作流、通用 create-task 默认等待路线选择、旧 confirm-risk 拒绝未选择路线任务、CLI 接受 `--route-choice recommended`、人工选择非 pipeline 路线留痕、指定 agent 缺 assignee 拒绝、backlog runner 正向校验 pipeline 路线、workflow selector 路线建议。
最后验证：2026-04-28 21:31 本地 `python -m unittest tests.scripts_openclaw_ops.test_human_inbox tests.scripts_openclaw_ops.test_policy_task_manual_route tests.scripts_openclaw_ops.test_deadline_to_task_bridge tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_workflow_selector -v` 18 项 OK；`python -m py_compile` 覆盖 `policy_route_selection.py`、`task_capability_binding.py`、`deadline_to_task_bridge.py`、`human_inbox.py`、`backlog_runner.py`、`policy_observe.py`、`policy_task.py` 通过。
复用建议：如果后续要恢复全自动，应先统计推荐链路与人工最终选择的一致率，只对稳定类别放开自动，不要全局关闭人工选择。

## 2026-04-28 - nofx Discord profile 高权限工作流维护模式

类型：task
范围：`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`、`tests/scripts_openclaw_ops/test_nofx_profile_templates.py`、`memory/`
事实：已把两个 nofx Discord profile 模板从“workflow 自修只读诊断”升级为“高权限工作流维护模式”。普通业务任务仍进入 coordinator pipeline；修 hardflow workflow/runtime/profile/SOUL/dual review/auto-repair/git_publish/runtime installer/cron workflow 时，profile 不再启动新的 `smart-arb-pipeline`，而是直接切到 hardflow 仓库修工作流宿主、跑测试、按需安装 runtime，并在无法启动独立 reviewer 时标记 `review=pending_external`。当前仅完成本地模板、文档、记忆和测试；SSH 到 nofx 未返回有效输出，live profile 同步和 gateway 重启待 SSH 恢复且确认无活跃 pipeline 后执行。
证据：`test_nofx_profile_templates.py` 断言两个模板含“高权限工作流维护模式”、hardflow 仓库路径、runtime installer 和 `review=pending_external`，且不再含“只允许做只读诊断和状态回传”。
最后验证：2026-04-28 19:59 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_nofx_profile_templates tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` OK；`git diff --check` OK。
复用建议：要让该权限在 Discord live 生效，必须同步本仓 `config/nofx-hermes-profiles/<profile>/SOUL.md` 到 nofx live `/home/arbops/.hermes/profiles/<profile>/SOUL.md`，并重启对应 gateway；重启前先查活跃 `smart-arb-pipeline`。

## 2026-04-28 - nofx 安装 workflow runtime 17d9b369

类型：deploy
范围：nofx hardflow 仓库、`/home/arbops/.hermes/ops`、runtime installer、cron jobs、Discord gateways、内控 API、Task Center smoke
事实：已在 nofx 拉取并安装最新 workflow 仓库状态。服务器仓库当前 `HEAD=17d9b36`，与 `origin/main` 对齐，`git pull --ff-only origin main` 返回 already up to date，`HEAD...origin/main=0 0`，工作树 clean，未创建 stash。runtime installer 返回 `ok=true`、`changed=true`，安装 5 个 runtime skill、18 个 ops 脚本和 12 个 cron job；本轮没有 profile SOUL 变更，因此未重启 gateway。
证据：安装日志 `/tmp/hardflow-runtime-install-20260428T113954Z.json`；远端安装态 3 个核心脚本 `py_compile` 通过；远端 `compileall` 通过；远端 `python3 -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 76 项 OK；仓库源码与 runtime 安装态 SHA256 对齐；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；cron job 数为 12 且 `memtidy_hits=0`；两个 Discord gateway `running`；内控 API `/health` 为 `status=ok`、`/api/strategy/status` 为 `running=false`；echo smoke `install-smoke-arbitrageagent-20260428T114016095602Z` 完成 15/15，`next_action=none`。
最后验证：2026-04-28 19:40
复用建议：以后 nofx “拉取最新代码并安装 workflow”按 `git fetch -> git status -> 必要时 stash -> git pull --ff-only -> runtime_installer.py install -> py_compile/compileall/unittest -> help/cron/gateway/API/smoke` 顺序执行；远端复杂脚本优先 Paramiko，避免 PowerShell stdin BOM。

## 2026-04-28 - nofx 安装 workflow runtime 353f420d

类型：deploy
范围：nofx hardflow 仓库、`/home/arbops/.hermes/ops/pipeline_runner.py`、runtime installer、cron jobs、Discord gateways
事实：已把 workflow 代码批次 `353f420d` 推送到 `origin/main` 并安装到 nofx。服务器仓库从 `195c513` fast-forward 到 `353f420`，`HEAD...origin/main=0 0`；runtime installer 返回 `ok=true`、`changed=true`，安装态 `pipeline_runner.py` 与仓库源码 SHA256 对齐。本轮只更新 ops 脚本，不涉及 profile SOUL，因此未重启 gateway。
证据：远端安装态 `pipeline_runner.py` `py_compile` 通过；远端 `python3 -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 73 项 OK；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；cron job 数为 12 且 `memtidy_hits=0`；两个 Discord gateway `running`，日志近 80 行无错误；runtime dry-run smoke `/tmp/hardflow-install-smoke-20260428T110456Z` 验证 Windows 绝对路径进入 `filtered_target_candidates` 而不是 `target_files`。
最后验证：2026-04-28 19:05
复用建议：nofx 安装 workflow 代码时，先用 `git pull --ff-only` 对齐仓库，再跑 runtime installer。入口 smoke 使用 `/home/arbops/.local/bin/smart-arb-pipeline` 绝对路径；如果本轮没有 profile 模板变化，不需要重启 `hermes-discord-*`。

## 2026-04-28 - 本机 WSL multicore Codex 登录修复

类型：runbook
范围：WSL Ubuntu `/home/ubuntu/.hermes/profiles/{trend-backtest,multicore}`、tmux `multicore-gateway`
事实：`multicore` profile 的 Discord gateway 能连接，但 Hermes provider 调用失败为 `No Codex credentials stored`。真实原因不是全局 Windows Codex 登录失效，而是 `trend-backtest` 已有 profile 级 Hermes auth store：`/home/ubuntu/.hermes/profiles/trend-backtest/auth.json`，而 `multicore` 缺少 `/home/ubuntu/.hermes/profiles/multicore/auth.json`。已将已验证可用的 profile auth store 安装到 `multicore`，权限为 `0600`，并重启 `multicore-gateway`。
证据：修复前 `hermes -p multicore status` 显示 `OpenAI Codex ✗ not logged in` 且 auth file 指向 `/home/ubuntu/.hermes/profiles/multicore/auth.json`；修复后 `hermes -p multicore status` 显示 `OpenAI Codex ✓ logged in`，gateway PID 更新为 `5169`；`timeout 90 hermes -p multicore chat -q '只回复 OK，不要调用工具。'` 返回 `OK`，0 tool calls。
最后验证：2026-04-28 17:44
复用建议：本机 WSL 多 profile 登录排障时，先查 `hermes -p <profile> status` 里显示的 profile 级 auth file，不要只查 `/home/ubuntu/.codex/auth.json` 或 Windows `C:\Users\Administrator\.codex\auth.json`。新增 profile 若复用同一 Codex 账号，可从已登录 profile 复制 `auth.json` 并设置 `chmod 600`，然后重启对应 tmux gateway。

## 2026-04-28 - DeliveryPlan 目标路径收敛与异常反馈

类型：bugfix
范围：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：修复简单任务在 `solution_package` / `delivery_plan.json` 生成时被扩散到 workflow 宿主和控制面路径的问题，并补齐异常候选的可观测反馈。`target_files` 现在优先信任用户原始需求与修复上下文；`requirements_review`、`research_report` 和 `project_memory_context` 只作为低信任补充，并过滤 `.workflow/`、`agent-workspaces/`、`command-runs/`、`task-center/`、`.hermes/`、`.openclaw/`、`.codex/`、`auth-profiles/`、`credential-imports/`、`sessions/` 以及项目记忆控制文件名。被过滤的异常候选写入 `plan_findings.filtered_target_candidates`，`solution.md` 同步展示 path/source/reason。`human_blockers` 文案从 `Requires credentials...` 收敛为 stop-boundary 表达，避免 `revise_solution` 自动回流被风险扫描误判为正向凭证/资金请求。
证据：新增 `control_plane_plan_path_reason()`、`low_trust_plan_paths()`、`merge_plan_paths()`、候选拒绝原因记录和 `Filtered Target Candidates` 渲染；新增回归测试覆盖简单任务不把 `API_REGISTRY.json` / `.workflow` / `.hermes` 作为目标文件但会反馈 `project_memory_control_file`，review context 中保留真实实现文件但过滤并反馈控制面路径，否定 `.workflow` 路径反馈 `negated_context`，生成的方案边界文案不阻断 `revise_solution`。
最后验证：2026-04-28 18:52 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 73 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过；code-reviewer 复审通过。
复用建议：以后 `solution_review` 因方案“触碰 workflow 宿主 / 敏感路径 / 控制面路径”卡住时，先查 `delivery_plan.json.target_files` 和 `plan_findings.filtered_target_candidates`。用户没有明确点名文件时，宁可让 `discovery_required=true`，也不要把项目记忆、runtime host 或 pipeline artifact 路径当成业务修改目标。

## 2026-04-28 - nofx profile 普通沟通/独立协作边界上线

类型：deploy
范围：`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、nofx live profile `SOUL.md`、Discord gateway
事实：完善 nofx 上“不走工作流”的真实执行边界：普通沟通、只读查询、方案讨论和用户明确要求“直接沟通 / 先讨论 / 先自己开发 / 这次不用自动流程”时不启动 `smart-arb-pipeline`；但代码修改、部署、依赖安装、提交推送和生产配置变更仍不能在 Discord profile 会话里直接做，必须由外部 Codex/SSH operator 处理，或由用户重新授权进入 coordinator pipeline。工作流自身修复例外已从“只要说不要走工作流”收窄为“不要走工作流且目标是 pipeline/profile/auto-repair/git_publish 等运行时问题”。
证据：本地模板已更新；nofx 仓库模板与 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 均通过 SFTP 同步并备份为 `SOUL.md.bak-ordinary-collab-20260428T170108`；重启 `hermes-discord-arbitrage` / `hermes-discord-spread` 后，两者 `gateway_state=running`、Discord `connected`，日志尾部无新增错误。
最后验证：2026-04-28 17:01
复用建议：以后 Discord 里“不走工作流”优先理解为“本轮不启动 pipeline”，再按任务类型判断：能直接答就直接答，需要真实改动就提示外部 operator 或重新授权 pipeline。

## 2026-04-28 - 工作流外普通沟通与独立开发边界

类型：decision
范围：用户级 `AGENTS.md`、项目交付优先工作流文档、项目记忆
事实：补齐“工作流之外也能独立开发和沟通”的规则：当用户明确说不走工作流、直接沟通、先自己开发或这次不用自动流程时，当前 Codex 会话直接处理，不进入 `smart-arb-pipeline`、Discord pipeline、Task Center backlog runner 或新的 OMX workflow run。该规则与“工作流自身故障时绕过自修”并列存在，不再把所有“不走工作流”都解释成故障降级。
证据：`C:\Users\Administrator\.codex\AGENTS.md` 新增普通 Codex 协作模式段落；`docs/核心主工作流/项目交付优先工作流/README.md` Out Of Scope 新增边界；`memory/DECISIONS.md` 已记录长期决策。
最后验证：2026-04-28
复用建议：用户如果只是想讨论方案、让主代理直接改文件、或临时不想进自动流程，就留在普通会话完成；只有用户重新要求 `$name`、`omx ...`、pipeline、长期自动推进或 Discord 工作流交付时，才恢复 workflow。

## 2026-04-28 - nofx Discord 回复状态标识

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：Discord pipeline 启动卡和运行中进度卡现在明确显示 `回答状态: 正在回复/执行中`；最终 `# nofx 任务执行状态` 显示 `回答状态: 已回答完毕`、`未回答完毕，等待人工确认或自动修复` 或无法解析执行结果。两个 nofx profile SOUL 同步要求只读直接回复在末尾追加 `回答状态: 已回答完毕`，长只读查询可先发 `回答状态: 正在回复/查询中`。代码批次 `f94c2284` 已推送并部署到 nofx，远端 hardflow HEAD 为 `f94c228`，live runtime 安装态已加载 `回答状态` 渲染逻辑。
证据：新增 `answer_status_label()`、进度卡/最终卡渲染断言，以及两个 profile 模板规则。nofx 两个 live profile `SOUL.md` 已同步仓库模板，备份为 `SOUL.md.bak-answer-status-20260428T082523Z`，并重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`；gateway 均为 `running/connected`；echo smoke `deploy-smoke-spreadagent-20260428T082751163478Z` 完成 15/15 阶段，状态卡显示 `回答状态: 已回答完毕`。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 39 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`python -B -m py_compile scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`git diff --check` 通过。nofx 远端 `py_compile`、`compileall`、39 项定向 `unittest`、`smart-arb-pipeline --help`、gateway state、内控 API `/health` 和 `/api/strategy/status` smoke 均通过
复用建议：以后用户反馈“看不出是否还在回复 / 是否答完”时，先检查状态卡是否包含 `回答状态` 行，再确认 profile SOUL 是否已同步到 live runtime 并重启 gateway。

## 2026-04-28 - MemTidy 退役与待办拆分门禁

类型：refactor
范围：`cron/jobs.json`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`、`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`skills/library/memtidy/`、`config/memtidy_rules.json`
事实：根据用户确认，Hermes 已有记忆整理能力，本仓删除 MemTidy 自动修改型能力：不再注册 `memtidy_runner（每日记忆整理）` cron，不再通过 runtime installer 安装 `memtidy` skill / `memtidy_runner.py`，并移除本仓 `memtidy_rules.json`。当时待办自动运行链保留；2026-04-28 已进一步收口为到期 TODO 先人工路线选择，backlog runner 只推进已确认走 pipeline 的 Task Center 项。`delivery_plan.json` 现在会把多事项需求拆成 `scope_slices`，第一块为 `current`，后续块为 `deferred`，避免一个 pipeline run 吞掉过重任务。
证据：`cron/jobs.json` 删除 memtidy job；`runtime_installer.py` 删除 `memtidy` 和 `memtidy_runner.py` 安装项；`pipeline_runner.py` 新增 `plan_scope_slices()`、`task_split_policy` 和 solution 展示；新增单测覆盖重任务拆分。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner` 31 项 OK；`python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_runtime_installer tests.scripts_openclaw_ops.test_active_agent_registry` 5 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol`、JSON 解析和 `git diff --check` 通过。
复用建议：以后用户要求“自动推进待办”时，保留 TODO/deadline/backlog runner；如果任务过大，由主代理/项目交付契约先拆小，只有凭证、资金、生产破坏、需求不清或需要核对的点才回问用户。

## 2026-04-28 - DeliveryPlan 结构化方案契约与 revise_solution 回流

类型：bugfix
范围：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`、`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：修复 nofx pipeline 方案阶段总被 `solution_review` 拦住的结构性问题。`solution_package` 现在生成通用 `delivery_plan.json` 作为交付契约，`solution.md` 只从契约渲染，避免靠 Markdown 文案过 reviewer。契约字段覆盖任务类型、owner、切片、目标文件/定位策略、实施步骤、验证命令、发布/回滚门禁、人工阻塞条件和安全边界；`solution_review`、`code_execution` 和后续阶段上下文都会读取该契约。`revise_solution` 加入自动回流白名单；否定式安全边界如 “do not set PRODUCTION_TRADING_ENABLED=true” 不再误判为 high risk，正向启用真实交易/下单/资金/凭证仍 hard block。
证据：`compile_delivery_plan()`、`delivery_plan.json` artifact、`PIPELINE_DELIVERY_PLAN_FILE`、`stage_context_files()` 和 `REPAIRABLE_NEXT_ACTIONS` 已更新；新增/更新单测覆盖结构化契约、prompt 注入、非代码 stage 隔离 artifact 写入路径、`revise_solution` 自动回流和真实交易正向表达 hard block。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 96 项 OK；nofx 已安装 runtime 代码批次 `3a44f0b0`，远端 `compileall` 与 67 项定向单测 OK
复用建议：方案评审要求 `requires_revision` 时先看 `delivery_plan.json` 和 `solution_review.md` 的结构化缺口，不要放松 reviewer。修 pipeline/runtime 自身继续绕过 Discord workflow，走外部 Codex/SSH/operator 改 hardflow、测试后再安装。

## 2026-04-28 - nofx Discord 证据短标签与 cron 群投递

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`cron/jobs.json`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_runtime_installer.py`
事实：Discord 状态卡中的证据项不再直接显示 `solution_review.md`、`command-runs/external_research-1.json` 这类文件名，而是显示 20 字以内中文短说明，例如“方案评审报告”“外部资料核对命令2”。完整证据目录和文件仍保留在 pipeline run 目录。`cron/jobs.json` 的 announce / failureAlert 投递目标已从旧 Telegram 群切到 spreadagent Discord 群 `1494595527181078578`，让定时任务结果和失败告警进入群里。2026-04-28 后续部署已把包含该变更的 runtime 代码批次 `3a44f0b0` 安装到 nofx live runtime，并同步两个 profile `SOUL.md`。
证据：新增证据短标签映射和单测；安装器测试校验 selected cron job 安装后的 delivery/failureAlert 指向 Discord 群；两个 nofx profile SOUL 要求状态卡证据项保持 20 字以内中文短说明；远端 `arbops@43.153.157.46` SSH 低频重试返回 `kex_exchange_identification: read: Connection reset by peer`。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 36 项 OK；`python -B -m json.tool cron/jobs.json`、`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过
复用建议：如果用户反馈状态卡证据看不懂，优先补 `ARTIFACT_EVIDENCE_LABELS` 的中文短标签；如果要换定时任务群，更新 `cron/jobs.json` 后重跑 runtime installer，不要改任务 payload。远端 SSH 恢复后按 nofx installer 流程同步本仓库到 `/home/arbops/.hermes`。

## 2026-04-28 - nofx 拉取并安装 runtime 代码批次 3a44f0b0

类型：deploy
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、nofx profile `SOUL.md`、runtime installer、cron jobs、内控 API
事实：本机 runtime 代码批次 `3a44f0b0` 已推送到 `origin/main`；nofx hardflow 仓库已安装该代码批次，安装时工作树 clean，`HEAD...origin/main=0 0`。后续文档/记忆记录提交可继续 fast-forward 到 `origin/main`，不改变本批 runtime artifact。runtime installer 返回 `ok=true`、`changed=true`，安装态 ops 文件与仓库源码 SHA256 对齐。两个 live profile `SOUL.md` 已同步仓库模板并备份为 `SOUL.md.bak-20260428T143343`，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
证据：远端 `compileall` 通过；远端 `python3 -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 67 项 OK；`smart-arb-pipeline --help` 正常；两个 gateway 均为 `running/connected`；内控 API `127.0.0.1:18080/health` 为 `status=ok`，`127.0.0.1:18080/api/strategy/status` 为 `running=false`。
最后验证：2026-04-28 14:40
复用建议：nofx 安装请求完成后要同时检查仓库 HEAD、runtime ops SHA256、profile `SOUL.md` SHA256、gateway connected 和内控 API；若 profile 模板有变更，安装器之外必须同步 live profile 并重启 gateway。

## 2026-04-27 - nofx 拉取并安装 067fbc43 hardflow runtime

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、Task Center、内控 API
事实：按“不要走工作流”的自修边界，从外部 Codex/SSH 直接完成 nofx hardflow 拉取与 runtime 安装。远端仓库已对齐 `067fbc43`，安装前备份 runtime 目标文件到 `/home/arbops/.hermes/ops/install/backups/pre-hardflow-install-20260427T151242Z`；安装后 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 的安装态 SHA256 与仓库源码一致。echo smoke 使用 `--skip-deployment-command` 与 `--skip-git-publish-command`，不重启服务、不执行 git publish、不触发真实 Hermes chat。
证据：远端 `git rev-list --left-right --count HEAD...origin/main` 为 `0 0`；`smart-arb-pipeline --help` 正常；远端安装态 `py_compile`、仓库 `compileall` 通过；远端定向 `unittest` 98 项 OK；cron 命中三项治理任务；两个 gateway `running/connected`；内控 API `/health` 为 `status=ok`，`/api/strategy/status` 为 `running=false`；echo smoke `install-smoke-arbitrageagent-20260427T151733781612Z` 完成且 Task Center `passed`；`smart-arb-api` cwd 为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 23:17
复用建议：workflow/runtime 自修时继续用外部 SSH/operator，不让 Discord profile 自己改自身；安装后必须复核安装态 hash、入口 help、Task Center smoke 和 `smart-arb-api` cwd。

## 2026-04-27 - nofx Discord 输出降噪与工作流状态卡

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/config.yaml`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：聊天频道不再默认展示 `[Background process ... finished]`、Hermes `Still working...` 心跳、tool progress、reviewer/tester/terminal stdout/stderr 或旧版“关键证据”列表。`smart-arb-pipeline` 的进度卡和最终状态卡保留 `agent 分工与完成情况`、`阶段命令状态`、`阻塞原因`、`自动修复判断` 和证据目录；命令状态默认只含 stage/agent/returncode/证据文件，调试时才用 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` / `--chat-include-command-output` 展开脱敏摘要。两个 nofx profile 模板新增 `agent.gateway_notify_interval: 0`、`display.tool_progress: off`、`display.background_process_notifications: off`，让长任务反馈由 pipeline 中文状态卡负责。
证据：`report_line()` 默认只输出 stage/agent/returncode/证据文件，`render_progress_update()` 使用 `## 最近命令状态`，`render_chat_summary()` 使用 `## 阶段命令状态`，`--chat-include-command-output` 和 `--chat-show-key-artifacts` 作为显式调试开关；两个 nofx profile 模板关闭 `gateway_notify_interval`、`tool_progress` 和 `background_process_notifications`。本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 32 项 OK；`python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；`git diff --check` 通过。
最后验证：2026-04-27 20:05
复用建议：以后用户反馈 Discord 输出太吵时，先区分 Hermes runtime 噪音和 pipeline 状态卡；通用心跳/background wrapper 在 profile config 关闭，业务进度只保留 `# nofx 任务执行进度` / `# nofx 任务执行状态`。不要把 command report 的原始 stdout/stderr 直接转发到聊天频道。

## 2026-04-27 - nofx Discord 运行中进度卡

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`
事实：Discord 入口不再只依赖 Hermes 自带 `Still working...` 心跳。`smart-arb-pipeline` 默认每 60 秒输出 `# nofx 任务执行进度`，展示 run id、已运行时间、阶段进度、当前阶段、最近命令状态和证据目录；`--emit-json` / no chat summary 模式会关闭运行中进度卡。runner 在长命令开始前写 `pipeline_state.json`，加入临时 `running` stage，命令完成后再刷新最终 stage record。进度卡输出会先脱敏，覆盖 header、普通赋值、JSON/TOML quoted sensitive key、常见短 secret 和长 token；预脱敏的 API key 占位文本在“需要凭证”上下文仍保持 high-risk，不自动回流。
证据：新增/更新 `test_render_progress_update_shows_current_stage_and_recent_output`、`test_live_command_writes_running_pipeline_state_before_completion`、`test_redact_text_handles_quoted_sensitive_assignments`、`test_redacted_secret_request_stays_high_risk`；完整相关 unittest 通过；`python -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；Codex code-reviewer 最终复审 `APPROVED`。
最后验证：2026-04-27 19:10
复用建议：后续 Discord 仍只显示 `Still working...` 时，先看 profile 是否调用了带 `--progress-interval-seconds` 的 `/home/arbops/.local/bin/smart-arb-pipeline`，再看对应 run 的 `pipeline_state.json` 是否在命令执行期间刷新，最后看 profile 是否把 stdout 分段回传到频道。不要把未脱敏的 `command-runs/*.json` 原文直接贴进聊天频道。

## 2026-04-27 - git_publish secret scan 误报修复

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`
事实：`git_publish` 的 staged diff secret scan 改为只检查新增行，并对 value 上下文做区分：真实 token 形态、真实 cookie / Authorization 值、OAuth secret、交易所 API key、`.env` 实值、高熵长随机串、PEM private key marker/material 仍 hard block；`DASHBOARD_BASIC_PASS`、`BASIC_PASS` 这类环境变量名、`os.getenv(...)` 空默认值、`rotatable-pass` 测试假密码、`Authorization: Basic Auth` 测试说明、Markdown 行内 `Authorization: Bearer <token>` 占位说明和“替换为实际强密码”文档占位不再误报。扫描器新增结构化 finding，包含脱敏 `file/line/rule/risk/blocking/snippet`；非占位的 `sample-*`、`*-example` 等敏感赋值仍按 high 阻断；`os.getenv(..., '真实 token')` 与真实短 `Authorization` payload 不会被环境变量或 test/example only 文本上下文放行。`fix_git_publish` 自动回流会识别 `Secret Scan Findings` 中的 high/blocking finding，真实 secret evidence 仍停人工。
证据：新增/更新测试 `test_staged_diff_secret_scan_allows_env_names_and_test_placeholders`、`test_staged_diff_secret_scan_allows_markdown_inline_basic_auth_placeholder`、`test_staged_diff_secret_scan_blocks_markdown_inline_real_authorization_value`、`test_staged_diff_secret_scan_blocks_real_secret_shapes`、`test_staged_diff_secret_scan_blocks_short_real_values_in_example_contexts`、`test_staged_diff_secret_scan_blocks_short_getenv_fallback_secret`、`test_staged_diff_secret_scan_blocks_unquoted_high_entropy_assignment`、`test_staged_diff_secret_scan_blocks_non_placeholder_example_assignments`、`test_staged_diff_secret_scan_blocks_hardcoded_getenv_fallback_secret`、`test_staged_diff_secret_scan_blocks_pem_private_key_lines`、`test_staged_diff_secret_scan_reports_redacted_file_line_and_rule`、`test_git_publish_blocks_real_secret_with_redacted_findings`、`test_staged_diff_secret_scan_allows_basic_auth_test_placeholders`、`test_staged_diff_secret_scan_ignores_removed_secret_lines`、`test_staged_diff_secret_scan_allows_scanner_code_diff`、`test_fix_git_publish_can_auto_repair_without_secret_evidence`、`test_fix_git_publish_stays_high_risk_with_secret_evidence`、`test_fix_git_publish_stays_high_risk_with_secret_scan_findings`；本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过。
最后验证：2026-04-27 19:10
复用建议：以后处理 `Secret-like content detected in staged diff` 时，先打开 `command-runs/git_publish-*.json` 与 staged diff finding，区分“新增真实密钥值”和“环境变量名/测试占位/文档说明”；不要通过关闭 `git_publish` 或移除安全扫描绕过真实 secret hard block。

## 2026-04-27 - nofx 工作流自修闭环修复

类型：task
范围：`pipeline_runner.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、nofx SmartMultiPlatformArbitrage 工作区
事实：修复 nofx Discord 工作流自修循环与未验收业务补丁残留问题。`requirements.md` 保留本轮用户具体需求、禁止范围和安全边界，不再泛化成“构建端到端 pipeline”模板；requirements review 通过后新增 `resolved_requirement.md` 作为下游 handoff，`solution.md` 消费该 handoff；主工作区脏路径与 code patch 路径重叠时拒绝应用，`verification` 或 `code_review` 阻塞时会反向撤回已应用到主项目目录的 code workspace patch 并记录 rollback artifact，回滚失败会升级为 `rollback_cleanup/manual_cleanup_required`；两个 profile SOUL 增加工作流自修例外，避免“修 pipeline 本身”请求再次进入同一个 pipeline。远端 SmartMulti 主工作区中 `_close_position` / `execution_orchestration` 相关未通过 review 的业务漂移已隔离到 stash。
证据：本地 `python -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 共 68 项 OK；`python -m unittest tests.scripts_openclaw_ops.test_project_delivery_runtime_installer tests.scripts_openclaw_ops.test_project_delivery_hermes_profile_smoke tests.scripts_openclaw_ops.test_active_agent_registry` 共 7 项 OK；本地合并定向测试 75 项 OK；`python -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；nofx SmartMulti `git status --short --branch` 回到 `## main...origin/main`，旧业务漂移 stash 为 `pre-workflow-fix-rejected-business-drift-20260427T075431Z`。nofx hardflow 已拉到 `429ce994` 并重装 runtime；远端 `compileall` 通过，75 项定向 unittest OK；live profile `SOUL.md` 已同步自修例外并重启 gateway，`arbitrageagent` / `spreadagent` 均为 `running` / Discord `connected`；内控 API `/health` 与 `/api/strategy/status` smoke 通过。
最后验证：2026-04-27 16:39
复用建议：后续 workflow runtime 自修先走外部 SSH/operator，不让 Discord profile 自己改自身；业务 patch 只有 verification/code_review 通过后才允许进入发布链路，失败时应检查 `rollback_*` artifact 和主工作区状态。

## 2026-04-27 - nofx 拉取并安装最新 hardflow runtime

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`、Task Center
事实：nofx hardflow 仓库已从 `44b4dae` fast-forward 到 `578b3f0`；本次远端工作区无脏改动，未创建 stash。runtime installer 已把最新项目交付 runtime 安装到 `/home/arbops/.hermes`，包括 `backlog_runner.py`、`repo_hygiene_reviewer.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 和 cron jobs。`arbitrageagent` / `spreadagent` gateway 已重启并恢复 connected。
证据：runtime installer JSON 返回 `ok=true`、`changed=true`；`compileall` 通过；定向单测 53 项 OK；cron 检查命中 `backlog_runner_30m`、`repo_hygiene_reviewer_2d`、`source_registry_watcher`；内控 API `/health` 与 `/api/strategy/status` smoke 通过；echo smoke `install-smoke-arbitrageagent-20260427T065537Z` 写入 Task Center 且状态 `passed`；受控 backlog runner smoke 任务 `todo-hardflow-install-smoke-20260427T070123Z` 被标记 `passed`，并写入 1 条 `backlog_runner_attempt`；`smart-arb-api` 最终 cwd 核对为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 15:01
复用建议：以后用户说“进入服务器安装最新代码”时，默认按 `DEPLOYMENT.md` 的 nofx 安装命令执行，并在测试后复核 gateway state、cron jobs、Task Center smoke 和 `smart-arb-api` cwd。

## 2026-04-27 - Task Center 待办持续推进 runner

类型：task
范围：`scripts/openclaw-ops/backlog_runner.py`、`cron/jobs.json`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`、`tests/scripts_openclaw_ops/test_backlog_runner.py`
事实：新增 `backlog_runner.py`，将 Task Center 中可安全执行的 backlog 转交给 runtime 内安装的 pipeline 入口继续推进；最初默认每 30 分钟由 `backlog_runner_30m` 最多推进 1 个低风险、无需人工确认、无需澄清任务。2026-04-28 已收口为只推进已确认走 pipeline 的任务。pending 任务必须有 `selected_route` 为 `coding_workflow` 或 `todo_auto_candidate`、`human_confirmed=true`、`action=confirmed_for_execution`；failed 任务必须显式 `--include-failed`、已有 pipeline route 记录且 `next_action` 在允许列表内。高风险、需确认、需澄清、人工升级、未选择路线和非 pipeline 手动选择任务不自动执行。runtime installer 已同步安装该脚本，cron `--pipeline-command` 指向 runtime `ops/smart_arb_pipeline_entry.py`，避免自定义 runtime home 下路径失效。
证据：新增测试覆盖 dry-run 只选择安全任务、真实执行时调用 pipeline 并把任务标记 passed、pipeline 启动失败不会卡在 running、安装器安装 `ops/backlog_runner.py`、自定义 runtime home 下 backlog cron payload 指向 runtime entry；相关测试 9 项 OK。
最后验证：2026-04-27 12:00
复用建议：该 runner 是“持续推进”入口，不是人工确认替代品。若 backlog 没有推进，先看任务是否被安全门禁跳过，再看是否达到 `max_attempts_per_task`，最后查 pipeline run id 对应的 `pipeline_state.json`。

## 2026-04-27 - 工作流合规收敛：风险分流、9 owner、双 reviewer

类型：task
范围：`deadline_to_task_bridge.py`、`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`openclaw.json`、`openclaw/openclaw.json`、`cron/jobs.json`
事实：历史实现中，到期 TODO 不再全部转人工确认，低风险到期项会创建 `dispatch_pipeline` 候选并由 backlog runner 推进；2026-04-28 已收口为默认人工路线选择，低风险项也先 `await_route_selection`。active agent 配置收敛为 9 个 workflow owner，cron 只挂 `coordinator/project-agent`。需求、方案、代码审查都必须有两条不同命令、不同 `reviewer_role`（`reviewer-a`/`reviewer-b`）的 reviewer command report，且 verdict 全部匹配才放行。
证据：相关测试覆盖低风险/高风险 TODO 分流、单 reviewer 阻塞、重复 reviewer role 阻塞、重复 command 阻塞、两 reviewer 放行、Hermes smoke 双 reviewer 同步、live bridge 三类 review verdict、entry 默认注入 reviewer-a/reviewer-b、active registry 与 cron owner 合规。
最后验证：2026-04-27
复用建议：后续回答“是不是 9 个 agent、是否双 AI 审核、低风险 TODO 是否自动推进”时，以 active registry 测试、pipeline command artifacts（含 `reviewer_role`）和 Task Center payload 为准，不再沿用旧 cron owner 口径。

## 2026-04-27 - nofx agent 口径与模型快照修正

类型：task
范围：`agents/`、`openclaw.json`、`openclaw/openclaw.json`、`memory/INDEX.md`、`memory/RUNBOOK.md`、`docs/核心主工作流/项目交付优先工作流/`、`docs/基础设施/多Agent体系/README.md`、`todo.md`
事实：修正关于 nofx “14 个常驻 agent”的误导口径。当前 nofx live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`，两者模型均为 `openai-codex/gpt-5.5` 且 gateway running；真正执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`，它们是阶段 owner / workspace / Task Center 标签，不是独立常驻 agent；前端/UI/页面/交互类代码执行可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。定时任务层只挂 `coordinator/project-agent`，`ops-agent/optimization-agent` 已退出 active 配置。2026-03 的 14 Agent 文档保留为历史 OpenClaw 注册表快照，不再作为 nofx 运行态结论；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
证据：2026-04-27 nofx 远程核对 profile config、gateway_state、tmux 会话、缺失常驻 agent 目录、cron/jobs 和 hardflow 仓库 HEAD；本地 `openclaw.json`、`openclaw/openclaw.json`、pipeline runner、entry、live bridge 与文档已统一为 2 个入口 profile、9 个 active workflow owner、2 类 cron owner；新增 active registry 测试保证配置和 cron 不再引用 `ops-agent/optimization-agent`。文档已同步标注当前 server runtime 仍在 `44b4dae`，尚未安装本仓库最新运行态。
最后验证：2026-04-27 11:14
复用建议：后续沟通一律使用“四层口径”：入口 profile、workflow runner、阶段 owner 标签、cron 责任标签；模型只对真实 profile 或明确 provider command 声明，不把标签误写成独立模型。

## 2026-04-27 - 2 天仓库精简巡检与 Git 发布门禁

类型：task
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、`source_registry_watcher.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：新增 `repo_hygiene_reviewer.py` 只读仓库精简巡检，默认每 2 天由 `coordinator` 执行；`source_registry_watcher` 频率也调整为每 2 天并修复 `--base-path` 生效；项目交付流水线新增 `git_publish` 可选阶段，默认 live entry 会注入该命令，提交说明必须中文且脱敏，失败回流 `fix_git_publish`；发布输入会优先采用 `memory_writeback` 隔离工作区 patch，避免漏掉文档/记忆写回变更，并禁止夹带 `command_cwd` 未验收脏改动。本轮修复仓库精简脚本对内联冲突标记示例的误报，并删除已跟踪的 `cron/jobs.json.bak.20260422220950` 备份文件。
证据：相关测试覆盖 pipeline git_publish 成功/失败、写回后 patch 进入发布工作区、未验收脏改动不进入发布工作区、entry 默认注入/可跳过、live bridge 中文 commit/push 与 commit message 脱敏、repo hygiene 只读扫描、冲突标记误报防护、source watcher base path、runtime installer 安装新脚本。
最后验证：2026-04-27 11:14 相关单元测试与 repo hygiene smoke 通过
复用建议：仓库治理候选不直接删除；通过人工确认后再进入交付流水线。Git 发布不替代部署，deployment 仍只做内控服务 smoke；真正生产部署需按对应项目 RUNBOOK 执行。

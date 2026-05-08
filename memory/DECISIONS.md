# DECISIONS

## 2026-05-08 - execution_guard 替代高权限关键词硬门禁

类型：decision
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pre_execution_risk.json`、`execution_guard.json`
事实：真实交易、下单、撤单、划转、提现、force push、删除、覆盖、数据库 drop/truncate/delete 等关键词不再自动停在 `risk_gate`。命中这些高权限动作时，runner 生成 `execution_guard.json`，按最小可执行金额/用户指定小额、账号/市场/地址白名单、idempotency、审计日志、状态回读、破坏性操作前备份、备份可读性证明、恢复命令和保留 TTL 继续执行。硬停只保留三类：凭证/secret/cookie/auth-state 泄露或打印/提交/写入，破坏性目标不明确，备份或审计准备失败。`--human-risk-confirmed` 仍可记录调用方确认，但不再是交易/资金/破坏性关键词继续执行的前置门禁。
证据：`HARD_STOP_PLAN_PATTERNS` 与 `GUARDED_OPERATION_PLAN_PATTERNS` 分离；新增 `build_execution_guard()`、`execution_guard.json` artifact、`guarded_execute` / `confirmed_guarded_execute` / `hard_block` 决策；entry 自动修复把交易/资金/破坏性动作降级为 medium 可回流，凭证仍 high；live bridge code_execution/review prompt 读取 `execution_guard.json`。测试覆盖交易 guarded 继续、凭证打印 hard_block、破坏性目标不明确 hard_block、明确目标+备份 destructive guarded、entry 54 项全模块 OK。
最后验证：2026-05-08 14:53
复用建议：后续遇到工作流因“真实交易/下单/提现/划转/删除/force push”字样卡住，先看 `execution_guard.json.guard_status` 和 `hard_stop_reasons`。如果 guard ready，应继续实现并落实小额/备份/审计/回读；不要恢复关键词硬停或反复要求用户二次确认。只有凭证泄露、目标不清或备份/审计失败才停。

## 2026-05-07 - solution_review 是方案质量软门禁

类型：decision
范围：`pipeline_runner.py`、`smart_arb_live_bridge.py`、`solution_review`、`code_execution`、`code_review`
事实：方案评审不再把普通方案质量 blocker 当成实现前硬停。只要 `solution_review` 有 reviewer 输出，且未命中凭证/secret/cookie/auth-state 泄露、破坏性目标不明确、备份/审计失败、明确绕过安全门禁等硬边界，`requires_revision` 会被写入 `solution_review_soft_gate.md` 并以 `soft_continue` 进入 `code_execution`。code agent 必须把这些 blocker 当作强约束吸收，后续 `code_review` 再硬性判断是否按需求、方案和 reviewer 约束完成。无 reviewer 输出仍不软放行；requirements_review 和 code_review 仍是硬门禁。2026-05-08 起，force push 和破坏性生产变更本身进入 `execution_guard.json`，不再因关键词硬停。
证据：`solution_review_can_soft_continue()`、`solution_review_hard_blocker_lines()`、`render_solution_review_soft_gate()`、`PIPELINE_SOLUTION_REVIEW_SOFT_GATE_FILE`；live bridge 的 code_execution prompt 要求读取 `solution_review_soft_gate.md` 并吸收 reviewer blocker。测试覆盖普通计划 blocker 软继续、凭证 blocker 硬停、live pipeline 软继续到 code_execution 并完成 code_review。
最后验证：2026-05-07 15:32
复用建议：以后不要因为 `solution_review` 发现 `create_if_missing`、verification、docs/memory、acceptance 等计划缺口而反复停住；这些属于可吸收约束。真正要停的是凭证泄露、目标不清、备份/审计失败，或完全没有有效 reviewer 输出。

## 2026-05-07 - reviewer 未通过时必须产出联合修订方案

类型：decision
范围：`pipeline_runner.py`、`smart_arb_live_bridge.py`、需求/方案/代码 review 门禁、`revise_solution`
事实：双 reviewer 不是只做二元审核票决。若任一有效 reviewer 给出 `requires_revision`、`fail` 或阶段非期望 verdict，review 阶段仍必须阻断，但输出必须包含完整非通过原因、两路 reviewer 的讨论/挑战和合并后的可执行修订计划。该计划要能落回 `delivery_plan.json`，包括目标文件处理、`create_if_missing` 理由、实施步骤、验收命令、发布 containment、文档/记忆断言、人工验收边界和剩余阻塞项。provider/model 不可用仍按 fallback / degraded single valid 规则处理；真实 blocker 不因 fallback 成功而被放行。
证据：`render_reviewer_discussion()`、`render_dual_ai_review()`、`review_failure_detail()` 与 `extract_review_blocker_lines()`；live bridge 的 review prompt 已要求 reviewer 不通过时写出全部 Blocker 和完整 revised plan。测试覆盖具体 reviewer blocker 即使另一 reviewer 通过仍阻断、双 reviewer 输出联合修订计划，以及最新 nofx run artifact 复盘后 `delivery_plan` 消除 root date path、缺 rationale、模板化步骤和验收缺口。
最后验证：2026-05-07 15:02
复用建议：后续不要把 reviewer 不通过输出压缩成“requires_revision”。状态卡、failure summary 和 auto repair context 都要保留可执行 blocker 清单；下一轮 `revise_solution` 应优先消费该清单，而不是重新生成泛化方案。

## 2026-05-07 - reviewer 模型不可用时按有效输出降级放行

类型：decision
范围：`pipeline_runner.py`、`smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py`、需求/方案/代码 review 门禁
事实：双 reviewer 仍是默认目标，但 provider/model 不可用属于运行时降级问题，不再等同于需求阻塞。入口会先用 reviewer 原始模型，再按 fallback 链 `zai/glm-5.1 -> zhipu/glm-5.1 -> openai-codex/gpt-5.5` 重试；如果某一路 reviewer 最终仍没有有效 verdict，只要至少另一路产出期望 verdict，且没有任何 reviewer 给出明确 blocker（例如 `requires_revision` / `fail`），该 review 阶段可按 `degraded_single_valid` 放行。若任一有效 reviewer 明确要求修订，仍必须阻断并进入修复循环。
证据：`DEFAULT_REVIEWER_FALLBACK_MODELS`、`reviewer_model_attempts()`、`run_hermes_stage()` fallback 循环、`valid_review_reports()`、`blocking_review_reports()`、`dual_review_pass()`；测试覆盖单有效 reviewer 放行、具体 blocker 阻断、同模型不再硬阻塞、入口默认注入 fallback 链和 live bridge Kimi 404 后切到 GLM。
最后验证：2026-05-07 00:55
复用建议：后续遇到 `reviewer-b provider/model ... HTTP 404`、`missing_verdict` 或 `command_failed`，先看 `command-runs/*review*.json` 是否已有至少一个有效期望 verdict，以及是否存在明确 blocker。模型不可用应修 provider/model 或 fallback 配置，不应把最终 verdict 改成 `requires_revision` 要人工确认。

## 2026-05-06 - SmartMulti 策略高风险确认后可继续执行

类型：decision
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`backlog_runner.py`、`cron/jobs.json`、nofx Discord profile
事实：该记录是 2026-05-06 的历史口径：真实交易、下单、划转、提现和资金类需求对 SmartMultiPlatformArbitrage 属于策略业务本身，不再作为永久阻断；当时需要 `--human-risk-confirmed` 后继续执行。2026-05-08 起，这类动作默认进入 `execution_guard.json`，`--human-risk-confirmed` 只记录确认来源，不再是前置放行条件；凭证保护、测试、双 reviewer、deployment、memory writeback 和 git_publish 仍不解除。
证据：`PipelineConfig.human_risk_confirmed`、`apply_human_risk_confirmation()`、`smart_arb_pipeline_entry.py --human-risk-confirmed`、`backlog_runner.py` 已确认高风险透传、`cron/jobs.json --allow-confirmed-high-risk`、profile SOUL 模板的高风险确认命令示例；测试覆盖高风险未确认阻断、确认后继续、backlog runner 透传确认、入口透传确认和 profile 模板。
最后验证：2026-05-06 22:58
复用建议：排查 2026-05-08 之后的新 run 时优先看 `execution_guard.json.guard_status` 和 `hard_stop_reasons`，不要只看 `--human-risk-confirmed`。不要关闭凭证、secret scan、测试、review 或发布门禁。

## 2026-05-06 - nofx 双 reviewer 默认不同模型

类型：decision
范围：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、双 reviewer 门禁
事实：该批次的原始目标是避免 reviewer-a/reviewer-b 都落到 `openai-codex/gpt-5.5` 而形成同模型伪双审，因此入口保持 reviewer-a 继承 live bridge 默认 `openai-codex/gpt-5.5`，reviewer-b 默认使用 `kimi-coding/kimi-k2.6`，仍允许环境变量或 CLI 覆盖。2026-05-07 已进一步收敛为“优先异构双审 + fallback 降级”：模型不可用或缺 verdict 时不再硬阻塞，只要至少一个有效 reviewer 通过且无明确 blocker 即可放行。
证据：`DEFAULT_REVIEWER_B_PROVIDER=kimi-coding`、`DEFAULT_REVIEWER_B_MODEL=kimi-k2.6`；`test_main_defaults_reviewer_b_to_distinct_model` 断言默认注入不同 provider/model；`hermes_profile_smoke.py` echo/hybrid reviewer 输出补齐 provider/model 元数据，避免 smoke 被 dual review gate 误判。
最后验证：2026-05-06 22:58
复用建议：后续 requirements/solution/code review 明明有有效通过却仍阻塞时，优先检查 `command-runs/*review*.json` 中的 `Reviewer role/provider/model`、`Final verdict`、fallback attempt 和明确 blocker；不能只看单个 reviewer-b 的 provider/model 失败。

## 2026-04-28 - Discord 入口所有任务先选择且 profile 为最高权限入口

类型：decision
范围：nofx Discord Hermes profile、Task Center 手动路线选择、SmartMultiPlatformArbitrage 项目交付入口
事实：Discord 入口不再只对“普通执行类任务”做路线选择，也不再保留只读查询、简单解释、普通沟通或“不走工作流”的直接执行例外。所有来自 Discord 的新任务都必须先发“执行链路选择”卡，并等待用户明确选择。连接 Discord 的 profile 是该入口的最高权限调度入口，负责路线选择、推荐理由、执行调度、状态回传和最终口径；Task Center owner、pipeline stage label、其他 agent 建议或旧文档口径不能覆盖 Discord 用户本轮选择。最高权限不等于跳过安全边界：凭证泄露仍 hard block，真实交易、资金、force push、删除生产数据和生产破坏必须通过 `execution_guard.json` 的保护契约。
证据：用户明确纠正“所有的任务都走选择，而且连接 Discord 的 agent 的权限最高”；两个 nofx profile 模板已写入“收到任何 Discord 新任务”“不要直接做只读查询或普通沟通”“Discord profile 是本入口的最高权限 operator”；`tests/scripts_openclaw_ops/test_nofx_profile_templates.py` 已覆盖该规则。
最后验证：2026-04-28 23:54；nofx live profile 已同步并重启 gateway
复用建议：以后 Discord 没有先问路线，优先检查 live `SOUL.md` 是否同步和 gateway 是否重启；不要只修 `human_inbox`、backlog runner 或 delivery plan。

## 2026-04-28 - 执行链路默认手动选择

类型：decision
范围：`deadline_to_task_bridge.py`、`human_inbox.py`、`backlog_runner.py`、项目交付优先工作流入口
事实：当前阶段不启用“系统自动决定执行链路”。系统可以推荐链路和原因，但用户必须手动选择：直接运行、需求探讨、指定 agent、指定编码工作流或 TODO 自动候选。到期 TODO 和通用 `create-task` 默认都先创建 `need_human_confirm=true/action=await_route_selection` 的路线选择候选；只有人工选择为 `coding_workflow` 或 `todo_auto_candidate`、记录 `selected_route`、且 action 为 `confirmed_for_execution` 后，`backlog_runner` 才能推进。选择为 `direct_run`、`requirement_discussion` 或 `specified_agent` 的任务不会被 backlog runner 偷偷执行；其中 `specified_agent` 必须显式提供 `--assignee <agent-id>`，否则保持 fail-close，不会把任务移出人工队列。
证据：`policy_route_selection.py` 统一路线选项、描述和 action 映射；`deadline_to_task_bridge.py` 复用该统一路线 helper 并生成 `route_selection.mode=manual_selection` 与 `human_question`；`policy_task.py` 让通用 `create-task` 默认进入手动路线选择，并让旧 `confirm-risk` 对未选择路线的任务 fail-close；`human_inbox.py confirm --route-choice` 记录 `selected_route`，CLI 支持 `--route-choice recommended`，且拦截未指定 assignee 的 `specified_agent`；`backlog_runner.py` 正向校验 `selected_route in {coding_workflow,todo_auto_candidate}`、`human_confirmed=true` 和 pipeline action；相关单测覆盖低风险到期 TODO、通用 create-task、旧确认入口拒绝、CLI 推荐路线、人工选择非 pipeline 路由、指定 agent assignee 防呆和 runner 正向门禁。
最后验证：2026-04-28 21:31 本地 `python -m unittest tests.scripts_openclaw_ops.test_human_inbox tests.scripts_openclaw_ops.test_policy_task_manual_route tests.scripts_openclaw_ops.test_deadline_to_task_bridge tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_workflow_selector -v` 18 项 OK；`py_compile` 覆盖 7 个改动脚本通过。
复用建议：后续要切全自动，必须先根据一段时间的推荐/人工选择/执行结果做准确率复盘，再只对稳定类型开放自动执行；不要直接恢复“低风险 TODO 自动入队执行”。

## 2026-04-28 - Discord profile 可直接维护工作流宿主

类型：decision
范围：`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、nofx hardflow workflow/runtime 修复
事实：普通 SmartMulti 业务交付仍走 `smart-arb-pipeline` coordinator pipeline；但当用户明确要求修复 hardflow workflow/runtime/profile/SOUL/dual review/auto-repair/git_publish/runtime installer/cron workflow，或说“给 Discord agent 更高权限 / 允许改工作流 / 工作流流程有问题”时，Discord profile 进入高权限工作流维护模式，不再递归启动同一条 `smart-arb-pipeline`。该模式允许直接切到 `/home/arbops/projects/openclaw-hardflow-backup-20260302` 修改工作流宿主、运行测试并按需安装 runtime；不能触碰凭证明文，真实交易、force push 或破坏性数据操作必须走 `execution_guard.json`。若 profile 无法启动真正独立 code-reviewer，最终状态卡必须标记 `review=pending_external`。
证据：两个 nofx profile 模板已新增“高权限工作流维护模式”；`tests/scripts_openclaw_ops/test_nofx_profile_templates.py` 覆盖该模式不能退回“只读诊断和状态回传”；`docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`、`memory/INDEX.md`、`memory/RUNBOOK.md` 已同步该边界。
最后验证：2026-04-28 19:59
复用建议：以后 Discord 里修 workflow 流程问题时，不要再让旧 workflow 评审自己；先走高权限维护模式或外部 SSH，维护 hardflow 宿主后再安装 runtime。普通业务修改仍回到 coordinator pipeline。

## 2026-04-28 - 普通 Codex 协作模式独立于工作流

类型：decision
范围：用户级 `C:\Users\Administrator\.codex\AGENTS.md`、项目交付优先工作流边界
事实：用户明确说“不要走工作流”“不走 workflow”“别进 pipeline”“先自己开发”“直接沟通”“我们先讨论”“这次不用自动流程”等时，主代理应进入普通 Codex 协作模式，不把请求包装进 OMX runtime workflow、Discord pipeline、Task Center backlog runner 或新的自动化 run。这不是只在 workflow 故障时才可用的降级路径，而是日常沟通和独立开发入口；仍必须保留项目事实核对、安全/生产确认、测试、code-reviewer、文档/记忆和 Git 门禁。
证据：`C:\Users\Administrator\.codex\AGENTS.md` 的 `10.1 OMX keyword 与 runtime workflow 边界` 已新增普通 Codex 协作模式规则；`docs/核心主工作流/项目交付优先工作流/README.md` 的 Out Of Scope 已同步该边界。
最后验证：2026-04-28
复用建议：以后用户要求“不走工作流”时，先判断是普通沟通/独立开发，还是 workflow 自身故障修复；两者都不启动新的 workflow run，但前者可以直接在当前 Codex 会话沟通和实现，后者按外部 operator/SSH 修 runtime。两者都不能跳过安全、测试、审查、文档/记忆和 Git 门禁。

## 2026-04-28 - MemTidy 退役，任务拆分进入交付契约

类型：decision
范围：`cron/jobs.json`、`runtime_installer.py`、`pipeline_runner.py`、`skills/library/memtidy/`
事实：Hermes 运行态已有记忆整理能力，本仓不再维护或安装 `memtidy_runner.py`，也不再注册 `memtidy_runner` 每日 cron。Task Center 待办自动推进保留；当需求包含多个独立事项时，`delivery_plan.json` 必须拆出 `scope_slices`，只把第一块作为本轮 `current` 执行，其余标记 `deferred`，需要继续时由后续 Task Center run 或用户确认推进。
证据：`cron/jobs.json` 已删除 `memtidy_runner（每日记忆整理）`；`runtime_installer.py` 不再安装 `memtidy` skill 或 `memtidy_runner.py`；`compile_delivery_plan()` 新增 `task_split_policy` 和 deferred slice 边界。
最后验证：2026-04-28
复用建议：后续遇到“任务太重”时，不要把大任务整包塞进一个 run；先拆出当前最小可验收切片，剩余事项留 Task Center 或人工确认。记忆整理类需求优先使用 Hermes 原生能力，不再恢复本仓 MemTidy。

## 2026-04-27 - 仓库精简采用专门巡检器而不是复用 reviewer

类型：decision
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、项目交付流水线
事实：代码精简、冗余文件、失效缓存、冲突残留和测试残留治理由 `repo_hygiene_reviewer.py` 承担定期只读扫描，cron 执行 owner 使用 `coordinator`。`reviewer` 仍负责需求、方案和代码审查裁决，不承担长期仓库清理执行。`optimization-agent` 不再作为 active agent 注册。
证据：`cron/jobs.json` 的 `repo_hygiene_reviewer_2d` 每 2 天运行一次；脚本只生成报告和 `repo_hygiene_candidate` 人工确认候选，不自动删除、不自动提交。
最后验证：2026-04-27
复用建议：下次需要“仓库保持整洁”时，先看 repo hygiene 报告和 Task Center 候选；真正删除或重构必须单独进入交付流水线，并通过测试、code reviewer 和 Git 发布门禁。

## 2026-04-27 - Git 发布只能作为通过门禁后的可选阶段

类型：decision
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`
事实：reviewer 审核通过后不会直接部署或上传 Git；发布阶段必须在 verification、code review、deployment（如有）、acceptance 和 memory writeback 全部通过后执行。`git_publish` 输入必须是已验收变更集：优先使用 `memory_writeback` 隔离工作区 patch，缺失时只回退到 `code_execution` patch，不发布 `command_cwd` 的未验收脏改动。提交说明、备注和变更描述必须使用中文且先脱敏；疑似密钥、远端冲突、认证失败或 push 失败会阻塞到 `fix_git_publish`。
证据：`pipeline_runner.py` 中 `git_publish` 位于 memory writeback 成功之后，并写入 `git_publish_input_patch_report`；`smart_arb_live_bridge.py --stage git_publish` 执行 `git diff --check`、`git diff --cached --check`、staged diff 密钥扫描、脱敏中文 commit message 和普通 `git push <remote> HEAD:<branch>`。默认不做 force push；如用户明确要求，必须先通过 `execution_guard.json` 记录目标分支、备份/回滚路径和审计证据。
最后验证：2026-04-27
复用建议：如果用户要求“审核完自动上传”，必须确认已经开启 `--git-publish-command`，并检查 `git_publish_report.md`；不要把 `reviewer pass` 误解为已经部署或已 push。

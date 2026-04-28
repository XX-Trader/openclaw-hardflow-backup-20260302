# DECISIONS

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
事实：普通 SmartMulti 业务交付仍走 `smart-arb-pipeline` coordinator pipeline；但当用户明确要求修复 hardflow workflow/runtime/profile/SOUL/dual review/auto-repair/git_publish/runtime installer/cron workflow，或说“给 Discord agent 更高权限 / 允许改工作流 / 工作流流程有问题”时，Discord profile 进入高权限工作流维护模式，不再递归启动同一条 `smart-arb-pipeline`。该模式允许直接切到 `/home/arbops/projects/openclaw-hardflow-backup-20260302` 修改工作流宿主、运行测试并按需安装 runtime；不能触碰凭证、真实交易、force push 或破坏性数据操作。若 profile 无法启动真正独立 code-reviewer，最终状态卡必须标记 `review=pending_external`。
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
证据：`pipeline_runner.py` 中 `git_publish` 位于 memory writeback 成功之后，并写入 `git_publish_input_patch_report`；`smart_arb_live_bridge.py --stage git_publish` 执行 `git diff --check`、`git diff --cached --check`、staged diff 密钥扫描、脱敏中文 commit message 和普通 `git push <remote> HEAD:<branch>`，不做 force push。
最后验证：2026-04-27
复用建议：如果用户要求“审核完自动上传”，必须确认已经开启 `--git-publish-command`，并检查 `git_publish_report.md`；不要把 `reviewer pass` 误解为已经部署或已 push。

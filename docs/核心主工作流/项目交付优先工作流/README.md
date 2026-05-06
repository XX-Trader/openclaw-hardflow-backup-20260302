# 项目交付优先工作流

> 状态：✅ Phase 6.6 已实现（dry-run 状态机 + Task Center 镜像 + 运营事件入队 + 人工队列 + live 命令适配层 + Hermes hybrid profile smoke + 手动链路选择 + backlog runner 受控推进） | 触发方式：人工触发 / 项目维护事件 / 运维事件 / 人工确认后的 Task Center backlog runner
> 上级目录：[核心主工作流](../README.md)
> 2026-04-24 运行态说明：旧 `install_workflow_profile.py` / `workflow_setup.py` 已删除；新安装入口是 `skills/library/project-delivery-pipeline/scripts/runtime_installer.py`，支持任意 `--runtime-home/--runtime-name`。
> 2026-04-24 需求收束：真实目标不是“把某个工作流装进 Hermes”，而是完善一整套编码流水线：自动探索需求、生成需求包、生成方案、编码、测试、代码审核、修复、验收、文档和记忆回写。
> 2026-04-24 Hermes 验证：WSL `/home/ubuntu/.hermes` 已完成 `hermes_profile_smoke.py --agent-mode hybrid --provider zai` 非 dry-run smoke；新 `hybrid-single-chat` 路径用一次 Hermes chat 生成 AI 阶段 bundle，run_id=`hermes-profile-smoke-20260424T135014Z`。
> 2026-04-25 nofx 验证：SmartMultiPlatformArbitrage Discord live 入口已补齐外部研究、双 AI 需求讨论、代码执行、验证、代码审查、内部 deployment 与记忆写回证据桥，详见 [Smart Arb nofx live evidence bridge](smart-arb-nofx-live-evidence-bridge.md)。
> 2026-04-27 治理增强：流水线在验收和记忆回写通过后可进入 `git_publish` 受控发布阶段，提交说明/备注必须使用中文；`source_registry_watcher` 与仓库精简巡检均调整为每 2 天一次，仓库精简由 `coordinator` 触发只读候选报告并进入人工确认。
> 2026-04-27 nofx 运行态口径：服务器 live 入口是 `arbitrageagent` 与 `spreadagent` 两个 Hermes Discord profile，模型均为 `openai-codex/gpt-5.5`；执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline -> /home/arbops/.hermes/ops/pipeline_runner.py`；`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` 是 workflow 阶段 owner / workspace 标签，不是 nofx 上 14 个常驻 agent。
> 2026-04-27 持续推进补齐：新增 `backlog_runner.py` 与 `backlog_runner_30m` cron。该能力已在 2026-04-28 收口为“人工确认后的受控推进”：到期 TODO 和通用 create-task 先进入路线选择，runner 只选择已确认走 pipeline、无需澄清且有 `selected_route` 正向凭证的待办，或带允许 `next_action` 且已有 pipeline 选择记录的 failed 项，调用 `smart-arb-pipeline` 继续推进。
> 2026-04-28 方案契约收敛：`delivery_plan.json.target_files` 只把用户原始需求/修复上下文中的显式路径作为高可信目标；review/research/project memory 仅作低信任补充，并过滤 `.workflow`、runtime host、Task Center、agent workspace、command report 和项目记忆控制文件。简单任务找不到可靠业务文件时保持 discovery required，不猜测编辑 workflow 宿主；被过滤的异常候选会进入 `plan_findings.filtered_target_candidates` 并展示到 `solution.md`。
> 2026-04-28 手动链路选择：当前默认不让系统自动决定“单 agent / 需求探讨 / 指定 agent / 编码工作流 / TODO 自动候选”。系统只输出推荐链路、原因和可选项；用户确认后才进入对应链路。到期 TODO 和通用 create-task 即使低风险，也先进入 `human_inbox.py` 的路线选择问题；只有被选择为 `coding_workflow` 或 `todo_auto_candidate` 且记录 `human_confirmed=true/action=confirmed_for_execution` 的项才允许 `backlog_runner` 推进。选择 `specified_agent` 时必须显式提供 `--assignee <agent-id>`。
> 2026-05-06 nofx/OpenClaw backup 当前口径：AI 能力提升后，任务拆分粒度不再作为 hard gate；需求分析必须基于 graphify 项目知识图谱来写，先用 God Nodes / Surprising Connections / Suggested Questions 定位核心模块、隐藏耦合和澄清问题；project-agent 必须综合项目记忆、RAG/graphify、当前 Git 分支、HEAD、dirty state、本地/远端分支和 fetch 结果；web-agent 负责外部资料或明确 `NO_EXTERNAL_LOOKUP_NEEDED`；多 reviewer 必须使用不同模型、合并所有意见并循环修复直到无 blocker、达到自动修复上限或触发高风险人工门禁。详见 [OpenClaw Backup 多 Agent 工作流当前口径](openclaw-backup-multiagent-current.md)。
> 2026-05-06 高风险确认贯通：真实交易、下单、划转、提现和资金类策略需求不再作为 SmartMulti 策略项目的永久阻断；它们仍会被标记为 high risk，但用户在路线选择或 human inbox 中明确确认后，入口/runner 会携带 `--human-risk-confirmed` 通过 `risk_gate`，后续测试、双 reviewer、deployment、memory writeback 和 git_publish 门禁保持不变。

## 功能概述

这条工作流用于把 OpenClaw / Hermes 的默认目标从“让系统持续自我进化”切换为“让系统持续稳定地完成编码交付”。

它不是单纯的安装器，也不是只做需求前置治理，而是一条完整的编码交付流水线编排层：

```text
需求进入
→ 自动探索项目上下文与外部成熟方案
→ 项目记忆检索定位：项目画像 / 决策 / API / 影响面
→ 生成需求包与验收标准
→ 双 AI 需求审查
→ 生成架构/实施方案
→ 双 AI 方案审查
→ 编码执行
→ 自动化测试与运行态验证
→ 双 AI 代码审核
→ 修复循环
→ 最终验收
→ 文档、项目记忆、Task Center 状态回写
→ 受控 Git 发布（可选，中文提交说明）
```

它解决的不是单点工具问题，而是主流程错位问题：

1. 需求和方案即使写得完整，AI 产出的第一版产品仍然经常存在结构、边界、实现质量问题。
2. 当前 `reviewer` 主要停留在代码后置审查，介入太晚，无法在方案不合理时提前阻断。
3. 新功能、新第三方 API、新技术选型经常需要先参考成熟方案，但当前流程没有把“先查官方与成熟实现”做成默认门禁。
4. 第三方 API、SDK、依赖规则会持续变化，项目需要专门的外部事实源维护，而不是临时碰到再查。
5. 不同项目的上下文、架构、API、历史决策和踩坑经验已经超过单次上下文窗口，需要独立的项目级记忆模块长期维护。

## 核心目标

1. **端到端编码交付**：把需求探索、方案、编码、测试、审核、修复、验收、回写和受控 Git 发布串成一条可重复执行的流水线。
2. **检索是第一反应**：任何新需求、新功能、新技术选型，第一反应就是直接去网上查，借鉴成熟方案再改，不浪费时间和 token 自己从零研究。
3. **双 AI 对抗式审查**：不是 1 个 AI 审核就完了，要 2 个 AI 互相探讨、互相质疑，得出最优方案。审查覆盖需求、方案、代码三个阶段。
4. **失败学习 → 文档回写**：如果某个模型对某类任务总是完成得不好，不要继续让它瞎做——去修改需求文档，明确告诉 AI 该怎么做，必要时去网上查方案补充到文档里。
5. **项目维护 owner 明确化**：`project-agent` 成为项目事实源 owner（项目介绍、API、规划、逻辑说明），具备强记忆能力，不同项目有不同记忆模块，超出上下文的部分由记忆分仓管理。
6. **自进化完全不做**：自进化这块不用研究，主要工作就是把整个流程实现全自动。所有自进化类任务从默认主链完全移除，不保留为"可选"。

## 核心能力

1. **自动需求探索**：自动读取仓库、现有文档、项目记忆、测试、日志、接口契约和官方资料，形成 `research_report.md` 与未知项清单。
2. **需求包生成**：把用户原始需求整理为范围、非目标、验收标准、风险、外部来源、影响面和待确认项。
3. **双 AI 对抗式审查（需求 + 方案 + 代码）**：
   - 需求审查：`reviewer-a` 与 `reviewer-b` 两条不同命令、不同 `reviewer_role` 的 command report 均输出 `Final verdict: ready_for_solution` 才放行。
   - 方案审查：两条不同命令、不同 `reviewer_role` 的 reviewer command report 均输出 `Final verdict: ready_for_implement` 才进入实现。
   - 代码审查：两条不同命令、不同 `reviewer_role` 的 reviewer command report 均输出 `Final verdict: pass` 才允许进入验收/写回/发布。
4. **编码执行编排**：通过 `--code-command` 接入 HardFlow Core / ACP / runtime agent 编码链，保证实现者只按通过审查的需求包和方案包工作。
5. **测试与验收编排**：通过多个 `--verification-command` 统一收集 lint、typecheck、unit、integration、smoke、部署验证和人工验收证据。
6. **修复循环**：测试失败或代码审查失败时，自动回到实现阶段；如果失败反复出现，则触发失败学习。
7. **失败学习与文档回写闭环**：当某个模型/某条流程反复做不好某类任务时，分析根因 → 去网上查正确做法 → 回写到需求文档/方案文档 → 下次执行时按新规则走。
8. **项目维护中枢**：`project-agent` 维护项目介绍、架构图、模块边界、API surface、外部依赖、规划与历史决策，每个项目独立记忆模块。
9. **项目级长期记忆**：按项目拆分的事实记忆、经验记忆、第三方来源、API watch 列表和影响面索引，超出上下文的长期知识存在项目记忆模块中。
10. **第三方 API 持续跟踪**：每 2 天检查第三方库来源，只跟踪项目声明过的官方 docs / changelog / repo。
11. **Task Center 可观测性**：每次流水线可镜像到 `task_center.db`，统一查看状态、阶段、agent 通信、输出和 incident。
12. **仓库精简巡检**：`coordinator` 每 2 天只读触发冗余文件、失效缓存、冲突残留、重复文件和测试残留扫描；只生成报告和人工确认候选，不自动删除。
13. **受控 Git 发布**：只有验证、代码审查、deployment（如有）、验收和记忆回写通过后才允许 `git_publish`；发布输入优先采用 `memory_writeback` 隔离工作区 patch，缺失时只回退到已验收的 `code_execution` patch，确保代码与文档/记忆写回作为同一个已验收变更集发布且不夹带未验收脏改动；提交说明、备注和变更描述必须使用中文并脱敏，禁止 force push。发布前只扫描 staged diff 的新增行：真实 token、真实 cookie、OAuth secret、交易所 key、`.env` 实值和高熵随机串 hard block；环境变量名、空值、`os.getenv(...)`、README 占位说明和测试假密码不应误报。
14. **运行态 agent 口径分层**：nofx 当前只有两个 live Hermes profile；阶段 owner 只负责隔离 workspace、状态卡展示和 Task Center 交接，不等于独立常驻模型进程。判断是否真正 native fan-out，必须看独立 session/run id。
15. **手动链路选择与待办推进**：系统先推荐执行链路，但默认由用户手动选择；`backlog_runner.py` 每 30 分钟最多推进 1 个已确认走 pipeline 的 Task Center 项。直接运行、需求探讨、指定 agent 等非 pipeline 选择不会被 backlog runner 偷偷执行；指定 agent 必须给出具体 assignee，避免任务从人工队列消失但没有负责人。
16. **高风险确认凭证贯通**：`human_inbox` / Discord 路线选择确认后的高风险 pipeline 项可携带 `--human-risk-confirmed` 进入 `code_execution`；该凭证只解除重复人工等待，不解除凭证保护、测试、双 reviewer、部署和发布门禁。

## 可控性与可维护性裁决

| 要求 | 实现方式 |
|------|----------|
| 流程清晰 | 固定一条状态机：需求 → 项目记忆定位 → research → 需求包 → 方案包 → 编码 → 测试 → 审查 → 验收 → 回写 → Git 发布（可选） |
| 功能可追踪 | 每次运行生成 `.workflow/pipeline-runs/<run_id>/pipeline_state.json`，并可写入 Task Center |
| 问题可定位 | `project_memory_context.md` 和 `IMPACT_MAP.json` 必须说明候选修改位置、测试和文档 |
| 执行可控 | 每个阶段都有 pass signal 和失败回退动作，不允许跳过审查或测试 |
| 代码可维护 | 结构化项目记忆 + keyword/symbol 检索是默认；向量 RAG / GraphRAG 只作为可插拔增强，不默认引入重服务 |

## 项目记忆与 RAG 策略

每个项目维护独立记忆模块：

```text
.workflow/project-memory/<project_key>/
├── PROJECT_PROFILE.md
├── DECISIONS.md
├── DELIVERY_RULES.md
├── API_REGISTRY.json
├── SOURCE_REGISTRY.json
├── IMPACT_MAP.json
└── RETRIEVAL_MANIFEST.json
```

默认策略是 hybrid local-first：先查结构化项目记忆、再查代码关键字/符号、必要时接向量 RAG。GraphRAG 只用于跨模块、多跳依赖、全局架构问题；不作为每次需求的默认成本。

## 子功能清单

| 子功能 | 说明 | 状态 |
|--------|------|------|
| 端到端流水线状态机 | 串联探索、需求、方案、编码、测试、审核、修复、验收、回写 | 🟡 MVP 已实现（dry-run） |
| 自动需求探索 | 新功能先查项目事实源、官方文档与成熟实现，再进入需求定义 | 🟡 方案已定义 |
| reviewer 前移 | reviewer 介入需求、方案、代码三个阶段 | 🟡 方案已定义 |
| 编码执行编排 | 调用 HardFlow Core / ACP 编码链，绑定已审查需求包和方案包 | ✅ `--code-command` live 适配已实现 |
| 测试与验收编排 | 聚合 lint、typecheck、unit、integration、smoke、部署验证证据 | ✅ `--verification-command` 证据收集已实现 |
| 代码审核与修复循环 | 代码审查失败自动回到实现；反复失败触发失败学习 | ✅ `--code-review-command` + 回退已实现 |
| project-agent 升级 | 维护项目画像、API 注册表、规划与记忆索引 | 🟡 方案已定义 |
| 项目级记忆模块 | 为每个项目建立独立记忆目录与摘要注入策略 | 🟡 方案已定义 |
| 项目记忆定位门禁 | 编码前定位模块、文件、测试、文档和历史决策 | ✅ MVP 已实现 |
| Task Center 镜像 | 将流水线状态、阶段、通信、输出、incident 写入任务中心 | ✅ MVP 已实现 |
| 到期 TODO 手动链路选择 | `deadline_to_task_bridge.py` 将到期 TODO 转为 `need_human_confirm=true` 人工路线选择候选，系统给出推荐链路但不自动开跑 | ✅ 已实现 |
| 异常日志自动建任务 | `exception_to_task_bridge.py` 扫描增量日志并按指纹去重创建运维任务/incident | ✅ 已实现 |
| 人工处理队列 | `human_inbox.py` 统一查看/确认/拒绝/澄清待人工处理、已升级和需确认任务 | ✅ 已实现 |
| 第三方 API watch | 项目维度维护官方来源和更新检查；默认每 2 天执行一次 | ✅ 已实现 |
| 仓库精简巡检 | `repo_hygiene_reviewer.py` 每 2 天只读扫描冗余、冲突、缓存、重复文件并创建人工确认候选 | ✅ 已实现 |
| Git 发布门禁 | `git_publish` 在前序门禁通过后执行中文 commit/push，失败回流 `fix_git_publish` | ✅ 已实现 |
| Task Center 受控推进 | `backlog_runner.py` 只挑选已确认走 `coding_workflow` / `todo_auto_candidate` 或其他已验收 pipeline 动作的安全待办，调用 `smart-arb-pipeline` 继续推进 | ✅ 已实现 |
| 联网 research 接入 | 接入 researcher/web agent 或外部命令，写入 `research_report.md` | ✅ `--research-command` live 适配已实现 |
| 项目记忆真实写回 | 验收后调用 `project_memory_writer.py` 写入项目记忆 | ✅ `--write-project-memory` 已实现 |
| 通用 runtime 宿主适配 | 同一流水线可安装到任意显式 runtime home，OpenClaw/Hermes 只是示例 | ✅ runtime adapter + installer + Hermes hybrid smoke 已实现 |
| 默认 cron 裁剪 | 自进化链退出默认主链，只保留项目交付核心链 | 🟡 模板已裁剪，安装入口待收口 |

## 与现有工作流的关系

### 与 ACP 全链路编码工作流的关系

- `ACP 全链路编码工作流` 继续负责编码阶段的 HardFlow Core、G0-G6 门禁、验收和完成前验证。
- 本工作流不是只位于 ACP 之前，而是包住 ACP：前置负责需求探索和方案审查，中段调用 ACP 编码链，后置负责代码审核、验收、修复循环和项目记忆回写。
- 后续默认主链调整为：

```text
需求输入
→ project-agent 建立/更新项目上下文
→ 外部成熟方案检索
→ 需求包生成
→ reviewer 双 AI 审需求
→ 方案包生成
→ reviewer 双 AI 审方案
→ ACP 全链路编码工作流实现
→ 自动化测试 / smoke / 部署验证
→ reviewer 双 AI 审代码
→ 修复循环或 tester 最终验收
→ project-agent 回写项目记忆
→ coordinator 受控 Git 发布门禁
```

### 与通用运营工作流的关系

- 通用运营工作流继续负责任务调度、Task Center、Task Executor、基础运维与任务派发。
- 但它不再承担“替代项目维护”和“替代方案研究”的职责。

## 范围边界

### In Scope

1. 项目级 PRD / 架构 / 实施规划的维护责任收口。
2. reviewer 的职责前移和审查标准重构。
3. 端到端编码流水线状态机。
4. HardFlow Core / ACP 编码链的受控调用。
5. 测试、代码审核、修复循环、最终验收和交付证据收集。
6. 项目级记忆与 API 来源管理。
7. 第三方方案检索和依赖更新 watch 机制。
8. 通用 runtime 宿主路径、任务中心和运行态状态适配。
9. 默认 cron/job 基线向项目交付主链收缩。
10. 执行链路推荐、人工选择和选择结果留痕。

### Out Of Scope

1. 不新增新的平行编码引擎，编码仍复用 HardFlow Core。
2. 不保留“为了优化 OpenClaw 自身而自动持续运行”的重型自进化链为默认主线。
3. 不在本阶段引入通用外部 workflow 下载市场。
4. 不在本阶段强依赖单一远端记忆后端，先允许本地项目记忆方案落地。
5. 不为不同 runtime 维护多套业务流程，宿主差异只允许存在于 runtime adapter。
6. 用户明确要求“不走工作流”“直接沟通”“先自己开发”时，不把本轮请求包装进 `smart-arb-pipeline`、Discord pipeline 或 Task Center backlog runner；直接回到普通 Codex 协作模式处理，但仍保留事实核对、安全、测试、审查、文档/记忆和 Git 门禁。

## 成功标准

1. 新功能在进入实现前，必须有明确的外部来源证据和方案审查结论。
2. 每个需求都有 `Coding Pipeline Run`，能追踪当前状态、产物、失败原因和下一步。
3. `reviewer` 不再只在代码完成后出现，而是在需求、方案、代码三个阶段都有阻断能力。
4. 编码完成后必须经过测试、代码审核、验收和文档/记忆回写；启用发布命令时还必须完成中文提交说明的受控 Git 发布，不能只以“代码已改”作为完成。
5. 每个活跃项目都有独立的项目画像、API 注册表、第三方来源和项目记忆模块。
6. 默认常驻 job 中，不再以“自动进化 OpenClaw 自身”为主目标。
7. 项目问题的修复经验、依赖更新和架构裁决能回写到项目事实源，而不是散落在聊天上下文里。
8. 推荐链路稳定前，所有用户入口和到期 TODO 都默认先手动选择；只有用户确认走 pipeline 的项才可被 backlog runner 自动推进。

## 文档清单

| 文档 | 内容 |
|------|------|
| [架构设计](项目交付优先工作流架构设计.md) | 角色拓扑、数据对象、流程分层、项目记忆与 API watch 结构 |
| [实施规划](项目交付优先工作流实施规划.md) | Phase 拆分、落地步骤、验证点、风险与回滚策略 |
| [Smart Arb nofx live evidence bridge](smart-arb-nofx-live-evidence-bridge.md) | SmartMultiPlatformArbitrage Discord 入口、Hermes runtime、live 证据桥、内部 deployment 边界与 nofx 验收证据 |

# OpenClaw Backup 多 Agent 工作流当前口径

更新时间：2026-05-06

## 1. 项目边界

本页描述的是 **OpenClaw backup / hardflow 多 agent 工作流**，不是 SmartMultiPlatformArbitrage 业务代码本身。

- 工作流宿主仓库：`/home/arbops/projects/openclaw-hardflow-backup-20260302`
- nofx runtime 安装目录：`/home/arbops/.hermes`
- 入口命令：`/home/arbops/.local/bin/smart-arb-pipeline`
- 业务项目示例：`/home/arbops/projects/SmartMultiPlatformArbitrage`

SmartMultiPlatformArbitrage 只作为被交付/被修改的业务项目之一；多 agent 协调、路线选择、review 门禁、risk gate、失败摘要、git publish 等能力属于 OpenClaw backup 工作流。

## 2. 用户期望的完整流程

当前目标流程是：

1. Discord 入口先等待人工选择执行链路。
2. 选择 `coding_workflow` / `todo_auto_candidate` / `specified_agent` 后，进入 live coordinator pipeline。
3. `project-agent` 先读取项目上下文、项目记忆、RAG/图谱、Git 当前分支、HEAD、脏工作区、本地分支、远端分支、fetch 结果，输出“项目地图”。
4. `web-agent` 查官方资料、外部方案、成熟项目或明确输出 `NO_EXTERNAL_LOOKUP_NEEDED` 与本地证据。
5. `project-agent` 与 reviewer 做需求讨论，综合项目地图和外部资料，形成完整需求、验收标准、风险边界、目标文件和测试命令。
6. 多个 reviewer 用不同模型独立审查需求；所有 blocker 合并后修订，直到无 blocker 或达到自动修复上限/高风险人工门禁。
7. `project-agent` 生成结构化 `delivery_plan.json`，`solution.md` 只作为人工可读渲染。
8. graphify/RAG 作为软上下文补充跨模块影响面；只在跨仓路径、凭证/密钥、真实交易/下单/划转等风险时变成 hard block。
9. 多个 reviewer 用不同模型独立审查方案；综合意见后必须全部通过，才能进入执行。
10. `coordinator` 输出 `group_plan_publish.md`，把完整执行方案、风险和验证方式回传群里。
11. `risk_gate` 写入 `pre_execution_risk.json`：低/中风险自动执行；高风险必须等人工确认。
12. `backend-dev` / `frontend-dev` / 指定 agent 执行代码或文档修改。
13. `tester` 运行确定性测试、compileall、diff check、API smoke 或项目指定验收。
14. 多 reviewer 用不同模型做代码审查；任一 reviewer 有 blocker 就回到修改/测试循环。
15. `deployer` 只在允许时部署或 smoke，不得擅自启动真实交易、下单、划转、读取凭证。
16. `git_publish` 在测试和 review 通过后提交/推送，并验证远端包含目标提交。
17. 任一步失败时写 `failure_summary.md`，把具体失败阶段、失败原因、下一步修复建议总结回群。
18. 完成后写回项目 memory/docs/todo/done，并输出中文状态卡。

## 3. 不再使用任务拆分粒度硬门禁

由于当前 AI 能力提升，OpenClaw backup 工作流不再把“任务拆得足够小”作为硬性放行条件。

新的规则是：

- reviewer 和 implementer 必须审视 **完整已接受需求**；
- 不允许为了粒度而制造人工延期项；
- 只有出现真实 blocker 时才阻断，例如：目标文件无效、上下文不足、测试缺失、生产风险、凭证风险、跨仓越权、需求本身矛盾；
- 可在 `delivery_plan.json.scope_slices` 中保留 `holistic-scope` 作为整体交付范围；
- 如果风险门禁判断为高风险，才等待人工确认。

## 4. 多 reviewer 多模型规则

reviewer 不是走过场。当前规则：

- 至少需要 reviewer-a 与 reviewer-b；
- reviewer-a 与 reviewer-b 必须有不同 `reviewer_role`；
- 必须暴露 provider/model 元数据；
- provider/model 组合必须不同，不能同一命令/同一模型伪装双 reviewer；
- requirements_review 期望 verdict：`ready_for_solution`；
- solution_review 期望 verdict：`ready_for_implement`；
- code_review 期望 verdict：`pass`；
- 任一 reviewer 未通过、命令失败、缺少角色、缺少模型或模型重复，都不能通过 dual review gate；
- 通过前必须把所有 reviewer 意见合并为 `Merged Reviewer Consensus`。

默认入口支持环境变量或 CLI 指定 reviewer 模型：

```bash
SMART_ARB_REVIEWER_A_PROVIDER=...
SMART_ARB_REVIEWER_A_MODEL=...
SMART_ARB_REVIEWER_B_PROVIDER=...
SMART_ARB_REVIEWER_B_MODEL=...
```

或：

```bash
smart-arb-pipeline \
  --reviewer-a-provider openai-codex --reviewer-a-model gpt-5.5 \
  --reviewer-b-provider <other-provider> --reviewer-b-model <other-model> \
  ...
```

## 5. project-agent 地图/RAG/Git 职责

`project-agent` 是项目地图 owner。进入方案和编码前，它必须综合：

- 项目记忆模块，例如 `PROJECT_PROFILE.md`、`DECISIONS.md`、`DELIVERY_RULES.md`、`IMPACT_MAP.json`；
- docs/todo/done/memory 事实源；
- 当前 Git 分支、HEAD、dirty state；
- 本地分支、远端分支、fetch/prune 结果；
- remote refs 中可能影响当前任务的分支；
- graphify/RAG 图谱上下文；
- 相关 API registry / source registry；
- 当前运行态或 smoke 证据。

输出产物：

- `project_memory_context.md`
- `git_repository_context.md`
- `graphify_context.md`
- `graphify_scope_validation.md`

project-agent 的核心问题不是“直接写代码”，而是回答：

1. 当前项目逻辑是什么？
2. 哪些文件/模块最可能需要修改？
3. 哪些测试/文档/配置必须一起更新？
4. 当前分支和远端分支有没有冲突或未合并事实？
5. 有没有历史决策约束本次改动？
6. 哪些范围必须交给 reviewer 或人工确认？

## 6. web-agent 职责

`web-agent` 负责外部资料，不代替 reviewer 做裁决。

它必须：

- 查询官方文档、SDK、API changelog、成熟方案或行业实践；
- 总结可复用方案和不适用点；
- 如果本地事实足够，必须明确写 `NO_EXTERNAL_LOOKUP_NEEDED`，并说明为什么无需联网；
- 输出 `research_report.md`，作为 requirements discussion 和 reviewer 输入。

## 7. 风险门禁

`pre_execution_risk.json` 是编码前风险事实源。

低/中风险：

- 可自动分配给前端/后端/tester/reviewer；
- 仍需完整测试与 review；
- 失败必须回流修复。

高风险：

- 凭证、token、cookie、OAuth、API key、私钥、auth state；
- 真实交易、下单、撤单、平仓、划转、提现、链上签名；
- force push、reset hard、删除生产数据；
- 跨仓越权或无法确认目标文件；
- 生产部署/权限边界不清。

高风险必须停在 `risk_gate`，等待群里人工确认。

## 8. 失败与自动修复循环

工作流不应在第一次失败后只说“失败”。必须记录：

- failed_stage；
- next_action；
- blocker evidence；
- reviewer blocker；
- 已尝试的修复次数；
- 自动修复是否允许；
- 下一步应该回到需求、方案、代码、测试还是部署。

自动修复策略：

- 默认最多 4 次；
- 只修复低/中风险、review contract、solution review、code review、verification 等可修复问题；
- 高风险不自动修，必须等人工；
- 每次修复都生成 `auto_repair_context_N.md`；
- 最终仍需通过多 reviewer、测试和 git publish。

## 9. 不同项目分开表示

在飞书/项目记录中，至少分开维护：

1. **OpenClaw Backup 多 Agent 工作流**
   - 需求分析：workflow 入口、project-agent、web-agent、multi-reviewer、risk gate、失败摘要、git publish、runtime install。
   - 执行顺序：先修 workflow，再安装 runtime，再用 workflow 执行业务项目。

2. **SmartMultiPlatformArbitrage 业务项目**
   - 需求分析：行情监控、价差监控、资金费率、币股、数字货币、借币、价差套利、前端展示。
   - 执行顺序：币股 MVP 口径、监控/Discord 查询验收、FundingRateScanner Phase 1、mock/replay、策略切片、signal-only/mock 闭环、借币/链上/真实交易后置。

3. **nofx 运行态/部署项目**
   - 需求分析：Hermes profile、FastAPI、dashboard proxy、cron/runtime、Git 身份、服务恢复。
   - 执行顺序：安全检查、runtime 安装、gateway/API smoke、状态卡回传、异常回滚。

这三个项目可以相互引用，但不能混成一个“SmartMultiPlatformArbitrage 文档”。

## 10. 当前实现检查点

必须保留并测试以下关键字符串/产物：

- `Task-splitting granularity control is disabled`
- `git_repository_context.md`
- `graphify_context.md`
- `graphify_scope_validation.md`
- `group_plan_publish.md`
- `pre_execution_risk.json`
- `failure_summary.md`
- `Merged Reviewer Consensus`
- `SMART_ARB_REVIEWER_A_PROVIDER/MODEL`
- `SMART_ARB_REVIEWER_B_PROVIDER/MODEL`

## 11. 验收命令

```bash
cd /home/arbops/projects/openclaw-hardflow-backup-20260302
python3 -B -m unittest \
  tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry \
  tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner \
  -v
python3 -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline
git diff --check
```

安装 runtime 前必须确认没有活跃 `smart-arb-pipeline` / `pipeline_runner.py` / `smart_arb_live_bridge.py` 业务运行。

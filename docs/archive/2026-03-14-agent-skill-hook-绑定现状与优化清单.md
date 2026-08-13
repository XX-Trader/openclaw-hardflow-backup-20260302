# Agent / Skill / Hook 绑定现状与优化清单

## 目标

把当前仓库里 `agent`、`skill`、`hook`、`task assignee` 的真实关系收敛成一份可检索说明，避免后续继续把“角色声明”“运行时装载”“任务派发”混在一起理解。

## 相关文档

- [2026-03-14-doc-map-agent-workflow.md](./2026-03-14-doc-map-agent-workflow.md)
- [2026-03-14-自我进化工作流问题记录.md](./2026-03-14-自我进化工作流问题记录.md)
- [2026-03-13-workflow-architecture-manifesto.md](./plans/2026-03-13-workflow-architecture-manifesto.md)
- [runtime-boundary.md](../integration/openclaw-bridge/runtime-boundary.md)

## 范围与真值源

以下结论以代码为准，不以聊天结论或历史索引截图为准。

### 运行时真值源

- `openclaw/openclaw.json`
  - 运行时 agent 列表
  - 默认入口 agent
  - subagent allowlist
  - bindings
  - hooks.internal.entries
  - skills loader 配置
- `scripts/openclaw-ops/install_workflow_profile.py`
  - 仓库 `hooks/`、`skills/` 如何注入官方 loader
- `skills/library/control-plane-ops/scripts/policy/task_executor_runner.py`
  - task-center 任务如何调用 agent
- `cron/jobs_agent_mapping.md`
  - cron job 到 agent 的当前映射

### 声明层真值源

- `skills/by_agent/*.md`
  - 每个 agent 声明的 skill 清单
- `skills/index/*.json`
  - skill 与 agent 的索引映射
- `agents/*/SOUL.md`
  - agent 角色边界、主线 skill 文本说明

## 当前结论

## 状态更新（2026-03-14 晚）

- `main` 已移除 `using-superpowers` 声明，当前仓库巡检 `missing_skills=0`
- 零 skill agent 已在 manifest 中显式标注 `capability_mode=role_only`
- runtime hook 矩阵已覆盖 builtin hook，包括 `boot-md`、`bootstrap-extra-files`、`command-logger`、`session-memory`
- 任务层 `required_capabilities / required_skills / allowed_agents` 已落地，执行器 preflight 已启用
- planner `allowAgents` 已接入 preflight 自动校验
- 已新增 `task-capability-coverage` 统计命令与 `cron/index/cron_agent_capability_matrix.json`

## 状态更新（2026-03-22）

- 默认产品口径已经收口为：`coding-default` 是唯一默认 workflow profile
- 平台总入口口径已经收口为：`需求澄清 -> 任务拆分 -> workflow 选择 -> 执行`
- `HardFlow` 的定位从“一个很强的 workflow”上升为“所有 workflow 共享的 Core”
- `capability` 现在被正式定义为 workflow 与 skill 之间的稳定接口
- `skill` 不再作为默认工作流的一等真值源，而是 capability 的实现说明
- task 层后续应补充 `workflow_profile_id`，避免“同一任务约束不属于哪条 workflow”继续漂移
- self-evolution 升级统一采用 `stable -> candidate -> compare -> promote/rollback` 口径

### 新的边界原则

从现在开始，推荐把这五层严格区分：

1. `workflow selector`
   - 定义需求澄清后如何选择 workflow profile
2. `workflow profile`
   - 定义阶段图、默认链路、评分策略、hook 策略
3. `capability`
   - 定义这条 workflow 某个阶段需要什么能力
4. `skill`
   - 定义 agent 如何实现该能力
5. `hook`
   - 定义运行时护栏和审计，不承载 workflow 真值

### 1. 任务不是直接绑定 skill

当前执行链路是：

`task-center task -> assignee -> agentId -> agent runtime -> agent 自带 skills / SOUL`

依据：

- `skills/library/control-plane-ops/scripts/policy/task_executor_runner.py` 直接把 `task.assignee` 写入 `agentId`
- `cron/jobs_agent_mapping.md` 只记录 `agent=...`
- 当前任务执行路径里没有 `task.skill`、`required_skill`、`required_capability` 这类正式字段

新的收口方向应是：

`workflow_selector -> workflow_profile -> stage -> required_capabilities -> allowed_agents -> agent runtime -> skill`

### 2. hook 不是绑定到单个 agent

当前 hook 是全局 runtime 级配置，而不是 agent 级配置。

依据：

- `openclaw/openclaw.json` 通过 `hooks.internal.entries.*` 全局启用
- `scripts/openclaw-ops/install_workflow_profile.py` 通过 `hooks.internal.load.extraDirs` 注入仓库 `hooks/`
- 当前配置里没有 `agent -> hooks` 的显式绑定段

### 3. skill 分成两层

- 声明层 skill
  - 由 `skills/by_agent/*.md` 与 `agents/*/SOUL.md` 描述
  - 体现“这个 agent 理应具备什么能力”
- 运行时补齐 skill
  - 由 `scripts/openclaw-ops/runtime-required-skills.json`
  - 通过 `ensure_runtime_skills.py` 安装到 runtime
  - 体现“运行时必须额外装什么”

这两层目前没有自动收敛成单一真值。

新的优先级应是：

`workflow profile > capability binding > skill declaration > runtime required skill`

### 4. 调度层字段与任务层字段需要分层理解

当前文档里容易混淆的不是“有没有能力字段”，而是“能力字段属于哪一层”。

- 调度层：
  - 真值源：`ScheduleInventoryEntry`
  - 目标：描述长期存在的 cron / scheduler / external trigger
  - 现有字段：`capability`、`required_skills`、`required_runtime`
- 任务层：
  - 真值源：TaskCenter 单个任务包
  - 目标：描述某次具体执行时的约束
  - 当前已存在字段：`assignee`
  - 建议补充字段：`required_capabilities`、`required_skills`、`allowed_agents`

约束：

- 任务层不是为了替代调度层。
- 调度层回答“这个任务长期依赖什么能力与运行时”。
- 任务层回答“这一次具体任务允许谁执行、缺能力时怎么回退”。
- 后续如果新增字段，必须显式说明属于哪一层，避免在不同文档里对同一个概念重复命名。

从默认编码工作流角度，建议新增或固定以下任务层字段：

- `workflow_profile_id`
- `required_capabilities`
- `required_skills`
- `allowed_agents`
- `verification_contract`

从平台总入口角度，建议后续再补一层选择字段：

- `workflow_selection_reason`
- `workflow_selection_inputs`

## 当前 agent -> skill 摘要

| agent | 声明 skills | 备注 |
| --- | --- | --- |
| `main` | `agent-manager`, `requirements-clarity`, `smart-workflow`, `result-synthesizer`, `intelligent-router`, `task-decomposer`, `codex` | 入口协调 |
| `coordinator` | `task-decomposer`, `smart-workflow`, `dispatching-parallel-agents`, `parallel-executor`, `agent-manager`, `requirements-clarity` | 规划与分发 |
| `backend-dev` | `feature-development`, `systematic-debugging`, `auto-fix`, `verification-before-completion`, `mcp-builder`, `using-git-worktrees` | 执行型 |
| `frontend-dev` | `frontend-design`, `feature-development`, `ui-ux-pro-max`, `verification-before-completion`, `auto-fix`, `playwright-interactive`, `webapp-testing`, `using-git-worktrees` | 执行型 |
| `doc-writer` | `writing-plans`, `docx`, `changelog-generator`, `internal-comms`, `product-requirements`, `baoyu-format-markdown`, `pdf`, `pptx`, `xlsx` | 文档型 |
| `reviewer` | `requesting-code-review`, `receiving-code-review`, `systematic-debugging`, `verification-before-completion`, `openclaw-security-audit` | 审核型 |
| `tester` | `playwright-interactive`, `webapp-testing`, `auto-fix`, `deployment-test`, `systematic-debugging` | 测试型 |
| `deployer` | `db-deploy`, `deployment-test`, `github-actions-runner`, `windows-fullstack-deploy`, `openclaw-security-audit` | 发布型 |
| `agent-factory` | 无 | 只有角色说明，无显式 skill 清单 |
| `ops-agent` | 无 | 只有角色说明，无显式 skill 清单 |
| `optimization-agent` | 无 | 只有角色说明，无显式 skill 清单 |
| `project-agent` | 无 | 只有角色说明，无显式 skill 清单 |
| `web-agent` | 无 | 只有角色说明，无显式 skill 清单 |

## 当前 runtime hooks

### 内置 hooks

- `command-logger`
- `session-memory`
- `boot-md`

### 本仓自定义 hooks

- `hardflow-command-guard`
  - 事件：`command:new`, `command:reset`
- `hardflow-audit`
  - 事件：`command`
- `hardflow-stop-gate-reminder`
  - 事件：`command:stop`
- `hardflow-policy-enforcer`
  - 事件：`command:new`, `command:reset`, `command:stop`

## 已确认问题

说明：

- 以下 8 项是实施前的原始问题清单。
- 其中“默认入口索引漂移、缺失 skill、零 skill agent 机器声明、runtime 替换映射、任务层能力字段、hook 事件矩阵、planner allowlist 校验”已在 2026-03-14 晚完成收口。
- 保留本节是为了追溯问题来源，而不是表示这些问题仍然未处理。

### 1. 绑定真值分散，且存在索引漂移

运行时真值在 `openclaw/openclaw.json`，但仓库里还存在：

- `agents/agent_index.md`
- `agents/agent_index.json`
- `skills/by_agent/*.md`
- `skills/index/*.json`

这些索引是辅助产物，不是运行时真值；一旦未同步，就会出现读者看到的配置和实际生效配置不一致。

### 2. 默认入口 agent 索引已经漂移

当前 `openclaw/openclaw.json` 里 `main` 是 `default: true`，但 `agents/agent_index.md` 显示的是 `coordinator` 为默认入口。

这说明“索引已过期”已经不是潜在风险，而是现存事实。

### 3. `main` 声明了缺失 skill

`skills/README.md` 明确记录缺失 skill 为 `using-superpowers`。
这会导致：

- 文档宣称 `main` 有该能力
- 实际 runtime/skills library 里却没有对应 skill

结果是“能力宣称”和“可执行资源”脱节。

### 4. 多个关键 agent 没有显式 skill 清单

当前这些 agent 只有角色说明，没有正式 skill 绑定：

- `agent-factory`
- `ops-agent`
- `optimization-agent`
- `project-agent`
- `web-agent`

这会带来两个问题：

- 人能靠 SOUL 理解职责，但机器无法稳定做 capability 校验
- 后续如果做 task routing / task preflight，很难基于 skill 自动判断是否该派给该 agent

### 5. 运行时补装 skill 与 agent 声明 skill 可能冲突

`runtime-required-skills.json` 会安装 `frontend-design-ultimate`，并声明与 `frontend-design` 冲突。
但 `frontend-dev` 的声明 skill 仍然写的是 `frontend-design`。

这意味着：

- 声明层告诉读者：前端 agent 绑定 `frontend-design`
- runtime 可能实际替换成 `frontend-design-ultimate`

如果不补充一层“运行时替换映射”，文档和实际能力集会继续漂移。

### 6. 任务层缺少 capability / skill 约束

当前任务执行只靠 `assignee`，没有显式表达：

- 需要什么能力
- 允许哪些 agent
- 依赖哪些 skill
- 不满足能力时该如何回退

这会导致任务派发能运行，但无法在执行前做结构化校验。

### 7. hook 是全局生效，但没有影响矩阵

目前能看到 hook 列表和事件，但还没有一份稳定矩阵说明：

- 哪些 hook 会影响 `/new`
- 哪些 hook 会影响 `/reset`
- 哪些 hook 会阻断 `/stop`
- hook 执行顺序的预期是什么

这不影响当前运行，但会增加排障成本。

### 8. subagent allowlist 与 task 路由之间缺少自动校验

`openclaw/openclaw.json` 维护了 `allowAgents`，但当前没有看到一条自动校验链路去确认：

- 规划器派发出去的 agent 是否一定在 allowlist 中
- 某些 cron / follow-up 任务是否可能绕过预期层级

当前主要依赖配置正确与 hook/policy 守门，而不是显式一致性校验。

## 优化清单

### P0：先把真值收敛

- [ ] 新增单一生成文件，例如 `agents/agent_capability_manifest.json`
  - 合并 `openclaw/openclaw.json`、`skills/by_agent/*.md`、`agents/*/SOUL.md`
  - 产出字段至少包含：`agent_id`、`default`、`model`、`allow_agents`、`declared_skills`、`runtime_skill_overrides`、`hook_events_affected`
- [ ] 增加一致性校验脚本
  - 校验 `openclaw/openclaw.json` 与 `agents/agent_index.*` 是否一致
  - 校验 `skills/by_agent/*.md` 里的 skill 是否都真实存在
  - 校验缺失 skill 是否只允许出现在白名单例外里
- [ ] 修正当前默认入口索引漂移
  - 重新生成 `agents/agent_index.md`
  - 重新生成 `agents/agent_index.json`
- [ ] 明确处理 `using-superpowers`
  - 要么补装该 skill
  - 要么从 `main` 声明层移除
  - 不应长期保持“声明存在、运行时缺失”

### P1：把“角色说明”升级为“机器可校验能力”

- [ ] 为零 skill agent 补正式能力声明
  - 至少覆盖 `project-agent`、`optimization-agent`、`ops-agent`、`web-agent`
  - 如果故意不使用 skill，也应显式标注 `capability_mode=role_only`
- [ ] 为 runtime 补装 skill 建立替换映射
  - 示例：`frontend-design -> frontend-design-ultimate`
  - 文档和校验脚本都要能识别这种替换，而不是把它当冲突漂移
- [ ] 为 hook 建一份事件影响矩阵
  - 推荐落盘为 `hooks/index/hook_event_matrix.json`
  - 字段至少包含：`hook_id`、`events`、`blocking`、`doc_path`

### P1：让任务派发具备“能力前置校验”

- [ ] 在 task schema 增加可选字段
  - `required_capabilities`
  - `required_skills`
  - `allowed_agents`
- [ ] 在 `task_executor_runner.py` 增加执行前 preflight
  - 校验 `assignee` 是否存在
  - 校验 `assignee` 是否满足 `required_capabilities` / `required_skills`
  - 不满足时返回结构化 `need_reassign`，而不是直接硬跑
- [ ] 在 planner / follow-up 建单脚本里补能力字段
  - `ops_cron_runner.py`
  - `web_intel_collect_runner.py`
  - `web_intel_review_runner.py`
  - `self_evolution_todo.py`

### P2：补运维与可观测性

- [ ] 增加一条统一检查命令
  - 示例：`python scripts/openclaw-ops/inspect_runtime_bindings.py --emit-json`
  - 输出 agent / skill / hook / binding / cron assignee 总览
- [ ] 把索引文件改成“只生成不手改”
  - 在文档中标明 generated
  - 安装或校验流程里自动刷新
- [ ] 为 cron -> agent -> capability 建一份矩阵
  - 解决“某个 cron 为什么落到这个 agent”不可追溯的问题
- [ ] 在验收清单增加绑定一致性检查
  - `openclaw hooks list --json`
  - `openclaw hooks check --json`
  - `openclaw agents list`
  - `python skills/library/openclaw-workflow-manager/scripts/ensure_runtime_skills.py --dry-run --emit-json`

## 推荐实施顺序

1. 先做索引统一与一致性校验，解决“看不清真值”的问题。
2. 再做零 skill agent 的能力声明，解决“机器无法判断是否能做”的问题。
3. 最后给任务 schema 增加能力字段和 preflight，解决“任务能派但不一定派对”的问题。

## 最小验证步骤

```bash
openclaw hooks list --json
openclaw hooks check --json
openclaw agents list
python skills/library/openclaw-workflow-manager/scripts/ensure_runtime_skills.py --dry-run --emit-json
python skills/library/openclaw-workflow-manager/scripts/bootstrap_runtime_agents.py --dry-run
```

如果上述输出与本文结论不一致，应优先以运行时命令结果和 `openclaw/openclaw.json` 为准，再回头刷新索引文档。

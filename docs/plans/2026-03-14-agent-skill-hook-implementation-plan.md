# Agent / Skill / Hook 绑定治理实施计划

## 目标

把当前仓库中分散的 `agent`、`skill`、`hook`、`task assignee` 关系，逐步收敛成“可观测、可生成、可校验、可渐进上线”的治理体系。

## 当前进度（2026-03-14）

- Phase 1 到 Phase 7 已完成，并补齐了收尾缺口。
- 当前状态：
  - `task_executor_runner.py` 保留全量 warn-only 统计，并对高风险任务启用严格拦截。
  - `main` 的缺失 skill 声明已移除，当前 `missing_skills=0`。
  - builtin hook 事件已纳入 `hook_event_matrix.json`，覆盖 `boot-md`、`bootstrap-extra-files`、`command-logger`、`session-memory`。
  - preflight 已增加 planner `allowAgents` 自动校验。
  - 已新增 `task-capability-coverage` 覆盖率统计命令。
  - 已新增 `cron/index/cron_agent_capability_matrix.json`。
- 强拦截命中后返回结构化 `need_reassign` 建议，不直接继续调用执行 agent。

这份计划只回答一个问题：

如果现在开始真正实施，先做什么，后做什么。

## 设计约束

- 先做只读观测，再做真值生成，最后才做执行拦截。
- 先解决“看不清”，再解决“跑不对”。
- 不一次性重写任务系统，只做渐进式兼容。
- 任务层新增能力字段时，不引入 `fallback_agents`。
- `PatternCard`、调度层字段、任务层字段都必须保持分层，不互相替代。

## 范围

### 本次实施覆盖

- runtime 绑定巡检
- agent / skill / hook 统一清单生成
- 已知静态漂移修正
- TaskCenter 任务能力字段扩展
- 执行前 preflight 校验
- 任务生产端逐步补齐能力字段

### 本次实施不覆盖

- 直接重写 `policy_enforcer` 主流程
- 重构全部 cron 安装器
- 一次性把所有历史任务迁移到新 schema
- 引入新的 agent fallback 机制

## 真值分层

### 运行时真值

- `openclaw/openclaw.json`
- `scripts/openclaw-ops/install_workflow_profile.py`
- `scripts/openclaw-ops/policy/task_executor_runner.py`

### 调度层真值

- `ScheduleInventoryEntry`
- 关键字段：
  - `capability`
  - `required_skills`
  - `required_runtime`

### 任务层真值

- TaskCenter 单个任务包
- 当前主字段：
  - `assignee`
- 计划新增字段：
  - `required_capabilities`
  - `required_skills`
  - `allowed_agents`

说明：

- 本计划不引入 `fallback_agents`。
- 如果未来真要做 fallback，应单独立项，而不是混进本轮治理。

## 实施顺序

### Phase 0：建立基线，不改行为

目标：

- 明确当前真实状态
- 冻结本轮实施前的观测基线

动作：

- 记录当前 `openclaw/openclaw.json`
- 记录当前 `skills/by_agent/*`
- 记录当前 `hooks/*/HOOK.md`
- 记录当前 `cron/jobs_agent_mapping.md`
- 导出当前 `agents/agent_index.*`

交付：

- 一份基线报告
- 一份待修问题列表

验收：

- 能回答“现在有哪些 agent、skill、hook、绑定关系”
- 能明确指出索引漂移、缺失 skill、零 skill agent、runtime 替换 skill

### Phase 1：先做只读巡检器

目标：

- 用脚本统一读取所有绑定真值
- 先发现问题，不修改运行时

建议新增：

- `scripts/openclaw-ops/inspect_runtime_bindings.py`

最小能力：

- 读取 `openclaw/openclaw.json`
- 读取 `skills/by_agent/*.md`
- 读取 `agents/*/SOUL.md`
- 读取 `hooks/*/HOOK.md`
- 读取 `cron/jobs_agent_mapping.md`
- 输出 JSON 报告
- 输出人类可读摘要

建议输出字段：

- `agents`
- `declared_skills`
- `missing_skills`
- `runtime_required_skills`
- `runtime_skill_conflicts`
- `hooks`
- `hook_events`
- `cron_agent_bindings`
- `index_drift`

验收：

- 不改任何配置
- 能稳定发现当前已知问题

### Phase 2：生成统一真值产物

目标：

- 让仓库里有一份明确的“机器可读能力清单”
- 降低人工比对多份文档的成本

建议新增：

- `agents/agent_capability_manifest.json`
- `hooks/index/hook_event_matrix.json`

建议重生成：

- `agents/agent_index.md`
- `agents/agent_index.json`

`agent_capability_manifest.json` 建议字段：

- `agent_id`
- `default`
- `model`
- `allow_agents`
- `declared_skills`
- `runtime_skill_overrides`
- `capability_mode`
- `hook_events_affected`

验收：

- 生成产物可以完全由代码推导出来
- 以后看 agent 能力优先看 manifest，而不是手工拼接多个来源

### Phase 3：修掉静态脏点

目标：

- 先把不需要运行逻辑就能修的脏点收掉

优先事项：

1. 处理 `using-superpowers`
   - 补装，或移除声明
2. 明确 `frontend-design -> frontend-design-ultimate` 的运行时替换关系
3. 给零 skill agent 补能力声明
   - `project-agent`
   - `optimization-agent`
   - `ops-agent`
   - `web-agent`
   - `agent-factory`

建议做法：

- 保持 SOUL 的职责描述
- 增加机器可读字段或生成规则
- 明确哪些 agent 是 `role_only`

验收：

- `main` 不再声明缺失 skill
- 关键 agent 不再处于“只有人能看懂、机器看不懂”的状态

### Phase 4：扩展任务层 schema，但先不拦

目标：

- 让任务开始显式表达能力需求
- 不破坏现有任务执行链路

计划新增任务字段：

- `required_capabilities`
- `required_skills`
- `allowed_agents`

兼容原则：

- 旧任务没有这些字段也能继续执行
- 新任务可以逐步写入这些字段
- 不引入 `fallback_agents`

验收：

- schema 扩展后，旧任务仍然可运行
- 新任务可以开始携带能力约束

### Phase 5：给执行器加 warn-only preflight

目标：

- 在真正拦截之前，先观察任务匹配质量

建议改造：

- `scripts/openclaw-ops/policy/task_executor_runner.py`

preflight 首阶段只做告警，不中断执行：

- 校验 `assignee` 是否存在
- 校验 `allowed_agents` 是否包含当前 `assignee`
- 校验 `required_skills` 是否被当前 agent 满足
- 校验 `required_capabilities` 是否被当前 agent 满足

建议输出：

- `preflight.ok`
- `preflight.warnings`
- `preflight.missing_skills`
- `preflight.missing_capabilities`

验收：

- 线上链路不因为新校验直接中断
- 能积累真实不匹配样本

### Phase 6：回填任务生产端

目标：

- 让新字段真正被使用起来，而不是只存在于 schema

优先改造脚本：

- `scripts/openclaw-ops/ops_cron_runner.py`
- `scripts/openclaw-ops/web_intel_collect_runner.py`
- `scripts/openclaw-ops/web_intel_review_runner.py`
- `scripts/openclaw-ops/self_evolution_todo.py`

建议策略：

- 先给高价值任务写能力字段
- 再给低频或实验链路补齐

验收：

- 新建任务中，至少核心链路具备能力字段
- 能统计“多少任务已升级到新 schema”

### Phase 7：把 preflight 从 warn 提升到 enforce

前提：

- manifest 稳定
- 关键 agent 的能力声明稳定
- 主要任务生产端已回填能力字段
- 已观测到 warn-only 阶段没有高频误报

升级动作：

- 缺失关键能力时，返回结构化 `need_reassign`
- `allowed_agents` 不匹配时，拒绝直接执行

验收：

- 错派任务可以被稳定拦住
- 正常任务不会因为治理收紧而大面积误伤

## 交付物清单

### 第一批必须交付

- `inspect_runtime_bindings.py`
- `agent_capability_manifest.json`
- `hook_event_matrix.json`
- `cron_agent_capability_matrix.json`
- 一致性校验命令

### 第二批交付

- 任务 schema 扩展
- 执行器 warn-only preflight
- 若干任务生产端字段回填

### 第三批交付

- enforce 模式
- 验收文档与巡检报告

## 验收命令

```bash
python scripts/openclaw-ops/inspect_runtime_bindings.py --emit-json
openclaw hooks list --json
openclaw hooks check --json
openclaw agents list
python scripts/openclaw-ops/ensure_runtime_skills.py --dry-run --emit-json
python scripts/openclaw-ops/bootstrap_runtime_agents.py --dry-run
python scripts/openclaw-ops/policy/policy_enforcer.py task-capability-coverage
```

进入任务层阶段后补充：

```bash
python scripts/openclaw-ops/policy/task_executor_runner.py --help
python -m unittest tests.scripts_openclaw_ops.test_task_executor_output_contract
```

## 风险与控制

### 风险 1：过早拦截导致现有链路中断

控制：

- 先上 warn-only，再上 enforce

### 风险 2：文档定义了字段，但生产端长期不写

控制：

- 先选核心任务生产端回填
- 增加升级覆盖率统计

### 风险 3：manifest 生成规则不稳定

控制：

- Phase 1 先做只读巡检
- Phase 2 再冻结生成规则

### 风险 4：调度层和任务层再次混淆

控制：

- 所有新文档都必须明确字段所属层级
- 不允许把 `ScheduleInventoryEntry` 字段直接抄成任务字段

## 推荐开工点

如果现在就开工，建议第一步只做：

1. 新建 `inspect_runtime_bindings.py`
2. 生成一版 JSON 报告
3. 根据报告确认静态脏点清单

原因：

- 风险最低
- 能最快得到真实问题列表
- 不会打断现有任务执行

## 相关文档

- [2026-03-14-doc-map-agent-workflow.md](../2026-03-14-doc-map-agent-workflow.md)
- [2026-03-14-agent-skill-hook-绑定现状与优化清单.md](../2026-03-14-agent-skill-hook-绑定现状与优化清单.md)
- [2026-03-14-agent-skill-hook-实施验收报告.md](../2026-03-14-agent-skill-hook-实施验收报告.md)
- [2026-03-14-external-pattern-learning-pipeline.md](./2026-03-14-external-pattern-learning-pipeline.md)
- [2026-03-14-pattern-card-field-spec.md](./2026-03-14-pattern-card-field-spec.md)
- [2026-03-13-workflow-architecture-manifesto.md](./2026-03-13-workflow-architecture-manifesto.md)

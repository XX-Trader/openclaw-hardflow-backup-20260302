# OpenClaw 基建设施输入输出与通信标准

- 状态: Accepted
- 生效日期: 2026-03-23
- 适用范围: `scripts/openclaw-ops/`、`scripts/hardflow/`、task-center、workflow profile、benchmark、control-plane、公告链、后续新增 workflow

## 1. 决策摘要

从今天开始，OpenClaw 的自动化主链不再允许“每个 runner 自己发明一套输入、输出、日志和通信格式”。

后续所有升级、优化、回滚、benchmark、公告、人工介入，都必须建立在统一契约上。统一契约的目标不是为了好看，而是为了让以下事情稳定可做：

- 自动删环节
- 负载均衡
- 并行自适应
- profile 自动回写
- 定向 benchmark 验证
- incident 升级与回滚
- dashboard / summary / announce 统一消费

一句话要求：

**文档先定义契约，registry 声明目标，runner 按契约执行，acceptance 按契约验收。**

## 2. SSOT 顺序

与本标准相关的唯一事实来源顺序如下：

1. 本文档  
2. [OpenClaw 基建模板文档](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/templates/openclaw-foundation-contract-templates.md)  
3. [FIELD_DICTIONARY.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)  
4. [workflow-profile-registry.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/workflow-profile-registry.json)  
5. [benchmark-suite-registry.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/benchmark-suite-registry.json)  
6. 运行时代码实现

如果文档与代码冲突：

- 短期以代码真实行为为准
- 但必须在同一批变更里把文档补齐
- 不允许长期存在“代码靠猜、文档靠记忆”的状态

## 3. 必须统一的 8 类对象

后续所有新能力，都必须落到以下 8 类标准对象之一：

1. `HumanRequestEnvelope`
2. `TaskEnvelope`
3. `AgentExecutionInput`
4. `AgentMessageEnvelope`
5. `AgentResultEnvelope`
6. `StandardOutputPacket`
7. `IncidentEnvelope`
8. `BenchmarkRunEnvelope`

如果某个脚本需要新增结构化对象，必须先回答两个问题：

- 它属于上面哪一类的扩展？
- 为什么不能复用现有对象？

## 4. 全链路强制字段

以下字段必须成为后续所有自动化链路的稳定骨架：

- `task_id`
- `workflow_profile_id`
- `workflow_channel`
- `stage_id`
- `selection_reason`
- `selection_inputs`
- `assignee`
- `required_capabilities`
- `required_skills`
- `allowed_agents`
- `required_runtime`
- `tool_requirements`

后续新增自动化链路时，默认还必须补齐两类统一字段：

- `trace_id`
- `attempt_id`

当前代码里已经广泛使用 `task_id / workflow_profile_id / stage_id / selection_inputs`，但 `trace_id` 还没有做到全链路强制统一。因此从这份标准开始：

**新脚本、新 runner、新公告链，必须优先支持 `trace_id`。**

## 5. 日志与追踪标准

### 5.1 当前可复用的事实表

当前 task-center 已经提供以下标准存储面：

- `task_events`
- `stage_runs`
- `module_logs`
- `module_communications`
- `task_outputs`
- `task_incidents`
- `benchmark_runs`
- `workflow_selection_records`

### 5.2 后续统一追踪要求

后续所有脚本至少要做到：

1. 启动时记录模块日志
2. 跨模块通信时记录通信日志
3. 结束时记录标准化结果
4. 失败时记录 incident 或失败事件
5. 能够通过 `task_id + trace_id` 回放单次执行链

### 5.3 推荐追踪骨架

后续应逐步统一成：

- `trace_id`: 一次端到端运行的全局追踪 ID
- `task_id`: 任务实体 ID
- `attempt_id`: 同一任务的第几次执行
- `correlation_id`: 模块间一次消息交换的链路 ID

## 6. 标准化升级原则

升级 workflow 或 capability 时，不允许直接靠经验修改若干文件。必须按以下顺序：

1. 文档写清楚改动目标
2. registry 声明改动目标
3. dispatcher / applier / validation 执行
4. benchmark 验证
5. acceptance 验收
6. 不通过则 rollback

也就是说，升级必须是：

**文档驱动的声明式变更**

而不是：

**经验驱动的脚本式操作**

## 7. 哪些字段允许自动回写，哪些必须人工确认

### 7.1 可自动回写

以下字段可以在控制面自动优化链中进入 `candidate` 通道：

- `parallel_execution`
- `simplification_hint`
- `optimization_hints`
- `clarification_required_fields`
- stage 级提示性 contract 扩展

### 7.2 默认需要人工确认

以下变更默认不允许静默自动回写：

- 新增或删除 workflow profile
- 大规模 stage 删除
- score gate 阈值大幅变更
- benchmark suite 删除或基线数量大幅变更
- capability 允许 agent 范围扩张
- tool/runtime 安全边界放宽

## 8. 以后必须一起统一的内容

除了输入输出模板本身，后续还必须一起统一这些东西：

1. `TraceContract`
2. `ExecutionEnvelope`
3. 状态枚举
4. 错误码与失败原因枚举
5. incident 生命周期
6. telemetry 字段
7. benchmark 结果字段
8. 版本号与 schema 兼容策略
9. 人工审批与回滚策略

如果只统一“输入输出长什么样”，而不统一这些支撑字段，后面的自动优化还是会逐步失控。

## 9. 后续实现要求

从本文生效后，所有新增 runner、workflow、benchmark、公告链、profile 更新器都必须满足：

- 先查本文档
- 再查模板文档
- 再查字段字典
- 然后实现

不允许反过来先写脚本，最后再补文档。

## 10. 当前阶段的优先补齐项

本标准落地后，下一批最值得继续推进的是：

1. 全链路 `trace_id` 统一
2. `ExecutionEnvelope` 正式落地
3. 结构化 logger 包装层
4. 真正的生产链路 live 验收
5. dashboard 交互化产品层

## 11. 关联文档

- [OpenClaw 基建模板文档](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/templates/openclaw-foundation-contract-templates.md)
- [FIELD_DICTIONARY.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)
- [workflow-profile-registry.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/workflow-profile-registry.json)
- [benchmark-suite-registry.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/benchmark-suite-registry.json)

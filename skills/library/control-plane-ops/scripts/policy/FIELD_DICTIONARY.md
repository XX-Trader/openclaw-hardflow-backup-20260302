# OpenClaw Workflow 字段字典

## 2026-03-23 新增字段补充

- stage_execution_strategy
  - 所属对象：selection_inputs / preflight
  - 用途：统一汇总当前阶段的执行策略视图
  - 当前包含：parallel_execution、simplification_hint、optimization_hints

- stage_simplification_candidate
  - 所属对象：workflow evolution / optimization_hints
  - 用途：根据真实 stage 日志、质量评分、incident、benchmark 结果生成删环节候选建议
  - 当前落点：control_plane_optimization_advisor.py、workflow-profile-registry.json、selection_inputs.stage_optimization_hints

版本: `2026-03-23`

这份文档是运行时字段字典，不负责讲设计背景，只负责回答三件事：

1. 这个字段或对象是什么
2. 它现在存在哪里
3. 后续新增脚本时应该如何复用

设计原则与模板请优先查看：

- [OpenClaw 基建设施输入输出与通信标准](/docs/adr/2026-03-23-openclaw-foundation-contract-standard.md)
- [OpenClaw 基建设施模板文档](/docs/templates/openclaw-foundation-contract-templates.md)

## 1. 任务主表关键字段

当前任务主链的稳定字段包括：

- `task_id`: 任务唯一 ID
- `task_type`: 任务类型，例如 `workflow`、`clarification_required`
- `assignee`: 当前执行 agent
- `planner_id`: 当前 planner / coordinator
- `workflow_profile_id`: 任务归属 workflow
- `workflow_channel`: workflow 通道，例如 `stable`、`candidate`
- `stage_id`: 当前 workflow stage
- `selection_reason`: workflow 选择原因
- `selection_inputs`: workflow 选择与 stage 提示的结构化输入
- `required_capabilities`: 任务需要的 capability 列表
- `required_skills`: 任务需要的 skill 列表
- `allowed_agents`: 允许执行的 agent 列表
- `stage_score_gate`: 当前 stage 对应的评分 gate
- `stage_min_evidence_count`: 当前 stage 最少证据数
- `stage_output_contract`: 当前 stage 输出合同
- `stage_verification_contract`: 当前 stage 验证合同

## 2. `selection_inputs` 嵌套字段

`selection_inputs` 是当前运行时最重要的扩展字段之一。后续新增 workflow 或自动优化能力时，优先往这里补结构化上下文，而不是再发明新的散乱字段。

当前已稳定使用的嵌套字段包括：

- `selector_state`
- `matched_keyword_groups`
- `matched_keywords`
- `context_fields`
- `context_fields_missing`
- `capability_binding`
- `stage_context_gate`
- `stage_parallel_execution`
- `stage_simplification_hint`
- `stage_optimization_hints`
- `stage_required_fields`
- `stage_missing_context_fields`

## 3. capability binding 字段

`selection_inputs.capability_binding` 当前用于承接 capability -> assignee/runtime/tool 绑定结果。

推荐稳定字段：

- `resolved_assignee`
- `required_capabilities`
- `required_skills`
- `allowed_agents`
- `required_runtime`
- `tool_requirements`
- `binding_reason`
- `candidate_agents`

## 4. task-center 标准表

### 4.1 `task_events`

用途：

- 记录任务生命周期事件

关键字段：

- `task_id`
- `ts`
- `actor`
- `event_type`
- `stage`
- `details_json`

### 4.2 `stage_runs`

用途：

- 记录单个任务某个 stage 的执行状态

关键字段：

- `task_id`
- `stage`
- `agent_id`
- `model_id`
- `status`
- `started_at`
- `finished_at`
- `duration_ms`
- `exit_code`
- `error_reason`
- `input_ref`
- `output_ref`
- `details_json`

### 4.3 `module_logs`

用途：

- 记录模块自身运行日志

关键字段：

- `task_id`
- `module_name`
- `phase`
- `level`
- `status`
- `message`
- `duration_ms`
- `details_json`

### 4.4 `module_communications`

用途：

- 记录模块与模块之间的通信

关键字段：

- `task_id`
- `from_module`
- `to_module`
- `protocol`
- `message_type`
- `status`
- `latency_ms`
- `correlation_id`
- `payload_ref`
- `details_json`

### 4.5 `task_outputs`

用途：

- 记录标准输出包

关键字段：

- `task_id`
- `output_type`
- `audience`
- `channel`
- `status`
- `summary`
- `payload_json`

### 4.6 `task_incidents`

用途：

- 记录异常、人工介入、合同失败等 incident

关键字段：

- `task_id`
- `incident_type`
- `severity`
- `status`
- `reason`
- `summary`
- `owner`
- `details_json`

### 4.7 `benchmark_runs`

用途：

- 记录 benchmark suite 的一次运行结果

关键字段：

- `benchmark_run_id`
- `task_id`
- `benchmark_suite_id`
- `workflow_profile_id`
- `workflow_channel`
- `target_kind`
- `target_id`
- `baseline_run_ids`
- `candidate_run_ids`
- `summary_file`
- `scorecard_file`
- `decision_json`
- `details_json`

### 4.8 `workflow_selection_records`

用途：

- 记录为什么这个任务进入了这个 workflow

关键字段：

- `selection_id`
- `task_id`
- `workflow_profile_id`
- `workflow_channel`
- `selection_reason`
- `selection_inputs`
- `selected_by`
- `created_at`
- `updated_at`

## 5. 标准输出包 `StandardOutputPacket`

当前 `policy_enforcer.py` 已经会构造统一输出包，核心结构如下：

- `schema_version`
- `task_id`
- `workflow`
- `outcome`
- `human_gate`
- `telemetry`
- `contracts`
- `delivery`

### 5.1 `workflow`

- `profile_id`
- `channel`
- `stage_id`
- `score_gate`

### 5.2 `outcome`

- `report_status`
- `task_status_before`
- `task_status_after`
- `task_action_after`
- `solved`
- `failure_count`
- `failed_items`
- `quality_score`
- `quality_grade`

### 5.3 `human_gate`

- `need_human_confirm`
- `human_confirmed`
- `needs_clarification`
- `clarification_reason`
- `requires_human_assistance`
- `notify_chat`

### 5.4 `telemetry`

- `duration_ms`
- `model_id`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cost_estimate`
- `task_token_usage`
- `task_timing`

### 5.5 `contracts`

- `stage_output_contract`
- `stage_verification_contract`
- `stage_contract`
- `stage_contract_gate`

### 5.6 `delivery`

- `channel`
- `status`
- `human_summary`
- `machine_summary`

## 6. incident 标准记录

当前统一 incident 记录推荐包含：

- `incident_type`
- `severity`
- `status`
- `reason`
- `summary`
- `owner`
- `details`

当前稳定 incident 类型示例：

- `task_escalated`
- `needs_clarification`
- `stage_contract_failed`

当前稳定状态枚举：

- `open`
- `acked`
- `resolved`
- `suppressed`

## 7. benchmark 记录与 promotion 相关对象

当前 benchmark 主链涉及的稳定对象：

- `benchmark-suite-registry.json`
- `benchmark_runs`
- `promotion_bundle`

建议稳定字段：

- `benchmark_suite_id`
- `workflow_profile_id`
- `baseline_channel`
- `candidate_channel`
- `target_kind`
- `target_id`
- `decision.veto_reasons`
- `decision.promote_to_new_baseline`

## 8. workflow profile 与 stage 声明

`workflow-profile-registry.json` 当前 stage 级稳定字段包括：

- `stage_id`
- `display_name`
- `score_gate`
- `min_evidence_count`
- `output_contract`
- `verification_contract`
- `required_capabilities`
- `required_skills`
- `clarification_required_fields`
- `parallel_execution`
- `simplification_hint`
- `optimization_hints`

## 9. CLI / runner 最小接入要求

每个新增 runner 至少要做到：

1. 启动时记录 `module_logs`
2. 跨模块协作时记录 `module_communications`
3. 结束时产出 `AgentResultEnvelope`
4. 对外输出时沉淀 `task_outputs`
5. 出现异常或人工门禁时沉淀 `task_incidents`

## 10. 当前缺口

这份字段字典已经能覆盖当前主链，但后续还要继续补齐：

- `trace_id`
- `attempt_id`
- 完整的 `ExecutionEnvelope`
- 统一错误码枚举
- 全链路结构化 logger 规范

这些会作为下一阶段标准化重点。
## 2026-03-23 Trace / ExecutionEnvelope 字段补充

- `trace_id`
  - 所属对象：`tasks / task_outputs / task_incidents / benchmark_runs / preflight`
  - 用途：统一串起任务创建、执行、输出、incident、benchmark 的最小追踪主键

- `attempt_id`
  - 所属对象：`tasks / preflight / execution_envelope`
  - 用途：区分同一条追踪链里的执行轮次，默认从 `attempt-001` 开始

- `execution_envelope`
  - 所属对象：`selection_inputs / preflight`
  - 用途：把当前执行所需的最小标准输入统一收口到一个结构里
  - 当前稳定包含：
    - `trace_id`
    - `attempt_id`
    - `task_id`
    - `workflow`
    - `task`
    - `routing`
    - `capability_binding`
    - `contracts`

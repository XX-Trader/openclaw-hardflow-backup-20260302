# Workflow 字段标准字典（日志/通信/回报）

版本: 2026-03-04  
适用命令:
- `policy_enforcer.py log-module`
- `policy_enforcer.py log-communication`
- `policy_enforcer.py report-agent-result`
- `policy_enforcer.py planner-summary`

## 1. 模块日志 `log-module`

用途:
- 记录模块自身执行状态，定位“模块内部”问题。

核心字段:
- `task_id`: 关联任务 ID（可空；为空表示流程级日志）
- `module_name`: 模块唯一标识，建议 `agent/module` 格式
- `phase`: 阶段，如 `dispatch` / `scan` / `project-index`
- `level`: `debug|info|warn|error`
- `status`: `started|running|passed|failed|timeout|skipped`
- `message`: 简要说明
- `duration_ms`: 本次执行耗时（毫秒）
- `details_json`: 扩展上下文（JSON 对象）
- `actor`: 记录执行身份

建议:
- 开始、结束都写一条；失败必须写 `level=error` 或 `status=failed/timeout`。
- `details_json` 固定放结构化数据，不放大段文本。

## 2. 模块通信日志 `log-communication`

用途:
- 记录模块间消息交互，定位“通信链路”问题。

核心字段:
- `task_id`: 关联任务 ID（可空）
- `from_module`: 发送方模块
- `to_module`: 接收方模块
- `protocol`: 通信协议/机制，如 `policy-enforcer`、`internal-event`
- `message_type`: 消息类型，如 `task_dispatch`、`incident_handoff`
- `status`: `sent|acked|failed|timeout`
- `latency_ms`: 通信耗时
- `correlation_id`: 链路追踪 ID（同一流程保持一致）
- `payload_ref`: 外部证据引用（文件路径/记录 ID）
- `details_json`: 扩展上下文（JSON 对象）
- `actor`: 操作身份

建议:
- 每次任务派发至少一条 `task_dispatch`。
- `failed/timeout` 必须附带可复现证据（`payload_ref` 或 `details_json`）。

## 3. Agent 回报 `report-agent-result`

用途:
- agent 完成阶段或任务后，向规划者回传标准化完成信息。

核心字段:
- `task_id`: 必填，必须存在于任务中心
- `agent_id`: 执行 agent
- `planner_id`: 规划者（默认 `coordinator`）
- `status`: `passed|failed|partial|escalated`
- `solved`: 是否解决问题
- `resolved_issues`: 已解决项（逗号分隔）
- `resolution_summary`: 解决摘要
- `resolution_steps`: 关键步骤（逗号分隔）
- `failed_items`: 未解决项/失败项（逗号分隔）
- `failure_count`: 失败次数
- `duration_ms`: 耗时
- `model`: 使用模型（可空）
- `input_tokens` / `output_tokens`: token 使用
- `cost_estimate`: 成本估算
- `quality_score`: 质量分（0-100）
- `quality_grade`: 质量等级（如 `a/b/c/d`）
- `notify_chat`: 是否向聊天通道发消息
- `details_json`: 扩展上下文（JSON 对象）
- `actor`: 回报身份

通知策略:
- 默认仅异常触发聊天消息：
- `status in (failed, escalated)` 或 `solved=false` 或 `failure_count>0` => `notify_chat=true`
- 正常完成 => `notify_chat=false`，只入库并回传规划者 payload

## 4. 规划者统计 `planner-summary`

用途:
- 按 `planner_id` 聚合 agent 回报，自动统计完成质量和成本。

输入字段:
- `planner_id`: 规划者 ID
- `since`: 开始时间（ISO8601，可空）
- `limit`: 最大回报条数

输出核心字段:
- `report_count`: 回报数
- `task_count`: 任务数
- `resolved_task_count`: 已解决任务数
- `failed_task_count`: 失败任务数
- `solved_ratio_pct`: 解决率
- `status_counts`: 各状态计数
- `total_tokens` / `total_cost_estimate`: token 与成本
- `avg_duration_ms` / `avg_quality_score`: 平均时长与质量
- `by_agent`: 按 agent 聚合统计

## 5. 命名与取值约束

- `task_id`: 全局唯一、不可复用、可追踪来源（推荐 `prefix-yyyymmddhhmmss-rand`）。
- `module_name`/`from_module`/`to_module`: 统一使用 `agent/module` 风格，避免别名。
- `status`/`level`: 严格使用枚举值，避免同义词污染统计。
- 时间统一 ISO8601；耗时统一 `ms`；token 统一整数。

## 6. 最小接入清单

每个 agent 脚本至少实现:
1. 启动时 `log-module(status=started)`
2. 与其他模块协作时 `log-communication`
3. 结束时 `report-agent-result`
4. 定时或收尾时拉取 `planner-summary` 供规划者看板

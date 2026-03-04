# Self-Evolution Phase 1 变更说明

日期：2026-03-04

## 1. 记忆系统（Experience）升级

### 1.1 新增字段
- `ExperienceCard.agentId`
- `ExperienceCard.memoryTier`：`reflex | long_term | recent | archive`
- `ExperienceCard.priorityScore`
- `stats.cards[cardId].memoryTier`
- `stats.cards[cardId].priorityScore`

### 1.2 新增维护产物
- `.workflow/experience/maintenance/priority-buckets.json`

该文件包含：
- 全局优先级桶 `global`
- 每个 agent 独立桶 `byAgent.<agentId>`
- 层级顺序 `tierOrder`

### 1.3 召回逻辑变化
- `hardflow-experience-recall` 优先读取 `priority-buckets.json` 进行候选召回。
- 仅当桶缺失或为空时，回退到 `cards.ndjson` 全量读取。
- 召回排序新增 tier/priority 偏置，优先 `reflex`、`long_term`。

### 1.4 维护脚本变化
- `scripts/hardflow/experience-maintain.mjs` 版本更新为 `experience-score-v2`。
- 新增 `memoryTier` 分类和 `priorityScore` 计算。
- 输出报告新增 `memoryTier` 统计与 `topPriority`。

## 2. 积分系统（任务奖励）升级

### 2.1 数据库新增表
- `agent_points_ledger`

记录维度：
- `actor_type`：`agent | planner`
- `actor_id`
- `points`
- `base_points`
- `quality_factor`
- `timeliness_factor`
- `status/solved/details_json`

### 2.2 新增 TaskCenter 能力
- `upsert_agent_points(...)`
- `list_agent_points(...)`
- `points_summary(...)`

### 2.3 计分接入点
- `policy_enforcer.py::report_agent_result`

在 agent 回报后自动入账：
- agent 积分（执行表现）
- planner 积分（分配质量分成）

## 3. 保底派单升级（低分 agent）

### 3.1 `next-todo` 新逻辑
- 在 FIFO 基础上引入“低分 agent 保底槽位”。
- 保底命中任务会携带：
  - `dispatch_reason=guarantee_low_score_agent`
  - `guarantee_hit=true`

### 3.2 返回结果新增
- `guarantee_policy.enabled`
- `guarantee_policy.min_tasks_per_agent`
- `guarantee_policy.low_score_threshold`
- `guarantee_policy.lookback_days`
- `guarantee_policy.points_since`
- `guarantee_policy.guarantee_hits`
- `guarantee_policy.low_score_agents`
- `scanned_ready_count`

## 4. 配置新增项

文件：`scripts/openclaw-ops/policy/policy-config.json`

新增：
- `agent_points_policy`
  - `enabled`
  - `leaderboard_lookback_days`
  - `quality_weight`
  - `timeliness_weight`
  - `planner_share`
  - `minimum_quality_for_positive`
  - `base_points_by_priority`
  - `risk_multiplier`
  - `timeliness_sla_ms_by_priority`
- `todo_queue_policy.agent_guarantee`
  - `enabled`
  - `min_tasks_per_agent`
  - `low_score_threshold`
  - `lookback_days`

## 5. 最小验证命令

```bash
python -m py_compile scripts/openclaw-ops/policy/task_center.py scripts/openclaw-ops/policy/policy_enforcer.py
node --check scripts/hardflow/experience-maintain.mjs
node --experimental-strip-types scripts/hardflow/hook-selftest.mjs --hooks-dir hooks --workspace .workflow/tmp-hook-selftest
```

## 6. 兼容性说明
- 老数据不需要迁移脚本，可直接运行。
- 若不希望启用积分/保底，可在配置中关闭：
  - `agent_points_policy.enabled=false`
  - `todo_queue_policy.agent_guarantee.enabled=false`

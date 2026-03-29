# 任务成本统计工作流

> 状态：🔧 部分实现 | 触发方式：任务完成自动触发 / 定时触发
> 上级目录：[专项场景工作流](../README.md)

## 功能概述

自动统计每个任务的耗时、Token 消耗、资源占用，输出成本分析报表。帮助优化模型选择策略和资源分配。

## 当前实现情况

### ✅ 已实现（基础设施层）

| 能力 | 实现位置 | 说明 |
|------|----------|------|
| Token 记录 | `policy_enforcer.py record-token` | 每次 Agent 执行后记录 input/output tokens |
| 成本计算 | `token-pricing.json` | 本地价格表（per_1m_tokens） |
| 任务耗时 | `task_center.py` | `duration_ms` 字段追踪 |
| Agent 回报 | `report-agent-result` | 含 cost_estimate / model / tokens |
| 日报统计 | `daily_work_report.py` | 按 Agent 统计 token/cost |
| 规划者摘要 | `planner-summary` | 任务完成情况 + Agent 质量 |

### ❌ 待实现

| 能力 | 说明 |
|------|------|
| 独立成本报表脚本 | 按时间段/Agent/模型维度生成成本趋势分析 |
| 成本预警 | 单任务成本超阈值自动告警 |
| 模型 ROI 分析 | 对比不同模型的性价比，输出切换建议 |
| 资源占用统计 | CPU/内存/磁盘使用量关联任务 |
| Cron Job 注册 | 独立定时任务生成成本报表 |

## 实施计划

### Phase 1（建议优先）
创建 `cost_report_generator.py`，从 `task_center.db` 读取 token_records 表，按以下维度汇总：
- 按日/周/月聚合
- 按 Agent 分组
- 按模型分组
- 输出 Markdown + JSON 双格式

### Phase 2
注册 Cron Job（每周一生成周报），与 daily_work_report 互补。

### Phase 3
增加成本预警阈值（`policy-config.json` 扩展），超过时自动告警。

## 现有价格表

位置：`scripts/openclaw-ops/policy/token-pricing.json`

```json
{
  "models": {
    "gpt-5.4": { "input_per_1m": 2.50, "output_per_1m": 10.00 },
    "gpt-5.4-mini": { "input_per_1m": 0.40, "output_per_1m": 1.60 },
    "Doubao-Seed-2.0-pro": { "input_per_1m": 0.30, "output_per_1m": 0.80 }
  }
}
```

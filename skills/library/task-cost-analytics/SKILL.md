---
name: task-cost-analytics
description: >
  任务成本统计技能。用于统计 Token 消耗、分析任务执行成本、
  生成成本报告。当需要了解 LLM 调用成本或优化 Token 使用时使用。
allowed-tools: Bash, Read, Grep
---

# 任务成本统计操作手册

## 适用场景

- 统计指定时间范围内的 Token 消耗
- 分析各 Agent 的成本占比
- 识别高成本任务和优化机会
- 生成成本报告

## 操作流程

### 1. 查看成本概览

```bash
# 查看今日成本
python3 ~/scripts/openclaw-ops/cost_analytics.py --today

# 查看本周成本
python3 ~/scripts/openclaw-ops/cost_analytics.py --week
```

### 2. Agent 成本分析

```bash
python3 ~/scripts/openclaw-ops/cost_analytics.py --by-agent
```

### 3. 任务类型分析

```bash
python3 ~/scripts/openclaw-ops/cost_analytics.py --by-task-type
```

## 成本维度

| 维度 | 指标 | 说明 |
|------|------|------|
| Token 总量 | input_tokens + output_tokens | 请求+响应 |
| 按 Agent | 各 Agent 的 Token 消耗占比 | 识别高消耗 Agent |
| 按任务类型 | coding/review/ops/evolution | 识别高消耗场景 |
| 按模型 | gpt-5.4 vs glm-4.7 等 | 模型成本对比 |

## 约束

- 数据来源：任务执行日志和 Gateway 统计
- 报告格式：Markdown 或 JSON
- 不直接修改模型配置，只提供分析建议

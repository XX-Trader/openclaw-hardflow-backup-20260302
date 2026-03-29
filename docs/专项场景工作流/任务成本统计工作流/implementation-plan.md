# 任务成本统计工作流 — 实施计划

> 版本：v1.0 | 2026-03-29
> 状态：🔧 部分实现

## 现状评估

**已有基础设施**（可直接复用）：
- `task_center.db.token_records` 表 — 每次 Agent 执行自动记录 input/output tokens
- `token-pricing.json` — 模型价格表（支持按 per_1m_tokens 计算成本）
- `report-agent-result --cost-estimate` — 单任务成本估算
- `daily_work_report.py` — 日报中含按 Agent 汇总的 token/cost

**缺失能力**：独立的成本分析报表脚本、成本预警、模型 ROI 分析

## 实施步骤

### Phase 1：成本报表脚本（预计 4h）

创建 `scripts/openclaw-ops/cost_report_generator.py`

**核心功能**：
1. 从 `task_center.db.token_records` 读取数据
2. 按 日/周/月 时间维度聚合
3. 按 Agent 分组统计
4. 按 Model 分组统计
5. 输出 Markdown + JSON 双格式
6. CLI 参数：`--db`, `--since`, `--until`, `--group-by`, `--output-dir`

**输出示例**：
```
| 模型           | 输入 Tokens | 输出 Tokens | 总成本($) | 任务数 |
|----------------|------------|------------|----------|--------|
| gpt-5.4        | 890,000    | 320,000    | 54.20    | 42     |
| Doubao-Seed-2  | 1,200,000  | 560,000    | 8.08     | 128    |
```

### Phase 2：Cron Job 注册（预计 0.5h）

注册每周一生成成本周报，与 `daily_work_report` 互补。

```json
{
  "name": "cost_report_weekly",
  "agentId": "ops-agent",
  "schedule": { "kind": "cron", "cron": "0 6 * * 1" }
}
```

### Phase 3：成本预警（预计 2h）

在 `policy-config.json` 扩展阈值配置：
```json
{
  "cost_alert": {
    "single_task_max_usd": 5.00,
    "daily_max_usd": 50.00,
    "notify_channel": "telegram"
  }
}
```

### Phase 4：模型 ROI 分析（预计 3h）

对比同类任务使用不同模型的性价比：
- 输入：同 task_type 的不同模型执行记录
- 输出：每个模型的"质量/成本比"排名 + 建议切换

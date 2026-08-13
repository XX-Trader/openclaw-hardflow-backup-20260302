---
name: task-cost-analytics
description: 任务运行与输出统计技能，用于聚合 Task Center 状态、失败原因、执行指标和增量广播。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}}}
---

# 任务运行与输出统计

## Owner

- `scripts/daily_work_report.py`
- `scripts/task_output_consumer.py`
- `scripts/task_output_broadcast_runner.py`

## 流程

1. 从 Task Center 和结构化运行产物读取数据。
2. 按时间窗、任务状态和可见性聚合。
3. 对相同输出使用稳定去重键。
4. 仅发送新增或变化的可见结果。

先对 `--help` 和临时任务库执行 smoke，再接入 Runtime 调度。输出隐藏凭证、内部绝对路径和原始会话内容。

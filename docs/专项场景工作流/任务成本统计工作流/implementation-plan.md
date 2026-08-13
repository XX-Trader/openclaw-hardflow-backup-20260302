# 任务成本与输出统计实施说明

当前 owner 位于 `skills/library/task-cost-analytics/scripts/`：

- `daily_work_report.py`：聚合任务状态、执行结果和异常。
- `task_output_consumer.py`：消费结构化任务输出。
- `task_output_broadcast_runner.py`：只广播可见且发生变化的结果。

统计输入必须来自 Task Center 或结构化运行产物；输出不得包含凭证、内部绝对路径或原始会话转录。验收覆盖空窗口、重复输入、失败任务和增量广播。

---
name: hardflow-failure-detector
description: Detect consecutive tool failures and inject PUA pressure escalation into agent messages.
metadata: { "openclaw": { "emoji": "🔥", "events": ["tool:result"] } }
---

# HardFlow Failure Detector

基于 PUA v3 failure-detector 适配的 OpenClaw Hook。

1. 监听 Agent 工具执行结果（`tool:result` 事件）。
2. 检测 error/exception/非零退出码等失败信号。
3. 维护 `consecutive_failure_count`（per-session）。
4. 根据失败次数注入分级压力提示到 `messages[]`：
   - L1 (2次): 停下，切换本质不同的方案
   - L2 (3次): 搜索+读源码+列3个假设
   - L3 (4次): 完成7项检查清单
   - L4 (5次+): 结构化失败报告或最小PoC
5. 成功执行后重置失败计数器。

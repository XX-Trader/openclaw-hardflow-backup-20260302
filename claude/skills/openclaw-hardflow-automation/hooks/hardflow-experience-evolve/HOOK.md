---
name: hardflow-experience-evolve
description: 在任务收口后根据结果反馈更新经验成功率，实现经验自动进化。
metadata:
  { "openclaw": { "emoji": "📈", "events": ["command:stop"] } }
---

# HardFlow Experience Evolve

## 功能

1. 在 `command:stop` 读取本会话已召回经验。
2. 按 gate 结果（或会话信号）判定成功/失败。
3. 更新经验统计（复用次数、成功率、最近结果）。

## 说明

该 Hook 只更新统计，不改写历史经验卡片正文。


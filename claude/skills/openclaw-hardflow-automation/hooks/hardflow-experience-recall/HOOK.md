---
name: hardflow-experience-recall
description: 在 Agent 启动时召回高相关经验，并注入到引导上下文中以提升复用率。
metadata:
  { "openclaw": { "emoji": "📚", "events": ["agent:bootstrap"] } }
---

# HardFlow Experience Recall

## 功能

1. 在 `agent:bootstrap` 时读取经验卡片和统计。
2. 根据当前 `todo.md/done.md` 计算相关性，召回 Top-K。
3. 生成 `EXPERIENCE_RECALL.md` 并注入到 bootstrap 上下文。

## 说明

该 Hook 不覆盖现有系统文件，只追加经验召回文档。


---
name: hardflow-experience-capture
description: 在会话结束或切换前自动沉淀经验卡片，形成可复用的问题解决资产。
metadata:
  { "openclaw": { "emoji": "🧠", "events": ["command:stop", "command:new", "command:reset"] } }
---

# HardFlow Experience Capture

## 功能

1. 在 `command:stop/new/reset` 时读取会话消息。
2. 自动提取问题、根因、步骤、验证与回滚信息。
3. 写入 `.workflow/experience/cards.ndjson` 与对应 Markdown 卡片文件。

## 说明

该 Hook 仅记录经验，不阻断命令流程。


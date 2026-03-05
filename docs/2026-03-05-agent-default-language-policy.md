# Agent 默认输出语言策略（2026-03-05）

## 目标
- 统一所有 OpenClaw agent 的默认输出语言为中文（简体，`zh-CN`）。

## 持久化位置
- 全局配置：`openclaw/openclaw.json`
  - `agents.defaults.outputPolicy.defaultLanguage = zh-CN`
  - `agents.defaults.outputPolicy.requireChineseByDefault = true`
  - `agents.defaults.outputPolicy.allowOverrideByUser = true`
- agent 角色约束：`agents/*/SOUL.md`
  - 每个 agent 明确写入“默认输出中文，除非用户明确要求其他语言”。

## 规则说明
- 默认行为：所有 agent 输出中文（简体）。
- 用户覆盖：当用户明确要求英文或其他语言时，可按用户要求切换。

## 验证建议
- 对任意 agent 发起一条普通问答，确认默认回复为中文。
- 再发起“请用英文回复”请求，确认可按需切换。


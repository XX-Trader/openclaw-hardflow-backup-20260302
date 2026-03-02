---
name: "codeagent"
description: "codeagent 技能"
version: "1.0.0"
triggers:
  keywords:
    - "codeagent"
    - "代码代理"
    - "AI代码"
    - "多backend"
    - "Codex"
    - "Claude"
    - "Gemini"
  auto_trigger: true
  confidence_threshold: 0.7
---

name: codeagent
description: Execute codeagent-wrapper for multi-backend AI code tasks. Supports Codex, Claude, and Gemini backends with file references (@syntax) and structured output.
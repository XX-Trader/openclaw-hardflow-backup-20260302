---
name: "requirements-clarity"
description: "requirements-clarity skill"
triggers:
  keywords:
    - "需求澄清"
    - "需求不清晰"
    - "模糊需求"
    - "需求确认"
    - "clarify requirements"
  auto_trigger: true
  confidence_threshold: 0.7

---
name: Requirements Clarity
description: Clarify ambiguous requirements through focused dialogue before implementation. Use when requirements are unclear, features are complex (>2 days), or involve cross-team coordination. Ask two core questions - Why? (YAGNI check) and Simpler? (KISS check) - to ensure clarity before coding.
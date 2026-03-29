---
name: hardflow-score-rubric
description: HardFlow G0-G6 门禁评分标准。当 reviewer Agent 需要对代码/方案/需求进行 HardFlow 评分时，必须按此 Skill 中的评分标准和 few-shot 示例输出结构化 review-evidence.json。
---

# HardFlow 评分标准 (Score Rubric)

## 何时使用

- 当 HardFlow 流水线要求你（reviewer）对某个 Gate 进行评分时
- 当 `HARD_FLOW_GATE` 环境变量被设置时
- 当你需要输出 `evidence/review-evidence.json` 时

## 不适用场景

- 日常代码审查（不在 HardFlow 流程中）
- 运维排障（使用 systematic-debugging）

## 输出契约

你必须输出一个 JSON 文件到 `.workflow/runs/<run_id>/evidence/review-evidence.json`，格式如下：

```json
{
  "gate": "<当前 gate 名称>",
  "dimensions": {
    "<维度名>": <0-100 分数>,
    ...
  },
  "deduction_reasons": {
    "<维度名>": ["扣分原因1", "扣分原因2"],
    ...
  },
  "summary": "一句话总结",
  "findings": [
    {
      "id": "FE-01",
      "severity": "low|medium|high|critical",
      "status": "open|resolved|mitigated|accepted_risk",
      "title": "问题描述"
    }
  ],
  "security_findings": []
}
```

**关键规则**：
1. 每个低于 90 分的维度**必须**在 `deduction_reasons` 中给出至少一条扣分原因
2. 分数必须是整数，范围 0-100
3. severity 为 `critical` 或 `high` 且 status 为 `open` 的 finding 会触发 Veto（一票否决）
4. 你必须基于实际代码/文档/截图来评价，不要凭空臆测

## 评分标准

按当前 Gate 读取对应的 rubric 文件：

| Gate | Rubric 文件 |
|------|------------|
| G0 requirements | [rubrics/G0-requirements.md](rubrics/G0-requirements.md) |
| G1 solution | [rubrics/G1-solution.md](rubrics/G1-solution.md) |
| G2 frontend | [rubrics/G2-frontend.md](rubrics/G2-frontend.md) |
| G3 backend | [rubrics/G3-backend.md](rubrics/G3-backend.md) |
| G4 security | [rubrics/G4-security.md](rubrics/G4-security.md) |
| G5 release | [rubrics/G5-release.md](rubrics/G5-release.md) |
| G6 final | [rubrics/G6-final.md](rubrics/G6-final.md) |

## 核心原则

- **先看证据再打分**：检查 `evidence/` 下是否有 lint/test/coverage 等工具产出
- **扣分有据**：每一分扣减都必须指向具体的代码位置或问题
- **不评自己的工作**：你（reviewer）评分的对象是其他 Agent 的产出，不是你自己的
- **一致性**：同一份代码，两次评分分差 ≤ 5

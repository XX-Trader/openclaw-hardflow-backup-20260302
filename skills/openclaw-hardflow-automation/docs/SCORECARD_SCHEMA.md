# HardFlow Scorecard Schema (G0-G6)

Every score gate consumes one JSON scorecard file.

Default location per gate:
`.workflow/runs/<run_id>/scorecards/<gate>.json`

## 1) Required top-level fields

1. `gate` (string): one of `requirements|solution|frontend|backend|security|release|final`
2. `overall` (number): overall score, range `0-100`
3. `dimensions` (object): dimension score map, each value range `0-100`
4. `reviewer` (string): reviewer agent name or id
5. `summary` (string): short conclusion
6. `evidence` (array[string]): evidence list (command output, file path, screenshots, logs)

## 2) Optional fields

1. `findings` (array[object]): generic findings list
2. `security_findings` (array[object]): security findings list
3. `criticalRisks` (array[object]): security finding alias
4. `deduction_reasons` (object): dimension-level deduction reasons, each value is array[string]
5. `evidence_sources` (object): deterministic check results + LLM evaluator metadata
6. `planVersion` (string)
7. `notes` (string)

For security veto, each finding object should include:

1. `id` (string)
2. `severity` (string): usually `low|medium|high|critical`
3. `status` (string): `open|in_progress|resolved|mitigated|accepted_risk`
4. `title` (string, optional)

## 3) Example (frontend gate)

```json
{
  "gate": "frontend",
  "overall": 93,
  "reviewer": "reviewer-agent",
  "summary": "Layout and interaction quality are ready for release.",
  "dimensions": {
    "visual_design": 92,
    "information_architecture": 94,
    "interaction_quality": 91,
    "responsive_accessibility": 92,
    "code_structure": 93
  },
  "evidence": [
    "Project/ShengBeiVue/src/views/dashboard/index.vue",
    ".workflow/runs/20260301_101010/attempt-1/test.log",
    "playwright screenshot: artifacts/frontend-review.png"
  ],
  "findings": [
    {
      "id": "FE-11",
      "severity": "low",
      "status": "resolved",
      "title": "Button alignment was inconsistent on small screens"
    }
  ]
}
```

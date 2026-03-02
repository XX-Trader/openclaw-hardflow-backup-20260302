---
name: hardflow-lobster
description: 基于 Lobster 的 HardFlow 完整版编排技能，支持 G0-G6 独立评分门禁与自动部署/自动推送。
license: MIT
---

# HardFlow Lobster Skill

## 1. 适用场景

1. 需要单次调用跑完整流水线。
2. 需要自动执行部署与 `git push`（不再停在审批节点）。
3. 需要在结果中输出可追溯的评分与扣分明细。

## 2. 核心步骤（自动部署/自动推送）

1. `classify`
2. `score_g0_requirements`
3. `dispatch`
4. `score_g1_solution`
5. `implement`
6. `test_loop`
7. `review`
8. `score_g2_frontend`
9. `score_g3_backend`
10. `score_g4_security`
11. `api_doc_gate`
12. `quality_gate_predeploy`
13. `preview_deploy`
14. `deploy`
15. `post_test`
16. `score_g5_release`
17. `score_g6_final`
18. `quality_gate_postdeploy`
19. `preview_git_push`
20. `git_push`
21. `score_report`

## 3. 推荐参数

```json
{
  "action": "run",
  "pipeline": "/absolute/path/to/scripts/hardflow/hardflow-v1.lobster.yaml",
  "argsJson": "{\"task\":\"实现XX需求\",\"max_retries\":\"3\",\"score_max_retries\":\"3\"}",
  "timeoutMs": 180000
}
```

## 4. 质量门槛

1. 所有 score gates 必须 `passed=true`。
2. 安全 Gate 触发 veto 时必须回流修复。
3. `check-review-test-gate.sh` 会统一拦截未通过 gate。

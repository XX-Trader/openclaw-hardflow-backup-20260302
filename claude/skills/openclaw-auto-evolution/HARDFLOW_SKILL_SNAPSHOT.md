---
name: hardflow
description: 多角色 HardFlow 完整版技能（G0-G6 独立高分门禁 + 回流整改 + 审计追踪）。
license: MIT
---

# HardFlow Skill

## 1. 适用场景

1. 需要前端/后端/测试/审核/部署/文档协同自动化。
2. 需要“低分即回流整改”的质量闭环。
3. 需要“安全一票否决 + 接口文档门禁”。
4. 需要可审计、可复盘、可批量部署的标准流程。

## 2. Gate 规则（完整版）

1. `G0 requirements >= 93`
2. `G1 solution >= 92`
3. `G2 frontend >= 92`
4. `G3 backend >= 93`
5. `G4 security >= 95`，且高危未闭环 veto
6. `G5 release >= 92`
7. `G6 final >= 93`

每个 Gate 必须独立通过，不允许总分抵扣。

## 3. 关键目录

```text
scripts/hardflow/
├── hardflow-run.sh
├── check-score-gate.mjs
├── score-policy.json
├── SCORECARD_SCHEMA.md
├── check-api-doc-gate.sh
├── check-review-test-gate.sh
├── hardflow-v1.lobster.yaml
└── hardflow-tmux-runner.sh

.claude/hardflow/hooks/
├── hardflow-command-guard/
├── hardflow-audit/
└── hardflow-stop-gate-reminder/
```

## 4. 使用原则

1. 需求先落 `todo.md`。
2. 完成后落 `done.md`（含评分证据）。
3. 接口增删改必须同步 API 文档。
4. 评分命令必须输出 scorecard JSON。
5. Gate 失败必须执行改进命令并重评分。

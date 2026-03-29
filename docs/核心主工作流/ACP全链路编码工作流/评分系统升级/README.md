# ACP 评分系统升级

> 状态：📋 需求已定义 | 父级：[ACP全链路编码工作流](../README.md)
> 创建时间：2026-03-29 | 研究参考：[Harness Engineering 实战难点与借鉴](../../研究参考/harness-engineering-实战难点与借鉴.md)

## 一、需求背景

HardFlow 的门禁检查管道（`check-score-gate.mjs` + `score-policy.json`）架构完善，但评分数据源（`score-gate.sh`）为硬编码常量（全部 92-95 分），导致整条管道被架空。同时 `improve-gate.sh` 为空壳，评分不通过后无真正的修复逻辑。

**核心问题**：G0-G6 的 38 个维度阈值检查从未被真正触发，Veto 机制从未拦截过 finding，`evolution-upgrader` 的 baseline/candidate 对比系统无真实数据可消费。

## 二、设计原则

**产出证据的人 ≠ 评价的人 ≠ 做事的人**

评分采用三步流水线模式：
1. **证据收集**：执行 Agent（tester/frontend-dev/backend-dev）产出结构化证据
2. **独立评价**：另一个 Agent（reviewer）基于证据给出各维度评价
3. **确定性聚合**：纯计算脚本（无 LLM）读取证据和评价 → 按权重产出 scorecard.json

## 三、子功能清单与验收状态

| # | 子功能 | 优先级 | 验收标准 | 状态 |
|---|-------|--------|---------|------|
| 1 | 新建 `score-aggregator.sh` 替换硬编码 | 🔴 P0 | scorecard 各维度分数为真实值，非固定常量 | [ ] |
| 2 | test-loop 阶段产出结构化证据 | 🔴 P0 | `evidence/test-results.json` 等文件存在 | [ ] |
| 3 | review 阶段产出结构化证据 | 🔴 P0 | `evidence/review-evidence.json` 存在 | [ ] |
| 4 | scorecard 含 findings + deduction_reasons | 🔴 P0 | G4 veto 在有安全问题时被触发 | [ ] |
| 5 | 确认 `score-gate-audit.ndjson` 正常产出 | 🔴 P0 | 审计日志文件存在且非空 | [ ] |
| 6 | 新建 `hardflow-score-rubric` Skill | 🟡 P1 | 包含 G0-G6 各维度的判分标准 + few-shot 示例 | [ ] |
| 7 | Skill 绑定到 reviewer Agent | 🟡 P1 | `skills/by_agent/reviewer.md` 包含该 skill | [ ] |
| 8 | 替换 `improve-gate.sh` 为真实改进引擎 | 🟡 P2 | 评分→不通过→improve→再评分→分数上升 | [ ] |
| 9 | 接通 HardFlow 评分 → evolution-upgrader | 🟢 P3 | `workflow_upgrade_scoring.py` 能消费评分数据 | [ ] |

## 四、约束与边界

- **不新增 Agent**：评分职责通过角色分离实现，不新建"evaluator"角色
- **不改下游**：`check-score-gate.mjs`、`score-policy.json`、`check-review-test-gate.sh` 不变
- **聚合器无 LLM**：`score-aggregator.sh` 是纯确定性计算
- **评分可复现**：同一份证据两次聚合的分数完全一致

## 五、关联文档

| 文档 | 类型 | 路径 |
|------|------|------|
| 架构设计 v2 | 架构 | [architecture.md](architecture.md) |
| 实施计划 v2 | 实施 | [implementation-plan.md](implementation-plan.md) |
| 研究报告 | 参考 | [Harness Engineering 研究](../../研究参考/harness-engineering-实战难点与借鉴.md) |
| 评分卡 Schema | 规范 | [`scripts/hardflow/SCORECARD_SCHEMA.md`](../../../../scripts/hardflow/SCORECARD_SCHEMA.md) |

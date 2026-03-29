# ACP 评分系统升级 — 实施计划

> 版本：v2.0 | 2026-03-29（v2: 对齐"证据→评价→聚合"三步流水线）
> 需求文档：[README.md](README.md) | 架构文档：[architecture.md](architecture.md)

---

## 阶段一：P0 — 评分管道修复（解封 38 维度检查）

### Step 1.1 — 新建评分聚合脚本 `score-aggregator.sh`

- **新建** `scripts/hardflow/score-aggregator.sh`
- **角色**：三步流水线的 Step 3（纯确定性聚合，不调 LLM）
- **输入**：`.workflow/runs/<run_id>/evidence/` 目录下的证据文件
- **逻辑**：
  1. 读取 `score-policy.json` 获取该 gate 的维度列表
  2. 对确定性维度：从 `lint-report.json`/`test-results.json`/`coverage-report.json` 等证据文件中提取数值 → 按公式计算分数
  3. 对 LLM 维度：从 `review-evidence.json` 中读取 reviewer 已给出的评价和分数
  4. 加权聚合 → 输出 `scorecard.json`（含 `deduction_reasons` + `evidence_sources`）
- **不做的事**：不调用任何 Agent，不执行任何 LLM 请求

### Step 1.2 — 扩展 test-loop 阶段的证据输出

- **修改** `hardflow-run.sh` 的 `cmd_test_loop()` 函数
- 在测试执行完成后，新增证据文件输出：
  - 将测试结果汇总为 `evidence/test-results.json`
  - 将覆盖率报告（如有）复制为 `evidence/coverage-report.json`
  - 将 lint 结果输出为 `evidence/lint-report.json`
- **关键**：仅在 `$RUN_DIR/evidence/` 下新增文件，不改变现有 test-loop 的执行逻辑

### Step 1.3 — 扩展 review 阶段的证据输出

- **修改** `hardflow-run.sh` 的 review 阶段
- reviewer 的审查结果除了写入 `gates/reviewer.json`，还额外输出 `evidence/review-evidence.json`
- Schema：各维度评价 + 扣分原因 + reviewer 对各维度的建议分数

### Step 1.4 — 替换 hardflow.env 中的 SCORE_*_CMD

- **修改** `scripts/hardflow/hardflow.env.example`
- 所有 `SCORE_*_CMD` 从 `score-gate.sh` 改为 `score-aggregator.sh`
- 保留 `score-gate.sh` 不删除（作为后备），但不再作为默认

### Step 1.5 — 验证管道端到端

- 验证点：
  1. `evidence/` 目录下有 test 和 review 的证据文件
  2. `scorecard.json` 各维度分数非固定 92-95
  3. `score-gate-audit.ndjson` 存在且非空
  4. G4 security 的 veto 在有安全问题时被触发

---

## 阶段二：P1 — 评分标准 Skill 建设

### Step 2.1 — 新建 hardflow-score-rubric Skill

- **新建** `skills/library/hardflow-score-rubric/`
- 目录结构：
  ```
  skills/library/hardflow-score-rubric/
  ├── SKILL.md              # 主入口
  ├── rubrics/
  │   ├── G0-requirements.md
  │   ├── G1-solution.md
  │   ├── G2-frontend.md
  │   ├── G3-backend.md
  │   ├── G4-security.md
  │   ├── G5-release.md
  │   └── G6-final.md
  └── examples/
      ├── high-score.jsonc
      └── low-score.jsonc
  ```
- 每个 rubric 含：满分/良好/需改进/不合格条件 + 扣分规则 + few-shot 示例

### Step 2.2 — 绑定到 reviewer Agent

- **修改** `skills/by_agent/reviewer.md` 追加 skill 绑定

### Step 2.3 — 替换 improve-gate.sh

- **新建** `scripts/hardflow/improve-evaluator.sh`
- 读取 scorecard 的 `deduction_reasons` → 分类修复

---

## 阶段三：P2-P4（后续）

- P2: 推广与治理
- P3: 接通 evolution-upgrader 闭环
- P4: Agent schema 级权限

---

## 验证计划

### 自动化验证

```bash
# 1. 验证 score-aggregator 能正确读取证据并输出 scorecard
mkdir -p /tmp/test-evidence
echo '{"total":10,"passed":8,"failed":2}' > /tmp/test-evidence/test-results.json
echo '{"pass":true,"warnings":3}' > /tmp/test-evidence/lint-report.json
bash scripts/hardflow/score-aggregator.sh \
  --gate frontend \
  --evidence-dir /tmp/test-evidence \
  --scorecard /tmp/test-scorecard.json
# 预期：/tmp/test-scorecard.json 的 dimensions 中各值均非 92-95

# 2. 验证 check-score-gate.mjs 仍能正常校验新 scorecard
node scripts/hardflow/check-score-gate.mjs \
  --policy scripts/hardflow/score-policy.json \
  --gate frontend \
  --scorecard /tmp/test-scorecard.json \
  --output /tmp/test-gate.json \
  --audit-log /tmp/test-audit.ndjson
# 预期：gate 结果 JSON 产出，audit.ndjson 非空
```

### 手动验证

1. **完整管道端到端**：提一个前端需求 → 跑 HardFlow → 观察 G2 是否基于真实评分通过/拒绝
2. **评分一致性**：同一份代码评两次，分差 ≤ 5
3. **Veto 触发**：故意硬编码密钥 → G4 security 应拒绝

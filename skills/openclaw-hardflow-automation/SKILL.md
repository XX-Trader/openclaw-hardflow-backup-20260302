---
name: hardflow
description: >
  HardFlow 多门禁质量工作流。用于前端/后端功能开发的多阶段质量门禁（G0-G6），
  包含需求分析、方案设计、编码实现、安全审查、发布验收。
  当需要执行编码任务并确保质量时使用此技能。
  支持低分回流整改、安全一票否决、评分三步流水线。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# HardFlow 多门禁工作流 — 操作手册

## 1. 任务分类决策树

收到编码任务后，首先判断任务类型，决定走哪些 Gate：

| 任务类型 | 判断条件 | 必经 Gate | 可选 Gate |
|---------|---------|----------|----------|
| 纯前端 UI | 只改 Vue/React/CSS/HTML | G0 → G2 → G4 → G6 | G5(部署) |
| 纯后端 API | 只改 Python/Go/DB | G0 → G1 → G3 → G4 → G6 | G5 |
| 前后端联动 | 同时改前后端 | G0 → G1 → G2 → G3 → G4 → G6 | G5 |
| Bug 修复 | 修复已知 Bug | G0 → G2或G3 → G4 | — |
| 文档更新 | 只改 docs/README | G0 → G2 | — |
| 迭代优化 | 在已有功能上优化 | G0 → G3.5 → G4 | — |

## 2. 各 Gate 详细操作步骤

### G0 — 需求分析（Requirements Quality）

**目标**：确保理解正确，范围清晰，验收标准明确。

**操作**：
1. 阅读任务描述，提炼目标和约束
2. 检查是否有 `docs/<模块>/README.md` 需求文档
3. 明确验收标准（什么算"做完了"）
4. 识别风险和边缘情况
5. 输出需求分析文档或确认理解

**评分维度**（阈值 93 分）：
- goal_clarity（93）：目标是否清晰无歧义
- scope_boundary（92）：范围是否有明确边界
- acceptance_criteria（93）：验收标准是否可验证
- constraints_coverage（92）：约束条件是否完整
- risk_analysis（92）：风险是否已识别

**约束**：此阶段只读，不要修改任何代码文件。

### G1 — 方案设计（Solution Fitness）

**目标**：产出可执行的技术方案。

**操作**：
1. 基于 G0 需求，设计技术方案
2. 评估可行性和替代方案
3. 确定数据结构和接口设计
4. 输出 `docs/<模块>/architecture.md` 或实施计划

**评分维度**（阈值 92 分）：
- fit_for_problem（92）：方案是否匹配问题
- feasibility（92）：技术可行性
- complexity_control（91）：复杂度是否可控
- alternatives_evaluation（90）：是否评估了替代方案
- risk_mitigation（91）：风险缓解措施

**约束**：此阶段只能写 docs/ 目录下的文档，不要写代码。

### G2 — 前端实现（Frontend Quality）

**目标**：完成前端代码实现。

**操作**：
1. 按方案创建/修改 Vue/React 组件
2. 实现样式和交互逻辑
3. 确保响应式和可访问性
4. 自测基本功能

**评分维度**（阈值 92 分）：
- visual_design（90）：视觉效果
- information_architecture（91）：信息架构
- interaction_quality（90）：交互质量
- responsive_accessibility（90）：响应式和可访问性
- code_structure（91）：代码结构

### G3 — 后端实现（Backend Quality）

**目标**：完成后端代码实现。

**操作**：
1. 按方案实现 API 接口
2. 编写数据模型和迁移
3. 实现业务逻辑
4. 确保错误处理和参数校验

**评分维度**（阈值 93 分）：
- architecture_design（92）：架构设计
- api_contract_quality（92）：API 契约质量
- data_flow_integrity（92）：数据流完整性
- maintainability（92）：可维护性
- scalability（91）：可扩展性

### G3.5 — 迭代优化（Iterative Refinement Quality）

**目标**：对已有功能进行迭代改进。

**评分维度**（阈值 90 分）：
- error_analysis_accuracy（90）：问题分析准确性
- fix_effectiveness（92）：修复有效性
- regression_coverage（91）：回归测试覆盖
- root_cause_depth（90）：根因分析深度
- methodology_rigor（89）：方法论严谨性

### G4 — 安全审查（Security Gate）

**目标**：发现并消除安全风险。阈值最高（95 分），支持一票否决。

**操作**：
1. 检查所有输入是否校验和转义
2. SQL 是否参数化（禁止拼接）
3. 密钥/Token 是否硬编码
4. 认证授权是否完整
5. 依赖包是否有已知漏洞
6. 如果有浏览器，打开页面检查 XSS 风险

**评分维度**（阈值 95 分）：
- authn_authz（95）：认证授权
- input_validation（95）：输入校验
- secrets_protection（95）：密钥保护
- dependency_security（93）：依赖安全
- auditability（93）：可审计性
- privileged_access_control（94）：特权访问控制

**一票否决（Veto）机制**：
- 如果存在 severity=critical 或 severity=high 的安全发现
- 且 status 不是 resolved/mitigated/accepted_risk
- 则**无论总分多高，直接判定 Gate 失败**

**约束**：此阶段只读代码 + 浏览器截图检查，不要修改源代码。

### G5 — 发布验证（Release Readiness）

**目标**：确认可以安全发布。

**评分维度**（阈值 92 分）：
- test_coverage（92）：测试覆盖率
- regression_result（92）：回归测试结果
- deployment_reliability（92）：部署可靠性
- rollback_readiness（92）：回滚准备
- observability（90）：可观测性

### G6 — 最终验收（Final Acceptance）

**目标**：全流程最终确认。

**操作**：
1. 代码整体审查
2. 如果有部署，做冒烟测试
3. 确认文档更新完整
4. 确认所有交付物一致

**评分维度**（阈值 93 分）：
- code_review_quality（93）：代码审查质量
- production_smoke（93）：生产冒烟测试
- metric_stability（92）：指标稳定性
- documentation_completeness（92）：文档完整性
- deliverable_consistency（92）：交付物一致性

## 3. 评分三步流水线

**这是不可简化的核心机制。每个 Gate 的评分必须严格走完三步。**

### 步骤 1：证据收集（由执行 Agent 完成）

执行 Agent（tester/coder）完成工作后，将结构化证据输出为 JSON：

```bash
# 证据文件位置
.workflow/runs/<run_id>/scorecards/<gate>.json
```

证据 JSON 格式（必填字段）：
```json
{
  "gate": "frontend",
  "overall": 93,
  "reviewer": "reviewer-agent",
  "summary": "一句话结论",
  "dimensions": {
    "visual_design": 92,
    "information_architecture": 94,
    "interaction_quality": 91,
    "responsive_accessibility": 92,
    "code_structure": 93
  },
  "evidence": [
    "src/views/dashboard/index.vue",
    ".workflow/runs/current/test.log",
    "playwright screenshot: artifacts/review.png"
  ],
  "findings": [],
  "security_findings": []
}
```

### 步骤 2：独立评价（由 reviewer Agent 完成）

reviewer Agent 基于 evidence 目录进行独立审查：
- 阅读代码变更
- 如果有 UI 变更，用浏览器打开页面截图审查
- 按各维度独立打分
- 输出 scorecard JSON 到证据目录

**reviewer 不能修改源代码**，只读 + 浏览器审查。

### 步骤 3：确定性聚合（由脚本完成，无 LLM）

使用 `check-score-gate.mjs` 脚本做纯计算聚合：

```bash
node scripts/check-score-gate.mjs \
  --gate frontend \
  --scorecard .workflow/runs/<run_id>/scorecards/frontend.json \
  --policy scripts/hardflow/score-policy.json \
  --output .workflow/runs/<run_id>/gate-results/frontend.json \
  --run-id <run_id> \
  --audit-log .workflow/audit/gate-audit.ndjson
```

此脚本做的事情（纯计算，无 LLM）：
1. 读取 scorecard JSON 和 score-policy.json
2. 校验 overall 分数是否 >= 阈值
3. 校验每个维度分数是否 >= 维度阈值
4. 校验证据数量是否 >= 最低要求
5. 检查安全 Veto（高危未关闭的发现）
6. 写入判定结果 + 追加审计日志

退出码：0=通过，1=失败，2=参数错误

## 4. 回流整改机制

当 Gate 评分不通过时：

1. 分析 gate-results JSON 中的 `reason` 字段，找到失败原因
2. 针对性修改代码/文档
3. 重新提交证据（regenerate scorecard JSON）
4. 重新执行 `check-score-gate.mjs`
5. 最大重试次数：3 次（score-policy.json 中 `global.defaultMaxRetries`）
6. 3 次仍不通过，需要回退到上一个 Gate 重新设计

## 5. 关键文件说明

| 文件 | 位置 | 用途 |
|------|------|------|
| score-policy.json | scripts/hardflow/ | 各 Gate 阈值 + 维度阈值 + Veto 策略 |
| check-score-gate.mjs | scripts/hardflow/ | 确定性评分校验引擎（310行 Node.js） |
| score-report.mjs | scripts/hardflow/ | 评分报告格式化输出 |
| SCORECARD_SCHEMA.md | scripts/hardflow/ | 证据 JSON 字段规范 |
| check-api-doc-gate.sh | scripts/hardflow/ | API 文档门禁检查 |

## 6. 约束与红线

1. **评分聚合禁止使用 LLM**：`check-score-gate.mjs` 是纯计算脚本，确保评分可复现
2. **每个 Gate 必须独立通过**：不允许总分抵扣子项
3. **安全 Gate（G4）一票否决**：高危未关闭的发现直接判定失败
4. **reviewer 不能改代码**：审查阶段只读
5. **G0 阶段只读**：需求分析不要修改代码文件
6. **G1 阶段只写文档**：方案设计只能写 docs/ 目录
7. **todo.md 同步**：开始前在 todo.md 标记任务，完成后移到 done.md
8. **接口变更同步 API 文档**：增删改 API 必须更新文档

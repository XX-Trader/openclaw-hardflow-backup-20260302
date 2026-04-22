# 对抗审查与 HardFlow G0-G6 门禁映射契约

> 版本：v1.0 | 2026-04-22
> 关联文档：dual-ai-review/SKILL.md、ACP全链路编码工作流架构设计

---

## 1. 基本原则

双 AI 对抗审查与 HardFlow G0-G6 门禁是**上下游关系**，不是替代关系。

- 双 AI 审查检查**业务合理性**（需求对不对、方案好不好、代码是否按规则做）
- HardFlow 门禁检查**格式完整性与自动化指标**（评分阈值、测试通过、安全检查）

**铁律**：没有双 AI 联合结论，不允许进入对应的 HardFlow Gate。

---

## 2. 映射关系表

| 双 AI 审查阶段 | 前置/后置 | 对应 HardFlow Gate | 关系说明 |
|---------------|-----------|-------------------|----------|
| 需求审查 | G0 之前 | G0 | 双 AI 先审业务合理性，通过后 G0 做格式化需求包校验 |
| 方案审查 | G0-G1 之间 | G1 | 双 AI 审查技术方案，通过后进入 HardFlow 编码循环 |
| 代码审查 | G3-G4 之间 | G4 | 双 AI 审查代码逻辑，G4 做自动化安全扫描 |

### 2.1 完整流程映射

```text
用户需求
    │
    ▼
外部检索 (web-agent)
    │
    ▼
project-agent 建立上下文
    │
    ▼
<< 双 AI 需求审查 >>
    ├── ready_for_solution → 继续
    ├── requires_revision → 回写 README.md → 重新审查
    └── blocked_by_unknowns → 暂停，补充信息
    │
    ▼
G0 需求包检查（格式化校验）
    │
    ▼
架构设计 / 实施规划更新
    │
    ▼
<< 双 AI 方案审查 >>
    ├── ready_for_implement → 继续
    ├── requires_revision → 回写架构设计 → 重新审查
    └── blocked_by_unknowns → 暂停，补充信息
    │
    ▼
G1 方案质量检查
    │
    ▼
编码实现（frontend-dev / backend-dev）
    │
    ▼
G2 前端检查 / G3 后端检查
    │
    ▼
<< 双 AI 代码审查 >>
    ├── pass → 继续
    ├── need_fix → 修复 → 重新审查
    └── reject → 回写需求/方案文档
    │
    ▼
G4 安全扫描 / G5 发布检查 / G6 终审
    │
    ▼
部署验收 (tester)
```

---

## 3. 信号转换规则

### 3.1 需求审查 → G0

| 双 AI 联合结论 | G0 门禁状态 | 说明 |
|---------------|------------|------|
| `ready_for_solution` | 待触发 | 允许 coordinator 触发 G0 |
| `requires_revision` | **阻断** | 必须先修改需求文档 |
| `blocked_by_unknowns` | **阻断** | 必须先补充信息 |
| 无审查产物 | **阻断** | 未触发双 AI 审查，G0 不允许执行 |

### 3.2 方案审查 → G1

| 双 AI 联合结论 | G1 门禁状态 | 说明 |
|---------------|------------|------|
| `ready_for_implement` | 待触发 | 允许 coordinator 触发 G1 |
| `requires_revision` | **阻断** | 必须先修改架构设计/实施规划 |
| `blocked_by_unknowns` | **阻断** | 必须先补充信息 |

### 3.3 代码审查 → G4

| 双 AI 联合结论 | G4 门禁状态 | 说明 |
|---------------|------------|------|
| `pass` | 待触发 | 允许进入 G4 安全扫描 |
| `need_fix` | **阻断** | 必须先修复代码 |
| `reject` | **阻断** | 可能需回写需求/方案 |

---

## 4. 执行器接口

`review_gate_enforcer.py` 负责读取双 AI 联合结论并控制门禁。

### 4.1 输入

```json
{
  "task_id": "task-20260422-001",
  "review_type": "requirements|solution|code",
  "review_path": ".workflow/reviews/task-20260422-001/consensus.md",
  "expected_verdict": ["ready_for_solution", "ready_for_implement", "pass"]
}
```

### 4.2 输出

```json
{
  "task_id": "task-20260422-001",
  "gate_allowed": true,
  "verdict": "ready_for_implement",
  "confidence": "high",
  "dissent": false,
  "next_action": "proceed_to_G1"
}
```

### 4.3 阻断输出

```json
{
  "task_id": "task-20260422-001",
  "gate_allowed": false,
  "verdict": "requires_revision",
  "confidence": "medium",
  "dissent": true,
  "dissent_detail": "A 认为可以通过，B 认为需要补充性能估算",
  "next_action": "human_arbitration_required",
  "rewrite_targets": ["architecture.md", "implementation-plan.md"]
}
```

---

## 5. 异常处理

| 异常情况 | 处理方式 |
|---------|----------|
| 审查产物格式不符合模板 | 拒绝，要求重新审查 |
| A/B 意见均为空或敷衍 | 拒绝，标记为"无效审查" |
| 3 轮未收敛且无人工裁决 | 阻断，等待用户裁决 |
| 审查材料缺失 | 阻断，要求补充材料 |
| 历史失败记录查询失败 | 告警但不阻断，继续审查 |

---

## 6. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-22 | 初始版本，定义双 AI 审查与 HardFlow 门禁的映射契约 |

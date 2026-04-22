# 双 AI 对抗审查共识规则

> 版本：v1.0 | 2026-04-22
> 关联文档：dual-ai-review/SKILL.md

---

## 1. 核心规则

### 1.1 模型隔离

- Reviewer-B 在产出**独立意见**阶段，**绝对不允许**看到 Reviewer-A 的意见
- Round 1（A 独立审查）完成后，A 的意见被锁定
- Round 2（B 独立审查 + 质疑）开始时，B 才能看到 A 的意见
- Round 3（A 回应质疑）开始时，A 才能看到 B 的质疑

### 1.2 讨论轮次上限

- 最多 3 轮讨论（Round 1-3）
- 第 3 轮结束后仍未收敛 → 强制标记分歧，上报人工裁决
- 不允许无限制讨论消耗 token

### 1.3 中止条件

以下情况任一发生，立即中止讨论：

1. **方向性错误**：任一方发现需求/方案/代码存在根本性方向错误（如 XY 问题、架构完全不可行）
2. **事实性错误**：任一方发现关键事实错误（如引用的 API 已废弃、依赖版本不兼容）
3. **安全一票否决**：代码审查中发现 P0 级安全风险

中止后输出 `blocked_by_unknowns`，不继续浪费 token。

---

## 2. 共识判定算法

```python
def resolve_consensus(opinion_a, opinion_b, round_count):
    if round_count > 3:
        return {"verdict": "dissent", "action": "human_arbitration"}
    
    if opinion_a == opinion_b:
        return {"verdict": opinion_a, "action": "proceed"}
    
    if is_directional_error(opinion_a) or is_directional_error(opinion_b):
        return {"verdict": "blocked_by_unknowns", "action": "halt"}
    
    if round_count == 3:
        return {"verdict": "dissent", "action": "human_arbitration"}
    
    return {"verdict": "continue", "action": "next_round"}
```

### 2.1 置信度加权

| 场景 | 置信度 |
|------|--------|
| A/B 一致且证据充分 | high |
| A/B 一致但证据较弱 | medium |
| A/B 分歧但 3 轮内一方被说服 | medium |
| A/B 分歧且 3 轮未收敛 | low（必须人工裁决） |

---

## 3. 分歧处理

### 3.1 分歧标记

当 A/B 无法达成一致时，审查产物必须包含：

```markdown
## 分歧记录

### 分歧点
- 争议主题：...
- A 的立场：...
- B 的立场：...
- 双方论据摘要：...

### 建议人工裁决的问题
1. ...
2. ...

### 风险提示
- 如果按 A 的方案执行：...
- 如果按 B 的方案执行：...
```

### 3.2 人工裁决流程

1. coordinator 收到分歧标记后，暂停当前任务
2. 向用户输出：分歧摘要 + 双方立场 + 风险对比
3. 用户选择：支持 A / 支持 B / 要求补充信息 / 提出第三种方案
4. 用户裁决写入 `DECISIONS.md`，作为项目级决策记录
5. 按用户裁决继续执行

---

## 4. 快速通道（轻量模式）

对于低风险、明确验收的小任务，可以启用快速通道：

| 条件 | 快速通道行为 |
|------|-------------|
| 纯文档更新（README、注释） | A 审查后，B 只做关键点抽查 |
| Bug 修复（已明确根因） | A 审查后，B 只验证修复是否彻底 |
| 配置变更（无代码逻辑变更） | A 审查后，B 只验证配置格式 |

快速通道需在审查产物中标注：`mode: fast_track`，并说明理由。

---

## 5. 问责与复盘

### 5.1 漏检追溯

如果审查通过后仍出现重大问题：

1. 回溯审查产物，分析 A/B 为何均未发现
2. 检查是 prompt 缺陷、模型能力不足、还是审查材料不完整
3. 将分析结果写入 `failure_analysis.md`，触发失败学习流程

### 5.2 模型性能记录

每次审查记录：

```json
{
  "task_id": "...",
  "review_type": "requirements|solution|code",
  "model_a": "gpt-5.4",
  "model_b": "glm-4.7",
  "a_verdict": "...",
  "b_verdict": "...",
  "final_verdict": "...",
  "rounds": 2,
  "post_review_issue": false,
  "timestamp": "2026-04-22T10:00:00Z"
}
```

用于后续分析哪个模型在哪种审查类型上表现更好。

---

## 6. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-22 | 初始版本，定义双 AI 对抗共识规则 |

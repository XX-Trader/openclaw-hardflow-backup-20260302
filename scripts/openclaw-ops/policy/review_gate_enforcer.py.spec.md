# review_gate_enforcer.py — 接口规范

> 版本：v1.0 | 2026-04-22
> 实现者：待分配
> 审核者：Claude Code

---

## 1. 职责

读取双 AI 对抗式审查的联合结论，决定是否允许进入下一个 HardFlow Gate。

**铁律**：没有双 AI 联合结论，G0 不允许执行。

## 2. 命令行接口

```bash
python review_gate_enforcer.py \
  --task-id <task_id> \
  --review-type requirements|solution|code \
  --review-path <path/to/consensus.md> \
  [--expected-verdict ready_for_solution|ready_for_implement|pass] \
  [--dry-run]
```

## 3. 输入

### 3.1 命令行参数

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `--task-id` | 是 | str | 任务唯一标识 |
| `--review-type` | 是 | enum | 审查类型：requirements / solution / code |
| `--review-path` | 是 | path | consensus.md 文件路径 |
| `--expected-verdict` | 否 | enum | 期望结论，用于校验 |
| `--dry-run` | 否 | flag | 只检查不执行 |

### 3.2 consensus.md 解析

必须解析以下字段：

```python
class ConsensusDoc(BaseModel):
    final_verdict: Literal[
        "ready_for_solution",
        "ready_for_implement",
        "pass",
        "requires_revision",
        "blocked_by_unknowns",
        "dissent"
    ]
    confidence: Literal["high", "medium", "low"]
    dissent: bool
    dissent_detail: Optional[str]
    rewrite_targets: Optional[list[str]]
    failure_learning_triggered: Optional[bool]
    rounds: int  # 讨论轮次
```

## 4. 状态机

```
【待检查】
    │
    ├──检查 consensus.md 存在？
    │   └── 否 → 【阻断】(GATE_BLOCKED: missing_review)
    │
    ├──解析有效？
    │   └── 否 → 【阻断】(GATE_BLOCKED: invalid_format)
    │
    ├── final_verdict 在允许列表中？
    │   └── 否 → 【阻断】(GATE_BLOCKED: unknown_verdict)
    │
    └── verdict == expected_verdict？
        ├── 是 → 【放行】(GATE_ALLOWED)
        └── 否
            ├── requires_revision → 【阻断】(GATE_BLOCKED: requires_revision)
            ├── blocked_by_unknowns → 【阻断】(GATE_BLOCKED: blocked)
            ├── dissent → 【阻断】(GATE_BLOCKED: dissent)
            └── 其他 → 【阻断】(GATE_BLOCKED: mismatch)
```

## 5. 输出

### 5.1 放行

```json
{
  "task_id": "task-20260422-001",
  "gate_allowed": true,
  "verdict": "ready_for_implement",
  "confidence": "high",
  "dissent": false,
  "review_type": "solution",
  "next_action": "proceed_to_G1",
  "timestamp": "2026-04-22T10:00:00Z"
}
```

### 5.2 阻断

```json
{
  "task_id": "task-20260422-001",
  "gate_allowed": false,
  "verdict": "requires_revision",
  "confidence": "medium",
  "dissent": true,
  "dissent_detail": "A 认为可以通过，B 认为需要补充性能估算",
  "review_type": "solution",
  "next_action": "human_arbitration_required",
  "rewrite_targets": ["architecture.md", "implementation-plan.md"],
  "timestamp": "2026-04-22T10:00:00Z"
}
```

## 6. 与 HardFlow 集成

`hardflow_runner.py` 在 G0 之前调用：

```python
# 伪代码
result = subprocess.run([
    sys.executable,
    "scripts/openclaw-ops/policy/review_gate_enforcer.py",
    "--task-id", task_id,
    "--review-type", "requirements",
    "--review-path", f".workflow/reviews/{task_id}/consensus.md",
    "--expected-verdict", "ready_for_solution"
], capture_output=True, text=True)

gate_result = json.loads(result.stdout)
if not gate_result["gate_allowed"]:
    raise GateBlockedError(gate_result)
```

## 7. 错误码

| 错误码 | 说明 | HTTP 状态码 |
|--------|------|-----------|
| `missing_review` | 审查产物不存在 | 400 |
| `invalid_format` | 审查产物格式不符合模板 | 400 |
| `unknown_verdict` | 结论值非法 | 400 |
| `requires_revision` | 需要修改后重新审查 | 403 |
| `blocked` | 关键信息缺失 | 403 |
| `dissent` | A/B 分歧未解决 | 403 |

## 8. 测试用例

### TC-1: 正常放行
- 输入：consensus.md 中 final_verdict = "ready_for_implement"
- 期望：返回 gate_allowed=true

### TC-2: 需要修改
- 输入：consensus.md 中 final_verdict = "requires_revision"
- 期望：返回 gate_allowed=false，next_action=rewrite_docs

### TC-3: A/B 分歧
- 输入：consensus.md 中 dissent=true
- 期望：返回 gate_allowed=false，next_action=human_arbitration_required

### TC-4: 缺少审查产物
- 输入：--review-path 指向不存在的文件
- 期望：返回错误码 missing_review

---

## 9. 实现提示

1. 使用 `pydantic` 做输入校验
2. 使用正则表达式从 markdown 中提取字段（不依赖 markdown parser 库，减少依赖）
3. 所有输出必须是 JSON，方便 hardflow_runner.py 解析
4. 日志写入 `.workflow/logs/review_gate_enforcer/<date>.log`

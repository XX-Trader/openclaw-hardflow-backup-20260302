# Task Center: 需求-结果验收评分流程

## 1. 任务模型
- `requirement.what`: 做什么
- `requirement.why`: 为什么
- `result.expected_outputs`: 可观测输出（文件/API/状态/消息）
- `result.observed_outputs`: 实际观测到的输出
- `acceptance.pass_line`: 通过线（0-100）
- `scoring.weights`: 默认 `result=70`、`stability=35`
- `action`: 决策与动作（`pass/retry/escalate` -> `通过/重试/升级人工`）

## 2. 创建任务（带需求与预期结果）
```bash
python3 ~/.openclaw/ops/task_center.py create \
  --title "P0 接口回归" \
  --bucket jobs \
  --priority P0 \
  --risk high \
  --source tester \
  --reason "回归阻断发布" \
  --what "验证接口A/B在高峰期稳定可用" \
  --why "保障发布窗口成功" \
  --expected-output "API /v1/a 返回200" \
  --expected-output "API /v1/b 延迟<300ms" \
  --acceptance-threshold 80
```

## 3. 评估任务（结果+稳定性 -> 动作）
```bash
python3 ~/.openclaw/ops/task_center.py evaluate \
  --task-id <TASK_ID> \
  --result-score 82 \
  --stability-score 70 \
  --observed-output "API /v1/a: 200" \
  --observed-output "API /v1/b: p95=240ms" \
  --note "夜间窗口验证"
```

## 4. 决策规则
- 归一化评分：`(result_score*result_weight + stability_score*stability_weight) / (result_weight + stability_weight)`
- 通过：`normalized_score >= pass_line` -> `status=DONE`
- 不通过且未超重试上限：`status=FAILED`，动作=`重试`
- 不通过且达到重试上限：`status=ESCALATED`，动作=`升级人工`

## 5. 备注
- 你的权重是 `70 + 35 = 105`，系统按“归一化加权平均”处理，保证最终评分仍是 `0-100`。
- 每次评估会写入 `task-events.jsonl`（`event_type=task_evaluated`）并保留动作历史。

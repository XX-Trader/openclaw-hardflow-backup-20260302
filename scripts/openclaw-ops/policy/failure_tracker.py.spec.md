# failure_tracker.py — 接口规范

> 版本：v1.0 | 2026-04-22
> 实现者：待分配
> 审核者：Claude Code

---

## 1. 职责

跟踪同类任务的失败次数，检测触发条件，为失败学习提供数据支撑。

**铁律**：偶发性失败不触发，只追踪系统性、反复性失败。

## 2. 命令行接口

```bash
# 检测是否触发失败学习
python failure_tracker.py check \
  --task-type <task_type> \
  --model <model_name> \
  [--project-key <key>]

# 记录一次失败
python failure_tracker.py record \
  --task-id <task_id> \
  --task-type <task_type> \
  --model <model_name> \
  --failure-reason <reason> \
  [--project-key <key>]

# 查询历史记录
python failure_tracker.py query \
  --task-type <task_type> \
  [--model <model_name>] \
  [--limit 10]

# 清理过期记录
python failure_tracker.py cleanup \
  [--days 30]
```

## 3. 数据模型

### 3.1 失败记录 (FailureRecord)

```python
class FailureRecord(BaseModel):
    record_id: str          # UUID
    task_id: str            # 关联任务 ID
    task_type: str          # 任务类型（如 requirements-review, solution-review, code-review）
    model: str              # 执行模型（如 gpt-5.4, glm-4.7）
    project_key: Optional[str]  # 关联项目
    failure_reason: str     # 失败原因摘要
    root_cause: Optional[str]   # 分析后的根因分类
    review_path: Optional[str]  # 审查产物路径
    timestamp: datetime     # 记录时间
    resolved: bool          # 是否已解决
    resolved_at: Optional[datetime]
    resolution: Optional[str]   # 解决方式
```

### 3.2 触发条件 (TriggerCondition)

```python
class TriggerCondition(BaseModel):
    task_type: str
    consecutive_failures: int = 2  # 连续失败次数阈值
    time_window_hours: int = 168   # 检查时间窗口（默认 7 天）
    models: Optional[list[str]]    # 指定模型（None 表示所有模型）
```

## 4. 存储

### 4.1 存储路径

```
.workflow/failure-tracking/
├── failures.ndjson           # 失败记录（按行追加的 JSON）
├── triggers.json             # 当前触发的学习任务
└── stats/
    ├── daily-<date>.json      # 每日统计
    └── monthly-<month>.json   # 每月统计
```

### 4.2 failures.ndjson 格式

每行一个 JSON 对象，按时间倒序排列：

```json
{"record_id": "rec-001", "task_id": "task-001", "task_type": "solution-review", "model": "gpt-5.4", "failure_reason": "方案复杂度过高", "timestamp": "2026-04-22T10:00:00Z", "resolved": false}
```

## 5. 输出

### 5.1 check 命令

```json
{
  "task_type": "solution-review",
  "triggered": true,
  "consecutive_failures": 3,
  "records": [
    {"record_id": "rec-003", "timestamp": "2026-04-22T10:00:00Z", "failure_reason": "..."},
    {"record_id": "rec-002", "timestamp": "2026-04-21T10:00:00Z", "failure_reason": "..."},
    {"record_id": "rec-001", "timestamp": "2026-04-20T10:00:00Z", "failure_reason": "..."}
  ],
  "suggested_action": "trigger_failure_learning"
}
```

### 5.2 query 命令

```json
{
  "task_type": "solution-review",
  "total_records": 15,
  "unresolved_count": 5,
  "records": [
    {...}
  ]
}
```

## 6. 与 dual-ai-review 的集成

Reviewer-B 在审查时必须查询 failure_tracker：

```bash
# 在 Reviewer-B 的 prompt 中嵌入
python failure_tracker.py query \
  --task-type <current_task_type> \
  --model <current_model> \
  --limit 5
```

如果查询结果显示该模型在此类任务上有未解决的失败记录，Reviewer-B 必须在审查产物中标注：

```markdown
## 历史失败警告
- 该模型在此类任务上近期有 {{unresolved_count}} 次未解决的失败
- 建议检查 failure_tracker 详情
```

## 7. 测试用例

### TC-1: 触发检测
- 设置：solution-review 连续 2 次失败
- 输入：failure_tracker.py check --task-type solution-review
- 期望：triggered=true

### TC-2: 未触发
- 设置：solution-review 只有 1 次失败
- 输入：failure_tracker.py check --task-type solution-review
- 期望：triggered=false

### TC-3: 记录失败
- 输入：failure_tracker.py record --task-id task-001 --task-type code-review --model gpt-5.4 --failure-reason "安全漏洞未发现"
- 期望：记录写入 failures.ndjson

### TC-4: 清理过期记录
- 输入：failure_tracker.py cleanup --days 30
- 期望：删除 30 天前的记录

---

## 8. 实现提示

1. 不使用数据库，直接操作 NDJSON 文件（减少依赖）
2. 写操作时使用文件锁（fcntl 或 Windows 等效方案）避免并发写冲突
3. 日志写入 `.workflow/logs/failure_tracker/<date>.log`
4. 支持按 `project_key` 过滤查询

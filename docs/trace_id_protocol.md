# trace_id 全链路注入协议

> 版本：v1.0 | 2026-03-28

## 1. 概述

所有 Agent 执行、Cron 任务、跨 Agent 调用必须携带 `trace_id`，实现完整链路追踪。

## 2. trace_id 格式

```
{source_type}:{source_id}:{timestamp_epoch}:{random_4hex}
```

示例：
- `cron:system-exception-patrol:1772729600:a1b2`
- `agent:ops-agent:1772729600:c3d4`
- `hook:hardflow-failure-detector:1772729600:e5f6`

## 3. 注入协议

### 3.1 Cron 任务入口

每个 runner 脚本的 `--task-id` 参数作为 trace_id 的 source_id：

```python
from chat_output import build_trace_id

trace_id = build_trace_id(task_id=args.task_id)
# 该 trace_id 贯穿整个执行周期
```

### 3.2 Agent Hook 入口

在 `hooks/` 中的每个 hook 脚本入口处生成 trace_id：

```python
import os, time, secrets

def generate_trace_id(source_type: str, source_id: str) -> str:
    ts = int(time.time())
    rand = secrets.token_hex(2)
    return f"{source_type}:{source_id}:{ts}:{rand}"

# 设置为环境变量，供子进程继承
os.environ["OPENCLAW_TRACE_ID"] = generate_trace_id("hook", hook_name)
```

### 3.3 跨 Agent 调用

通过 `task_center.db` 的 `context_json` 字段传播：

```json
{
  "parent_trace_id": "cron:web-intel-collect:1772729600:a1b2",
  "trace_id": "agent:ops-agent:1772729601:c3d4"
}
```

### 3.4 日志输出

所有日志行必须包含 trace_id 前缀：

```
[cron:system-exception-patrol:1772729600:a1b2] ✅ 扫描完成
```

## 4. 现有基础设施

| 组件 | 状态 |
|------|------|
| `build_trace_id()` in `chat_output.py` | ✅ 已就绪 |
| `--task-id` CLI 参数 | ✅ 所有 runner 已支持 |
| `policy_enforcer.py` context_json | ✅ 已支持 trace_id 字段 |
| 环境变量 `OPENCLAW_TRACE_ID` | 📋 协议约定，各 hook 自行实现 |

## 5. 落地路径

1. **已完成**：所有 runner 的 `--task-id` 作为 trace 源
2. **已完成**：`render_chat_notice()` 自动附加 trace_id
3. **待实现**：各 hook 入口统一注入环境变量（按需渐进）
4. **待实现**：异常报告中关联 trace_id 进行链路查询

---
name: todo-patrol
description: >
  TODO 巡检技能。用于扫描 todo.md 完成状态、检测过期任务、
  生成待办摘要和提醒。当需要审查项目进度或催办过期任务时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# TODO 巡检操作手册

## 适用场景

- 定期巡检 todo.md 完成状态
- 检测过期或长期未动的任务
- 生成待办摘要推送给用户
- 自动将完成项从 todo.md 移到 done.md
- 将到期 TODO 转成 Task Center 候选任务：低风险自动进入 backlog runner，高风险等待人工确认

## 操作流程

### 1. 执行巡检

```bash
python3 ~/scripts/openclaw-ops/todo_patrol.py --scan
```

### 2. 查看报告

```bash
python3 ~/scripts/openclaw-ops/todo_patrol.py --report
```

### 3. 自动归档完成项

```bash
python3 ~/scripts/openclaw-ops/todo_patrol.py --archive
```

## 巡检规则

| 规则 | 条件 | 动作 |
|------|------|------|
| 过期检测 | 任务带 `⏰` 时间标记且已过期 | 标记为过期 |
| 停滞检测 | `[/]` 状态超过 7 天未更新 | 告警 |
| 完成归档 | `[x]` 状态项 | 建议移入 done.md |

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `todo_patrol.py` | TODO 巡检引擎 |
| `todo_deadline_checker.py` | TODO 截止时间检测与标记 |
| `deadline_to_task_bridge.py` | 到期 TODO → Task Center 风险分流候选任务 |

## 约束

- 只读扫描，不自动修改 todo.md（归档需确认）
- 到期 TODO 必须先做风险分流：低风险可创建 `need_human_confirm=false` / `action=dispatch_pipeline` 候选，高风险必须创建 `need_human_confirm=true` 人工候选
- 巡检报告格式化为 Markdown 摘要

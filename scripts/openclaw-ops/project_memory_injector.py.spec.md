# project_memory_injector.py — 接口规范

> 版本：v1.0 | 2026-04-22
> 实现者：待分配
> 审核者：Claude Code

---

## 1. 职责

会话启动时，按项目注入记忆摘要到 coordinator 上下文中。

**铁律**：切换项目时必须清除旧项目上下文，避免混杂。

## 2. 命令行接口

```bash
python project_memory_injector.py \
  --project-key <key> \
  --session-id <session_id> \
  [--inject-level full|summary|minimal] \
  [--output-format markdown|json]
```

## 3. 输入

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `--project-key` | 是 | str | 项目唯一标识 |
| `--session-id` | 是 | str | 会话标识 |
| `--inject-level` | 否 | enum | 注入级别（默认 summary） |
| `--output-format` | 否 | enum | 输出格式（默认 markdown） |

## 4. 注入级别

| 级别 | 注入内容 | token 估算 |
|------|----------|------------|
| `full` | PROJECT_PROFILE.md 全文 + DELIVERY_RULES.md 全文 + DECISIONS.md 全文 | ~4000 |
| `summary` | PROJECT_PROFILE.md 摘要 + DELIVERY_RULES.md 全文 + DECISIONS.md 最近 5 条 | ~2000 |
| `minimal` | PROJECT_PROFILE.md 一句话描述 + DELIVERY_RULES.md 关键规则 | ~500 |

## 5. 输出

### 5.1 Markdown 格式（默认）

```markdown
# 项目上下文

## 基本信息
- 项目：xx-trader
- 类型：webapp
- 技术栈：Vue + Django + PostgreSQL

## 模块边界
...

## 交付规则
...

## 关键决策
1. 2026-04-20: 使用策略模式替代 if-else
2. 2026-04-18: API 版本锁定为 v2
```

### 5.2 JSON 格式

```json
{
  "project_key": "xx-trader",
  "session_id": "sess-001",
  "inject_level": "summary",
  "injected_files": ["PROJECT_PROFILE.md", "DELIVERY_RULES.md"],
  "injected_tokens": 2048,
  "status": "success",
  "memory_summary": "...",
  "timestamp": "2026-04-22T10:00:00Z"
}
```

## 6. 错误处理

| 错误 | 处理 |
|------|------|
| 项目不存在 | 返回空上下文，coordinator 决定是否创建新项目 |
| 画像文件缺失 | 告警，使用 `minimal` 级别（仅含 project_key） |
| 文件读取失败 | Fail-fast，上报错误 |

## 7. 测试用例

### TC-1: 正常注入
- 输入：project-key=xx-trader, inject-level=summary
- 期望：返回包含 profile + rules + decisions 摘要的上下文

### TC-2: 项目不存在
- 输入：project-key=non-existent
- 期望：返回空上下文，status=project_not_found

### TC-3: 级别降级
- 输入：inject-level=full 但文件过大
- 期望：自动降级为 summary，记录降级原因

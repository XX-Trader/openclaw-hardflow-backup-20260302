# MemTidy 记忆自动整理工作流 — 架构设计

> 版本：v1.0 | 2026-03-29

## 处理流程

```mermaid
graph TB
    A[Cron 每日03:00] --> B{备份所有记忆目录}
    B --> C[遍历 *.md 文件]
    C --> D{保护模式检查}
    D -->|匹配保护列表| E[🛡️ 跳过]
    D -->|不匹配| F{修剪关键词检查}
    F -->|匹配废弃词| G[🗑️ 删除]
    F -->|不匹配| H{文件年龄分类}
    H -->|0-30天| I[🔥 热：保持]
    H -->|31-180天| J{行数检查}
    J -->|>200行| K[📝 温：压缩摘要]
    J -->|≤200行| L[温：保持]
    H -->|180天+| M[📁 冷：归档]
```

## 规则配置结构

```json
{
  "hot_memory": { "days": 30 },
  "warm_memory": {
    "days_min": 31, "days_max": 180,
    "compact_threshold_lines": 200,
    "compact_target_lines": 80
  },
  "cold_memory": {
    "days": 181,
    "archive_dir": "~/.openclaw/memory-archive/"
  },
  "prune": {
    "keywords": ["测试对话", "调试日志", "临时笔记", ...],
    "empty_file_action": "delete"
  },
  "protected_patterns": ["MEMORY.md", "core-identity", "偏好", "soul", ...],
  "backup": { "enabled": true, "max_backups": 7 }
}
```

## 产物

| 产物 | 路径 |
|------|------|
| JSON 报告 | `~/.openclaw/ops/memtidy-reports/memtidy-<timestamp>.json` |
| Markdown 报告 | `~/.openclaw/ops/memtidy-reports/memtidy-<timestamp>.md` |
| 备份 | `~/.openclaw/ops/memtidy-backups/memtidy-backup-<timestamp>/` |
| 归档文件 | `~/.openclaw/memory-archive/` |

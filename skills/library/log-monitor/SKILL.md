---
name: log-monitor
description: >
  统一异常日志巡检技能。用于扫描多进程日志目录、分类异常、
  增量去重、生成巡检报告。当需要检查系统日志健康状态、
  定位异常模式时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# 统一异常日志巡检操作手册

## 适用场景

- 定期巡检系统日志（每 6 小时自动）
- 定位异常模式（重复错误、OOM、连接超时等）
- 生成增量巡检报告（只报告新出现的异常）
- 异常分类和优先级排序
- 将异常报告按 fingerprint 去重写入 Task Center 运维任务和 incident

## 操作流程

### 1. 执行全量扫描

```bash
# 带自动发现功能的全量扫描
python3 ~/skills/library/log-monitor/scripts/unified_exception_logger.py --auto-discover

# 指定目录扫描
python3 ~/skills/library/log-monitor/scripts/unified_exception_logger.py --scan-dir /var/log/openclaw
```

### 2. 查看巡检报告

报告产出路径：`~/.openclaw/ops/logs/exception_report_<timestamp>.json`

报告结构：
```json
{
  "scan_time": "2026-04-02T00:00:00Z",
  "total_files_scanned": 15,
  "new_exceptions": 3,
  "categories": {
    "connection_error": 2,
    "oom_kill": 1
  },
  "details": [...]
}
```

### 3. 异常分类标准

| 分类 | 关键词 | 严重度 |
|------|--------|--------|
| OOM/内存 | `OOM`, `MemoryError`, `killed` | 🔴 高 |
| 连接/网络 | `ConnectionError`, `timeout`, `refused` | 🟡 中 |
| 认证/授权 | `401`, `403`, `AuthError` | 🟡 中 |
| 文件/权限 | `PermissionError`, `FileNotFound` | 🟡 中 |
| Gateway | `gateway`, `crash`, `restart` | 🔴 高 |
| 配置/JSON | `JSONDecodeError`, `KeyError` | 🟢 低 |
| 未分类 | 其他 | 🟢 低 |

### 4. 增量去重

- 使用 MD5 指纹去重，同一异常在一个扫描周期内只报告一次
- 历史指纹存储在 `~/.openclaw/ops/logs/.exception_fingerprints`

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `unified_exception_logger.py` | 统一异常日志扫描器（21KB） |
| `exception_to_task_bridge.py` | 异常日志 → Task Center 运维任务/incident 桥接 |

## 约束

- 只读操作，不修改日志文件
- 自动建任务只写 Task Center，不直接做生产修复；critical 异常默认进入人工确认
- 巡检报告必须包含扫描范围和时间
- 高严重度异常必须在报告摘要中突出显示

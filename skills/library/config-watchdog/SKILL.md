---
name: config-watchdog
description: >
  配置变更安全兜底技能。用于定期快照 OpenClaw 配置文件、
  检测意外变更、JSON 格式校验、必要时自动回滚。
  当怀疑配置被意外修改或 JSON 损坏时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# 配置变更安全兜底操作手册

## 适用场景

- 定期配置快照（每 4 小时自动）
- 检测 `openclaw.json`、`jobs.json` 等核心配置意外变更
- JSON 格式校验（防止语法错误导致系统崩溃）
- 配置回滚到上一个已知正常快照

## 操作流程

### 1. 查看看门狗状态

```bash
python3 ~/skills/library/config-watchdog/scripts/config_watchdog.py --status
```

### 2. 手动触发快照

```bash
python3 ~/skills/library/config-watchdog/scripts/config_watchdog.py --snapshot
```

### 3. 检测变更

```bash
python3 ~/skills/library/config-watchdog/scripts/config_watchdog.py --diff
```

### 4. 回滚配置

```bash
# 查看可用快照
python3 ~/skills/library/config-watchdog/scripts/config_watchdog.py --list-snapshots

# 回滚到指定快照（需确认）
python3 ~/skills/library/config-watchdog/scripts/config_watchdog.py --rollback <snapshot_id>
```

## 监控的配置文件

| 文件 | 重要性 | 说明 |
|------|--------|------|
| `~/.openclaw/openclaw.json` | 🔴 关键 | 系统主配置 |
| `~/.openclaw/cron/jobs.json` | 🔴 关键 | 定时任务注册 |
| `~/.openclaw/ops/policy/policy-config.json` | 🟡 重要 | 策略配置 |

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `config_watchdog.py` | 配置看门狗（530 行） |

## 约束

- 快照存储在 `~/.openclaw/ops/config_snapshots/`
- 回滚操作需要用户二次确认（高危操作）
- JSON 校验失败时立即告警，不自动回滚

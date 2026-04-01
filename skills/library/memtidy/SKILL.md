---
name: memtidy
description: >
  MemTidy 记忆自动整理技能。用于 OpenClaw 记忆系统的
  热/温/冷三层管理、自动备份、过期修剪、容量监控。
  当需要整理记忆存储或诊断记忆膨胀问题时使用。
allowed-tools: Bash, Read, Grep
---

# MemTidy 记忆整理操作手册

## 适用场景

- 每日自动记忆整理（03:00 Cron）
- 记忆容量监控和报警
- 过期记忆修剪
- 记忆备份和恢复

## 三层记忆模型

| 层级 | 保留期 | 存储位置 | 操作 |
|------|--------|---------|------|
| 🔴 热层 | 7 天 | 活跃记忆 | 实时读写 |
| 🟡 温层 | 30 天 | 归档记忆 | 只读查询 |
| 🟢 冷层 | 90 天 | 压缩备份 | 按需恢复 |

## 操作流程

### 1. 查看记忆状态

```bash
python3 ~/scripts/openclaw-ops/memtidy_runner.py --status
```

### 2. 执行整理

```bash
# 标准整理（热→温→冷流转 + 过期修剪）
python3 ~/scripts/openclaw-ops/memtidy_runner.py --tidy

# 强制全量整理
python3 ~/scripts/openclaw-ops/memtidy_runner.py --tidy --force
```

### 3. 备份

```bash
python3 ~/scripts/openclaw-ops/memtidy_runner.py --backup
```

### 4. 恢复

```bash
python3 ~/scripts/openclaw-ops/memtidy_runner.py --restore <backup_id>
```

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `memtidy_runner.py` | 记忆整理引擎（518 行） |

## 约束

- 修剪操作先备份再删除，防止误删
- 冷层超过 90 天的记忆自动清除
- 整理报告输出当前各层容量和变动

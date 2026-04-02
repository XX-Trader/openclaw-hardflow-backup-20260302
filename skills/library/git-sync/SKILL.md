---
name: git-sync
description: >
  Git 同步与备份技能。用于本地 Git 备份、远程仓库同步、
  多服务器配置分发、代码变更追踪。
  当需要管理 Git 备份策略或排查同步问题时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# Git 同步与备份操作手册

## 适用场景

- 本地 Git 自动备份（commit-only，不推远端）
- 远程仓库同步（GitHub ↔ 本地）
- 多服务器间配置分发
- 排查同步冲突或丢失问题

## 操作流程

### 1. 本地备份状态

```bash
# 查看备份 runner 状态
python3 ~/.openclaw/ops/local_git_backup_runner.py --status

# 手动触发备份
python3 ~/.openclaw/ops/local_git_backup_runner.py --run
```

### 2. 远程同步

```bash
# 拉取远程变更
cd ~/scripts && git pull --rebase

# 推送本地变更
cd ~/scripts && git push
```

### 3. 多服务器分发

```bash
# 使用 fleet-sync 工具分发配置（参见 fleet-sync Skill）
python3 ~/scripts/openclaw-ops/multi_server_sync.py --target all
```

## 备份策略

| 仓库 | 备份频率 | 模式 | 保留策略 |
|------|---------|------|---------|
| `~/.openclaw/` | 每 4 小时 | commit-only | 保留 30 天 |
| `~/scripts/` | 每 4 小时 | commit + push | 永久（GitHub） |
| 项目仓库 | 按需 | push | 永久（GitHub） |

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `local_git_backup_runner.py` | 本地 Git 自动备份 |
| `multi_server_sync.py` | 多服务器同步 |
| `github_sync_runner.py` | GitHub 同步 |

## 约束

- 本地备份只 commit 不 push，防止敏感信息泄漏
- 同步冲突必须人工确认解决方案
- 黑名单排除：`.env`、`token`、`credentials` 等敏感文件

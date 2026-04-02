---
name: fleet-sync
description: >
  多服务器同步技能。用于跨服务器配置分发、Skill 部署、
  Cron Job 同步、状态对比。当需要在多台远程服务器间
  保持配置一致性时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# 多服务器同步操作手册

## 适用场景

- 将 nofx 验证通过的变更推广到其他服务器
- 跨服务器 Skill 目录同步
- Cron Job 配置分发
- 服务器间状态对比

## 服务器清单

| 别名 | 用途 | SSH 配置 |
|------|------|---------|
| nofx | 主验证服务器 | `ssh_config` |
| pm-website | 站点服务器 | `ssh_config` |
| 大白pm | 项目管理 | `ssh_config` |
| coingod | 交易服务 | `ssh_config` |
| tokyo-claw | 东京节点 | `ssh_config` |

## 操作流程

### 1. 状态对比

```bash
# 对比所有服务器的 manifest 版本
python3 ~/scripts/openclaw-ops/multi_server_sync.py --diff

# 对比指定服务器
python3 ~/scripts/openclaw-ops/multi_server_sync.py --diff --target pm-website
```

### 2. 配置分发

```bash
# 分发到所有服务器
python3 ~/scripts/openclaw-ops/multi_server_sync.py --sync --target all

# 分发到指定服务器
python3 ~/scripts/openclaw-ops/multi_server_sync.py --sync --target pm-website
```

### 3. Skill 部署

```bash
# 同步 Skill 目录到远程
scp -r -F D:/ssh_keys/ssh_config ~/.claude/skills/<skill-name> <alias>:~/.claude/skills/
```

### 4. 验证同步结果

```bash
# 远程检查
ssh -F D:/ssh_keys/ssh_config <alias> 'ls ~/.claude/skills/<skill-name>/'
```

## 同步策略

- **先 nofx 验证 → 再推广**：任何变更先在 nofx 单机验证稳定后再分发
- **skip-if-exists**：默认不覆盖已有文件，防止丢失本地定制
- **增量同步**：只同步有差异的文件

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `multi_server_sync.py` | 多服务器同步引擎 |
| `remote_deploy_skills.py` | 远程 Skill 部署 |

## 约束

- 使用 `D:/ssh_keys/ssh_config`（或 `F:/ssh_keys/ssh_config`）配置 SSH
- 长时间运行任务必须使用 tmux
- 破坏性操作需要用户二次确认

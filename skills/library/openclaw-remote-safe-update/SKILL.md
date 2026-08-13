---
name: openclaw-remote-safe-update
description: 处理远程工作流仓库的拉取冲突，支持运行态重置、stash 和快照分支三种显式策略。
---

# Remote Safe Update

本技能用于通用远程工作流仓库。主机、仓库位置、SSH 配置和分支都由参数或环境变量提供。

## 默认原则

- 运行态生成文件与源代码分离。
- 人工改动不自动丢弃。
- 同步只使用 `git fetch` 与 `git pull --ff-only`。
- 多个候选仓库同时命中时停止并要求显式 `--repo-path`。

## 策略

- `runtime-reset`：只恢复运行态白名单；发现其他改动时状态为 `blocked_dirty_nonvolatile`。
- `stash-nonvolatile`：暂存人工改动，快进拉取后恢复；冲突以 `stash_pop_conflict` 报告。
- `snapshot-branch`：把现场保存到时间戳分支，再恢复主分支并同步。

## 配置

```dotenv
SSH_CONFIG=~/.ssh/config
HARDFLOW_REMOTE_WORKFLOW_REPO=~/workflow-infra
```

## 命令

```bash
python3 skills/library/fleet-sync/scripts/remote_safe_update.py   --mode inspect   --servers HOST_A   --repo-path ~/workflow-infra

python3 skills/library/fleet-sync/scripts/remote_safe_update.py   --mode sync   --strategy runtime-reset   --servers HOST_A HOST_B   --repo-path ~/workflow-infra
```

运行态白名单默认包含项目索引、执行经验、会话和控制面运行目录；项目级 `memory/` 不属于运行态白名单。

## 实现

- `skills/library/fleet-sync/scripts/remote_safe_update.py`
- `skills/library/fleet-sync/scripts/remote_safe_update.ps1`
- `skills/library/fleet-sync/scripts/remote_safe_update.sh`

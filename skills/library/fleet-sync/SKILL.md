---
name: fleet-sync
description: >
  多主机同步技能。用于跨主机分发配置、安装运行时任务、对比版本与验证结果。
metadata: {"openclaw": {"requires": {"bins": ["python3", "ssh"]}, "os": ["linux", "windows"]}}
---

# 多主机同步

## 配置

主机清单来自命令参数或环境变量，不在仓库中固化真实别名、地址和凭证：

```dotenv
SSH_CONFIG=~/.ssh/config
HARDFLOW_FLEET_SERVERS=HOST_A,HOST_B
HARDFLOW_REMOTE_WORKFLOW_REPO=~/workflow-infra
HARDFLOW_REMOTE_RUNTIME_HOME=~/.openclaw
```

## 流程

1. 在单个验证主机执行 dry-run。
2. 比对代码版本、目标路径和预期变更。
3. 只向显式主机清单分发。
4. 在每台主机执行安装器并记录结构化结果。
5. 任一主机失败时保留已完成结果，只重试失败主机。

## 安装 TODO 巡检任务

```bash
DRY_RUN=1 bash skills/library/fleet-sync/scripts/sync_todo_patrol_to_servers.sh HOST_A
bash skills/library/fleet-sync/scripts/sync_todo_patrol_to_servers.sh HOST_A HOST_B
```

PowerShell 7：

```powershell
pwsh -File skills/library/fleet-sync/scripts/sync_todo_patrol_to_servers.ps1 `
  -Servers HOST_A,HOST_B `
  -DryRun
```

脚本复用仓库根目录 `setup.py`，通过 `--job-name` 安装单项任务；不会复制不存在的旧脚本。

## 安全更新

```bash
python3 skills/library/fleet-sync/scripts/remote_safe_update.py   --mode inspect --servers HOST_A --repo-path ~/workflow-infra
```

同步前先区分运行态文件与人工改动；默认只处理运行态白名单，其他改动会阻断同步。

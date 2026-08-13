---
name: openclaw-workflow-manager
description: 通用 Runtime 工作流管理技能，用于安装、漂移检查、技能补齐、调度核对和卸载。
---

# Runtime Workflow Manager

本技能管理工作流运行面，不承载项目业务逻辑。

## 入口

- 安装：仓库根目录 `python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME>`
- 技能补齐：`scripts/ensure_runtime_skills.py`
- 调度导出：`skills/library/control-plane-ops/scripts/export_schedule_registry.py`
- 卡住恢复：`skills/library/control-plane-ops/scripts/recover_stale_cron_running_state.py`
- 卸载：`scripts/uninstall_workflow_profile.py`

## 原则

所有路径、通知目标和时区显式注入；先 dry-run，后写入；安装和卸载都保留托管清单与回滚证据。

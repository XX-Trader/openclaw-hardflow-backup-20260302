---
name: openclaw-workflow-manager
description: Use when someone needs an OpenClaw workflow map, runbook, drift check, install or reinstall guidance, feature enable or disable guidance, daily health review, or external workflow intake for cron jobs, task executor, evolution chains, and git sync.
description_zh: "openclaw-workflow-manager 技能，用于解释、巡检和管理 OpenClaw 工作流。"
version: "1.0.0"
triggers:
  keywords:
    - "工作流地图"
    - "工作流管理"
    - "workflow manager"
    - "workflow map"
    - "定时任务说明"
    - "workflow drift"
    - "工作流巡检"
    - "启停工作流"
  auto_trigger: true
  confidence_threshold: 0.7
---

# OpenClaw Workflow Manager

将本技能视为 OpenClaw 工作流的控制面入口，而不是业务执行器本身。

用本技能解释整套工作流由哪些层组成、哪些部分已经自动化、哪些步骤仍需要人工确认；用本技能驱动安装、重装、启停、巡检、漂移校验、日志日检和外部模式接入评估。真正持续运行的仍然是 cron jobs、task center、task executor、reviewer 与各类 evolution runner。

## 何时使用

- 需要回答“当前工作流有哪些组成部分、怎么流转、多久执行一次”
- 需要解释某个 job 为什么存在、失败会影响哪条链路
- 需要安装、重装、卸载 OpenClaw workflow profile
- 需要对比仓库模板与运行态是否漂移
- 需要查看哪些能力已经实现、哪些只是可选、哪些还只是外部候选方案
- 需要做每日健康检查、异常归因或恢复卡住的 cron 状态
- 需要评估网上找到的新技能、新工作流是否适合接入当前体系

## 不适用场景

- 不直接代替 `governance_evolution_runner.py`、`self_evolution_todo.py`、`task_executor_runner.py` 执行业务任务
- 不把 `~/.openclaw/cron/jobs.json` 当作长期设计文档；它是运行态，不是唯一说明书
- 不把外部文章或外部技能直接当成当前系统真值；先做差异评估，再决定是否接入

## 使用流程

1. 先判定诉求类型：`解释`、`状态`、`变更`、`巡检`、`外部接入评估`。
2. 读取 `references/workflow-map.md`，建立“仓库模板 / 运行态 / 任务执行 / 代码回推”四层视图。
3. 读取 `references/operations.md`，选择现有脚本入口，不优先手改运行态文件。
4. 解释类问题必须区分：
   - 仓库模板：`cron/jobs.json`、`scripts/openclaw-ops/CRON_TASK_INDEX.md`
   - 运行态：`~/.openclaw/openclaw.json`、`~/.openclaw/cron/jobs.json`
   - 自动执行：cron -> task center -> task executor -> agent
   - 人工门禁：`need_human_confirm`、PR gate、review task
5. 变更类问题优先使用已有安装器：
   - 整体安装或对齐：`scripts/openclaw-ops/install_workflow_profile.py`
   - 整体卸载：`scripts/openclaw-ops/uninstall_workflow_profile.py`
   - 单项能力：`install_task_executor_job.py`、`install_project_index_job.py`、`install_governance_evolution_job.py`、`install_local_openclaw_backup_job.py`、`install_reviewer_scan_jobs.py`、`install_web_intel_jobs.py`
6. 巡检类问题优先使用已有只读工具：
   - 运行态绑定：`scripts/openclaw-ops/inspect_runtime_bindings.py`
   - 调度总表：`scripts/openclaw-ops/export_schedule_registry.py`
   - 卡住恢复：`scripts/openclaw-ops/recover_stale_cron_running_state.py`
7. 外部模式接入必须输出三段结论：
   - 当前系统是否已经有同类能力
   - 当前是已实现、未启用，还是完全缺失
   - 如果要接入，应落在技能、脚本、job、任务中心还是 PR gate 哪一层

## 快速对照

| 需求 | 优先入口 | 预期产物 |
| --- | --- | --- |
| 解释全景 | `references/workflow-map.md` | 结构图、边界、自动化范围 |
| 查看安装态 | `inspect_runtime_bindings.py` | repo 与 runtime 差异 |
| 查看任务编排 | `CRON_TASK_INDEX.md` + `cron/jobs.json` | job、频率、脚本入口 |
| 整体安装/重装 | `install_workflow_profile.py` | profile 对齐 |
| 整体卸载 | `uninstall_workflow_profile.py` | runtime 清理计划 |
| 恢复 cron 卡住 | `recover_stale_cron_running_state.py` | 清理 stale runningAtMs |
| 查看调度总表 | `export_schedule_registry.py` | schedule registry JSON |
| 评估外部模式 | `references/operations.md` 中“外部模式接入” | 差异分析与落点建议 |

## 核心原则

- 将 `cron/jobs.json` 视为仓库模板，将 `~/.openclaw/cron/jobs.json` 视为线上实际状态。
- 将 `openclaw/openclaw.json` 视为 overlay 源，将 `~/.openclaw/openclaw.json` 视为运行态配置。
- 将技能视为“地图 + 说明书 + 管理入口”，不要把技能本身当成无人值守调度器。
- 任何“启用 / 停用 / 调频 / 自动 PR”判断都要明确写出当前是仓库默认值还是运行态现值。
- 外部工作流接入先做差异评估，再做落地，不直接把网上方案覆盖本地工作流。

## 常见误区

- 把 `self_evolution_todo.py` 误认为自动改代码器。它默认产出的是建议和任务包，不直接改 workflow 仓库。
- 把 `github_web_evolution_runner.py` 误认为完全无人值守。默认仍可能需要人工确认。
- 把 `ops_local_openclaw_git_backup` 误认为会推远端。它是本地 commit-only 备份。
- 把仓库 `cron/jobs.json` 误认为线上真实状态。实际安装态可能漂移，必须再查 runtime。
- 把“发现了外部好方案”直接等价成“当前系统已有此能力”。必须标记为候选能力并给出接入层级。

## 参考资料

- `references/workflow-map.md`
- `references/operations.md`
- `docs/plans/2026-03-21-openclaw-workflow-evolution-upgrade-design.md`
- `scripts/openclaw-ops/CRON_TASK_INDEX.md`
- `cron/jobs.json`

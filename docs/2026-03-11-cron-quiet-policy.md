# 2026-03-11 Cron 静默策略调整

## 目标

减少 `coingod` 一类服务器上低价值、重复性的 Telegram cron 告警，只保留真正需要人工关注的异常。

## 本次默认收口

以下维护型任务安装后仍保持 `delivery.mode=none`，但不再额外写入 `failureAlert`：

- `todo_patrol_15m`
- `project_index_maintainer_30m`
- `ops_conversation_evolution_incremental`
- `ops_governance_evolution_incremental`
- `ops_github_web_evolution_incremental`
- `ops_git_sync_push`
- `ops_auto_update_install_hourly`
- `web_intel_collect_hourly`
- `web_intel_review_optimization_4h`
- `web_intel_review_project_docs_6h`

## 运维巡检忽略名单

`ops_cron_runner.py` 的 `workflow_monitor.ignore_job_names` 默认忽略上述维护型任务，以及运行时常见的 `task_retry_10m`。

效果是：

- 这些 job 自己超时，不再直接推 Telegram 单行失败告警。
- `ops_incremental_monitor` 不再把这些 job 计入“失败工作流”摘要，避免重复汇总。
- 关键巡检、reviewer、核心服务类问题仍会保留告警能力。

## 保留告警的方向

当前仍保留重点上报能力的，主要是：

- `ops_incremental_monitor`
- `ops_full_calibration`
- reviewer 相关任务
- 明确高风险的服务/运行态异常

## 说明

这次策略是“默认更安静”，不是删除运行记录。相关 job 的 run history、报告文件、cron 状态仍然保留，可通过官方 `openclaw cron` surface 查看。

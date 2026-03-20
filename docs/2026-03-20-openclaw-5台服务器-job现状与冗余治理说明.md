# OpenClaw 5 台服务器 Job 现状与冗余治理说明

## 1. 目标与结论

这份文档用于沉淀当前 `pm-website`、`大白pm`、`nofx`、`coingod`、`tokyo-claw` 5 台服务器上的 OpenClaw workflow job 现状、冗余判断、清理结果，以及整套 workflow 的执行闭环。

本次治理结论：

1. `project_index_maintainer_30m` 的真实运行频率已经是 `4h`，只是名字和 `task-id` 仍然沿用旧标识。
2. 仓库基线已统一改为 `project_index_maintainer_4h`，并已完成 5 台服务器统一同步安装，远端运行态已经收敛到新名字。
3. 已从服务器上清理 3 个明确冗余 job：
   - `大白pm` 的重复 `task_executor_10m`
   - `tokyo-claw` 的重复 `web_intel_collect_hourly`
   - `tokyo-claw` 的历史残留 `System Schedule Audit`
4. `ops_daily_summary` 和 `ops_daily_work_report_dingtalk` 都属于日报类 job，不属于这次要删除的冗余项。

## 2. 当前 5 台服务器基线

### 2.1 共同基线

当前 5 台服务器的共同基线是下面 19 个启用 job：

1. `todo_patrol_15m`
2. `task_executor_10m`
3. `ops_incremental_monitor`
4. `ops_full_calibration`
5. `ops_daily_summary`
6. `ops_system_schedule_audit`
7. `ops_daily_work_report_dingtalk`
8. `ops_self_evolution_weekly_todo`
9. `ops_governance_evolution_incremental`
10. `ops_github_web_evolution_incremental`
11. `ops_git_sync_push`
12. `ops_auto_update_install_hourly`
13. `ops_local_openclaw_git_backup`
14. `project_index_maintainer_4h`
15. `reviewer_incremental_daily_4am`
16. `reviewer_weekly_structure_review`
17. `web_intel_collect_hourly`
18. `web_intel_review_optimization_4h`
19. `web_intel_review_project_docs_6h`

说明：

1. 远端运行态现在已经显示 `project_index_maintainer_4h`。
2. 仓库代码、文档和运行态已经统一到新的 canonical name：`project_index_maintainer_4h`。

### 2.2 单机差异

| 服务器 | 启用 job 数 | 差异项 | 说明 |
|---|---:|---|---|
| `pm-website` | 20 | `ops_governance_evolution_incremental:lobster` | 业务特例，不是冗余 |
| `大白pm` | 19 | 无 | 已清掉重复 `task_executor_10m` 后回到标准基线 |
| `nofx` | 20 | `NOFX上游仓库同步检查` | 业务特例，不是冗余 |
| `coingod` | 19 | 无 | 当前最干净的标准模板机 |
| `tokyo-claw` | 19 | 无 | 已清掉重复 `web_intel_collect_hourly` 和历史残留 `System Schedule Audit` |

## 3. `project_index` 的真实状态

### 3.1 真实频率

5 台服务器当前 `project_index` job 的真实 schedule 都是：

```json
{
  "kind": "every",
  "everyMs": 14400000
}
```

这表示它实际是每 `4` 小时执行一次，而不是每 `30` 分钟执行一次。

### 3.2 为什么要改名

当前运行态有两个问题：

1. job 名字还是 `project_index_maintainer_30m`
2. payload 里的 `task-id` 还是 `cron:project-index-maintainer-30m`

这会造成两个认知问题：

1. 运营和排障时容易误以为它仍按 `30m` 在跑
2. 文档、监控、样例和运行态名字长期不一致

因此本次已经把仓库基线统一改成：

1. job name: `project_index_maintainer_4h`
2. task-id: `cron:project-index-maintainer-4h`

### 3.3 本轮实际落地结果

本轮已经按正式路径完成了远端切换：

1. 本地仓库先把 canonical name 和 task-id 收口到 `4h`
2. 代码已推送到 `origin/main`
3. 5 台目标服务器已完成 `git pull --ff-only`
4. 5 台目标服务器已重新执行 `install_workflow_profile.py --profile core`

最终结果是：

1. 5 台服务器的 live job 名称都已经切到 `project_index_maintainer_4h`
2. payload 内的 task-id 也已经切到 `cron:project-index-maintainer-4h`
3. 真实 schedule 仍然保持 `everyMs=14400000`

## 4. 两个日报 Job 的定义

### 4.1 `ops_daily_summary`

这条 job 是运维日报，当前 schedule 是：

```json
{
  "kind": "cron",
  "expr": "5 0 * * *",
  "tz": "Asia/Shanghai"
}
```

也就是北京时间每天 `00:05` 执行一次。

### 4.2 `ops_daily_work_report_dingtalk`

这条 job 是工作日报，当前 schedule 是：

```json
{
  "kind": "cron",
  "expr": "15 0 * * *",
  "tz": "Asia/Shanghai"
}
```

也就是北京时间每天 `00:15` 执行一次。

### 4.3 冗余判断

这两条 job 都是“日报类”，但职责并不完全相同：

1. `ops_daily_summary` 更偏向 cron/runtime/workflow 风险汇总
2. `ops_daily_work_report_dingtalk` 更偏向 TODO/DONE 和工作日报投递

所以它们不是这次要清理的“明确冗余 job”。

### 4.4 当前投递现状

需要特别注意的是，在本次代码收口之前，这两条日报在 5 台服务器上的 delivery 都还是 `announce`，而且 `to` 是 Telegram 正整数 ID，不是群组 ID。

本次策略已经统一调整为：

1. `ops_daily_summary -> delivery=none`
2. `ops_daily_work_report_dingtalk -> delivery=none`

也就是说，日报结果已经统一改成静默留痕，不再额外发给特定个人。

当前运行态会继续保留 `channel/to` 元数据，但由于 `mode=none`，它们不会实际向该个人发送日报。

## 5. 本次已清理的冗余 Job

### 5.1 `大白pm`

已删除重复 job：

1. `03921b44-1f7b-4d5d-bd1a-caa95dc8fcb1`
2. job name: `task_executor_10m`

保留的 canonical job：

1. `c2c75adf-5e80-4b50-bf18-40ceadfa6bd6`

备份文件：

1. `/home/ubuntu/.openclaw/cron/jobs.json.bak.redundancy-cleanup.20260320_143141`

### 5.2 `tokyo-claw`

已删除重复/残留 job：

1. `1e09769a-ffff-4660-9da0-f9d392f51dbc`
   - job name: `web_intel_collect_hourly`
2. `a330184b-4b1d-465f-9528-96f5ac1dbd51`
   - job name: `System Schedule Audit`

保留的 canonical `web_intel_collect_hourly`：

1. `fa03a968-2ce6-4cf9-a8ab-6c32f7c8a0a1`

备份文件：

1. `/root/.openclaw/cron/jobs.json.bak.redundancy-cleanup.20260320_143148`

### 5.3 清理后状态

清理后 5 台服务器的关键结果：

1. 每台都只剩 1 个 `task_executor_10m`
2. 每台都只剩 1 个 `web_intel_collect_hourly`
3. `tokyo-claw` 已不再存在 `System Schedule Audit`

## 6. 整套 Workflow 的中文梳理

这套 workflow 可以拆成三条链：

1. 单次需求交付链
2. 常驻巡检与派单链
3. 反馈与自演化链

### 6.1 单次需求交付链

当人直接提需求时，走 HardFlow 主链：

1. `coordinator` 接收需求
2. 进入 `hardflow workflow`
3. 依次经过 `classify -> G0 requirements -> dispatch -> G1 solution`
4. 继续经过 `implement -> test-loop -> review -> G2 frontend -> G3 backend -> G4 security`
5. 再过 `API doc gate -> predeploy gate -> deploy -> post-test`
6. 再过 `G5 release -> G6 final -> acceptance-test -> verify-completion`
7. 最后才允许 `git-push`

### 6.2 常驻巡检与派单链

当来源是 TODO、巡检、治理扫描或外部情报时，走自治闭环：

1. `todo_patrol` 扫描待办
2. `ops_cron` 扫描 runtime、workflow 和系统调度
3. `reviewer`、`web_intel`、`governance` 产生问题或建议
4. 进入 `task_center`
5. `task_executor_10m` 取 `pending` 任务
6. 调用对应 agent 执行
7. 把 `events / stage_runs / reports / token_usage` 回写

### 6.3 反馈与自演化链

系统并不是只执行任务，还会不断回看自己：

1. `ops_incremental_monitor` 和 `ops_full_calibration` 扫描运行健康
2. `reviewer` 负责结构审查和技术债
3. `web_intel` 负责外部信息采集和项目文档优化
4. `governance` 负责 workflow 本身的治理改进
5. 发现的问题继续回写到 `task_center`，再交给执行链处理

## 7. 总流程 ASCII 图

```text
┌──────────────────────────────┐
│      人 / Telegram / 指令入口      │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│  coordinator 接收任务并判断来源  │
│  是“明确需求”还是“巡检/待办事件”  │
└───────────────┬──────────────┘
                │
      ┌─────────┴─────────┐
      │                   │
      ▼                   ▼
┌──────────────────┐   ┌──────────────────────┐
│   单次需求交付链   │   │   常驻巡检与派单链      │
│ hardflow workflow │   │ cron / todo / 风险事件 │
└────────┬─────────┘   └──────────┬───────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐   ┌──────────────────────┐
│ classify         │   │ todo_patrol           │
│ G0 requirements  │   │ ops_incremental_monitor│
│ dispatch         │   │ reviewer / web_intel  │
│ G1 solution      │   │ governance            │
└────────┬─────────┘   └──────────┬───────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐   ┌──────────────────────┐
│ implement        │   │   policy / task_center │
│ test-loop        │   │   建单、派单、统一留痕   │
│ review           │   └──────────┬───────────┘
│ G2 / G3 / G4     │              │
└────────┬─────────┘              ▼
         │             ┌──────────────────────┐
         ▼             │ task_executor_10m    │
┌──────────────────┐   │ 定时取 pending 任务   │
│ API doc gate     │   └──────────┬───────────┘
│ predeploy gate   │              │
│ deploy           │              ▼
│ post-test        │   ┌──────────────────────┐
└────────┬─────────┘   │ 对应 agent 执行任务     │
         │             │ frontend/backend/... │
         ▼             └──────────┬───────────┘
┌──────────────────┐              │
│ G5 / G6          │              ▼
│ acceptance-test  │   ┌──────────────────────┐
│ verify-completion│   │ 回写 task_center      │
│ git-push         │   │ event/stage/report    │
└──────────────────┘   │ token/cost/status     │
                       └──────────────────────┘
```

## 8. 服务器常驻 Job 分层图

```text
┌──────────────────────────────────────────┐
│            服务器常驻 Job 分层图             │
└──────────────────────────────────────────┘

【第 1 层：待办与执行】
todo_patrol_15m
        │
        ▼
task_center
        │
        ▼
task_executor_10m

【第 2 层：运行巡检】
ops_incremental_monitor
ops_full_calibration
ops_system_schedule_audit

【第 3 层：日报/周报】
ops_daily_summary
ops_daily_work_report_dingtalk
ops_self_evolution_weekly_todo

【第 4 层：知识与治理】
project_index_maintainer_4h
ops_governance_evolution_incremental
ops_github_web_evolution_incremental
web_intel_collect_hourly
web_intel_review_optimization_4h
web_intel_review_project_docs_6h

【第 5 层：审查层】
reviewer_incremental_daily_4am
reviewer_weekly_structure_review

【第 6 层：同步与备份层】
ops_git_sync_push
ops_auto_update_install_hourly
ops_local_openclaw_git_backup
```

## 9. 后续建议

建议按下面顺序继续收口：

1. 如果后面仍希望把日报发到群里，再单独补一层“每台服务器 -> 群目标”的显式映射
2. 如果想把其他 `announce` 类运维任务也从个人改到群里，再统一收口 `channel/to` 策略

## 10. 更新时间

最后更新：2026-03-20 北京时间

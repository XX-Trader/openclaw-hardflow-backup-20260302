# OpenClaw Workflow Operations

本文件给出工作流管理技能的操作手册。原则是优先走现有脚本入口，不优先手改运行态文件。

## 1. 常见操作入口

### 1.1 整体安装或重装

适用：

- 新机器首次安装
- 运行态与仓库模板明显漂移
- 需要在 `core` 与 `all` profile 之间切换

命令：

```bash
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile core \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302
```

```bash
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile all \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302
```

说明：

- `core` 安装核心链路
- `all` 在 `core` 基础上附加 Web/GitHub 进化链路
- 如果需要更多参数，先执行 `python3 scripts/openclaw-ops/install_workflow_profile.py --help`

### 1.2 整体卸载运行态

适用：

- 需要清理当前 profile 管理的 runtime artifacts
- 需要重建运行态前先移除旧安装

命令：

```bash
python3 scripts/openclaw-ops/uninstall_workflow_profile.py \
  --profile all \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302 \
  --dry-run
```

说明：

- 先 `--dry-run` 看清理计划
- 该脚本只清理运行态，不会删除仓库源码

## 2. 单项能力管理

当前“单项启停”已经部分有安装器，但还没有所有功能都统一成一个总控脚本。优先顺序如下：

1. 能通过专用安装器重装的，优先用专用安装器
2. 能通过 profile 重装对齐的，优先整体对齐
3. 只有运行态存在、暂无统一安装器的，才考虑审慎编辑 `~/.openclaw/cron/jobs.json`

### 2.1 任务执行器

入口：

- `scripts/openclaw-ops/install_task_executor_job.py`

默认：

- job 名称：`task_executor_10m`
- 默认频率：`--every-ms 600000`

用途：

- 定时消费 task center 中的 pending 任务
- 这是“发现任务”与“真正执行任务”之间的关键桥梁

### 2.2 项目索引

入口：

- `scripts/openclaw-ops/install_project_index_job.py`

默认：

- job 名称：`project_index_maintainer_4h`
- 默认频率：`--every-ms 14400000`

用途：

- 维护项目索引、文档入口和 git HEAD 变更感知

### 2.3 运行态本地备份

入口：

- `scripts/openclaw-ops/install_local_openclaw_backup_job.py`

默认：

- job 名称：`ops_local_openclaw_git_backup`
- 默认频率：`--every-ms 3600000`

注意：

- 这是本地 commit-only 备份
- 不负责把 `~/.openclaw` 推远端

### 2.4 治理进化

入口：

- `scripts/openclaw-ops/install_governance_evolution_job.py`
- `scripts/openclaw-ops/cron_setup.py`

默认：

- job 名称：`ops_governance_evolution_incremental`
- 默认频率：`--every-ms 21600000`

关键开关：

- `--auto-pr`
- `--push-before-pr`
- `--project-context-gate`
- `--create-review-task`

### 2.5 Reviewer 巡检

入口：

- `scripts/openclaw-ops/install_reviewer_scan_jobs.py`

用途：

- 日度增量巡检
- 周度结构巡检
- 可选 PR gate

### 2.6 Web/GitHub 外部进化

入口：

- `scripts/openclaw-ops/install_web_intel_jobs.py`
- `scripts/openclaw-ops/cron_setup.py`

注意：

- 这是“外部模式发现链路”，不是默认所有场景都自动改代码
- 使用前要先确认人审门槛与执行边界

## 3. 状态、漂移与健康检查

### 3.1 查看 repo 与 runtime 绑定关系

命令：

```bash
python3 scripts/openclaw-ops/inspect_runtime_bindings.py
```

或机器可读输出：

```bash
python3 scripts/openclaw-ops/inspect_runtime_bindings.py --emit-json
```

用途：

- 看 agent、skill、hook、cron 绑定是否完整
- 看有没有 missing skills、unknown cron agents、runtime 冲突

### 3.2 导出统一调度总表

命令：

```bash
python3 scripts/openclaw-ops/export_schedule_registry.py --profile all --emit-json
```

用途：

- 把 openclaw jobs 和外部附着调度统一导出
- 适合做“这台机器上到底有什么调度面”的快照

### 3.3 恢复卡住的 running 状态

命令：

```bash
python3 scripts/openclaw-ops/recover_stale_cron_running_state.py --dry-run --emit-json
```

确认后再执行：

```bash
python3 scripts/openclaw-ops/recover_stale_cron_running_state.py --emit-json
```

用途：

- 清理 `~/.openclaw/cron/jobs.json` 中过期的 `runningAtMs`

注意：

- 先 dry-run
- 只在确认是 stale marker 时才执行

## 4. 每日巡检建议

每日或每次异常后，至少检查以下 6 项：

1. `~/.openclaw/cron/jobs.json` 中关键 job 是否仍为 `enabled=true`
2. `task_executor_10m` 是否还指向正确 manifest 和 report 目录
3. gateway 是否健康，是否存在 OAuth、handshake、config invalid 类错误
4. task center 是否存在长期 pending、failed、waiting_human_confirm 堆积
5. `ops_git_sync_push` 是否仍能 push，是否出现 remote mismatch 或冲突
6. `inspect_runtime_bindings.py` 是否报告新增 drift

## 5. 外部模式接入

当从网上发现新的技能、工作流或自动化方式时，按下面步骤处理：

### 5.1 先做对照，不先落代码

先回答 3 个问题：

1. 当前系统是否已经有同类能力
2. 当前是“已实现”“未启用”还是“完全缺失”
3. 如果接入，应落在哪一层

可选落点：

- 技能层：补地图、说明书、操作入口
- 脚本层：增加安装器、doctor、审计工具
- cron 层：新增 job 或调频
- task center 层：新增派单与执行链路
- gate 层：新增 PR gate、review task 或人工确认

### 5.2 再做最小接入

建议按“小步接入”处理：

1. 先补文档和地图
2. 再补只读巡检或 dry-run 能力
3. 最后再补自动改动、push 或 auto-pr

### 5.3 外部方案不要直接覆盖本地工作流

原因：

- 外部方案可能只适合单机、单仓库，当前系统却有 runtime、task center、review gate
- 外部方案可能假设“脚本直接执行”，当前系统却要求 agent 能力门禁和审计留痕
- 外部方案可能缺少“已实现/未启用/候选能力”的区分

## 6. 现在还缺什么

当前系统已经有不少安装器，但仍缺一个真正统一的总控入口。这个技能正是为了补这一层控制面：

- 让开发知道工作流由哪些部分构成
- 让运维知道当前状态、频率、依赖和告警面
- 让未来的新技能、新工作流接入有固定落点

换句话说，本技能现在既是地图，也是临时总控入口；后续如果再补统一 CLI 或 UI，本文件应继续作为说明书和索引。

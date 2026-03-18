# 2026-03-17 pm-website Cron 基线

## 目标

给 `pm-website` 这类“线上运行节点 + Telegram 交互入口 + 核心运维执行机”定义一套更稳的 cron 基线，避免把它同时当成重度 reviewer 机和全自动进化机。

## 适用范围

- 适用于 `pm-website`
- 可作为其他以“稳定运行优先”为目标的 OpenClaw 服务器参考
- 不直接等同于所有服务器的全量默认档位

## 本次确认的策略

### 必开

- `todo_patrol_15m`
- `task_executor_10m`
- `ops_incremental_monitor`
- `ops_full_calibration`
- `ops_system_schedule_audit`
- `ops_daily_work_report_dingtalk`

### 建议开

- `project_index_maintainer_30m`
  - 保留原 job 名称与 job id，避免破坏现有观测与历史映射
  - 调整为“按 git HEAD 变更触发索引，4 小时兜底执行一次”
  - 额外写入 `project-index-state.json`，记录上次已索引的 git HEAD
- `ops_local_openclaw_git_backup`
- `reviewer_weekly_structure_review`

### 可选

- `ops_daily_summary`
- `ops_governance_evolution_incremental`
- `ops_self_evolution_weekly_todo`

### 建议关闭

- `reviewer_git_update_hourly`
- `reviewer_incremental_daily_4am`
- `reviewer_recurring_bi_daily`

## 可选增强：PR 审查 / 自动合并 Gate 档

如果这台机器要承担“治理改动自动建 PR -> reviewer 自动审查 -> approval 命中后自动合并”的职责，可以在不恢复重型日审查的前提下，额外开启一档受控自动化：

- `ops_governance_evolution_incremental`
  - 开启 `auto-pr`
  - 仅允许受控 agent 创建 PR
- `reviewer_git_update_hourly`
  - 改成 `PR gate only`
  - 只检查 open PR
  - 只对命中 approval file 的受控 PR 执行 merge gate
  - `workspace` 必须指向真实 git 仓库根目录，不能指向 `~/.openclaw/workspace`
  - approval file 优先使用 `head_prefix + base` 规则，不建议手工逐条写 PR 编号
- 仍保持关闭：
  - `reviewer_incremental_daily_4am`
  - `reviewer_recurring_bi_daily`

## 设计理由

### 1. 项目索引不要固定 30 分钟硬跑

原来的 `project_index_maintainer_30m` 固定轮询过于频繁，而且在 git HEAD 没变化时重建索引没有收益，只会增加：

- 文件扫描成本
- 文档抓取成本
- 记忆链负担
- 运行噪音

调整后：

- 每次运行先读取 `project-index-state.json`
- 对 git 仓库取当前 `HEAD`
- 若与上次已索引 HEAD 相同，则直接跳过重建
- 只有 HEAD 变更或索引文件缺失时才重新生成
- 频率从 30 分钟降为 4 小时兜底

### 2. reviewer 不要在运行节点上高频常驻

`pm-website` 的核心职责是：

- 维持 Telegram 交互可用
- 跑核心运维巡检
- 执行 task-center 修复任务

而 reviewer 日级/小时级审查链路偏重，容易因为：

- `project-context-gate`
- `--fix`
- 长上下文
- 审查模型时延

拖慢整机运行稳定性。

因此 `pm-website` 上只保留：

- `reviewer_weekly_structure_review`

默认把高频 reviewer 链路关闭。

如果启用上面的“PR 审查 / 自动合并 Gate 档”，也只恢复 `reviewer_git_update_hourly` 的 PR gate 能力，不恢复 repo 全扫。

### 3. `task_executor_10m` 的通知必须首报后转增量

`pm-website` 的任务执行器是高频任务。如果每 10 分钟都把同一批未闭环问题完整重发，会直接淹没人能消费的信息。因此通知策略调整为：

- 第一次发现某批未闭环任务时，发送首报。
- 后续只有在以下情况才继续推送：
  - 新问题出现
  - 负责人变化
  - 状态变化
  - 阻塞原因变化
  - 任务闭环
- 如果本轮与上次相比没有变化，则静默，不重复刷屏。

同时，任务执行器的人类摘要改成固定五字段卡片：

- 事项
- 负责人
- 进展
- 问题
- 待补

不再输出大段“原因解析 / 执行概况 / 值得做”流水账。

## 建议的输出策略

对于 git 更新后触发的审查或优化结果，优先采用：

1. 先提交到独立 git 分支
2. 再人工或规则化创建 PR
3. reviewer 只审 PR，不直接改代码
4. approval 命中后再自动 merge

不建议由运行节点直接把自动审查结果推送到主分支。

## 实施清单

### 仓库侧

- `project_index_maintainer.py`
  - 新增 git HEAD 状态记录
  - 支持 `--skip-unchanged-git-projects`
- `install_project_index_job.py`
  - 默认改为 4 小时
  - 安装命令默认启用 `--skip-unchanged-git-projects`
- `workflow_views.py`
  - 展示文案改为“按 Git 更新 / 4 小时兜底”
  - `task_executor_10m` 改为“首报 + 增量 + 无变化静默”的紧凑问题卡片
- `policy/task_executor_runner.py`
  - 为 `task_executor_10m` 增加任务通知快照，按任务状态变化做增量推送

### pm-website 运行态

- `project_index_maintainer_30m`
  - 改为 `everyMs=14400000`
- `reviewer_incremental_daily_4am`
  - `enabled=false`
- `reviewer_git_update_hourly`
  - 默认 `enabled=false`
  - 如果启用 PR gate 档，则改为：
    - `enabled=true`
    - `--check-pr`
    - `--pr-gate-only`
    - 可选 `--allow-merge`
    - 必须配 `reviewer-merge-approval.json`
- `reviewer_recurring_bi_daily`
  - 保持 `enabled=false`
- `reviewer_weekly_structure_review`
  - 保持 `enabled=true`

## 验收点

- `project_index_maintainer_30m` 运行后会生成 `project-index-state.json`
- 同一 git HEAD 下重复执行时，任务应返回 skip，而不是重复重建
- `pm-website` 的 reviewer 只剩周审查启用
- `openclaw cron status --json` 中不再显示 reviewer 日审查为 active
- `task_executor_10m` 首次会完整播报未闭环任务，后续只在任务有新增 / 变化 / 闭环时发消息
- 同一批未闭环任务连续重复运行时，Telegram 不再每 10 分钟整批重发

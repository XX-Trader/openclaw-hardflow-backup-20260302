# OpenClaw Cron 定时任务索引

> 最后更新：2026-04-28
> 数据源：`cron/jobs.json`
> 裁剪记录：移除 3 个自进化 job（ops_git_sync_push / reviewer_incremental_daily / reviewer_weekly_structure）
> 投递模板：`delivery` / `failureAlert` 使用 `${HARDFLOW_NOTIFICATION_CHANNEL}` 与 `${HARDFLOW_NOTIFICATION_TARGET}`，安装时由环境或参数注入；未配置时安装器移除投递块。

## 任务总览

- **总计**：12 个定时任务
- **分类**：核心运维(4) / 项目交付(5) / 安全治理(2) / 基础设施(1)

## 一、核心运维任务

### 1.1 TODO 巡检（15分钟）
- **ID**：`16cb8d03-...`
- **频率**：每 15 分钟
- **功能**：巡检 TODO.md，去重播报，检测任务执行状态

### 1.2 每日 TODO 摘要
- **ID**：`2ce5fe63-...`
- **频率**：每日 00:00 UTC
- **功能**：生成每日 TODO 汇总，通过 Discord 群发送

### 1.3 系统异常巡检
- **ID**：`d4e5f6a7-...`
- **频率**：每 6 小时
- **功能**：扫描 Agent 工作流日志，按异常分类，MD5 指纹去重

### 1.4 异常日志转任务
- **ID**：`e6f7a8b9-...`
- **频率**：每 6 小时
- **功能**：将异常日志按 fingerprint 去重写入 Task Center 运维任务和 incident；critical 默认进入人工确认

## 二、项目交付任务

### 2.1 项目索引维护（4h）
- **ID**：`5797cd5b-...`
- **频率**：每 4 小时
- **功能**：维护项目文档索引，确保 INDEX.md 同步

### 2.2 截止时间检测
- **ID**：`f5e6f7a8-...`
- **频率**：每日
- **功能**：检测 todo 中的截止时间，到期预警

### 2.3 到期 TODO 转任务候选
- **ID**：`f6a7b8c9-...`
- **频率**：每日 00:05
- **功能**：将到期 TODO 转为 Task Center 候选任务；低风险任务可进入 `dispatch_pipeline`，高风险、需求不清、凭证或生产破坏类任务进入 `human_inbox.py` 等待确认

### 2.4 仓库精简巡检
- **ID**：`r1h2g3f4-...`
- **执行 agent**：`coordinator`
- **频率**：每 2 天
- **功能**：只读扫描冗余文件、失效缓存、冲突残留、重复文件和可清理项，生成报告并创建人工确认候选任务；不自动删除、不自动推送

### 2.5 Task Center 待办持续推进
- **ID**：`b9c8d7e6-...`
- **执行 agent**：`coordinator`
- **频率**：每 30 分钟
- **功能**：从 Task Center 选择 1 个低风险、无需人工确认、无需澄清的 pending 待办，或允许 `next_action` 的 failed 项，调用 `project-delivery-pipeline` 继续推进；高风险和人工门禁任务继续停在 `human_inbox.py`

## 三、安全治理任务

### 3.1 诚信审计
- **ID**：`a1b2c3d4-...`
- **频率**：每日
- **功能**：验证 claim 声明的真实性

### 3.2 配置安全巡检
- **ID**：`c3d4e5f6-...`
- **频率**：定期
- **功能**：监控配置文件变更，检测异常修改

## 四、基础设施任务

### 4.1 API 来源监控
- **ID**：`s1a2b3c4-...`
- **频率**：每 2 天
- **功能**：监控 API 数据来源注册表，检测失效源；`--base-path` 指向 runtime 项目记忆目录时必须按该目录读取，不回落到脚本默认目录

## ⛔ 已移除任务

| 任务名称 | 原 ID 前缀 | 移除原因 |
|----------|-----------|----------|
| ops_git_sync_push | `5dd96c0a` | 自进化 Git 同步，项目交付优先工作流不再需要 |
| reviewer_incremental_daily | `0f3ba2df` | 自进化代码评审，已裁剪 |
| reviewer_weekly_structure | `771fda88` | 自进化结构扫描，已裁剪 |
| memtidy_runner | `b2c3d4e5` | 2026-04-28 退役；Hermes 已有记忆整理能力，本仓不再安装或注册该任务 |

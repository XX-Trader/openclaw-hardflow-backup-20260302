# OpenClaw Cron 定时任务索引

> 最后更新：2026-03-28
> 数据源：`cron/jobs.json`

## 任务总览

- **总计**：22 个定时任务
- **启用**：19 个
- **禁用**：3 个
- **执行 Agent**：ops-agent(8) / optimization-agent(7) / reviewer(4) / coordinator(3)

## 一、核心运维任务

### 1.1 TODO 巡检（ops-agent）
- **频率**：每 15 分钟
- **脚本**：`todo_patrol.py`
- **功能**：巡检 TODO.md，去重播报，检测任务执行状态，自动请求 coordinator 分配未指派任务

### 1.2 每日 TODO 摘要（ops-agent）
- **频率**：每日 00:00 UTC
- **脚本**：`daily_todo_digest_runner.py`
- **功能**：生成每日 TODO 汇总，通过 Telegram 发送

### 1.3 系统异常巡检（ops-agent）
- **频率**：每 6 小时
- **脚本**：`unified_exception_logger.py`
- **功能**：扫描 Agent 工作流日志，按 7 类异常分类（API/文件系统/配置/Agent通信/系统/路径校验/通用），MD5 指纹去重，增量扫描

## 二、自进化闭环

### 2.1 目录树快照 + 变更增量扫描（optimization-agent）
- **频率**：每日 04:00
- **脚本**：`reviewer_cron_runner.py --mode daily_snapshot`
- **功能**：扫描工作流/Skills/Hooks 目录结构变更

### 2.2 自我进化总结（optimization-agent）
- **频率**：每日 04:37
- **脚本**：`reviewer_cron_runner.py --mode daily_self_evolution`
- **功能**：蒸馏每日记忆中的最佳实践，更新 Agent 行为约束配置

### 2.3 Hook 沙盒自测（optimization-agent）
- **频率**：每日（24h 间隔）
- **脚本**：`algo_micro_optimizer_runner.py`
- **功能**：运行 hook-selftest 检测 hook 健康度

### 2.4 Git 同步推送（optimization-agent）
- **频率**：每 6 小时
- **脚本**：`git_sync_push_runner.py`
- **功能**：自动同步审核通过的优化到远程仓库，内置密钥内容检测拦截

### 2.5 配置变更审核（optimization-agent）
- **频率**：每 6 小时
- **脚本**：`config_diff_review_runner.py`
- **功能**：监控 `.openclaw` 本地 git 变更，触发 optimization-agent 审核

### 2.6 Agent 自进化评估（ops-agent）
- **频率**：每周一 04:00
- **脚本**：`agent_self_evolution.py`
- **功能**：基于 task_center.db 历史数据多维度评分，生成优化建议报告

## 三、外部进化通道

### 3.1 上游社区进化（ops-agent）
- **频率**：每日 03:00
- **脚本**：`auto_update_install_runner.py`
- **功能**：拉取上游仓库最新代码并运行安装脚本，保持系统同步

### 3.2 网页情报采集（ops-agent）
- **频率**：每日 03:30
- **脚本**：`web_intel_collect_runner.py`
- **功能**：采集关注的网页情报源，存档变更，自动建单修复失败来源

### 3.3 开源项目进化（optimization-agent）
- **频率**：每日 04:00
- **脚本**：`github_web_evolution_runner.py`
- **功能**：扫描 GitHub 高信号仓库和 Skill4Agent 技能库，发现新工具/方法论

## 四、代码评审

### 4.1 每日增量评审（reviewer）
- **频率**：每日 04:00
- **脚本**：`reviewer_cron_runner.py --mode incremental_daily`
- **功能**：全量增量评审：代码质量/安全/架构，自动落地优化

### 4.2 每周结构扫描（reviewer）
- **频率**：每周日 04:30
- **脚本**：`reviewer_cron_runner.py --mode weekly_structure`
- **功能**：文件组织/依赖/冗余/一致性检查

### 4.3 每周安全审计（reviewer）
- **频率**：每周日 05:00
- **脚本**：`reviewer_cron_runner.py --mode weekly_security`
- **功能**：密钥泄漏/权限/XSS/注入扫描

### 4.4 每周文档新鲜度（reviewer）
- **频率**：每周日 05:30
- **脚本**：`reviewer_cron_runner.py --mode weekly_doc_freshness`
- **功能**：文档与代码的同步性检查

## 五、协调管理

### 5.1 心跳检测（coordinator）
- **频率**：每 5 分钟
- **功能**：coordinator 存活检测

### 5.2 每日工作规划（coordinator）
- **频率**：每日 04:00
- **功能**：生成每日工作规划

### 5.3 每周回顾（coordinator）
- **频率**：每周日 05:00
- **功能**：每周工作回顾总结

## ⏸️ 已禁用任务

| 任务名称 | Agent | 禁用原因 |
|----------|-------|----------|
| TODO 巡检-hardflow | ops-agent | 备份仓库巡检，当前不需要 |
| ops_governance_evolution_incremental | ops-agent | 治理巡检，先观察手动效果 |
| optimize 目录树快照-hardflow | optimization-agent | 备份仓库快照，当前不需要 |

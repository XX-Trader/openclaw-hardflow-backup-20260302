# 自进化优化工作流

> 状态：✅ 已上线 | 触发方式：每日/每周自动触发 / 人工触发
> 上级目录：[专项场景工作流](../README.md)

## 功能概述

OpenClaw 的自我优化引擎，通过定期评审代码质量、扫描系统瓶颈、分析执行数据，自动生成优化建议并落地。涵盖代码评审、配置同步、Hook 健康检测、工作流升级反馈等子系统。

## 核心能力

1. **每日增量评审** — 代码质量/安全/架构自动评审 + 优化落地
2. **每周结构扫描** — 文件组织/依赖/冗余/一致性检查
3. **每周安全审计** — 密钥泄漏/权限/XSS/注入扫描
4. **每周文档新鲜度** — 文档与代码的同步性检查
5. **优化建议→TODO** — 控制面分析 + MD5 去重 + 风险标记自动写入
6. **配置双向同步** — GitHub ↔ 服务器 .openclaw 配置自动同步
7. **Hook 沙盒自测** — 定期运行 hook-selftest 检测健康度
8. **升级反馈** — 执行报告→workflow scorecard→低分自动回流

## 核心组件

| 组件 | 路径 | 规模 |
|------|------|------|
| 评审执行器 | `scripts/openclaw-ops/reviewer_cron_runner.py` | 98KB |
| 优化顾问 | `scripts/openclaw-ops/control_plane_optimization_advisor.py` | 23KB |
| Hook 自测器 | `scripts/openclaw-ops/algo_micro_optimizer.py` | 8KB |
| 升级反馈收集 | `scripts/openclaw-ops/upgrade_feedback_runner.py` | 35KB |
| 工作流审计 | `scripts/openclaw-ops/workflow_audit.py` | 13KB |
| 工作流升级评分 | `scripts/openclaw-ops/workflow_upgrade_scoring.py` | 5KB |
| Git 同步推送 | `scripts/openclaw-ops/git_sync_push_runner.py` | 27KB |
| 配置变更审核 | 通过 config_diff_review cron 触发 | — |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| reviewer_incremental_daily_4am | reviewer | 每日 04:00 |
| reviewer_weekly_structure_review | reviewer | 每周日 04:30 |
| reviewer_weekly_security_audit | reviewer | 每周日 05:00 |
| reviewer_weekly_doc_freshness | reviewer | 每周日 05:30 |
| advisor_todo_daily | optimization-agent | 每日 04:15 |
| algo_micro_optimizer_daily | optimization-agent | 每24小时 |
| upgrade_feedback_daily | optimization-agent | 每日 03:00 |
| ops_git_sync_push | optimization-agent | 每6小时 |
| config_diff_review | optimization-agent | 每6小时 |
| local_config_snapshot | optimization-agent | 每1小时 |

## 子功能文档

| 子功能 | 位置 | 说明 |
|--------|------|------|
| 配置自动进化 | [`docs/自动进化/配置自动进化/`](../../自动进化/配置自动进化/README.md) | 三层目录架构（A/B/C层）+ 四层同步循环 |

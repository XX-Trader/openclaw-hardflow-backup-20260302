# 配置自动进化 — 功能索引

> 所属路线图：[阶段四·任务 4.2 / 4.3](../../execution-roadmap.md)
> 上级目录：[自动进化体系](../README.md)

## 功能概述

OpenClaw 运行时配置的双向自动同步：下行部署（GitHub → 服务器）+ 上行备份（服务器 → GitHub）。

## 文档清单

| 文档 | 内容 |
|------|------|
| [架构设计](architecture.md) | 三层目录架构（A/B/C 层）、四层同步循环、定时任务映射 |
| [实施计划](implementation-plan.md) | 模块划分、代码位置索引、4 个 Phase 实施步骤 |

## 涉及的定时任务

| Cron 任务 | 周期 | Agent | 职责 |
|-----------|------|-------|------|
| `auto_update_daily` | 每日 03:00 | ops-agent | 从 GitHub pull + setup 安装 |
| `config_diff_review` | 每 6 小时 | optimization-agent | 检测本地 git 变更并审核 |
| `ops_git_sync_push` | 每 6 小时 | optimization-agent | 审核 + push 到 GitHub |
| **待新建** | 每 1 小时 | optimization-agent | 本地 git 快照 |

## 涉及的脚本

| 脚本 | 路径 | 状态 |
|------|------|------|
| 部署入口 | `setup.py` | ✅ |
| Git Sync 执行器 | `scripts/openclaw-ops/git_sync_push_runner.py` | ✅ |
| Cron 安装器 | `scripts/openclaw-ops/install_git_sync_job.py` | ✅ |
| 本地快照 | `scripts/openclaw-ops/local_snapshot_runner.py` | ❌ 待新建 |

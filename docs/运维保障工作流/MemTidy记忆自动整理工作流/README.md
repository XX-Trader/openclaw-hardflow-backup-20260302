# MemTidy 记忆自动整理工作流

> 状态：✅ 已上线 | 触发方式：每日凌晨 3:00 自动触发
> 上级目录：[运维保障工作流](../README.md)

## 功能概述

记忆文件热/温/冷三层自动管理系统。每日低峰期扫描所有记忆目录，按文件年龄和内容特征执行保持/压缩/归档/修剪操作，自动备份后执行，降低 Token 消耗并提升召回准确率。

## 代码审计结果

> ⚠️ 用户规划中标注为"开发中"，但代码审计发现 **脚本已完整实现（518行）**、规则文件已配置、**Cron Job 已注册**。

## 三层管理策略

| 层级 | 时间范围 | 操作 |
|------|----------|------|
| 🔥 热记忆 | 0-30天 | 保持原样 |
| 📝 温记忆 | 31-180天 | 超长文件压缩摘要（>200行 → 保留前80行） |
| 📁 冷记忆 | 180天+ | 移入归档目录 |
| 🗑️ 修剪 | 匹配废弃关键词 | 直接删除 |
| 🛡️ 保护 | 匹配核心模式 | 永不处理 |

## 保护文件模式

`MEMORY.md`、`core-identity`、`偏好`、`system-prompt`、`soul`、`INDEX.md`、`agent.md`

## 修剪关键词

`测试对话`、`调试日志`、`临时笔记`、`test_session`、`debug_log`、`tmp_`、`scratch_`

## 核心组件

| 组件 | 路径 | 规模 |
|------|------|------|
| MemTidy 执行器 | `scripts/openclaw-ops/memtidy_runner.py` | 518行 / 18KB |
| 规则配置 | `config/memtidy_rules.json` | 1.4KB |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| memtidy_runner（每日记忆整理） | coordinator | 每日 03:00 |

## 备份策略

- 每次执行前自动备份所有记忆目录
- 备份位置：`~/.openclaw/ops/memtidy-backups/`
- 最多保留 7 个备份

## 产物

- JSON 报告：`~/.openclaw/ops/memtidy-reports/memtidy-{timestamp}.json`
- Markdown 报告：`~/.openclaw/ops/memtidy-reports/memtidy-{timestamp}.md`

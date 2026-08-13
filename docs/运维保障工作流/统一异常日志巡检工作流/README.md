# 统一异常日志巡检工作流

> 状态：✅ 已上线 | 触发方式：每6小时自动触发
> 上级目录：[运维保障工作流](../README.md)

## 功能概述

统一采集所有 Agent 工作流日志中的异常信息，按 7 类异常自动分类，MD5 指纹去重避免重复告警，增量扫描仅处理近期日志，并自动执行日志生命周期管理（压缩/删除）。

支持 `--auto-discover` 自动发现模式，无需手动指定日志目录，自动扫描 `~/.openclaw/` 下所有 agent sessions、executor runs、系统日志等目录。

## 代码审计结果

> ⚠️ 用户规划中标注为"开发中"，但代码审计发现 **脚本已完整实现（21KB）** 且 **Cron Job 已注册运行**。

## 7 类异常分类

| # | 分类 | 说明 |
|---|------|------|
| 1 | `api_error` | API 调用失败（超时/限速/认证） |
| 2 | `filesystem_error` | 文件读写/权限/磁盘空间 |
| 3 | `config_error` | 配置加载/解析/缺失 |
| 4 | `agent_communication_error` | Agent 间通信失败 |
| 5 | `system_error` | 内存/进程/系统级异常 |
| 6 | `path_validation_error` | 路径合法性校验错误 |
| 7 | `general_error` | 未分类通用异常 |

## 核心组件

| 组件 | 路径 | 规模 |
|------|------|------|
| 异常巡检器 | `skills/library/log-monitor/scripts/unified_exception_logger.py` | 21KB / 549行 |

## Auto-Discover 目录发现（2026-03-29 新增）

使用 `--auto-discover` 时，自动扫描以下 7 类日志目录（glob 匹配，仅包含实际存在的目录）：

| # | Glob 模式 | 说明 |
|---|-----------|------|
| 1 | `agents/*/sessions` | 各 Agent 会话日志（核心） |
| 2 | `ops/task-center/executor-runs` | 任务执行器报告 |
| 3 | `ops/exception-reports` | 历史异常报告 |
| 4 | `ops/workflow-logs` | 工作流日志 |
| 5 | `logs` | Gateway/系统日志 |
| 6 | `workspace-*/sessions` | Workspace 会话日志 |
| 7 | `subagents/*/sessions` | 子 Agent 会话日志 |

**用法**：
```bash
# 自动发现模式（推荐）
python3 unified_exception_logger.py --auto-discover --dry-run

# 自动发现 + 手动补充
python3 unified_exception_logger.py --auto-discover --log-dirs /extra/dir --output-dir ~/.openclaw/ops/exception-reports/

# 传统手动指定模式（向后兼容）
python3 unified_exception_logger.py --log-dirs /dir1 /dir2 --dry-run
```

## 日志生命周期

| 时间 | 操作 |
|------|------|
| 0-7天 | 原始保留 |
| 7-30天 | gzip 压缩归档 |
| 30天+ | 自动删除 |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| system_exception_patrol | coordinator | 每6小时 |

## 产物目录

- 分类报告：`~/.openclaw/ops/exception-reports/`
- 异常归档：`~/.openclaw/logs/abnormal/`

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-03-29 | 新增 `--auto-discover` 自动目录发现，解决 AI agent 路径推理错误问题 |
| 2026-03-28 | 新增第 7 类异常分类 `path_validation_error` + `--abnormal-dir` + `--cleanup` |
| 2026-03-25 | 初始版本：6 类异常分类 + MD5 指纹去重 |

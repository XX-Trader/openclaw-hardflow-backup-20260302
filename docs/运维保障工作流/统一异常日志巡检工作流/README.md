# 统一异常日志巡检工作流

> 状态：✅ 已上线 | 触发方式：每6小时自动触发
> 上级目录：[运维保障工作流](../README.md)

## 功能概述

统一采集所有 Agent 工作流日志中的异常信息，按 7 类异常自动分类，MD5 指纹去重避免重复告警，增量扫描仅处理近期日志，并自动执行日志生命周期管理（压缩/删除）。

## 代码审计结果

> ⚠️ 用户规划中标注为"开发中"，但代码审计发现 **脚本已完整实现（18KB）** 且 **Cron Job 已注册运行**。

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
| 异常巡检器 | `scripts/openclaw-ops/unified_exception_logger.py` | 18KB |

## 日志生命周期

| 时间 | 操作 |
|------|------|
| 0-7天 | 原始保留 |
| 7-30天 | gzip 压缩归档 |
| 30天+ | 自动删除 |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| system_exception_patrol | ops-agent | 每6小时 |

## 产物目录

- 分类报告：`~/.openclaw/ops/exception-reports/`
- 异常归档：`~/.openclaw/logs/abnormal/`

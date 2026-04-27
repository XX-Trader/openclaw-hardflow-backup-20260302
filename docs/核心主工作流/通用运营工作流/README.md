# 通用运营工作流

> 状态：✅ 已上线 | 触发方式：人工触发 / 事件自动触发
> 上级目录：[核心主工作流](../README.md)

## 功能概述

OpenClaw 的日常运营中枢，负责任务调度、监控巡检、需求对接、故障处理、功能优化。所有非编码类的运营活动（TODO 管理、Agent 协调、日报生成、配置核查等）均通过本工作流驱动。

## 核心能力

1. **任务路由与调度** — 基于 `routing-rules.json` 自动分配任务到合适 Agent
2. **风险门禁** — 高风险任务强制人工审核（失败≥3次自动升级）
3. **评分闭环** — `raw_score = result_score × 0.70 + stability_score × 0.30`
4. **TODO 巡检** — 每15分钟扫描 TODO.md，未分配项自动请求 coordinator 分配
5. **日报/周报** — 自动生成任务统计、Token 消耗、Agent 表现报告
6. **coordinator 协调** — 心跳检测、每日工作规划、每周回顾

## 文档清单

| 文档 | 内容 |
|------|------|
| [架构设计](architecture.md) | 任务中心数据模型、路由策略、评分机制、消息通知 |

## 核心组件

| 组件 | 路径 | 说明 |
|------|------|------|
| Policy Enforcer | `scripts/openclaw-ops/policy/policy_enforcer.py` | 硬约束策略执行器（28+ CLI 子命令） |
| Task Center | `scripts/openclaw-ops/policy/task_center.py` | SQLite 任务中心（188KB，任务/事件/阶段/token） |
| Task Executor | `scripts/openclaw-ops/policy/task_executor_runner.py` | 任务分发执行器（91KB） |
| TODO Patrol | `scripts/openclaw-ops/todo_patrol.py` | TODO 巡检器（57KB） |
| Daily Digest | `scripts/openclaw-ops/daily_todo_digest.py` | 每日摘要生成（39KB） |
| Daily Report | `scripts/openclaw-ops/daily_work_report.py` | 工作日报生成（56KB） |
| Routing Rules | `scripts/openclaw-ops/policy/routing-rules.json` | 任务路由规则（14KB） |
| Policy Config | `scripts/openclaw-ops/policy/policy-config.json` | 硬约束策略配置 |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| TODO 巡检（15分钟） | coordinator | 每15分钟 |
| daily_todo_digest_daily | coordinator | 每日 00:00 |
| coordinator 心跳 | coordinator | 每5分钟 |
| coordinator_daily_plan | coordinator | 每日 04:00 |
| coordinator_weekly_retrospective | coordinator | 每周日 05:00 |
| todo_deadline_checker_daily | coordinator | 每日 00:00 |

## 详细文档

- Policy Enforcer 代码级文档：[`scripts/openclaw-ops/policy/README.md`](../../../scripts/openclaw-ops/policy/README.md)
- 字段字典：[`scripts/openclaw-ops/policy/FIELD_DICTIONARY.md`](../../../scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)
- TODO 巡检策略流程：[`scripts/openclaw-ops/TODO_PATROL_POLICY_FLOW.md`](../../../scripts/openclaw-ops/TODO_PATROL_POLICY_FLOW.md)

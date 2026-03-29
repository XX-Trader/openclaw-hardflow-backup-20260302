# OpenClaw 文档导航（INDEX）

> 最后更新：2026-03-29 | 代码审计同步
> 配套文件：[execution-roadmap.md](execution-roadmap.md)（路线图）、[todo.md](../todo.md)（待办）、[done.md](../done.md)（已完成）

---

## 📊 工作流全景图

| 工作流类型 | 工作流名称 | 状态 | 触发方式 | 核心能力 |
|------------|-----------|------|----------|----------|
| 🎯 核心主工作流 | [通用运营工作流](核心主工作流/通用运营工作流/README.md) | ✅ 已上线 | 人工/事件触发 | 任务调度、TODO巡检、日报、评分闭环 |
| 🎯 核心主工作流 | [ACP全链路编码工作流](核心主工作流/ACP全链路编码工作流/README.md) | ✅ 已上线 | 人工触发 | G0-G6门禁、回流整改、部署验收 |
| 📦 专项场景 | [巡检故障闭环工作流](专项场景工作流/巡检故障闭环工作流/README.md) | ✅ 已上线 | 每6小时/异常触发 | 异常分类→知识库匹配→自修复 |
| 📦 专项场景 | [记忆知识沉淀工作流](专项场景工作流/记忆知识沉淀工作流/README.md) | ✅ 已上线 | 每日/每周 | 知识蒸馏、经验→技能封装 |
| 📦 专项场景 | [情报采集分析工作流](专项场景工作流/情报采集分析工作流/README.md) | ✅ 已上线 | 每日自动 | 上游同步、网页爬取、GitHub扫描 |
| 📦 专项场景 | [自进化优化工作流](专项场景工作流/自进化优化工作流/README.md) | ✅ 已上线 | 每日/每周 | 评审、配置同步、Hook自测、升级反馈 |
| 📦 专项场景 | [任务成本统计工作流](专项场景工作流/任务成本统计工作流/README.md) | 🔧 部分实现 | 任务完成触发 | Token统计、成本分析（缺独立报表） |
| 🚀 运维保障 | [配置变更安全兜底工作流](运维保障工作流/配置变更安全兜底工作流/README.md) | ✅ 已上线 | 每4小时 | 配置快照、变更检测、JSON校验、回滚 |
| 🚀 运维保障 | [统一异常日志巡检工作流](运维保障工作流/统一异常日志巡检工作流/README.md) | ✅ 已上线 | 每6小时 | 7类异常分类、MD5去重、增量扫描 |
| 🚀 运维保障 | [MemTidy记忆整理工作流](运维保障工作流/MemTidy记忆自动整理工作流/README.md) | ✅ 已上线 | 每日03:00 | 热/温/冷三层管理、备份+修剪 |

---

## 🏗️ 基础设施

| 分类 | 入口 | 文档数 |
|------|------|--------|
| [部署与运维](基础设施/部署与运维/README.md) | Linux/Windows部署、Gateway守护、排障 | 7篇 |
| [多Agent体系](基础设施/多Agent体系/README.md) | 14 Agent 角色绑定、能力 manifest | 1篇 |
| [协议与规范](基础设施/协议与规范/README.md) | trace_id、任务派发、错误进化、TG输出 | 4篇 |
| [治理与审核](治理与审核/README.md) | Cron治理、升级方案、优化backlog | 5篇 |

---

## 📐 架构决策 (ADR)

| ADR | 日期 | 主题 |
|-----|------|------|
| [default-coding-workflow-profile](adr/2026-03-22-default-coding-workflow-profile.md) | 2026-03-22 | 默认编码工作流 Profile |
| [foundation-contract-standard](adr/2026-03-23-openclaw-foundation-contract-standard.md) | 2026-03-23 | 基础设施契约标准 |
| [requirement-package-gate-standard](adr/2026-03-24-requirement-package-gate-standard.md) | 2026-03-24 | 需求包 Gate 标准 |

---

## 📋 执行计划 (Plans)

| 计划 | 日期 | 状态 |
|------|------|------|
| [architecture-upgrade-roadmap](plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md) | 2026-03-22 | 活跃 |
| [infrastructure-foundation-spec](plans/2026-03-22-openclaw-infrastructure-foundation-spec.md) | 2026-03-22 | 活跃 |
| [workflow-selection-runtime](plans/2026-03-22-workflow-selection-runtime-implementation-plan.md) | 2026-03-22 | 活跃 |
| [remaining-tasks-roadmap](plans/2026-03-25-remaining-tasks-and-execution-roadmap.md) | 2026-03-25 | 活跃 |
| *归档计划（6篇）* | — | [plans/archive/](plans/archive/) |

---

## 📎 模板 (Templates)

| 模板 | 用途 |
|------|------|
| [SOUL 全局短模板](templates/SOUL_GLOBAL_SHORT_TEMPLATE.md) | Agent SOUL.md 统一模板 |
| [SOUL 规划者深入触发模板](templates/SOUL_PLANNER_DEEPDIVE_LITE_TRIGGER_TEMPLATE.md) | 规划者深入分析触发 |
| [Tmux Codex UTF8 环境模板](templates/TMUX_CODEX_UTF8_ENV_TEMPLATE.md) | 远程 tmux 编码环境 |
| [DeepDive 英文模板](templates/deepdive-en.md) | 深入分析英文版 |
| [基础设施契约模板](templates/openclaw-foundation-contract-templates.md) | Foundation Contract |

---

## 📦 代码级文档（scripts 目录）

> 以下文档在各脚本目录内，与工作流 README 互相引用。

### HardFlow 核心（→ [ACP编码工作流](核心主工作流/ACP全链路编码工作流/README.md)）

| 文档 | 说明 |
|------|------|
| [`scripts/hardflow/README.md`](../scripts/hardflow/README.md) | HardFlow 完整文档（305行） |
| [`scripts/hardflow/SCORECARD_SCHEMA.md`](../scripts/hardflow/SCORECARD_SCHEMA.md) | 评分卡 Schema |
| [`scripts/hardflow/ISSUE_SCHEMA.md`](../scripts/hardflow/ISSUE_SCHEMA.md) | Issue Schema |
| [`scripts/hardflow/PROCESS_OPTIMIZATION.md`](../scripts/hardflow/PROCESS_OPTIMIZATION.md) | 流程优化记录 |
| [`scripts/hardflow/ROLLBACK.md`](../scripts/hardflow/ROLLBACK.md) | 回滚策略 |
| [评分系统升级 README](核心主工作流/ACP全链路编码工作流/评分系统升级/README.md) | 需求定义（9个子功能） |
| [评分系统升级 架构](核心主工作流/ACP全链路编码工作流/评分系统升级/architecture.md) | 混合评分管道设计 |
| [评分系统升级 实施](核心主工作流/ACP全链路编码工作流/评分系统升级/implementation-plan.md) | P0-P4 分阶实施计划 |

### 运营策略（→ [通用运营工作流](核心主工作流/通用运营工作流/README.md)）

| 文档 | 说明 |
|------|------|
| [`scripts/openclaw-ops/README.md`](../scripts/openclaw-ops/README.md) | 运营脚本总索引 |
| [`scripts/openclaw-ops/policy/README.md`](../scripts/openclaw-ops/policy/README.md) | Policy Enforcer 完整文档（263行） |
| [`scripts/openclaw-ops/CRON_TASK_INDEX.md`](../scripts/openclaw-ops/CRON_TASK_INDEX.md) | Cron 任务完整索引 |
| [`scripts/openclaw-ops/TODO_PATROL_POLICY_FLOW.md`](../scripts/openclaw-ops/TODO_PATROL_POLICY_FLOW.md) | TODO 巡检策略流程 |
| [`scripts/openclaw-ops/MODEL_TIER_SWITCH.md`](../scripts/openclaw-ops/MODEL_TIER_SWITCH.md) | 模型档位切换文档 |
| [`scripts/openclaw-ops/SETUP_WORKFLOW.md`](../scripts/openclaw-ops/SETUP_WORKFLOW.md) | 工作流安装文档 |
| [`scripts/openclaw-ops/RUNTIME_SKILLS.md`](../scripts/openclaw-ops/RUNTIME_SKILLS.md) | 运行时技能清单 |

---

## 📁 归档 (Archive)

`docs/archive/` — 18 篇历史文档（2026-03-04 ~ 2026-03-19），已归档不再活跃维护。

---

## 🔗 项目根目录文档

| 文件 | 说明 |
|------|------|
| [PROJECT_MEMORY_GUIDE.md](../PROJECT_MEMORY_GUIDE.md) | 项目记忆使用指南 |
| [done.md](../done.md) | 已完成功能清单 |
| [todo.md](../todo.md) | 待办事项 |

---

## 代码审计状态修正说明

经 2026-03-29 代码审计，以下工作流由用户规划标注的"开发中"修正为"已上线"：
- 🚀 **配置变更安全兜底**：`config_watchdog.py`（530行）+ Cron 每4小时
- 🚀 **统一异常日志巡检**：`unified_exception_logger.py`（18KB）+ Cron 每6小时
- 🚀 **MemTidy记忆整理**：`memtidy_runner.py`（518行）+ Cron 每日03:00

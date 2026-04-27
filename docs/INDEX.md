# OpenClaw 文档导航（INDEX）

> 最后更新：2026-04-27 | nofx agent/model 口径已修正为 2 个 Hermes profile（`openai-codex/gpt-5.5`）+ workflow owner 标签；14 Agent 文档仅保留为历史 OpenClaw 注册表快照
> 配套文件：[execution-roadmap.md](execution-roadmap.md)（路线图）、[todo.md](../todo.md)（待办）、[done.md](../done.md)（已完成）

---

## 📊 工作流全景图

| 工作流类型 | 工作流名称 | 状态 | 触发方式 | 核心能力 |
|------------|-----------|------|----------|----------|
| 🎯 核心主工作流 | [通用运营工作流](核心主工作流/通用运营工作流/README.md) | ✅ 已上线 | 人工/事件触发 | 任务调度、TODO巡检、日报、评分闭环 |
| 🎯 核心主工作流 | [ACP全链路编码工作流](核心主工作流/ACP全链路编码工作流/README.md) | ✅ 已上线 | 人工触发 | G0-G6门禁、回流整改、部署验收 |
| 🎯 核心主工作流 | [项目交付优先工作流](核心主工作流/项目交付优先工作流/README.md) | 🟡 Phase 6.3 已实现 | 人工触发 / 项目维护事件 / 运维事件 | 自动需求探索、项目记忆定位、编码执行、测试验收、代码审核、受控 Git 发布、Task Center 追踪、人工队列 |
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
| [部署与运维](基础设施/部署与运维/README.md) | Linux/Windows部署、Gateway守护、排障 | 8篇 |
| [多Agent体系](基础设施/多Agent体系/README.md) | 历史 14 Agent 注册表；nofx 当前为 2 个 Hermes profile + workflow owner 标签 | 1篇 |
| [协议与规范](基础设施/协议与规范/README.md) | trace_id、任务派发、错误进化、TG输出 | 4篇 |
| [记忆蒸馏](基础设施/记忆蒸馏/README.md) | 多源会话蒸馏、热记忆、技能候选 | 4篇 |
| [技能化架构](基础设施/技能化架构/README.md) | Skill 标准化、HardFlow 迁移、评分三步流水线 | 3篇 |
| [治理与审核](治理与审核/README.md) | Cron治理、升级方案、优化backlog、仓库精简巡检 | 7篇 |

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
| [项目级记忆模块](基础设施/项目记忆模块/README.md) | 项目记忆目录结构、注入策略、与蒸馏集成 |

---

## 📦 代码级文档（scripts 目录）

> 以下文档在各脚本目录内，与工作流 README 互相引用。

### 项目交付优先工作流（核心文档）

| 文档 | 说明 |
|------|------|
| [项目交付优先工作流 README](核心主工作流/项目交付优先工作流/README.md) | 需求定义与范围边界 |
| [项目交付优先工作流架构设计](核心主工作流/项目交付优先工作流/项目交付优先工作流架构设计.md) | 端到端编码流水线状态机、双 AI 审查、项目记忆定位、Task Center 控制面、runtime adapter、Git 发布门禁 |
| [项目交付优先工作流实施规划](核心主工作流/项目交付优先工作流/项目交付优先工作流实施规划.md) | Phase 1-6.5 分阶实施步骤 |
| [Smart Arb nofx live evidence bridge](核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md) | SmartMultiPlatformArbitrage Discord 需求入口、Hermes runtime、live 证据桥与 deployment 边界 |

### 端到端编码交付流水线 Skill

| 文档 | 说明 |
|------|------|
| [`skills/library/project-delivery-pipeline/SKILL.md`](../skills/library/project-delivery-pipeline/SKILL.md) | 项目交付优先编码流水线主入口 |
| [`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`](../skills/library/project-delivery-pipeline/scripts/pipeline_runner.py) | dry-run 状态机、项目记忆门禁、Task Center 镜像与 view 入口 |
| [`skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py`](../skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py) | Hermes profile 非 dry-run smoke 验收入口 |
| [`skills/library/project-delivery-pipeline/references/state-machine.md`](../skills/library/project-delivery-pipeline/references/state-machine.md) | 状态、产物、门禁、失败回退、Task Center 镜像规则 |
| [`skills/library/project-delivery-pipeline/references/runtime-adapter.md`](../skills/library/project-delivery-pipeline/references/runtime-adapter.md) | 通用 runtime 宿主、任务中心与检索后端适配契约 |
| [`skills/library/todo-patrol/scripts/deadline_to_task_bridge.py`](../skills/library/todo-patrol/scripts/deadline_to_task_bridge.py) | 到期 TODO 转 Task Center 候选任务，等待人工确认 |
| [`skills/library/log-monitor/scripts/exception_to_task_bridge.py`](../skills/library/log-monitor/scripts/exception_to_task_bridge.py) | 增量异常日志转运维任务与 incident |
| [`skills/library/control-plane-ops/scripts/policy/human_inbox.py`](../skills/library/control-plane-ops/scripts/policy/human_inbox.py) | 人工确认、拒绝、澄清、升级任务统一入口 |

### 双 AI 对抗审查 Skill

| 文档 | 说明 |
|------|------|
| [`skills/library/dual-ai-review/SKILL.md`](../skills/library/dual-ai-review/SKILL.md) | 双 AI 对抗审查主 Skill（覆盖需求/方案/代码三阶段） |
| [`skills/library/dual-ai-review/templates/requirements_review.md`](../skills/library/dual-ai-review/templates/requirements_review.md) | 需求审查输出模板 |
| [`skills/library/dual-ai-review/templates/solution_review.md`](../skills/library/dual-ai-review/templates/solution_review.md) | 方案审查输出模板 |
| [`skills/library/dual-ai-review/templates/code_review.md`](../skills/library/dual-ai-review/templates/code_review.md) | 代码审查输出模板 |
| [`skills/library/dual-ai-review/references/review-gate-contract.md`](../skills/library/dual-ai-review/references/review-gate-contract.md) | 对抗审查与 G0-G6 门禁映射契约 |
| [`skills/library/dual-ai-review/references/consensus-rules.md`](../skills/library/dual-ai-review/references/consensus-rules.md) | 双 AI 共识规则（3 轮上限、分歧上报、中止条件） |

### 失败学习回写 Skill

| 文档 | 说明 |
|------|------|
| [`skills/library/failure-learning/SKILL.md`](../skills/library/failure-learning/SKILL.md) | 失败学习回写主 Skill（根因分析、用户确认、文档回写） |
| [`skills/library/failure-learning/templates/failure_analysis.md`](../skills/library/failure-learning/templates/failure_analysis.md) | 失败分析报告模板 |

### 项目画像与 API 注册表 Skill

| 文档 | 说明 |
|------|------|
| [`skills/library/project-profile-manager/SKILL.md`](../skills/library/project-profile-manager/SKILL.md) | 项目画像管理 Skill（init/update/show/list） |
| [`skills/library/project-profile-manager/templates/PROJECT_PROFILE.md`](../skills/library/project-profile-manager/templates/PROJECT_PROFILE.md) | 项目画像模板 |
| [`skills/library/api-registry-manager/SKILL.md`](../skills/library/api-registry-manager/SKILL.md) | API 注册表管理 Skill（add/remove/list/check） |
| [`skills/library/api-registry-manager/templates/API_REGISTRY.json`](../skills/library/api-registry-manager/templates/API_REGISTRY.json) | API 注册表 JSON Schema 模板 |
| [`skills/library/api-registry-manager/templates/SOURCE_REGISTRY.json`](../skills/library/api-registry-manager/templates/SOURCE_REGISTRY.json) | 来源注册表 JSON Schema 模板 |

### HardFlow 核心（→ [ACP编码工作流](核心主工作流/ACP全链路编码工作流/README.md)）

| 文档 | 说明 |
|------|------|
| [`skills/openclaw-hardflow-automation/SKILL.md`](../skills/openclaw-hardflow-automation/SKILL.md) | **HardFlow Skill 操作手册（269行，v2.0）** |
| [`skills/.../scripts/`](../skills/openclaw-hardflow-automation/scripts/) | 7 个核心脚本（评分引擎/聚合器/策略/报告/门禁） |
| [`scripts/hardflow/README.md`](../scripts/hardflow/README.md) | HardFlow 旧版完整文档（305行） |
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
| [`skills/library/openclaw-workflow-manager/scripts/RUNTIME_SKILLS.md`](../skills/library/openclaw-workflow-manager/scripts/RUNTIME_SKILLS.md) | 运行时技能清单 |

---

## 🔬 研究参考

| 文档 | 日期 | 主题 |
|------|------|------|
| [Claude Code 源码还原研究](研究参考/claude-code-源码还原研究.md) | 2026-04-01 | 53 个工具、Coordinator 多 Agent 编排、KAIROS 持久助手、隐藏命令与环境变量、9 大 OpenClaw 改进项分析 |
| [4 项改进实施方案](研究参考/openclaw-4项改进实施方案.md) | 2026-04-01 | Dream 记忆蒸馏(含 Codex) + Gate 工具集限制 + Worker 自包含 Prompt + VerifyPlanExecution |
| [Harness 工程实战难点与借鉴](研究参考/harness-engineering-实战难点与借鉴.md) | — | Harness 平台工程经验 |
| [Multica Managed Agents 平台研究](研究参考/multica-managed-agents-平台研究.md) | 2026-04-23 | Web/daemon/agent runtime/skill/autopilot 架构评估，裁决为借鉴轻量机制、不迁移 OpenClaw 主链 |

---

## 📁 归档 (Archive)

`docs/archive/` — 18 篇历史文档（2026-03-04 ~ 2026-03-19），已归档不再活跃维护。

---

## 🔗 项目根目录文档

| 文件 | 说明 |
|------|------|
| [PROJECT_MEMORY_GUIDE.md](../PROJECT_MEMORY_GUIDE.md) | 项目记忆使用指南 |
| [memory/INDEX.md](../memory/INDEX.md) | 项目记忆入口、nofx runtime 排障边界与长期事实导航 |
| [done.md](../done.md) | 已完成功能清单 |
| [todo.md](../todo.md) | 待办事项 |

---

## 代码审计状态修正说明

经 2026-03-29 代码审计，以下工作流由用户规划标注的"开发中"修正为"已上线"：
- 🚀 **配置变更安全兜底**：`config_watchdog.py`（530行）+ Cron 每4小时
- 🚀 **统一异常日志巡检**：`unified_exception_logger.py`（21KB）+ Cron 每6小时 + `--auto-discover` 自动目录发现
- 🚀 **MemTidy记忆整理**：`memtidy_runner.py`（518行）+ Cron 每日03:00

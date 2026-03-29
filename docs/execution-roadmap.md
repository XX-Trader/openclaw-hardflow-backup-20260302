# OpenClaw 执行路线图（2026 Q2）

> 基于 2026-03-29 全量代码审计 + 10 条工作流盘点
> 配套文件：[todo.md](../todo.md)（待办）、[done.md](../done.md)（已完成）、[INDEX.md](INDEX.md)（文档导航）

---

## 📊 工作流成熟度矩阵

| 工作流类型 | 工作流 | 代码 | Cron | 文档 | 成熟度 |
|-----------|--------|------|------|------|--------|
| 🎯 核心 | 通用运营 | ✅ | ✅ 6个 | ✅ | ⭐⭐⭐⭐⭐ |
| 🎯 核心 | ACP全链路编码 | ✅ | N/A | ✅ | ⭐⭐⭐⭐⭐ |
| 📦 专项 | 巡检故障闭环 | ✅ | ✅ 2个 | ✅ | ⭐⭐⭐⭐ |
| 📦 专项 | 记忆知识沉淀 | ✅ | ✅ 4个 | ✅ | ⭐⭐⭐⭐ |
| 📦 专项 | 情报采集分析 | ✅ | ✅ 3个 | ✅ | ⭐⭐⭐⭐ |
| 📦 专项 | 自进化优化 | ✅ | ✅ 10个 | ✅ | ⭐⭐⭐⭐ |
| 📦 专项 | 任务成本统计 | 🔧 部分 | ❌ | ✅ | ⭐⭐ |
| 🚀 运维 | 配置变更安全兜底 | ✅ | ✅ 2个 | ✅ | ⭐⭐⭐⭐ |
| 🚀 运维 | 统一异常日志巡检 | ✅ | ✅ 1个 | ✅ | ⭐⭐⭐ |
| 🚀 运维 | MemTidy记忆整理 | ✅ | ✅ 1个 | ✅ | ⭐⭐⭐ |

---

## 阶段一～五：✅ 全部完成

> 详见 [done.md](../done.md) 完整记录

- **安全加固与清理**：密钥检测、冗余 Job 删除、废弃脚本清理
- **外部进化通道**：上游同步 / 网页情报 / GitHub 扫描 3 通道上线
- **异常巡检增强**：7类分类 + 路径校验 + 日志生命周期
- **自进化闭环补全**：advisor→TODO、config_diff_review、trace_id 全链路
- **高级自进化能力**：记忆→Skill 封装、错误驱动进化、截止时间检测

---

## 阶段六：推广与治理（进行中）

| # | 任务 | 状态 |
|---|------|------|
| 6.1 | nofx 全功能验收测试 | ✅ 已完成 |
| 6.2 | 推广到其余 4 台服务器 | ⏳ 放最后 |
| 6.3 | Lobster 仓库配置为 `external_readonly` | ⏳ 待执行 |
| 6.4 | 拆分 `policy_enforcer.py`（5970行） | ✅ 已完成 |
| 6.5 | Agent 模型配置同步 | ✅ 已完成 |

---

## 阶段七：工作流能力补全（规划中）

> 基于 2026-03-29 代码审计识别出的功能缺口

### 7.1 任务成本统计工作流补全（P2）

| 子任务 | 说明 | 预计工时 |
|--------|------|----------|
| 创建 `cost_report_generator.py` | 从 task_center.db 按日/周/月、Agent/模型维度汇总 | 4h |
| 注册 Cron Job | 每周一生成周报 | 0.5h |
| 成本预警阈值 | 单任务超阈值自动告警 | 2h |
| 模型 ROI 分析 | 对比不同模型性价比 | 3h |

### 7.2 运维保障增强（P3）

| 子任务 | 说明 | 预计工时 |
|--------|------|----------|
| config_watchdog 自动回滚 | 检测到破坏性变更时自动触发回滚 | 3h |
| MemTidy 摘要压缩增强 | 引入 AI 摘要替代前 N 行截断 | 4h |
| 异常日志→故障知识库联动 | exception_logger 结果自动入 fault_knowledge_base | 3h |

### 7.3 平台化能力（P3 长期）

| 子任务 | 说明 |
|--------|------|
| Workflow Scorecard 综合评分驱动优化 | `algo_micro_optimizer` 方案 B |
| 核心 registry JSON Schema 强校验 | 配置变更兜底的上层保障 |
| MetaClaw 跨次学习闭环 | `lesson_to_skill.py` |
| 外部 workflow/skill 下载市场 | 对外开放 |
| 多 workflow 负载均衡 | 环节裁剪策略 |

---

## 架构决策记录 (ADR)

| ADR | 日期 | 主题 |
|-----|------|------|
| [default-coding-workflow-profile](adr/2026-03-22-default-coding-workflow-profile.md) | 2026-03-22 | 默认编码工作流 Profile 设计 |
| [foundation-contract-standard](adr/2026-03-23-openclaw-foundation-contract-standard.md) | 2026-03-23 | OpenClaw 基础设施契约标准 |
| [requirement-package-gate-standard](adr/2026-03-24-requirement-package-gate-standard.md) | 2026-03-24 | 需求包 Gate 标准 |

## 执行计划 (Plans)

| 计划 | 日期 | 状态 |
|------|------|------|
| [architecture-upgrade-roadmap](plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md) | 2026-03-22 | 活跃 |
| [infrastructure-foundation-spec](plans/2026-03-22-openclaw-infrastructure-foundation-spec.md) | 2026-03-22 | 活跃 |
| [workflow-selection-runtime](plans/2026-03-22-workflow-selection-runtime-implementation-plan.md) | 2026-03-22 | 活跃 |
| [remaining-tasks-roadmap](plans/2026-03-25-remaining-tasks-and-execution-roadmap.md) | 2026-03-25 | 活跃 |
| *归档计划（6篇）* | — | [plans/archive/](plans/archive/) |

## 模板 (Templates)

| 模板 | 用途 |
|------|------|
| [SOUL 全局短模板](templates/SOUL_GLOBAL_SHORT_TEMPLATE.md) | Agent SOUL.md 统一模板 |
| [SOUL 规划者深入触发模板](templates/SOUL_PLANNER_DEEPDIVE_LITE_TRIGGER_TEMPLATE.md) | 规划者深入分析触发 |
| [Tmux Codex UTF8 环境模板](templates/TMUX_CODEX_UTF8_ENV_TEMPLATE.md) | 远程 tmux 编码环境 |
| [DeepDive 英文模板](templates/deepdive-en.md) | 深入分析英文版 |
| [基础设施契约模板](templates/openclaw-foundation-contract-templates.md) | Foundation Contract |

## 归档 (Archive)

> `docs/archive/` 包含 18 篇历史文档（2026-03-04 ~ 2026-03-19），已归档不再维护。
> 完整清单见 [docs/archive/](archive/) 目录。

---

## 管理规则

1. **每完成一项**：从 `todo.md` 移到 `done.md`
2. **每完成一个阶段**：更新本文件阶段状态
3. **新功能接入**：先在 INDEX.md 定位到所属工作流，在对应目录补文档
4. **风险分级执行**：低风险自动、高风险人工审核

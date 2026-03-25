---
name: openclaw-evolution-upgrader
description: Use when upgrading OpenClaw workflows, skills, hooks, agents, installer flows, or runtime architecture based on logs, scores, repeated failures, drift, or external workflow and skill patterns.
---

# OpenClaw Evolution Upgrader

将本技能视为 OpenClaw 的升级控制面，而不是日常运行中的执行器。
用它把“问题总结、评分、外部吸收、架构落点”收口成固定流程，避免每次都从零判断该改 workflow、skill、hook、agent 还是 installer。

## 何时使用

- 需要回答“这个低分或异常应该改哪一层、哪些文件”
- 需要升级 `workflow`、`skill`、`hook`、`agent`、`installer`、`runtime overlay`
- 需要根据日志、任务执行报告、review 报告做问题归因和评分
- 需要吸收网络上的 workflow / skill / agent pattern，再判断是否接入当前体系
- 需要回答“当前架构距离目标架构还差什么，下一步先补哪一层”

## 不适用场景

- 不直接替代 `task_executor_runner.py`、`governance_evolution_runner.py`、`self_evolution_todo.py` 去执行业务任务
- 不把运行时 `~/.openclaw/*` 视为首选修改入口；优先改仓库模板、installer、技能规范
- 不在缺少证据时直接宣布“这次升级更好了”；先保留为候选方案

## 固定入口

- `internal-feedback-upgrade`
  - 从日志、执行报告、闭环情况、重复失败里提炼问题并评分
- `external-pattern-upgrade`
  - 从外部 workflow / skill / agent pattern 中吸收可迁移做法
- `architecture-upgrade`
  - 判断当前问题属于哪一层，以及怎样把现有架构推进到更易升级的目标架构

## 使用流程

1. 先读取 `../openclaw-workflow-manager/references/workflow-map.md`，建立当前系统地图。
2. 再按诉求读取对应参考资料：
   - 内部反馈：`references/internal-feedback-upgrade.md`
   - 外部吸收：`references/external-pattern-upgrade.md`
   - 架构升级：`references/architecture-upgrade.md`
3. 优先收集结构化证据，再下结论：
   - executor runs
   - reviewer / governance / self-evolution 报告
   - runtime drift 迹象
   - 外部官方文档、官方仓库、设计说明
4. 将问题归因到固定分类：
   - `architecture_gap`
   - `workflow_gap`
   - `skill_gap`
   - `runtime_gap`
5. 先找“最小可写面”，再决定是否需要跨层修改。
6. 用 `assets/workflow-upgrade-scorecard-template.json` 或 `assets/skill-evolution-review-template.md` 产出结构化结论。
7. 输出时必须同时给出：
   - 证据来源
   - 当前问题分类
   - 建议修改落点
   - 不建议先改的地方
   - 验证与评分比较方法

## 可执行入口

- `../../../scripts/openclaw-ops/workflow_upgrade_scoring.py`
  - 把 baseline / candidate executor reports 转成 workflow scorecard
- `../../../scripts/openclaw-ops/skill_evolution_review.py`
  - 把 baseline / candidate executor reports 转成 skill review markdown
- `../../../scripts/openclaw-ops/upgrade_feedback_runner.py`
  - 自动从 executor runs 切 baseline / candidate，并一次性生成 scorecard/review/summary
- `../../../scripts/openclaw-ops/upgrade_analysis.py`
  - 统一提供报告装载、归因分类、评分与晋升判断

推荐把脚本产物继续沉淀回：

- `assets/workflow-upgrade-scorecard-template.json`
- `assets/skill-evolution-review-template.md`

## 输出契约

至少输出以下 6 段：

1. 当前问题摘要
2. 证据与评分依据
3. 归因分类
4. 最小可写面
5. 建议改动顺序
6. 验证与是否晋升为新基线

## 快速对照

| 诉求 | 优先入口 | 主要产物 |
| --- | --- | --- |
| 重复失败、低分、闭环差 | `references/internal-feedback-upgrade.md` | 归因 + scorecard |
| 网上找到新 workflow / 新 skill | `references/external-pattern-upgrade.md` | 外部 pattern 差异评估 |
| 想知道先改 workflow 还是 skill | `references/architecture-upgrade.md` | 升级层级与文件落点 |
| 想把结果沉淀为固定格式 | `assets/*.template` | 结构化评审资产 |

## 核心原则

- 先看地图，再改实现。
- 先看评分，再改细节。
- 先改仓库模板、规则、manifest，再考虑手改运行态。
- 先升级边界和接口，再升级具体 runner。
- 纯“改好了一点”的描述不算升级；必须能比较 `baseline` 与 `candidate`。

## 常见误区

- 把所有问题都归到 runner 上。很多问题真正应该改的是 skill 规范或 binding manifest。
- 把外部文章里的方案直接照搬到本仓。先做差异评估，再决定落在 skill、workflow 还是 hook。
- 看到运行态坏了就先改 `~/.openclaw/*`。优先回到 repo 模板、installer、overlay 源头。
- 把“这次没报错”当作升级成功。没有评分对比，只能算临时修补。

## 参考资料

- `../openclaw-workflow-manager/references/workflow-map.md`
- `../../../docs/plans/2026-03-21-openclaw-workflow-evolution-upgrade-design.md`
- `../../../docs/plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md`
- `../../../docs/plans/2026-03-13-workflow-architecture-manifesto.md`
- `../../../docs/2026-03-14-agent-skill-hook-绑定现状与优化清单.md`
- `references/internal-feedback-upgrade.md`
- `references/external-pattern-upgrade.md`
- `references/architecture-upgrade.md`

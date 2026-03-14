# 2026-03-14 文档导航：绑定、运行现状与外部模式学习

## 目的

把 2026-03-14 这一轮新增的“现状梳理 / 运行问题 / 方案设计 / 字段规范”文档串成一张导航图，避免同一主题散落在多份文件里难以回看。

## 阅读顺序

1. 先看绑定现状
   - [2026-03-14-agent-skill-hook-绑定现状与优化清单.md](./2026-03-14-agent-skill-hook-绑定现状与优化清单.md)
2. 再看运行快照
   - [2026-03-14-自我进化工作流问题记录.md](./2026-03-14-自我进化工作流问题记录.md)
3. 再看方案设计
   - [2026-03-14-external-pattern-learning-pipeline.md](./plans/2026-03-14-external-pattern-learning-pipeline.md)
4. 再看实施计划
   - [2026-03-14-agent-skill-hook-implementation-plan.md](./plans/2026-03-14-agent-skill-hook-implementation-plan.md)
5. 最后看数据契约
   - [2026-03-14-pattern-card-field-spec.md](./plans/2026-03-14-pattern-card-field-spec.md)

## 文档分工

| 文档 | 角色 | 真值等级 | 适用问题 |
| --- | --- | --- | --- |
| `2026-03-14-agent-skill-hook-绑定现状与优化清单.md` | 现状与问题总览 | 中 | 当前 agent / skill / hook / task 绑定关系是什么 |
| `2026-03-14-自我进化工作流问题记录.md` | 运行快照 | 低 | 某个时间点自我进化链路为什么不健康 |
| `2026-03-14-external-pattern-learning-pipeline.md` | 方案设计 | 中 | 外部模式学习能力应该怎么建设 |
| `2026-03-14-agent-skill-hook-implementation-plan.md` | 实施顺序 | 高 | 如果现在开始落地，先做什么，后做什么 |
| `2026-03-14-pattern-card-field-spec.md` | 数据契约 | 高 | `PatternCard` 的 JSON 结构和字段定义是什么 |
| `2026-03-13-workflow-architecture-manifesto.md` | 架构背景 | 高 | 调度清单、能力字段、系统边界的既有定义 |
| `integration/openclaw-bridge/*.md` | runtime bridge 契约 | 高 | overlay / 官方 surface / hooks / skills / plugin 的边界是什么 |

## 三层真值

### 运行时真值

- `openclaw/openclaw.json`
- `scripts/openclaw-ops/install_workflow_profile.py`
- `scripts/openclaw-ops/policy/task_executor_runner.py`

### 文档真值

- `PatternCard` 字段规范以 [2026-03-14-pattern-card-field-spec.md](./plans/2026-03-14-pattern-card-field-spec.md) 为准
- 调度清单字段以 [2026-03-13-workflow-architecture-manifesto.md](./plans/2026-03-13-workflow-architecture-manifesto.md) 为准

### 快照文档

以下文档属于时点记录，不应当被误读为长期真值：

- [2026-03-14-自我进化工作流问题记录.md](./2026-03-14-自我进化工作流问题记录.md)

## 维护规则

- 新增“运行问题记录”时，必须写清：
  - 观察时间
  - 观察范围
  - 数据来源
  - 复核命令
  - 时效性说明
- 新增“字段规范”时，必须明确唯一真值源，禁止多份文档重复定义同一组 JSON 键
- 新增“方案设计”时，必须显式说明它依赖哪份已有规范，不得隐式覆盖旧契约

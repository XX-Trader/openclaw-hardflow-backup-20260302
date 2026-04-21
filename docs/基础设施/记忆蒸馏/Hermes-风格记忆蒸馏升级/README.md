# Hermes 风格记忆蒸馏升级

> 所属：基础设施 / 记忆蒸馏 / Hermes 风格对齐
> 状态：🚧 Phase 1 已落地，后续阶段待实现
> 上级文档：[../README.md](../README.md)

## 1. 方案定位

本子功能不是"参考一点 Hermes 灵感"，而是：

> **在方法论与技术抽象层面，完整对齐 Hermes 的记忆、会话检索、技能化与上下文压缩设计，并把最终交付物收口为一个可同时运行在 Hermes / OpenClaw 的通用技能。**

核心含义：

- **方法层完全对齐 Hermes**
- **交付物不再是 OpenClaw 私有脚本，而是通用技能 + 宿主适配器**
- **运行态集成仍保留各宿主自己的 SSOT、安装器和控制面**

## 2. 关键裁决

### 2.1 新需求裁决

用户已明确新目标：

> 把蒸馏层做成一个通用技能，让在 IDE 中产生的大量编码经验，可被 Hermes 与 OpenClaw 共同消费，尤其反哺 OpenClaw 的能力。

本方案正式裁决：

- **主交付物**：跨宿主通用技能 `shared distillation skill`
- **Hermes**：作为一个宿主，直接调用该技能并读写自身热记忆/检索层
- **OpenClaw**：作为另一个宿主，调用同一技能，并把结构化产物继续喂给 `openclaw-evolution-upgrader`
- **IDE 经验**：视为第一现场，优先级高于 OpenClaw 自己的工作流噪音日志
- **解析执行单元**：统一复用宿主内 Agent；共享技能不在核心脚本里裸调模型
- **控制面桥接**：蒸馏结果除了进入记忆与检索层，还必须输出给 `task_center / executor-runs / upgrade-feedback` 既有控制面闭环

### 2.2 热记忆落点裁决

当前仓库内存在三个不完全一致的方向，本方案正式裁决：

| 层级 | 准入文件 | 说明 |
|------|---------|------|
| 热记忆层 | `workspace/USER.md` + `workspace/MEMORY.md` | 两套宿主统一遵循 Hermes 风格 |
| 经验层 | `.workflow/experience/` | 按主题聚合 |
| 决策层 | `docs/adr/` | 架构决策 |
| 技能层 | `skill drafts/` → 正式 `skills/` | 人工确认后安装 |
| 检索层 | 多源 session index | 不进入热注入 |
| 归档层 | 旧 `~/.openclaw/memory/` | 退为归档/兼容迁移角色，不再作为热注入首选 |

### 2.3 宿主内 Parser Agent 裁决

- **共享技能不在核心脚本里裸调模型**，而是把高价值候选窗口交给宿主内部 Agent 解析
- **解析 Agent 只产出结构化 artifact，不允许直接写 `USER.md` / `MEMORY.md`**
- 共享技能核心只负责：候选准备、解析 schema、结果校验、路由落盘

> 调度协议、输入输出 schema 和门禁规则详见 [架构设计文档](Hermes-风格记忆蒸馏升级架构设计.md) §3.2.7、§3.5。

## 3. Hermes 借鉴清单

| 编号 | Hermes 能力 | 对齐方式 | 状态 |
|------|-------------|----------|------|
| H1 | 双层持久记忆：`MEMORY.md` + `USER.md` | 拆分环境/项目事实与用户偏好 | ⬜ |
| H2 | 冻结快照注入 | 会话开始一次性注入，运行中写盘但不重拼前缀 | ⬜ |
| H3 | 受控记忆动作：`add/replace/remove` | 用结构化写入网关替代随意改文件 | ⬜ |
| H4 | Session Search 与长期记忆分层 | 多源会话进入检索层，长期记忆只留高价值摘要 | ⬜ |
| H5 | 技能是程序性记忆 | PATTERN 高频升级为 Skill draft，再人工激活 | ⬜ |
| H6 | 外部 Memory Provider 可插拔 | 保留宿主适配器 / provider adapter 扩展点 | ⬜ |
| H7 | 双层压缩与上下文摘要 | 复用 Hermes 风格结构化 summary 模板 | ⬜ |
| H8 | 稳定前缀缓存 | 写入和压缩都遵守"不频繁改系统前缀" | ⬜ |
| H9 | 安全扫描与容量预算 | 记忆写入前做注入/凭证/越权扫描 | ⬜ |
| H10 | 技能优先扩展 | 规则优先写入 Skill，而不是先造新 Tool | ⬜ |

## 4. 功能边界

### 4.1 本方案覆盖

- Claude Code / Gemini / Codex / OpenClaw / Hermes 会话采集与统一清洗
- IDE 侧高价值工件与代码变更证据采集
- `USER.md` / `MEMORY.md` 热记忆模型
- session search 检索层
- 经验卡片、ADR、skill draft 的落点
- 上下文压缩摘要模板与缓存边界
- OpenClaw 升级技能如何消费蒸馏证据
- Hermes / OpenClaw 如何共用同一套蒸馏核心

> 数据源矩阵（第一批/第二批详细列表、字段、优先级）、端到端数据链路（9 层）、存储分层策略（6 层）、领域对象定义等详见 [架构设计文档](Hermes-风格记忆蒸馏升级架构设计.md)。

### 4.2 本方案不覆盖

- 不直接复刻 Hermes 的 `state.db` schema
- 不把 `.hermes/` 当作 OpenClaw 的运行态事实源
- 不改写 `upgrade_feedback_runner.py` 的核心评分职责
- 不在本阶段替换现有 task-center / executor / installer 主链
- 不把"IDE 经验吸收"简化成只读 transcript；必须允许代码改动和验证结果作为辅助证据

## 5. 核心设计原则（摘要）

1. **热记忆必须极小而稳定**：长期注入内容必须可控，避免 prompt 膨胀。
2. **会话历史是检索层，不是注入层**：不把完整 transcript 当成记忆。
3. **写入必须结构化**：所有记忆更新都走显式动作，不允许自由文本乱追加。
4. **模式优先技能化**：重复成功流程先抽成 Skill，而不是继续依赖长记忆。
5. **IDE 第一现场原则**：蒸馏主链必须优先吸收 IDE 侧会话、工件、代码改动与验证证据。
6. **路径按宿主逐一探测**：禁止按当前进程 OS 一刀切。
7. **原始数据先落盘，后解析**：禁止边读边写热记忆。
8. **解析必须宿主内化**：共享技能只定义解析契约，真正执行解析的一定是宿主体系内的 Agent。

> 完整 12 条设计原则及每条的约束理由详见 [架构设计文档](Hermes-风格记忆蒸馏升级架构设计.md) §5。

## 6. 关键来源

### Hermes 官方文档

- [Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
- [Memory Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers)
- [Creating Skills](https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills/)
- [Context Compression and Caching](https://hermes-agent.nousresearch.com/docs/developer-guide/context-compression-and-caching/)
- [Configuration / Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/)

### 本仓现有文档

- [知识蒸馏引擎总览](../README.md)
- [知识蒸馏通用架构](../architecture.md)（冻结）
- [知识蒸馏通用实施计划](../implementation-plan.md)（冻结）
- [4 项改进实施方案](../../../研究参考/openclaw-4项改进实施方案.md)
- [架构升级路线图](../../../plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md)

## 7. 解封条件

本方案已经把"是否仿照 Hermes、仿照到哪一层、哪些旧设计要推翻"说清楚。
后续只有在以下条件都完成后，才允许进入代码实施：

1. 完成本目录架构设计与实施规划的审阅
2. 明确 `USER.md` / `MEMORY.md` / `session index` / `skill draft` 的 SSOT
3. 确认蒸馏层与升级控制面的边界不再冲突
4. 明确宿主内 Parser Agent Contract 与控制面桥接契约

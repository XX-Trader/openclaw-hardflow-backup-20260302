# OpenClaw 技能化架构

> 状态：✅ Phase 1-5 全部完成 | 创建时间：2026-04-01 | 更新：2026-04-27 | v3.0 脚本归并完成
> 父级：[INDEX.md](../../INDEX.md) | 分类：基础设施

## 一、需求背景

当前 OpenClaw 的能力散落在三个地方：
- **114 个 ops 脚本**（`~/.openclaw/ops/`）— 独立的 Python/Bash 脚本
- **23 个 Cron Job**（`jobs.json`）— 直接在 `payload.message` 中写 `python3 xxx.py`
- **51 个 Skill**（`~/.claude/skills/`）— SKILL.md 指导 LLM 操作

**核心问题**：脚本和 Cron Job 是"旧时代"的自建编排（自己写方法调 LLM），而 Skill 是现代 LLM 原生能力。需要统一为 **Skill 驱动模式**。

## 二、Skill 的本职定位（对标 Claude Code 官方 + ClawHub）

**Skill = 指导 LLM 如何完成特定任务的操作手册**。仅此而已。

| Skill 负责 | Skill 不负责（OpenClaw 平台管） |
|-----------|-------------------------------|
| 操作步骤和决策树 | Agent 调度和路由 |
| 约束和红线 | 模型选择和 API 凭证 |
| 可执行脚本（scripts/） | 频道推送（Telegram/微信） |
| 评分标准和产出物规范 | 定时任务注册（Cron）|
| | Agent-Skill 绑定关系 |

**frontmatter 极简**，仅 `name` / `description` / `allowed-tools`。

## 三、设计目标

**Skill = 一个功能的集合**，包含：
1. **SKILL.md** — LLM 操作手册（frontmatter 元数据 + 决策树 + 操作步骤）
2. **scripts/** — 可执行脚本（被 LLM 通过 `run_command` 调用）

**调度和配置在 OpenClaw 平台层**：
- Agent 绑定：`agent_capability_manifest.json` 的 `declared_skills`
- Cron 绑定：`jobs.json` 新增 `skill_ref` 字段引用 Skill
- 模型/频道：OpenClaw 环境配置注入

## 四、子功能清单与验收状态

| # | 子功能 | 优先级 | 验收标准 | 状态 |
|---|--------|--------|---------|------|
| 1 | Skill 标准结构规范 | P0 | frontmatter 对标官方（name/description/allowed-tools） | [x] |
| 2 | Agent-Skill 绑定 | P0 | `declared_skills` 声明 Skill，Agent 执行时自动加载 | [x] |
| 3 | Cron-Skill 绑定 | P0 | `jobs.json` 21 个 Job 全部添加 `skill_ref` | [x] |
| 4 | HardFlow 技能化迁移 | P0 | 工作流编排从 Bash 迁移到 SKILL.md 操作手册 | [x] |
| 5 | 控制面运维技能化 | P1 | 控制面 19 个脚本 + 10 子目录整合为 `control-plane-ops` Skill | [x] |
| 6 | Git 同步技能化 | P1 | 同步/备份 3 个脚本整合为 `git-sync` Skill | [x] |
| 7 | 多服务器同步技能化 | P1 | 13 个同步脚本整合为 `fleet-sync` Skill | [x] |
| 8 | 全量 ops 脚本迁移 | P2 | 16 个能力域全部完成技能化 | [x] |
| 9 | Cron 统一治理引擎 | P2 | 21 个 Job 全部 skill_ref 绑定 | [x] |
| 10 | 脚本归并到 Skill | P0 | 98 个脚本 + 13 目录归并为自包含 Skill | [x] |

## 五、约束与边界

- **不新增 Agent**：技能化不改变 2026-03 OpenClaw 历史注册表，只改 Skill 内容；runtime-host 当前运行态不按 14 个常驻 Agent 管理，而是两个 Hermes profile 承载 workflow owner / cron 责任标签
- **不改评分管道**：三步流水线（证据→评价→确定性聚合）保持不变
- **渐进式迁移**：新旧并行，逐步替换，不一次性切换
- **向下兼容**：旧的 `python3 xxx.py` 命令仍可直接执行

## 六、关联文档

| 文档 | 类型 | 路径 |
|------|------|------|
| 架构设计 | 架构 | [architecture.md](architecture.md) |
| 实施计划 | 实施 | [implementation-plan.md](implementation-plan.md) |

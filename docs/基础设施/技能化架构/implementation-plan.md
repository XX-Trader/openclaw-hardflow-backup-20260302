# OpenClaw 技能化架构 — 实施计划

> 版本：v2.0 | 2026-04-01
> 需求文档：[README.md](README.md) | 架构文档：[architecture.md](architecture.md)
> v2.0 修正：移除 Skill 层的编排设计，回归官方规范

---

## Phase 1：标准对齐（P0，✅ 已完成）

### Step 1.1 — SKILL.md 规范对标官方

frontmatter 仅保留：
```yaml
---
name: skill-name
description: 一句话描述 + 触发场景
allowed-tools: Bash, Read, Grep
---
```

### Step 1.2 — jobs.json 新增 skill_ref 支持

在 `jobs.json` 的 Job 条目中新增：
```json
{
  "name": "control_plane_dashboard",
  "skill_ref": "control-plane-ops",
  "mode": "direct",
  "on_failure": "llm",
  "max_retry": 2
}
```

- `skill_ref`：引用 Skill 名称，执行引擎去找对应 SKILL.md
- `mode`：`direct`（直接执行脚本）或 `llm`（启动 Agent 读 SKILL.md）
- `on_failure`：direct 失败后升级为 llm 分析
- 定时任务配置留在 jobs.json，不进 Skill

### Step 1.3 — agent_capability_manifest.json 补充 declared_skills

确保每个 Agent 的 `declared_skills` 正确引用其需要的 Skill 名称（已有机制，只需补全）。

---

## Phase 2：试点迁移 — HardFlow（P0，✅ 已完成）

### Step 2.1 — 重写 HardFlow SKILL.md ✅

- 54 行速查卡 → 200+ 行 LLM 操作手册
- frontmatter 对标官方（name/description/allowed-tools）
- 正文包含：任务分类决策树、各 Gate 操作步骤、评分三步流水线、约束红线

### Step 2.2 — 实现评分系统 P0 ✅

- 新建 `scripts/score-aggregator.sh`（确定性聚合，无 LLM）
- 确保 tester 输出结构化 evidence/ JSON
- 确保 reviewer 读 evidence/ 多维度评价

### Step 2.3 — 删除 Bash 编排层 ⚠️ 待手动

- 删除 `hardflow-run.sh` 等 7 个 Bash 脚本
- 保留 `check-score-gate.mjs`（移入 scripts/）

### Step 2.4 — 验证三条调用路径

- Agent 调用：coordinator 读 SKILL.md → 执行 Gate 流程
- Cron 调用：jobs.json skill_ref → 按 mode 执行
- 人工调用：`/hardflow` → LLM 引导

---

## Phase 3：批量迁移（P1-P2，后面做）

### 批次 A — P1 高价值域

| 能力域 | Skill 名称 | 包含脚本数 |
|--------|-----------|:---------:|
| 控制面运维 | `control-plane-ops` | 10 |
| 自进化引擎 | `self-evolution` | 4 |
| 日志巡检 | `log-monitor` | 2 |
| Git 同步与备份 | `git-sync` | 5 |

### 批次 B — P1 外部能力

| 能力域 | Skill 名称 | 包含脚本数 |
|--------|-----------|:---------:|
| Web 情报 | `web-intelligence` | 4 |
| GitHub/外部进化 | `external-evolution` | 3 |
| 多服务器同步 | `fleet-sync` | 9 |

### 批次 C — P2 剩余域

其余 9 个能力域逐步迁移。

### 每个 Skill 的迁移步骤

```
1. 在 ~/.claude/skills/<skill-name>/ 下创建目录
2. 编写 SKILL.md（frontmatter 极简 + 操作手册）
3. 将相关脚本移入 scripts/
4. 更新 agent_capability_manifest.json declared_skills
5. 更新 jobs.json 相关 Job 添加 skill_ref
6. 验证三条调用路径
```

---

## Phase 4：治理（P2，长期做）

### Step 4.1 — 统一 Cron 管理

- jobs.json 所有 Job 都通过 skill_ref 引用 Skill
- 消除直接写 `python3 xxx.py` 的旧模式

### Step 4.2 — 废弃旧安装器

- 废弃 `cron_setup.py`（3819 行）
- 废弃 `install_*_job.py` × 10

### Step 4.3 — Gateway 工具集硬限制

- 按 SKILL.md 正文中的约束，在 Gateway 层强制工具白名单
- 需要修改 Gateway 代码

---

## 验证计划

### 自动化验证

1. SKILL.md frontmatter 合法性校验
2. Agent `declared_skills` 引用的 Skill 目录存在性校验
3. `jobs.json` 的 `skill_ref` 与 Skill 目录存在性校验

### 手动验证

1. HardFlow 试点：完整 Gate 流程端到端
2. 控制面试点：Cron direct 模式 → 脚本执行 → 失败升级 llm
3. 新服务器部署：部署 Skill 目录 → 更新 manifest → Cron 自动关联

---

## 里程碑

| 里程碑 | 内容 | 预计完成 |
|--------|------|---------|
| M1 | Phase 1 标准对齐 + Phase 2 HardFlow 试点 | 1 周 |
| M2 | Phase 3 批次 A（控制面/自进化/日志/Git） | 2 周 |
| M3 | Phase 3 批次 B+C（全量迁移） | 3 周 |
| M4 | Phase 4 治理 + 废弃旧安装器 | 4 周 |

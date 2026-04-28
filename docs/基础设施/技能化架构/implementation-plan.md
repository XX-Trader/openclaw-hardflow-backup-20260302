# OpenClaw 技能化架构 — 实施计划

> 版本：v3.0 | 2026-04-02
> 需求文档：[README.md](README.md) | 架构文档：[architecture.md](architecture.md)
> v3.0 更新：Phase 1-5 全部完成，更新最终目录结构

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

### Step 1.2 — jobs.json 新增 skill_ref 支持 ✅

所有 21 个 Job 已添加 `skill_ref` 字段。

### Step 1.3 — agent_capability_manifest.json 补充 declared_skills ✅

coordinator、reviewer、ops-agent 已绑定对应 Skill。

---

## Phase 2：试点迁移 — HardFlow（P0，✅ 已完成）

### Step 2.1 — 重写 HardFlow SKILL.md ✅
- 54 行速查卡 → 269 行 LLM 操作手册
- frontmatter 对标官方（name/description/allowed-tools）

### Step 2.2 — 实现评分系统 ✅
- `score-aggregator.sh`（确定性聚合，无 LLM）
- `check-score-gate.mjs`、`hook-selftest.mjs`、`process-optimize.mjs`

### Step 2.3 — 删除 Bash 编排层 ✅
- 14 个旧 .sh 脚本全部删除（`hardflow-run.sh` 等）
- `scripts/hardflow/` 目录已物理删除

### Step 2.4 — 验证三条调用路径
- Agent 调用：coordinator 读 SKILL.md → 执行 Gate 流程
- Cron 调用：jobs.json skill_ref → 按 mode 执行
- 人工调用：`/hardflow` → LLM 引导

---

## Phase 3：批量迁移（P1，✅ 已完成）

### Phase 3A — 现有 Skill frontmatter 修正 ✅
- `openclaw-workflow-manager`：移除 triggers/version/description_zh
- `openclaw-security-audit`：移除 description_zh

### Phase 3B — 新建 9 个运维 Skill ✅

> 2026-04-28 更新：`memtidy` 已退役并删除实现，记忆文件生命周期交给 Hermes 原生能力承接；下表保留当前仍可调度的运维 skill。

| Skill | 能力域 |
|-------|--------|
| `control-plane-ops` | 控制面运维（系统巡检/Agent审查/Cron诊断）|
| `log-monitor` | 异常日志扫描/分类/增量去重 |
| `config-watchdog` | 配置快照/变更检测/回滚 |
| `git-sync` | 本地备份/远程同步 |
| `todo-patrol` | TODO巡检/过期检测/归档 |
| `web-intelligence` | GitHub扫描/网页情报/外部评估 |
| `fleet-sync` | 多服务器配置分发/状态对比 |
| `task-cost-analytics` | Token统计/成本分析 |

---

## Phase 4：治理层（P1，✅ 已完成）

### Step 4.1 — jobs.json 全部 skill_ref ✅
21 个 Cron Job 已全部添加 `skill_ref` 字段。

### Step 4.2 — 废弃旧安装器 ✅
- `cron_setup.py` + 10 个 `install_*_job.py` 已删除
- `deploy-hardflow-automation.ps1` 已删除

---

## Phase 5：脚本归并 — 自包含 Skill（P0，✅ 已完成）

**核心原则**：Skill = SKILL.md 操作手册 + scripts/ 实现代码

### 迁移结果

| Skill | 归入脚本数 | 子目录数 |
|-------|-----------|---------|
| control-plane-ops | 19 | 10 (含 policy/) |
| openclaw-workflow-manager | 25 | 2 dirs |
| fleet-sync | 13 | — |
| openclaw-evolution-upgrader | 10 | — |
| web-intelligence | 6 | — |
| todo-patrol | 4 | — |
| openclaw-security-audit | 4 | — |
| git-sync | 3 | — |
| task-cost-analytics | 3 | — |
| receiving-code-review | 2 | — |
| log-monitor | 2 | — |
| config-watchdog | 1 | — |
| shared/ (跨Skill公用) | 5 | — |

### 最终目录结构

```
skills/
├── README.md                              ← 单入口总索引
├── openclaw-hardflow-automation/
│   ├── SKILL.md
│   ├── scripts/ (10 files)
│   └── docs/ (7 files)
└── library/
    ├── control-plane-ops/scripts/         ← 19 files + 10 dirs
    ├── openclaw-workflow-manager/scripts/  ← 25 files + 2 dirs
    ├── fleet-sync/scripts/                ← 13 files
    ├── openclaw-evolution-upgrader/scripts/ ← 10 files
    ├── web-intelligence/scripts/          ← 6 files
    ├── todo-patrol/scripts/               ← 4 files
    ├── openclaw-security-audit/scripts/   ← 4 files
    ├── git-sync/scripts/                  ← 3 files
    ├── task-cost-analytics/scripts/       ← 3 files
    ├── receiving-code-review/scripts/     ← 2 files
    ├── log-monitor/scripts/               ← 2 files
    └── config-watchdog/scripts/           ← 1 file

scripts/openclaw-ops/
├── README.md
├── CRON_TASK_INDEX.md
├── RELEASE_VERSION
└── shared/ (5 个跨 Skill 公共工具)
```

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

| 里程碑 | 内容 | 完成时间 |
|--------|------|---------|
| M1 | Phase 1 标准对齐 + Phase 2 HardFlow 试点 | 2026-04-01 ✅ |
| M2 | Phase 3 批量创建 16 能力域 Skill | 2026-04-01 ✅ |
| M3 | Phase 4 治理 + 废弃旧安装器 | 2026-04-02 ✅ |
| M4 | Phase 5 脚本归并（自包含 Skill）| 2026-04-02 ✅ |
| M5 | 远程服务器部署 + 端到端验证 | 待执行 |
| M6 | Phase 6 Agent-Skill 绑定全面补齐 | 2026-04-02 ✅ |

---

## Phase 6：Agent-Skill 绑定全面补齐（P0，✅ 已完成）

> 打通三大执行管道（人工触发→Agent协作、HardFlow门禁、Cron自动巡检修复）与技能的连接。

### Step 6.1 — SOUL.md 技能声明 ✅

历史步骤曾为 6 个空绑定 Agent 补充 `## 技能主线` 段落；2026-04-27 起 nofx 当前 active 口径以 `docs/基础设施/多Agent体系/README.md` 为准，不再把 `agent-factory` / `explorer` 注册为 active owner：

| Agent | 技能数 | 绑定内容 |
|-------|:------:|---------|
| `ops-agent` | 6 | control-plane-ops, log-monitor, config-watchdog, fleet-sync, todo-patrol, task-cost-analytics |
| `optimization-agent` | 4 | openclaw-evolution-upgrader, openclaw-workflow-manager, task-cost-analytics, workflow-audit |
| `project-agent` | 3 | product-requirements, requirements-clarity, writing-plans |
| `web-agent` | 3 | web-intelligence, pretext-text-layout, playwright-interactive |

### Step 6.2 — 索引文件四方同步 ✅

- `agent_to_skills.json`：历史 OpenClaw 注册表 14 个 Agent 全覆盖（无空数组）；不作为 nofx 当前 Hermes runtime 的常驻 agent 数量依据
- `skill_to_agents.json`：反向补齐 + 新增条目
- `skills_by_domain.json`：历史上新增 `ops_infra`（8技能）和 `intelligence`（2技能）域；2026-04-28 起 `memtidy` 不再属于当前可调度 ops_infra 能力
- `skills/by_agent/`：历史 2026-03 技能索引保留作参考；nofx 当前 active owner 不包含 `explorer`

### Step 6.3 — README 速查表 ✅

`skills/README.md` 底部速查表从 6 行扩展到 14 行全覆盖。

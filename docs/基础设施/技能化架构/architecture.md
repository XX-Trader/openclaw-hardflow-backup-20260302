# OpenClaw 技能化架构设计

> 版本：v3.0 | 2026-04-02
> 需求文档：[README.md](README.md)
> v2.0 对标 Claude Code 官方 + ClawHub 规范，Skill 回归本职
> v3.0 新增：执行模式分层、记忆体系、自进化闭环、权限隔离

## 1. 核心定位修正

### Skill 是什么

**Skill = 指导 LLM 如何完成特定任务的操作手册**。

Skill 只需要做好一件事：当 LLM 面对特定类型的任务时，提供清晰的操作步骤、决策树和约束条件。

### Skill 不负责什么

| 职责 | 归属 | 不是 Skill 的事 |
|------|------|----------------|
| Agent 调度和路由 | OpenClaw Coordinator | ❌ Skill 不管"谁来执行" |
| 模型选择和 API Key | OpenClaw 环境配置 | ❌ Skill 不管"用哪个模型" |
| 频道推送（Telegram/微信） | OpenClaw delivery 机制 | ❌ Skill 不管"在哪推送" |
| 定时任务注册 | OpenClaw jobs.json | ❌ Skill 不管"什么时候执行" |
| Agent-Skill 绑定 | agent_capability_manifest.json | ❌ Skill 不需要知道谁用它 |

### 对标 Claude Code 官方规范

```yaml
# Claude Code 官方 Skill frontmatter（极简）
---
name: my-skill
description: What this skill does. Use when...
allowed-tools: Bash, Read, Grep
---
```

**只有 3 个字段**。没有 agents、没有 cron、没有 delivery。

## 2. 架构分层

```
┌─────────────────────────────────────────────────┐
│ OpenClaw 平台层（调度 + 配置 + 推送）              │
│                                                 │
│  ┌──────────────────────┐  ┌────────────────┐   │
│  │ agent_capability_    │  │ jobs.json      │   │
│  │ manifest.json        │  │ (Cron 注册)    │   │
│  │ - declared_skills    │  │ - skill_ref    │   │
│  │ - capability_modes   │  │ - schedule     │   │
│  └───────┬──────────────┘  │ - mode         │   │
│          │                 │ - delivery     │   │
│  ┌───────▼──────────────┐  └────────────────┘   │
│  │ OpenClaw 环境        │                       │
│  │ - 模型选择           │                       │
│  │ - API 凭证           │                       │
│  │ - 频道推送           │                       │
│  │ - 任务执行引擎       │                       │
│  └──────────────────────┘                       │
└──────────────────┬──────────────────────────────┘
                   │ LLM 读取
┌──────────────────▼──────────────────────────────┐
│ Skill 层（纯指令，无编排逻辑）                     │
│                                                 │
│  ┌────────────────────────────────────────────┐  │
│  │ SKILL.md                                   │  │
│  │                                            │  │
│  │ ---                                        │  │
│  │ name: hardflow                             │  │
│  │ description: HardFlow 多门禁工作流...       │  │
│  │ allowed-tools: Bash, Read, Write           │  │
│  │ ---                                        │  │
│  │                                            │  │
│  │ # 操作手册                                  │  │
│  │ ## 1. 决策树（遇到什么任务走哪条路）          │  │
│  │ ## 2. 操作步骤（每个 Gate 怎么做）           │  │
│  │ ## 3. 评分流程（证据->评价->聚合）           │  │
│  │ ## 4. 约束与红线                            │  │
│  └────────────────────────────────────────────┘  │
│                                                 │
│  scripts/                                       │
│  ├── score-aggregator.sh    (确定性脚本)         │
│  └── check-score-gate.mjs   (阈值校验)          │
└─────────────────────────────────────────────────┘
```

## 3. Skill 标准结构

```
skills/
└── openclaw-hardflow-automation/
    ├── SKILL.md            # 唯一配置 + 操作手册
    ├── scripts/            # 可选：确定性脚本
    │   ├── score-aggregator.sh
    │   └── check-score-gate.mjs
    ├── rubrics/            # 可选：附属资源（评分标准等）
    └── examples/           # 可选：示例
```

## 4. SKILL.md 规范（对标官方）

```yaml
---
name: openclaw-hardflow-automation
description: >
  HardFlow 多门禁质量工作流。用于前端/后端功能开发的多阶段质量门禁，
  包含需求分析(G0)、方案设计(G1)、编码实现(G2-G3)、审查(G4)、
  发布(G5)、验收(G6)。当 coordinator 分配编码任务时自动触发。
allowed-tools: Bash, Read, Write, Grep, WebBrowser
---

# HardFlow 多门禁工作流 — 操作手册

## 1. 任务分类决策树

判断当前任务属于哪种类型，决定走哪些 Gate：

| 任务类型 | 必经 Gate | 可选 Gate |
|---------|----------|----------|
| 纯前端 UI | G0 → G2 → G4 → G6 | G5(部署) |
| 前后端联动 | G0 → G1 → G2 → G3 → G4 → G6 | G5 |
| Bug 修复 | G0 → G2 → G4 | - |
| 文档更新 | G0 → G2 | - |

## 2. 各 Gate 操作步骤

### G0 — 需求分析
- 理解任务目标和验收标准
- ...

### G4 — 代码审查
- 阅读所有变更文件
- 检查命名规范、错误处理、安全防御
- ...

## 3. 评分三步流水线

### 步骤 1：证据收集
tester 执行测试，将结构化证据输出到 evidence/ 目录...

### 步骤 2：独立评价
reviewer 基于 evidence/ 进行多维度评分...

### 步骤 3：确定性聚合
执行 score-aggregator.sh，读取 evidence/，计算加权总分...

## 4. 约束与红线
- 评分聚合脚本（score-aggregator.sh）禁止使用 LLM
- reviewer 不能修改源代码，只读 + 浏览器截图
- ...
```

## 5. 谁调用 Skill —— 在 OpenClaw 平台层解决

### 5.1 Agent 调用 Skill（已有机制）

```json
// agent_capability_manifest.json（OpenClaw 平台配置）
{
  "agent_id": "coordinator",
  "declared_skills": ["openclaw-hardflow-automation", "control-plane-ops", ...]
}
```

Agent 在 `declared_skills` 里看到技能名 → 读 SKILL.md → 按指令操作。
**Skill 不需要反向声明 "agents" 字段**。

### 5.2 Cron 调用 Skill（在 jobs.json 中配置）

```json
// jobs.json（OpenClaw 平台配置）
{
  "name": "control_plane_dashboard",
  "skill_ref": "control-plane-ops",
  "mode": "direct",
  "schedule": { "expr": "0 */1 * * *" },
  "on_failure": "llm",
  "max_retry": 2,
  "delivery": { "channel": "telegram", "on_success": "silent" }
}
```

Cron 配置在 OpenClaw 层（`jobs.json`），不在 Skill 里。
`skill_ref` 只是告诉执行引擎"去读哪个 Skill"。

### 5.3 人工调用 Skill

```
用户: /hardflow   或   "使用 hardflow 技能"
→ LLM 匹配 description → 读 SKILL.md → 按操作手册执行
```

## 6. Cron direct/llm 两种模式（在 OpenClaw 层配置）

| 模式 | 配置在 | 执行流 |
|------|--------|--------|
| `direct` | jobs.json | Cron → 直接执行脚本 → 退出码判断 → 失败可升级 llm |
| `llm` | jobs.json | Cron → 启动 Agent → 读 SKILL.md → 执行 + 分析 |

**输出检查不需要额外任务**：
- `direct`：退出码判断 + `on_failure: llm` 自动升级
- `llm`：Agent 本身就在分析输出
- 趋势分析：由 control-plane-ops Skill 的 dashboard 负责

## 7. 与评分三步流水线的关系（不变）

```
HardFlow Skill (SKILL.md 描述操作流程)
├── Gate 流程决策 ← SKILL.md 指导 LLM
├── 证据收集 ← tester Agent（平台调度）
├── 独立评价 ← reviewer Agent（含浏览器截图）
├── 确定性聚合 ← score-aggregator.sh（Skill 内脚本）
└── 阈值校验 ← check-score-gate.mjs（Skill 内脚本）
```

## 8. Gate 工具集限制

通过 SKILL.md 正文中的自然语言约束告诉 LLM：

```markdown
## 约束与红线
- G0 阶段：只读操作，不能修改代码文件
- G1 阶段：只能写 docs/ 目录下的文档
- G4 阶段：reviewer 只读源码 + 浏览器截图，不能改代码
```

**不在 frontmatter 里加 gate_tool_policy 字段**——这不是官方规范支持的字段。
用自然语言约束 LLM 已经足够（软限制），硬限制未来在 Gateway 层做。

## 9. 优先级分层

### 现在做（Phase 1-2）

| 项目 | 说明 |
|------|------|
| 按官方规范重写 HardFlow SKILL.md | frontmatter 极简 + 操作手册 |
| 评分系统 P0（score-aggregator） | 解封评分管道 |
| jobs.json 新增 skill_ref 字段 | Cron 引用 Skill |
| 验证 3 条调用路径 | Agent / Cron / 人工 |

### 后面做（Phase 3）

| 项目 | 说明 |
|------|------|
| 16 能力域批量整合为 Skill | 逐步替换 |
| 控制面脚本适配 | 等试点稳定后 |

### 长期做（Phase 4）

| 项目 | 说明 |
|------|------|
| 治理引擎 | 扫描 Skill → 自动管理 |
| 废弃旧安装器 | 新旧并行后退役 |
| Gateway 硬限制工具集 | 需改 Gateway 代码 |

## 10. 迁移路径

```
Phase 1: 标准对齐（现在做）
  → SKILL.md frontmatter 对标官方（name/description/allowed-tools）
  → jobs.json 新增 skill_ref + mode 字段
  → agent_capability_manifest.json 补充 declared_skills

Phase 2: 试点 HardFlow（现在做）
  → 按官方规范重写 SKILL.md（操作手册 + 决策树）
  → 实现 score-aggregator.sh
  → 验证 3 条调用路径
  → 删除 Bash 编排层

Phase 3: 批量迁移（后面做）
  → 16 能力域分批整合
  → 每个 Skill: SKILL.md + scripts/

Phase 4: 治理（长期做）
  → 统一 Cron 管理
  → 废弃 cron_setup.py
  → Gateway 工具集硬限制
```

## 11. 执行模式分层 — 脚本先行 / LLM 兜底自愈

### 11.1 核心原则

**脚本是哨兵，LLM 是指挥官** — 哨兵没报警，指挥官不出动。

所有定时任务和运维技能分为三个执行级别：

| 级别 | 标识 | 触发方式 | LLM 消耗 |
|------|------|---------|---------|
| 🟢 LLM-FREE | `execution-mode: script` | 纯脚本执行，exit 0 静默完成 | 0 Token |
| 🟡 LLM-LIGHT | `execution-mode: llm-light` | 脚本为主，LLM 可增强解读 | 按需 |
| 🔴 LLM-HEAVY | `execution-mode: llm-heavy` | 核心推理依赖 LLM | 每次消耗 |

### 11.2 脚本先行 + 失败自动升级

```
脚本运行
  │
  ├── exit 0 ──→ ✅ 静默完成（0 Token）
  │
  └── exit ≠ 0 ──→ 🧠 自动升级为 Agent 会话
                    │
                    ├── 1. 读取 stderr/日志 → 诊断根因
                    ├── 2. 执行修复（如 git 冲突 → 智能合并）
                    ├── 3. 记录修复经验到记忆层
                    └── 4. 必要时修补脚本本身
```

### 11.3 SKILL.md frontmatter 扩展

```yaml
---
name: config-watchdog
description: 配置变更安全兜底技能...
allowed-tools: Bash, Read, Grep
execution-mode: script     # script | llm-light | llm-heavy
---
```

### 11.4 当前 Cron 任务执行模式分布

| 级别 | 数量 | 占比 | 代表任务 |
|------|:----:|:----:|---------|
| 🟢 LLM-FREE | 13 | 81% | todo_patrol、git_backup、auto_update |
| 🟡 LLM-LIGHT | 1 | 6% | governance_evolution |
| 🔴 LLM-HEAVY | 2 | 12% | reviewer 代码审查 |

**81% 的 Cron 任务可脱离 LLM 独立运行。**

### 11.5 LLM 介入后的三层价值

1. **完成任务** — 解决异常，让流程继续
2. **记录经验** — 修复过程沉淀到记忆层，下次直接复用
3. **修复根因** — 如果发现是脚本 bug，可建单让编码 Agent 修复

---

## 12. 记忆分层体系 — 复用 OpenClaw 内置记忆

### 12.1 五层记忆架构

不依赖任何单一外部工具（如 MCP Memory），优先复用 OpenClaw 内置机制：

```
┌─────────────────────────────────────────────┐
│ L1 短期记忆 — Agent 会话记录（原始素材）      │
│ 位置: ~/.openclaw/agents/*/sessions/         │
│ 生命周期: 7-30天自动清理                      │
├─────────────────────────────────────────────┤
│ L2 工作记忆 — 结构化事实（可直接引用）        │
│ 位置: MEMORY.md / openclaw-memory/            │
│ 内容: 项目路径、服务端口、SSH别名、常用命令    │
├─────────────────────────────────────────────┤
│ L3 经验记忆 — 方法论沉淀（可复用的模式）      │
│ 位置: .workflow/experience/                   │
│ 内容: "git冲突这样合并最稳" "OOM排查查这3项"  │
├─────────────────────────────────────────────┤
│ L4 技能记忆 — 固化为可执行技能（最高复用）    │
│ 位置: skills/library/                         │
│ 触发: 同一操作流程出现≥3次 → 升级为 Skill     │
├─────────────────────────────────────────────┤
│ L5 外部增强（可选插件，非必须）               │
│ MCP Memory / 向量数据库 / 外部知识图谱         │
└─────────────────────────────────────────────┘
```

### 12.2 optimization-agent 记忆整理流程

复用已有定时任务 `daily_self_evolution`，补全蒸馏逻辑：

```
Cron 触发（每日）
  │
  ├── Step 1: 清洗会话记录
  │   读取最近 24h 的 Agent sessions
  │   过滤噪声（重复stdout、心跳、空回复）
  │   提取有价值内容（修复过程、新发现、决策依据）
  │
  ├── Step 2: 分类归档
  │   ├── 事实类 → 更新 MEMORY.md / openclaw-memory
  │   │   "项目 xx-trader 部署在 大白pm:8080"
  │   │   "xx-trader 日志路径: /var/log/trader/"
  │   │
  │   ├── 经验类 → 写入 .workflow/experience/
  │   │   "PowerShell 的 && 要用 ; 替代"
  │   │
  │   └── 模式类 → 评估是否升级为 Skill
  │       同一操作≥3次 → 建议封装为 SKILL.md
  │
  ├── Step 3: 去重合并
  │   与现有记忆对比，重复跳过，冲突标注待人工裁决
  │
  └── Step 4: 产出报告
      "新增 3 条事实、2 条经验、1 个技能候选"
```

### 12.3 项目画像（记忆整理的核心产出）

每个 Agent 应了解自己管辖的项目：

| 维度 | 示例 |
|------|------|
| 项目位置 | `xx-trader: H:\GitHub\xx-trader, 远程: /home/ubuntu/xx-trader` |
| API/服务 | `端口 8080, 入口 /api/v1/, gunicorn + nginx` |
| 日志路径 | `/var/log/trader/, 本机 logs/` |
| 核心功能 | 跟单信号、余额监控、策略执行 |
| 最佳技能组合 | 部署用 db-deploy + deployment-test |
| 已知陷阱 | wallet 初始化必须在 unlock 后调用 |

---

## 13. 自进化闭环 — 评分驱动定向优化

### 13.1 闭环全景

```
人给任务 → 自动完成 → 不懂问人 → 经验复用 → 评分驱动优化 → 进化
   ↑                                                         │
   └─────────────────────────────────────────────────────────┘
```

### 13.2 reviewer 评分 → 薄弱环节识别

```
reviewer 给分（代码质量/安全/架构/文档...）
  │
  ├── 分析: "backend-dev 安全维度连续3次 < 70分"
  │   → 判定薄弱环节: 安全意识不足
  │   → 优化方案: 给 backend-dev 加强 security-audit 技能
  │   → 或: 在 SOUL.md 中强化安全检查约束
  │
  ├── 分析: "deployer 回滚速度评分持续低"
  │   → 判定薄弱环节: 回滚流程不完善
  │   → 优化方案: 补充回滚经验卡片到 experience/
  │
  └── 优化建议本身写入 todo → 下次编码自动应用
      → 下轮 reviewer 再打分 → 验证分数是否提升
```

### 13.3 三种进化路径

| 薄弱类型 | 进化方式 | 产出物 |
|----------|---------|--------|
| 知识缺失 | 补充经验卡片 | `.workflow/experience/*.md` |
| 技能缺失 | 绑定已有技能或新建 | `skills/library/` + SOUL.md 更新 |
| 行为约束不足 | 修改 SOUL.md 铁律 | `agents/*/SOUL.md` 约束强化 |

### 13.4 经验 → 技能的升级条件

```
同一操作流程出现 ≥ 3次
  │
  ├── optimization-agent 自动检测
  ├── 生成 SKILL.md 草稿
  ├── 提交人工确认（高风险默认需人确认）
  └── 确认后注册到 agent_to_skills.json
```

---

## 14. Agent 权限隔离 — 代码修改权限

### 14.1 权限矩阵

| Agent | 改业务代码 | 改配置 | 改运维脚本 | 改 SOUL.md |
|-------|:--------:|:-----:|:--------:|:---------:|
| backend-dev | ✅ | ❌ | ❌ | ❌ |
| frontend-dev | ✅ | ❌ | ❌ | ❌ |
| ops-agent | ❌ | ✅ | ✅ | ❌ |
| deployer | ❌ | ✅ | ❌ | ❌ |
| reviewer | ❌ | ❌ | ❌ | ❌ |
| coordinator | ❌ | ❌ | ❌ | ❌ |
| optimization-agent | ❌ | ❌ | ❌ | ✅ (建议) |
| doc-writer | ❌ | ❌ | ❌ | ❌ |

### 14.2 异常处理的任务分发

```
ops-agent 发现异常
  │
  ├── 是配置/运维问题 → ops-agent 自己修
  │   重启进程、回滚配置、清理日志
  │
  └── 是代码 bug → ⚠️ 禁止自己改代码！
        │
        ├── 建单到 task_center.db
        │   描述: 错误日志 + 复现路径 + 影响范围
        │
        └── 指派 → coordinator → 编码 Agent
              │
              ├── LLM 判定为低风险 → 编码 Agent 直接修
              └── LLM 判定为高风险 → 人确认后再修
                    │
                    └── 人可改判: "这类以后是低风险"
                         → 经验沉淀，下次自动走快速通道
```

### 14.3 铁律

- **ops-agent 只治标（重启/回滚），不治本（改代码）。治本的事建单走 HardFlow。**
- **reviewer 只读不写** — 读代码、看截图，不改一行代码。
- **optimization-agent 只建议不执行** — 产出优化建议/SOUL.md 修改建议，由人或其他 Agent 落地。

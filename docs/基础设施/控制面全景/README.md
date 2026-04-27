# OpenClaw 控制面全景 — 系统运行架构手册

> **最后更新：2026-04-27**
> 本文档是 OpenClaw 历史控制面的全局运行指南，涵盖：谁在运行、怎么调度、工作流如何流转、配置在哪里改。
> nofx 当前 Hermes workflow runtime 已精简为 `arbitrageagent` / `spreadagent` 两个 live profile，模型均为 `openai-codex/gpt-5.5`；本文中 14 Agent 口径仅代表历史 OpenClaw 注册表，不代表 nofx 当前运行态。

---

## 1. 回答你的核心问题

| 问题 | 现状 | 位置 |
|------|------|------|
| **有哪些 Agent** | 历史 OpenClaw 注册表：14 个 Agent + 1 路由别名；nofx 当前运行态：2 个 Hermes profile + workflow stage owner 标签 | [多Agent体系/README.md](file:///H:/GitHub/openclaw-hardflow-backup-20260302/docs/基础设施/多Agent体系/README.md) |
| **Agent 用什么能力/技能** | `agent_capability_manifest.json` | `~/agents/agent_capability_manifest.json` |
| **工作流有哪些** | 5 个 Profile（4 个编码 + 1 个治理） | `~/.openclaw/ops/policy/workflow-profile-registry.json` |
| **整个流程是什么** | 见下方 §3. 端到端流程图 | — |
| **有没有总控台** | ❌ **没有可视化控制台** | 目前全靠 JSON 文件 + Cron 日志 |

> [!IMPORTANT]
> **当前最大的治理缺陷：没有统一的可视化控制台。** 所有控制都散落在 10+ 个 JSON 配置文件中，变更靠手工编辑，状态靠 Telegram 推送 + 日志文件追溯。这是后续需要优先解决的问题。

---

## 2. 控制面全景地图

### 配置文件职责一览

```mermaid
graph LR
    subgraph 谁来做["① 谁来做 (Agent 层)"]
        A1["agent_index.json<br/>运行时注册"]
        A2["capability_manifest.json<br/>能力+技能声明"]
        A3["capability-registry.json<br/>能力域定义"]
        A4["agents/*/SOUL.md<br/>角色指令"]
    end
    subgraph 怎么分["② 怎么分配 (路由层)"]
        R1["routing-rules.json<br/>关键词→Agent"]
        R2["policy-config.json<br/>策略+调度规则"]
    end
    subgraph 怎么做["③ 怎么做 (工作流层)"]
        W1["workflow-profile-registry.json<br/>工作流 Profile"]
        W2["score-policy.json<br/>质量门禁"]
    end
    subgraph 什么时候["④ 什么时候 (调度层)"]
        C1["cron/jobs.json<br/>定时任务"]
        C2["task_center.db<br/>任务数据库"]
    end
    subgraph 多少钱["⑤ 多少钱 (成本层)"]
        T1["token-pricing.json<br/>模型定价"]
        T2["model_tier_profiles.json<br/>模型档位"]
    end
```

### 详细文件索引

| 层级 | 文件 | 路径 | 你改它干嘛 |
|------|------|------|-----------|
| **① Agent 层** | `agent_capability_manifest.json` | `~/agents/` | 新增/修改 Agent 的能力和技能声明 |
| | `agent_index.json` | `~/.openclaw/agents/` | Agent 运行时绑定（模型/工作空间/子调度） |
| | `capability-registry.json` | `~/.openclaw/ops/policy/` | 能力域定义（哪些 Agent 拥有什么能力） |
| | `SOUL.md` | `agents/<agent-id>/` | 修改 Agent 的角色指令/行为边界 |
| **② 路由层** | `routing-rules.json` | `~/.openclaw/ops/policy/` | 修改关键词→Agent 的自动路由规则 |
| | `policy-config.json` | `~/.openclaw/ops/policy/` | 修改全局策略（模型选择/积分/风险/调度） |
| **③ 工作流层** | `workflow-profile-registry.json` | `~/.openclaw/ops/policy/` | 修改工作流阶段/门禁/验证合约 |
| | `score-policy.json` | `~/scripts/hardflow/` | 修改质量评分的门禁配置 |
| **④ 调度层** | `jobs.json` | `~/.openclaw/cron/` | 修改定时任务频率/参数 |
| | `task_center.db` | `~/.openclaw/ops/task-center/` | 任务状态数据库（SQLite，不手动改） |
| **⑤ 成本层** | `token-pricing.json` | `~/.openclaw/ops/policy/` | 模型 token 定价 |
| | `model_tier_profiles.json` | `~/scripts/openclaw-ops/` | 模型档位（标准/经济/高性能） |

---

## 3. 端到端流程图

```mermaid
flowchart TB
    subgraph 触发["触发源"]
        T1["⏰ Cron 定时任务"]
        T2["👤 用户手动"]
        T3["🔗 Webhook"]
    end

    subgraph 入口["入口路由"]
        E1["routing-rules.json<br/>关键词匹配"]
        E2["policy-config.json<br/>任务分级 light/medium/major"]
    end

    subgraph 派单["Preflight + 派单"]
        P1["capability_manifest.json<br/>能力校验"]
        P2["capability-registry.json<br/>域权限校验"]
        P3["agent_index.json<br/>allowAgents 校验"]
    end

    subgraph 执行["工作流执行"]
        W1["clarify 阶段<br/>需求澄清"]
        W2["implement 阶段<br/>代码实现"]
        W3["iterative_refine<br/>多轮自愈"]
        W4["review 阶段<br/>代码审查"]
        W5["deploy 阶段<br/>部署上线"]
    end

    subgraph 门禁["质量门禁"]
        G1["score-policy.json<br/>requirements ≥ 70"]
        G2["score-policy.json<br/>backend ≥ 75"]
        G3["score-policy.json<br/>refine ≥ 70"]
        G4["score-policy.json<br/>review ≥ 85"]
    end

    subgraph 产出["产出"]
        O1["task_center.db<br/>状态记录"]
        O2["executor-runs/<br/>执行日志"]
        O3["📱 Telegram 通知"]
    end

    T1 & T2 & T3 --> E1
    E1 --> E2
    E2 --> P1
    P1 --> P2
    P2 --> P3
    P3 -->|通过| W1
    P3 -->|阻断| O3

    W1 --> G1
    G1 -->|通过| W2
    W2 --> G2
    G2 -->|通过| W4
    G2 -->|失败| W3
    W3 --> G3
    G3 -->|通过| W4
    W4 --> G4
    G4 -->|通过| W5

    W5 --> O1
    O1 --> O2
    O2 --> O3
```

---

## 4. 工作流 Profile 清单

| Profile ID | 显示名 | 通道 | 阶段数 | 状态 |
|------------|--------|------|:------:|:----:|
| `coding-default` | 默认编码工作流 | stable | 5 | ✅ |
| `coding-default` | 默认编码工作流 | canary | 5 | ✅ |
| `coding-default` | 默认编码工作流 | experimental | 5 | ✅ |
| `governance-evolution` | 治理进化工作流 | stable | 3 | ✅ |
| `hardflow-pipeline` | HardFlow 全流程 | stable | 7 | ✅ |

### 编码工作流阶段

| 阶段 | 门禁 | 校验 | 说明 |
|------|------|------|------|
| `clarify` | requirements ≥ 70 | 需求完整性检查 | project-agent 澄清 |
| `implement` | backend ≥ 75 | 测试证据 ≥ 3 项 | 实际编码 + 验证 |
| `iterative_refine` | refine ≥ 70 | 修复后测试通过 | 失败重试自愈 |
| `review` | review ≥ 85 | 安全 + 质量审查 | reviewer 独立评审 |
| `deploy` | (无独立门禁) | 部署后测试 | deployer 执行 |

---

## 5. Cron 定时任务

| 任务 ID | 频率 | Agent | 说明 |
|---------|------|-------|------|
| 增量巡检 | 15 分钟 | ops-agent | 系统健康检查 |
| 任务执行器 | 10 分钟 | coordinator | 执行未闭环任务 |
| 全量校准 | 每周 | optimization-agent | 策略/配置全量审计 |
| 自进化 | 每周 | optimization-agent | 经验沉淀 + 改进 |
| HardFlow 审查 | 触发式 | project-agent | 代码变更审查 |

---

## 6. 当前缺什么？改什么在哪改？

### 常见操作速查

| 我想... | 改哪个文件 |
|---------|-----------|
| 新增一个 Agent | [运维 SOP](file:///H:/GitHub/openclaw-hardflow-backup-20260302/docs/基础设施/多Agent体系/README.md) §7.1 |
| 修改 Agent 的模型 | `policy-config.json` → `agent_model_overrides` |
| 修改 Agent 能调度谁 | `agent_capability_manifest.json` → `allow_agents` |
| 修改任务路由关键词 | `routing-rules.json` → `assignee_rules` |
| 修改质量门禁分数 | `score-policy.json` → 对应 gate 的 `pass_line` |
| 修改 cron 频率 | `jobs.json` → 对应 job 的 `interval_minutes` |
| 修改工作流阶段 | `workflow-profile-registry.json` → `profiles.stages` |
| 切换模型档位 | 运行 `switch_model_tier.py` |

### 缺失的能力（待建设）

| 缺失项 | 影响 | 建议优先级 |
|--------|------|:---------:|
| **可视化总控台** | 无法一览 Agent/任务/工作流状态，只能看JSON和日志 | 🔴 高 |
| **配置变更审计** | 改了配置不知道谁改的、什么时候改的 | 🟡 中 |
| **配置自动同步** | 本文档改了，四个 JSON 文件不会自动更新 | 🟡 中 |
| **Agent 健康看板** | 不知道哪个 Agent 在线、响应延迟多少 | 🟡 中 |
| **任务看板** | 看不到未闭环任务列表和执行进度 | 🟡 中 |

# Claude Code 源码还原深度研究

> 状态：✅ 研究完成 | 日期：2026-04-01
> 来源：[XX-Trader/Claude-Code](https://github.com/XX-Trader/Claude-Code)（fork 自 pengchengneo/Claude-Code）
> 性质：从 `@anthropic-ai/claude-code` npm 包的 source map 中还原的完整 TypeScript 源码
> 规模：1,987 个 TS/TSX 源文件 | 53 个工具 | 87 个斜杠命令 | 148 个 UI 组件

---

## 一、项目架构概览

```
src/                         # 核心源码
├── tools/                   # 53 个工具（Bash/FileEdit/Agent/MCP...）
├── commands/                # 87 个斜杠命令
├── services/                # API / MCP / analytics / autoDream
├── components/              # 148 个终端 UI 组件（React + Ink）
├── hooks/                   # 87 个自定义 Hooks
├── buddy/                   # 宠物伴侣系统
├── assistant/               # KAIROS 助手模式
├── coordinator/             # 多 Agent 协调器（核心参考）
├── bridge/                  # 远程控制桥接（33 文件）
├── proactive/               # 主动模式
├── vim/                     # Vim 模式引擎
├── voice/                   # 语音交互
└── ...
shims/                       # 原生模块兼容替代
vendor/                      # 原生绑定源码
```

---

## 二、7 大隐藏功能

### 1. BUDDY — AI 电子宠物

- 源码：`src/buddy/`
- 编译开关：`feature('BUDDY')`
- 18 种物种、5 级稀有度（普通60% → 传说1%）、1% 闪光概率
- 确定性生成：账号 UUID + 固定盐值 `'friend-2026-401'` 经 FNV-1a 哈希
- 交互命令：`/buddy pet`（抚摸）、`/buddy hatch`（孵化）、`/buddy card`（卡片）

### 2. KAIROS — 永不关机的 Claude（⭐ 对 OpenClaw 高价值）

- 源码：`src/assistant/`、`src/proactive/`、`src/services/autoDream/`
- 编译开关：`feature('KAIROS')`、`feature('KAIROS_BRIEF')`、`feature('KAIROS_CHANNELS')`

**核心子系统：**

| 子系统 | 功能 | 对 OpenClaw 的价值 |
|--------|------|-------------------|
| 跨会话持久运行 | 关闭终端后后台继续 | ⭐⭐⭐ 对标我们的 Gateway |
| Dream 记忆整合 | 4 阶段：Orient → Gather → Consolidate → Prune | ⭐⭐⭐ 参考多平台记忆蒸馏 |
| Proactive 主动模式 | 没人说话时自己找活干，没活就 `SleepTool` 等着 | ⭐⭐ 类似 cron 执行 |
| Cron 调度器 | 每 1 秒 tick，支持一次性/循环/永久/会话级任务 | ⭐⭐ 我们 `jobs.json` 类似 |
| Jitter 防雷群 | 确定性延迟（interval 的 10%，上限 15 分钟） | ⭐⭐ 🆕 我们缺少 |
| 锁机制 | `.consolidate-lock` + PID 存活检查 | 已有 `.gateway.lock` |

**激活五层门控：**
```
1. feature('KAIROS')           ← 编译时 flag
2. settings.assistant: true    ← .claude/settings.json
3. 目录信任状态检查             ← 防恶意仓库劫持
4. tengu_kairos                ← GrowthBook 远程开关
5. setKairosActive(true)       ← 全局状态激活
```

### 3. ULTRAPLAN — 云端深度规划

- 源码：`src/commands/ultraplan.tsx`、`src/utils/ultraplan/`
- 编译开关：`feature('ULTRAPLAN')`
- `/ultraplan <prompt>` → 创建远程 CCR 会话 → Opus 模型独立研究（30 分钟超时）
- 传送（Teleport）：`src/utils/teleport.tsx` 支持 Git Bundle 打包代码上下文
- **仅内部可用**：`isEnabled: () => "external" === 'ant'`

### 4. Coordinator — 多 Agent 编排模式（⭐⭐⭐ 最高参考价值）

- 源码：`src/coordinator/coordinatorMode.ts`（~370 行）
- 编译开关：`feature('COORDINATOR_MODE')`
- 环境变量：`CLAUDE_CODE_COORDINATOR_MODE`

> **详见下方第三节专题分析**

### 5. 26+ 隐藏命令

**Feature-gated 命令（编译开关控制）：**

| 命令 | 编译开关 | 功能 |
|------|---------|------|
| `/buddy` | `BUDDY` | 宠物伴侣系统 |
| `/proactive` | `PROACTIVE` / `KAIROS` | 主动自主模式 |
| `/assistant` | `KAIROS` | 持久助手模式 |
| `/bridge` | `BRIDGE_MODE` | 远程控制桥接 |
| `/voice` | `VOICE_MODE` | 语音交互 |
| `/ultraplan` | `ULTRAPLAN` | 云端深度规划 |
| `/fork` | `FORK_SUBAGENT` | 子代理分叉 |
| `/peers` | `UDS_INBOX` | 对等通信（Unix Domain Socket） |
| `/workflows` | `WORKFLOW_SCRIPTS` | 工作流脚本 |
| `/force-snip` | `HISTORY_SNIP` | 强制历史截断 |

**仅内部用户命令（`USER_TYPE === 'ant'`）：**

| 命令 | 功能 |
|------|------|
| `/teleport` | 传送会话到远程/本地 |
| `/bughunter` | 内部 Bug 猎人 |
| `/ctx_viz` | 上下文可视化 |
| `/autofix-pr` | 自动修复 PR |
| `/debug-tool-call` | 调试工具调用 |
| `/agents-platform` | 智能体平台管理 |

### 6. Bridge — 远程遥控终端

- 源码：`src/bridge/`（33 个文件）
- 编译开关：`feature('BRIDGE_MODE')` + `feature('DAEMON')`
- WebSocket 双向通道，支持从 claude.ai 或手机直接操控本地 CLI
- 含权限回调、状态同步、崩溃恢复机制

### 7. 50 个编译开关 + 远程门控

**三层门控体系：**

| 层次 | 机制 | 数量 |
|------|------|------|
| 第一层 | 编译时开关 `feature()` | ~50 个 |
| 第二层 | 用户类型 `USER_TYPE` | `ant`(内部) / `external`(外部) |
| 第三层 | GrowthBook 远程 A/B 测试 | ~10 个 `tengu_*` 开关 |

**关键编译开关：**

| 开关 | 功能 | OpenClaw 相关性 |
|------|------|----------------|
| `COORDINATOR_MODE` | 多 Agent 协调 | ⭐⭐⭐ |
| `KAIROS` | 持久助手模式 | ⭐⭐⭐ |
| `PROACTIVE` | 主动模式 | ⭐⭐ |
| `WORKFLOW_SCRIPTS` | 工作流脚本 | ⭐⭐ |
| `MCP_SKILLS` | MCP 技能系统 | ⭐⭐ |
| `FORK_SUBAGENT` | 子代理分叉 | ⭐⭐ |
| `EXTRACT_MEMORIES` | 记忆提取 | ⭐⭐ |
| `TOKEN_BUDGET` | Token 预算控制 | ⭐⭐ |
| `UNATTENDED_RETRY` | 无人值守重试 | ⭐⭐ |
| `BG_SESSIONS` | 后台会话 | ⭐⭐ |

---

## 三、Coordinator 多 Agent 编排专题

### 角色分离

| 角色 | 职责 | 可用工具 |
|------|------|---------:|
| **Coordinator（指挥官）** | 理解目标、拆解任务、综合结果 | 仅 `Agent`、`SendMessage`、`TaskStop` |
| **Worker（执行者）** | 具体代码操作 | 完整工具集（过滤掉内部工具） |

### 标准四阶段流程

| 阶段 | 执行者 | 目的 |
|------|--------|------|
| **Research** | Worker（可并行） | 调查代码库，查找文件，理解问题 |
| **Synthesis** | Coordinator 自身 | 阅读发现、编写实施规格 |
| **Implementation** | Worker | 按规格做精准改动 |
| **Verification** | Worker | 测试改动是否生效 |

### Worker 通信机制

```xml
<task-notification>
  <task-id>{agentId}</task-id>
  <status>completed|failed|killed</status>
  <summary>{状态摘要}</summary>
  <result>{Worker 的最终文本回复}</result>
  <usage><total_tokens>N</total_tokens></usage>
</task-notification>
```

### 并发管理

| 任务类型 | 并行策略 |
|----------|---------|
| 只读任务（研究） | 自由并行 |
| 写操作（实施） | 同一组文件同时只能一个 Worker |
| 验证 | 可与实施在不同区域并行 |

### Continue vs Spawn 决策

| 场景 | 决策 | 方式 |
|------|------|------|
| 研究的文件就是要编辑的文件 | Continue | `SendMessage` |
| 研究范围广但实施范围窄 | Spawn fresh | `Agent` |
| 修正失败或扩展近期工作 | Continue | `SendMessage` |
| 验证另一个 Worker 刚写的代码 | Spawn fresh | 独立视角 |
| 第一次方案完全错误 | Spawn fresh | 避免锚定效应 |

### 核心铁律

> **禁止甩锅式委派** — Coordinator 必须自己做综合分析。  
> Prompt 必须包含**具体文件路径、行号、要做什么改动**。  
> **Worker 看不到 Coordinator 的对话**，每个 prompt 必须完全自包含。

### Scratchpad（跨 Worker 共享知识）

- Coordinator 告知 Worker 一个 scratchpad 目录路径
- Worker 可在该目录下自由读写（不需要权限提示）
- 用于跨 Worker 的持久化知识共享

---

## 四、53 个内置工具清单

### 核心编码工具
| 工具 | 功能 |
|------|------|
| `BashTool` | Shell 命令执行 |
| `PowerShellTool` | Windows PowerShell 执行 |
| `FileReadTool` | 文件读取 |
| `FileWriteTool` | 文件写入 |
| `FileEditTool` | 文件编辑（diff 级别） |
| `GlobTool` | 文件名匹配搜索 |
| `GrepTool` | 文本内容搜索 |
| `NotebookEditTool` | Jupyter Notebook 编辑 |
| `LSPTool` | Language Server Protocol 集成 |
| `REPLTool` | REPL 交互式执行 |
| `TerminalCaptureTool` | 终端输出捕获 |

### Agent 相关工具
| 工具 | 功能 |
|------|------|
| `AgentTool` | 创建子代理/Worker |
| `SendMessageTool` | 向已有 Worker 发送消息 |
| `TaskCreateTool` | 创建任务 |
| `TaskGetTool` | 获取任务状态 |
| `TaskListTool` | 列出任务 |
| `TaskUpdateTool` | 更新任务 |
| `TaskStopTool` | 停止任务 |
| `TaskOutputTool` | 获取任务输出 |
| `TeamCreateTool` | 创建团队 |
| `TeamDeleteTool` | 删除团队 |

### Web 与 MCP 工具
| 工具 | 功能 |
|------|------|
| `WebBrowserTool` | 浏览器交互 |
| `WebFetchTool` | HTTP 抓取 |
| `WebSearchTool` | 搜索引擎 |
| `MCPTool` | MCP 通用工具调用 |
| `McpAuthTool` | MCP 认证 |
| `ListMcpResourcesTool` | 列出 MCP 资源 |
| `ReadMcpResourceTool` | 读取 MCP 资源 |

### 辅助工具
| 工具 | 功能 |
|------|------|
| `SkillTool` | 技能搜索与执行 |
| `DiscoverSkillsTool` | 技能发现 |
| `ToolSearchTool` | 工具搜索 |
| `MonitorTool` | 系统监控 |
| `SleepTool` | 休眠等待 |
| `SnipTool` | 历史截断 |
| `WorkflowTool` | 工作流执行 |
| `ConfigTool` | 配置管理 |
| `TodoWriteTool` | Todo 列表管理 |
| `ReviewArtifactTool` | 产出物审查 |
| `ScheduleCronTool` | 定时任务调度 |
| `RemoteTriggerTool` | 远程触发 |
| `SendUserFileTool` | 发送文件给用户 |
| `BriefTool` | 简报生成 |
| `EnterPlanModeTool` | 进入规划模式 |
| `ExitPlanModeTool` | 退出规划模式 |
| `EnterWorktreeTool` | 进入 Git Worktree |
| `ExitWorktreeTool` | 退出 Git Worktree |
| `VerifyPlanExecutionTool` | 验证规划执行 |
| `SyntheticOutputTool` | 合成输出 |
| `TungstenTool` | 内部诊断 |
| `OverflowTestTool` | 溢出测试 |
| `AskUserQuestionTool` | 向用户提问 |

---

## 五、隐藏环境变量（可直接使用）

### 常用但未公开

| 环境变量 | 功能 |
|----------|------|
| `ANTHROPIC_MODEL` | 覆盖默认模型 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 最大输出 token 数 |
| `CLAUDE_CODE_DISABLE_THINKING` | 禁用思考 |
| `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` | 禁用自适应思考 |
| `CLAUDE_CODE_PROACTIVE` | 主动模式 |
| `CLAUDE_CODE_COORDINATOR_MODE` | 协调器模式 |
| `CLAUDE_CODE_BRIEF` | 简报模式 |
| `CLAUDE_CODE_SYNTAX_HIGHLIGHT` | 语法高亮主题 |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` | 禁用自动记忆 |
| `CLAUDE_CODE_IDLE_THRESHOLD_MINUTES` | 空闲阈值（默认 75 分钟） |
| `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` | 最大工具并发数 |

### 第三方模型集成

| 环境变量 | 功能 |
|----------|------|
| `CLAUDE_CODE_USE_BEDROCK` | 使用 AWS Bedrock |
| `CLAUDE_CODE_USE_VERTEX` | 使用 Google Vertex |
| `CLAUDE_CODE_USE_FOUNDRY` | 使用 Foundry |

### API 扩展

| 环境变量 | 功能 |
|----------|------|
| `CLAUDE_CODE_EXTRA_BODY` | API 请求附加 JSON body |
| `CLAUDE_CODE_EXTRA_METADATA` | API 请求附加元数据 |

---

## 六、与 OpenClaw 多 Agent 系统的对比

### 四阶段 vs HardFlow G0-G6

| 维度 | Claude Code 四阶段 | OpenClaw HardFlow |
|------|-------------------|-------------------|
| 研究 | Research（Worker 并行） | G0（单线程） |
| 方案 | Synthesis（Coordinator 亲做） | G1（可委派） |
| 实现 | Implementation | G2 |
| 验证 | Verification | G3 |
| 审查 | ❌ 无 | G4 |
| 部署 | ❌ 无 | G5 |
| 运维 | ❌ 无 | G6 |
| 门禁 | ❌ 无 | ✅ 每个 Gate 有质量分数阈值 |
| 回流 | Spawn fresh 重来 | ✅ 回流到上一阶段整改 |

**结论**：四阶段更轻量，HardFlow 更完整。不用替换，在 G0 阶段引入并行 Research 能力即可。

---

## 七、9 大改进项对 OpenClaw 的适用性分析

### 1. Dream 记忆整合 → 多平台统一记忆蒸馏

**KAIROS Dream 4 阶段**：Orient → Gather → Consolidate → Prune

**我们的改进方向**：扩展为跨平台蒸馏

```
数据源：
├── IDE 记忆（Gemini KI / Claude Code 会话 / Codex 对话）
├── OpenClaw 记忆（MCP Memory / Agent 日志 / task_center.db）
└── 输出 → docs/ 体系 + skills/(draft) + 策略调优
```

**实施**：新增 cron 任务，每日凌晨低峰期运行，触发条件："距上次整合 > 24h + 5+ 新会话"

### 2. Worker 独立子进程隔离

**Claude Code 做法**：Worker 在独立子进程，看不到 Coordinator 对话，Prompt 完全自包含。

**我们的改进**：
- Prompt 自包含规范：每个任务描述必须包含目标、完成标准、相关文件路径和行号、约束条件
- 结果回传标准化：统一 JSON 格式（status/summary/result/files_modified/token_usage）

### 3. 四阶段流程 — 引入并行 Research

**建议**：不替换 HardFlow，在 G0 阶段引入 Coordinator 的并行研究能力：
- G0：Coordinator 派多个 Worker 并行调查（一个查代码结构、一个查文档、一个查历史 PR）
- G1：Coordinator 亲自综合分析，产出实施规格
- G2-G6 保持原样

### 4. 文件级并发锁

**Claude Code 规则**：只读自由并行，写操作同一组文件只能一个 Worker。

**实施**：新增 `~/.openclaw/ops/.file-locks.json`，按文件/目录区域加锁，锁包含 worker_id + pid + acquired_at。

### 5. Scratchpad 共享知识目录

**建议**：新增 `~/.openclaw/scratchpad/`，每个任务组共享子目录，完成后归档到 `ops/scratchpad-archive/`。

### 6. 工作流工具化

**目前缺失**：Agent 无法在对话中主动触发其他工作流。

**建议**：新增 OpenClaw 指令：
- `/workflow run <name> [--args]` — 主动触发工作流
- `/workflow list` — 列出可用工作流
- `/workflow status <run_id>` — 查询执行状态

### 7. ScheduleCronTool — Agent 自主调度

**建议**：新增 `/cron create` 指令，安全约束：
- Agent 创建的任务标记为 `source: "agent-created"`
- 需 Coordinator/Gateway 审批才能激活
- 默认只允许一次性任务，循环任务需人工确认
- 自动设置 7 天过期

### 8 & 9. 规划模式 + 验证 → Gate 阶段工具集限制

**最有价值的改进**：按 HardFlow Gate 阶段动态限制可用工具集：

| HardFlow 阶段 | 可用工具集 | 约束 |
|---------------|-----------|------|
| G0 Research | FileRead, Grep, Glob, WebSearch | ❌ 不能写文件 |
| G1 Synthesis | FileRead, FileWrite(仅 docs/) | ❌ 只能写文档 |
| G2 Implementation | 完整工具集 | ✅ 可以写代码 |
| G3 Verification | Bash(测试命令), FileRead | ❌ 不能修改代码 |
| G4 Review | FileRead, Grep | ❌ 只读 |

**实施**：在 task_executor 的 `preflight` 中注入 `allowed_tools`，Agent 调用非法工具时 Gateway 拦截。

---

## 八、优先级排序

| 批次 | 改进项 | 复杂度 | 价值 |
|------|--------|--------|------|
| **第 1 批** | #9 Gate 阶段工具集限制 | 🟡 中 | ⭐⭐⭐ |
| **第 1 批** | #2 Worker 自包含 Prompt 规范 | 🟢 低 | ⭐⭐⭐ |
| **第 2 批** | #7 ScheduleCronTool Agent 自主调度 | 🟡 中 | ⭐⭐ |
| **第 2 批** | #4 文件级并发锁 | 🟡 中 | ⭐⭐ |
| **第 2 批** | #6 工作流工具化 | 🟡 中 | ⭐⭐ |
| **第 3 批** | #5 Scratchpad 共享知识目录 | 🟢 低 | ⭐ |
| **第 3 批** | #3 G0 并行 Research 能力 | 🔴 高 | ⭐⭐ |
| **第 3 批** | #1 多平台 Dream 记忆整合 | 🔴 高 | ⭐⭐⭐ |

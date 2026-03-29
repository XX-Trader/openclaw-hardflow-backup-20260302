# AI 自主编程的真实难点与业界实战借鉴

> 基于 OpenAI 官方博客、3 个开源项目、2 篇 2026 年最新论文的深度提炼
> 
> 核心问题：**让 AI 在 IDE/终端上自主完成编程任务，到底难在哪？别人是怎么解决的？**

---

## 一、真实世界的五大致命难点

### 难点 1：AI 会陷入死循环 — "同一个错误修了又修"

**现象**：AI 跑 type-check 失败 → 修改代码 → 再跑 type-check → 报同一个错误 → 再修 → 再报 … 直到 token/turns 耗尽。

这是所有实际落地团队遇到的**头号问题**。日本 Explaza 团队的真实踩坑记录：

> "max-turns を上げると実行時間とコストが膨張する。AIが同じエラーをループする"
> 
> —— 提高 max-turns → 时间和成本膨胀。AI 在同一个错误上死循环。

**根本原因**：AI 不具备"我已经尝试过这个方案了"的元认知。它每一轮都在重新推理，但上下文中积累的失败尝试反而干扰了它的判断。

**业界解法（具体代码）**：

Explaza 团队在他们的 `orchestrate.ts` 编排器中实现了 stderr 监控 + 循环检测：

```typescript
const LOOP_THRESHOLD = 3  // 同一个错误出现 3 次就强制终止

child.stderr.on('data', (data: Buffer) => {
  const line = data.toString().trim()
  // 关键：正则化处理 — 去掉时间戳和行号再比较
  const normalized = line
    .replace(/\d{4}-\d{2}-\d{2}[\sT][\d:.]+/g, '')  // 去时间戳
    .replace(/:\d+:\d+/g, ':X:X')                      // 去行号
    .trim()
  if (normalized.length < 20) return
  
  const count = (errorCounts.get(normalized) || 0) + 1
  errorCounts.set(normalized, count)
  
  if (count === LOOP_THRESHOLD) {
    console.warn(`Loop detected: same error ${LOOP_THRESHOLD} times, terminating`)
    child.kill('SIGTERM')  // 强杀进程，不再浪费 token
  }
})
```

**实战要点**：
- 必须做"正则化"——去掉时间戳和行号后再比较，否则每次报错内容细微不同，检测不到循环
- 阈值设为 3 次是经验值：1 次太严（可能误判），5 次太松（已浪费太多 token）
- 终止后不是直接失败，而是**回流到人工复审或更换策略**

---

### 难点 2：上下文窗口是有限的 — "AI 忘了你前面说的话"

**现象**：对话初期 AI 严格遵守的规则（命名规范、架构约束），在 30+ 次工具调用后就被"忘了"。

OPENDEV 论文给出了精确的数据：

> **工具输出（文件内容、命令结果、搜索结果）占据一个典型会话上下文的 70-80%。**
> 
> 系统提示的影响力随对话增长而衰减。前几轮可靠遵守的指令，30+ 工具调用后频繁被违反。

**根本原因**：LLM 的注意力机制使得最近的内容权重最高。当前面的系统指令被大量工具输出"淹没"后，AI 的行为就开始"漂移"。

**业界解法 1 — 自适应上下文压缩（OPENDEV 论文）**：

把历史观测分三级管理，如同内存的 L1/L2/L3 缓存：

```
Active 观测 → Faded 观测 → Archived 观测
(完整原始内容)  (LLM 摘要替代)   (仅核心事实)
```

效果：**峰值上下文消耗减少 54%**。

一个关键的反直觉发现：不要反复压缩已压缩的摘要（会信息失真），应该**定期从完整历史重新生成摘要**。

**业界解法 2 — 事件驱动的系统提醒（OPENDEV 论文）**：

不是在对话开头说一次规则就完事，而是在关键事件节点（如"即将编辑文件"、"即将执行 shell 命令"）自动重新注入核心规则。

```
场景：Agent 即将执行第 35 个工具调用，是一个 file_write
系统自动注入提醒："你必须遵守项目的命名规范：组件名用 PascalCase，
                    函数名用 camelCase，文件名用 kebab-case"
```

**业界解法 3 — Architect Agent 做摘要（CCA 论文）**：

当上下文快满时，不是简单截断，而是调用一个**专门的"建筑师 Agent"**来做结构化摘要，显式保留：任务目标、已作决策、待办事项、关键错误轨迹。

消融实验证明：**摘要模型的质量直接影响最终任务解决率**（用强模型做摘要比弱模型高 8 个百分点）。

---

### 难点 3：AI 产出的代码会"散乱" — 熵增不可避免

**现象**：AI 连续生成一段时间的代码后，命名规则偏离、未使用代码堆积、API 格式不一致、console.log 残留。

**根本原因**：AI 没有"全局代码品味"。每次生成都是局部最优的，但日积月累就形成了独特的"AI 式散乱"——跟人类的技术债不同，但同样致命。

**业界解法 — 周次品质扫描 + autoFixable 自动修复（Zenn 实战）**：

Explaza 团队建立了 12 个检查项的品质扫描，最关键的设计是**用 `autoFixable` 标志区分"机械可修"和"需人类判断"**：

```
品质扫描 (每周一 9:00 自动运行)
│
├─ autoFixable = true (lint 错误 / console.log 残留 / 分号 / var 使用)
│   ↓ 自动创建 ai-implement Issue
│   ↓ orchestrate.ts 120 秒内自动检测
│   ↓ AI 自动修复 → 提交 Draft PR
│
└─ autoFixable = false (架构违反 / 设计决策)
    ↓ 创建 chore Issue
    ↓ 人类负责 triage
```

月次还有"垃圾回收"：扫描未使用 export、空文件、90 天未变更文件。

**核心思想**："AI 生成的问题由 AI 自动修复"——形成闭环。

---

### 难点 4：AI 可能执行破坏性操作 — "rm -rf 级灾难"

**现象**：AI 为了"修复"一个 bug，删除了关键配置文件/覆盖了生产数据库。

**根本原因**：LLM 无法分辨"我有权做"和"我该不该做"。它看到 schema 里有 `rm` 命令就可能用。

**业界解法 1 — Schema 级安全（OPENDEV 论文，最核心的思想）**：

> **"不要设置护栏栏杆，而是直接把路拆掉"**
> 
> 如果 Agent 的 schema 中根本没有写文件的工具，它就不可能写文件。它甚至不知道写文件这个能力存在。
> 
> 这比运行时权限检查更安全：Agent 无法推理它看不到的能力。

OPENDEV 将此落地为双模式：

| 模式 | 工具权限 | 用途 |
|------|---------|------|
| **Plan Mode** | 仅注入只读工具 schema | 调查、规划。**物理上不可能**产生任何副作用 |
| **Normal Mode** | 完整读写工具 schema | 实际执行 |

Explaza 团队用 `--allowedTools` 做了等价实现：

```typescript
const ALLOWED_TOOLS = [
  'Read', 'Write', 'Edit', 'MultiEdit', 'Bash',
  'Glob', 'Grep', 'Agent', 'Skill',
  'WebFetch', 'WebSearch', 'TodoWrite',
].join(',')
// 只有这 12 个工具可用，其他一概不给
```

**业界解法 2 — 生命周期钩子硬阻断（OPENDEV 论文）**：

OPENDEV 定义了 10 个生命周期事件。最关键的是 `PreToolUse` 钩子：

```python
# 钩子脚本返回 exit code 2 → 绝对阻断这次工具调用
# 无论 Agent 怎么 argue，都不可能绕过

def pre_tool_check(event):
    tool_name = event['tool_name']
    tool_input = event['tool_input']
    
    # 阻止删除保护路径
    if tool_name == 'bash' and 'rm -rf' in tool_input.get('command', ''):
        if '/production' in tool_input['command']:
            return 2  # 硬阻断，不可覆盖
    
    # 阻止修改锁定文件
    if tool_name == 'write_file':
        protected = ['package-lock.json', '.env.production']
        if any(p in tool_input.get('path', '') for p in protected):
            return 2
    
    return 0  # 放行
```

**业界解法 3 — 工具参数透明重写（OPENDEV 论文）**：

钩子可以返回 `updatedInput` 字段透明修改工具参数。比如自动给所有 `rm` 命令注入 `--dry-run`：

```json
{
  "updatedInput": {
    "command": "rm --dry-run -rf /some/path"
  }
}
```

Agent 不知道自己的命令被改了。

---

### 难点 5：多 Agent 协作的"信息鸿沟" — SubAgent 会过度工程

**现象**：主 Agent 委派一个调查任务给 SubAgent。SubAgent 缺乏原始上下文，做了过度分析，返回了一个过于复杂的方案。主 Agent 信任 SubAgent 的"专业意见"，实施了这个不必要的复杂方案。

CCA 论文通过案例研究精确记录了这个问题：

```
主 Agent (有完整上下文): "帮我查一下这个 CUDA 内存问题的根因"
     ↓ 委派
SubAgent (无上下文，只有任务描述): 
     → 被指示"要全面彻底地分析"
     → 因没有业务上下文，过度分析了问题
     → 返回了一个过度工程的解决方案
     ↓
主 Agent: "SubAgent 比我专业，听它的"
     → 实施了不必要的复杂方案
```

**CCA 的结论**：

> 对于**明确范围的调试任务**，多 Agent 委派的好处可能被以下风险抵消：
> 1. 上下文丢失
> 2. Agent 间目标错位（SubAgent 追求"全面"，主 Agent 需要"精准"）

**实战建议**：
- 简单任务：**单 Agent 优于多 Agent**（保持完整上下文）
- 复杂任务才拆分，且 SubAgent 的 prompt 中必须注入**精确的范围约束**，而非"尽可能全面"

---

## 二、设计全自主编程流水线的核心架构

综合所有资料，一条成熟的 AI 自主编程流水线应包含以下环节：

```
任务输入 (Issue/Ticket)
    │
    ▼
┌─────────────────────────────────────┐
│  上下文初始化 (Context Engineering)  │
│  · 从 Issue 自动提取文件路径         │
│  · 检索相似的历史已合并 PR           │
│  · 按条件组合系统 prompt             │
│  · 注入仅相关的工具 schema           │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Phase 1: Explore (只读模式)         │
│  · 工具 schema 中无写操作           │
│  · 调查代码库、分析影响范围          │
│  · 输出实装计划（不修改任何文件）     │
│  · 内建约束："不得修改代码"          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Phase 2: Implement (写模式)         │
│  · Explore 的输出注入到 prompt      │
│  · 每次文件编辑后自动跑 lint+format │
│  · stderr 循环检测(3次即终止)        │
│  · 最小权限工具集                    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Phase 3: Review (自审)              │
│  · AI 对照项目规约自审实装结果       │
│  · 检查命名规则、API 格式、架构边界  │
│  · 不合格 → 回流到 Phase 2          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  机械门禁 (无 LLM 依赖的确定性检查)  │
│  · CI 跑通？ Lint 全绿？             │
│  · 类型检查通过？ 测试全过？          │
│  · 架构边界未被突破？                │
│  · 安全关键路径未被修改？             │
└─────────────────────────────────────┘
    │
    ├─ 通过 → Draft PR → 人类 Review
    │
    └─ 不通过 → 回流修复 或 升级为人类任务
```

---

## 三、值得直接抄的 8 个具体做法

### 做法 1：编辑后自动 Lint（Claude Code Hooks 模式）

**原理**：AI 每次编辑文件后，自动触发 lint + format。不是"请 AI 遵守格式"，而是**违规代码根本不可能存在**。

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "cd web && yarn fix:all --quiet 2>/dev/null || true"
      }]
    }]
  }
}
```

**为什么有效**：把"提案"变成"强制"。AI 不需要知道格式规则，工具链自动修正。

---

### 做法 2：条件式 Prompt 组合 — 不是所有指令都该给 AI

**原理**：系统 prompt 被拆成独立的 Markdown 段落，每段有条件谓词。不满足条件的段落不加载。

```python
# 示例：只在 Git 仓库中才加载 Git 工作流指令
sections = [
    Section("identity.md",        condition=None,             priority=1),
    Section("git-workflow.md",    condition=lambda: in_git_repo, priority=5),
    Section("task-tracking.md",   condition=lambda: has_todo,    priority=6),
    Section("provider-openai.md", condition=lambda: provider == "openai", priority=10),
]

# Filter → Sort → Load → Join
active = [s for s in sections if s.condition is None or s.condition()]
active.sort(key=lambda s: s.priority)
system_prompt = "\n".join([load_markdown(s.path) for s in active])
```

**为什么有效**：无关指令不仅浪费 token（工具定义就占 5-7%），还会**稀释**重要指令的注意力权重。

---

### 做法 3：失败复盘笔记 — AI 的"错题本"

**原理**（CCA 论文）：每次任务结束后，专门的笔记 Agent 提取失败经验，按结构化格式持久化。

```markdown
# projects/openlibrary/escaping_wildcards_in_infobase_queries.md

## 问题上下文
搜索作者名包含 '*' 时，Infobase 将其当通配符处理

## 解决方案
在精确/备选名匹配中 escape 星号，但在 surname 匹配中保留通配符

## 关键洞察
1. 上下文相关的 escaping：有些查询要 escape，有些要保留
2. 使用 `r"\*"` 进行 escape
3. 创建新记录时保留原始名称，不用 escaped 版本

## 相关文件
- /app/openlibrary/catalog/add_book/load_book.py — find_author()
```

笔记分为 `shared/`（跨项目通用，如"前缀移除的空字符串边界情况"）和 `projects/`（项目专属）。

**为什么有效**：下次遇到同类问题时，Agent 立即检索已知解法，避免从零重新踩坑。

---

### 做法 4：仓库就绪度评分 — AI Harness Scorecard 的 31 项检查

在让 AI 自主编程之前，先给仓库打分。5 大类 31 项检查，纯确定性（无 LLM）：

```
架构文档化 (20%):   架构文档 / Agent 指令文件 / ADR / 模块边界 / API 文档
机械约束   (25%):   CI / Linter / 类型安全 / 依赖审计 / Conventional Commits
测试稳定性 (25%):   测试套件 / 覆盖率 / Mutation / Property-based / Fuzz / 契约
审查防漂移 (15%):   Code Review 强制 / 定时 CI / 过期文档检测 / PR 模板
AI 安全    (15%):   AI 使用规范 / 小批量强制 / 先设计后编码 / 安全路径标记
```

安装一行命令：`pip install ai-harness-scorecard && ai-harness-scorecard assess .`

输出示例：
```
Grade: B (74.2/100) 
┌──────────────────────┬────────┬───────┬────────┐
│ Category             │ Weight │ Score │ Checks │
├──────────────────────┼────────┼───────┼────────┤
│ Architectural Docs   │ 20%   │ 60%   │ 3/5    │
│ Mechanical Constraint│ 25%   │ 91%   │ 6/7    │
│ Testing & Stability  │ 25%   │ 72%   │ 5/8    │
│ Review & Drift       │ 15%   │ 60%   │ 3/6    │
│ AI-Specific Safety   │ 15%   │ 67%   │ 3/5    │
└──────────────────────┴────────┴───────┴────────┘
```

---

### 做法 5：AX/UX 通道分离 — 给人看的和给 AI 看的不是同一个东西

**原理**（CCA 论文）：人类需要丰富的执行追踪（diff、进度条、色彩），AI 只需要压缩的结构化结果。

```
给人看 (UX):
  Creating file at config.py
  File created successfully at config.py
  Here is the diff:
  + PORT=8080
  + DEBUG=true
  + MAX_CONNECTIONS=100

给 AI 看 (AX):
  <result>File created successfully</result>
```

**为什么有效**：很多框架把人类看的 trace 直接喂给模型，导致上下文膨胀和"虚假锚定"——AI 被自己的调试输出误导。

---

### 做法 6：ADR 共存在代码旁 — 架构决策记录

Explaza 团队的实践：

> 把"为什么放弃 GitHub Actions"的决策理由作为 ADR（Architecture Decision Record）写在代码旁边。
> 
> **"なぜGHAをやめたか"をコードの隣に置いておくことで、将来同じ検討を繰り返さずに済む**

这是上下文工程的一环——AI 在未来的任务中能自动读到这个决策背景，不会再走弯路。

---

### 做法 7：Hard 任务用 Agent Teams — 但用完就杀进程

```typescript
// Hard 任务使用 team-lead Agent
// team-lead 自动 spawn planner + implementer + code-reviewer

// 关键：detached 模式启动，完成即终止
const child = spawn('claude', args, { detached: true })

child.stdout.on('data', (data) => {
  if (data.includes('"type":"result"')) {
    // 检测到完成标志 → 15 秒后清理整个进程组
    setTimeout(() => process.kill(-child.pid, 'SIGTERM'), 15000)
  }
})
// 不是等 120 分钟超时，而是完成即走
```

---

### 做法 8：AGENTS.md 是"目次"不是"百科全书"

OpenAI 的原话：

> AGENTS.md 应该被设计为"目次"——小入口，从中段阶段性地导航到深层信息源。
> 
> 不要把所有上下文一股脑塞给 AI。这会产生**"上下文腐烂"(Context Rot)**——模型在海量信息中迷失方向。

正确的结构：

```markdown
# AGENTS.md（目次）
## 项目概览（3 行）
## 架构约束 → 详见 docs/architecture.md
## 命名规范 → 详见 docs/conventions.md
## API 设计 → 详见 docs/api/
## 常见问题 → 详见 docs/faq.md
```

---

## 四、一句话总结

> **不要让模型更聪明，而是让环境更智能。**
> **不要"请求"AI 遵守规则，而是让违规"不可能发生"。**
> **不要事后修复 AI 的错误，而是建立"AI 修复 AI"的闭环。**

---

## 资料来源

| 资料 | 链接 | 类型 |
|------|------|------|
| OpenAI Harness Engineering | https://openai.com/index/harness-engineering/ | 官方博客 |
| Harness Engineering Playbook | https://github.com/broomva/harness-engineering | 技能库 |
| AI Harness Scorecard | https://github.com/marketplace/actions/ai-harness-scorecard | 评分工具 |
| Zenn 实战博客 (日文) | https://zenn.dev/explaza/articles/6c976d79c094dc | 企业踩坑 |
| OPENDEV 论文 | https://arxiv.org/abs/2603.05344 | arXiv 2603 |
| CCA 论文 | https://arxiv.org/abs/2512.10398 | arXiv 2512 |

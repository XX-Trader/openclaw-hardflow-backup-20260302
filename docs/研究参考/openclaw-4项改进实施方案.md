# OpenClaw 4 项改进实施方案

> 来源：[Claude Code 源码研究](claude-code-源码还原研究.md) 
> 日期：2026-04-01 | 状态：待实施
> 范围：Dream 记忆蒸馏 + Gate 工具集限制 + Worker 自包含 Prompt + VerifyPlanExecution

---

## 一、Dream 记忆蒸馏（含 Codex）

### 1.1 问题

各平台对话记录大量冗余（工具调用原始输出、重复文件内容、调试日志），直接蒸馏效率低且烧 Token。需要先清洗再蒸馏。

### 1.2 对话数据源清单

| 平台 | 对话存储位置 | 格式 |
|------|-------------|------|
| **Gemini** | `~/.gemini/antigravity/brain/*/` | 每个对话一个目录，含 `.system_generated/logs/` |
| **Claude Code** | `~/.claude/transcripts/*.jsonl` | JSONL 格式，每行一条消息 |
| **Codex** | `~/.openclaw/agents/*/sessions/*.jsonl` | 模型为 `openai-codex/*` 的会话 |
| **OpenClaw** | `~/.openclaw/agents/*/sessions/*.jsonl` | 模型为非 codex 的会话 |

### 1.3 处理流水线（4 阶段）

```
阶段 1: Clean（清洗）
├── 去掉工具调用的原始输出（file_read 返回的整文件内容、grep 结果等）
├── 去掉重复片段（同一文件被读取多次保留最后一次）
├── 去掉调试噪音（stack trace、进程日志、pip install 输出）
├── 保留：用户意图、AI 决策理由、最终结论、代码变更摘要
└── 输出：压缩后的对话摘要文件（原大小的 10-20%）

阶段 2: Extract（提取）
├── 从压缩对话中提取：
│   ├── 决策点（为什么选择方案 A 而非 B）
│   ├── 失败教训（什么没用、踩了什么坑）
│   ├── 最佳实践（什么有效、什么模式被复用）
│   └── 架构知识（模块关系、数据流、约束条件）
└── 输出：结构化知识条目

阶段 3: Consolidate（整合）
├── 跨平台去重（同一知识点在 Gemini 和 Claude Code 中都出现）
├── 知识冲突解决（优先取最新的决策）
├── 建立关联图谱（知识 A 与知识 B 的关系）
└── 输出：统一知识库条目

阶段 4: Settle（沉淀）
├── 高频模式 → skills/ (draft 模式，需人工激活)
├── 架构知识 → docs/ 体系
├── 运维经验 → workflows/ 或 hooks/
└── 过时知识 → 标记为 deprecated
```

### 1.4 现有基础设施复用

| 已有组件 | 复用方式 |
|---------|---------|
| MemTidy | 阶段 1 的文件遍历和热/温/冷分层逻辑可复用 |
| `governance_evolution_runner.py（69KB）` | 阶段 2 的增量扫描和提取逻辑可复用 |
| `memory_to_skill_extractor.py` | 阶段 4 的 Skill 封装逻辑可复用 |
| `self_evolution_todo.py` | 阶段 3 的知识产出逻辑可复用 |

### 1.5 Codex 专项处理

Codex 对话的特殊性：
- 模型标识：`openai-codex/gpt-5.4`、`openai-codex/gpt-5.3-codex` 等
- 共用 OpenClaw agent sessions 目录，需按 `model` 字段过滤
- Codex 对话通常更重代码、少文字，清洗规则需适配

### 1.6 触发策略

| 触发条件 | 配置 |
|----------|------|
| 定时触发 | 每日凌晨 03:30，接在 MemTidy 之后 |
| 阈值触发 | 距上次蒸馏 > 24h + 各平台合计新增 5+ 对话 |
| 手动触发 | `/dream run` 或 Telegram 指令 |

### 1.7 实施步骤

1. **新建脚本** `scripts/openclaw-ops/dream_distiller.py`
   - 参数：`--sources gemini,claude,codex,openclaw`（可选择性指定）
   - 参数：`--mode clean|extract|full`（可只做清洗或全流程）
   - 参数：`--since-hours 24`（时间窗口）
   - 参数：`--dry-run`（预览不执行）
2. **新建清洗规则** `config/dream_clean_rules.json`
   - 各平台的噪音模式正则
   - 保护模式（不应清洗的内容模式）
3. **新建 Cron 任务**，加入 `jobs.json`
4. **文档三件套**：`docs/专项场景工作流/Dream记忆蒸馏工作流/` 下的 README.md、architecture.md、implementation-plan.md

---

## 二、Gate 阶段工具集限制（#9）

### 2.1 核心理念

参考 Claude Code 的 `EnterPlanModeTool` / `ExitPlanModeTool`：在不同的 HardFlow Gate 阶段，**动态限制 Agent 可用的工具集**，从根源防止 Agent 在研究阶段乱改代码。

### 2.2 工具集矩阵

| HardFlow Gate | 允许工具 | 禁止工具 | 目的 |
|---------------|---------|---------|------|
| **G0 Research** | file_read, grep, glob, web_search, web_fetch | file_write, file_edit, exec(写操作) | 只读调研 |
| **G1 Synthesis** | file_read, file_write(仅 docs/), grep | file_edit(src/), exec(构建) | 只写文档 |
| **G2 Implementation** | 完整工具集 | — | 正式编码 |
| **G3 Verification** | exec(测试命令), file_read, grep | file_edit, file_write | 只测不改 |
| **G4 Review** | file_read, grep, glob | file_edit, file_write, exec | 纯审查 |
| **G5 Deploy** | exec(部署命令), file_read | file_edit | 部署操作 |
| **G6 Monitor** | exec(监控命令), file_read | file_write, file_edit | 运行监控 |

### 2.3 实施方式

**核心改动点：HardFlow 调度器的 preflight 阶段**

```python
# 概念伪代码 — 在 task_executor 的 preflight 中注入工具约束

GATE_TOOL_POLICY = {
    "G0": {
        "allow": ["file_read", "grep", "glob", "web_search", "web_fetch"],
        "deny_message": "当前处于 G0 Research 阶段，禁止写操作。请先完成调研再进入 G1。"
    },
    "G1": {
        "allow": ["file_read", "file_write:docs/*", "grep"],
        "deny_message": "当前处于 G1 Synthesis 阶段，只能编写设计文档。"
    },
    "G2": {
        "allow": ["*"],  # 完整权限
        "deny_message": None
    },
    "G3": {
        "allow": ["exec:test*", "file_read", "grep"],
        "deny_message": "当前处于 G3 Verification 阶段，禁止修改代码。"
    },
    "G4": {
        "allow": ["file_read", "grep", "glob"],
        "deny_message": "当前处于 G4 Review 阶段，纯只读审查。"
    }
}
```

**拦截点**：在 Gateway 处理 Agent 工具调用请求时检查当前 Gate 阶段，非法调用直接返回 `deny_message`。

### 2.4 文件变更清单

| 文件 | 变更 |
|------|------|
| `scripts/hardflow/score-policy.json` | 新增 `gate_tool_policy` 字段 |
| `scripts/hardflow/hardflow_orchestrator.py`（或等价调度入口） | preflight 中读取 policy 并注入约束 |
| Agent SOUL.md 模板 | 新增 Gate 阶段工具约束提示 |

### 2.5 实施步骤

1. **扩展 `score-policy.json`**，新增 `gate_tool_policy` 配置节
2. **修改 HardFlow 调度器**，在 Gate 切换时注入 `allowed_tools` 到 Agent 的系统提示词
3. **Agent SOUL.md 中声明**：当前处于哪个 Gate，可以用什么工具
4. **测试**：手动触发一个 G0 任务，验证 Agent 调用 `file_write` 时被拦截

---

## 三、Worker 自包含 Prompt 规范（#2）

### 3.1 核心原则

参考 Claude Code Coordinator 的铁律：**Worker 看不到 Coordinator 的对话，每个 prompt 必须完全自包含**。

### 3.2 Prompt 模板

```markdown
## 任务：{task_title}

### 目标
{明确的、可验证的目标描述}

### 上下文
- 项目：{项目名称和路径}
- 相关文件：
  - `{file_path_1}` — {该文件与任务的关系}
  - `{file_path_2}:L{start}-L{end}` — {具体行号和内容}
- 背景：{为什么要做这个任务，前置条件是什么}

### 完成标准
1. {具体条件 1}
2. {具体条件 2}
3. 验证方式：{如何确认任务完成}

### 约束
- ❌ 不要修改 {protected_files}
- ❌ 不要执行 {forbidden_operations}
- ✅ 必须保持 {invariants}

### 当前 Gate 阶段
{G0/G1/G2/...}，可用工具：{tool_list}
```

### 3.3 实施方式

这是**纯规范层面**的改进，不需要写新基建代码：

1. **文档化**：在 `docs/基础设施/协议与规范/` 下新建 `worker-prompt-specification.md`
2. **模板化**：在 `docs/templates/` 下新建 `WORKER_TASK_PROMPT_TEMPLATE.md`
3. **嵌入 task_executor**：修改 `task_executor_runner.py`，在派发任务时使用模板填充 prompt
4. **Coordinator SOUL.md 中强调**：派发任务时必须使用自包含模板

### 3.4 成果回传格式

统一 Worker 任务执行结果的回传格式：

```json
{
  "task_id": "task-abc123",
  "gate": "G2",
  "status": "completed",
  "summary": "一句话描述做了什么",
  "files_modified": [
    {"path": "src/api/views.py", "action": "modified", "lines_changed": 15},
    {"path": "tests/test_api.py", "action": "created", "lines_changed": 42}
  ],
  "verification": {
    "tests_run": "pytest tests/test_api.py",
    "tests_passed": true,
    "coverage_delta": "+2.1%"
  },
  "token_usage": {"input": 12500, "output": 3200},
  "duration_seconds": 45
}
```

---

## 四、VerifyPlanExecution（#8）

### 4.1 核心理念

参考 Claude Code 的 `VerifyPlanExecutionTool`：复杂任务执行后，自动对比"计划做什么" vs "实际做了什么"。

### 4.2 与 Gate 工具集限制的关系

#8 和 #9 是一套东西：
- **#9 Gate 限制** = 事前约束（规定每个阶段能做什么）
- **#8 VerifyPlan** = 事后核验（检查是否按计划执行了）

### 4.3 核验维度

| 核验项 | 做法 |
|--------|------|
| 文件覆盖 | 计划修改的文件列表 vs 实际 git diff 的文件列表 |
| 范围越界 | 检查是否修改了计划外的文件 |
| 测试状态 | 计划要求的测试是否执行且通过 |
| 完成标准 | 逐条检查 Prompt 中列出的完成标准 |

### 4.4 实施方式

**作为 HardFlow G3（Verification）阶段的自动步骤**：

```python
# 概念伪代码
def verify_plan_execution(plan: dict, execution_result: dict) -> VerifyReport:
    report = VerifyReport()
    
    # 1. 文件覆盖检查
    planned_files = set(plan["files_to_modify"])
    actual_files = set(execution_result["files_modified"])
    report.missing = planned_files - actual_files      # 计划改但没改的
    report.unexpected = actual_files - planned_files    # 没计划但改了的
    
    # 2. 完成标准逐条检查
    for criterion in plan["completion_criteria"]:
        report.criteria_met[criterion] = check_criterion(criterion, execution_result)
    
    # 3. 测试验证
    if plan.get("required_tests"):
        report.test_results = run_tests(plan["required_tests"])
    
    # 4. 产出验证报告
    report.verdict = "PASS" if report.is_all_met() else "FAIL"
    report.fail_reasons = report.get_failures()
    
    return report
```

### 4.5 文件变更清单

| 文件 | 变更 |
|------|------|
| `scripts/hardflow/hardflow_orchestrator.py` | G3 阶段自动调用 verify 逻辑 |
| 新建 `scripts/hardflow/verify_plan_execution.py` | 独立核验脚本 |
| `score-policy.json` | G3 评分中加入 plan-vs-execution 对比权重 |

### 4.6 实施步骤

1. **新建 `verify_plan_execution.py`**
   - 输入：plan JSON（G1 阶段产物） + execution result JSON（G2 阶段产物）
   - 输出：核验报告 JSON/MD
2. **嵌入 HardFlow G3**：G3 开始时自动调用核验
3. **核验不通过 → 触发回流**：回到 G2 整改

---

## 五、总结与实施顺序

| 步骤 | 改进项 | 优先做什么 | 预估工作量 |
|------|--------|-----------|-----------|
| 1 | #2 Worker 自包含 Prompt | 先写模板和规范文档 | 1-2 小时（纯文档） |
| 2 | #9 Gate 工具集限制 | 扩展 score-policy.json + 修改调度器 | 4-6 小时 |
| 3 | #8 VerifyPlanExecution | 新建核验脚本 + 嵌入 G3 | 3-4 小时 |
| 4 | Dream 记忆蒸馏 | 新建 dream_distiller.py + 清洗规则 | 8-12 小时（最复杂） |

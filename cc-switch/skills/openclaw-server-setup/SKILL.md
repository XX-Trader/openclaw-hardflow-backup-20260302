# OpenClaw + Codex CLI 多 Agent 标准作业手册（最新）
版本: 3.0.0
更新时间: 2026-03-02（北京时间）

## 1. 目标与原则

本手册是当前生产可用的 OpenClaw 运行基线，核心目标:
- 入口统一
- 任务结构清晰
- 可观测与可追踪
- 低 token 成本优先
- 旧流程不兼容，直接清理

当前架构不使用 `secretary-agent`，已统一为 `coordinator` 直连入口。

## 2. 当前架构（已确认）

### 2.1 入口与编排
- 外部入口: Telegram
- 入口绑定: `coordinator`
- 规划角色: `coordinator`
- 项目上下文助手: `project-agent`

### 2.2 角色职责
- `coordinator`: 任务澄清、风险分级、任务包生成、任务分配、重试/升级判定。
- `project-agent`: 维护项目索引（README/API/模块/流程），负责拉最新代码和生成结构化项目信息，不直接执行开发改动。
- `frontend-dev/backend-dev/reviewer/tester/deployer/ops-agent/optimize-agent/doc-writer`: 执行与反馈。

## 3. 目录约定（禁止写死路径）

统一使用环境变量，默认值如下:

```bash
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$OPENCLAW_HOME/openclaw.json}"
TASK_CENTER_DIR="${TASK_CENTER_DIR:-$OPENCLAW_HOME/ops/task-center}"
WORKFLOW_IO_DIR="${WORKFLOW_IO_DIR:-$TASK_CENTER_DIR/workflow-io}"
AGENT_LOG_ROOT="${AGENT_LOG_ROOT:-$TASK_CENTER_DIR/agents}"
PROJECT_REGISTRY="${PROJECT_REGISTRY:-$TASK_CENTER_DIR/project-registry.json}"
TOKEN_PRICING_FILE="${TOKEN_PRICING_FILE:-$TASK_CENTER_DIR/token-pricing.json}"
WORKFLOW_SNAPSHOT_DIR="${WORKFLOW_SNAPSHOT_DIR:-$HOME/openclaw-workflow-latest}"
```

## 4. 任务模型（todo/jobs）

### 4.1 双池模型
- `todo`: 延时任务、低优先级、可批处理。
- `jobs`: 立即处理任务、高优先级、阻断风险任务。

### 4.2 任务字段（原子化）
每条任务必须记录:
- `task_id`（唯一，后端保存，不要求前台展示）
- `task_type`（workflow/manual/cron/planner）
- `reason`（为什么要做）
- `created_at` / `scheduled_at`
- `source`（入口来源）
- `priority`（high/medium/low）
- `risk_level`（high/low）
- `assignee`（分配给哪个 agent 或 human）
- `status`（pending/running/passed/failed/escalated）
- `retry_count` / `failure_count`
- `observable_outputs`（文件/API/状态/消息）
- `acceptance_thresholds`（阈值）
- `score`（评分）
- `token_usage`（按 agent 聚合）
- `cost_estimate`（按模型单价估算）

### 4.3 分配规则
- 高风险任务: 人工确认后分配。
- 低风险任务: 自动分配。
- 同一任务连续失败 >= 3 次: 自动升级人工，并附带问题详情、修复方案、修复结果。

## 5. 需求-结果-验收-评分-动作闭环

统一流程:
1. 需求: 做什么、为什么。
2. 结果: 可观测输出（文件/API/状态/消息）。
3. 验收: 明确阈值（通过线）。
4. 评分: 结果权重 70 + 稳定性权重 35。
5. 动作: 通过 / 重试 / 升级人工。

评分建议:
- `raw_score = result_score * 0.70 + stability_score * 0.35`（满分 105）
- `normalized_score = raw_score / 105 * 100`（用于统一展示）
- 默认通过线: `raw_score >= 75` 且关键验收项全部通过。

## 6. Token 与费用统计（M 单位）

### 6.1 统计要求
对以下对象都要统计 token 与费用:
- 所有工作流执行
- 所有定时任务
- 所有 agent 调用
- 每日总结（按 agent 维度 + 全局维度）

单位:
- token 展示单位使用 `M`（百万 token）
- 费用使用估算值（基于本地价格表，不每次外查）

### 6.2 定价配置（可扩展）
统一维护到 `token-pricing.json`，新增模型只改这里。

示例:

```json
{
  "version": "2026-03-02",
  "currency": "CNY",
  "unit": "per_1m_tokens",
  "models": {
    "glmcode/glm-5": {"input": 0, "output": 0},
    "kimicode/kimi-k2.5": {"input": 0, "output": 0},
    "glmcode/glm-4.7": {"input": 0, "output": 0}
  }
}
```

新增模型步骤:
1. 在 `models.providers` 增加模型定义。
2. 在 `agents.defaults.model.fallbacks` 或具体 agent 中配置引用。
3. 在 `token-pricing.json` 增加该模型价格。
4. 重启 OpenClaw 并验证。

## 7. 日志与留痕（必须）

### 7.1 工作流 I/O 留痕
每一步都记录:
- 输入摘要
- 输出摘要
- 状态
- 耗时
- token/cost
- 错误信息（如有）

建议目录:

```bash
$WORKFLOW_IO_DIR/<date>/<task_id>/step-*.json
```

### 7.2 按 agent 归档
- 每个 agent 单独目录存档日志。
- 定时任务日志按所属 agent 归档，不混写。

建议目录:

```bash
$AGENT_LOG_ROOT/<agent_id>/YYYY-MM-DD/*.jsonl
```

### 7.3 分析留痕
所有 AI 分析必须留文档，支持增量分析:
- 分析了哪些源
- 分析到哪一段
- 本次增量范围
- 结论与下一步

## 8. Project-Agent 运行规则

### 8.1 职责边界
- 维护项目索引文档（项目说明、模块说明、API、运行流程、修改流程）。
- 定时 `git pull --ff-only`，更新索引。
- 输出结构化上下文给 `coordinator`。
- 不直接改业务代码。

### 8.2 项目文档位置
- OpenClaw 配置与脚本在 `OPENCLAW_HOME`。
- 项目说明文档在项目仓库内部（例如 `docs/project-index/...`）。

### 8.3 低 token 策略
- 已工具化的固定流程优先走脚本。
- AI 只做决策层和异常判定。
- 重复任务沉淀为代码，不反复消耗推理 token。

## 9. 标准操作（服务器）

### 9.1 连接服务器

```bash
ssh -F "D:/学习资料/ssh_keys/ssh_config" hangqing-zhongxin
```

### 9.2 清理秘书 agent（当前基线已执行）

```bash
rm -rf "$OPENCLAW_HOME/workspace-secretary-agent"
rm -rf "$OPENCLAW_HOME/agents/secretary-agent"
```

### 9.3 生成最新工作流快照

```bash
rm -rf "$WORKFLOW_SNAPSHOT_DIR"
mkdir -p "$WORKFLOW_SNAPSHOT_DIR"/{config,docs,scripts,agents}

cp "$OPENCLAW_CONFIG" "$WORKFLOW_SNAPSHOT_DIR/config/openclaw.json"
cp "$TASK_CENTER_DIR/token-pricing.json" "$WORKFLOW_SNAPSHOT_DIR/config/token-pricing.json"
cp "$TASK_CENTER_DIR/project-registry.json" "$WORKFLOW_SNAPSHOT_DIR/config/project-registry.json"
cp "$TASK_CENTER_DIR/REQUIREMENT_RESULT_FLOW.md" "$WORKFLOW_SNAPSHOT_DIR/docs/"
cp "$TASK_CENTER_DIR/PROJECT_AGENT_WORKFLOW.md" "$WORKFLOW_SNAPSHOT_DIR/docs/"
cp "$TASK_CENTER_DIR/TOKEN_PRICING.md" "$WORKFLOW_SNAPSHOT_DIR/docs/"
cp "$TASK_CENTER_DIR/WORKFLOW_CONSOLIDATION_REPORT.md" "$WORKFLOW_SNAPSHOT_DIR/docs/"
cp "$OPENCLAW_HOME/ops/project_index_maintainer.py" "$WORKFLOW_SNAPSHOT_DIR/scripts/"
cp "$OPENCLAW_HOME/workspace-coordinator/SOUL.md" "$WORKFLOW_SNAPSHOT_DIR/agents/coordinator.SOUL.md"
cp "$OPENCLAW_HOME/workspace-project-agent/SOUL.md" "$WORKFLOW_SNAPSHOT_DIR/agents/project-agent.SOUL.md"
```

### 9.4 同步到本地用户目录

```bash
scp -F "D:/学习资料/ssh_keys/ssh_config" -r \
  hangqing-zhongxin:"$WORKFLOW_SNAPSHOT_DIR" \
  C:/Users/superma/.openclaw/
```

## 10. 配置检查清单

每次改完都检查:
- `openclaw.json` 不含 `secretary-agent`。
- `bindings` 入口仍是 `coordinator`。
- `project-agent` 在 `agents.list` 存在。
- `agentToAgent.allow` 包含 `project-agent`。
- `token-pricing.json` 可解析、模型键齐全。
- `project-registry.json` 中项目路径有效。

## 11. 每日总结输出要求

每日总结必须包含:
- 全局 token 使用量（M）
- 全局费用估算
- 每个 agent 的 token 使用量（M）
- 每个 agent 的费用估算
- 当日 todo/jobs 处理统计
- 高风险任务占比、升级人工数量
- 失败>=3 次任务明细

并附带:
- `done.md`
- 定时任务执行摘要
- 异常任务修复记录

## 12. 常见问题

- 问: 后续新增模型会不会改很多地方？
  答: 不会。统一改三处: provider、agent model 引用、`token-pricing.json`。

- 问: OpenClaw 目录会不会写死？
  答: 不会。统一用 `OPENCLAW_HOME` 及衍生变量。

- 问: 是否保留旧流程兼容？
  答: 当前策略是不兼容旧流程，直接清理死代码。

## 13. 当前生效结论

- 已移除 `secretary-agent`。
- 已启用 `project-agent`。
- 已保留并强化 `coordinator` 作为统一入口编排者。
- 已具备 todo/jobs、评分闭环、token 费用估算、日志留痕、快照归档的统一规范。

# Policy Enforcer（OpenClaw 硬约束）

本目录提供 OpenClaw 工作流的 fail-close 策略执行层，目标是把“规范建议”升级为“不可绕过的硬约束”。

## 1. 核心能力

- 单入口与单分配：仅 `coordinator` 可作为入口与分配者。
- 任务原子字段：创建任务时强制 `reason/requirement/result_output/acceptance/observable_outputs/acceptance_thresholds`。
- 风险门禁：高风险任务必须人工确认后才能执行。
- 失败升级：同任务失败 `>=3` 次自动升级人工。
- 评分闭环：`raw_score = result_score * 0.70 + stability_score * 0.30`。
- token/cost 门禁：未记录 token/cost 的任务不能 `complete-task`。
- 可观测记录：任务、阶段、token、事件全部入库并可导出报告。
- 模块与通信日志：统一记录模块内部状态与模块间通信状态，支持故障归因（模块/通信/流程）。
- Agent 回报闭环：agent 完成后回传规划者（完成度、解决项、失败项、token、时长、质量评分、模型）。
- 异常通知策略：默认仅异常回报触发聊天消息，正常完成仅回传规划者与任务中心。
- TODO 调度规则：按“无可执行时间 or 到点可执行”优先，再排未来任务。
- 日报模板：按 agent+全局统计 token/cost，附高风险占比、升级数、失败>=3明细。
- 身份留痕：所有发送消息脚本与任务事件统一标注 `sender_identity/actor`。

## 2. 目录文件

- `policy_enforcer.py`：策略入口 CLI（门禁、路由、核查、日报、报告）。
- `task_center.py`：SQLite 任务中心（任务/事件/阶段/token 原子化存储）。
- `policy-config.json`：硬约束策略配置。
- `routing-rules.json`：任务路由规则（可在线增量更新）。
- `token-pricing.json`：本地价格表（单位 `per_1m_tokens`）。
- `FIELD_DICTIONARY.md`：日志/通信/回报/统计字段标准字典（多 agent 统一接入）。
- `runtime.env.example`：环境变量模板（避免路径写死）。
- `bootstrap_multi_project.py`：多项目自适应安装器。
- `project_index_maintainer.py`：`project-agent` 项目索引维护器（可选 git pull），并维护动态文档知识索引（stack/API endpoints/official docs update checks/direct-fetch cache/search-index）。

## 3. 环境变量（推荐）

可直接参考并落地：

```bash
cp scripts/openclaw-ops/policy/runtime.env.example .workflow/policy.runtime.env
```

重点变量：

- `OPENCLAW_HOME`
- `TASK_CENTER_DIR`
- `PROJECT_REGISTRY`
- `TOKEN_PRICING_FILE`
- `POLICY_DB_FILE/POLICY_FILE/POLICY_ROUTING_FILE/POLICY_PRICING_FILE`

## 4. 快速初始化

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py init \
  --db .workflow/task-center/task_center.db \
  --policy-file scripts/openclaw-ops/policy/policy-config.json \
  --routing-file scripts/openclaw-ops/policy/routing-rules.json \
  --pricing-file scripts/openclaw-ops/policy/token-pricing.json
```

## 5. 常用命令

创建任务（硬约束字段）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py create-task \
  --task-id wf-20260302-demo \
  --task-type workflow \
  --reason "修复 cron 超时" \
  --source cron \
  --priority high \
  --risk-level high \
  --pool jobs \
  --entry-agent coordinator \
  --assignee coordinator \
  --requirement "将超时阈值统一为 30 分钟并补告警" \
  --result-output "任务状态 passed 且无超时告警" \
  --acceptance "连续 3 次调度成功" \
  --observable-outputs "文件/接口状态/消息回执" \
  --acceptance-thresholds "3/3 调度成功；关键检查项全部通过"
```

记录 token/cost：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py record-token \
  --task-id wf-20260302-demo \
  --agent-id backend-dev \
  --model kimicode/Doubao-Seed-2.0-Code \
  --input-tokens 12000 \
  --output-tokens 8000
```

记录模块运行日志（标准化）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py log-module \
  --task-id wf-20260302-demo \
  --module-name planner \
  --phase dispatch \
  --level info \
  --status running \
  --message "planner dispatch task to backend-dev" \
  --duration-ms 180
```

记录模块间通信日志（标准化）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py log-communication \
  --task-id wf-20260302-demo \
  --from-module planner \
  --to-module backend-dev \
  --protocol internal-event \
  --message-type task_handoff \
  --status acked \
  --latency-ms 72 \
  --correlation-id corr-20260302-001
```

Agent 完成任务后回报规划者（异常才发聊天）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py report-agent-result \
  --task-id wf-20260302-demo \
  --agent-id backend-dev \
  --planner-id coordinator \
  --status passed \
  --solved true \
  --resolved-issues "cron timeout,retry policy" \
  --resolution-summary "统一超时阈值并修复重试参数" \
  --resolution-steps "定位日志,修改配置,灰度验证" \
  --failure-count 0 \
  --duration-ms 248000 \
  --model kimicode/Doubao-Seed-2.0-Code \
  --input-tokens 12000 \
  --output-tokens 8000 \
  --cost-estimate 0.36 \
  --quality-score 92 \
  --quality-grade a
```

说明（2026-03）：
- `report-agent-result` 会同步回写 `tasks.status` 与 `tasks.action`，避免任务长期停留在 `pending`。
- 映射规则：`passed -> passed/pass`，`failed -> failed/retry`，达到失败阈值自动升级为 `escalated/escalate_human`。
- 聊天消息仍遵循“仅异常发送”，正常成功路径返回 `NO_REPLY`。

历史状态回填（修复旧数据）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py reconcile-task-status \
  --dry-run \
  --limit 2000

python3 scripts/openclaw-ops/policy/policy_enforcer.py reconcile-task-status \
  --limit 2000
```

规划者统计（任务完成情况/agent完成质量）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py planner-summary \
  --planner-id coordinator \
  --since 2026-03-01T00:00:00+00:00 \
  --limit 200
```

完成任务（评分闭环）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py complete-task \
  --task-id wf-20260302-demo \
  --result-score 92 \
  --stability-score 88 \
  --critical-pass true
```

任务路由建议：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py route-task \
  --description "产品经理：梳理项目模块边界并给出迭代计划" \
  --source ops
```

说明：
- 当消息前缀命中 `产品经理/项目经理/PM` 时，路由会直达 `project-agent`（可绕过规划者分发，用于需求沟通与规划）。
- 常规任务仍走规划者分发；若分发失败，可触发规划者兜底自执行并留痕。

TODO 队列按时间 FIFO 拉取（限流）：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py next-todo --limit 3
```

规则说明：
- `scheduled_at` 为空或已到达当前时间的任务优先返回。
- 未到时间的未来任务仍会排在后面，避免遗漏 backlog。

动态更新风险规则（聊天驱动）：

```bash
python3 scripts/openclaw-ops/policy/risk_rule_sync.py \
  --routing-file scripts/openclaw-ops/policy/routing-rules.json \
  batch \
  --apply-default-preset \
  --add-high "api契约升级" \
  --add-low "网络临时抖动"
```

周度自我进化（边界约束）：

- 只输出建议与任务包，不自动改工作流/技能。
- 默认写入 TODO，低优先级、高风险、需人工确认。
- 周度全量复盘，按 FIFO 带时间入队，并限制每次产出数量。

任务可观测报告：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py task-report \
  --task-id wf-20260302-demo \
  --output .workflow/task-center/wf-20260302-demo.report.json
```

日报：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py daily-summary \
  --date 2026-03-02 \
  --output .workflow/task-center/daily-2026-03-02.md
```

配置核查清单：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py check-config \
  --openclaw-config openclaw/openclaw.json \
  --project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --strict
```

## 6. 多项目安装

详见 [MULTI_PROJECT_INSTALL.md](./MULTI_PROJECT_INSTALL.md)。

最小命令：

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py \
  --project-root /srv/project-a \
  --project-root /srv/project-b \
  --openclaw-home ~/.openclaw
```

## 7. Project-Agent 规范

- `project-agent` 负责规划与派工（可分配执行任务），但不直接修改业务代码。
- 支持 `git pull --ff-only` 后更新项目索引（README/API/模块/流程）。
- 输出索引供 `coordinator` 做任务规划和风险分派。

## Context Gate

See CONTEXT_GATE.md for request_source split, AI context completeness gate, and clarification workflow.

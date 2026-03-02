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
- 日报模板：按 agent+全局统计 token/cost，附高风险占比、升级数、失败>=3明细。

## 2. 目录文件

- `policy_enforcer.py`：策略入口 CLI（门禁、路由、核查、日报、报告）。
- `task_center.py`：SQLite 任务中心（任务/事件/阶段/token 原子化存储）。
- `policy-config.json`：硬约束策略配置。
- `routing-rules.json`：任务路由规则（可在线增量更新）。
- `token-pricing.json`：本地价格表（单位 `per_1m_tokens`）。
- `runtime.env.example`：环境变量模板（避免路径写死）。
- `bootstrap_multi_project.py`：多项目自适应安装器。
- `project_index_maintainer.py`：`project-agent` 项目索引维护器（可选 git pull）。

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
  --description "生产 cron 连续失败并触发告警，需要立即处理" \
  --source ops
```

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
  --project-registry .workflow/project-index/project-registry.json \
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

- `project-agent` 仅维护项目索引，不直接修改业务代码。
- 支持 `git pull --ff-only` 后更新项目索引（README/API/模块/流程）。
- 输出索引供 `coordinator` 做任务规划和风险分派。

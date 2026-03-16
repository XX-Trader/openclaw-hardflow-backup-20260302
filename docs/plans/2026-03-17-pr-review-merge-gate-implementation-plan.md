# PR 审查与自动合并改造方案

## 背景

当前仓库已经有两段可复用能力，但职责边界还不够清楚：

- `governance_evolution_runner.py` 已支持受控改动、可选 push、可选创建 PR。
- `reviewer_cron_runner.py` 已支持 PR 检查、approval file、可选自动 merge。

问题在于，`reviewer` 仍保留了“高频全仓扫描器”的历史定位，而 `pm-website` 这类运行节点更需要稳定，不适合再承担重型仓库巡检。因此需要把职责收口成一条更稳的闭环：

`治理/优化 agent 产出改动 -> 创建或更新 PR -> reviewer 只审查 PR -> 命中 gate 才自动合并`

## 目标

把 `reviewer` 从“高频全仓巡检器”收口成“PR 审查与自动合并 gate”，形成一条受控、可回滚、可留痕的自动化链路。

## 适用范围

- 适用节点：`pm-website` 这一类线上运行节点
- 适用改动：受控 agent 生成的低到中风险 workflow / ops 仓库改动
- 不适用：
  - 高风险生产配置变更
  - 需要人工业务判断的改动
  - 涉及数据库 / 删除数据 / 权限升级的操作

## 新的职责边界

### `ops_governance_evolution_incremental`

新的推荐职责：

- 发现可落地的治理/优化改动
- 生成受控分支
- 提交改动、push 分支
- 创建或更新 PR
- 记录 PR URL、PR 编号、失败原因

它是“改动生产者”和“PR 创建者”，不是最终合并者。

### `reviewer`

新的推荐职责：

- 只看 open PR
- 只做审查、风险判断、merge gate
- 命中 approval file 才允许自动合并
- 审查失败时只报告、挂起、建 follow-up task

它是“PR reviewer”和“merge gate”，不再是运行节点上的高频全仓扫描器。

## 明确不做的事

- 不让 `reviewer` 在运行节点上继续高频扫整个仓库
- 不让 `reviewer` 直接改代码再 merge
- 不让运行节点自动 push 主分支
- 不把“审查失败”自动等价成“回退主分支”

## 目标行为

1. `governance evolution` 发现一组可落地改动。
2. 生成分支、提交、push，并创建或更新 PR。
3. `reviewer` 只扫描 open PR，不再以 repo diff 为主输入。
4. `reviewer` 给出结论：
   - 通过：按 approval gate 自动 merge
   - 不通过：产出报告、保留 PR、创建 follow-up task
5. 全链路留痕至少包括：
   - 分支名
   - PR URL / PR 编号
   - reviewer 结论
   - merge 结果
   - 失败原因

## 自动合并前置约束

自动合并必须同时满足以下条件：

- PR 来自受控 agent 或受控分支
- reviewer 审查结论通过
- `merge approval file` 命中
- 必要验证通过
- 没有高风险 `risk_reasons`

审查失败只产出报告和 follow-up task，不自动回退 `main`。

## 代码修改清单

### 一、文档与索引

涉及文件：

- `docs/plans/2026-03-13-workflow-architecture-manifesto.md`
- `scripts/openclaw-ops/CRON_TASK_INDEX.md`
- `scripts/openclaw-ops/README.md`

要修改的内容：

- 把 `reviewer_git_update_hourly` 的推荐口径改成“PR 检查 / open PR review / 可选 merge gate”
- 把 `ops_governance_evolution_incremental` 的推荐口径改成“改动生产者 + 可选 auto-pr”
- 把本方案文档加入 README 索引

### 二、治理链输出 PR 元数据

涉及文件：

- `scripts/openclaw-ops/governance_evolution_runner.py`
- `tests/scripts_openclaw_ops/test_governance_evolution_runner.py`

要修改的内容：

- 统一 `auto_pr` 报告结构
- 成功时稳定输出：
  - `attempted`
  - `ok`
  - `branch`
  - `pr_url`
  - `pr_number`
- 失败时稳定输出 reason，例如：
  - `no_commits_ahead_base`
  - `worktree_dirty`
  - `gh_pr_create_failed:*`
- 必要时把 reviewer follow-up task 与 PR URL 关联起来

### 三、把 reviewer 收口为 PR 审查 gate

涉及文件：

- `scripts/openclaw-ops/reviewer_cron_runner.py`
- `scripts/openclaw-ops/install_reviewer_scan_jobs.py`
- `tests/scripts_openclaw_ops/test_reviewer_pr_gate.py`
- `tests/scripts_openclaw_ops/test_cron_quiet_modes.py`

要修改的内容：

- `hourly_git` 或后续替代模式优先看 open PR，而不是 repo diff
- 明确 merge 条件：
  - 来源分支匹配
  - approval file 命中
  - reviewer 结论通过
  - 没有高风险 `risk_reasons`
- merge 失败时只报告，不自动回退
- job 文案改成“PR 审查 / merge gate”，不再写成“小时级全仓扫描”

### 四、安装链支持 PR gate 策略

涉及文件：

- `scripts/openclaw-ops/install_workflow_profile.py`
- `scripts/openclaw-ops/policy/workflow_setup.py`
- `scripts/openclaw-ops/export_schedule_registry.py`
- `tests/scripts_openclaw_ops/test_cron_quiet_modes.py`

要修改的内容：

- 安装器明确支持“governance auto-pr + reviewer gate”的组合
- `pm-website` 推荐策略下，不恢复 reviewer 全仓高频审查
- schedule registry 能输出“PR 审查 / 自动合并 gate”职责说明

## 推荐实施顺序

### 第一步：先补测试，再改实现

优先加两组测试：

- `governance_evolution_runner.py` 的 PR 元数据测试
- `reviewer` 的 PR gate 测试

目标是先把新职责的输入/输出结构钉住，避免边改边漂移。

### 第二步：补 governance PR 元数据

先让治理链把 PR URL、编号、分支名、失败原因稳定写出来。  
没有这层稳定元数据，后面的 reviewer 无法可靠做 gate。

### 第三步：收口 reviewer

把 reviewer 从“repo scan”改成“PR review gate”，并把 merge gate 条件写死。

### 第四步：改安装链和 registry

让 profile 安装器和 schedule 导出也使用新的职责描述，避免代码改完但文档/安装器还在说旧话。

### 第五步：只在 `pm-website` 灰度

先单机灰度，不直接全量推广到所有服务器。

## `pm-website` 灰度落地步骤

### 1. 先备份运行态

至少备份：

- `~/.openclaw/cron/jobs.json`
- `~/.openclaw/ops/reviewer_cron_runner.py`
- `~/.openclaw/ops/governance_evolution_runner.py`
- `~/.openclaw/ops/install_reviewer_scan_jobs.py`
- `~/.openclaw/ops/install_workflow_profile.py`

### 2. 同步新脚本并重装 reviewer job

灰度原则：

- 不恢复 `reviewer_incremental_daily_4am`
- 不恢复全仓高频 reviewer 扫描
- 只保留 reviewer 的 PR 审查 / merge gate 能力

### 3. 准备 approval file

建议使用：

`~/.openclaw/ops/reviewer-merge-approval.json`

最小结构：

```json
{
  "approved_prs": [],
  "approved_branches": []
}
```

后续可以扩展：

- `approved_labels`
- `approved_agents`
- `blocked_branches`

### 4. 运行态验收

建议至少执行：

```bash
openclaw cron status --json
openclaw cron run <reviewer_job_id> --force
openclaw cron runs --id <reviewer_job_id> --limit 20
```

验收标准：

- reviewer 能看到 open PR
- 非命中 approval file 的 PR 不 merge
- 命中 approval file 且通过审查的 PR 才 merge
- 审查失败时只报告，不回退主分支

## 测试与验收要求

### 本地测试

至少补并执行：

```bash
py -3 -m pytest tests/scripts_openclaw_ops/test_governance_evolution_runner.py -q
py -3 -m pytest tests/scripts_openclaw_ops/test_reviewer_pr_gate.py -q
py -3 -m pytest tests/scripts_openclaw_ops/test_cron_quiet_modes.py -k 'reviewer or workflow_profile' -q
```

### 运行态验收

至少确认：

- governance 能稳定创建或更新 PR
- reviewer 能识别 PR
- reviewer 只对受控 PR 执行 merge gate
- merge 失败时有明确风险报告

## 回滚方案

如果灰度失败，按以下顺序回滚：

1. 关闭 governance `--auto-pr`
2. reviewer 改回只保留周结构审查
3. 恢复旧 `jobs.json`
4. 保留已创建 PR，不自动删分支

不建议在失败时自动回退主分支；PR 本身就是更安全的回滚边界。

## 成功标准

- reviewer 的职责从“仓库高频审查”成功收口为“PR 审查 + merge gate”
- governance evolution 可以稳定创建或更新 PR
- 自动 merge 只对受控 PR 生效
- 审查失败时只报告和挂起，不破坏主分支
- `pm-website` 的整体运行稳定性不因 reviewer 链再次下降

## 建议的最终运行策略

对于 `pm-website`，推荐长期保持：

- `project_index_maintainer`：Git 更新触发 + 4 小时兜底
- `reviewer_incremental_daily_4am`：关闭
- `reviewer_git_update_hourly`：不再作为高频全仓扫描器使用
- `reviewer`：只承担 PR 审查与 merge gate
- `governance evolution`：承担改动生产和 PR 创建

这样可以把“自动化改代码”与“自动化审查合并”拆成两段，既保留自动化收益，也不把运行节点再次拖回重型巡检模式。

# 2026-03-17 OpenClaw 改造与部署状态

## 目的

这份文档用于在长对话压缩前，固化当前仓库和服务器侧的真实进展，避免后续继续实施时需要重新翻聊天记录。

内容分 3 部分：

- 已完成
- 待完成
- 建议执行顺序

## 一、已完成

### 1. `pm-website` 单仓运行基线

已经完成并验证：

- Telegram 私聊基线修复
- `session.dmScope = per-channel-peer`
- 错误群目标清理
- `workspace-coordinator` HardFlow 文件补齐
- `memory-openviking` 轻量召回与 fail-fast 基线
- `coordinator` 默认模型切到 `kimicode/Doubao-Seed-2.0-Code`
- `ops_daily_work_report_dingtalk` / 任务卡片的人类可读输出优化

参考：

- [2026-03-16-pm-website-telegram-openviking-runbook.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-16-pm-website-telegram-openviking-runbook.md)
- [2026-03-17-pm-website-cron-baseline.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-17-pm-website-cron-baseline.md)

### 2. `pm-website` PR gate 闭环

已经完成并验证：

- `gh auth login`
- `governance auto-pr`
- `reviewer` 按 approval file 审查 open PR
- 命中 gate 后自动 merge

真实验证结果：

- smoke test PR 已成功自动合并
- cleanup PR 也已成功自动合并
- `pm-website` 运行仓库已快进到 GitHub 最新主线

### 3. 其它 4 台服务器基线

已经完成：

- `大白pm`
- `nofx`
- `coingod`
- `tokyo-claw`

这些机器已经补齐：

- Telegram / OpenViking 基线
- `workspace-coordinator` 的 HardFlow 核心文件

说明：

- 它们已达到“可稳定运行”的基础状态
- 但还没有像 `pm-website` 一样做完整 PR gate 闭环演练

### 4. 多项目服务器第一阶段

已经完成：

- 多项目服务器运行模板文档
- 多项目 reviewer merge approval 样例
- 多项目 registry 样例入口

参考：

- [2026-03-17-multi-project-server-template.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-17-multi-project-server-template.md)
- [project-registry.example.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/project-registry.example.json)
- [reviewer-merge-approval.multi-project.example.json](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/reviewer-merge-approval.multi-project.example.json)

### 5. 多项目服务器第二阶段

已经完成本地实现与测试：

- `install_reviewer_scan_jobs.py`
  - 支持 `--selected-jobs`
  - 支持 `--job-scope`
- 新增单仓安装器：
  - [install_governance_evolution_job.py](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/install_governance_evolution_job.py)
  - [install_git_sync_job.py](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/install_git_sync_job.py)
  - [install_auto_update_install_job.py](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/install_auto_update_install_job.py)
- `install_workflow_profile.py`
  - 支持按 `project-registry` 批量派生：
    - per-repo governance job
    - per-repo reviewer PR gate job
    - per-repo git sync job
    - per-repo auto update install job

### 6. 当前已通过的测试

已通过的定向测试包括：

- `tests/scripts_openclaw_ops/test_reviewer_pr_gate.py`
- `tests/scripts_openclaw_ops/test_cron_quiet_modes.py`
  - 与多项目安装器相关的定向用例
- 新增安装器脚本的 `py_compile`
- JSON 示例文件格式校验

## 二、待完成

### 1. 提交并推送当前多项目安装器改动

当前状态：

- 代码已经完成
- 测试已经通过
- 但这轮多项目第二阶段改动尚未执行 `git commit / push`

### 2. 选一台“真实多项目服务器”做 dry-run 安装验证

建议目标：

- 一台已经安装 OpenClaw、且存在两个以上真实业务仓库的服务器

验证内容：

- `install_workflow_profile.py --dry-run`
- `project-registry` 是否正确识别业务仓库
- 是否按预期派生：
  - governance
  - reviewer PR gate
  - git sync
  - auto update install

### 3. 决定多项目 `auto update install` 的生产策略

当前代码支持两种来源：

- 每个项目自己的 `auto_update_install_cmd`
- 全局模板 `--multi-project-auto-update-install-cmd-template`

仍需人工确认：

- 哪些项目允许自动安装
- 哪些项目只允许自动建 PR / 自动 sync，不允许自动部署

### 4. 决定是否把多项目 `git sync / auto update install` 推广到其它服务器

现在功能已经具备，但还未完成真实服务器落地。

### 5. 如果要继续提升自动化，可做第三阶段

候选项：

- 让 `install_workflow_profile.py` 支持更细的 per-repo job 频率配置
- 让 registry 支持 reviewer / governance / git sync / auto update 的独立开关
- 输出多项目安装报告到单独 JSON/Markdown 文件

## 三、建议执行顺序

### 第一步：提交本地改动

先提交：

- 多项目安装器改动
- 测试改动
- 文档和样例改动

### 第二步：推到 GitHub 主线

推送后，保证：

- 本地仓库
- GitHub 主线
- 后续服务器安装器入口

三者保持一致。

### 第三步：选一台多项目服务器做 dry-run

只验证 job 生成，不先真正启用所有 job。

### 第四步：只启用 per-repo governance / reviewer PR gate

这一步风险较低，先看：

- PR 创建
- reviewer 审查
- approval file
- 自动 merge

### 第五步：最后才决定是否启用 per-repo git sync / auto update

这两类属于“直接改仓 / 直接安装”的高副作用动作，应放在最后。

## 四、当前推荐口径

如果后续继续实施，建议坚持这条顺序：

1. 先 PR gate
2. 再 git sync
3. 最后 auto update install

也就是：

- 先把“改动可审查、可合并”打稳
- 再把“自动推送分支”打稳
- 最后才放开“自动安装部署”

## 五、当前最重要的入口文件

- [2026-03-16-pm-website-telegram-openviking-runbook.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-16-pm-website-telegram-openviking-runbook.md)
- [2026-03-17-pm-website-cron-baseline.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-17-pm-website-cron-baseline.md)
- [2026-03-17-multi-project-server-template.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/2026-03-17-multi-project-server-template.md)
- [2026-03-17-pr-review-merge-gate-implementation-plan.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/plans/2026-03-17-pr-review-merge-gate-implementation-plan.md)


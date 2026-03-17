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

已经完成实现、推送与远端 dry-run：

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

补充结果：

- 多项目第二阶段提交已推送到 GitHub 主线
  - commit: `b627851`
  - message: `feat: support multi-project repo job installation`
- `pm-website` 已完成一次真实远端 dry-run
  - 使用临时 sample registry
  - `discovery.enabled = false`
  - 不改正式 `project-registry.json`
  - 不落盘 `jobs.json`
  - 派生并验证通过：
    - `lobster`
    - `openclaw-hardflow-backup-20260302-deploy`
  - `steps_total = 22`
  - `ok = true`

### 6. `pm-website` 首个正式多项目节点

已经完成正式落地：

- 正式 `project-registry.json` 已写入 `pm-website`
- 当前正式登记项目：
  - `openclaw-hardflow-backup-20260302`（workflow）
  - `openclaw-local-install`（internal）
  - `lobster`（business）
- `discovery.enabled = false`
- `lobster` 已正式启用：
  - `ops_governance_evolution_incremental:lobster`
  - `reviewer_git_update_hourly:lobster`
- `project_index_maintainer_30m` 已切到正式 registry
- `schedule-registry.json` 已重新导出

重要边界：

- `openclaw-hardflow-backup-20260302-deploy` 虽然也是一份 git checkout
- 但它和 workflow repo 指向同一个 GitHub remote
- 因此当前**没有**把它作为正式 per-repo PR gate 目标
- 这样可以避免对同一批 PR 产生重复审查 / 自动合并竞争

### 7. `lobster` governance / reviewer 闭环演练

已经完成一次手动闭环演练，结论如下：

- governance 已手动触发
- reviewer gate 已手动触发
- 闭环**没有真正走到建 PR / 自动合并**

真实结果：

- governance report:
  - `changes_all_count = 14`
  - `changes_scoped_count = 0`
  - `auto_pr.attempted = true`
  - `auto_pr.ok = false`
  - `auto_pr.reason = invalid_branch_for_pr`
  - `branch = main`
- reviewer report:
  - `open_prs = 16`
  - `merge_actions = []`

已确认的原因：

1. `lobster` 当前这轮增量扫描没有命中 workflow 关注范围  
   也就是 repo 有变更，但不在 governance 当前 `watch_prefixes` 内，所以没有产出优化任务，也没有创建受控自动分支。

2. governance 在 `changes_scoped_count = 0` 时，仍然进入了 `auto_pr.attempted = true`  
   但因为分支还是 `main`，最终报 `invalid_branch_for_pr`。

3. reviewer 并不是坏了  
   它成功拉到了 `lobster` 的 open PR 列表，但没有任何一条命中：
   - `repo = lobster`
   - `head_prefix = auto/evolution-`
   - `base = main`
   所以没有执行 merge。

4. GitHub 权限仍是潜在阻塞  
   `pm-website` 上登录的 `XX-Trader` 对 `openclaw/lobster` 当前只有 `READ` 权限。  
   这次还没走到 push/建 PR 那一步就先停了，但即便前面修好，后续仍会卡在写权限。

补充事实：

- `lobster` 本地工作树当时有未跟踪文件：
  - `.workflow/`
  - `package-lock.json`

因此，当前最需要修的不是 reviewer，而是 governance 的前半段：

- 先明确 `lobster` 应该监控哪些路径
- 再避免 `changes_scoped_count = 0` 时仍去尝试 auto-pr
- 最后再解决 `openclaw/lobster` 的 push/PR 权限

### 8. `lobster` governance scoped 规则修复

已经完成本地修复、测试和 `pm-website` 远端验证：

- `governance_evolution_runner.py`
  - 修正 `changes_scoped_count = 0` 时仍错误标记 `auto_pr.attempted = true`
  - 现在会正确返回：
    - `attempted = false`
    - `reason = no_scoped_changes`
- `install_governance_evolution_job.py`
  - 新增 `--watch-prefix`
  - 新增 `--exclude-prefix`
- `install_workflow_profile.py`
  - 新增从 `project-registry.json` 读取 per-repo：
    - `governance.watch_prefixes`
    - `governance.exclude_prefixes`
    - `governance.auto_pr_enabled`

`pm-website` 上已经正式补进 `lobster.governance` 配置：

- `watch_prefixes`
  - `README.md`
  - `VISION.md`
  - `package.json`
  - `package-lock.json`
  - `src/`
  - `test/`
- `exclude_prefixes`
  - `.workflow/`
  - `dist/`
  - `build/`
  - `coverage/`
- `auto_pr_enabled = false`

远端验证结果：

- `install_workflow_profile.py --dry-run` 已成功从正式 registry 派生出带这些前缀参数的 `lobster` governance job
- `jobs.json` 中 `ops_governance_evolution_incremental:lobster` 的 message 已带上：
  - `--watch-prefix ...`
  - `--exclude-prefix ...`
- 手动重跑后最新 report：
  - `changes_all_count = 14`
  - `changes_scoped_count = 14`
  - `auto_pr.attempted = false`
  - `auto_pr.reason = not_run`

说明：

- `lobster` 的 governance 作用范围已经命中
- 误报 `invalid_branch_for_pr` 的问题已经消失
- 当前剩余阻塞已收敛为 GitHub 写权限，而不是 governance/reviewer 代码逻辑

### 9. `lobster` 已切换为外部只读仓模式

由于 `pm-website` 上当前 GitHub 账号 `XX-Trader` 对 `openclaw/lobster` 只有 `READ` 权限，这个仓库不再继续按“自动 PR / 自动 merge”模式运行。

已完成的收口动作：

- `lobster.governance.watch_prefixes` 移除了 `package-lock.json`
- 保留 `.workflow/` 在 `exclude_prefixes`
- `lobster.governance.auto_pr_enabled = false`
- `reviewer_git_update_hourly:lobster` 已在 `jobs.json` 中关闭
- `schedule-registry.json` 已重新导出

当前口径：

- `lobster` 保留：
  - 索引
  - 增量治理分析
  - 报告和任务输出
- `lobster` 关闭：
  - reviewer PR gate
  - auto-pr
  - git sync
  - auto update install

也就是说，`lobster` 现在是“外部只读观察仓 / 治理建议仓”，不是“可自动改仓业务仓”。

### 10. 当前已通过的测试

已通过的定向测试包括：

- `tests/scripts_openclaw_ops/test_reviewer_pr_gate.py`
- `tests/scripts_openclaw_ops/test_cron_quiet_modes.py`
  - 与多项目安装器相关的定向用例
- `tests/scripts_openclaw_ops/test_governance_evolution_runner.py`
  - `resolve_auto_pr_result` 的 `no_scoped_changes` 保护
- 新增安装器脚本的 `py_compile`
- JSON 示例文件格式校验

## 二、待完成

### 1. 决定多项目 `auto update install` 的生产策略

当前代码支持两种来源：

- 每个项目自己的 `auto_update_install_cmd`
- 全局模板 `--multi-project-auto-update-install-cmd-template`

仍需人工确认：

- 哪些项目允许自动安装
- 哪些项目只允许自动建 PR / 自动 sync，不允许自动部署

### 2. 决定是否把多项目 `git sync / auto update install` 推广到其它服务器

现在功能已经具备，但还未完成真实服务器落地。

### 3. 解决 `lobster` 的 GitHub 写权限

`lobster` 的 governance 作用范围和 scoped 逻辑已经修好。  
现在剩下的真正阻塞是：

- `XX-Trader` 对 `openclaw/lobster` 只有 `READ` 权限

在正式把 `lobster` 当作可自动 PR/自动 merge 的业务仓前，必须先补这一步。

### 4. 补齐其它服务器的正式多项目 `project-registry`

当前现状：

- `pm-website` 已完成首个正式多项目节点落地
- 其它 4 台正式 registry 目前仍只有：
  - workflow repo
  - `openclaw-local-install`

因此，下一步如果要把多项目 job 推广出去，需要先把其它服务器上的真实业务仓库登记进正式 registry。

### 5. 如果要继续提升自动化，可做第三阶段

候选项：

- 让 `install_workflow_profile.py` 支持更细的 per-repo job 频率配置
- 让 registry 支持 reviewer / governance / git sync / auto update 的独立开关
- 输出多项目安装报告到单独 JSON/Markdown 文件

## 三、建议执行顺序

### 第一步：补齐正式多项目 `project-registry`

先在目标服务器把真实业务仓库登记进正式 registry，再决定是否正式安装 per-repo job。

### 第二步：只启用 per-repo governance / reviewer PR gate

这一步风险较低，先看：

- PR 创建
- reviewer 审查
- approval file
- 自动 merge

### 第三步：最后才决定是否启用 per-repo git sync / auto update

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

# 2026-03-17 多项目服务器运行模板

## 目标

给“一台服务器承载多个 Git 项目”的 OpenClaw 运行方式定义统一模板，明确：

- 哪些任务按整机共享
- 哪些任务必须按项目拆分
- `project-registry`、`reviewer merge approval`、`governance auto-pr` 应该怎么配
- 当前代码已经支持到哪一层，哪些地方还需要手工复制 job 或后续扩展安装器

## 一句话结论

多项目服务器可以共用一套 OpenClaw，但必须遵守这条边界：

- 整机运维任务共用一套
- 项目索引共用一套 `project_index_maintainer`
- 会改仓的任务必须一项目一份：`governance auto-pr`、`reviewer PR gate`、`git sync`、`auto update`

不要把多个仓库的自动改仓逻辑混在同一个 job 里。

## 适用范围

- 一台 Linux 服务器上存在多个业务仓库
- 共用一套 `~/.openclaw`
- 希望保留统一任务中心、统一巡检、统一 Telegram / OpenClaw 入口
- 同时希望每个仓库拥有独立的 PR 审查与自动合并边界

## 当前代码的真实支持边界

### 已经支持

#### 1. `project-registry` 支持多项目

仓库内已有可直接使用的示例：

- [project-registry.example.json](../scripts/openclaw-ops/policy/project-registry.example.json)

运行时支持：

- 显式 `projects`
- 顶层 `discovery`
- 自动扫描本地 Git 仓库
- 多项目索引维护

#### 2. `project_index_maintainer` 适合多项目共享

它会基于 `project-registry` 逐个项目索引，并且已经支持：

- Git HEAD 未变化时跳过重建
- 4 小时兜底执行
- 自动补充 `doc_sources`、`repo_sources`

所以这类任务适合整机共用一份。

#### 3. `reviewer_cron_runner` 能识别多个 repo

当 `workspace` 指向一个父目录时，reviewer 本体可以发现多个 Git 仓库并做扫描。

但这只是“扫描能力”。

如果你要做“PR 审查 + 自动合并”，不建议一个 reviewer job 同时给多个仓库做 merge gate。

#### 4. `governance_evolution_runner` 不适合对多仓模糊运行

当 `project-registry` 匹配出多个项目时，它会要求你显式传：

- `--repo-id`
- 或 `--repo-path`

也就是说，自动建 PR 这条链必须落到具体仓库，不能靠“一个 job 扫所有项目”糊过去。

### 当前仍然单仓导向的点

#### 1. `install_reviewer_scan_jobs.py`

它默认写入固定的 reviewer job id / job name：

- `reviewer_git_update_hourly`
- `reviewer_incremental_daily_4am`
- `reviewer_recurring_bi_daily`
- `reviewer_weekly_structure_review`

这意味着：

- 直接重复运行安装器，会覆盖同一组 reviewer job
- 不会自动生成“每个仓库一份 reviewer gate”

#### 2. `install_workflow_profile.py`

它当前默认也是按“一套 runtime 对应一套 workflow 仓库”来安装 reviewer / governance 相关 job。

所以在多项目模式下：

- 整机共享任务可以继续用安装器
- 多仓的 reviewer PR gate / governance auto-pr 目前应视为“每仓库单独复制 job 配置”

## 推荐目录与运行文件

### 仓库目录

推荐把业务仓库集中放在一层目录下，例如：

```text
/srv/repos/
  pbm-website/
  quant-engine/
  admin-console/
```

### OpenClaw 运行目录

统一放在：

```text
~/.openclaw/
```

其中与多项目最相关的文件建议是：

- `~/.openclaw/ops/task-center/project-registry.json`
- `~/.openclaw/ops/reviewer-merge-approval.multi-project.json`
- `~/.openclaw/cron/jobs.json`

## 任务分层模板

### A. 整机共享，只保留一份

这些任务服务的是整台服务器，不针对某个仓库：

- `todo_patrol_15m`
- `task_executor_10m`
- `ops_incremental_monitor`
- `ops_full_calibration`
- `ops_system_schedule_audit`
- `ops_daily_work_report_dingtalk`
- `ops_local_openclaw_git_backup`

### B. 多项目共享一份

这类任务可共享，但其输入必须是完整 `project-registry`：

- `project_index_maintainer_30m`

推荐配置：

- 有 Git 变更才重建索引
- 4 小时兜底执行一次
- 统一读取 `project-registry.json`

### C. 必须按项目拆分

这类任务会对仓库本身产生副作用，必须一项目一份：

- `ops_governance_evolution_incremental`
- `reviewer_git_update_hourly`（仅 PR gate 模式）
- `ops_git_sync_push`
- `ops_auto_update_install_hourly`

原因：

- 它们都需要明确 `repo-id`
- 它们都需要明确 `repo-path`
- 它们都需要明确 `base branch`
- 它们都需要明确 `merge approval` 规则

## 推荐命名规范

建议把 `repo-id` 作为多项目模式下所有“改仓任务”的唯一主键。

例如：

- `pbm-website`
- `quant-engine`
- `admin-console`

对应的 job 命名建议：

- `ops_governance_evolution_incremental:pbm-website`
- `reviewer_pr_gate_hourly:pbm-website`
- `ops_git_sync_push:pbm-website`
- `ops_auto_update_install_hourly:pbm-website`

说明：

- 当前默认安装器不会自动生成这些名称
- 这是推荐的 `jobs.json` 自定义命名口径
- 同时也建议让 `task_id`、报告目录、state 文件带上相同 `repo-id`

## `project-registry` 如何设置

优先直接从现有示例开始：

- [project-registry.example.json](../scripts/openclaw-ops/policy/project-registry.example.json)

多项目场景最关键的字段是：

- `id`
- `name`
- `path`
- `git_remote`
- `git_branch`
- `integrations`
- `doc_sources`

如果你要启用这轮新增的多项目安装器能力，还可以额外配置：

- `git_sync.enabled`
- `git_sync.commit_prefix`
- `auto_update_install_cmd`

顶层建议保留：

- `discovery.enabled = true`
- `discovery.scan_roots = [你的仓库父目录]`

这样可以让 registry 既有“明确登记项目”，又能自动发现新增本地仓库。

## `reviewer merge approval` 如何设置

多项目场景建议使用一个集中审批文件，按 `repo + head_prefix + base` 做规则匹配。

示例文件：

- [reviewer-merge-approval.multi-project.example.json](../scripts/openclaw-ops/reviewer-merge-approval.multi-project.example.json)

推荐原则：

- `repo` 写仓库目录名或 `repo-id` 对应名，保持一致
- `head_prefix` 只放受控自动分支前缀
- `base` 明确写目标主分支

不建议：

- 只按 PR 编号审批
- 给多个项目共用一条过于宽泛的 `head_prefix`

## 推荐实施顺序

### 第一步：先把整机共享任务装好

保留：

- 整机巡检
- TODO 巡逻
- 任务执行器
- 每日工作报告
- 项目索引维护

这一步仍可沿用现有安装器。

### 第二步：准备好多项目 registry

把运行时 registry 固定到：

```text
~/.openclaw/ops/task-center/project-registry.json
```

内容以：

- [project-registry.example.json](../scripts/openclaw-ops/policy/project-registry.example.json)

为基础修改。

### 第三步：为每个仓库单独建 governance job

每个 governance job 必须显式带：

- `--project-registry`
- `--repo-id`
- 必要时 `--repo-path`
- `--auto-pr`
- `--pr-base`

关键点：

- 一个 governance job 只负责一个 repo
- 不要省略 `repo-id`

### 第四步：为每个仓库单独建 reviewer PR gate job

每个 reviewer PR gate job 必须显式带：

- `--workspace <真实 git 仓库根目录>`
- `--check-pr`
- `--pr-gate-only`
- `--allow-merge`
- `--merge-approval-file <多项目审批文件>`

关键点：

- `workspace` 必须是真实 Git 仓库根目录
- 不能指向 `~/.openclaw/workspace`
- 不建议一个 reviewer gate job 自动合并多个 repo

### 第五步：按仓库增加 git sync / auto update

如果这台服务器还承担自动同步与自动安装，那么这两类也必须一项目一份：

- `ops_git_sync_push`
- `ops_auto_update_install_hourly`

## 当前最稳的落地方式

如果你现在就要上线多项目模式，而不先改安装器，我建议这样做：

1. 共用现有安装器安装整机任务
2. 用 `project-registry.json` 统一索引全部项目
3. 手工在 `jobs.json` 中复制 reviewer / governance job
4. 给每个复制出来的 job 分配新的：
   - `id`
   - `name`
   - `description`
   - `state file`
   - `history dir`
   - `repo-id` / `workspace`

这是当前仓库最稳、最可控、与现有代码最一致的方案。

## 不建议的配置

### 1. 一个 governance job 扫所有项目

这样做会导致：

- 匹配歧义
- PR 归属不清
- 回滚困难

### 2. 一个 reviewer gate job 自动合并多个 repo

这样做会导致：

- approval 规则越来越混乱
- 不同仓库的主分支策略混在一起
- 排障困难

### 3. reviewer 的 `workspace` 指向聊天 workspace

这是之前单仓排障里已经验证过的坑：

- 会出现 `no git remotes found`
- reviewer 看不到真实仓库

## 验收清单

多项目模式落地后，至少检查：

- `project_index_maintainer_30m` 能看到所有登记项目
- 同一项目 Git HEAD 不变时索引会 skip
- 每个 governance job 都只命中自己的 `repo-id`
- 每个 reviewer gate job 的 `workspace` 都是对应 repo 根目录
- `gh pr list` / `gh pr view` 在对应 repo 目录下可正常工作
- approval file 的规则只命中对应项目的受控分支

## 建议的下一步代码演进

如果后续要把多项目模式从“可实施”升级成“一键安装”，优先补这两个能力：

1. `install_reviewer_scan_jobs.py`
   - 支持传入自定义 job id / job name / state file / history dir
   - 支持同一台服务器安装多份 reviewer PR gate

2. `install_workflow_profile.py`
   - 支持读取多项目 registry
   - 自动为每个 repo 生成 governance / reviewer / git sync job

在这两个能力补完之前，推荐口径仍然是：

- 共享任务自动装
- 改仓任务按项目手工复制 job

## 2026-03-17 之后可直接使用的安装器参数

这轮代码已经补了第一批多项目安装支持：

- `install_workflow_profile.py`
  - `--install-multi-project-governance-jobs`
  - `--install-multi-project-reviewer-pr-gates`
- `install_reviewer_scan_jobs.py`
  - `--selected-jobs`
  - `--job-scope`
- `install_governance_evolution_job.py`
  - 单仓 governance job 安装器，可被 `install_workflow_profile.py` 按 registry 批量调用

建议使用方式：

```bash
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile core \
  --openclaw-home ~/.openclaw \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302 \
  --workflow-repo-id openclaw-hardflow-backup-20260302 \
  --project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --governance-auto-pr \
  --reviewer-enable-hourly-pr-gate \
  --reviewer-hourly-allow-merge \
  --reviewer-hourly-merge-approval-file ~/.openclaw/ops/reviewer-merge-approval.multi-project.json \
  --install-multi-project-governance-jobs \
  --install-multi-project-reviewer-pr-gates
```

这条命令的实际效果是：

- 主 workflow 仓库继续安装默认那套共享任务
- 额外为 registry 中的其他 `business` 项目派生：
  - 一份 governance auto-pr job
  - 一份 reviewer hourly PR gate job

如果还要同时派生 `git sync / auto update install`，再追加：

```bash
  --install-multi-project-git-sync-jobs \
  --install-multi-project-auto-update-install-jobs \
  --multi-project-auto-update-install-cmd-template "bash deploy/{repo_id}.sh"
```

规则如下：

- `git sync`
  - 默认会为所有 `business` 项目派生
  - 如果某个项目声明 `git_sync.enabled = false`，则跳过
  - `git_sync.commit_prefix` 可覆盖默认提交前缀
- `auto update install`
  - 只会为“明确有安装命令”的项目派生
  - 优先使用项目自己的 `auto_update_install_cmd`
  - 若项目未声明，则回退到 `--multi-project-auto-update-install-cmd-template`

当前仍然保留的边界：

- 多项目 `git sync / auto update install` 这轮已经支持批量派生
- 但安装器还不会自动判断“哪个项目真的应该启用 auto update install”
- 所以生产环境建议：
  - 只给明确有部署脚本的项目配置 `auto_update_install_cmd`
  - 不要给所有项目统一套同一个高风险部署命令

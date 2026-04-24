# OpenClaw Workflow Map

本文件描述当前工作流体系的实际地图。阅读时始终区分：

- 仓库模板
- 运行态现值
- 技能化入口
- 废弃安装链
- Phase 6 MVP 已实现的编码交付流水线

## 1. 当前总体判断

当前仓库不是缺少零件，而是缺少一条统一的端到端编码交付状态机。

已经存在的底座：

- HardFlow Core / ACP 编码链
- 双 AI 对抗审查 Skill
- 失败学习 Skill
- project-agent 相关项目画像、API registry、项目记忆脚本
- cron/job 模板和 `skill_ref`
- 任务中心与 task executor
- 运行态技能补齐、绑定检查、调度导出等运维脚本

当前最大缺口：

1. `project-delivery-pipeline` 状态机已落地为 dry-run MVP。
2. “自动探索 -> 需求包 -> 方案包 -> 编码 -> 测试 -> 审核 -> 验收 -> 回写” 已有统一编排产物，但真实 agent 执行仍待接入。
3. OpenClaw/Hermes 宿主适配已有 runtime adapter MVP。
4. 旧 `install_workflow_profile.py` 曾经承担过太多安装职责，已经不适合继续扩展。

## 2. 当前实际分层

### 2.1 仓库模板层

- `cron/jobs.json`
- `openclaw/openclaw.json`
- `docs/核心主工作流/项目交付优先工作流/`
- `skills/library/*`

### 2.2 技能化执行层

- `skills/library/dual-ai-review/`
- `skills/library/failure-learning/`
- `skills/library/project-profile-manager/`
- `skills/library/api-registry-manager/`
- `skills/library/cross-runtime-memory-distiller/`
- `skills/library/project-delivery-pipeline/`（Phase 6 MVP 已实现）

### 2.3 编码交付执行层

目标主链：

```text
用户需求
-> context_discovery
-> external_research
-> requirement_package
-> requirement_review
-> solution_package
-> solution_review
-> code_execution
-> local_verification
-> code_review
-> acceptance
-> writeback
```

编码执行仍复用 HardFlow Core / ACP，不新增平行编码引擎。

### 2.4 运行态层

- `~/.openclaw/openclaw.json`
- `~/.openclaw/cron/jobs.json`
- `~/.openclaw/ops/task-center/task_center.db`
- Hermes 场景下对应 `$HOME/.hermes/...`

OpenClaw/Hermes 差异必须留在 runtime adapter，不能污染业务流程。

## 3. 已废弃链路

| 链路 | 当前处理 | 原因 |
|------|----------|------|
| `install_workflow_profile.py` 旧实现 | 已删除主体，只保留 fail-fast 入口 | 依赖已删除的 `cron_setup.py / install_*_job.py` |
| `cron_setup.py` | 不恢复 | 技能化架构已废弃 |
| `install_*_job.py` 安装器链 | 不恢复 | 会把端到端流水线退回旧 cron 拼装 |
| `core/all profile` 安装模式 | 不作为主线 | 与 Phase 6 状态机冲突 |
| 默认自进化链 | 不恢复 | 用户明确要求不做自进化 |

## 4. 仍需要做的工作

1. 接入 Hermes 真实多 agent 调度，让需求讨论、编码、测试、审查由真实 agent 产出。
2. 接入真实联网 research agent，把官方文档、成熟方案和现成代码候选写入 `research_report.md`。
3. 接入 HardFlow Core / ACP live 编码链，让 `patch_summary.md` 来自真实实现。
4. 接入 lint、typecheck、unit、integration、smoke 和部署验证命令证据。
5. 通过 `project_memory_writer.py` 执行真实项目记忆回写，而不是只生成 `writeback_report.md` 建议。
6. 在 Hermes live runtime 中做一次完整 dry-run 和一次小任务 live smoke。

## 5. 明确不用做的工作

1. 不恢复旧 profile 安装器主体逻辑。
2. 不恢复 `cron_setup.py`。
3. 不恢复 10 个 `install_*_job.py`。
4. 不为 OpenClaw/Hermes 写两套业务流程。
5. 不新增新的编码引擎。
6. 不把 runtime `jobs.json` 当长期架构文档。
7. 不让自进化链回到默认主线。
8. 不做外部 workflow 市场或下载器。

## 6. 未来新增 workflow 的约束

1. 新增的是 `workflow skill + state machine`，不是平行脚本链。
2. 必须复用 HardFlow Core 的证据、Gate、验收、完成前验证。
3. 必须声明依赖哪些 capability。
4. 必须有 dry-run 与产物目录。
5. 必须能被 runtime adapter 映射到 OpenClaw/Hermes。

换句话说：可以多 workflow，但只能单底座、单状态机模式。

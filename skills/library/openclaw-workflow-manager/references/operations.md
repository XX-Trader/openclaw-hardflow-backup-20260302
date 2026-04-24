# OpenClaw Workflow Operations

本文件给出工作流管理技能的操作手册。原则是优先走当前有效的技能化入口，不优先手改运行态文件。

> 2026-04-24 裁决：旧 `install_workflow_profile.py` 与 `cron_setup.py / install_*_job.py` 链路已废弃。它们不能再作为安装、重装或 profile 对齐入口；若被误调用，应 fail-fast 并指向 Phase 6 的 `project-delivery-pipeline`。

## 1. 当前有效入口

| 场景 | 当前入口 | 说明 |
|------|----------|------|
| 编码交付主链 | `skills/library/project-delivery-pipeline/` | Phase 6 MVP 已实现，负责自动探索、编码、测试、代码审核、验收、回写；真实 Hermes 多 agent 调度待接入 |
| 运行态技能补齐 | `skills/library/openclaw-workflow-manager/scripts/ensure_runtime_skills.py` | 只处理 runtime skills，不承担旧 profile 安装 |
| 运行态绑定检查 | `scripts/openclaw-ops/inspect_runtime_bindings.py` | 只读检查 repo 与 runtime 绑定 |
| 调度总表导出 | `scripts/openclaw-ops/export_schedule_registry.py` | 只读导出调度面 |
| stale cron 清理 | `scripts/openclaw-ops/recover_stale_cron_running_state.py` | 先 dry-run，再执行 |
| 旧 profile 卸载 | `uninstall_workflow_profile.py` | 仅用于历史 runtime 清理计划 |

## 2. 已废弃入口

| 旧入口 | 处理方式 | 原因 |
|--------|----------|------|
| `install_workflow_profile.py` | 仅保留 fail-fast 兼容入口 | 旧实现依赖已删除的 `cron_setup.py / install_*_job.py` |
| `cron_setup.py` | 不再恢复 | 技能化架构已裁决废弃 |
| `install_*_job.py` 安装器链 | 不再恢复 | 端到端流水线应走 skillized state machine |
| `core/all profile` 安装模式 | 不再作为主线 | 会把编码交付问题退回旧 cron 拼装模型 |

## 3. 端到端编码交付还需要做什么

1. 新增 `skills/library/project-delivery-pipeline/SKILL.md`，作为用户侧主入口。
2. 新增 `scripts/pipeline_runner.py`，实现 `Coding Pipeline Run` 状态机。
3. 新增运行产物目录 `.workflow/pipeline-runs/<run_id>/`。
4. 新增模板：`run_meta.json`、`requirements.md`、`solution.md`、`verification_report.md`、`delivery_evidence.md`。
5. 接入已有 `dual-ai-review`、`failure-learning`、`project-profile-manager`、`api-registry-manager`。
6. 调用 HardFlow Core / ACP 编码链，但不复制新的编码引擎。
7. 聚合 lint、typecheck、unit、integration、smoke、部署验证和代码审核证据。
8. 实现失败回退：需求失败回探索，方案失败回方案，测试/代码审核失败回编码，反复失败触发失败学习。
9. 实现 OpenClaw/Hermes runtime adapter，只处理路径、runtime home、job payload、状态目录和记忆蒸馏 DB。
10. 增加 dry-run 集成测试，验证状态机产物、阻断和回退。

## 4. 明确不用做什么

1. 不恢复 `cron_setup.py`。
2. 不恢复 `install_*_job.py` 安装器链。
3. 不维护 OpenClaw 和 Hermes 两套业务流程。
4. 不新增平行编码引擎，编码继续复用 HardFlow Core / ACP。
5. 不把自进化链重新放回默认主线。
6. 不用旧 `core/all profile` 作为编码交付主线。
7. 不用运行态 `jobs.json` 反向充当长期架构文档。
8. 不把外部方案直接覆盖本地工作流，必须先做差异评估。

## 5. 常用只读命令

```bash
python scripts/openclaw-ops/inspect_runtime_bindings.py --emit-json
```

```bash
python scripts/openclaw-ops/export_schedule_registry.py --profile all --emit-json
```

```bash
python scripts/openclaw-ops/recover_stale_cron_running_state.py --dry-run --emit-json
```

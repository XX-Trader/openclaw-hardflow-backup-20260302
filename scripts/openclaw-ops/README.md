# scripts/openclaw-ops

> 2026-04-24 裁决：根目录 `scripts/openclaw-ops/` 不再作为新增工作流代码的主要承载面。大部分实现已归并到 `skills/library/*/scripts/`。这里仅保留少量共享工具、兼容文件和历史迁移边界。

## 当前原则

1. 新的编码交付流水线放到 `skills/library/project-delivery-pipeline/`。
2. OpenClaw/Hermes 宿主差异放到 Phase 6 的 runtime adapter。
3. 不恢复 `cron_setup.py`。
4. 不恢复 `install_*_job.py` 安装器链。
5. 不恢复旧 `install_workflow_profile.py` 主体逻辑。
6. 不把本目录当作新的脚本堆放区。

## 当前仍有效的内容

| 路径 | 用途 |
|------|------|
| `CRON_TASK_INDEX.md` | 旧 cron/job 分类索引 |
| `failure_tracker.py` | 失败学习触发跟踪 |
| `project_memory_writer.py` | 项目记忆回写 |
| `project_memory_injector.py` | 项目记忆注入 |
| `source_registry_watcher.py` | 项目第三方来源 watch |
| `shared/` | 少量共享工具 |
| `policy/` | 技能化前遗留的控制面策略代码，后续应逐步迁移或删除 |

## 新增代码落点

新增端到端编码交付能力时，不要放回本目录，应使用：

```text
skills/library/project-delivery-pipeline/
├── SKILL.md
├── scripts/pipeline_runner.py
├── templates/
└── references/
```

## 已删除的旧入口

| 旧入口 | 处理 |
|--------|------|
| `cron_setup.py` | 已废弃，不恢复 |
| `install_*_job.py` | 已废弃，不恢复 |
| `install_workflow_profile.py` | 主体逻辑已删除，兼容入口在 `skills/library/openclaw-workflow-manager/scripts/` fail-fast |
| `control_plane_live_acceptance_runner.py` | 已删除，依赖旧安装面 |

## 查找真实入口

- 项目交付优先工作流：`docs/核心主工作流/项目交付优先工作流/`
- 技能化架构：`docs/基础设施/技能化架构/`
- 工作流地图：`skills/library/openclaw-workflow-manager/references/workflow-map.md`
- 操作手册：`skills/library/openclaw-workflow-manager/references/operations.md`

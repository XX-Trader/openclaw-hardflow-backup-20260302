# Cron 基线裁剪执行清单

> 版本：v1.1 | 2026-04-27
> 关联文档：[项目交付优先工作流架构设计](../核心主工作流/项目交付优先工作流/项目交付优先工作流架构设计.md)

---

## 1. 裁剪目标

自进化完全移除。不是降级为"可选"，是从默认主链**完全移除**。

## 2. 保留清单（项目交付核心链 + 基础设施）

| Job | 分类 | 状态 |
|-----|------|------|
| `task_executor` | 核心运营 | 保留 |
| `todo_patrol` | 核心运营 | 保留 |
| `distill_runner` | 基础设施 | 保留 |
| `config_watchdog` | 基础设施 | 保留 |
| `memtidy_runner` | 基础设施 | 保留 |
| `unified_exception_logger` | 基础设施 | 保留 |
| `source_registry_watcher` | 项目交付 | 保留（每 2 天） |
| `repo_hygiene_reviewer_2d` | 项目交付治理 | 新增保留（每 2 天，`coordinator` 只读扫描 + 人工确认候选） |

## 3. 移除清单（自进化 + 泛化扫描）

| Job | 分类 | 状态 |
|-----|------|------|
| `optimization_agent_*` | 自进化 | **移除** |
| `skill_evolution_review` | 自进化 | **移除** |
| `workflow_upgrade_scoring` | 自进化 | **移除** |
| `github_scanner` | 泛化扫描 | **移除** |
| `web_intelligence_*` | 泛化扫描 | **移除** |

## 4. 执行步骤

### 4.1 修改 `cron/jobs.json`

1. 删除所有移除清单中的 job 条目
2. 验证保留清单中的 job 配置正确
3. 确保 `source_registry_watcher` 频率为每 2 天
4. 确保 `repo_hygiene_reviewer_2d` 只读扫描，不自动删除、不自动 Git 发布

### 4.2 修改安装器默认 profile

1. 新部署默认只激活保留清单中的 job
2. 移除清单中的 job 不注册到默认 profile
3. 保留手动恢复入口（如需重新启用）

### 4.3 更新文档

1. 更新 `CRON_TASK_INDEX.md`
2. 更新 [Cron 任务治理说明](cron-任务治理说明.md)
3. 在 `项目交付优先工作流架构设计.md` 中同步

### 4.4 验证

1. 默认 job 数量从 ~15 降至 ~7
2. 核心交付链（task_executor、todo_patrol）稳定运行
3. 无任何自进化相关任务在运行

## 5. 回滚预案

如需恢复某个移除的 job：

1. 在 `cron/jobs.json` 中重新添加条目
2. 手动执行一次验证
3. 更新 `CRON_TASK_INDEX.md`

## 6. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-22 | 初始版本，定义 cron 裁剪保留/移除清单 |
| v1.1 | 2026-04-27 | 将 API 来源监控调为每 2 天，并新增只读仓库精简巡检 |

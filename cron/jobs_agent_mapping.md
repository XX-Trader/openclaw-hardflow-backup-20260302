# Cron Job Agent 映射表

> 最后更新：2026-03-29
> 总计：23 个定时任务（✅ 启用 20 个 / ⏸️ 禁用 3 个）

## ops-agent（8 个）

| 状态 | 任务名称 | 频率 | 功能简述 |
|------|----------|------|----------|
| ✅ | TODO 巡检（15分钟） | 每15分钟 | 巡检 TODO.md，去重播报，检测执行状态，未分配项请求 coordinator 分配 |
| ✅ | daily_todo_digest_daily | 每日 00:00 | 每日 TODO 摘要，通过 Telegram 发送 |
| ✅ | system_exception_patrol（系统异常巡检） | 每6小时 | 扫描 Agent 工作流日志，按7类异常分类，MD5指纹去重，增量扫描 |
| ✅ | agent_self_evolution（Agent 自进化评估） | 每周一 04:00 | 基于 task_center.db 历史数据多维度评分，生成优化建议 |
| ✅ | auto_update_daily（上游社区进化） | 每日 03:00 | 拉取上游仓库最新代码 + `setup.py --yes` 自动安装到 .openclaw |
| ✅ | web_intel_collect_daily（情报采集） | 每日 03:30 | 采集网页情报源，存档变更，自动建单修复失败源 |
| ⏸️ | TODO 巡检-hardflow | 每15分钟 | hardflow 备份仓库的 TODO 巡检（当前禁用） |
| ⏸️ | ops_governance_evolution_incremental | 每6小时 | 治理巡检与进化提取（当前禁用） |

## optimization-agent（8 个）

| 状态 | 任务名称 | 频率 | 功能简述 |
|------|----------|------|----------|
| ✅ | optimize 目录树快照+变更增量扫描 | 每日 04:00 | 扫描工作流/Skills/Hooks 目录变更 |
| ✅ | optimize 自我进化总结 | 每日 04:37 | 蒸馏记忆中的最佳实践，更新 Agent 行为约束配置 |
| ✅ | algo_micro_optimizer_daily | 每日（24h） | Hook 沙盒自测，检测 hook 健康度 |
| ✅ | ops_git_sync_push | 每6小时 | 自动同步审核通过的优化到远程仓库（含密钥检测） |
| ✅ | config_diff_review | 每6小时 | 监控 .openclaw 本地 git 变更，触发 optimization-agent 审核 |
| ✅ | github_web_evolution_daily（开源项目进化） | 每日 04:00 | 扫描 GitHub 高信号仓库和技能库，创建评估任务 |
| ⏸️ | optimize 目录树快照-hardflow | 每日 04:00 | hardflow 备份仓库的目录树快照（当前禁用） |
| ✅ | local_config_snapshot（本地配置快照） | 每1小时 | 同步 .openclaw/ 核心配置到 B 层 clone（白名单+排除+内容比对） |

## reviewer（4 个）

| 状态 | 任务名称 | 频率 | 功能简述 |
|------|----------|------|----------|
| ✅ | reviewer_incremental_daily_4am | 每日 04:00 | 全量增量评审：代码质量/安全/架构，自动落地优化 |
| ✅ | reviewer_weekly_structure_scan | 每周日 04:30 | 结构化扫描：文件组织/依赖/冗余/一致性 |
| ✅ | reviewer_weekly_security_audit | 每周日 05:00 | 安全审计：密钥泄漏/权限/XSS/注入 |
| ✅ | reviewer_weekly_doc_freshness | 每周日 05:30 | 文档新鲜度检查：文档与代码的同步性 |

## coordinator（3 个）

| 状态 | 任务名称 | 频率 | 功能简述 |
|------|----------|------|----------|
| ✅ | coordinator 心跳 | 每5分钟 | 存活检测 |
| ✅ | coordinator_daily_plan | 每日 04:00 | 每日工作规划 |
| ✅ | coordinator_weekly_retrospective | 每周日 05:00 | 每周回顾总结 |

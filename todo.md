# TODO

> 策略：先在 **nofx 单机** 验证所有变更稳定后，再推广到其他 4 台服务器。
> 更新时间：2026-03-27

## P0 — 安全与基础设施（阻塞级）

- [⏰ 2026-04-01] [🔴 P0] `git_sync_push_runner.py` 增加密钥内容检测（第二层审核）
  - 在 push 前对 eligible_files 做正则内容扫描（API Key / Token / PRIVATE KEY）
  - 匹配到敏感内容 → 自动移出 eligible + TG 告警
  - 当前只有路径过滤（第一层），文件内容无任何检测，有泄漏风险

- [⏰ 2026-04-01] [🔴 P0] nofx 环境配置校验：Telegram cron delivery 目标、webhook / secret / runtime.env

- [⏰ 2026-04-03] [🔴 P0] nofx 日志验证：按运行日志做服务器侧基础验证，确认所有核心 cron job 正常

## P1 — Cron Job 清理与优化

- [⏰ 2026-04-03] [🟠 P1] Cron Job 批量清理（删除 7 个冗余 Job）
  - 删除 Job：optimize 频率策略管理、reviewer_git_update_hourly、reviewer_recurring_bi_daily、control_plane_summary_daily、control_plane_dashboard_daily、benchmark_sweep_12h、log-watcher agent、ops 汇总
  - 删除脚本+测试：benchmark_orchestrator.py、benchmark_output_consumer.py（含测试文件）
  - 注意：control_plane_summary_runner.py 和 control_plane_dashboard.py **不删**（advisor 依赖）
  - 服务器上额外删除：optimize_frequency_manager.py、log-watcher 相关脚本

- [⏰ 2026-04-03] [🟠 P1] 启用 `daily_todo_digest_daily`（每日 TODO 摘要推送 TG）

- [⏰ 2026-04-03] [🟠 P1] 降频 `algo_micro_optimizer` → 24h（hook-selftest 不需要 4h）

- [⏰ 2026-04-03] [🟠 P1] 重命名 `unified_exception_logger（异常巡检）` → 更具描述性的名称

- [⏰ 2026-04-05] [🟠 P1] 注册 3 个外部进化 Cron Job（均为每日一次）
  - `upstream_update_daily` — `auto_update_install_runner.py` — 凌晨 1:00
  - `web_intel_collect_daily` — `web_intel_collect_runner.py` — 凌晨 2:00
  - `github_evolution_daily` — `github_web_evolution_runner.py` — 凌晨 2:30

- [⏰ 2026-04-05] [🟠 P1] 重写定时任务索引文件
  - `CRON_TASK_INDEX.md`：删除已删 Job 条目、新增 3 个外部进化 Job、更新模型说明
  - `jobs_agent_mapping.md`：重新生成匹配清理后的 Job 列表

## P1 — 功能增强

- [⏰ 2026-04-07] [🟠 P1] `unified_exception_logger` 增强：统一异常日志目录
  - 新建 `/root/.openclaw/logs/abnormal/` 统一目录
  - 所有异常日志自动归档到该目录，按 `日期-任务ID-错误类型.log` 命名
  - 自动去重：相同错误只保留 1 份

- [⏰ 2026-04-07] [🟠 P1] `unified_exception_logger` 增强：命令路径合法性校验
  - 新增第 7 类异常分类正则：检测无效路径引用、文件不存在的命令调用
  - 覆盖常见路径错误模式（脚本路径写错、配置文件引用失效）

- [⏰ 2026-04-10] [🟠 P1] `unified_exception_logger` 增强：日志自动清理
  - 超过 7 天的异常报告自动压缩归档（gzip）
  - 超过 30 天的归档自动清理，避免磁盘空间占用

- [⏰ 2026-04-10] [🟠 P1] `control_plane_optimization_advisor` 改造：输出写入 TODO
  - 遍历 recommendations，将每条建议追加到 TODO.md
  - severity=high → [🔴 P1]，medium → [🟡 P2]，low → [🟢 P3]
  - 标记 [来源:advisor]，todo_patrol 识别为 ai 来源时自动要求上下文补全
  - 任务只加入 TODO，需人工确认后才执行

- [⏰ 2026-04-12] [🟠 P1] 新增定时任务 `config_diff_review`：本地配置变更审核同步
  - 定时扫描 `/root/.openclaw` 的 git diff（本地 git 快照变更）
  - 调用 optimization-agent 审核变更内容（配置/脚本/Agent 属性）
  - 审核通过 → 自动同步到 `/root/openclaw-hardflow-backup-20260302/` 对应路径
  - 已有的 `git_sync_push` 再将 backup 仓库推到 GitHub
  - 闭合「本地运行配置 → 审核 → 远程仓库」的完整链路

- [⏰ 2026-04-15] [🟠 P1] `git_sync_push` 增加第三层审核：Agent 审核
  - push 前调用 optimization-agent 审核 eligible_files 的变更摘要
  - Agent 返回 approve/reject + 理由
  - reject 时中止 push 并 TG 告警

## P1 — 可观测性

- [⏰ 2026-04-15] [🟠 P1] 统一调用链追踪（trace_id 全链路注入）
  - 现状：task_center 4 张表已有 trace_id 字段，build_trace_id() 生成器已有，多个脚本已使用
  - 缺失：Agent 入口自动注入（Hook 层面）、跨 Agent/子会话传播、token 消耗关联
  - 目标：所有日志/token消耗/步骤都带 trace_id，实现全链路可观测
  - 可在 `hardflow-audit` hook 中注入，通过 context_payload 向下传播

## P2 — 自进化增强

- [⏰ 2026-04-20] [🟡 P2] 记忆 → Skill/Hook 自动封装闭环
  - governance_evolution 扫描记忆，提取可复用流程/最佳实践
  - 自动生成 Skill 模板（SKILL.md + 脚本框架）
  - 生成的 Skill 标记为 [draft]，需人工审核后激活
  - 高风险：直接修改 SOUL.md → 需人工确认；低风险：新增 Skill → 可自动执行

- [⏰ 2026-04-20] [🟡 P2] 错误驱动进化闭环
  - 增强 `unified_exception_logger`：扫描完异常后自动查 `fault_knowledge_base`
  - 匹配到已知修复方案 → 自动生成修复 TODO（低风险自动执行，高风险人工确认）
  - 修复经验反哺知识库

- [⏰ 2026-04-20] [🟡 P2] TODO 格式增加截止时间标记
  - 格式：`- [⏰ YYYY-MM-DD] [🔴 P0] 任务描述`
  - todo_patrol.py 增加截止时间解析正则
  - 超期任务自动升级优先级

- [⏰ 2026-04-25] [🟡 P2] 任务派发 5 要素确认协议文档化
  - 写入 routing-rules.json 或 Agent SOUL 配置
  - 5 要素：任务内容、实现流程、预期效果、执行角色、时间要求
  - AI 来源任务缺少要素时自动要求补全

- [⏰ 2026-04-25] [🟡 P2] `control_plane_optimization_advisor` 未来启用
  - 当前暂停，待手动效果观察后启用
  - 启用前提：advisor → TODO 改造完成（上方 P1 项）

- [⏰ 2026-04-30] [🟡 P2] `optimize 全量校准` 启用（每 14 天兜底，增量扫描的补充）

## P2 — 推广与治理

- [⏰ 2026-05-01] [🟡 P2] nofx 验证通过后，推广到其余 4 台服务器
- [⏰ 2026-05-01] [🟡 P2] 调整 Lobster 仓库配置为 `external_readonly`
- [⏰ 2026-05-05] [🟡 P2] 把默认 `coding-default` workflow profile 的 manifest、安装入口正式落地
- [⏰ 2026-05-05] [🟡 P2] 为 `upgrade feedback` 补齐晋升/回滚规则
- [⏰ 2026-05-10] [🟡 P2] 拆分 `policy_enforcer.py`（270KB 巨型单体）为独立模块

## P3 — 长期优化

- [🟢 P3] `algo_micro_optimizer` 方案 B：Workflow Scorecard 综合分驱动自动优化
- [🟢 P3] 核心 registry 配置 JSON Schema 强校验
- [🟢 P3] MetaClaw 跨次学习闭环：`lesson_to_skill.py`
- [🟢 P3] CLI 交互体验优化（交互式引导 + 自动补全）
- [🟢 P3] 多 workflow 负载均衡与环节裁剪策略
- [🟢 P3] 外部 workflow / skill 下载与安装市场
- [🟢 P3] `project-registry` 扩展：项目级独立配置

## Agent 模型配置待同步

> 以下配置需要在服务器 openclaw.json 中更新（当前备份仓库与服务器一致，均未更新）

| Agent | 当前配置 | 应有配置 | 状态 |
|-------|---------|---------|------|
| coordinator | `gpt-5.4-mini` | `gpt-5.4` | ❌ 待更新 |
| tester | `gpt-5.4-mini` | `Doubao-Seed-2.0-pro` | ❌ 待更新 |
| doc-writer | `gpt-5.4-mini` | `Doubao-Seed-2.0-pro` | ❌ 待更新 |
| explorer | 不存在 | `gpt-5.4-mini`（发散探索） | ❌ 待新增 |

---
## 参考文档
完整执行计划与细节见：[docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md](/docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md)

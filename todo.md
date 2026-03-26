# TODO

> 策略：先在 **nofx 单机** 验证所有变更稳定后，再推广到其他 4 台服务器。

## P0 — nofx 单机验证（阻塞级）

- ~~交叉评审基建（score_evaluator + check-score-gate.mjs 强制校验）~~ ✅
- ~~algo_micro_optimizer.py 沙盒评估器（4h cron）~~ ✅
- ~~nofx 服务器部署 + gateway restart（tmux 持久化）~~ ✅
- ~~文档审计清理（37→12 个文件）~~ ✅
- ~~代码冗余清理（9 个死文件 + .tmp/ 目录）~~ ✅
- nofx 环境配置校验：Telegram cron delivery 目标、webhook / secret / runtime.env
- nofx 日志验证：按运行日志做服务器侧基础验证，确认所有核心 cron job 正常
- 调整 Lobster 仓库配置为 `external_readonly`，关闭 `auto_pr_enabled` 与 `auto_update_install_cmd`
- 落地只读仓库保护逻辑，禁止对 `external_readonly` 标记的仓库发起任何写操作
- 把平台总入口正式落地为：`需求澄清 -> 任务拆分 -> workflow 选择 -> 执行`
- 把默认 `coding-default` workflow profile 的 manifest、安装入口和 `stable/candidate` 配置正式落地
- 为 `upgrade feedback` 补齐晋升/回滚规则（`baseline / candidate / delta / promotion_decision`）
- 任务层补齐 `workflow_profile_id` 与 `required_capabilities`，preflight 约束生效

## P1 — nofx 稳定后推广 + 基建增强

- **nofx 验证通过后**，将配置推广到其余 4 台服务器（pm-website / 大白pm / coingod / tokyo-claw）
- 为其它服务器补齐正式 `project-registry.json`，选 1 台作为第二个多项目正式节点
- 在多项目服务器上验收 reviewer PR gate 闭环
- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些只允许到 PR gate / git sync
- 补充"外部上游仓库只读→自有克隆修改→按需向上游贡献"使用规范文档
- 给"共享同一 GitHub remote 的 deploy checkout 不挂 PR gate"补正式文档
- 为 `coding-default` 之外的第二个 workflow profile 准备最小样板
- capability manifest / skill binding / hook policy 统一导出
- 核心 registry 配置 JSON Schema 强校验
- MetaClaw 跨次学习闭环：`lesson_to_skill.py`
- ~~Score Gate 交叉评审基建~~ ✅ 已完成

## P2 — 长期优化

- `algo_micro_optimizer` 方案 B：Workflow Scorecard 综合分驱动自动优化
- 启用第二批进化 Jobs（`benchmark_sweep_12h`、`control_plane_optimization_advisor_12h`）
- 拆分 `policy_enforcer.py`（270KB 巨型单体）为独立模块
- 高危操作审计日志
- CLI 交互体验优化（交互式引导 + 自动补全）
- 本地开发环境一键启动脚本
- 多 workflow 负载均衡与环节裁剪策略
- 外部 workflow / skill 下载与安装市场
- `project-registry` 扩展：项目级独立配置
- 多项目安装报告导出

---
## 参考文档
完整执行计划与细节见：[docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md](/docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md)

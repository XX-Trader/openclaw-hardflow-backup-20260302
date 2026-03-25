# TODO

## P0

- 为 5 台服务器补齐这轮部署后的环境配置，重点检查：
  - Telegram cron delivery 目标
  - webhook / secret / runtime.env
  - `pm-website` 以外 4 台是否仍落到 `-1003333097130`
- 环境配置完成后，按日志做一轮服务器侧验证，不先做功能级人工回归。
- 为其它服务器补齐正式 `project-registry.json`，至少再选 1 台存在真实业务仓库的节点作为第二个多项目正式节点。
- 调整Lobster仓库配置为`external_readonly`类型，关闭`auto_pr_enabled`与`auto_update_install_cmd`
- 落地只读仓库保护逻辑，禁止对`external_readonly`标记的仓库发起任何写操作
- 把平台总入口正式落地为：`需求澄清 -> 任务拆分 -> workflow 选择 -> 执行`，避免继续默认直接进入某条 workflow。
- 把默认 `coding-default` workflow profile 的 manifest、安装入口和 `stable/candidate` 配置正式落地，避免继续只靠“事实默认”运行。
- 为 `upgrade feedback` 补齐默认晋升/回滚规则，至少能产出 `baseline / candidate / delta / promotion_decision`。
- 把任务层补齐 `workflow_profile_id` 与 `required_capabilities`，让默认编码工作流的 preflight 约束正式生效。

## P1

- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些项目只允许到 PR gate / git sync。
- 在一台多项目服务器上完成真实安装并逐项验收 reviewer PR gate 闭环。
- 补充"外部上游仓库只读→自有克隆修改→按需向上游贡献"正式使用规范文档。
- 给“共享同一 GitHub remote 的 deploy checkout 不要单独挂 PR gate”补一条正式文档说明。
- 为 `coding-default` 之外的第二个 workflow profile 准备最小样板，但不先接入默认入口。
- 让 capability manifest、skill binding、hook policy 共享同一份机器可读导出产物。
- 为核心registry配置文件新增JSON Schema强校验，非法配置直接fail-fast。

## P2

- 视需要扩展 `project-registry`，让每个项目可独立配置 governance / reviewer / git sync / auto update 的开关和频率。
- 视需要补充多项目安装报告导出。
- 落地高危操作审计日志，所有配置变更、任务删除、权限调整都记录可溯源日志。
- 优化CLI交互体验，复杂命令新增交互式引导模式与自动补全脚本。
- 提供本地开发环境一键启动脚本，降低新开发者上手门槛。
- 默认编码工作流稳定后，再评估多 workflow 负载均衡与环节裁剪策略。
- 默认编码工作流稳定后，再评估外部 workflow / skill 下载与安装市场。

---
## 参考文档
完整执行计划与细节见：[docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md](/docs/plans/2026-03-25-remaining-tasks-and-execution-roadmap.md)

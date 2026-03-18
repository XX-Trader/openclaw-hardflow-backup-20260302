# TODO

## P0

- 为 5 台服务器补齐这轮部署后的环境配置，重点检查：
  - Telegram cron delivery 目标
  - webhook / secret / runtime.env
  - `pm-website` 以外 4 台是否仍落到 `-1003333097130`
- 环境配置完成后，按日志做一轮服务器侧验证，不先做功能级人工回归。
- 为其它服务器补齐正式 `project-registry.json`，至少再选 1 台存在真实业务仓库的节点作为第二个多项目正式节点。

## P1

- 如果未来要让 `lobster` 进入自动 PR 模式，先拿到 `openclaw/lobster` 的 `WRITE` 权限，再把它从“外部只读仓”切回“可改仓业务仓”。
- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些项目只允许到 PR gate / git sync。
- 在一台多项目服务器上完成真实安装并逐项验收 reviewer PR gate 闭环。
- 给“共享同一 GitHub remote 的 deploy checkout 不要单独挂 PR gate”补一条正式文档说明。

## P2

- 视需要扩展 `project-registry`，让每个项目可独立配置 governance / reviewer / git sync / auto update 的开关和频率。
- 视需要补充多项目安装报告导出。

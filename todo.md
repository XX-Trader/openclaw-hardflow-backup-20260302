# TODO

## P0

- 解决 `openclaw/lobster` 的 push/PR 权限，至少让 `pm-website` 运行账号对该仓库具备 `WRITE`，然后再重跑 `governance -> reviewer -> merge` 真闭环。
- 为其它服务器补齐正式 `project-registry.json`，至少再选 1 台存在真实业务仓库的节点作为第二个多项目正式节点。

## P1

- 决定 `lobster.governance.auto_pr_enabled` 何时从 `false` 打开为 `true`；当前只适合保留“命中作用范围但不自动 PR”的安全模式。
- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些项目只允许到 PR gate / git sync。
- 在一台多项目服务器上完成真实安装并逐项验收 reviewer PR gate 闭环。
- 把 `lobster` 的 `governance.watch_prefixes / exclude_prefixes / auto_pr_enabled` 这次正式配置沉淀进多项目部署文档。
- 给“共享同一 GitHub remote 的 deploy checkout 不要单独挂 PR gate”补一条正式文档说明。

## P2

- 视需要扩展 `project-registry`，让每个项目可独立配置 governance / reviewer / git sync / auto update 的开关和频率。
- 视需要补充多项目安装报告导出。

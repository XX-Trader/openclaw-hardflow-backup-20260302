# TODO

## P0

- 把真实业务仓库补进正式 `project-registry.json`，至少先确定哪台服务器要作为首个多项目正式节点。
- 在选中的多项目服务器上，先正式启用 per-repo governance / reviewer PR gate，再决定是否放开 git sync / auto update。

## P1

- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些项目只允许到 PR gate / git sync。
- 在一台多项目服务器上完成真实安装并逐项验收 reviewer PR gate 闭环。
- 把 `pm-website` 这次 dry-run 用到的 sample registry 规则沉淀进正式多项目部署文档。

## P2

- 视需要扩展 `project-registry`，让每个项目可独立配置 governance / reviewer / git sync / auto update 的开关和频率。
- 视需要补充多项目安装报告导出。

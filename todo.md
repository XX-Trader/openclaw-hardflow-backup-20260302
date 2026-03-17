# TODO

## P0

- 提交并推送当前多项目安装器改动到 GitHub 主线。
- 选择一台真实多项目服务器，执行 `install_workflow_profile.py --dry-run` 验证批量派生的 governance / reviewer / git sync / auto update job。

## P1

- 明确哪些项目允许启用 `auto_update_install_cmd`，哪些项目只允许到 PR gate / git sync。
- 在一台多项目服务器上完成真实安装并逐项验收 reviewer PR gate 闭环。

## P2

- 视需要扩展 `project-registry`，让每个项目可独立配置 governance / reviewer / git sync / auto update 的开关和频率。
- 视需要补充多项目安装报告导出。


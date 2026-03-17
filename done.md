# DONE

## 2026-03-17

- 完成 `pm-website` 的 Telegram / OpenViking / cron 稳定运行基线。
- 完成 `pm-website` 的 `governance auto-pr -> reviewer 审查 -> approval gate 自动合并` 闭环验证。
- 补齐 `大白pm / nofx / coingod / tokyo-claw` 的 HardFlow 核心文件集。
- 完成多项目服务器模板文档、审批样例和 registry 样例入口。
- 完成多项目第二阶段本地实现：
  - per-repo governance job
  - per-repo reviewer PR gate job
  - per-repo git sync job
  - per-repo auto update install job
- 完成相关定向测试与样例 JSON 校验。
- 完成多项目第二阶段提交并推送到 GitHub 主线：
  - `b627851 feat: support multi-project repo job installation`
- 完成 `pm-website` 远端多项目 dry-run：
  - 使用临时 sample registry
  - 关闭 `discovery.enabled`
  - 成功派生并验证 `lobster` 与 `openclaw-hardflow-backup-20260302-deploy` 的 governance / reviewer / git sync / auto update job

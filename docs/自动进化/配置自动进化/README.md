# 配置演进工作流

配置演进由只读检测、人工确认、窄范围修改、验证和回滚组成。

- 漂移检测：`skills/library/config-watchdog/scripts/config_watchdog.py`
- 本地快照：`skills/library/git-sync/scripts/local_snapshot_runner.py`
- 本地提交备份：`skills/library/git-sync/scripts/local_git_backup_runner.py`
- Runtime 安装：`setup.py`

凭证和机器专属值只从私有环境注入；模板仓库仅保存占位符。

# Scheduler Snapshots

该目录用于存放服务器定时任务快照，包含：

- OpenClaw `~/.openclaw/cron/jobs.json`
- 用户 crontab
- root crontab（若当前账号可读取）
- `/etc/cron.d` 列表与可读取文件
- `systemctl list-timers --all` 输出

建议每次重要变更后更新一次快照，并提交到仓库。

# QUICK_CHECK_COMMANDS

## 本地备份检查

```powershell
Get-ChildItem C:\Users\superma\.claude\hooks\hardflow
Get-Content C:\Users\superma\.claude\hooks\hardflow\BACKUP_MANIFEST.md
```

## 服务器状态检查（逐台）

```bash
openclaw hooks list | head -n 20
openclaw config get hooks.internal.entries.hardflow-experience-capture.enabled
openclaw config get hooks.internal.entries.hardflow-experience-recall.enabled
openclaw config get hooks.internal.entries.hardflow-experience-evolve.enabled
crontab -l | sed -n '/HARDFLOW EXPERIENCE MAINTENANCE/,+5p'
```

## memory 可用性

```bash
openclaw memory status --json
openclaw memory search "经验" --scope project --limit 3
```

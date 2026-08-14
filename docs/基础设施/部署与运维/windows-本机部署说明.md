# Windows 本机部署

## 前置条件

- PowerShell 7（统一使用 `pwsh`）
- Python 3.11+
- Git

## 安装

```powershell
pwsh -NoProfile -Command 'python setup.py --runtime-home "$env:USERPROFILE\.hardflow-runtime" --runtime-name local --dry-run --emit-json'
pwsh -NoProfile -Command 'python setup.py --runtime-home "$env:USERPROFILE\.hardflow-runtime" --runtime-name local --emit-json'
```

通知通道按需增加 `--notification-channel <CHANNEL> --notification-target <TARGET>`；未提供目标时安装器会移除发送配置，避免把模板值当真实地址。

## 复验

```powershell
pwsh -NoProfile -Command 'python skills/library/log-monitor/scripts/runtime_profile_healthcheck.py --help'
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_project_delivery_runtime_installer.py'
```

先保留 dry-run 输出作为变更基线，再执行实际写入。安装器会自动创建受管文件快照；回退最近一次变更使用：

```powershell
pwsh -NoProfile -Command 'python setup.py rollback --runtime-home "$env:USERPROFILE\.hardflow-runtime" --runtime-name local --emit-json'
```

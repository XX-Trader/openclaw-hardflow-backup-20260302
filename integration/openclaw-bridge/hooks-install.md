# Hooks 安装

1. 使用 `skills/library/fleet-sync/scripts/sync_openclaw_hooks_files.py` 将仓库 `hooks/` 同步到目标 Runtime 的 hooks 目录。
2. 使用 `python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --dry-run --emit-json` 核对安装边界。
3. 目标配置只引用 Runtime 内目录；凭证由私有环境文件注入。
4. 安装后执行最小命令守卫 smoke，并保留同步清单用于回滚。

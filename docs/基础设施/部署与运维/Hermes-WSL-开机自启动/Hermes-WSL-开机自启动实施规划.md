# Hermes WSL 开机自启动实施规划

> 最后更新：2026-04-15

## P0. 文档与任务盘落位

- 在 `docs/基础设施/部署与运维/Hermes-WSL-开机自启动/` 建立文档三件套
- 在根目录 `todo.md` 记录宏观任务
- 在完成后同步写入 `done.md`

## P1. 启动现状固化

- 导出当前 `HermesAgent-AutoStart` 计划任务信息
- 记录当前 Principal、Trigger、Action、LastRunTime、LastTaskResult
- 确认当前 WSL 启动入口脚本与日志路径

## P2. 启动入口收敛

- 将 `/home/runtime-user/hermes-windows-starter.sh` 改为 Windows 调度专用入口
- 让该脚本统一委派给 `/home/runtime-user/.hermes/start-hermes.sh`
- 在入口脚本中补齐任务级日志

## P3. 开机触发落地

- 新增 `HermesAgent-BootStart` 计划任务
- 触发器使用 `AtStartup`
- Principal 使用当前 Windows 用户的非交互运行模式
- 保留现有 `HermesAgent-AutoStart` 作为 `AtLogon` 兜底

## P4. 验证

- 手动触发 `HermesAgent-BootStart`
- 核对任务结果码
- 核对 WSL 启动日志
- 核对 `Hermes` 进程与连接状态
- 确认幂等退出逻辑有效

## P5. 收尾

- 更新 `docs/基础设施/部署与运维/README.md`
- 更新 `todo.md` / `done.md`
- 输出残余风险：该验证等价于“非交互启动验证”，不等价于真实整机重启回放

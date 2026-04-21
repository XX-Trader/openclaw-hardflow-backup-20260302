# Hermes WSL 开机自启动

> 状态：已实现，待整机重启回放验证
> 最后更新：2026-04-15

## 1. 需求定义

当前 `Hermes` 在 Windows 本机上的真实启动链路是：

- Windows 登录触发计划任务
- 计划任务调用 `wsl.exe`
- WSL 内部执行 `hermes-windows-starter.sh`
- 脚本再用 `screen` 拉起 `Hermes Gateway`

这条链路只能保证“登录后自启动”，不能保证“Windows 开机后、用户尚未登录时也自动拉起”。

本次目标是把它升级为真正的开机自启动，并满足以下验收标准：

1. Windows 启动后，无需人工登录，也存在可执行的启动触发器。
2. 计划任务必须能在非交互上下文中调用 `wsl.exe -d Ubuntu`。
3. 启动脚本必须具备幂等性，避免开机触发与登录触发重复拉起多个 `Hermes Gateway`。
4. 保留现有登录触发链路作为兜底，避免开机触发异常时完全失联。
5. 启动链路必须有日志，便于定位是任务未触发、WSL 未启动、还是 `Hermes` 进程未拉起。

## 2. 范围边界

本次只处理：

- Windows 计划任务触发方式
- WSL 启动入口脚本
- Hermes 启动链路日志
- 文档与任务盘同步

本次不处理：

- `OpenAI Codex HTTP 429` 额度问题
- Telegram/Feishu 通道业务逻辑
- `Hermes` 内部模型路由策略
- WSL 内 `cron` 的完整常驻治理

## 3. 子功能清单

- [x] 识别当前真实启动链路
- [x] 确认当前为登录触发而非开机触发
- [x] 设计开机触发计划任务
- [x] 统一 Windows/WSL 启动脚本入口
- [x] 验证幂等性与日志可观测性
- [x] 回写 `todo.md` / `done.md`

## 4. 当前已知风险

1. 现有 `HermesAgent-AutoStart` 的 `LogonType=Interactive`，无法在未登录状态运行。
2. WSL 发行版绑定当前 Windows 用户，不能简单切换到 `SYSTEM` 账户执行，否则可能拿不到该用户的 Ubuntu 发行版。
3. 当前 WSL 中存在 `cron @reboot` 配置，但 `cron` 服务未运行，这条链路不能作为开机启动真凭据。
4. 当前 `systemd user service` 文件存在，但 WSL 不是以 `systemd` 作为 PID 1 启动，因此该链路也未生效。

## 5. 验收状态

- [x] 已创建开机触发计划任务
- [x] 已保留登录触发兜底
- [x] 已确认启动脚本单入口
- [x] 已确认计划任务手动运行成功
- [x] 已确认 `Hermes Gateway` 进程保持单实例

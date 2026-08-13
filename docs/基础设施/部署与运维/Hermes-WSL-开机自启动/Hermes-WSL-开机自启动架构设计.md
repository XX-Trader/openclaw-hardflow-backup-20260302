# Hermes WSL 开机自启动架构设计

> 最后更新：2026-04-15

## 1. 问题复盘

现状存在三条候选启动链路：

1. Windows 登录计划任务：实际生效
2. WSL `cron @reboot`：已配置但未生效
3. WSL `systemd user service`：存在文件但当前运行时未生效

真正可靠且当前环境可控的是 Windows 计划任务，因为它不依赖 WSL 内部的 `systemd` 状态，也不要求 `cron` 先运行。

## 2. 设计目标

1. 把启动主链路调整为“Windows 开机触发”。
2. 保留现有“Windows 登录触发”作为兜底。
3. 不引入第二套 Gateway supervisor，避免与现有 `screen` 方案冲突。
4. 统一 WSL 启动脚本入口，减少重复逻辑。
5. 启动日志必须落盘到 `~/.hermes/logs/`，便于定位问题。

## 3. 方案选型

### 3.1 启动编排

采用“双触发 + 单入口 + 幂等启动”方案：

- 触发 A：Windows `AtStartup`
- 触发 B：Windows `AtLogon`
- 入口脚本：`/home/runtime-user/hermes-windows-starter.sh`
- 实际启动脚本：`/home/runtime-user/.hermes/start-hermes.sh`
- 守护方式：`screen` 单实例拉起 `python -m hermes_cli.main gateway run --replace`

### 3.2 为什么不用 `SYSTEM`

不采用 `SYSTEM` 账户直接运行 `wsl.exe`，原因是：

1. Ubuntu 发行版注册在当前 Windows 用户上下文下。
2. `SYSTEM` 账户下调用 `wsl.exe -d Ubuntu` 可能看不到该发行版。
3. 这类问题一旦出现，故障点会从 `Hermes` 变成 Windows / WSL 账户边界，排障成本更高。

因此优先选择：

- 计划任务运行账号由 `${WINDOWS_ACCOUNT}` 注入
- `LogonType` 切换为可非交互运行的模式
- 同时增加 `AtStartup` 触发器

### 3.3 幂等与防重复

两条触发链路可能在一次开机过程中都被触发，因此必须满足：

1. 启动入口只保留一个真实实现。
2. 脚本通过 `pgrep -f "hermes_cli.main gateway run"` 判断是否已运行。
3. 已运行时直接退出，不再重复创建 `screen` 会话。

## 4. 影响面分析

### 4.1 直接影响

- Windows 计划任务：
  - `HermesAgent-AutoStart`
  - 新增或更新开机触发计划任务
- WSL 启动脚本：
  - `/home/runtime-user/hermes-windows-starter.sh`
  - `/home/runtime-user/.hermes/start-hermes.sh`

### 4.2 间接影响

- `Hermes` 的 Telegram / Feishu 通道会在更早时机启动
- 登录后再次触发时依赖幂等检测避免重复实例
- 启动日志将成为后续排障主证据

## 5. 失败回滚策略

若开机触发任务注册失败或验证不通过：

1. 保留原 `HermesAgent-AutoStart` 登录触发，不做删除。
2. 仅回退新增的开机触发任务。
3. 启动脚本保持兼容原调用方式。

## 6. 验证点

1. 计划任务注册后，能以非交互上下文成功运行。
2. 任务手动触发后，WSL 内能看到对应日志。
3. `Hermes` 已运行时再次触发，日志显示幂等退出。
4. 不出现第二个 `Hermes Gateway` 实例。

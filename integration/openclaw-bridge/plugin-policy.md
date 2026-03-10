# Channel / Plugin / Skills 策略

## 总原则

消息通道、插件生命周期和 skills 装载统一回收到官方 surface。
本仓库只维护 overlay 配置和业务约束，不再维护私有 Telegram 分支实现。

## 当前收口规则

- `channels.telegram` 仍然通过 `openclaw/openclaw.json` / `~/.openclaw/openclaw.json` 读取。
- `plugins.entries.telegram` 由官方 plugin surface 管理。
- 仓库 `skills/` 目录通过 `skills.load.extraDirs` 注入官方 skills loader。

## 允许保留在 Overlay 的内容

- `allowFrom`
- `groupPolicy`
- `groupAllowFrom`
- `commands`
- `workspace`
- `agentDir`
- agent routing / binding
- 其他业务级配置包装

## 不再由 Overlay 统一覆盖的内容

- `channels.telegram.botToken` 等每台服务器独立的 Telegram 凭据
- 通道协议实现
- 插件生命周期
- skills 安装/发现主流程

## 运行时约束

- `install_workflow_profile.py` 在合并 overlay 到本地 `~/.openclaw/openclaw.json` 时，保留服务器已有的 Telegram 凭据。
- 仓库 `openclaw/openclaw.json` 不再保存统一的 Telegram `botToken`。
- 新服务器若需要启用 Telegram，必须在本地配置独立 token，而不是依赖仓库默认值。

## 验证

```bash
openclaw plugins list
openclaw config get channels.telegram
```

预期：

- `plugins list` 能看到启用的 telegram 插件。
- `config get channels.telegram` 能读到 Telegram 配置。
- 多台服务器的 `botToken` 不会再因 workflow 安装器被统一覆盖。

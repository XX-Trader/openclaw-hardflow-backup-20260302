# Channel / Plugin / Skills 策略

## 总原则

消息通道、插件生命周期和 skills 装载统一回收至官方 surface，本仓库只维护 overlay 配置与业务约束。

## 当前收口规则

- `channels.telegram` 以 `openclaw/openclaw.json` / `~/.openclaw/openclaw.json` 为唯一配置入口。
- `plugins.entries.telegram` 由官方 plugin surface 管理。
- 本仓库不再维护私有 Telegram 分支实现。
- 本仓库 `skills/` 目录通过 `skills.load.extraDirs` 注入官方 skills loader。

## 允许保留在 overlay 的内容

- `allowFrom`
- `groupPolicy`
- `workspace`
- `agentDir`
- agent routing / binding
- 其他业务级配置包装

## 不再由 overlay 接管的内容

- 通道协议实现
- 插件生命周期
- skills 安装/发现主流程

## 验证

```bash
openclaw plugins list
openclaw config get channels.telegram
```

预期：

- `plugins list` 可看到启用的 telegram 插件。
- `config get channels.telegram` 能从统一配置入口读到 Telegram 配置。

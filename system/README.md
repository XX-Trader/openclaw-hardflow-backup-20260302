# System templates

本目录只保存可复用的系统服务模板，不保存任何主机的运行态快照、用户清单、日志、凭证或绝对路径。

## Gateway 用户服务

`systemd_user_units/openclaw-gateway.service` 从以下文件读取运行环境：

```text
~/.config/openclaw/runtime.env
```

按需配置：

```dotenv
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_GATEWAY_TOKEN=<runtime-secret>
```

安装与验证：

```bash
install -Dm644 system/systemd_user_units/openclaw-gateway.service \
  "$HOME/.config/systemd/user/openclaw-gateway.service"
systemctl --user daemon-reload
systemctl --user enable --now openclaw-gateway.service
systemctl --user status openclaw-gateway.service
```

`runtime.env` 应保持在仓库之外，并限制为当前用户可读。

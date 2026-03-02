# REQUIRED_INFO

## 部署前必须确认的信息

1. 服务器清单（别名/IP/用户）
2. OpenClaw 配置文件路径（通常 `~/.openclaw/openclaw.json`）
3. hooks 主目录（建议 `~/.openclaw/hardflow-hooks`）
4. memory provider 方案
5. embedding 模型与 API 提供商
6. 日志目录（建议 `~/.openclaw/logs`）
7. 是否启用定时维护（daily/weekly/monthly）
8. 重启方式（systemd 服务名或手工命令）

## memory 关键配置（OpenRouter 方案）

在 `openclaw.json` 确认：

```json
{
  "memorySearch": {
    "provider": "openai",
    "model": "baai/bge-m3",
    "remote": {
      "baseUrl": "https://openrouter.ai/api/v1",
      "apiKey": "<sk-or-...>"
    }
  }
}
```

## 安全建议

1. 不把 API Key 写入文档仓库。
2. key 仅通过环境变量或服务器本地配置注入。
3. 验证时只输出 key 指纹/前缀，不打印全量。

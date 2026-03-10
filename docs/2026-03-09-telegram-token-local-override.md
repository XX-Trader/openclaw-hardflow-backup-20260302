# 2026-03-09 Telegram Token 本地优先说明

## 变更目的

避免 workflow 安装器在多台服务器之间统一覆盖 Telegram 机器人 token。

## 变更内容

1. 仓库 `openclaw/openclaw.json` 不再保存统一的 `channels.telegram.botToken`。
2. `scripts/openclaw-ops/install_workflow_profile.py` 在同步 overlay 到本地 `~/.openclaw/openclaw.json` 时，保留服务器已有的 Telegram 凭据。
3. 允许继续由仓库 overlay 管理 Telegram 的通用行为配置，例如：
   - `enabled`
   - `commands`
   - `allowFrom`
   - `groupPolicy`
   - `groupAllowFrom`

## 当前规则

- 每台服务器的 Telegram `botToken` 必须在本地配置。
- workflow 安装器不再用仓库默认值覆盖本地 token。
- 新服务器首次部署后，如果需要 Telegram，必须单独写入本机 token。

## 影响

- 重新运行 `install_workflow_profile.py` 不会再把所有服务器写成同一个 Telegram 机器人。
- 已经被统一覆盖过的服务器，仍需单独恢复各自本地 token。

# OpenClaw Gateway Service 冲突防护说明

日期：2026-03-11

## 背景

在 `nofx` 服务器上出现过一类运行时冲突：

- 系统级 service：`openclaw.service`
- 用户级 service：`openclaw-gateway.service`

两者同时存在时，会争抢同一个 Gateway 端口，表现为：

- `openclaw.service` 持续 `auto-restart`
- 旧 `openclaw-gateway` 进程长期驻留
- CPU 异常升高
- cron 任务出现级联超时

## 现在的统一策略

仓库新增了：

- `scripts/openclaw-ops/policy/gateway_service_manager.py`

所有相关同步/部署脚本现在都改为通过这个 helper 重启 Gateway，而不是直接裸调 `openclaw gateway restart`。

## 规则

`gateway_service_manager.py` 的默认规则如下：

1. 如果检测到系统级 `openclaw.service` 存在，则优先以它作为唯一受管 service。
2. 如果同时检测到用户级 `openclaw-gateway.service`，会先停用并清理它，再启用/重启系统级 service。
3. 如果系统级 service 不存在，但用户级 service 存在，则继续使用用户级 service。
4. 如果两种 service 都不存在，才回退到 `openclaw gateway restart`。

## 已接入的脚本

- `scripts/openclaw-ops/sync_policy_enforcer_to_servers.sh`
- `scripts/openclaw-ops/sync_policy_enforcer_to_servers.ps1`
- `scripts/openclaw-ops/sync_gpt54_to_servers.sh`
- `scripts/openclaw-ops/sync_gpt54_to_servers.ps1`
- `scripts/openclaw-ops/sync_model_to_doubao_servers.sh`
- `scripts/openclaw-ops/sync_model_to_doubao_servers.ps1`
- `scripts/openclaw-ops/sync_agents_12_to_servers.sh`
- `scripts/hardflow/deploy-evolution-hooks.sh`

## 目的

把“同机只保留一个 Gateway supervisor”从人工约定，变成脚本默认行为，避免部署后再次出现双 service 冲突。

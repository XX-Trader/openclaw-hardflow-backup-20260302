# 部署与运维

> 最后更新：2026-03-29

## 文档清单

| 文档 | 说明 |
|------|------|
| [Linux 服务器部署说明](linux-服务器部署说明.md) | nofx 等 Linux 服务器部署流程 |
| [Windows 本机部署说明](windows-本机部署说明.md) | 本机开发环境部署 |
| [安装与工作流部署说明](安装与工作流部署说明.md) | setup.py + workflow_setup.py 流程 |
| [Gateway 守护进程说明](gateway-守护进程说明.md) | openclaw gateway 守护/监控 |
| [Hermes WSL 开机自启动](Hermes-WSL-开机自启动/README.md) | Windows 开机触发 WSL Hermes 的设计与实施 |
| [Hermes Discord 趋势回测机器人](Hermes-Discord-趋势回测机器人/README.md) | 独立 Hermes profile、Discord 接线与群组 mention 规则 |
| [多项目服务器模板](多项目服务器模板.md) | 多项目共存的服务器配置模板 |
| [Rollout 进度追踪](rollout-进度追踪.md) | 5 台服务器推广进度 |
| [项目维护与排障索引](项目维护与排障索引.md) | 按问题类型定位文件的排障速查 |

## 核心入口文件

| 文件 | 说明 |
|------|------|
| `setup.py` | 项目安装入口 |
| `scripts/openclaw-ops/policy/workflow_setup.py` | 工作流部署器（130KB） |
| `scripts/openclaw-ops/cron_setup.py` | Cron 安装器（187KB） |
| `scripts/openclaw-ops/bootstrap_runtime_agents.py` | Agent 运行时初始化 |

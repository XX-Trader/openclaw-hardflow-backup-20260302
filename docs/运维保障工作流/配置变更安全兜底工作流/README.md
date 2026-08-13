# 配置变更安全兜底工作流

> 状态：✅ 已上线 | 触发方式：每4小时自动触发
> 上级目录：[运维保障工作流](../README.md)

## 功能概述

配置文件安全看门狗，对 `openclaw.json`、`cron/jobs.json`、Agent SOUL.md 等关键配置定期快照，检测未授权变更，异常时支持一键回滚，避免配置变更导致服务崩溃。

## 代码审计结果

> ⚠️ 用户规划中标注为"开发中"，但代码审计发现 **脚本已完整实现（530行）** 且 **Cron Job 已注册**。

## 核心能力

1. **配置快照** — 对监控文件取 SHA-256 hash + 文件备份
2. **变更检测** — 与最新快照对比，报告已修改/新增/删除的文件
3. **JSON 语法校验** — 自动校验所有 JSON 配置文件语法
4. **openclaw.json 业务校验** — 检查 Agent 目录/Hook handler/模型配置
5. **一键回滚** — 从最新快照恢复指定配置文件
6. **快照生命周期** — 自动保留最近 10 个快照

## 核心组件

| 组件 | 路径 | 规模 |
|------|------|------|
| 配置看门狗 | `skills/library/config-watchdog/scripts/config_watchdog.py` | 530行 / 19KB |
| 本地快照同步 | `skills/library/git-sync/scripts/local_snapshot_runner.py` | 6KB |
| 配置修复重启 | `skills/library/config-watchdog/scripts/config_watchdog.py` | 4KB |
| Gateway 验证 | `skills/library/config-watchdog/scripts/config_watchdog.py` | 1.7KB |

## 监控文件清单

- `openclaw.json`
- `cron/jobs.json`
- `hooks/hardflow-audit/handler.js`
- `hooks/hardflow-failure-detector/handler.js`
- `agents/*/SOUL.md`（glob 匹配）

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| config_watchdog（配置安全巡检） | coordinator | 每4小时 |
| local_config_snapshot | coordinator | 每1小时 |

## CLI 用法

```bash
# 创建快照
python config_watchdog.py --config-dir ~/.openclaw/ --snapshot

# 变更检测
python config_watchdog.py --config-dir ~/.openclaw/ --verify

# 语法校验
python config_watchdog.py --config-dir ~/.openclaw/ --validate

# 回滚指定文件
python config_watchdog.py --config-dir ~/.openclaw/ --rollback --target openclaw.json
```

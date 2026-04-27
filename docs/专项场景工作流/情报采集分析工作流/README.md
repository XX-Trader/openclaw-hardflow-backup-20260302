# 情报采集分析工作流

> 状态：✅ 已上线 | 触发方式：每日自动触发 / 人工触发
> 上级目录：[专项场景工作流](../README.md)

## 功能概述

自动化的外部情报采集系统，包括三个独立通道：上游社区更新、网页情报采集、GitHub 开源项目扫描。每日低峰期自动执行，将采集结果结构化存档，异常源自动建单修复。

## 核心能力

1. **上游社区同步** — 拉取 OpenClaw 上游仓库最新代码 + 自动安装
2. **网页情报采集** — 采集关注的网页情报源，存档变更，检测失败源
3. **开源项目扫描** — 扫描 GitHub 高信号仓库和 Skill4Agent 技能库
4. **自动建单** — 采集失败的源自动创建修复 TODO

## 核心组件

| 组件 | 路径 | 规模 |
|------|------|------|
| 上游更新器 | `scripts/openclaw-ops/auto_update_install_runner.py` | 15KB |
| 情报采集器 | `scripts/openclaw-ops/web_intel_collect_runner.py` | 41KB |
| 情报评审器 | `scripts/openclaw-ops/web_intel_review_runner.py` | 42KB |
| 开源进化器 | `scripts/openclaw-ops/github_web_evolution_runner.py` | 78KB |
| 情报源运行时 | `scripts/openclaw-ops/web_sources_runtime.py` | 13KB |
| 供应商目录 | `scripts/openclaw-ops/vendor_source_catalog.py` | 6KB |

## 关联定时任务

| Cron 任务 | Agent | 频率 |
|-----------|-------|------|
| auto_update_daily | coordinator | 每日 03:00 |
| web_intel_collect_daily | coordinator | 每日 03:30 |
| github_web_evolution_daily | coordinator | 每日 04:00 |

## 三通道架构

```mermaid
graph LR
    subgraph 通道一：上游社区
        A1[OpenClaw 上游仓库] -->|git pull| B1[auto_update_install_runner]
        B1 -->|setup.py --yes| C1[自动安装到 .openclaw/]
    end
    subgraph 通道二：网页情报
        A2[网页情报源列表] -->|爬取| B2[web_intel_collect_runner]
        B2 -->|变更检测| C2[存档 + Telegram 通知]
        B2 -->|失败源| D2[自动建单修复]
    end
    subgraph 通道三：开源项目
        A3[GitHub 高信号仓库] -->|扫描| B3[github_web_evolution_runner]
        A4[Skill4Agent 技能库] -->|扫描| B3
        B3 -->|评估任务| C3[创建评估 TODO]
    end
```

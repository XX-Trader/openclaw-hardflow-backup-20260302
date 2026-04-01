---
name: web-intelligence
description: >
  Web 情报采集分析技能。用于上游信息同步、网页内容爬取、
  GitHub 仓库扫描、外部模式评估。
  当需要采集外部信息或评估新技术方案时使用。
allowed-tools: Bash, Read, Grep, WebBrowser
---

# Web 情报采集分析操作手册

## 适用场景

- 定期采集上游项目更新（GitHub Release/Changelog）
- 扫描技术社区新方案和最佳实践
- 爬取指定网页内容并结构化存储
- 评估外部 workflow/skill/tool 是否适合引入

## 操作流程

### 1. GitHub 仓库扫描

```bash
python3 ~/scripts/openclaw-ops/github_web_evolution_runner.py --scan
```

### 2. 网页内容采集

```bash
python3 ~/scripts/openclaw-ops/web_intel_runner.py --url <target_url>
```

### 3. 上游同步

```bash
python3 ~/scripts/openclaw-ops/upstream_sync_runner.py
```

### 4. 外部模式评估

当发现外部新方案时，必须输出三段结论：
1. 当前系统是否已有同类能力
2. 当前是已实现、未启用还是完全缺失
3. 如果要接入，应落在 Skill / 脚本 / Job / 任务中心哪一层

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `github_web_evolution_runner.py` | GitHub 仓库扫描 |
| `web_intel_runner.py` | 通用网页情报采集 |
| `upstream_sync_runner.py` | 上游项目同步 |

## 约束

- 爬取操作遵守 robots.txt
- 采集结果存储在 `~/.openclaw/intel/` 目录
- 外部方案不直接覆盖本地配置，必须先做差异评估

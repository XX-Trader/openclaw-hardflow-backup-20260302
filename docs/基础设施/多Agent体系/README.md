# 多 Agent 体系

> 最后更新：2026-03-29

## 概述

OpenClaw 采用 13+1 多 Agent 协作架构。每个 Agent 有独立的工作空间、SOUL 角色定义、模型绑定。

## Agent 清单

| Agent | 名称 | 模型 | 允许子Agent | 职责 |
|-------|------|------|-------------|------|
| main | 大总管 | gpt-5.4 | 13 | 默认入口，总调度 |
| coordinator | coordinator | gpt-5.4 | 13 | 任务协调与分配 |
| doc-writer | doc-writer | glm-4.7 | 0 | 文档生成 |
| frontend-dev | frontend-dev | gpt-5.3-codex | 0 | 前端开发 |
| backend-dev | backend-dev | gpt-5.3-codex | 0 | 后端开发 |
| reviewer | 代码审核 | gpt-5.4 | 0 | 代码评审+安全审计 |
| tester | 测试验收 | glm-4.7 | 0 | 测试用例+验收 |
| deployer | deployer | glm-4.7 | 0 | 部署执行 |
| agent-factory | agent-factory | gpt-5.3-codex | 3 | Agent 创建/管理 |
| ops-agent | ops-agent | glm-4.7 | 2 | 运维巡检 |
| optimization-agent | optimization-agent | gpt-5.3-codex | 2 | 优化进化 |
| project-agent | project-agent | gpt-5.3-codex | 1 | 项目索引/规划 |
| web-agent | web-agent | glm-4.7 | 0 | 网页交互 |
| explorer | explorer | gpt-5.4-mini | 0 | 探索研究 |

## 相关文件

| 文件 | 说明 |
|------|------|
| `agents/agent_index.md` | Agent 运行时绑定索引（自动生成） |
| `agents/agent_index.json` | Agent 索引 JSON |
| `agents/agent_capability_manifest.json` | 能力清单（13KB） |
| `agents/<agent-id>/SOUL.md` | 各 Agent 角色定义 |
| `scripts/openclaw-ops/switch_model_tier.py` | 模型切换脚本 |
| `scripts/openclaw-ops/model_tier_profiles.json` | 模型档位配置 |
| `cron/jobs_agent_mapping.md` | Cron→Agent 映射表 |

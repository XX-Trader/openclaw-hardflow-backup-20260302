---
name: fault-troubleshoot
description: 故障知识库查询与排查。基于历史故障文档自动匹配类似问题，返回诊断步骤和修复方案。
---

# 🔧 故障排查修复技能

## 概述

基于 `docs/` 下的历史故障文档自动构建结构化知识库索引，支持按关键词/症状模糊查询匹配类似故障。

## 使用场景

- Agent 遇到未知错误时，自动查库匹配历史同类故障
- 运维排障前快速定位历史修复方案
- 新团队成员了解系统常见故障类型

## 使用方式

### 构建索引

```bash
python3 $HOME/.openclaw/ops/fault_knowledge_base.py \
  --docs-dir /path/to/docs/ \
  --build-index \
  --index-output /path/to/fault-index.json
```

### 查询故障

```bash
python3 $HOME/.openclaw/ops/fault_knowledge_base.py \
  --docs-dir /path/to/docs/ \
  --query "配置文件启动失败 plugin not found" \
  --top 3
```

### 使用已有索引查询（更快）

```bash
python3 $HOME/.openclaw/ops/fault_knowledge_base.py \
  --index-path /path/to/fault-index.json \
  --query "cron任务不执行"
```

## 故障分类（7 类）

| 类别 | 示例关键词 |
|---|---|
| 配置故障 | config, json, 插件, 路径错误 |
| 定时任务故障 | cron, 调度, 卡住, executor |
| 部署故障 | deploy, SSH, SCP, pm2 |
| Agent 故障 | agent, 会话, 模型, rate limit |
| 数据/存储故障 | database, sqlite, OOM |
| 进化/自优化故障 | evolution, 治理, benchmark |
| 网络/API 故障 | HTTP, 429, timeout, token |

## 输出格式

查询返回 Markdown 格式的匹配结果，包含：
- 相关度评分
- 故障分类
- 症状描述
- 修复步骤
- 相关源文件

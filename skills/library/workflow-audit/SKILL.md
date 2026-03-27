---
name: workflow-audit
description: 对 Agent 工作流会话进行审计。支持结果摘要模式和详细明细模式，检测未完成任务、异常声明和进度偏差。
---

# 🔍 Workflow Audit 技能

## 概述

对 Agent 工作流会话进行事后审计，验证任务完成质量。

## 使用场景

- 用户怀疑 Agent 虚报进度时
- 定期工作流质量抽查
- 重大部署后复盘

## 使用方式

### 结果模式（默认）

```bash
python3 $HOME/.openclaw/ops/workflow_audit.py \
  --session-dir $HOME/.openclaw/sessions/<session-id>/ \
  --mode summary
```

输出简洁的一页摘要：任务总数、完成率、异常数、诚信度评分。

### 明细模式

```bash
python3 $HOME/.openclaw/ops/workflow_audit.py \
  --session-dir $HOME/.openclaw/sessions/<session-id>/ \
  --mode detail
```

逐条列出每个任务的声明内容 + 验证结果 + 证据链。

### 批量审计

```bash
python3 $HOME/.openclaw/ops/workflow_audit.py \
  --session-dir $HOME/.openclaw/sessions/ \
  --mode summary \
  --batch \
  --since-hours 24
```

批量扫描最近 24 小时所有会话，输出汇总报告。

## 输出格式

- JSON: `<output-dir>/audit-<timestamp>.json`
- Markdown: `<output-dir>/audit-<timestamp>.md`

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 全部通过 |
| 1 | 发现警告级问题 |
| 2 | 发现严重不一致 |

## 依赖

- `claim_verification_auditor.py`（声明交叉验证）
- `unified_exception_logger.py`（异常分类）

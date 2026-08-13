---
name: web-intelligence
description: 通用外部资料采集、复核和适用性评估技能，用于维护可追溯来源与候选改进项。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}}}
---

# 外部资料采集与复核

## Owner

- `scripts/web_intel_collect_runner.py`：按来源清单采集并生成结构化摘要。
- `scripts/web_intel_review_runner.py`：复核变化、适用范围和风险。
- `scripts/github_web_evolution_runner.py`：发现通用工程候选。
- `scripts/web_sources_runtime.py`：解析来源配置。

## 约束

来源、时间、状态码、摘要和失败原因必须可追溯；外部模式先评估再进入项目流水线。报告隐藏内部绝对路径和凭证。

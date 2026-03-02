---
name: "logv"
description: "logv 技能"
version: "1.0.0"
triggers:
  keywords:
    - "日志"
    - "日志查看"
    - "日志分析"
    - "log"
    - "log viewer"
    - "去重"
  auto_trigger: true
  confidence_threshold: 0.7
---

name: logv
description: "通用日志查看器与去重工具。支持大日志文件压缩去重、异常统计、业务逻辑分析、重要日志保护、配置持久化。触发条件：用户提到日志、log、需要分析日志文件时自动触发。"
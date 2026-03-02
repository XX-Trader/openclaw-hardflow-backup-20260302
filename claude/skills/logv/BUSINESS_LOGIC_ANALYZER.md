# 业务逻辑分析器使用指南

## 概述

业务逻辑分析器是一个**通用日志分析工具**，通过配置文件可以适配任意项目的日志分析需求。

### 架构设计

```
通用分析器 (business_logic_analyzer.py)
    ├── 核心分析引擎（项目无关）
    └── 配置文件驱动 (JSON格式)
         ├── 量化交易项目 (config/trading_bot.json)
         ├── Web应用项目 (config/web_app.json)
         └── 其他项目...
```

---

## 快速开始

### 1. 使用默认配置（不进行业务逻辑分析）

```bash
python log_deduplicator.py app.log
```

### 2. 使用项目特定配置

```bash
python log_deduplicator.py app.log --business-config config/trading_bot.json
```

---

## 配置文件结构

### 完整配置示例

```json
{
  "description": "项目描述",

  "flow_steps": [
    {
      "name": "步骤名称",
      "pattern": "匹配此步骤的正则表达式"
    }
  ],

  "required_steps": ["必需步骤1", "必需步骤2"],

  "flow_grouping": {
    "start_pattern": "标记流程开始的正则",
    "end_pattern": "标记流程结束的正则",
    "id_pattern": "提取流程ID的正则（使用捕获组）"
  },

  "consistency_checks": [
    {
      "name": "问题名称",
      "pattern": "匹配问题的正则表达式",
      "severity": "严重程度: critical|high|medium|low",
      "description": "问题描述"
    }
  ],

  "parameter_checks": [
    {
      "name": "参数检查名称",
      "pattern": "匹配参数的正则表达式",
      "severity": "严重程度",
      "description": "检查描述"
    }
  ]
}
```

---

## 配置项详解

### 1. flow_steps - 流程步骤定义

定义项目中需要跟踪的关键步骤，用于统计和完整性检查。

**示例：**
```json
{
  "flow_steps": [
    {"name": "接收请求", "pattern": "\\\\[API\\].*接收.*请求"},
    {"name": "验证参数", "pattern": "\\\\[VALIDATE\\].*验证.*参数"},
    {"name": "处理业务", "pattern": "\\\\[PROCESS\\].*处理.*业务"},
    {"name": "返回响应", "pattern": "\\\\[RESPONSE\\].*返回.*响应"}
  ]
}
```

**用途：**
- 统计各步骤执行次数
- 检测流程完整性
- 计算完成率

### 2. required_steps - 必要步骤

定义流程中必须存在的步骤，如果缺失会报告问题。

**示例：**
```json
{
  "required_steps": ["接收请求", "验证参数", "处理业务"]
}
```

### 3. flow_grouping - 流程分组配置

定义如何将日志按流程分组（例如按请求ID、交易ID等）。

**示例：**
```json
{
  "flow_grouping": {
    "start_pattern": "\\\\[QUEUE\\].*新交易已加入队列",
    "end_pattern": "交易处理完成",
    "id_pattern": "新交易已加入队列:\\s*(0x[a-f0-9]{8,})"
  }
}
```

**用途：**
- 按单个流程（如单次请求、单笔交易）分析
- 检测流程中断
- 分析单流程的参数异常

### 4. consistency_checks - 一致性检查

定义全局一致性问题检测规则。

**示例：**
```json
{
  "consistency_checks": [
    {
      "name": "数据库连接失败",
      "pattern": "数据库.*连接.*失败",
      "severity": "high",
      "description": "无法连接到数据库"
    },
    {
      "name": "参数为空",
      "pattern": "参数.*=.*None|参数.*=.*''",
      "severity": "medium",
      "description": "关键参数为空值"
    },
    {
      "name": "API超时",
      "pattern": "API.*超时|timeout",
      "severity": "medium",
      "description": "API调用超时"
    }
  ]
}
```

### 5. parameter_checks - 参数检查

定义流程级别的参数异常检测规则。

**示例：**
```json
{
  "parameter_checks": [
    {
      "name": "用户ID为空",
      "pattern": "用户ID.*=.*None",
      "severity": "critical",
      "description": "用户ID不能为空"
    },
    {
      "name": "金额为负",
      "pattern": "金额.*=-\\d+",
      "severity": "high",
      "description": "金额不能为负数"
    }
  ]
}
```

---

## 配置文件模板

### 1. 通用Web应用

```json
{
  "description": "Web应用日志分析",

  "flow_steps": [
    {"name": "接收请求", "pattern": "\\\\[REQUEST\\].*接收.*请求"},
    {"name": "验证Token", "pattern": "\\\\[AUTH\\].*验证.*Token"},
    {"name": "处理业务", "pattern": "\\\\[PROCESS\\].*处理.*业务"},
    {"name": "返回响应", "pattern": "\\\\[RESPONSE\\].*返回.*响应"}
  ],

  "required_steps": ["接收请求", "验证Token"],

  "flow_grouping": {
    "start_pattern": "\\\\[REQUEST\\].*接收.*请求.*ID:\\s*(\\\d+)",
    "end_pattern": "\\\\[RESPONSE\\].*返回.*响应",
    "id_pattern": "请求.*ID:\\s*(\\\d+)"
  },

  "consistency_checks": [
    {
      "name": "数据库错误",
      "pattern": "数据库.*错误|Database.*error",
      "severity": "critical",
      "description": "数据库操作失败"
    },
    {
      "name": "认证失败",
      "pattern": "Token.*无效|认证.*失败",
      "severity": "high",
      "description": "用户认证失败"
    }
  ],

  "parameter_checks": [
    {
      "name": "用户ID缺失",
      "pattern": "用户ID.*=.*None",
      "severity": "critical",
      "description": "用户ID不能为空"
    }
  ]
}
```

### 2. 定时任务/批处理

```json
{
  "description": "批处理任务日志分析",

  "flow_steps": [
    {"name": "任务启动", "pattern": "\\\\[TASK\\].*任务.*启动"},
    {"name": "读取数据", "pattern": "\\\\[READ\\].*读取.*数据"},
    {"name": "处理数据", "pattern": "\\\\[PROCESS\\].*处理.*数据"},
    {"name": "保存结果", "pattern": "\\\\[SAVE\\].*保存.*结果"},
    {"name": "任务完成", "pattern": "\\\\[TASK\\].*任务.*完成"}
  ],

  "required_steps": ["任务启动", "处理数据", "任务完成"],

  "consistency_checks": [
    {
      "name": "数据读取失败",
      "pattern": "读取.*失败|读取.*错误",
      "severity": "high",
      "description": "无法读取输入数据"
    },
    {
      "name": "任务超时",
      "pattern": "任务.*超时|timeout",
      "severity": "medium",
      "description": "任务执行超时"
    }
  ]
}
```

---

## 严重程度说明

| 级别 | 说明 | 处理建议 |
|------|------|----------|
| **critical** | 严重问题，系统可能无法正常工作 | 立即处理 |
| **high** | 高优先级问题，影响核心功能 | 优先处理 |
| **medium** | 中等问题，不影响核心功能 | 计划处理 |
| **low** | 低优先级问题，优化建议 | 有空处理 |

---

## 输出报告

使用业务逻辑分析后会生成 `business_logic_report.txt`，包含：

1. **按严重程度分组的问题列表** - 最多显示10个，附带证据和建议
2. **流程统计** - 各步骤执行次数
3. **参数异常统计** - 按类型分组的异常数量
4. **数据一致性问题** - 高频问题的统计
5. **问题总结** - 按严重程度统计的总数

---

## 高级用法

### 1. 只运行业务逻辑分析（不去重）

如果只想分析业务逻辑，可以结合 `--dry-run` 使用：

```bash
python log_deduplicator.py app.log --dry-run --business-config config/trading_bot.json
```

### 2. 为不同项目创建多个配置

```
config/
├── trading_bot.json       # 量化交易机器人
├── web_app.json          # Web应用
├── batch_job.json        # 批处理任务
└── example.json          # 配置模板
```

使用时指定对应的配置文件：

```bash
python log_deduplicator.py app.log --business-config config/web_app.json
```

### 3. 调试正则表达式

如果正则表达式不匹配预期的日志，可以：

1. 使用在线正则测试工具（如 regex101.com）
2. 在配置文件中临时简化正则，测试是否能匹配
3. 查看生成的报告，确认哪些步骤被正确统计

---

## 常见问题

### Q: 为什么有些问题没有检测到？

A: 检查以下几点：
1. 正则表达式是否正确（注意转义，JSON中需要双反斜杠 `\\`）
2. 日志级别是否正确
3. 问题是否在配置文件中定义

### Q: 如何添加新的检测规则？

A:
1. 在配置文件中添加对应的 `consistency_checks` 或 `parameter_checks`
2. 使用正则表达式匹配问题日志
3. 指定合适的严重程度和描述

### Q: 流程分组配置是必须的吗？

A: 不是必须的。如果不配置 `flow_grouping`，则不会进行按流程分析，但仍会进行全局一致性检查和流程统计。

---

## 版本历史

- **v2.0.0** (2026-01-09): 重构为通用分析器，支持配置文件驱动
- **v1.3.0** (2026-01-09): 添加量化交易项目的业务逻辑分析

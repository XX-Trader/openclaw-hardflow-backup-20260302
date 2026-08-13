---
name: "intelligent-router"
description: "intelligent-router 技能"
description_zh: "intelligent-router技能，详见 SKILL.md"
version: "1.0.0"
triggers:
  keywords:
    - "智能路由"
    - "任务路由"
    - "subagent"
    - "自动路由"
    - "117个subagent"
  auto_trigger: true
  confidence_threshold: 0.7
---

# 智能路由插件 (Intelligent Router)

> **版本**: 1.0.0
> **更新时间**: 2026-01-07
> **作者**: maintainers
> **类型**: 自动化技能

## 📖 技能概述

智能路由插件是一个基于关键词匹配和文件类型检测的自动化任务路由系统。它能够根据用户输入和上下文，自动将任务路由到最合适的专业 Agent，在独立上下文中执行，保持主窗口简洁。

## 🎯 核心价值

### 1. 零配置自动激活
- 无需手动指定 Agent，系统自动识别并路由
- 基于 150+ 关键词和 80+ 文件类型的智能匹配
- 支持上下文感知（文件类型、任务类型、用户显式指定）

### 2. 上下文隔离
- 所有路由任务在独立上下文中执行
- 避免主窗口上下文膨胀
- 提高响应速度和质量

### 3. 高效并行执行
- 支持多个 Agent 并行处理不同任务
- 节省约 58% 的执行时间（相比串行）
- 结果自动整合到主窗口

### 4. 模块化设计
- JSON 配置文件，易于编辑和维护
- Python 路由引擎，可扩展和定制
- 完整的示例和文档

## 🚀 快速开始

### 自动激活机制

当满足以下任一条件时，插件自动激活：

1. **关键词匹配**：用户输入包含特定关键词
2. **文件类型检测**：正在编辑特定类型文件
3. **任务类型识别**：任务明显属于某个专业领域
4. **用户显式指定**：用户明确要求"使用 XXX agent"

### 使用示例

```markdown
# 示例 1: 关键词触发
用户: "帮我审查这段代码"
系统: 自动路由到 code-reviewer Agent

# 示例 2: 文件类型触发
上下文: 正在编辑 .vue 文件
用户: "优化这个组件"
系统: 自动路由到 frontend-developer Agent

# 示例 3: 显式指定
用户: "使用 python-expert 优化这段代码"
系统: 路由到 python-expert Agent（无视关键词/文件类型）

# 示例 4: 显式技能调用
用户: "[调用技能: pdf] 提取这个 PDF 中的表格数据"
系统: 直接调用 pdf 技能，跳过路由匹配

# 示例 5: 显式 Agent 调用
用户: "[调用 Subagent: smart-flow:python-expert] 优化这段代码性能"
系统: 直接路由到 python-expert Subagent
```

## 🎯 显式调用系统

### 调用格式

智能路由支持三种显式调用格式：

#### 1. 技能调用
```
[调用技能: <技能名>] 执行 <任务描述>
```

**示例**：
- `[调用技能: pdf] 提取这个 PDF 中的表格数据`
- `[调用技能: frontend-design] 设计一个登录页面`
- `[调用技能: auto-fix] 修复这个测试失败的问题`

#### 2. Agent 调用
```
[调用 Subagent: <Agent 类型>] 执行 <任务描述>
```

**示例**：
- `[调用 Subagent: smart-flow:python-expert] 优化这段代码性能`
- `[调用 Subagent: smart-flow:backend-developer] 创建用户认证 API`
- `[调用 Subagent: smart-flow:database-architect] 设计订单管理系统的数据库`

#### 3. 组合调用
```
[调用组合: <组合名>] 执行 <任务描述>
```

**示例**：
- `[调用组合: 数据分析组合] 分析这个数据管道的质量和性能`
- `[调用组合: 全栈开发组合] 从零开发一个待办事项应用`
- `[调用组合: 代码审查组合] 审查这个 PR 的代码质量和安全性`

### 显式调用识别

系统使用以下正则表达式识别显式调用：

```python
# config/intent_patterns.json
{
  "explicit_call_patterns": [
    "\\[调用技能:\\s*([^\\]]+)\\]\\s*(?:执行|来处理)?\\s*(.*)",
    "\\[调用\\s*Subagent:\\s*([^\\]]+)\\]\\s*(?:执行|来处理)?\\s*(.*)",
    "\\[调用组合:\\s*([^\\]]+)\\]\\s*(?:执行|来处理)?\\s*(.*)"
  ]
}
```

### 优先级更新

```
1. 显式调用声明（最高优先级）⭐ 新增
   └─> 直接使用指定技能/Agent，无需匹配

2. 用户显式指定
   └─> 如"使用 XXX agent"

3. 关键词匹配
   └─> 根据 triggers.keywords 自动匹配

4. 文件类型检测
   └─> 根据正在编辑的文件类型匹配
```

## 📋 路由规则

### 优先级顺序

1. **用户显式指定** > 2. **关键词匹配** > 3. **文件类型检测** > 4. **任务推断**

### 关键词路由

配置文件: `config/keyword_routes.json`

| 关键词 | 路由到 | 说明 |
|--------|--------|------|
| "新增功能"、"开发功能" | `feature-development` | Django+Vue 标准化开发流程 |
| "修复 Bug"、"修复错误" | `auto-fix` | 自动测试-修复-提交循环 |
| "部署项目"、"部署到服务器" | `db-deploy` | 全栈项目自动部署 |
| "审查代码"、"代码质量" | `code-reviewer` | 代码质量、安全审查 |

完整列表见 [keyword_routes.json](config/keyword_routes.json)

### 文件类型路由

配置文件: `config/file_type_routes.json`

| 文件扩展名 | 路由到 | 说明 |
|------------|--------|------|
| `.vue` | `frontend-developer` | Vue 组件 |
| `.py` | `python-expert` | Python 代码 |
| `.sql` | `sql-expert` 或 `database-optimizer` | SQL 查询/脚本 |

完整列表见 [file_type_routes.json](config/file_type_routes.json)

### Agent 注册表

配置文件: `config/agent_registry.json`

包含所有可用 Agent 的详细信息：
- Agent 名称和描述
- 适用场景
- 能力标签
- 类别归属

## 🔧 配置说明

### 修改路由规则

编辑 `config/keyword_routes.json` 或 `config/file_type_routes.json`:

```json
{
  "keywords": [
    {
      "patterns": ["你的关键词", "你的关键词2"],
      "agent": "目标-agent",
      "description": "路由说明",
      "priority": 1
    }
  ]
}
```

### 添加新 Agent

1. 在 `config/agent_registry.json` 中注册 Agent
2. 在路由配置中添加映射规则

### 优先级调整

`priority` 值越小，优先级越高（默认为 10）

## 📊 执行流程

```
用户输入
    ↓
检测触发条件（关键词/文件类型/任务类型）
    ↓
匹配路由规则（按优先级排序）
    ↓
验证目标 Agent 是否存在
    ↓
使用 Task tool 在独立上下文中启动 Agent
    ↓
等待 Agent 完成任务
    ↓
整合结果并简洁呈现
```

## 🎓 最佳实践

### 1. 灵活处理
如果任务简单（如单行修改），可直接在主窗口处理，无需路由。

### 2. 无需汇报
不要说"正在启动 XXX Agent"，直接执行即可。

### 3. 结果整合
Agent 完成后，整合关键信息，避免冗长输出。

### 4. 并行执行
对于独立任务，可同时启动多个 Agent 并行处理。

### 5. 容错机制
如果目标 Agent 不存在，回退到主窗口处理。

## 🔍 故障排查

### Agent 未启动
- 检查 Agent 名称是否在 `agent_registry.json` 中注册
- 检查路由规则配置是否正确
- 查看系统日志了解详细错误

### 路由不生效
- 检查关键词是否在配置文件中
- 检查文件扩展名是否在配置文件中
- 确认没有更高优先级的规则覆盖

### Agent 执行失败
- 检查 Agent 是否可用（使用 Task tool 验证）
- 查看具体错误信息
- 考虑使用备用 Agent

## 📚 相关文档

- [关键词路由配置](config/keyword_routes.json)
- [文件类型路由配置](config/file_type_routes.json)
- [Agent 注册表](config/agent_registry.json)
- [使用示例](examples/usage_examples.md)
- [路由引擎文档](lib/README.md)

## 🤝 贡献指南

### 添加新关键词
1. 编辑 `config/keyword_routes.json`
2. 添加关键词和路由规则
3. 测试路由是否生效

### 添加新文件类型
1. 编辑 `config/file_type_routes.json`
2. 添加文件扩展名和路由规则
3. 测试路由是否生效

### 优化路由逻辑
1. 修改 `lib/router.py` 或相关模块
2. 添加单元测试
3. 更新文档

## 📝 更新日志

### v1.0.0 (2026-01-07)
- ✅ 初始版本发布
- ✅ 支持 150+ 关键词路由
- ✅ 支持 80+ 文件类型路由
- ✅ 支持 117 个 Agent
- ✅ JSON 配置文件
- ✅ Python 路由引擎
- ✅ 完整文档和示例

## 📞 获取帮助

- 查看使用示例: [examples/usage_examples.md](examples/usage_examples.md)
- 查看配置文件: `config/*.json`
- 查看路由引擎: `lib/`
- 反馈问题: 在项目中提出 Issue

---

**维护者**: maintainers
**许可证**: MIT
**仓库**: 本地技能库
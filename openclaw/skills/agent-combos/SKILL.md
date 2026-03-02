---
name: agent-combos
displayName: "Agent 组合技能"
version: "1.0.0"
description: 预定义的专业 Subagent 组合，一键调用多个专家并行工作
description_zh: "agent-combos技能，详见 SKILL.md"
author: "superma"
license: "MIT"
updated_at: "2026-01-25"

triggers:
  keywords:
    - "全栈开发"
    - "完整功能"
    - "全面审查"
    - "PR 审查"
    - "性能分析"
    - "安全审计"
    - "量化策略"
    - "交易系统"
    - "多维度分析"
  auto_trigger: true
  confidence_threshold: 0.7

tools:
  required:
    - Task
  optional:
    - Read
    - Write
    - Bash

permissions:
  level: "full"
  scope:
    - "file:read"
    - "file:write"
    - "agent:dispatch"

context:
  mode: fork
  isolation: true
  max_context_tokens: 80000

hot_reload: true
progressive_load: true

metadata:
  category: "development"
  tags:
    - "subagent"
    - "并行执行"
    - "组合技能"
    - "智能路由"
---

# Agent 组合技能 (Agent Combos)

> 预定义的专业 Subagent 组合，一键调用多个专家并行工作，提升效率

## 📖 技能概述

本技能提供预定义的 Subagent 组合模板，针对常见开发场景，一键调用多个专业 Subagent 并行工作，充分利用智能路由系统的 117 个专业 Subagent。

## 🎯 核心价值

### 1. 一键调用
- 无需手动指定多个 Subagent
- 预定义组合，开箱即用
- 支持自定义组合

### 2. 并行执行
- 多个 Subagent 同时工作
- 节省约 58% 执行时间
- 结果自动整合

### 3. 上下文隔离
- 使用 Task tool 隔离执行
- 避免上下文污染
- 提高响应质量

## 🚀 可用组合

### 1. 全栈开发组合

**触发关键词**: "全栈开发"、"完整功能"、"端到端开发"

**调用 Subagent**:
```python
Task(subagent_type="backend-architect", prompt="设计后端架构和 API")
Task(subagent_type="frontend-developer", prompt="开发前端界面和交互")
Task(subagent_type="database-architect", prompt="设计数据库结构和表关系")
```

**适用场景**:
- 新功能完整开发
- 从零到一的产品开发
- 前后端联调

**并行优势**: 节省约 66% 时间（串行 30 分钟 → 并行 10 分钟）

---

### 2. 代码审查组合

**触发关键词**: "全面审查"、"PR 审查"、"代码质量审查"

**调用 Subagent**:
```python
Task(subagent_type="code-reviewer", prompt="审查代码质量、可维护性")
Task(subagent_type="security-auditor", prompt="检查安全漏洞、敏感信息")
Task(subagent_type="architect-review", prompt="审查架构一致性、设计模式")
Task(subagent_type="performance-engineer", prompt="分析性能影响、优化建议")
```

**适用场景**:
- Pull Request 提交前检查
- 代码质量评估
- 安全审计

**并行优势**: 节省约 75% 时间（串行 16 分钟 → 并行 4 分钟）

---

### 3. 性能分析组合

**触发关键词**: "性能分析"、"性能优化"、"性能瓶颈"

**调用 Subagent**:
```python
Task(subagent_type="performance-engineer", prompt="分析应用整体性能")
Task(subagent_type="database-optimizer", prompt="分析数据库查询性能")
Task(subagent_type="backend-architect", prompt="审查架构设计对性能的影响")
```

**适用场景**:
- 性能瓶颈分析
- 响应时间优化
- 数据库慢查询优化

---

### 4. 安全审计组合

**触发关键词**: "安全审计"、"安全检查"、"漏洞扫描"

**调用 Subagent**:
```python
Task(subagent_type="security-auditor", prompt="检查代码安全漏洞")
Task(subagent_type="api-security-audit", prompt="审计 API 接口安全性")
Task(subagent_type="code-reviewer", prompt="审查敏感信息泄露风险")
```

**适用场景**:
- 上线前安全检查
- OWASP Top 10 审计
- 敏感数据处理审查

---

### 5. 量化交易组合

**触发关键词**: "量化策略"、"交易系统"、"策略回测"

**调用 Subagent**:
```python
Task(subagent_type="quant-analyst", prompt="分析量化策略、回测结果")
Task(subagent_type="risk-manager", prompt="评估风险敞口、止损策略")
Task(subagent_type="data-engineer", prompt="处理交易数据、清洗数据")
```

**适用场景**:
- 量化策略开发
- 交易系统搭建
- 风险控制系统

---

### 6. 多维度分析组合

**触发关键词**: "多维度分析"、"全面分析"、"多角度评估"

**调用 Subagent**:
```python
Task(subagent_type="architect-review", prompt="架构维度分析")
Task(subagent_type="code-reviewer", prompt="代码质量分析")
Task(subagent_type="security-auditor", prompt="安全性分析")
Task(subagent_type="performance-engineer", prompt="性能分析")
Task(subagent_type="test-automator", prompt="测试覆盖分析")
```

**适用场景**:
- 项目整体评估
- 技术债务分析
- 重构前的全面评估

**并行优势**: 节省约 80% 时间（串行 25 分钟 → 并行 5 分钟）

---

### 7. 前端优化组合

**触发关键词**: "前端优化"、"React 优化"、"UI 优化"

**调用 Subagent**:
```python
Task(subagent_type="react-performance-optimization", prompt="优化 React 组件性能")
Task(subagent_type="frontend-developer", prompt="审查前端代码质量")
Task(subagent_type="ui-ux-designer", prompt="评估 UI/UX 体验")
```

**适用场景**:
- React 应用性能优化
- 前端代码重构
- 用户体验提升

---

### 8. 后端架构组合

**触发关键词**: "后端架构"、"API 设计"、"微服务架构"

**调用 Subagent**:
```python
Task(subagent_type="backend-architect", prompt="设计后端架构")
Task(subagent_type="database-architect", prompt="设计数据存储方案")
Task(subagent_type="api-documenter", prompt="编写 API 文档")
```

**适用场景**:
- 后端架构设计
- API 接口设计
- 微服务拆分

---

## 🔧 自定义组合

### 创建自己的组合

在技能内部调用多个 Task tool 即可：

```python
# 示例：自定义组合
Task(subagent_type="专家1", prompt="任务描述1")
Task(subagent_type="专家2", prompt="任务描述2")
Task(subagent_type="专家3", prompt="任务描述3")
```

### 可用的 Subagent

完整列表见：
- `~/.claude/skills/intelligent-router/config/agent_registry.json`
- 117 个专业 Subagent 可选

## 📊 执行流程

```
用户触发关键词
    ↓
识别组合类型
    ↓
并行启动多个 Subagent (Task tool)
    ↓
等待所有 Subagent 完成
    ↓
整合结果并呈现
```

## ⚡ 性能优势

| 场景 | 串行耗时 | 并行耗时 | 节省时间 |
|------|---------|---------|---------|
| 全栈开发 | 30分钟 | 10分钟 | 66% |
| 代码审查 | 16分钟 | 4分钟 | 75% |
| 多维度分析 | 25分钟 | 5分钟 | 80% |

## 🎓 最佳实践

### 1. 灵活使用
- 简单任务直接在主窗口处理
- 复杂任务使用组合技能

### 2. 结果整合
- 整合各 Subagent 的输出
- 去除重复信息
- 突出关键发现

### 3. 容错处理
- 如果某个 Subagent 失败，不影响其他
- 可手动重试失败的 Subagent

### 4. 上下文管理
- 为每个 Subagent 提供必要的上下文
- 避免信息过载

## 🚫 禁止事项

- ❌ 不要说"正在启动 XXX Subagent"，直接执行即可
- ❌ 不要重复启动相同的 Subagent
- ❌ 不要在组合中使用不存在的 Subagent

## 📚 相关文档

- [智能路由系统](~/.claude/skills/intelligent-router/SKILL.md)
- [Subagent 注册表](~/.claude/skills/intelligent-router/config/agent_registry.json)
- [关键词路由](~/.claude/skills/intelligent-router/config/keyword_routes.json)

## 📝 更新日志

### v1.0.0 (2026-01-25)
- ✅ 初始版本发布
- ✅ 8 个预定义组合
- ✅ 支持 117 个 Subagent
- ✅ 完整文档

---

**维护者**: superma
**许可证**: MIT
**依赖**: intelligent-router v1.0.0
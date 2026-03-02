# 智能路由插件使用示例

> **版本**: 1.0.0
> **更新时间**: 2026-01-07

## 目录

1. [基础使用](#基础使用)
2. [关键词路由示例](#关键词路由示例)
3. [文件类型路由示例](#文件类型路由示例)
4. [显式指定 Agent](#显式指定-agent)
5. [并行执行示例](#并行执行示例)
6. [批量路由示例](#批量路由示例)
7. [高级配置](#高级配置)
8. [故障排查](#故障排查)

---

## 基础使用

### 自动激活（推荐）

智能路由插件会自动检测以下情况并激活：

1. **关键词触发**
   ```markdown
   用户: "帮我审查这段代码"
   系统: 自动路由到 code-reviewer Agent
   ```

2. **文件类型触发**
   ```markdown
   上下文: 正在编辑 .vue 文件
   用户: "优化这个组件"
   系统: 自动路由到 frontend-developer Agent
   ```

3. **显式指定**
   ```markdown
   用户: "使用 python-expert 优化代码"
   系统: 路由到 python-expert Agent
   ```

---

## 关键词路由示例

### 示例 1: 开发功能

**用户输入**:
```
我需要添加一个用户管理功能
```

**路由结果**:
- **Agent**: `feature-development`
- **原因**: 关键词 "添加"、"功能" 匹配
- **描述**: Django+Vue 标准化开发流程

**执行流程**:
1. 检测到关键词 "添加" 和 "功能"
2. 查找配置，匹配到 `feature-development` 技能
3. 在独立上下文中启动该 Agent
4. Agent 完成需求分析、技术方案设计
5. 整合结果到主窗口

### 示例 2: 修复 Bug

**用户输入**:
```
测试失败了，帮我修复一下
```

**路由结果**:
- **Agent**: `auto-fix`
- **原因**: 关键词 "修复" 匹配
- **描述**: 自动测试-修复-提交循环

**执行流程**:
1. 检测到关键词 "修复"
2. 查找配置，匹配到 `auto-fix` 技能
3. 启动自动修复循环
4. 运行测试 → 分析问题 → 修复代码 → 提交
5. 循环直到所有测试通过

### 示例 3: 部署项目

**用户输入**:
```
帮我把项目部署到生产服务器
```

**路由结果**:
- **Agent**: `db-deploy`
- **原因**: 关键词 "部署"、"生产服务器" 匹配
- **描述**: 全栈项目自动部署

**执行流程**:
1. 检测到关键词 "部署" 和 "生产服务器"
2. 查找配置，匹配到 `db-deploy` 技能
3. 启动部署流程
4. 配置 GitHub Actions、Nginx、SSL 证书

### 示例 4: 代码审查

**用户输入**:
```
审查一下这段代码的质量
```

**路由结果**:
- **Agent**: `code-reviewer`
- **原因**: 关键词 "审查"、"代码质量" 匹配
- **描述**: 代码质量、安全审查

**执行流程**:
1. 检测到关键词 "审查" 和 "代码质量"
2. 查找配置，匹配到 `code-reviewer` Agent
3. 启动代码审查
4. 分析代码质量、安全性、可维护性

---

## 文件类型路由示例

### 示例 1: Python 文件

**上下文**: 正在编辑 `app.py`

**用户输入**:
```
优化这个函数
```

**路由结果**:
- **Agent**: `python-expert`
- **原因**: 文件扩展名 `.py` 匹配
- **描述**: Python 高级特性

### 示例 2: Vue 组件

**上下文**: 正在编辑 `UserList.vue`

**用户输入**:
```
优化这个组件的性能
```

**路由结果**:
- **Agent**: `frontend-developer`
- **原因**: 文件扩展名 `.vue` 匹配
- **描述**: Vue 组件

### 示例 3: SQL 文件

**上下文**: 正在编辑 `query.sql`

**用户输入**:
```
优化这个查询
```

**路由结果**:
- **Agent**: `sql-expert` 或 `database-optimizer`
- **原因**: 文件扩展名 `.sql` 匹配
- **描述**: SQL 查询/脚本

---

## 显式指定 Agent

### 示例 1: 覆盖关键词匹配

**用户输入**:
```
使用 python-expert 优化这段 JavaScript 代码
```

**路由结果**:
- **Agent**: `python-expert`
- **原因**: 用户显式指定（优先级最高）
- **描述**: Python 高级特性

**说明**: 即使文件类型是 `.js`，也会使用 `python-expert`

### 示例 2: 多 Agent 协作

**用户输入**:
```
使用 python-expert 和 code-reviewer 帮我优化并审查代码
```

**执行流程**:
1. 启动 `python-expert` 优化代码
2. 启动 `code-reviewer` 审查优化后的代码
3. 整合两个 Agent 的结果

---

## 并行执行示例

### 示例 1: 多维度分析

**场景**: 分析一个后端项目

**用户输入**:
```
分析这个后端项目的架构、性能、安全性、代码质量
```

**并行执行**:
```
1. architect-review - 架构分析
2. performance-engineer - 性能分析
3. security-auditor - 安全分析
4. code-reviewer - 代码质量分析
```

**时间节省**:
- 串行: 4 × 2分钟 = 8分钟
- 并行: max(2分钟) = 2分钟
- **节省 75% 时间**

### 示例 2: 全方位代码审查

**场景**: 提交 PR 前的全面检查

**并行执行**:
```
1. code-reviewer - 代码质量
2. security-auditor - 安全检查
3. architect-review - 架构一致性
4. performance-engineer - 性能影响
5. test-automator - 测试覆盖
```

### 示例 3: 跨平台移动应用

**场景**: 开发跨平台应用

**并行执行**:
```
1. ios-developer - iOS 原生实现
2. mobile-developer - React Native 实现
3. ui-ux-designer - UI/UX 设计
```

---

## 批量路由示例

### Python 代码示例

```python
from lib import IntelligentRouter

# 创建路由器
router = IntelligentRouter()

# 批量路由
tasks = [
    {"user_input": "新增功能"},
    {"user_input": "修复 bug"},
    {"user_input": "部署项目", "file_context": "app.py"},
    {"user_input": "审查代码"},
    {"user_input": "优化性能"},
]

results = router.route_batch(tasks)

# 输出结果
for i, result in enumerate(results):
    if result:
        print(f"任务 {i+1}: {result['agent']} - {result['reason']}")
    else:
        print(f"任务 {i+1}: 主窗口处理")
```

**输出**:
```
任务 1: feature-development - Django+Vue 标准化开发流程
任务 2: auto-fix - 自动测试-修复-提交循环
任务 3: db-deploy - 全栈项目自动部署
任务 4: code-reviewer - 代码质量、安全审查
任务 5: performance-engineer - 应用性能分析和优化
```

---

## 高级配置

### 添加自定义关键词

**编辑**: `config/keyword_routes.json`

```json
{
  "category": "自定义",
  "patterns": ["你的关键词", "关键词2"],
  "agent": "目标-agent",
  "description": "路由说明",
  "priority": 1
}
```

### 添加自定义文件类型

**编辑**: `config/file_type_routes.json`

```json
{
  "category": "自定义",
  "extensions": [".custom", ".xyz"],
  "agent": "目标-agent",
  "description": "自定义文件类型",
  "priority": 1
}
```

### 注册新 Agent

**编辑**: `config/agent_registry.json`

```json
{
  "name": "your-custom-agent",
  "description": "你的自定义 Agent",
  "category": "自定义",
  "capabilities": [
    "能力1",
    "能力2"
  ],
  "priority": 1,
  "available": true
}
```

### 运行时添加规则

```python
from lib import KeywordMatcher

matcher = KeywordMatcher("config/keyword_routes.json")
matcher.load_config()

# 运行时添加关键词
matcher.add_keyword(
    patterns=["新关键词", "新关键词2"],
    agent="target-agent",
    description="新路由规则",
    priority=1,
    category="自定义"
)
```

---

## 故障排查

### 问题 1: Agent 未启动

**症状**: 输入包含关键词，但没有启动 Agent

**排查步骤**:
1. 检查 Agent 名称是否在注册表中
2. 检查 Agent `available` 字段是否为 `true`
3. 查看系统日志了解详细错误

**解决方案**:
```python
from lib import IntelligentRouter

router = IntelligentRouter()

# 验证 Agent 是否可用
info = router.get_agent_info("your-agent")
if info:
    print(f"Agent 可用: {info}")
else:
    print("Agent 不可用或不存在")
```

### 问题 2: 路由不生效

**症状**: 关键词或文件类型没有匹配到 Agent

**排查步骤**:
1. 检查关键词是否在配置文件中
2. 检查文件扩展名是否在配置文件中
3. 确认没有更高优先级的规则覆盖

**解决方案**:
```python
from lib import KeywordMatcher, FileTypeMatcher

# 检查关键词配置
keyword_matcher = KeywordMatcher("config/keyword_routes.json")
keyword_matcher.load_config()
result = keyword_matcher.match("你的关键词")
print(f"关键词匹配结果: {result}")

# 检查文件类型配置
file_matcher = FileTypeMatcher("config/file_type_routes.json")
file_matcher.load_config()
result = file_matcher.match(".你的扩展名")
print(f"文件类型匹配结果: {result}")
```

### 问题 3: Agent 执行失败

**症状**: Agent 启动但执行失败

**排查步骤**:
1. 验证 Agent 是否真的可用（使用 Task tool 测试）
2. 查看具体错误信息
3. 考虑使用备用 Agent

**解决方案**:
```markdown
# 手动测试 Agent
请使用 Task tool 启动 your-agent，执行以下任务：
[你的任务]

# 如果失败，尝试备用 Agent
请使用 Task tool 启动 backup-agent，执行以下任务：
[你的任务]
```

---

## 最佳实践

### 1. 灵活处理

如果任务简单（如单行修改），可直接在主窗口处理，无需路由。

**示例**:
```markdown
用户: "把 print 改成 logging"
系统: 直接修改，不路由（简单任务）
```

### 2. 无需汇报

不要说"正在启动 XXX Agent"，直接执行即可。

**❌ 不推荐**:
```
检测到关键词"审查代码"，正在启动 code-reviewer Agent...
```

**✅ 推荐**:
```
[直接展示 code-reviewer Agent 的分析结果]
```

### 3. 结果整合

Agent 完成后，整合关键信息，避免冗长输出。

**示例**:
```
## 代码审查结果

### 主要问题
1. 缺少输入验证
2. 未处理异常情况

### 建议改进
1. 添加参数验证
2. 添加 try-except 块
```

### 4. 并行执行

对于独立任务，可同时启动多个 Agent 并行处理。

**示例**:
```markdown
# 并行启动架构、性能、安全分析
[同时启动 3 个 Agent]

# 等待所有完成后整合结果
[整合 3 个 Agent 的分析结果]
```

---

## 更多示例

查看完整示例:
- [关键词路由配置](../config/keyword_routes.json)
- [文件类型路由配置](../config/file_type_routes.json)
- [Agent 注册表](../config/agent_registry.json)
- [路由引擎源码](../lib/)

---

**维护者**: superma
**许可证**: MIT

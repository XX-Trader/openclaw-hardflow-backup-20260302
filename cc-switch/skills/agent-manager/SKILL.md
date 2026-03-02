---
name: agent-manager
description: Claude Code Agents 索引和管理技能。快速查找、调用和管理 117+ 个专业 AI 代理，支持分类浏览、关键词搜索和智能匹配。
category: development
tags: [agents, management, indexing]
version: 1.0.0
---

# Agent Manager - AI 代理管理技能

## 技能特性

- ✅ **完整索引**: 117 个专业 AI 代理，11 个类别
- ✅ **分类浏览**: 按领域组织（开发、安全、数据、基础设施等）
- ✅ **智能匹配**: 根据任务描述自动推荐合适的代理
- ✅ **快速查找**: 支持按名称和关键词搜索
- ✅ **调用指南**: 详细的代理调用方式和最佳实践
- ✅ **自动更新**: 一键重新生成索引，同步最新代理

---

## 快速开始

### 方式一：自动匹配（推荐）

直接描述你的需求，我会自动匹配合适的代理：

```
你: "帮我审查这段代码的质量"
我: [自动调用 code-reviewer 代理]

你: "优化这个 Python 函数的性能"
我: [自动调用 python-expert 代理]

你: "调试这个部署错误"
我: [自动调用 devops-troubleshooter 代理]
```

### 方式二：手动指定

明确指定使用某个代理：

```
"请使用 python-expert 代理帮我重构代码"
"使用 debugger 代理分析这个错误"
```

### 方式三：查看索引

运行脚本查看完整的代理列表：

**Windows**:
```bash
cd %USERPROFILE%\.claude\skills\agent-manager\scripts
python extract-agents.py
```

**Linux/Mac**:
```bash
cd $HOME/.claude/skills/agent-manager/scripts
python extract-agents.py
```

生成的索引文件位于：
- `data/AGENTS_INDEX.md` - Markdown 格式索引
- `data/agents.json` - JSON 格式数据

---

## 代理分类

| 类别 | 代理数量 | 典型用途 |
|------|----------|----------|
| **Language Specialists** | 12 | Python, TypeScript, Go, Rust 等语言专家 |
| **Development Architecture** | 12 | 前端、后端、移动端开发架构 |
| **Infrastructure Operations** | 8 | 云架构、数据库、运维、网络 |
| **Data & AI** | 11 | 数据工程、机器学习、AI 系统 |
| **Quality & Security** | 10 | 代码审查、安全审计、调试 |
| **Blockchain & Web3** | 2 | 智能合约、企业区块链 |
| **Crypto Trading** | 5 | 加密货币交易、DeFi 策略 |
| **Business & Finance** | 4 | 业务分析、量化交易、支付集成 |
| **Design & Experience** | 2 | UI/UX 设计、无障碍访问 |
| **Research** | 多个 | 学术研究、技术调研 |
| **Documentation** | 多个 | API 文档、技术文档 |

---

## 常用代理速查

### 开发相关

| 任务 | 推荐代理 |
|------|----------|
| Python 代码优化 | `python-expert` |
| 前端组件开发 | `frontend-developer` |
| API 接口设计 | `backend-architect` |
| 数据库优化 | `database-optimizer` |
| 代码审查 | `code-reviewer` |

### 调试相关

| 任务 | 推荐代理 |
|------|----------|
| 错误调试 | `debugger` |
| 生产故障 | `incident-responder` |
| 性能分析 | `react-performance-optimization` |
| 日志分析 | `error-detective` |

### DevOps 相关

| 任务 | 推荐代理 |
|------|----------|
| 部署配置 | `deployment-engineer` |
| 基础设施设计 | `cloud-architect` |
| 网络问题 | `network-engineer` |

---

## 技能文件结构

```
agent-manager/
├── SKILL.md                      # 本文件
├── data/                         # 生成的索引数据
│   ├── AGENTS_INDEX.md           # Agent 索引（Markdown）
│   └── agents.json               # Agent 数据（JSON）
├── scripts/                      # 工具脚本
│   └── extract-agents.py         # 索引生成脚本
└── workflows/                    # 工作流程（可选）
    ├── auto-match.md             # 自动匹配流程
    └── manual-call.md            # 手动调用流程
```

---

## 更新索引

当 `agents/` 目录有更新时，重新生成索引：

**Windows**:
```bash
cd %USERPROFILE%\.claude\skills\agent-manager\scripts
python extract-agents.py
```

**Linux/Mac**:
```bash
cd $HOME/.claude/skills/agent-manager/scripts
python extract-agents.py
```

输出示例：
```
[OK] Index generation complete!
[MD] Markdown: ~/.claude/skills/agent-manager/data/AGENTS_INDEX.md
[JSON] Data: ~/.claude/skills/agent-manager/data/agents.json
[STAT] Total 117 agents, 11 categories
```

---

## 调用示例

### 示例 1：代码审查

```
你: "我刚写完一个用户认证模块，帮我审查一下"

我自动识别为代码审查任务，调用 code-reviewer 代理：
1. 检查代码安全性
2. 验证错误处理
3. 评估性能影响
4. 提供改进建议
```

### 示例 2：性能优化

```
你: "这个 API 接口响应太慢了，帮我优化"

我自动调用：
- python-expert（如果是 Python）
- database-optimizer（如果涉及数据库）
- backend-architect（架构层面建议）
```

### 示例 3：跨领域协作

```
你: "实现一个加密货币交易策略"

我自动调用多个代理协作：
1. quant-analyst - 策略设计
2. python-expert - 代码实现
3. code-reviewer - 代码审查
4. debugger - 测试调试
```

---

## 最佳实践

1. **描述清楚任务**: 包含技术栈、具体问题、期望结果
2. **提供上下文**: 附上相关代码片段、错误信息、需求文档
3. **明确优先级**: 说明是快速修复还是深度优化
4. **逐步反馈**: 对代理的建议及时反馈，便于迭代改进

---

## 与其他技能的集成

本技能可以与以下技能配合使用：

- `feature-development` - 功能开发时自动调用相关代理
- `db-deploy` - 部署时调用 DevOps 相关代理
- `deployment-test` - 测试时调用调试代理

---

## 技术原理

### 自动匹配机制

```
用户输入
  ↓
关键词提取（技术栈、任务类型、领域）
  ↓
查询 agents.json
  ↓
计算匹配度
  ↓
返回 Top 3 推荐代理
  ↓
用户确认 / 自动调用
```

### 代理元数据

每个代理包含以下元数据：

```yaml
---
name: agent-name
description: 功能描述
category: 类别
---
```

---

**文档版本**: v1.0.0
**最后更新**: 2026-01-05
**维护者**: superma
**License**: MIT

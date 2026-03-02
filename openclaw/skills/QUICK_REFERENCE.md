# 技能与 Agent 快速参考卡

> **快速查找，高效调用**
> 更新时间: 2026-01-05
> **斜杠命令**: 6 个快捷命令（详见下方）

---

## 🎯 斜杠命令（Slash Commands）

**快速调用**: 输入 `/命令名` 即可使用

### 高频斜杠命令

```bash
/commit                           # 创建 Git 提交（最常用）
/深度思考 <问题>                  # 复杂问题深度分析
/循环 <任务>                      # 自动循环执行
/自动循环 <任务> 次数 <N> 完成 <条件>  # 一行搞定
```

### 完整命令列表

| 命令 | 功能 | 典型用法 |
|------|------|---------|
| `/commit` | Git 提交 | 创建规范的 Conventional Commits |
| `/深度思考` | 深度思考 | 架构设计、技术选型、产品方向 |
| `/深度分析` | 多角度分析 | 问题本质探索、反例验证 |
| `/循环` | 自动循环 | 交互式，适合新手 |
| `/自动循环` | 一行循环 | 非交互式，快速执行 |
| `/反复` | 反复执行 | 口语化版本 |

**完整索引**: [COMMANDS_INDEX](../commands/INDEX.md)

---

## 🚀 高频技能 TOP 6

| 技能 | 使用场景 | 快速调用 |
|------|---------|---------|
| **feature-development** | 新增功能模块 | "使用 feature-development 开发..." |
| **auto-fix** | 自动修复 Bug | "使用 auto-fix 修复..." |
| **db-deploy** | 部署到服务器 | "使用 db-deploy 部署..." |
| **project-sync** | 同步 Project 目录 | "使用 project-sync 同步..." |
| **code-reviewer** | 代码审查 | "审查这段代码" |
| **debugger** | 调试错误 | "调试这个问题" |

---

## 🎯 按场景快速查找

### 开发相关

```
新增功能     → feature-development
修复 Bug     → auto-fix
代码审查     → code-reviewer
调试问题     → debugger
性能优化     → performance-engineer
重构代码     → legacy-modernizer
编写测试     → test-automator
```

### 部署相关

```
生产部署     → db-deploy
本地环境     → windows-fullstack-deploy
部署测试     → deployment-test
CI/CD       → deployment-engineer
容器化      → deployment-engineer
项目同步     → project-sync
```

**GitHub Actions 部署规则**（使用自托管 Runner）:

| Commit Message 包含 | 部署内容 | 示例 |
|-------------------|---------|------|
| `deploy-all` | 前端 + 后端 | `feat: 新功能 deploy-all` |
| `deploy-frontend` | 仅前端 | `fix: UI 修复 deploy-frontend` |
| `deploy-backend` | 仅后端 | `fix: API 修复 deploy-backend` |
| `[skip-frontend]` | 跳过前端 | `chore: 配置更新 [skip-frontend]` |
| `[skip-backend]` | 跳过后端 | `docs: 文档更新 [skip-backend]` |
| 无标记 | 不部署 | `feat: 其他更改` |

**最佳实践**:
```bash
# 开发时频繁提交 - 不触发部署
git commit -m "feat: 添加用户界面"
git push origin main

# 完成功能后 - 触发部署
git commit -m "feat: 用户模块完成 deploy-all"
git push origin main
```


### 架构设计

```
架构设计     → deepdive + backend-architect
数据库设计   → database-architect
技术调研     → research-orchestrator
需求分析     → requirements-clarity
```

### 数据库

```
查询优化     → database-optimizer
性能调优     → database-optimization
数据库管理   → database-admin
```

### 语言专家

```
Python      → python-expert
JavaScript  → javascript-developer
TypeScript  → typescript-expert
Go          → golang-expert
Java        → java-developer
C++         → cpp-engineer
Rust        → rust-expert
```

### AI/ML

```
LLM 应用    → ai-engineer
数据处理    → data-engineer
ML 管道     → ml-engineer
MLOps       → mlops-engineer
Prompt 优化 → prompt-engineer
```

### 安全与质量

```
代码审查     → code-reviewer
安全审计     → security-auditor
API 安全     → api-security-audit
性能分析     → performance-engineer
```

---

## 📊 Agent 类别速查

| 类别 | 数量 | 代表 Agent |
|------|------|-----------|
| **开发架构** | 11 | frontend-developer, backend-architect |
| **语言专家** | 11 | python-expert, typescript-expert |
| **质量安全** | 14 | code-reviewer, debugger, security-auditor |
| **基础设施** | 8 | cloud-architect, deployment-engineer |
| **数据 AI** | 11 | ai-engineer, data-engineer |
| **专门领域** | 43 | research-orchestrator, legacy-modernizer |
| **商业金融** | 4 | business-analyst, quant-analyst |
| **加密交易** | 5 | crypto-trader, defi-strategist |
| **营销销售** | 6 | content-marketer, sales-automator |
| **区块链** | 2 | blockchain-developer |
| **设计体验** | 2 | ui-ux-designer |

---

## 💬 调用方式

### 自动匹配（推荐）

直接描述需求，系统自动匹配：

```
"帮我审查这段代码"          → code-reviewer
"部署项目到服务器"          → db-deploy
"新增一个用户管理功能"      → feature-development
"优化这个 Python 函数"      → python-expert
"调试这个错误"              → debugger
```

### 明确指定

明确指定技能或 agent：

```
"使用 python-expert 代理优化代码"
"调用 db-deploy 技能部署项目"
"请 feature-development 技能帮我开发..."
```

### 组合调用

多个技能/agent 协同：

```
"使用 python-expert 和 code-reviewer 帮我优化并审查代码"
"先 deepdive 思考，再用 backend-architect 设计架构"
```

---

## 🔍 搜索技巧

### 按关键词搜索

```
"显示所有 Python 相关的 agents"
"有哪些调试类的代理？"
"帮我找一个适合做代码审查的 agent"
"列出所有部署相关的技能"
```

### 按类别浏览

```
"显示所有 Development & Architecture 类别的 agents"
"有哪些 Language Specialists？"
"查看 Quality & Security 相关的代理"
```

### 按场景查找

```
"我需要做性能优化，应该用哪个 agent？"
"如何设计 REST API？"
"谁能帮我做数据分析？"
```

---

## 📖 完整文档链接

- **统一索引**: [SKILLS_AND_AGENTS_INDEX.md](../../SKILLS_AND_AGENTS_INDEX.md)
- **技能索引**: [../MASTER_INDEX.md](../MASTER_INDEX.md)
- **Agent 索引**: [agent-manager/data/AGENTS_INDEX.md](agent-manager/data/AGENTS_INDEX.md)
- **项目文档**: [CLAUDE.md](../../../CLAUDE.md)

---

## 🎓 使用建议

1. **优先自动匹配**: 让系统选择最合适的技能/agent
2. **查看完整索引**: 需要详细了解时查看统一索引
3. **组合使用**: 多个技能/agent 可以协同工作
4. **反馈优化**: 使用后反馈效果，优化匹配

---

**维护**: 本文件随技能和 agent 更新同步更新

**快速反馈**:
- 找不到合适的 agent？ → "帮我找一个能 [具体需求] 的 agent"
- 不确定用哪个技能？ → "我有 [需求]，应该用什么技能？"
- 想了解某个技能？ → "查看 [技能名] 的详细文档"

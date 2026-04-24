# OpenClaw Skills 技能总索引

> 单入口 · 分域分类 · 2026-04-02
> 所有 Skill 统一位于 `skills/library/<skill-name>/SKILL.md`

---

## 🎯 OpenClaw 核心运维

| Skill | 说明 | 脚本 |
|-------|------|------|
| [openclaw-hardflow-automation](openclaw-hardflow-automation/SKILL.md) | HardFlow G0-G6 门禁工作流 | ✅ 7 个脚本 |
| [control-plane-ops](library/control-plane-ops/SKILL.md) | 控制面巡检、Agent 审查、Cron 诊断 | — |
| [log-monitor](library/log-monitor/SKILL.md) | 异常日志扫描、分类、增量去重 | — |
| [config-watchdog](library/config-watchdog/SKILL.md) | 配置快照、变更检测、JSON 校验、回滚 | — |
| [memtidy](library/memtidy/SKILL.md) | 记忆三层管理、备份修剪 | — |
| [todo-patrol](library/todo-patrol/SKILL.md) | TODO 巡检、过期检测、归档 | — |
| [task-cost-analytics](library/task-cost-analytics/SKILL.md) | Token 统计、成本分析 | — |

## 🔄 同步与分发

| Skill | 说明 |
|-------|------|
| [git-sync](library/git-sync/SKILL.md) | 本地备份、远程同步、代码追踪 |
| [fleet-sync](library/fleet-sync/SKILL.md) | 多服务器配置分发、状态对比 |

## 🧠 进化与升级

| Skill | 说明 |
|-------|------|
| [openclaw-evolution-upgrader](library/openclaw-evolution-upgrader/SKILL.md) | 内部反馈升级、外部模式吸收、架构推进 |
| [openclaw-workflow-manager](library/openclaw-workflow-manager/SKILL.md) | 工作流地图、漂移巡检、安装管理 |
| [web-intelligence](library/web-intelligence/SKILL.md) | GitHub 扫描、网页情报采集、外部评估 |

## 🔒 安全与审核

| Skill | 说明 |
|-------|------|
| [openclaw-security-audit](library/openclaw-security-audit/SKILL.md) | 部署安全审计、漏洞扫描、修复建议 |
| [openclaw-hardflow-automation](openclaw-hardflow-automation/SKILL.md) | G4 安全审查门禁 |

## 💻 开发工具

| Skill | 说明 |
|-------|------|
| [auto-fix](library/auto-fix/SKILL.md) | 自动测试-修复循环 |
| [feature-development](library/feature-development/SKILL.md) | 全栈功能开发标准化 |
| [frontend-design](library/frontend-design/SKILL.md) | 前端界面设计 |
| [requesting-code-review](library/requesting-code-review/SKILL.md) | 发起代码审查 |
| [receiving-code-review](library/receiving-code-review/SKILL.md) | 接收代码审查 |
| [systematic-debugging](library/systematic-debugging/SKILL.md) | 系统化调试 |
| [verification-before-completion](library/verification-before-completion/SKILL.md) | 完成前验证 |
| [using-git-worktrees](library/using-git-worktrees/SKILL.md) | Git Worktree 使用 |

## 🚀 部署与测试

| Skill | 说明 |
|-------|------|
| [db-deploy](library/db-deploy/SKILL.md) | 全栈自动部署 |
| [deployment-test](library/deployment-test/SKILL.md) | 部署后自动化测试 |
| [windows-fullstack-deploy](library/windows-fullstack-deploy/SKILL.md) | Windows 本地环境部署 |
| [github-actions-runner](library/github-actions-runner/SKILL.md) | GitHub Actions Runner |
| [webapp-testing](library/webapp-testing/SKILL.md) | Web 应用交互测试 |
| [playwright-interactive](library/playwright-interactive/SKILL.md) | Playwright 浏览器测试 |

## 📄 文档与办公

| Skill | 说明 |
|-------|------|
| [docx](library/docx/SKILL.md) | Word 文档处理 |
| [pdf](library/pdf/SKILL.md) | PDF 操作 |
| [pptx](library/pptx/SKILL.md) | PPT 演示文稿 |
| [xlsx](library/xlsx/SKILL.md) | Excel 电子表格 |
| [changelog-generator](library/changelog-generator/SKILL.md) | 变更日志生成 |

## 🧩 编排与规划

| Skill | 说明 |
|-------|------|
| [smart-workflow](library/smart-workflow/SKILL.md) | 智能工作流 |
| [project-delivery-pipeline](library/project-delivery-pipeline/SKILL.md) | 端到端编码交付流水线状态机 |
| [task-decomposer](library/task-decomposer/SKILL.md) | 任务分解 |
| [writing-plans](library/writing-plans/SKILL.md) | 编写计划 |
| [product-requirements](library/product-requirements/SKILL.md) | 产品需求文档 |
| [requirements-clarity](library/requirements-clarity/SKILL.md) | 需求澄清 |
| [parallel-executor](library/parallel-executor/SKILL.md) | 并行执行 |
| [dispatching-parallel-agents](library/dispatching-parallel-agents/SKILL.md) | 派发并行 Agent |
| [result-synthesizer](library/result-synthesizer/SKILL.md) | 结果综合 |

## 🎨 其他

| Skill | 说明 |
|-------|------|
| [pua-methodology](pua-methodology/SKILL.md) | PUA 方法论 |
| [frontend-design-ultimate](frontend-design-ultimate/SKILL.md) | 极致前端设计 |
| [mcp-builder](library/mcp-builder/SKILL.md) | MCP Server 构建 |
| [pretext-text-layout](library/pretext-text-layout/SKILL.md) | 纯 JS 文本布局引擎 |
| [intelligent-router](library/intelligent-router/SKILL.md) | 智能路由 |
| [internal-comms](library/internal-comms/SKILL.md) | 内部通信 |

---

## Agent → Skill 绑定速查

| Agent | 绑定的 Skill |
|-------|-------------|
| **main** | agent-manager, requirements-clarity, smart-workflow, result-synthesizer, intelligent-router, task-decomposer, codex |
| **coordinator** | task-decomposer, smart-workflow, dispatching-parallel-agents, parallel-executor, agent-manager, requirements-clarity |
| **backend-dev** | feature-development, systematic-debugging, auto-fix, verification-before-completion, mcp-builder, using-git-worktrees |
| **frontend-dev** | frontend-design, feature-development, ui-ux-pro-max, verification-before-completion, auto-fix, playwright-interactive, webapp-testing, using-git-worktrees |
| **reviewer** | requesting-code-review, receiving-code-review, systematic-debugging, verification-before-completion, openclaw-security-audit |
| **tester** | playwright-interactive, webapp-testing, auto-fix, deployment-test, systematic-debugging |
| **deployer** | db-deploy, deployment-test, github-actions-runner, windows-fullstack-deploy, openclaw-security-audit |
| **doc-writer** | writing-plans, docx, changelog-generator, internal-comms, product-requirements, baoyu-format-markdown, pdf, pptx, xlsx |
| **ops-agent** | control-plane-ops, log-monitor, config-watchdog, memtidy, fleet-sync, todo-patrol, task-cost-analytics |
| **optimization-agent** | openclaw-evolution-upgrader, openclaw-workflow-manager, task-cost-analytics, workflow-audit |
| **project-agent** | product-requirements, requirements-clarity, writing-plans |
| **agent-factory** | agent-manager, openclaw-workflow-manager |
| **web-agent** | web-intelligence, pretext-text-layout, playwright-interactive |
| **explorer** | web-intelligence, smart-workflow |

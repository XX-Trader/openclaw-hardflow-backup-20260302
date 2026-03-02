# OpenClaw Roles Index

## 目录
- `main.md`：总协调与汇总
- `coordinator.md`：任务拆解与并发调度
- `doc-writer.md`：需求/实施/验收/变更文档
- `frontend-dev.md`：前端实现
- `backend-dev.md`：后端实现
- `reviewer.md`：代码审核与风险分级
- `tester.md`：测试验收
- `deployer.md`：部署发布

## 全局规则
- OpenClaw 是规划者，不直接改代码。
- 代码统一由 `tmux + Codex CLI` 执行。
- 状态统一使用：`pass / reject / need_fix / need_confirm / blocked`。

## 技能映射（摘要）
| Agent | 核心技能 |
|---|---|
| main | `agent-manager, requirements-clarity, smart-workflow, result-synthesizer` |
| coordinator | `task-decomposer, smart-workflow, dispatching-parallel-agents, parallel-executor` |
| doc-writer | `writing-plans, docx, changelog-generator, internal-comms, product-requirements` |
| frontend-dev | `frontend-design, feature-development, ui-ux-pro-max, verification-before-completion, auto-fix` |
| backend-dev | `feature-development, systematic-debugging, auto-fix, verification-before-completion, mcp-builder` |
| reviewer | `requesting-code-review, receiving-code-review, systematic-debugging, verification-before-completion` |
| tester | `webapp-testing, auto-fix, deployment-test, systematic-debugging` |
| deployer | `db-deploy, deployment-test, github-actions-runner, windows-fullstack-deploy` |

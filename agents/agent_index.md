# Agent Index

> 当前文件描述 nofx workflow 的逻辑 owner / cron 责任标签，不代表服务器上有同名常驻 agent 进程。
> 真实入口是 `arbitrageagent` / `spreadagent` 两个 Hermes Discord profile，模型均为 `openai-codex/gpt-5.5`。

## workflow stage owners

| Agent/Label | runtimeRole | model | 说明 |
|-------------|-------------|-------|------|
| coordinator | workflow-stage-owner | openai-codex/gpt-5.5 | 工作流协调与 Git 发布门禁 |
| project-agent | workflow-stage-owner | openai-codex/gpt-5.5 | 项目记忆、需求包、方案包 |
| web-agent | workflow-stage-owner | openai-codex/gpt-5.5 | 外部资料与官方来源核对 |
| reviewer | workflow-stage-owner | openai-codex/gpt-5.5 | 需求、方案、代码审查 |
| backend-dev | workflow-stage-owner | openai-codex/gpt-5.5 | 后端、脚本、服务和策略代码执行 |
| frontend-dev | workflow-stage-owner | openai-codex/gpt-5.5 | 前端、页面、UI 和交互代码执行 |
| tester | workflow-stage-owner | openai-codex/gpt-5.5 | 测试、验证、验收 |
| deployer | workflow-stage-owner | openai-codex/gpt-5.5 | 内控 deployment smoke |
| doc-writer | workflow-stage-owner | openai-codex/gpt-5.5 | 文档和项目记忆写回 |

## cron/task-center owners

| Agent/Label | runtimeRole | model | 说明 |
|-------------|-------------|-------|------|
| ops-agent | cron-task-owner | openai-codex/gpt-5.5 | TODO、异常日志、配置巡检、memtidy、claim audit 等运维定时任务 |
| optimization-agent | cron-task-owner | openai-codex/gpt-5.5 | 本地最新方案中的仓库精简巡检 |

## inactive legacy labels

`main`、`explorer`、`agent-factory`、`self-evolution-agent`、`git-master` 不属于 nofx 当前 active workflow / cron owner 集合；历史资料只保留在 archive 或旧会话证据中。

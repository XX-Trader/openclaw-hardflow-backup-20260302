# 多 Agent / Workflow Owner 体系

> 最后更新：2026-04-27
> 本页是 nofx 当前 workflow 口径，不再使用 2026-03 的 14 Agent 注册表作为 active 事实源。

## 当前结论

nofx 现在按四层理解：

1. **入口层**：服务器对外运行两个 Hermes Discord profile：`arbitrageagent`、`spreadagent`。它们是入口，不是完整工作流本身；两者模型均为 `openai-codex/gpt-5.5`。
2. **工作流层**：真正执行入口是 `/home/arbops/.local/bin/smart-arb-pipeline`，它调用 `/home/arbops/.hermes/ops/pipeline_runner.py`。
3. **逻辑 owner 层**：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` 是 workflow 阶段责任人 / workspace 标签，不是常驻进程。
4. **定时任务层**：cron/task-center 主要由 `ops-agent`、`project-agent` 执行；本地最新方案新增 `optimization-agent` 执行仓库精简巡检。

## 入口层

| profile | 类型 | 模型 | 作用 |
|---------|------|------|------|
| `arbitrageagent` | Hermes Discord profile | `openai-codex/gpt-5.5` | 套利策略运维与策略开发入口 |
| `spreadagent` | Hermes Discord profile | `openai-codex/gpt-5.5` | 价差费率监控与只读观测入口 |

这两个 profile 收到执行类请求后必须创建 `smart-arb-pipeline` run，不在 profile 会话里直接实现、部署、安装依赖、修改代码或提交 Git。

## 工作流层

标准入口：

```bash
/home/arbops/.local/bin/smart-arb-pipeline --profile <arbitrageagent|spreadagent> --source discord --requirement "<需求文本>"
```

安装态调用链：

```text
Hermes Discord profile
→ /home/arbops/.local/bin/smart-arb-pipeline
→ /home/arbops/.hermes/ops/smart_arb_pipeline_entry.py
→ /home/arbops/.hermes/ops/pipeline_runner.py
```

主阶段：

```text
research
→ 需求讨论
→ 方案
→ 编码
→ 测试
→ review
→ deployment
→ memory_writeback
```

`git_publish` 是 memory writeback 之后的可选发布门禁，由 `coordinator` 负责，不再注册为单独 agent。

## 逻辑 owner 层

| owner | 对应阶段 | 说明 |
|-------|----------|------|
| `coordinator` | intake、Git 发布门禁 | 组织流程、汇总状态、处理受控发布 |
| `project-agent` | 项目记忆、需求包、方案包、需求讨论 | 项目事实源和需求/方案结构化 |
| `web-agent` | research | 官方资料、外部来源、成熟方案核对 |
| `reviewer` | 需求审查、方案审查、代码审查 | 审查裁决与分歧拦截 |
| `backend-dev` | 编码 | 后端、脚本、服务和策略代码修改执行 |
| `frontend-dev` | 编码 | 前端、页面、UI 和交互代码修改执行 |
| `tester` | 测试、验收 | verification 与 acceptance |
| `deployer` | deployment | 内控 FastAPI restart/smoke |
| `doc-writer` | memory_writeback | 文档和项目记忆回写 |

这些 owner 会出现在 `command-runs/*.json`、`agent-workspaces/manifest.json`、Task Center 记录和状态卡里。它们代表阶段责任与隔离 workspace，不代表 nofx 上存在同名常驻模型进程。

## 定时任务层

| owner | 当前用途 |
|-------|----------|
| `ops-agent` | TODO 巡检、异常日志巡检、配置巡检、memtidy、claim audit、deadline bridge |
| `project-agent` | 项目索引维护、项目事实源相关定时任务 |
| `optimization-agent` | 本地最新方案新增的 `repo_hygiene_reviewer_2d` 仓库精简巡检 |

## 已停用 / 不再 active 的旧标签

以下标签不属于 nofx 当前 active workflow / cron owner 集合：

- `main`
- `explorer`
- `agent-factory`
- `self-evolution-agent`
- `git-master`

若历史文档或旧会话中出现这些名称，只能作为 2026-03 OpenClaw 旧注册表或旧任务证据理解，不能作为当前运行态结论。

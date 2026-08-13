# runtime-host 控制面全景

> 最后更新：2026-05-08
> 本页描述当前 runtime-host Hermes workflow runtime，不沿用旧 OpenClaw 14 Agent 控制面口径。

## 核心答案

| 问题 | 当前事实 | 真相源 |
|------|----------|--------|
| 对外入口是什么 | `deliveryagent`、`projectagent` 两个 Hermes Discord profile | `/home/runtime-user/.hermes/profiles/<profile>/config.yaml` |
| 使用什么模型 | 两个入口主模型均为 `openai-codex/gpt-5.5`；主回退 `kimi-coding/kimi-k2.6 -> zai/glm-5.1`；辅助任务默认 `zai/glm-4.7`，`compression/curator` 为 `zai/glm-5.1`；不使用 OpenRouter | profile `config.yaml` / `.env` |
| 真正执行什么 | `/home/runtime-user/.local/bin/project-delivery-pipeline` | profile `SOUL.md` 与软链接 |
| runner 在哪里 | `/home/runtime-user/.hermes/ops/pipeline_runner.py` | runtime installer 安装产物 |
| 逻辑 owner 有哪些 | `coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` | `pipeline_runner.py` / `project_pipeline_entry.py` |
| 定时任务 owner | `coordinator`、`project-agent`；仓库精简巡检也由 `coordinator` 承载 | `/home/runtime-user/.hermes/cron/jobs.json` |

## 运行链路

```text
Discord
→ Hermes profile: deliveryagent / projectagent
→ /home/runtime-user/.local/bin/project-delivery-pipeline
→ /home/runtime-user/.hermes/ops/project_pipeline_entry.py
→ /home/runtime-user/.hermes/ops/pipeline_runner.py
→ command-runs / agent-workspaces / Task Center
```

## 阶段链路

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

`git_publish` 是 memory writeback 后的可选发布门禁，由 `coordinator` 负责执行和状态回写，不再单独建 `git-master` agent。

## 排障优先级

1. 查两个 profile 的 `gateway_state.json` 和 `config.yaml`。
2. 查 `/home/runtime-user/.local/bin/project-delivery-pipeline` 是否指向当前 ops 脚本。
3. 查最近 run 的 `pipeline_state.json`、`command-runs/*.json`、`agent-workspaces/manifest.json`。
4. 查 `/home/runtime-user/.hermes/cron/jobs.json` 区分 cron owner 与 workflow owner。
5. 如果文档出现 14 Agent、`agent-factory`、`explorer`、`git-master` 等旧标签，先判断是否是 archive / 历史会话；不要据此推断当前 runtime-host 有同名常驻 agent。`frontend-dev` 仍是当前逻辑 owner，但不是入口或常驻进程。

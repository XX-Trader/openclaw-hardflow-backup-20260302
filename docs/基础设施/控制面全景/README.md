# nofx 控制面全景

> 最后更新：2026-04-27
> 本页描述当前 nofx Hermes workflow runtime，不沿用旧 OpenClaw 14 Agent 控制面口径。

## 核心答案

| 问题 | 当前事实 | 真相源 |
|------|----------|--------|
| 对外入口是什么 | `arbitrageagent`、`spreadagent` 两个 Hermes Discord profile | `/home/arbops/.hermes/profiles/<profile>/config.yaml` |
| 使用什么模型 | 两个入口均为 `openai-codex/gpt-5.5` | profile `config.yaml` |
| 真正执行什么 | `/home/arbops/.local/bin/smart-arb-pipeline` | profile `SOUL.md` 与软链接 |
| runner 在哪里 | `/home/arbops/.hermes/ops/pipeline_runner.py` | runtime installer 安装产物 |
| 逻辑 owner 有哪些 | `coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer` | `pipeline_runner.py` / `smart_arb_pipeline_entry.py` |
| 定时任务 owner | 主要是 `ops-agent`、`project-agent`；本地最新新增 `optimization-agent` 仓库精简巡检 | `/home/arbops/.hermes/cron/jobs.json` |

## 运行链路

```text
Discord
→ Hermes profile: arbitrageagent / spreadagent
→ /home/arbops/.local/bin/smart-arb-pipeline
→ /home/arbops/.hermes/ops/smart_arb_pipeline_entry.py
→ /home/arbops/.hermes/ops/pipeline_runner.py
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
2. 查 `/home/arbops/.local/bin/smart-arb-pipeline` 是否指向当前 ops 脚本。
3. 查最近 run 的 `pipeline_state.json`、`command-runs/*.json`、`agent-workspaces/manifest.json`。
4. 查 `/home/arbops/.hermes/cron/jobs.json` 区分 cron owner 与 workflow owner。
5. 如果文档出现 14 Agent、`agent-factory`、`explorer`、`git-master` 等旧标签，先判断是否是 archive / 历史会话；不要据此推断当前 nofx 有同名常驻 agent。`frontend-dev` 仍是当前逻辑 owner，但不是入口或常驻进程。

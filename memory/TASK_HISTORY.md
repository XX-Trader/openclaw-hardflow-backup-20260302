# TASK_HISTORY

## 2026-04-27 - nofx agent 口径与模型快照修正

类型：task
范围：`agents/`、`openclaw.json`、`openclaw/openclaw.json`、`memory/INDEX.md`、`memory/RUNBOOK.md`、`docs/核心主工作流/项目交付优先工作流/`、`docs/基础设施/多Agent体系/README.md`、`todo.md`
事实：修正关于 nofx “14 个常驻 agent”的误导口径。当前 nofx live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`，两者模型均为 `openai-codex/gpt-5.5` 且 gateway running；真正执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`。工作流阶段 owner 为 `coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`，它们是阶段 owner / workspace / Task Center 标签，不是独立常驻 agent；前端/UI/页面/交互类代码执行可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。定时任务层主要由 `ops-agent`、`project-agent` 执行，本仓库最新方案新增 `optimization-agent` 做仓库精简巡检。2026-03 的 14 Agent 文档保留为历史 OpenClaw 注册表快照，不再作为 nofx 运行态结论；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
证据：2026-04-27 nofx 远程核对 profile config、gateway_state、tmux 会话、缺失常驻 agent 目录、cron/jobs 和 hardflow 仓库 HEAD；本地 `openclaw.json`、`openclaw/openclaw.json`、agent index/capability manifest、pipeline runner、entry、live bridge 与文档已统一为 2 个入口 profile、9 个 workflow owner、3 类 cron owner；文档已同步标注当前 server runtime 仍在 `44b4dae`，尚未安装本仓库最新 `e45e0af` 的 `repo_hygiene_reviewer_2d` 与 2 天 `source_registry_watcher` 运行态。
最后验证：2026-04-27 11:14
复用建议：后续沟通一律使用“四层口径”：入口 profile、workflow runner、阶段 owner 标签、cron 责任标签；模型只对真实 profile 或明确 provider command 声明，不把标签误写成独立模型。

## 2026-04-27 - 2 天仓库精简巡检与 Git 发布门禁

类型：task
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、`source_registry_watcher.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：新增 `repo_hygiene_reviewer.py` 只读仓库精简巡检，默认每 2 天由 `optimization-agent` 执行；`source_registry_watcher` 频率也调整为每 2 天并修复 `--base-path` 生效；项目交付流水线新增 `git_publish` 可选阶段，默认 live entry 会注入该命令，提交说明必须中文且脱敏，失败回流 `fix_git_publish`；发布输入会优先采用 `memory_writeback` 隔离工作区 patch，避免漏掉文档/记忆写回变更，并禁止夹带 `command_cwd` 未验收脏改动。本轮修复仓库精简脚本对内联冲突标记示例的误报，并删除已跟踪的 `cron/jobs.json.bak.20260422220950` 备份文件。
证据：相关测试覆盖 pipeline git_publish 成功/失败、写回后 patch 进入发布工作区、未验收脏改动不进入发布工作区、entry 默认注入/可跳过、live bridge 中文 commit/push 与 commit message 脱敏、repo hygiene 只读扫描、冲突标记误报防护、source watcher base path、runtime installer 安装新脚本。
最后验证：2026-04-27 11:14 相关单元测试与 repo hygiene smoke 通过
复用建议：仓库治理候选不直接删除；通过人工确认后再进入交付流水线。Git 发布不替代部署，deployment 仍只做内控服务 smoke；真正生产部署需按对应项目 RUNBOOK 执行。

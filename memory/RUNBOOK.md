# RUNBOOK

## nofx 项目交付入口排障

常用事实源：

- nofx hardflow 仓库：`/home/arbops/projects/openclaw-hardflow-backup-20260302`
- nofx SmartMultiPlatformArbitrage 仓库：`/home/arbops/projects/SmartMultiPlatformArbitrage`
- Hermes runtime：`/home/arbops/.hermes`
- 标准入口：`/home/arbops/.local/bin/smart-arb-pipeline`（固定 live）
- pipeline runs：`/home/arbops/.hermes/pipeline-runs`
- Task Center DB：`/home/arbops/.hermes/ops/task-center/task_center.db`
- nofx profile SOUL 模板：`config/nofx-hermes-profiles/<profile>/SOUL.md`

## 2026-04-28 - Discord 全任务路线选择

类型：runbook
范围：nofx Discord profile `SOUL.md`、`smart-arb-pipeline` 入口、Task Center/backlog runner、SmartMultiPlatformArbitrage 安全仓库同步
事实：连接 Discord 的 Hermes profile 是 nofx Discord 入口的最高权限调度入口，但最高权限不等于跳过人工路线选择。所有 Discord 新任务都必须先发“执行链路选择”卡，固定选项为 `direct_run`、`requirement_discussion`、`specified_agent`、`coding_workflow`、`todo_auto_candidate`，并以 `回答状态: 等待人工选择` 结束。只读状态查询、简单解释、监控查询、“不要走工作流”、安全仓库同步、业务执行、TODO 推进和 hardflow workflow/runtime/profile 自修都必须先选择；用户选择 `direct_run` 后，当前 Discord profile 才可以作为最高权限 operator 直接处理。只有 `coding_workflow` / `todo_auto_candidate` 会启动 `smart-arb-pipeline`。
证据：2026-04-28 23:23 Discord run `discord-spreadagent-20260428T152135225120Z` 没有询问用户，直接进入 `smart-arb-pipeline` 并卡在 `solution_review`；artifact 显示旧 profile 仍把普通任务导向 pipeline，且只读/普通沟通存在直答例外。已将两个 profile 模板改为“收到任何 Discord 新任务，不要先执行、不要先启动 pipeline、不要直接做只读查询或普通沟通”，并增加模板测试覆盖。
最后验证：2026-04-28 23:54，nofx live profile 已同步，arbitrageagent / spreadagent gateway 均 `running/connected`
复用建议：排查“为什么 Discord 没问我”时，先查 live `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 前 20 行是否包含“所有来自 Discord 的新任务”“最高权限 operator”“回答状态: 等待人工选择”。如果只改了仓库模板没有同步 live profile 或没重启 gateway，Discord 仍会沿用旧规则。

排障顺序：

1. 查 `tmux ls`，确认 `hermes-tg`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-api` 是否存在。
2. 查 Hermes profile gateway state，确认 Discord 是否 connected。
3. 查最近 `pipeline_state.json` 和 `command-runs/*.json`，确认是否进入 live pipeline，以及每个阶段实际 command。
4. 查 `agent-workspaces/manifest.json`，确认每个阶段 owner 是否有独立 workspace。
5. 查 `command-runs/code_execution-1.patch` 是否生成并成功应用回主项目目录。
6. 查 `smart_arb_pipeline_entry.py` 和 `smart_arb_live_bridge.py` 的安装态版本，确认是否与本仓库 HEAD 对齐。
7. 若用户关心“是否转发到其他 agent”，必须检查是否有独立 agent session/run id，而不是只看 Task Center 的 `agent_id` 字段。

注意：当前 live bridge 已证明 workspace 隔离和阶段命令执行；2026-04-25 22:06 的 nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 里，命令阶段均记录为 `runtime-agent-workspace` / `isolated-agent-workspace`。native 多 agent fan-out 仍需以独立宿主 session/run id 为准。

## 2026-04-27 - nofx agent/model 实时口径

类型：runbook
范围：`/home/arbops/.hermes/profiles`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、项目交付优先工作流阶段 owner
事实：nofx 当前不是 14 个常驻 agent。服务器 live 入口是两个 Hermes Discord profile：`arbitrageagent` 和 `spreadagent`；两者均为 `model.provider=openai-codex`、`model.default=gpt-5.5`，且 `gateway_state=running`。服务器没有可作为 14 个常驻 agent 注册表解释的 `/home/arbops/.hermes/agents`、`/home/arbops/.openclaw/agents`、`/root/.openclaw/agents`、`/home/arbops/.codex/agents`、`/root/.codex/agents` 目录。真正执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`，阶段为 `research -> 需求讨论 -> 方案 -> 编码 -> 测试 -> review -> deployment -> memory_writeback`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`；cron / Task Center 定时任务只挂 `coordinator/project-agent`。`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
证据：2026-04-27 通过 nofx 远程核对：`tmux ls` 包含 `hermes-discord-arbitrage`、`hermes-discord-spread`、`hermes-tg`、`smart-arb-api`；两个 profile 的 `config.yaml` 均显示 `openai-codex/gpt-5.5`；`gateway_state.json` 均为 `running`。同时复核 nofx hardflow 仓库 `HEAD=44b4dae`，安装态 `/home/arbops/.hermes/ops/repo_hygiene_reviewer.py` 尚不存在，cron 仍有 11 个 job，其中 `source_registry_watcher` 仍是每周日运行。
最后验证：2026-04-27 10:30
复用建议：以后回答“服务器上有多少 agent、什么模型”时按四层区分：入口层是两个 live Hermes profile 与模型；工作流层是 `smart-arb-pipeline -> pipeline_runner.py`；逻辑 owner 层是 9 个 active owner 标签；定时任务层只允许 active owner 承载，当前为 `coordinator/project-agent`。不要把 2026-03 OpenClaw 14 Agent 注册表当成 nofx 当前运行态。若要把本仓库最新 2 天巡检和 Git 发布门禁同步到 nofx，先拉取最新 `main`，再运行 runtime installer。

## nofx hardflow 拉取与安装记录

### 2026-04-28 23:15 - 最新 `d2e530b7` 代码批次安装到 nofx

类型：runbook
范围：nofx hardflow 仓库、runtime installer、live profile SOUL、gateway、Task Center smoke
事实：nofx 安装顺序为：确认无活跃 `smart-arb-pipeline` -> `git pull --ff-only origin main` -> `runtime_installer.py install` -> 远端 `git diff --check`、`py_compile`、`compileall`、定向 `unittest` -> `smart-arb-pipeline --help` -> 同步 live profile SOUL -> 重启两个 Discord gateway -> 内控 API smoke -> echo pipeline smoke -> 清理 `file_write_audit.jsonl` 测试副作用。
证据：本轮远端 HEAD 为 `d2e530b7`，`HEAD...origin/main=0 0`，runtime installer 返回 `ok=true`/`changed=true`，19 项定向单测 OK，两个 gateway `running/connected`，echo smoke `install-smoke-arbitrageagent-20260428T151514657470Z` 完成 15/15 且 Task Center `passed`。
最后验证：2026-04-28 23:15
复用建议：复杂远端脚本优先 Paramiko 单连接；如果用 PowerShell 直接拼 SSH 命令，必须防止 `$p`、`$TS` 等远端 shell 变量被本地展开。profile 模板变化时不要只跑 runtime installer，还要同步 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 并重启 gateway。

### 2026-04-28 19:40 - 最新 `17d9b369` 文档记录提交同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、cron jobs、Discord gateways、内控 API
事实：nofx hardflow 仓库已对齐最新 `origin/main`：`HEAD=17d9b36`，`HEAD...origin/main=0 0`，工作树 clean；`git pull --ff-only origin main` 返回 already up to date，本轮没有远端脏改动，未创建 stash。runtime installer 返回 `ok=true`、`changed=true`，安装 5 个 runtime skill、18 个 ops 脚本和 12 个 cron job；`memtidy` 继续为 0。本轮只是安装 runtime ops 和文档记录提交，没有 profile SOUL 改动，因此不重启 `hermes-discord-*`。
证据：安装日志 `/tmp/hardflow-runtime-install-20260428T113954Z.json`；安装态 3 个核心脚本 `py_compile` 通过；远端 `compileall` 通过；定向 `unittest` 76 项 OK；`smart-arb-pipeline --help` 正常；`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 的仓库源码与 `/home/arbops/.hermes/ops` SHA256 分别一致；两个 gateway 为 `running`；内控 API `/health` 为 `status=ok`，`/api/strategy/status` 为 `running=false`；echo smoke `install-smoke-arbitrageagent-20260428T114016095602Z` 完成 15/15 阶段，`next_action=none`。
最后验证：2026-04-28 19:40
复用建议：远程多命令不要再用 PowerShell here-string 直接管道给 Bash；该路径会出现 BOM 首行，导致 `set: command not found` 和退出码污染。优先用 Paramiko 低频单连接，或用 Git for Windows ssh 执行简单命令。

### 2026-04-28 19:05 - filtered target candidates 版本同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops/pipeline_runner.py`、cron jobs、Discord gateways
事实：nofx hardflow 已从 `195c513` fast-forward 到 workflow 代码批次 `353f420d`（远端短 hash `353f420`），`HEAD...origin/main=0 0` 且工作树 clean。runtime installer 已把最新 `pipeline_runner.py` 安装到 `/home/arbops/.hermes/ops`，本轮没有 profile SOUL 改动，因此没有重启 Discord gateway。旧 `memtidy_runner` cron 继续保持移除，cron job 数为 12。
证据：远端 `py_compile` 安装态 `pipeline_runner.py` 通过；远端定向 `unittest` 73 项 OK；仓库源码与 runtime 安装态 `pipeline_runner.py` SHA256 均为 `c481bf4c933a64e6e5cda7845391f2b99a42b57aa56e1136d43ceca31dd5c6cf`；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；cron 命中 `backlog_runner`、`repo_hygiene_reviewer`、`source_registry_watcher`，`memtidy_hits=0`；`hermes-discord-arbitrage`、`hermes-discord-spread`、`hermes-tg` tmux 会话存在；两个 profile `gateway_state=running`，日志近 80 行错误数为 0；runtime dry-run smoke `/tmp/hardflow-install-smoke-20260428T110456Z` 验证 `E:/repo/src/app.py` 被过滤为 `external_or_runtime_absolute_path` 并展示到 `solution.md`。
最后验证：2026-04-28 19:05
复用建议：远端非登录 shell 里不要依赖裸 `smart-arb-pipeline`，用 `/home/arbops/.local/bin/smart-arb-pipeline`。只安装 ops 脚本且 profile 模板未变时，不必重启 Discord gateway。

### 2026-04-28 16:27 - Discord 回答状态版本同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}/SOUL.md`、Task Center、内控 API
事实：nofx hardflow 已 fast-forward 到回答状态代码批次 `f94c2284`（远端短 hash `f94c228`），runtime installer 已把 `smart_arb_pipeline_entry.py` 安装到 `/home/arbops/.hermes/ops`。安装态文件包含启动卡、运行中进度卡和最终状态卡的 `回答状态` 行。两个 live profile `SOUL.md` 已从仓库模板同步，原文件备份为 `SOUL.md.bak-answer-status-20260428T082523Z`，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
证据：远端 `python3 -m py_compile scripts/openclaw-ops/smart_arb_pipeline_entry.py` 通过；远端 `python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；远端定向 `unittest` 39 项 OK；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；两个 gateway 均为 `running` / Discord `connected`；内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`；echo smoke run `deploy-smoke-spreadagent-20260428T082751163478Z` 完成 15/15 阶段，状态卡顶部显示 `回答状态: 已回答完毕`，并使用 `--skip-deployment-command`、`--skip-git-publish-command`，未触发真实交易、真实部署或 git publish。
最后验证：2026-04-28 16:27
复用建议：以后修改 Discord 状态卡或 profile SOUL 后，必须同时验证三层：仓库源码、`/home/arbops/.hermes/ops` 安装态、live profile `SOUL.md`；仅 `git pull` 不代表 Discord gateway 已加载新提示词。

### 2026-04-28 14:34 - DeliveryPlan / revise_solution 版本同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`、内控 API
事实：nofx hardflow 已安装 runtime 代码批次 `3a44f0b0`，安装时 `HEAD...origin/main` 为 `0 0` 且工作树 clean；后续文档/记忆记录提交可继续 fast-forward 到 `origin/main`，不改变本批 runtime artifact。runtime installer 返回 `ok=true`、`changed=true`；安装态 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 与仓库源码 SHA256 对齐。两个 live profile `SOUL.md` 已从仓库模板同步并备份为 `SOUL.md.bak-20260428T143343`，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
证据：远端 `compileall` 通过；远端定向 `unittest` 67 项 OK；`smart-arb-pipeline --help` 正常；`arbitrageagent` PID `1137425`、`spreadagent` PID `1137427`，gateway 均为 `running` / Discord `connected`；内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`；安装器 JSON 显示 cron jobs 已同步。
最后验证：2026-04-28 14:40
复用建议：修改仓库内 nofx profile 模板后，安装 runtime ops 之外还要手动同步 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 并重启 gateway；否则 Discord profile 仍会使用旧提示词。

### 2026-04-27 23:17 - 密钥扫描收敛版本同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、Task Center、内控 API
事实：nofx hardflow 仓库已拉到 `067fbc43`，`HEAD...origin/main` 为 `0 0`。安装前已备份 runtime 目标文件到 `/home/arbops/.hermes/ops/install/backups/pre-hardflow-install-20260427T151242Z`；runtime installer 已把 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 安装到 `/home/arbops/.hermes/ops`，并与仓库源码 SHA256 对齐。本轮没有通过 Discord profile 自修，也没有执行真实 Hermes chat、服务重启或 git publish smoke。
证据：`smart-arb-pipeline --help` 正常；远端安装态 `py_compile` 通过；远端 `compileall` 通过；定向 `unittest` 98 项 OK；cron 中 `backlog_runner_30m`、`repo_hygiene_reviewer_2d`、`source_registry_watcher` 各 1 条；`arbitrageagent` 与 `spreadagent` gateway 均为 `running/connected`；内控 API `/health` 为 `status=ok` 且 `/api/strategy/status` 为 `running=false`；echo smoke run `install-smoke-arbitrageagent-20260427T151733781612Z` 为 `status=completed` 且 Task Center `passed`。`smart-arb-api` cwd 已复核为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 23:17
复用建议：Windows 自带 OpenSSH 若出现空退，可直接切 Git for Windows `C:\Program Files\Git\usr\bin\ssh.exe`；复杂远端脚本优先用 Paramiko stdin，避免 PowerShell 管道带 BOM 导致远端 bash 首行 `set` 被解析成 `﻿set`。

### 2026-04-27 15:01 - 最新 runtime installer 同步到 nofx

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`
事实：nofx hardflow 仓库已从 `44b4dae` fast-forward 到 `578b3f0`，本次 `git status --porcelain` 为空，`STASH_NAME=none`。runtime installer 返回 `ok=true`、`changed=true`，已安装 `repo_hygiene_reviewer.py`、`backlog_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 等 ops 脚本；runtime cron 已包含 `backlog_runner_30m（持续推进待办）`、`repo_hygiene_reviewer_2d（仓库精简巡检）` 和 `source_registry_watcher（API来源监控）`。
证据：`python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol` 通过；定向单测 `test_backlog_runner`、`test_project_delivery_runtime_installer`、`test_repo_hygiene_and_source_watcher`、`test_active_agent_registry`、`test_smart_arb_pipeline_entry`、`test_smart_arb_live_bridge` 共 53 项 OK；两个 Discord gateway 重启后 `gateway_state=running`、`discord=connected`；`curl http://127.0.0.1:18080/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`，`/api/strategy/status` 返回 `{"running":false,"pid":null}`；echo smoke run `install-smoke-arbitrageagent-20260427T065537Z` 为 `ok=true`、Task Center `passed`；受控 backlog runner smoke 任务 `todo-hardflow-install-smoke-20260427T070123Z` 被标记 `passed`，并写入 1 条 `backlog_runner_attempt`。
最后验证：2026-04-27 15:01
复用建议：安装完成后要额外核对 `smart-arb-api` tmux pane cwd，确认仍为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`，避免 live bridge deployment 单测或手工 smoke 把内控 API 留在临时目录。

### 2026-04-26 17:03 - Discord pipeline evidence 修复安装

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`
事实：本机提交 `edd05e23` 已推送到 `origin/main`，nofx 仓库已 fast-forward 到 `edd05e2` 并运行 runtime installer；`smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py` 已安装到 `/home/arbops/.hermes/ops`，`/home/arbops/.local/bin/smart-arb-pipeline` 指向新入口。拉取前服务器上已有上一轮手动同步的同批脏改动，已先保存为 `stash@{0}: pre-pull-hardflow-discord-pipeline-20260426`，再执行 `git pull --ff-only origin main`。
证据：runtime installer 返回 `ok=true`、`changed=true`、manifest 为 `/home/arbops/.hermes/ops/install/project-delivery-runtime-install.json`；`py_compile` 通过；nofx 相关单测 `tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 与 `tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 共 37 项 OK；`curl http://127.0.0.1:18080/health` 返回 `{"status":"ok","strategy_running":false,"ipc_connected":false}`，`/api/strategy/status` 返回 `{"running":false,"pid":null}`；echo smoke run `cli-arbitrageagent-20260426T090250542271Z` 为 14/14 阶段 completed，中文状态卡包含 agent 分工、agent 输出摘要和证据目录。
最后验证：2026-04-26 17:03
复用建议：以后 hardflow 代码推送后，nofx 安装按 `git fetch -> stash dirty tracked changes -> git pull --ff-only -> runtime_installer.py install -> py_compile -> gateway restart -> API smoke -> echo smart-arb-pipeline smoke` 顺序执行；若服务器仓库因手动同步变脏，先保留 stash，不要直接 reset。

## nofx profile SOUL 刷新

本仓库维护两个 UTF-8 模板：

- `config/nofx-hermes-profiles/arbitrageagent/SOUL.md`
- `config/nofx-hermes-profiles/spreadagent/SOUL.md`
- `config/nofx-hermes-profiles/arbitrageagent/config.yaml`
- `config/nofx-hermes-profiles/spreadagent/config.yaml`

刷新步骤：

1. 上传模板到 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 和 `config.yaml`，上传前备份原文件。
2. 避免通过 PowerShell 内联中文重写远程文件；用 SFTP 或 scp 按字节上传。
3. 确认 `SOUL.md` 内入口是绝对路径 `/home/arbops/.local/bin/smart-arb-pipeline`，不要依赖 gateway 的 `PATH`；确认 `config.yaml` 为 `approvals.mode: 'off'`、`security.tirith_enabled: false`。
4. 重启 tmux 会话：
   - `hermes-discord-arbitrage` 通过 `/home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh`
   - `hermes-discord-spread` 通过 `/home/arbops/.hermes/profiles/spreadagent/start-gateway.sh`
5. profile `.env` 和 `config.yaml` 必须保持 `arbops:arbops` 且 `0600`；如果通过 root/SFTP 写回，必须再 `chown arbops:arbops`，否则 gateway 或 Discord slash command 会因读写 profile 配置失败。
6. 验证：
   - `tmux ls`
   - `cat /home/arbops/.hermes/profiles/<profile>/gateway_state.json`
   - 读取 `SOUL.md` 前 10 行确认中文不是问号乱码。

### 2026-04-28 - 普通沟通/独立协作三分流（已被全任务路线选择取代）

类型：runbook
范围：nofx `arbitrageagent` / `spreadagent` Discord profile SOUL、`smart-arb-pipeline` 入口边界
事实：该三分流是 2026-04-28 17:01 的旧口径，已被 23:45 的“所有 Discord 新任务先执行链路选择”取代。现在“不走工作流 / 直接沟通 / 先讨论 / 先自己开发”也不能直接执行；如果不是上一张选择卡的明确回复，必须先发执行链路选择卡。选择 `direct_run` 后，当前 Discord profile 才直接沟通、只读查询或做低风险直接操作；选择 `coding_workflow` / `todo_auto_candidate` 后才启动 pipeline。
证据：2026-04-28 17:01 已把模板和 live profile 同步到 nofx，并重启两个 gateway；`arbitrageagent` / `spreadagent` 均 `gateway_state=running` 且 Discord `connected`。
最后验证：2026-04-28 23:45
复用建议：排查当前行为时优先使用本 RUNBOOK 顶部“Discord 全任务路线选择”条目，不再按三分流旧口径判断。

## nofx live verification 门禁

Discord live pipeline 的 verification 阶段不再默认跑全量 `unittest discover`，因为 nofx 上该命令曾在 async/zmq 相关测试中长时间挂起。当前安全默认是：

```bash
git diff --check
/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime
```

profile `.env` 显式配置：

```bash
SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS=180
SMART_ARB_LIVE_BRIDGE_TEST_COMMAND='/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime'
```

`smart-arb-pipeline --live` 会把单命令超时写入 verification bridge 命令，例如 `--verification-command-timeout-seconds 180`。排障时查：

1. `command-runs/verification-1.json` 的 `command` 是否包含 timeout 参数。
2. `verification_report.md` 是否记录实际验证命令和 returncode。
3. 如果需要全量 unittest，只能在人工排障或 CI 中单独跑，不要作为 Discord live 默认门禁。

## nofx Hermes profile 审批配置

本机 WSL 的有效做法是 profile 级配置，而不是只看全局 `~/.hermes/config.yaml`：`/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml` 中有顶层 `approvals.mode: 'off'`。

nofx 上没有 `/home/arbops/.hermes/config.yaml` 全局配置；Discord agent 需要分别看 profile：

- `/home/arbops/.hermes/profiles/arbitrageagent/config.yaml`
- `/home/arbops/.hermes/profiles/spreadagent/config.yaml`

若出现 `Command Approval Required`，先确认两个 profile 都有顶层配置：

```yaml
approvals:
  mode: 'off'
```

修改后重启两个 tmux gateway：

```bash
runuser -u arbops -- tmux kill-session -t hermes-discord-arbitrage
runuser -u arbops -- tmux kill-session -t hermes-discord-spread
runuser -u arbops -- tmux new-session -d -s hermes-discord-arbitrage /home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh
runuser -u arbops -- tmux new-session -d -s hermes-discord-spread /home/arbops/.hermes/profiles/spreadagent/start-gateway.sh
```

验收顺序：

1. 读两个 profile 的 `config.yaml`，确认顶层 `approvals.mode: 'off'`。
2. 读 `/home/arbops/.hermes/profiles/<profile>/gateway_state.json`，确认 `gateway_state=running` 且 `updated_at` 是重启后的时间。
3. 扫描 `/home/arbops/.hermes/profiles/<profile>/logs/*.log` 尾部，确认没有新的 `Command Approval Required` / `confusable` 记录。

## nofx smart-arb-pipeline 默认 live

`/home/arbops/.local/bin/smart-arb-pipeline` 固定真实执行 live coordinator pipeline，会注入 external research、需求讨论、编码、验证、代码审查、内部部署和记忆写回命令证据。该入口不再提供 simulation/dry-run 模式。

注意：这里的 live 指真实改代码、验证、文档/记忆写回和内部 FastAPI smoke；仍不等于解除 `PRODUCTION_TRADING_ENABLED=false`，也不允许真实下单。

如果需求明确是 memory/docs-only、只写长期事实、no service control、no deployment 或 no restart，entry 会跳过 deployment command，不重启 `smart-arb-api`。如果同一需求后续明确要求 restart/deploy/重启/部署，正向 deployment 动作优先；普通 API/服务代码改动仍会注入 deployment bridge，重启内控 FastAPI 并做 `/health` 与 `/api/strategy/status` smoke。

### 2026-04-27 - Git 发布门禁

类型：runbook
范围：`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：默认 live 入口会注入 `git_publish` 命令。runner 只在 verification、code review、deployment（如有）、acceptance 和 memory writeback 全部通过后执行该阶段；`git_publish` 优先接收 `memory_writeback` 隔离工作区 patch，缺失时只回退到已验收的 `code_execution` patch，确保不发布 `command_cwd` 的未验收脏改动；失败时阻塞为 `failed_stage=git_publish`、`next_action=fix_git_publish`。
证据：`pipeline_runner.py` 会写入 `git_publish_input_patch_report`；`smart_arb_live_bridge.py --stage git_publish` 会先执行 `git diff --check`，再 `git add -A`，随后执行 `git diff --cached --check`，打印 staged diff 统计，不打印完整 diff；随后扫描 staged diff 中的密钥形态，并在 `## Secret Scan Findings` 中输出脱敏的文件、行号、规则、风险等级和片段。真实 token/header/cookie/高熵值、hardcoded fallback secret、PEM private key marker/material 仍 hard block；环境变量名、测试假值、文档占位和 Basic Auth 说明只作为非阻塞 finding。确认安全后生成脱敏中文提交说明并执行 `git push <remote> HEAD:<branch>`。该阶段不使用 force push。
最后验证：2026-04-27 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 59 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过
复用建议：如远端冲突、认证失败、疑似密钥或 push 失败，先处理 `command-runs/git_publish-*.json` 与 `git_publish_report.md`。只有非密钥类发布失败可走 `fix_git_publish` 自动回流；secret scan 中 `risk=high` / `blocking=true` / high-risk rule evidence 仍停人工确认。不要绕过 reviewer、不要关闭 secret scan、不要 force push。需要临时关闭发布时使用 `--skip-git-publish-command` 或 `SMART_ARB_SKIP_GIT_PUBLISH_COMMAND=1`。

## 定时仓库治理

### 2026-04-28 - TODO 手动链路选择与任务拆分

类型：runbook
范围：`cron/jobs.json`、`pipeline_runner.py`、Task Center、`todo.md`
事实：待办持续推进能力保留，但当前默认先手动选择执行链路，不让系统直接自动开跑。当前 TODO 相关定时任务分工如下：
- `TODO 巡检（15分钟）`：巡检 `todo.md`，做去重播报、执行状态检测和未分配项协调。
- `todo_deadline_checker_daily（截止时间检测）`：每日 00:00 检查 `[截止:YYYY-MM-DD]` 未完成项，标记超期、到期和提醒项；远端 dry-run 曾返回 `NO_REPLY`，表示当前无需要输出的提醒。
- `todo_deadline_to_task_bridge_daily`：每日 00:05 把到期/超期 TODO 写入 Task Center；无论低风险或高风险，先创建 `route_selection.mode=manual_selection` 的 `human_question`，让用户在直接运行、需求探讨、指定 agent、编码工作流、TODO 自动候选中选择。路线选项统一来自 `policy_route_selection.py`。
- `policy_enforcer create-task`：通用任务创建默认也写入 `route_selection.mode=manual_selection`、`action=await_route_selection`、`assignee=human-inbox`；只有调用方已经提供人工选择后的 `selected_route` 和 `human_confirmed=true`，才按选择后的 action 入库。旧 `confirm-risk` 不可用于未选择路线的任务，会提示改用 `human_inbox.py confirm --route-choice ...`；选择 `specified_agent` 时必须提供 `--assignee <agent-id>`。
- `backlog_runner_30m（持续推进待办）`：每 30 分钟最多推进 1 个已人工确认且选择为 pipeline 动作的 pending 任务，或 allowlist 中带 `next_action` 且已有 pipeline 选择记录的 failed 任务；pending 任务必须正向满足 `selected_route in {coding_workflow,todo_auto_candidate}`、`human_confirmed=true`、`action=confirmed_for_execution`。选择为 `direct_run`、`requirement_discussion`、`specified_agent` 或未选择路线的任务会被跳过，默认每任务 1 次 attempt，防止循环重跑。
- `daily_todo_digest_daily`：每日汇总 TODO 状态，属于信息汇总，不是执行推进器。
- `project_index_maintainer_4h`：维护项目索引和注册表，帮助 TODO/Task Center 定位项目事实源，不直接执行待办。
拆分规则：当用户需求包含多个独立事项时，`delivery_plan.json` 必须写入 `scope_slices`。第一块为 `current` 并进入本轮执行，其余为 `deferred`，后续通过 Task Center run 或用户确认继续推进；凭证、资金、生产破坏、需求不清和边界冲突仍必须回问用户。
证据：`deadline_to_task_bridge.py` 会为到期 TODO 写入路线选择候选并复用统一路线 helper；`policy_task.py` 会为通用 create-task 写入路线选择候选并拦截旧确认入口；`human_inbox.py confirm --route-choice` 记录人工选择、CLI 支持 `recommended`、并拦截缺少 assignee 的 `specified_agent`；`backlog_runner.py` 使用正向 pipeline route 门禁；`pipeline_runner.py` 保留 `scope_slices` 拆分。
最后验证：2026-04-28 21:31 本地 `python -m unittest tests.scripts_openclaw_ops.test_human_inbox tests.scripts_openclaw_ops.test_policy_task_manual_route tests.scripts_openclaw_ops.test_deadline_to_task_bridge tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_workflow_selector -v` 18 项 OK；`py_compile` 覆盖 7 个改动脚本通过。
复用建议：以后用户说“先手动设置 / 先询问人走什么链路”时，按路线选择模式处理；等推荐准确率稳定后，再按任务类型逐步开放自动执行。

### 2026-04-28 - cron 状态投递到 Discord 群

类型：runbook
范围：`cron/jobs.json`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`
事实：本仓库 cron 模板中的 `delivery` 与 `failureAlert` 已从旧 Telegram 群切到 Discord spreadagent 群 `1494595527181078578`。OpenClaw cron delivery 支持显式 channel/to；Discord 数字频道 ID 会按 normalize 逻辑解析为目标 channel。该变更只影响定时任务结果和失败告警投递，不新增交易、资金、写接口或服务重启动作。
证据：`cron/jobs.json` 中 20 个投递目标均为 `channel=discord`、`to=1494595527181078578`；安装器测试会校验 `system_exception_to_task_bridge`、`todo_deadline_to_task_bridge_daily`、`backlog_runner_30m` 安装后的 `delivery` / `failureAlert` 均指向该 Discord 群。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 36 项 OK；`python -B -m json.tool cron/jobs.json`、`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过
复用建议：如果后续换群，只改 `cron/jobs.json` 中的投递目标并重新运行 runtime installer；不要在任务 payload 里硬编码 webhook 或 token。

### 2026-04-27 - Task Center 待办持续推进

类型：runbook
范围：`cron/jobs.json`、`scripts/openclaw-ops/backlog_runner.py`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`
事实：新增 `backlog_runner.py`，并注册 `backlog_runner_30m（持续推进待办）`。该 job 每 30 分钟最多选择 1 个 Task Center 中低风险、已人工确认走 pipeline、无需澄清的 pending 待办，或显式允许 `next_action` 的 failed 项，调用 runtime 内安装的 `python3 <runtime_home>/ops/smart_arb_pipeline_entry.py --live --profile spreadagent --source backlog-runner` 继续推进。高风险、需确认、需澄清、`escalate_human` 以及被人工选择为直接运行、需求探讨、指定 agent 的任务会被跳过，继续由 `human_inbox.py` 或人工协作处理；每个任务默认只记录 1 次 `backlog_runner_attempt`，避免无限重复续跑。若 pipeline 命令启动失败，runner 会记录 failed 输出并把任务转为 `failed`，不会卡在 `running`。
证据：`scripts/openclaw-ops/backlog_runner.py` 实现安全选择、失败项 next_action allowlist、防循环、pipeline 调用和启动失败兜底；`cron/jobs.json` 新增 `b9c8d7e6-backlog-runner-0030`，`--pipeline-command` 指向 runtime `ops/smart_arb_pipeline_entry.py`，不再从 runtime home 反推 `~/.local/bin`；`runtime_installer.py` 会把脚本安装到 runtime `ops/backlog_runner.py`；本地测试 `python -m unittest tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_project_delivery_runtime_installer tests.scripts_openclaw_ops.test_repo_hygiene_and_source_watcher` 共 9 项 OK。
最后验证：2026-04-27 12:00
复用建议：以后排查“很多 TODO 只有用户催才推进”时，先查 nofx 是否已安装 `ops/backlog_runner.py`，再查 `cron/jobs.json` 是否有 `backlog_runner_30m`，最后查 Task Center 中被跳过任务的 `need_human_confirm`、`needs_clarification`、`risk_level`、`source`、`next_action` 和 `backlog_runner_attempt` 输出。

### 2026-04-27 - 两天一次来源监控与仓库精简巡检

类型：runbook
范围：`cron/jobs.json`、`source_registry_watcher.py`、`repo_hygiene_reviewer.py`
事实：`source_registry_watcher（API来源监控）` 与 `repo_hygiene_reviewer_2d（仓库精简巡检）` 默认每 2 天执行一次。来源监控只检查项目记忆中声明过的官方来源；仓库精简巡检由 `coordinator` 执行，只读生成报告并创建 `repo_hygiene_candidate` 人工确认任务。
证据：`cron/jobs.json` 中两项任务均为 `kind=every`、`everyMs=172800000`；`source_registry_watcher.py` 会按传入 `--base-path` 读取 runtime 项目记忆目录；`repo_hygiene_reviewer.py` 只扫描并写报告，不删除、不提交、不推送。
最后验证：2026-04-27 相关单元测试 62 项 OK
复用建议：仓库精简候选必须先人工确认，再进入正常项目交付流水线；涉及删除、合并或修复冲突的改动仍需测试、code reviewer 和 `git_publish` 门禁。

## nofx Discord 输出与自动修复

Discord 入口默认输出中文状态卡，不只是 `failed_stage` / `next_action`：

0. 启动后先输出 `# nofx 任务执行进度`，并显示 `回答状态: 正在回复/执行中`，让 Discord channel 先看到任务已接入；运行中每 60 秒继续输出进度卡，从 `pipeline_state.json` 和 `command-runs/*.json` 读取已完成阶段、当前阶段、最近命令状态和证据目录；默认不展开 command stdout/stderr/error；`--emit-json` / `--no-chat-summary` 会关闭进度卡，保持机器可读原始输出。
1. `agent 分工与完成情况` 展示每个阶段对应 owner、状态、verdict、score 和证据文件。
2. `阶段命令状态` 从 `command-runs/*.json` 读取 stage、agent、returncode 和证据文件，默认把证据文件显示为 20 字以内中文短说明；失败时才追加脱敏摘要。
3. `阻塞原因` 展示失败阶段、stage detail、脱敏命令摘要或 artifact 摘要，不直接贴原始命令输出。
4. `自动修复判断` 记录是否回流、回流次数、风险分类和每次结果。
5. 最终 `# nofx 任务执行状态` 必须显示 `回答状态: 已回答完毕` 或 `回答状态: 未回答完毕...`。如果用户选择 `direct_run`，profile SOUL 要求直接回复末尾补 `回答状态: 已回答完毕`；长直接处理可先发 `回答状态: 正在回复/查询中`。

默认自动修复策略：

- `run_external_research`、`revise_solution`、`return_to_code_execution`、`return_to_deployment`、`fix_memory_writeback`、`fix_git_publish`：最多自动回流 2 次。
- 自动回流仍重新执行 `/home/arbops/.local/bin/smart-arb-pipeline`，每次使用 `<原 run_id>-repair<n>` 独立 run id，避免覆盖上一轮 `command-runs/*.json`。
- 自动回流会把上一轮失败证据写入上一轮失败 run 目录的 `auto_repair_context_<n>.md`，并同时通过内联 `PIPELINE_REPAIR_CONTEXT` 注入后续 Hermes stage prompt；即使文件写入失败，也不会丢失失败上下文。
- 状态卡默认展示最多 24 条 `command-runs/*.json` 状态行；需要更多可设置 `SMART_ARB_CHAT_COMMAND_LIMIT` 或传 `--chat-command-limit`。默认不展示 reviewer/tester/terminal 原始输出；排障时如需脱敏命令摘要，可设置 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` 或传 `--chat-include-command-output`；如需旧版“关键证据”列表，可设置 `SMART_ARB_CHAT_SHOW_KEY_ARTIFACTS=1` 或传 `--chat-show-key-artifacts`。profile SOUL 要求把中文状态卡分段回传到聊天频道，不允许只回 run id、失败阶段和证据目录。
- 进度卡默认 60 秒一次；需要调整可设置 `SMART_ARB_PROGRESS_INTERVAL_SECONDS` 或传 `--progress-interval-seconds`，最近阶段和最近命令条数分别由 `SMART_ARB_PROGRESS_STAGE_LIMIT` / `--progress-stage-limit`、`SMART_ARB_PROGRESS_COMMAND_LIMIT` / `--progress-command-limit` 控制。
- nofx profile 模板通过 `agent.gateway_notify_interval: 0`、`display.tool_progress: off`、`display.background_process_notifications: off` 关闭 Hermes 通用 `Still working...` 心跳、tool progress 和 `[Background process ...]` wrapper；聊天里的长任务反馈由 `smart-arb-pipeline` 中文状态卡负责。
- 如果 Hermes CLI stdout/stderr 只有 `session_id: ...`，但对应 profile session 文件已有 assistant 输出，live bridge 会从 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json` 恢复最新 assistant 内容，先做脱敏，再用于 `external_research` local-only pass 判定和状态卡输出。
- 非代码 Hermes 阶段只返回 stdout/final answer 证据，不直接编辑 `research_report.md`、`requirements_discussion.md`、`patch_summary.md` 等 pipeline artifacts；bridge 会在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，这些文件由 runner 负责持久化。
- `external_research` 如果不需要互联网检索，必须在输出里写明 `NO_EXTERNAL_LOOKUP_NEEDED`、原因和本地证据；这属于有效 research evidence，不应因缺少 browser lookup 被判失败。
- 高风险内容不自动继续：正向要求读取/输出/使用凭证、API key、token、private key、session_id，或要求启用真实交易、下单、资金转移、提现、破坏性数据操作、force push 等。`不得泄露凭证`、`不启动真实交易`、`不下单不划转` 这类纯否定式安全边界不应被当成高风险阻断；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]` 仍是 high，`No need for ...` / `Do not need ...` 这类否定式预脱敏噪音可回流；如果同一段同时出现“但需要资金操作 / but needs credentials”等正向子句，仍按高风险停人工确认。
- bridge 会在前序 artifact 注入后续 prompt 前脱敏常见 header、assignment、长 token 和 GitHub PAT / OpenAI `sk-` / Slack / HF / Google / AWS access key 等短格式 secret；排障时不要把原始 token 放进 artifact。
- 排障时优先看最终状态卡，再看原 run 与 `-repair<n>` run 各自的 `command-runs/*.json`，以及原 run 下的 `auto_repair_context_<n>.md`。

### 2026-04-28 - DeliveryPlan 目标路径过滤与异常反馈

类型：runbook
范围：`pipeline_runner.py`、`delivery_plan.json`、`solution_review`
事实：`delivery_plan.json.target_files` 不再把低信任上下文里的 workflow 控制面路径当成业务修改目标。可信顺序是：用户原始需求 / 自动修复上下文中的显式路径优先；`requirements_review`、`research_report`、`project_memory_context` 只作为低信任补充，且必须过滤 `.workflow/`、`agent-workspaces/`、`command-runs/`、`task-center/`、`.hermes/`、`.openclaw/`、`.codex/`、`auth-profiles/`、`credential-imports/`、`sessions/` 和项目记忆控制文件名。没有可靠业务文件时保持 `discovery_required=true`，由实现阶段先定位，不猜测编辑控制面。被过滤的异常候选会写入 `plan_findings.filtered_target_candidates`，并在 `solution.md` 的 `Filtered Target Candidates` 段展示 path/source/reason，避免 `solution_review` 只能看到空目标而不知道过滤原因。
证据：`pipeline_runner.py` 新增低信任路径过滤 helper、候选拒绝原因记录和 solution 展示；回归测试覆盖简单任务不再把 `API_REGISTRY.json`、`.workflow` 或 `.hermes` 放入 `target_files`，同时记录 `project_memory_control_file` / `negated_context` 等过滤原因；review context 中同时出现真实实现文件和控制面路径时只保留真实实现文件，并展示被排除候选。
最后验证：2026-04-28 18:52 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 73 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过；code-reviewer 复审通过。
复用建议：方案评审卡在敏感路径时不要放松 reviewer，先看 `target_files` 的来源和 `plan_findings.filtered_target_candidates`；如果路径来自 `project_memory_context`、runtime host 或否定上下文，只能作为检索/证据路径，不应作为修改目标。

### 2026-04-28 - DeliveryPlan 结构化方案契约

类型：runbook
范围：`pipeline_runner.py`、`smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py`
事实：`solution_package` 的事实源改为 `delivery_plan.json`，`solution.md` 只作为人工展示层。`delivery_plan.json` 使用 `delivery-plan/v1`，包含 task_type、owner、scope_slices、target_files/entry_points、out_of_scope、implementation_steps、verification_commands、release_gates、rollback_plan、human_blockers、risk_boundaries 和 plan_findings。`solution_review` 和 `code_execution` 的 prior context 都会读入 `delivery_plan.json`；方案 reviewer 必须先审结构化契约，不能只按 Markdown 文案形态放行或阻塞。
证据：`pipeline_runner.py` 新增 `compile_delivery_plan()`、`delivery_plan.json` artifact 和 `solution.md` 渲染；`smart_arb_live_bridge.py` 将 `delivery_plan.json` 注入 `solution_review`、`code_execution`、后续 verification/review/deploy/writeback/git_publish 上下文，并在非代码 Hermes stage 中剥离 `PIPELINE_DELIVERY_PLAN_FILE` 写入路径；`smart_arb_pipeline_entry.py` 将 `revise_solution` 加入自动回流白名单，并允许“do not set PRODUCTION_TRADING_ENABLED=true”这类否定式安全边界，不放行正向启用实盘。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 96 项 OK；远端 nofx 已安装 runtime 代码批次 `3a44f0b0`，`compileall` 通过，67 项定向单测 OK
复用建议：以后方案评审总是卡在“solution.md 不是实施方案”时，先看 `delivery_plan.json` 是否缺字段或 reviewer finding code，再走 `revise_solution` 回流；不要通过放松 reviewer 或手工润色 Markdown 解决。修 workflow 自身不再走同一条 `smart-arb-pipeline`，而是进入 Discord profile 的高权限工作流维护模式或外部 Codex/SSH/operator 维护 hardflow 宿主。

### 2026-04-27 - 工作流自修与未通过 review 补丁清理

类型：runbook
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、nofx Discord profile `SOUL.md`、SmartMultiPlatformArbitrage 主工作区
事实：工作流自身修复不能继续通过同一个 Discord profile 无限启动 `smart-arb-pipeline`。两个 nofx profile 模板的“工作流自修例外”已升级为“高权限工作流维护模式”：用户明确要求修 pipeline/bridge/profile/dual-review/auto-repair/git_publish/runtime installer/cron workflow 时，profile 不启动新的 `smart-arb-pipeline`，而是直接切到 `/home/arbops/projects/openclaw-hardflow-backup-20260302` 维护 hardflow 宿主、测试并按需安装 runtime；若无法启动真正独立 code-reviewer，最终状态卡必须标记 `review=pending_external`。`pipeline_runner.py` 会在 requirements review 通过后写 `resolved_requirement.md`，并让 `solution.md` 消费该 handoff。应用 code workspace patch 前会检查主工作区脏路径是否与补丁路径重叠，重叠则拒绝应用；`verification` 或 `code_review` 阻塞时对已应用到主项目目录的 patch 执行 `git apply -R` 并写入 `command-runs/rollback-<reason>.json`；如果回滚失败，pipeline 以 `failed_stage=rollback_cleanup`、`next_action=manual_cleanup_required` 阻塞，避免假装只是普通实现失败。
证据：本地测试 `python -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 共 68 项 OK；新增测试覆盖 requirement/solution artifact 保留具体用户请求、resolved requirement handoff、code review 失败回滚、verification 失败回滚、主工作区重叠脏路径拒绝应用、回滚失败升级为 manual cleanup。nofx 上旧业务漂移已保存到 `stash@{0}: pre-workflow-fix-rejected-business-drift-20260427T075431Z`，包含 `_close_position` / `execution_orchestration` 相关未通过 review 改动、`.workflow/` 和 `memory/smart-arb/`。nofx 已部署提交 `429ce994`：远端 `compileall` 与 75 项定向 unittest OK；runtime ops 命中 `Resolved Requirement`、`overlapping_dirty_paths`、`rollback_cleanup`；两个 live profile `SOUL.md` 已同步自修例外并重启，gateway 均为 `running` / Discord `connected`；SmartMulti 主工作区 clean，内控 API smoke 通过。
最后验证：2026-04-27 16:39
复用建议：遇到“修工作流本身”“不要走工作流”时，不要再让 Discord profile 调用同一条 pipeline；先确认没有活跃 `smart-arb-pipeline` run，再由高权限工作流维护模式或外部 SSH 改 hardflow 仓库、跑测试、安装 runtime。遇到 SmartMulti 主仓库残留未通过 review 的业务改动，优先 `git stash push -u -m pre-workflow-fix-rejected-business-drift-<timestamp>` 隔离，不要直接删除。

## nofx workflow 服务器级权限

早期不做细粒度权限划分时，nofx 采用高信任配置：

- Hermes profile：`approvals.mode: 'off'`
- Hermes security scan：profile 内 `security.tirith_enabled: false`
- Linux sudo：`/etc/sudoers.d/90-arbops-hermes` 允许 `arbops ALL=(ALL) NOPASSWD:ALL`

验收：

```bash
runuser -u arbops -- sudo -n true
runuser -u arbops -- sudo -n id
```

后期要收紧时，先把 sudoers 改成命令 allowlist，再重新打开 profile security scan。

## 2026-04-27 - 本机 WSL 两个 Discord agent profile 隔离

类型：runbook
范围：`/home/ubuntu/.hermes/profiles/{trend-backtest,multicore}`、tmux `trend-backtest-gateway`、tmux `multicore-gateway`、Hermes Discord adapter
事实：本机 WSL 当前为两个独立 Hermes Discord agent profile。`trend-backtest` 使用旧 Discord bot“趋势回测机器人”，只允许旧频道 `1495659215598125217`，SOUL 恢复为趋势回测专职 agent，默认 cwd `/home/ubuntu/projects/SmartTrendTracker`。`multicore` 使用新 Discord bot“多核电脑”，只允许新频道 `1498225531923988562`，SOUL 继承旧 Telegram 全局 Hermes SDLC 总协调官记忆，默认 cwd `/home/ubuntu/.hermes/profiles/multicore/workspace`。两个 profile 均设置 `DISCORD_ALLOWED_CHANNELS=<各自频道>`、`DISCORD_ALLOW_DMS=false`、`DISCORD_REQUIRE_MENTION=true`、`DISCORD_FREE_RESPONSE_CHANNELS=<各自频道>`，确保各自频道免 @，但不会跨频道抢消息，也不会在 DM 里产生双回复。
证据：2026-04-27 16:40 重启后 `trend-backtest` 的 `gateway_state=running`、PID `6470`、Discord connected as `趋势回测机器人#9621`、`/proc/6470/cwd=/home/ubuntu/projects/SmartTrendTracker`、home channel `1495659215598125217`；`multicore` 的 `gateway_state=running`、PID `6473`、Discord connected as `多核电脑#8868`、`/proc/6473/cwd=/home/ubuntu/.hermes/profiles/multicore/workspace`、home channel `1498225531923988562`。Discord API 只读核验显示旧 bot 可见 `趋势回测测试` 频道，新 bot 可见 `常规` 频道。拆分前完整备份在 `/home/ubuntu/.hermes/backups/profile-split-two-agents-20260427164001`。
最后验证：2026-04-27 16:41
复用建议：后续不要再把新“多核电脑”接到 `trend-backtest` profile。新增/调整本机 WSL agent 时，必须先明确 bot token、频道 ID、profile 名、SOUL、memory、`terminal.cwd`、`DISCORD_ALLOWED_CHANNELS` 和 `DISCORD_ALLOW_DMS`；同一个 bot token 如需多 gateway，必须先实现共享 token 锁隔离并强制频道白名单。

### 2026-04-28 - 本机 WSL multicore Codex 登录修复

类型：runbook
范围：`/home/ubuntu/.hermes/profiles/multicore/auth.json`、tmux `multicore-gateway`
事实：Hermes v0.10.0 的 OpenAI Codex 登录态按 profile 级 auth store 读取。`trend-backtest` 已登录，auth file 为 `/home/ubuntu/.hermes/profiles/trend-backtest/auth.json`；`multicore` 报 `Provider authentication failed: No Codex credentials stored` 是因为 `/home/ubuntu/.hermes/profiles/multicore/auth.json` 缺失。已从 `trend-backtest` 复制 auth store 到 `multicore`，设置 `0600`，并重启 `multicore-gateway`。
证据：修复后 `hermes -p multicore status` 显示 `OpenAI Codex ✓ logged in`，auth file 为 `/home/ubuntu/.hermes/profiles/multicore/auth.json`；`multicore-gateway` tmux session 重建于 2026-04-28 17:43，PID `5169`；`hermes -p multicore chat -q '只回复 OK，不要调用工具。'` 返回 `OK`。
最后验证：2026-04-28 17:44
复用建议：后续新增本机 WSL Hermes profile 时，不要只同步 `.env`、SOUL、cwd 和 Discord channel；还要补 profile 级 `auth.json`，否则 gateway connected 也会在实际模型调用时失败。

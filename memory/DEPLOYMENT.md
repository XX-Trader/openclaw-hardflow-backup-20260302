# DEPLOYMENT

## 2026-05-06 23:40 - nofx 安装高风险确认门禁修复批次

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`、`/home/arbops/.local/bin/smart-arb-pipeline`
事实：本机提交 `68b536a6` 和追加修复 `d236192e` 已推送到 `origin/main` 并安装到 nofx。远端 hardflow 仓库为 `HEAD=d236192`、`HEAD...origin/main=0 0`。本轮完成三项门禁修复：1. `--human-risk-confirmed` 从 backlog/Discord 入口透传到 pipeline risk gate，用户确认后的高风险策略任务不再停在 `await_human_confirmation`；2. reviewer-b 默认切到 `kimi-coding/kimi-k2.6`，避免双 reviewer 同模型伪双审；3. 风险文本清洗改为按子句处理，纯否定安全边界会剥离，但同一句里的正向真实交易/下单仍会触发高风险并在确认后继续。
证据：runtime installer 返回 `ok=true`、`changed=true`、5 个 workflow skills、22 个 ops scripts、12 个 cron jobs、`missing_sources=[]`；live profile `SOUL.md` SHA256 为 `arbitrageagent=5b2e7466a45c89c88a7950798d8d59209cb877c0e15d3787ffc7b248dd84440f`、`spreadagent=5292b57f196c549541f1def7609b3d0672f222c17586058f01e11e27b2b23d98`。远端 `compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/control-plane-ops/scripts/policy` 通过；远端定向 unittest 62 项 OK。高风险确认 echo smoke `cli-spreadagent-20260506T153935576001Z` 返回 `status=completed`、`next_action=none`、Task Center `passed`，`pre_execution_risk.json` 为 `risk_level=high`、`execution_decision=confirmed_execute`、`human_confirmation_confirmed=true`、`high_risk_reasons=enable_live_trading,place_real_order,graphify_scope_block`。已重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`，两者 `gateway_state=running` 且 Discord `connected`；内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`。
最后验证：2026-05-06 23:40
复用建议：以后 nofx 策略类真实交易/下单/划转/提现/资金任务不要删除风险扫描；应保留 high-risk 分类，人工确认后传 `--human-risk-confirmed`，并继续跑双 reviewer、测试、部署/写回/git publish 门禁。远端命令优先用 `runuser -u arbops -- /bin/sh -c`，不要用 root 直接 Git，也避免 `bash -lc` 触发 `/etc/bashrc` 的 brew 权限噪音。

## 2026-04-29 03:19 - nofx 安装 specified_agent/session-run-id 批次

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py`、`/home/arbops/.hermes/ops/task_executor_runner.py`、`/home/arbops/.hermes/ops/policy_workflow.py`、Task Center、Discord 状态卡
事实：本机代码批次 `22cecab` 已推送到 `origin/main` 并安装到 nofx runtime，后续文档/记忆提交已拉到 nofx，`HEAD...origin/main=0 0`。runtime installer 返回 `ok=true`、`changed=true`，已安装指定 agent 路线、Hermes fallback、policy 仓库路径解析、降权执行、报告目录权限修复和落库报告状态卡逻辑。`specified_agent` 路线现在会创建 Task Center `specified_agent_dispatch` 任务，分配给用户选择的 agent，调用执行器并回写 executor run id、agent session id、agent run id、session key；`coding_workflow` 路线会把真实 agent session/run id 聚合进 `command-runs`、`pipeline_state.agent_invocations`、Task Center payload 和 Discord 状态卡。
证据：远端安装态 `smart_arb_pipeline_entry.py`、`pipeline_runner.py`、`task_executor_runner.py`、`policy_workflow.py` `py_compile` 通过；远端定向 unittest：`test_smart_arb_pipeline_entry.py` 42 项 OK、`test_task_executor_output_contract.py` 6 项 OK、`test_project_delivery_runtime_installer.py` 3 项 OK。最终 live smoke 输出 `Task Center=specified-agent:tester:discord-spreadagent-spreadagent-specified-tester-20260428T191858817609Z`、`executor run id=exec-20260428_191859-571b8957`、`agent session id=task-specified-agent-tester-discord-s-aac5760c82`、`agent run id=20260429_031907_b99ea9`、`session key=agent:tester:cron:task-executor:run:task-specified-agent-tester-discord-s-aac5760c82`、`当前阶段=test-loop`、`是否完成=是`、`总状态=task=passed；report=passed`、`失败原因=none`、`回答状态=已回答完毕`。内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`。
最后验证：2026-04-29 03:19
复用建议：以后用户选择 `specified_agent` 时，完成标准不是只写 Task Center 责任标签，而是状态卡和 Task Center report 同时出现真实 `executor run id`、`agent session id`、`agent run id/session key`、完成状态和失败原因。远端安装仍按 `git pull --ff-only` -> runtime installer -> 远端定向测试 -> live smoke -> API smoke -> 文档/记忆回写执行。

## 2026-04-29 01:24 - nofx 安装 route-choice 入口硬门禁

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}/SOUL.md`、Discord gateways、内控 API
事实：本机提交 `8d952c0d` 已推送到 `origin/main`，nofx hardflow 仓库从 `7c7245a` fast-forward 到 `8d952c0`，`HEAD...origin/main=0 0` 且最终工作树 clean。拉取前远端两个 profile 模板存在上一轮手工同步残留，已保存为 `stash@{0}: pre-route-choice-deploy-20260428T172058Z`，没有 reset 或覆盖。runtime installer 返回 `ok=true`、`changed=true`，已把包含 route-choice 硬门禁的 `smart_arb_pipeline_entry.py` 安装到 `/home/arbops/.hermes/ops`。两个 live profile `SOUL.md` 已从仓库模板同步，备份后缀为 `route-choice-20260429T0124`，并重启 `hermes-discord-arbitrage` / `hermes-discord-spread`。
证据：远端 `git diff --check`、`py_compile`、`compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 均通过；远端定向 `unittest` 41 项 OK；`/home/arbops/.local/bin/smart-arb-pipeline --help` 显示 `--route-choice {coding_workflow,direct_run,requirement_discussion,specified_agent,todo_auto_candidate}`；仓库源码与安装态 `/home/arbops/.hermes/ops/smart_arb_pipeline_entry.py` SHA256 均为 `1f1ddfc728a96c89a25c6732262ee48becba3db6640d004fda48c1233cd0ee01`。两个 gateway 重启后 `arbitrageagent` PID `1374690`、`spreadagent` PID `1374779`，均为 `gateway_state=running` 且 Discord `connected`；内控 API `/health` 返回 `status=ok`、`/api/strategy/status` 返回 `running=false`。缺失 `--route-choice` 的 spreadagent smoke 只返回 `# nofx 执行链路选择` 和 `回答状态: 等待人工选择`；显式 `--route-choice direct_run --emit-json` 返回 `status=skipped`、`next_action=manual_route_not_pipeline:direct_run`；未发现活跃 `smart-arb-pipeline` / `pipeline_runner.py` 进程。
最后验证：2026-04-29 01:24
复用建议：以后“做好了没问题就部署”的 nofx hardflow 修复默认按本次闭环执行：本地测试和 staged secret scan 通过 -> commit/push -> nofx 保存远端脏改动 -> `git pull --ff-only origin main` -> runtime installer -> 远端定向测试/help/API -> 如 profile 变更则同步 live SOUL 并重启 gateway -> 缺失 route-choice 或 echo smoke -> 写回 `memory/`、`done.md`、`todo.md`。

## 2026-04-28 23:45 - nofx Discord 全任务路线选择与最高权限入口

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302/config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}/SOUL.md`、Discord gateways、SmartMultiPlatformArbitrage 安全同步
事实：已把 nofx Discord profile 规则从“普通执行类任务先选择、只读可直接处理”收紧为“所有 Discord 新任务先执行链路选择”。连接 Discord 的 profile 被定义为最高权限调度入口，负责路线选择、推荐理由、执行调度、状态回传和最终口径；只读查询、简单解释、方案讨论、监控查询、“不要走工作流”、安全仓库同步、业务执行、TODO 推进和 workflow/runtime/profile 自修都不能绕过选择。只有用户明确选择 `coding_workflow` / `todo_auto_candidate` 时才启动 `smart-arb-pipeline`；选择 `direct_run` 时由当前 Discord profile 作为最高权限 operator 直接处理，但仍受凭证、生产、资金、真实交易、force push 和删除生产数据等安全边界约束。本轮同时已按用户要求在 nofx 将 SmartMultiPlatformArbitrage 从 `df6f2c7` fast-forward 到 `00f3690a542bd65f2b16b9d8ae07c5df900c8dba`。
证据：本地 `test_nofx_profile_templates` 增加断言“所有来自 Discord 的新任务”“不要直接做只读查询或普通沟通”“Discord profile 是本入口的最高权限 operator”，并拒绝旧的只读直答口径。已同步两个仓库 profile 模板和 live `/home/arbops/.hermes/profiles/<profile>/SOUL.md`，live 备份后缀为 `all-route-choice-20260428T1545Z`；live `SOUL.md` 命中“所有来自 Discord 的新任务”“收到任何 Discord 新任务”“最高权限 operator”“回答状态: 等待人工选择”，旧规则 grep 未命中；重启后 arbitrageagent PID `1342103`、spreadagent PID `1342107`，两者 `gateway_state=running` 且 Discord `connected`。SmartMultiPlatformArbitrage 远端同步前 `## main...origin/main [behind 1]` 且工作树 clean，执行 `git fetch origin main` 与 `git pull --ff-only origin main` 后 `HEAD...origin/main=0 0`，`HEAD` 与 `origin/main` 均为 `00f3690a542bd65f2b16b9d8ae07c5df900c8dba`；内控 API `/health` 返回 `status=ok`、`/api/strategy/status` 返回 `running=false`。
最后验证：2026-04-28 23:54
复用建议：以后 Discord 里任何新任务都先看 live `SOUL.md` 是否含“收到任何 Discord 新任务”和“最高权限 operator”。若没有询问用户，优先检查 profile 模板是否同步到 `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 并重启 gateway；不要只修 `human_inbox` 或 backlog runner。

## 2026-04-28 23:15 - nofx 安装 d2e530b7 并同步高权限 profile

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}/SOUL.md`、Discord gateways、Task Center smoke
事实：本机提交 `d2e530b7` 已推送到 `origin/main`，nofx 仓库从 `17d9b36` fast-forward 到 `d2e530b`，`HEAD...origin/main=0 0` 且工作树 clean；本轮未创建 stash。runtime installer 返回 `ok=true`、`changed=true`，已安装 5 个 runtime skill、18 个 ops 脚本、12 个 cron job 和新增 policy 文件 `policy_route_selection.py`。两个 live profile `SOUL.md` 已从仓库模板同步，备份后缀为 `manual-route-20260428T151420Z`，并重启 `hermes-discord-arbitrage` / `hermes-discord-spread`。
证据：远端 `git diff --check` 通过；7 个改动脚本 `py_compile` 通过；远端 `compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/control-plane-ops/scripts/policy skills/library/todo-patrol/scripts` 通过；远端定向 `unittest` 19 项 OK；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；两个 gateway `gateway_state=running` 且 Discord `connected`；内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`；echo smoke `install-smoke-arbitrageagent-20260428T151514657470Z` 完成 15/15，Task Center `project-delivery:install-smoke-arbitrageagent-20260428T151514657470Z` 为 `passed`；cron job 数为 12、`memtidy_hits=0`、`backlog_runner_30m=1`。远端单测生成的 `file_write_audit.jsonl` 测试副作用已恢复，最终工作树 clean。
最后验证：2026-04-28 23:15
复用建议：以后 profile 模板有变化时，安装 runtime 后还必须同步 live `/home/arbops/.hermes/profiles/<profile>/SOUL.md` 并重启对应 gateway；重启前先查活跃 `smart-arb-pipeline`。复杂远端命令优先用 Paramiko 单连接，避免 PowerShell 对 `$p` 等 shell 变量做本地展开。

## 2026-04-28 19:40 - nofx 安装 17d9b369 workflow runtime

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、runtime installer、cron jobs、Discord gateways、内控 API、Task Center smoke
事实：nofx hardflow 仓库已对齐 `origin/main` 最新提交 `17d9b36`（本地完整提交 `17d9b369`），`git pull --ff-only origin main` 返回 already up to date，`HEAD...origin/main=0 0` 且工作树 clean；本轮无远端脏改动，`STASH_NAME=none`。runtime installer 返回 `ok=true`、`changed=true`，把 `project-delivery-pipeline`、`control-plane-ops`、`todo-patrol`、`log-monitor`、`task-cost-analytics` 和 18 个 ops 脚本安装到 `/home/arbops/.hermes`，cron job 数为 12，`memtidy` 仍为 0。本轮没有 profile SOUL 变更，因此未重启 Discord gateway。
证据：安装日志 `/tmp/hardflow-runtime-install-20260428T113954Z.json`；远端安装态 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` `py_compile` 通过；远端 `compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；远端定向 `unittest` 76 项 OK；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；仓库源码与 runtime 安装态 SHA256 对齐（`pipeline_runner.py=c481bf4c933a64e6e5cda7845391f2b99a42b57aa56e1136d43ceca31dd5c6cf`，`smart_arb_pipeline_entry.py=f280c5ab0e469517e12fd64bbb1d3367b22b46a92f02aa53d078b3a1e1d680f7`，`smart_arb_live_bridge.py=2443ded9914b5769f4a544d9b802c402dd274aebdb15d5529a7898d33f68ff52`）；两个 profile `gateway_state=running`；内控 API `/health` 返回 `status=ok`，`/api/strategy/status` 返回 `running=false`；echo smoke `install-smoke-arbitrageagent-20260428T114016095602Z` 完成 15/15 阶段，`next_action=none`，日志 `/tmp/hardflow-install-smoke-20260428T113954Z.json`。
最后验证：2026-04-28 19:40
复用建议：nofx 已有最新 Git 提交时也要重跑 runtime installer 和 echo smoke，不能只以 `git pull` already up to date 作为安装完成依据。PowerShell 管道会给远端 Bash stdin 带 BOM，复杂远端脚本优先用 Paramiko 或 Git for Windows ssh；仓库/runtime 操作继续通过 `runuser -u arbops` 执行。

## 2026-04-28 19:05 - nofx 安装 353f420d workflow runtime

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops/pipeline_runner.py`、runtime installer、cron jobs、Discord gateways
事实：本机 workflow 代码批次 `353f420d` 已推送到 `origin/main`，nofx hardflow 仓库已从 `195c513` fast-forward 到 `353f420`，`HEAD...origin/main=0 0` 且工作树 clean。runtime installer 返回 `ok=true`、`changed=true`，已把最新 `pipeline_runner.py` 安装到 `/home/arbops/.hermes/ops`；本轮未修改 nofx profile SOUL，因此未重启 Discord gateway。`memtidy_runner` 旧 cron 继续保持移除，当前 cron job 数为 12。
证据：远端 `python3 -m py_compile /home/arbops/.hermes/ops/pipeline_runner.py` 通过；远端 `python3 -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 73 项 OK；仓库源码与 runtime 安装态 `pipeline_runner.py` SHA256 均为 `c481bf4c933a64e6e5cda7845391f2b99a42b57aa56e1136d43ceca31dd5c6cf`；`/home/arbops/.local/bin/smart-arb-pipeline --help` 正常；cron 命中 backlog/source/repo 巡检任务且 `memtidy_hits=0`；`arbitrageagent` 与 `spreadagent` tmux 会话存在、gateway_state 均为 `running`、日志近 80 行错误数为 0；runtime dry-run smoke `/tmp/hardflow-install-smoke-20260428T110456Z` 返回 `status=completed`，`E:/repo/src/app.py` 未进入 `target_files`，并以 `external_or_runtime_absolute_path` 出现在 `filtered_target_candidates` 和 `solution.md`。
最后验证：2026-04-28 19:40
复用建议：以后远端 smoke 需要验证入口时优先使用绝对路径 `/home/arbops/.local/bin/smart-arb-pipeline`；非登录 shell 里裸 `smart-arb-pipeline` 可能不在 `PATH`，这不是 runtime installer 失败。只改 `/home/arbops/.hermes/ops` 脚本且 profile 模板无变化时，无需重启 Discord gateway。

## 2026-04-28 17:01 - nofx 普通沟通/独立协作边界同步到 live profile

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302/config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}/SOUL.md`、Discord gateways
事实：两个 nofx Discord profile 的 SOUL 已补齐三分流边界：用户明确说“不要走工作流 / 绕过工作流 / 可以绕过 / 别进 pipeline / 直接沟通 / 先讨论 / 先自己开发 / 这次不用自动流程”时，不启动 `smart-arb-pipeline`，只做直接沟通、澄清、只读查询、状态结论和方案说明；若后续要求实际改代码、安装依赖、重启、部署、提交推送或改生产配置，profile 不直接执行，必须提示外部 operator/Codex 经 SSH 处理，或由用户重新授权进入 coordinator pipeline。正常项目执行类请求仍默认进入 `smart-arb-pipeline`；工作流自身修复例外收窄为“不走工作流”且目标是 pipeline/profile/auto-repair/git_publish 等运行时问题。
证据：同步前确认 nofx 没有活跃 `smart-arb-pipeline` 进程；SFTP 备份并写入仓库模板和 live profile，备份后缀为 `SOUL.md.bak-ordinary-collab-20260428T170108`；`arbitrageagent` 模板/live SHA256 为 `70a2126b407e1c83bc0524a9a0a5eead9eaf402acad760ebaaf872e994b6c690`，`spreadagent` 为 `ed23e40fea8f8e21e76fb9e69b0b4c274459c32456a7ad023dcf9d249ddfb11f`；已重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`，两者 `gateway_state=running` 且 Discord `connected`，日志尾部未见新的 `error/exception/traceback/approval required`。
最后验证：2026-04-28 17:01
复用建议：以后用户在 Discord 里说“不走工作流”时，先判断是普通沟通/只读讨论，还是 pipeline/profile 自身修复；两者都不启动新的 pipeline run。若需要真实改代码或部署，不能由 Discord profile 直接做，必须切到外部 Codex/SSH operator 或重新进入 coordinator pipeline。

## nofx hardflow runtime

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`、`/home/arbops/.hermes/cron/jobs.json`
事实：nofx 是当前 hardflow -> SmartMultiPlatformArbitrage 项目交付工作流的先行部署服务器。SSH alias 为 `nofx`，连接配置在本机 `F:\ssh_keys\ssh_config`；SSH 默认进入 root 时，仓库和 runtime 操作必须切到 `arbops` 用户执行，避免 Git dubious ownership 和 profile 文件属主污染。
标准路径：
- hardflow 仓库：`/home/arbops/projects/openclaw-hardflow-backup-20260302`
- SmartMultiPlatformArbitrage 仓库：`/home/arbops/projects/SmartMultiPlatformArbitrage`
- Hermes runtime：`/home/arbops/.hermes`
- live 入口：`/home/arbops/.local/bin/smart-arb-pipeline`
- Task Center DB：`/home/arbops/.hermes/ops/task-center/task_center.db`
- 内控 API：tmux `smart-arb-api`，cwd `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`，监听 `127.0.0.1:18080`
标准安装命令：
```bash
python3 skills/library/project-delivery-pipeline/scripts/runtime_installer.py install \
  --runtime-home /home/arbops/.hermes \
  --runtime-name hermes \
  --repo-root /home/arbops/projects/openclaw-hardflow-backup-20260302 \
  --project-memory-dir /home/arbops/projects/SmartMultiPlatformArbitrage/memory \
  --task-center-db /home/arbops/.hermes/ops/task-center/task_center.db \
  --emit-json
```
最后验证：2026-04-28 19:05
复用建议：安装前先 `git fetch` 和 `git status --short --branch`；如有脏改动先 `git stash push -u -m pre-pull-hardflow-install-<timestamp>`，再 `git pull --ff-only origin main`。安装后至少检查 runtime installer JSON、`compileall`、定向单测、`/home/arbops/.hermes/ops` 文件、cron jobs、gateway state、内控 API smoke 和 echo smoke。

## 2026-04-28 - 安装 runtime 代码批次 3a44f0b0

类型：deploy
范围：nofx hardflow runtime、Hermes ops、cron jobs、Discord profile `SOUL.md`、Discord gateways、内控 API
事实：本机 runtime 代码批次 `3a44f0b0` 已推送到 `origin/main`；nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302` 已安装该代码批次，安装时工作树 clean，`HEAD...origin/main` 为 `0 0`。后续文档/记忆记录提交可继续 fast-forward 到 `origin/main`，不改变本批 runtime artifact。runtime installer 返回 `ok=true`、`changed=true`，已把最新 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 安装到 `/home/arbops/.hermes/ops`，且安装态 SHA256 与仓库源码一致。两个 live profile `SOUL.md` 已从仓库模板同步到 `/home/arbops/.hermes/profiles/<profile>/SOUL.md`，同步前备份为 `SOUL.md.bak-20260428T143343`，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
证据：远端 `python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol` 通过；远端定向 `unittest` 67 项 OK；`smart-arb-pipeline --help` 正常；`arbitrageagent` gateway PID `1137425`、`spreadagent` gateway PID `1137427`，两者 `gateway_state=running` 且 Discord `connected`；内控 API `127.0.0.1:18080/health` 返回 `status=ok`、`127.0.0.1:18080/api/strategy/status` 返回 `running=false`；`cron/jobs.json` 与最新安装器模板同步，profile `SOUL.md` SHA256 与仓库模板一致。
最后验证：2026-04-28 14:40
复用建议：若本仓库修改了 `config/nofx-hermes-profiles/<profile>/SOUL.md`，`runtime_installer.py install` 后还必须同步 live profile 文件并重启两个 Discord gateway；只装 `/home/arbops/.hermes/ops` 不足以让 profile 提示词更新生效。

## 2026-04-27 - 安装提交 067fbc43

类型：deploy
范围：nofx hardflow runtime、Hermes ops、cron jobs、Discord gateways、Task Center、内控 API
事实：nofx hardflow 仓库已拉到 `067fbc43`，与 `origin/main` ahead/behind 为 `0 0`，并重装 runtime。安装前已备份 `/home/arbops/.local/bin/smart-arb-pipeline`、`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 到 `/home/arbops/.hermes/ops/install/backups/pre-hardflow-install-20260427T151242Z`。安装态 `/home/arbops/.hermes/ops/pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 与仓库源码 SHA256 完全一致；`smart-arb-pipeline --help` 正常。
证据：远端 `python3 -m py_compile /home/arbops/.hermes/ops/{pipeline_runner.py,smart_arb_pipeline_entry.py,smart_arb_live_bridge.py}` 通过；`python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol` 通过；远端定向 `unittest` 98 项 OK；runtime cron 命中 `backlog_runner_30m`、`repo_hygiene_reviewer_2d`、`source_registry_watcher`；`arbitrageagent` 与 `spreadagent` gateway 均为 `running/connected`；内控 API `/health` 返回 `status=ok`、`/api/strategy/status` 返回 `running=false`；echo smoke `install-smoke-arbitrageagent-20260427T151733781612Z` 为 `status=completed`，Task Center `passed`。`smart-arb-api` 进程 cwd 核对为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 23:17
复用建议：远端命令优先使用 Git for Windows `ssh.exe` 或 Paramiko；本机 Windows 自带 `C:\Windows\System32\OpenSSH\ssh.exe` 本轮连 `ssh -V` 都返回 255 且无 stderr。通过 PowerShell 管道把多行脚本送入远端 bash 时要警惕 UTF-8 BOM，必要时改用 Paramiko stdin 执行，避免远端出现 `﻿set: command not found`。

## 2026-04-27 - 安装提交 429ce994

类型：deploy
范围：nofx hardflow runtime、Hermes ops、Discord profile `SOUL.md`、SmartMultiPlatformArbitrage 主工作区、内控 API
事实：nofx hardflow 仓库已拉到 `429ce994` 并重装 runtime，修复工作流自修循环、失败补丁回滚、requirements/solution artifact 泛化和 Hermes smoke 跨平台夹具问题。两个 live profile `SOUL.md` 已同步“工作流自修例外”，用户明确说“不要走工作流”或目标是修复 pipeline/bridge/profile/dual-review/auto-repair/git_publish 时，不再从 Discord profile 启动新的 `smart-arb-pipeline` 自修 run，而是只读诊断并提示外部 operator/Codex 通过 SSH 修复 hardflow。`arbitrageagent` 与 `spreadagent` gateway 已重启并恢复 connected。
证据：远端 `runtime_installer.py install --emit-json` 返回 `ok=true`、`changed=true`；远端 `python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；远端 75 项定向 unittest OK；`/home/arbops/.hermes/ops/pipeline_runner.py` 命中 `Resolved Requirement`、`overlapping_dirty_paths`、`rollback_cleanup`；live `SOUL.md` 命中 `auto-repair` 与 `git_publish` 自修例外；`arbitrageagent` PID `667702`、`spreadagent` PID `667704`，gateway 均为 `running` / Discord `connected`；SmartMulti 主工作区为 `## main...origin/main` clean；内控 API `/health` 返回 `status=ok`、`/api/strategy/status` 返回 `running=false`。
最后验证：2026-04-27 16:39
复用建议：后续修 hardflow runtime / Discord profile / pipeline 自身时，先走本仓库修改、测试、code-reviewer、push、nofx pull/install/smoke，再同步 live profile 并重启 gateway；不要让 nofx profile 自己调用同一个 pipeline 修自身。

## 2026-04-27 - 安装提交 578b3f0

类型：deploy
范围：nofx hardflow runtime、Hermes ops、cron jobs、Discord gateways、Task Center
事实：nofx 仓库从 `44b4dae` fast-forward 到 `578b3f0`，本次没有需要保存的本地 stash。runtime installer 返回 `ok=true`、`changed=true`，安装了 `repo_hygiene_reviewer.py`、`backlog_runner.py`、`smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py` 等 ops 脚本；runtime cron 已包含 `backlog_runner_30m（持续推进待办）`、`repo_hygiene_reviewer_2d（仓库精简巡检）`、`source_registry_watcher（API来源监控）`。
证据：远端执行 `python3 -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline skills/library/todo-patrol` 通过；定向单测 53 项 OK；`arbitrageagent` 与 `spreadagent` 的 `gateway_state=running`、`discord=connected`；`curl http://127.0.0.1:18080/health` 返回 `status=ok` 且 `strategy_running=false`；echo smoke `install-smoke-arbitrageagent-20260427T065537Z` 写入 Task Center 且状态 `passed`；受控 backlog runner smoke 任务 `todo-hardflow-install-smoke-20260427T070123Z` 被标记 `passed`，且 Task Center 中 `backlog_runner_attempt` 数量为 1。
最后验证：2026-04-27 15:01
复用建议：这次目标 TODO “将本仓库最新 runtime installer 同步到 nofx，验证 `backlog_runner_30m` 已安装并能写入 `backlog_runner_attempt`”已完成。后续真实 backlog runner 若没有推进，先查任务来源、风险、人类确认、澄清状态和 `max_attempts_per_task`。

## 2026-04-30 - multicorerouter 本机维护入口安装

类型：deploy
范围：本机 WSL `/home/ubuntu/projects/openclaw-hardflow-backup-20260302`、Hermes runtime `/home/ubuntu/.hermes`、multicorerouter profile `/home/ubuntu/.hermes/profiles/multicorerouter`。
事实：openclaw hardflow backup 仓库已克隆到 `/home/ubuntu/projects/openclaw-hardflow-backup-20260302`。新增 `multicorerouter_healthcheck.py` 只读健康检查脚本，覆盖 profile 必要路径、Discord 配置摘要、gateway 进程/screen、pipeline-runs、仓库状态和日志 tail 分类。runtime installer 已把该脚本安装到 `/home/ubuntu/.hermes/ops/multicorerouter_healthcheck.py`，并更新 `/home/ubuntu/.hermes/ops/install/project-delivery-runtime-install.json`。
证据：本地 `py_compile` 通过；`python3 tests/scripts_openclaw_ops/test_multicorerouter_healthcheck.py -v` 3 项 OK；`python3 tests/scripts_openclaw_ops/test_project_delivery_runtime_installer.py -v` 3 项 OK；安装命令 `runtime_installer.py install --runtime-home /home/ubuntu/.hermes --runtime-name hermes --repo-root /home/ubuntu/projects/openclaw-hardflow-backup-20260302 --project-memory-dir /home/ubuntu/.hermes/profiles/multicorerouter/.workflow/project-memory --task-center-db /home/ubuntu/.hermes/profiles/multicorerouter/ops/task-center/task_center.db --emit-json` 返回 `ok=true`。安装态健康检查返回总状态 OK，检查项 required_paths/config/logs/processes/pipeline_runs/repo 均 OK；日志中仅保留历史 Discord DNS warning，`hard_error_count=0`。
复用建议：以后检查本机 multicorerouter 工作流，优先运行 `/home/ubuntu/.hermes/ops/multicorerouter_healthcheck.py --format markdown --log-tail-lines 120`。如果脚本报 ATTENTION，再按输出定位 profile、日志、pipeline-runs 或 Git 状态。修改 hardflow 代码后先跑定向单测，再安装到 `/home/ubuntu/.hermes`，确认安装态脚本 smoke OK 后再提交推送。
最后验证：2026-04-30 15:38 +0800

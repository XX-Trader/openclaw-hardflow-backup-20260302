# PITFALLS

## 2026-04-27 - Discord 只显示 Still working 不是 agent 没产出

类型：pitfall
范围：nofx Discord Hermes profile、`smart_arb_pipeline_entry.py`、`pipeline_runner.py`
事实：Discord 频道只看到 `Still working...` 通常是入口在同步等待长子进程，Hermes 只能发 runtime 心跳；不代表 pipeline 内部没有阶段进展。修复后入口默认轮询 `pipeline_state.json` 和 `command-runs/*.json` 输出 `# nofx 任务执行进度`，但 profile 必须实际调用新版 entry，并把状态卡回传频道。进度卡默认只输出阶段、当前命令状态和证据文件，不允许直接贴原始 agent stdout/stderr。
证据：`run_pipeline_command()` 在 progress interval 大于 0 时用 `subprocess.Popen` 轮询 run state；`pipeline_runner.py` 在 stage command 开始前写入 running state；`render_progress_update()` 从 state 和 command reports 生成中文进度卡；测试覆盖长命令执行中 state 已落盘、进度卡展示当前阶段和最近命令状态、默认不展示 command stdout、开启调试开关后才输出脱敏摘要。
最后验证：2026-04-27 19:10
复用建议：排查同类问题按三步走：1. 确认 profile SOUL/入口命令包含 `--progress-interval-seconds` 或默认未关闭进度；2. 看 run 目录 `pipeline_state.json` 是否持续刷新；3. 看 Discord gateway/profile 是否把中文状态卡分段发回频道。不要只凭 Hermes 心跳判断卡死；也不要为了证明“还在工作”把 `[Background process ...]` 或 command stdout/stderr 原文转发到聊天频道。

## 2026-04-27 - git_publish secret scan 只应阻断真实新增密钥值

类型：pitfall
范围：`smart_arb_live_bridge.py --stage git_publish`、staged diff secret scan、nofx Discord workflow publish gate
事实：`Secret-like content detected in staged diff` 不一定代表业务代码审查失败，也不一定代表存在真实密钥；旧扫描器会把 staged diff 里的 `DASHBOARD_BASIC_PASS`、`BASIC_PASS`、`rotatable-pass`、`Authorization: Basic Auth` 或“替换为实际强密码”等环境变量名、测试假密码和文档占位误判为 secret。修复后扫描器只看新增行，并按 value 上下文判断：真实 token、cookie、Authorization payload、OAuth secret、交易所 key、`.env` 实值、高熵随机串和 PEM private key 仍阻断；环境变量名、空值、`os.getenv(...)` 空默认、测试假密码、Markdown 行内 Basic Auth / Bearer token 占位说明放行；`os.getenv(..., '真实 token')` 与 `Authorization: Bearer live-real-short-token test only` 这类真实短值不放行。阻断报告必须输出脱敏的文件、行号、规则、风险等级和片段，不能只给笼统一句 secret-like。
证据：`staged_diff_secret_findings()` 解析 staged diff 新增行，输出 `file/line/rule/risk/blocking/snippet`；`run_git_publish()` 在 `## Secret Scan Findings` 中展示脱敏 findings；测试覆盖误报放行、真 secret 阻断、docs/tests/.env.example 中短真实密钥阻断、非占位 example assignment 仍阻断、hardcoded getenv fallback secret 阻断、PEM private key marker/material 阻断、删除旧 secret 行不阻塞、阻断报告不泄露原 secret、Basic Auth/Bearer token 文档占位不阻塞、真实短 Bearer 值即使带 test/example only 仍阻断、`fix_git_publish` 遇到 secret scan high/blocking finding 不自动回流。本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过。
最后验证：2026-04-27 19:10
复用建议：后续遇到 `git_publish/fix_git_publish`，先判断失败文本是否来自 secret scan；如果是，必须定位 staged diff 的新增行和 finding rule。真实 secret/high-risk evidence 仍停人工确认。只允许调整 allowlist/context-aware scan，不允许关闭 hard block 或发布含真实 secret 的 diff。

## 2026-04-27 - 部署重启 gateway 前必须检查是否有活跃 Discord pipeline

类型：pitfall
范围：nofx `/home/arbops/.hermes/pipeline-runs`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-pipeline`
事实：Discord 里反复出现 `Still working...` 通常是 gateway 正在等待后台 `smart-arb-pipeline` 子进程完成；它不是业务结论，只是等待心跳。2026-04-27 14:43 的 `discord-spreadagent-20260427T064306800586Z` 在 14:56 阻塞于 `code_review`，随后自动 repair run `discord-spreadagent-20260427T064306800586Z-repair1` 在 15:02 阻塞于 `requirements_review`。本次 14:55 部署重启了 `hermes-discord-spread`，正好发生在该任务等待期间，因此最终阻塞状态卡可能没有回到 Discord，用户只看到多轮 `Still working...`。
证据：远端 `pipeline_state.json` 显示原 run `status=blocked failed_stage=code_review next_action=return_to_code_execution updated_at=2026-04-27T06:56:13Z`，repair1 显示 `status=blocked failed_stage=requirements_review next_action=revise_requirements updated_at=2026-04-27T07:02:32Z`；`ps` 复核时已无 `smart-arb-pipeline` 活跃进程，两个 Discord gateway 均为 `running/connected`。
最后验证：2026-04-27 15:15
复用建议：部署或重启 gateway 前，先查 `ps -ef | grep smart-arb-pipeline` 和最近 `/home/arbops/.hermes/pipeline-runs/*/pipeline_state.json`；如有 running/新近未完成 run，先等它完成或手工记录 run id，再重启。遇到用户只看到 `Still working...`，先按 run id 打开 `pipeline_state.json` 和 `command-runs/*.json`，不要把心跳当成最终失败原因。

## 2026-04-27 - nofx 上跑 live bridge deployment 相关单测后要复核 smart-arb-api cwd

类型：pitfall
范围：`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、nofx tmux `smart-arb-api`、`scripts/openclaw-ops/smart_arb_live_bridge.py`
事实：在 nofx 安装态执行 `test_smart_arb_live_bridge` 的定向单测时，deployment 相关测试会输出并演练 `tmux has-session/kill-session/new-session -s smart-arb-api` 以及 `curl` smoke。虽然本次最终核对 `smart-arb-api` 的 pane cwd 仍是 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`，但这类测试后必须显式复核，不能只看 HTTP smoke。
证据：2026-04-27 远端安装验证中，53 项定向单测 OK；随后通过 `tmux list-panes -t smart-arb-api -F '#{pane_pid}|#{pane_current_path}|#{pane_start_command}'` 确认 cwd 为 SmartMultiPlatformArbitrage 的 `智能多平台套利` 目录，进程命令为 `/home/arbops/.venvs/smart-arbitrage/bin/uvicorn api.main:app --host 127.0.0.1 --port 18080`。
最后验证：2026-04-27 14:58
复用建议：nofx 服务器上验证 live bridge 时，优先用 `compileall`、安装器测试和 echo smoke；如运行包含 deployment 的单测，测试后必须检查 tmux pane cwd、uvicorn 进程 cwd 和 `/health`，必要时按 `smart-arb-nofx-live-evidence-bridge.md` 的标准命令重启内控 API。

## 2026-04-27 - 工作流自身不能通过同一个 Discord pipeline 自修

类型：pitfall
范围：nofx `spreadagent` / `arbitrageagent` SOUL、`smart-arb-pipeline`、`pipeline_runner.py`、SmartMultiPlatformArbitrage 主工作区
事实：用户明确说“不要走工作流”“可以绕过”或“直接修工作流”时，旧 SOUL 仍把请求包装成新的 coordinator pipeline，导致 `discord-spreadagent-20260427T072912161741Z` 与后续 `discord-spreadagent-20260427T074448323797Z` 继续自修。该模式会在旧 runtime 上反复读取/生成 artifact，并可能把未通过 review 的业务补丁留在 SmartMulti 主工作区。
证据：远端进程曾显示两个 self-repair run 仍在执行；SmartMulti 工作区残留 `multi_exchange_arbitrage.py`、`execution_orchestration.py`、`tests/test_execution_orchestration.py`、`.workflow/`、`memory/smart-arb/`。本次已终止活跃 self-repair run，并把残留业务漂移保存为 `stash@{0}: pre-workflow-fix-rejected-business-drift-20260427T075431Z`。
最后验证：2026-04-27 15:54
复用建议：工作流宿主自修必须由外部 operator/Codex 经 SSH 修改 hardflow 仓库和安装态；Discord profile 只允许只读诊断并回传状态。后续若用户说“可以绕过”“不要走工作流”或看到 `Still working...` 对应的 run 目标是修 `smart-arb-pipeline` / `pipeline_runner.py` / `smart_arb_live_bridge.py`，先停止该 self-repair run，再部署修复后的 runtime。

## 2026-04-26 - P0 记忆写回不应被否定式敏感词或 session_id 输出卡住

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：run `discord-spreadagent-20260426T065131327963Z` 的 P0-1 OpenClaw 历史蒸馏已完成 external_research，但 code_execution 被安全门禁误判 high-risk；原因是报告里出现“未读取 / 不输出 token、key、cookie、OAuth、API key、credential”等否定式安全边界。随后新 run `discord-spreadagent-20260426T075133316811Z` 已完成 15 个阶段：external_research、需求讨论、code_execution、verification、code_review、deployment、acceptance、writeback 均通过。
证据：`smart_arb_pipeline_entry.py` 现在按子句处理风险扫描：纯否定式安全边界、历史文档清理记录、普通 `session_id=[REDACTED]` 和否定式预脱敏噪音可回流；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]`、真实 credential assignment、真实交易/资金/破坏性操作仍按 high 停人工确认。`smart_arb_live_bridge.py` 会在 Hermes CLI 只输出 `session_id` 时，从固定 profile session 文件恢复最新 assistant 输出并脱敏；`external_research` 的 `NO_EXTERNAL_LOOKUP_NEEDED` 可据此合成 pass。entry 还会在 memory/docs-only、no service control、no deployment、no restart 需求下跳过 deployment command，避免纯写回任务重启 `smart-arb-api`。
最后验证：2026-04-26 16:00
复用建议：遇到 P0/P1 文档或项目记忆写回任务被凭证词卡住时，先判断这些词是否处在否定句、历史清理记录或预脱敏噪音中；不要为了绕过门禁删除安全边界。若命令输出只有 `session_id`，去 profile session JSON 核对实际 assistant 输出。若需求写明不触碰服务，确认 runner 命令没有 `--deployment-command`。

## 2026-04-26 - external_research local-only 证据不应因 artifact 写入失败被判阻塞

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：最新 nofx run `discord-spreadagent-20260426T025738089361Z` 的 `external_research` 实际已经产出 local-only 研究证据，并说明不需要互联网检索；失败根因是 Hermes 阶段尝试直接编辑 `research_report.md`，触发 review diff 后 bridge 返回 `LIVE_BRIDGE_STATUS: fail`。同时失败证据里的“不得泄露凭证 / 不启动真实交易”是安全边界，不应被当作正向高风险请求。
证据：`smart_arb_live_bridge.py` 已要求非代码阶段不编辑 pipeline artifacts，只在 stdout/final answer 返回证据，并在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量；`external_research` 可输出 `NO_EXTERNAL_LOOKUP_NEEDED` 作为有效证据；`code_execution` prompt 会消费前序阶段上下文，避免 P0 任务漂移到后续 S1 策略重构，并在注入前脱敏常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack/HF/Google/AWS key。`smart_arb_pipeline_entry.py` 已把 `run_external_research` 纳入自动回流白名单，并按分句剥离纯否定式安全边界；混合句中的正向凭证/资金操作仍判高风险。测试 `test_negated_safety_terms_do_not_block_external_research_repair`、`test_positive_credential_or_trading_request_still_high_risk`、`test_negated_english_safety_terms_do_not_block_repair`、`test_redacts_short_known_secret_shapes_from_failure_evidence`、`test_non_code_hermes_env_hides_pipeline_artifact_paths`、`test_pipeline_context_redacts_sensitive_context_values`、`test_external_research_prompt_forbids_file_edits_and_allows_local_only_pass`、`test_code_execution_prompt_includes_prior_stage_context` 覆盖该行为。
最后验证：2026-04-26
复用建议：遇到 live gate 说 `run_external_research` 时，先查 `command-runs/external_research-*.json` 是否已有 local-only 证据；如果有，不要让 agent 直接改 `research_report.md`，而是通过自动回流重新生成 stdout 证据并由 runner 写入 artifact。

## 2026-04-26 - nofx Discord 状态卡不能只回 failed_stage

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：只把 `pipeline_state.json` 的 `status`、`failed_stage`、`next_action` 发回 Discord，会让用户看不到目标完成情况和具体阻塞证据。入口会读取 `command-runs/*.json`，状态卡包含 `阶段命令状态`、`阻塞原因` 和 `自动修复判断`；默认只展示 stage/agent/returncode/证据文件，避免把 reviewer/tester 原始输出刷进聊天频道。
证据：`smart_arb_pipeline_entry.py` 新增 command report 状态行、失败证据提取、高风险分类和自动回流；`smart_arb_live_bridge.py` 会读取 `PIPELINE_REPAIR_CONTEXT_FILE` / `SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE` 或内联 `PIPELINE_REPAIR_CONTEXT`，把上一轮失败证据注入后续 stage prompt；测试 `test_render_chat_summary_shows_block_reason_and_repair_decision`、`test_main_auto_repairs_low_risk_blocked_run`、`test_main_auto_repair_keeps_context_when_context_file_write_fails`、`test_main_does_not_auto_repair_high_risk_blocked_run` 覆盖该行为。
最后验证：2026-04-26 11:30
复用建议：遇到 Discord 回复“已阻塞，不能绕过 pipeline”时，先检查入口是否为新版；新版会在低/中风险下自动回流，只有凭证、真实交易、资金、破坏性数据操作等高风险才停人工确认。

## 2026-04-26 - nofx smart-arb-pipeline 旧默认值会把执行请求跑成 dry-run

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、nofx `/home/arbops/.local/bin/smart-arb-pipeline`、Discord `arbitrageagent` / `spreadagent`
事实：旧入口只有显式 `--live` 才真实执行，否则会向 runner 追加 `--dry-run`，导致 Discord 对“继续”“都依次完成”这类执行请求只生成编排证据并提示 `No product code was modified by this runner.`。已改为固定 live；`smart-arb-pipeline` 项目入口不再提供 simulation/dry-run 模式。
证据：`smart_arb_pipeline_entry.py` 不再追加 `--dry-run`，并默认注入 live bridge commands；两个 nofx profile SOUL 已改成“执行类需求默认 live pipeline”。
最后验证：2026-04-26 00:00
复用建议：遇到 Discord 回复“默认 pipeline dry-run/simulation”时，先查入口版本和 runner 命令；不要再要求用户补一句“继续真实执行”。

## 2026-04-26 - nofx 早期 workflow 权限按高信任模式配置

类型：decision
范围：nofx `/home/arbops/.hermes/profiles/*/config.yaml`、`/etc/sudoers.d/90-arbops-hermes`
事实：用户明确要求前期不做细粒度权限划分，workflow 和其他 agent 必须能直接执行服务器级修复。当前 nofx 两个 Discord profile 已关闭命令审批和 security scan，`arbops` 配置为无密码 sudo。真实交易仍由 `PRODUCTION_TRADING_ENABLED=false` 与策略手册边界约束，不在 Hermes 权限层放开。
证据：profile 模板 `config/nofx-hermes-profiles/*/config.yaml` 包含 `approvals.mode: 'off'` 与 `security.tirith_enabled: false`；nofx `/etc/sudoers.d/90-arbops-hermes` 写入 `arbops ALL=(ALL) NOPASSWD:ALL` 并通过 `visudo -cf`。
最后验证：2026-04-26 00:00
复用建议：后期收紧权限时，先把 sudoers 改成命令 allowlist，再打开 profile security scan；不要在用户要求“直接可用”阶段重新引入 approval gate。

## 2026-04-26 - nofx `/sethome` 写配置失败通常是 profile config 属主错误

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/<profile>/config.yaml`
事实：`/sethome` 需要 Hermes gateway 进程写当前 profile 的 `config.yaml`。如果文件被 root 写成 `root:root` 且 `0600`，`arbops` 用户运行的 gateway 会无法写入并返回 `[Errno 13]`。已将两个 Discord profile 的 `config.yaml` 修回 `arbops:arbops` + `0600`。
证据：远端 stat 曾显示 `spreadagent/config.yaml` 和 `arbitrageagent/config.yaml` 均为 `root:root 0600`，而 profile 目录与 `.env` 为 `arbops:arbops`；修复后以 `arbops` 身份完成写入 smoke。
最后验证：2026-04-26 00:00
复用建议：通过 root/SFTP 改 profile 配置后必须立即 `chown arbops:arbops /home/arbops/.hermes/profiles/<profile>/config.yaml`；不要只修 `.env`。

## 2026-04-25 - nofx live bridge 容易被误判为真实多 agent 分发

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、nofx Hermes runtime
事实：`smart-arb-pipeline --live` 当前仍默认注入 `smart_arb_live_bridge.py`，但已经补上 per-agent workspace 隔离：`web-agent`、`project-agent`、`reviewer`、`backend-dev`、`tester` 等 owner 会有独立 workspace 记录，`code_execution` workspace diff 会回流主项目并注入后续验收 workspace。Task Center 的 `agent_id` / `module_communications` 仍是责任标签与状态机镜像，不等于已经真实启动了多个宿主 native agent。
证据：`pipeline_runner.py` 固定使用 Git worktree、`agent-workspaces/manifest.json`、`PIPELINE_AGENT_REPO_DIR` 注入和 `command-runs/code_execution-1.patch`；`smart_arb_pipeline_entry.py` 不再暴露 `--agent-workspace-mode`；`smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为阶段项目目录；nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 的 Task Center 命令阶段为 `runtime-agent-workspace` / `isolated-agent-workspace`。
最后验证：2026-04-25 22:06
复用建议：如果用户问“为什么任务没有转给其他 agent”，先区分三层：责任标签、独立 workspace、宿主 native session。现在 workspace 层已落地；若要宣称 native fan-out，仍必须检查 command evidence 中是否存在独立 session/run id。

## 2026-04-25 - nofx SSH 并发采样可能触发临时拒绝

类型：pitfall
范围：nofx 远程巡检、PowerShell 原生 `ssh`、Paramiko
事实：本轮先用 PowerShell 原生 `ssh` 并发采样时空退，随后 Paramiko 曾成功一次，再出现 `Not allowed at this time`、`Error reading SSH protocol banner` 和连接重置。该状态下不能把“连不上 SSH”误认为 nofx runtime 自身异常。
证据：本地 socket 连接 22 端口返回 `Not allowed at this time`；Paramiko 报 `Authentication failed: transport shut down or saw EOF`、`No existing session`、`Error reading SSH protocol banner`。
最后验证：2026-04-25 19:05
复用建议：nofx 巡检优先单连接、低频重试；避免一次性并发多个 SSH 会话。若需要多项采样，应在同一连接内顺序执行，或等待服务端限制窗口恢复。

## 2026-04-25 - nofx Hermes profile SOUL 乱码导致 coordinator 约束变弱

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/SOUL.md`、`/home/arbops/.hermes/profiles/spreadagent/SOUL.md`
事实：远程两个 profile 的 `SOUL.md` 主体曾变成问号乱码，只有后追加的 `Pipeline Boundary Update` 可读。19:10 的 `spreadagent` Discord 会话收到“都依次完成吧”后没有创建新的 `smart-arb-pipeline` run，而是在 profile 会话里直接规划任务，说明 coordinator pipeline 约束没有稳定生效。
证据：远程读取 `SOUL.md` 首段显示 `# ???????`；`/home/arbops/.hermes/profiles/spreadagent/sessions/session_20260425_191017_e8d87b.json` 为 Discord 会话，用户消息为“都依次完成吧”，但 `/home/arbops/.hermes/pipeline-runs` 当时最新仍是 18:00 smoke run。
最后验证：2026-04-25 19:20
复用建议：profile 提示词不要用 PowerShell 内联中文写远程文件；应从仓库 UTF-8 模板按字节上传。更新后必须重启对应 tmux gateway，并确认 `gateway_state=running`、`discord=connected`。

## 2026-04-25 - nofx Command Approval Required 不能只改全局 Hermes 配置

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/config.yaml`、`/home/arbops/.hermes/profiles/spreadagent/config.yaml`、本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml`
事实：本机 WSL 虽然全局 `/home/ubuntu/.hermes/config.yaml` 仍是 `approvals.mode: manual`，但 live `trend-backtest` profile 是顶层 `approvals.mode: 'off'`，所以实际不会弹命令审批。nofx 没有 `/home/arbops/.hermes/config.yaml`，两个 Discord profile 原先也没有顶层 `approvals` 配置，遇到 Hermes security scan 的 `Command Approval Required` 仍会进入人工审批。已在 nofx 两个 profile 中补齐顶层 `approvals.mode: 'off'`，并重启 `hermes-discord-arbitrage`、`hermes-discord-spread`。
证据：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml` 第 7-8 行为 `approvals.mode: 'off'`；nofx 两个 profile 配置已验证 `approvals_mode_off=True`；`gateway_state.json` 显示 `arbitrageagent` 为 `running updated_at=2026-04-25T14:56:14.570586+00:00`，`spreadagent` 为 `running updated_at=2026-04-25T15:01:19.106822+00:00`；日志尾部未发现新的 `Command Approval Required` / `confusable` 记录，只有 22:48 的历史 Discord button approval。
最后验证：2026-04-25 23:03
复用建议：排查 nofx Hermes 审批问题时，先看 profile 级 `config.yaml`，不要用全局 `~/.hermes/config.yaml` 做结论。改配置后必须重启对应 tmux gateway；旧会话里已经生成的审批卡片不代表新配置未生效，后续新命令才会按 profile 配置执行。

## 2026-04-25 - nofx live verification 不应默认跑全量 unittest discover

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、nofx `/home/arbops/.hermes/pipeline-runs/discord-spreadagent-20260425T145231185916Z`
事实：机器人回复里的 `external_research` 阻塞不是最新真实状态；真实最新 run `discord-spreadagent-20260425T145231185916Z` 已完成 `external_research`、`requirements_discussion`、`code_execution` 三段，真正卡住的是 `verification`：默认 `/home/arbops/.venvs/smart-arbitrage/bin/python -m unittest discover -s tests -p 'test_*.py'` 长时间停在 async/zmq 相关等待。已把 live 默认验证收敛为 `git diff --check` 与 `compileall -q scripts strategy_runtime`，并新增 `--verification-command-timeout-seconds` 显式参数。
证据：旧 run `pipeline_state.json` 为 `status=blocked failed_stage=verification next_action=return_to_code_execution`；`verification_report.md` 显示 unittest 子进程被终止后 returncode=-15，stderr 含 `asyncio.exceptions.CancelledError` 与 zmq future；安装态真实 verification smoke 显示 `git diff --check` 和 `/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime` 均 returncode 0；echo live smoke `codex-spreadagent-20260425T154609125415Z` 15 阶段 completed，`verification-1.json` 命令包含 `--verification-command-timeout-seconds 180`。
最后验证：2026-04-25 23:46
复用建议：Discord live pipeline 只跑有限安全验证；全量 unittest 放到 CI 或人工排障。遇到“卡在 external_research”的机器人回复，先查最新 run 目录和 `ps`，不要相信旧 run_id 或错误路径。

## 2026-04-25 - root 写回 profile .env 会导致 Hermes gateway 立即退出

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/.env`、`/home/arbops/.hermes/profiles/spreadagent/.env`、`start-gateway.sh`
事实：用 root/SFTP 修改 profile `.env` 后，如果权限变成 root:root 且 `0600`，`arbops` 启动的 Hermes gateway 会因无法读取 `.env` 立即退出，tmux 会话看起来创建成功但很快消失。已修正两个 `.env` 为 `arbops:arbops` + `0600`，并用 profile `start-gateway.sh` 加载 `.env` 启动。
证据：两个 profile 的 `gateway.log` 曾出现 `PermissionError: [Errno 13] Permission denied: '/home/arbops/.hermes/profiles/<profile>/.env'`；修正属主后 `hermes-discord-arbitrage`、`hermes-discord-spread` 均在 tmux 中存在，`gateway_state.json` 显示 `running updated_at=2026-04-25T15:45:14/15Z`。
最后验证：2026-04-25 23:45
复用建议：profile `.env` 含凭证，不打印内容；只检查属主和 mode。通过 root 修改后必须 `chown arbops:arbops`，然后再重启对应 tmux gateway。
## 2026-04-27 - Hermes Discord connected 但频道发言 403

类型：pitfall
范围：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest`、Discord bot “多核电脑”、`本地项目 / #常规`
事实：`gateway_state.json` 显示 Discord `connected` 只能证明 bot token 有效且 gateway websocket 已连上；它不证明 bot 对目标频道有发送消息权限。2026-04-27 将 `trend-backtest` 接到新 bot 后，Hermes 日志显示 `[Discord] Connected as 多核电脑#8868`，但用 bot token 向 `1498225531923988562` 发消息返回 `403 Forbidden`。
证据：`hermes -p trend-backtest status` 显示 Discord home channel 为 `1498225531923988562` 且 gateway running；`POST https://discord.com/api/v10/channels/1498225531923988562/messages` 返回 HTTP 403。
最后验证：2026-04-27 16:03
复用建议：遇到“online/connected 但聊天不回”时不要只查 `hermes status`。先查 channel 发送权限，再查 Message Content Intent。免 @ 最小安全配置是 `require_mention: true` + `free_response_channels=<目标频道>`，不要为了免 @ 直接把 `require_mention=false` 放到多频道 guild，除非这是专用单频道服务器。

## 2026-04-27 - 替代 TG 入口不能沿用专项 profile SOUL

类型：pitfall
范围：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest`、旧 TG 全局 Hermes、Discord “多核电脑”入口
事实：把新 Discord bot 接到现有 `trend-backtest` profile 后，若只替换 token 和频道，bot 会继续加载该 profile 原有“趋势回测机器人 SOUL”，从而在新频道开场自称趋势回测 agent，并固定宣称默认工作目录 `/home/ubuntu/projects/SmartTrendTracker`。这与“替代之前 TG 频道、沿用 TG 记忆”的目标冲突。最终修正不是继续复用 `trend-backtest`，而是拆出独立 `multicore` profile，让 `trend-backtest` 回到旧趋势回测 bot/旧频道，让 `multicore` 承接新多核电脑 bot/新频道。
证据：2026-04-27 用户在 Discord 看到回复“我是趋势回测 agent，默认工作目录是 /home/ubuntu/projects/SmartTrendTracker”；随后核对发现全局 `~/.hermes/SOUL.md` 是旧 Telegram 的 Hermes SDLC 总协调官提示词，全局 `~/.hermes/memories/MEMORY.md` 是旧 TG 记忆，而 profile `SOUL.md` 是趋势回测专项提示词。
最后验证：2026-04-27 16:41
复用建议：做“渠道替换”时必须迁移 identity、SOUL、memory、session 四件套；只改 platform token 会造成入口身份漂移。如果原 profile 还代表另一个 agent，不要覆盖它，应该新建 profile 并把旧 profile 恢复到原 bot、原频道、原 cwd。

## 2026-04-27 - 两个 Discord agent 不能共用未隔离的 gateway

类型：pitfall
范围：本机 WSL Hermes Discord gateway、`/home/ubuntu/.hermes/profiles/{trend-backtest,multicore}`、`gateway/platforms/discord.py`
事实：同一个 Discord bot token 默认只能被一个 gateway 进程持有；即使不同 profile 绑定不同频道，如果没有频道白名单和 DM 禁用，也可能出现抢消息或 DM 双回复。当前本机两个 agent 使用不同 bot token，并各自设置 `DISCORD_ALLOWED_CHANNELS`；Hermes Discord adapter 还补了受控开关：`DISCORD_ALLOW_SHARED_BOT_TOKEN=true` 只有在同时设置 `DISCORD_ALLOWED_CHANNELS` 时才允许共享 token 分锁，`DISCORD_ALLOW_DMS=false` 会让 profile 忽略 DM。
证据：`gateway/platforms/discord.py` 在 `connect()` 中将共享 token 锁身份收敛为 `token:allowed_channels`，缺少 `DISCORD_ALLOWED_CHANNELS` 时返回 fatal；`_handle_message()` 在 DM 分支优先检查 `DISCORD_ALLOW_DMS=false` 并丢弃。相关回归测试 `test_discord_connect.py`、`test_discord_channel_controls.py`、`test_discord_reply_mode.py` 共 50 项通过。
最后验证：2026-04-27 16:41
复用建议：以后做多 Discord agent，不要只靠“频道不同”作为隔离。至少要有 profile 独立、session 独立、cwd 独立、`allowed_channels` 白名单、DM 策略；如果共享同一个 bot token，还必须有锁身份隔离。

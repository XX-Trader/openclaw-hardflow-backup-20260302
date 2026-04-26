# PITFALLS

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
事实：只把 `pipeline_state.json` 的 `status`、`failed_stage`、`next_action` 发回 Discord，会让用户看不到各 agent 实际输出、目标完成情况和具体阻塞证据。入口已改为读取 `command-runs/*.json`，状态卡包含 `agent 输出摘要`、`阻塞原因` 和 `自动修复判断`。
证据：`smart_arb_pipeline_entry.py` 新增 command report 摘要、失败证据提取、高风险分类和自动回流；`smart_arb_live_bridge.py` 会读取 `PIPELINE_REPAIR_CONTEXT_FILE` / `SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE` 或内联 `PIPELINE_REPAIR_CONTEXT`，把上一轮失败证据注入后续 stage prompt；测试 `test_render_chat_summary_shows_block_reason_and_repair_decision`、`test_main_auto_repairs_low_risk_blocked_run`、`test_main_auto_repair_keeps_context_when_context_file_write_fails`、`test_main_does_not_auto_repair_high_risk_blocked_run` 覆盖该行为。
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

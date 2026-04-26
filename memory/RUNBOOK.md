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

排障顺序：

1. 查 `tmux ls`，确认 `hermes-tg`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-api` 是否存在。
2. 查 Hermes profile gateway state，确认 Discord 是否 connected。
3. 查最近 `pipeline_state.json` 和 `command-runs/*.json`，确认是否进入 live pipeline，以及每个阶段实际 command。
4. 查 `agent-workspaces/manifest.json`，确认每个阶段 owner 是否有独立 workspace。
5. 查 `command-runs/code_execution-1.patch` 是否生成并成功应用回主项目目录。
6. 查 `smart_arb_pipeline_entry.py` 和 `smart_arb_live_bridge.py` 的安装态版本，确认是否与本仓库 HEAD 对齐。
7. 若用户关心“是否转发到其他 agent”，必须检查是否有独立 agent session/run id，而不是只看 Task Center 的 `agent_id` 字段。

注意：当前 live bridge 已证明 workspace 隔离和阶段命令执行；2026-04-25 22:06 的 nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 里，命令阶段均记录为 `runtime-agent-workspace` / `isolated-agent-workspace`。native 多 agent fan-out 仍需以独立宿主 session/run id 为准。

## nofx hardflow 拉取与安装记录

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

## nofx Discord 输出与自动修复

Discord 入口默认输出中文状态卡，不只是 `failed_stage` / `next_action`：

1. `agent 分工与完成情况` 展示每个阶段对应 owner、状态、verdict、score 和证据文件。
2. `agent 输出摘要` 从 `command-runs/*.json` 读取 stdout/stderr/error，展示每个 stage command 的 agent、returncode 和关键输出。
3. `阻塞原因` 展示失败阶段、stage detail、命令输出和 artifact 摘要。
4. `自动修复判断` 记录是否回流、回流次数、风险分类和每次结果。

默认自动修复策略：

- `run_external_research`、`return_to_code_execution`、`return_to_deployment`、`fix_memory_writeback`：最多自动回流 2 次。
- 自动回流仍重新执行 `/home/arbops/.local/bin/smart-arb-pipeline`，每次使用 `<原 run_id>-repair<n>` 独立 run id，避免覆盖上一轮 `command-runs/*.json`。
- 自动回流会把上一轮失败证据写入上一轮失败 run 目录的 `auto_repair_context_<n>.md`，并同时通过内联 `PIPELINE_REPAIR_CONTEXT` 注入后续 Hermes stage prompt；即使文件写入失败，也不会丢失失败上下文。
- 状态卡默认展开最多 24 条 `command-runs/*.json` 摘要；需要更多可设置 `SMART_ARB_CHAT_COMMAND_LIMIT` 或传 `--chat-command-limit`。profile SOUL 要求把完整中文状态卡分段回传到聊天频道，不允许只回 run id、失败阶段和证据目录。
- 如果 Hermes CLI stdout/stderr 只有 `session_id: ...`，但对应 profile session 文件已有 assistant 输出，live bridge 会从 `/home/arbops/.hermes/profiles/<profile>/sessions/session_<id>.json` 恢复最新 assistant 内容，先做脱敏，再用于 `external_research` local-only pass 判定和状态卡输出。
- 非代码 Hermes 阶段只返回 stdout/final answer 证据，不直接编辑 `research_report.md`、`requirements_discussion.md`、`patch_summary.md` 等 pipeline artifacts；bridge 会在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量，这些文件由 runner 负责持久化。
- `external_research` 如果不需要互联网检索，必须在输出里写明 `NO_EXTERNAL_LOOKUP_NEEDED`、原因和本地证据；这属于有效 research evidence，不应因缺少 browser lookup 被判失败。
- 高风险内容不自动继续：正向要求读取/输出/使用凭证、API key、token、private key、session_id，或要求启用真实交易、下单、资金转移、提现、破坏性数据操作、force push 等。`不得泄露凭证`、`不启动真实交易`、`不下单不划转` 这类纯否定式安全边界不应被当成高风险阻断；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]` 仍是 high，`No need for ...` / `Do not need ...` 这类否定式预脱敏噪音可回流；如果同一段同时出现“但需要资金操作 / but needs credentials”等正向子句，仍按高风险停人工确认。
- bridge 会在前序 artifact 注入后续 prompt 前脱敏常见 header、assignment、长 token 和 GitHub PAT / OpenAI `sk-` / Slack / HF / Google / AWS access key 等短格式 secret；排障时不要把原始 token 放进 artifact。
- 排障时优先看最终状态卡，再看原 run 与 `-repair<n>` run 各自的 `command-runs/*.json`，以及原 run 下的 `auto_repair_context_<n>.md`。

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

# RUNBOOK

## nofx 项目交付入口排障

常用事实源：

- nofx hardflow 仓库：`/home/arbops/projects/openclaw-hardflow-backup-20260302`
- nofx SmartMultiPlatformArbitrage 仓库：`/home/arbops/projects/SmartMultiPlatformArbitrage`
- Hermes runtime：`/home/arbops/.hermes`
- 标准入口：`/home/arbops/.local/bin/smart-arb-pipeline`
- pipeline runs：`/home/arbops/.hermes/pipeline-runs`
- Task Center DB：`/home/arbops/.hermes/ops/task-center/task_center.db`
- nofx profile SOUL 模板：`config/nofx-hermes-profiles/<profile>/SOUL.md`

排障顺序：

1. 查 `tmux ls`，确认 `hermes-tg`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-api` 是否存在。
2. 查 Hermes profile gateway state，确认 Discord 是否 connected。
3. 查最近 `pipeline_state.json` 和 `command-runs/*.json`，确认是否进入 `smart-arb-pipeline --live`，以及每个阶段实际 command。
4. 查 `agent-workspaces/manifest.json`，确认每个阶段 owner 是否有独立 workspace。
5. 查 `command-runs/code_execution-1.patch` 是否生成并成功应用回主项目目录。
6. 查 `smart_arb_pipeline_entry.py` 和 `smart_arb_live_bridge.py` 的安装态版本，确认是否与本仓库 HEAD 对齐。
7. 若用户关心“是否转发到其他 agent”，必须检查是否有独立 agent session/run id，而不是只看 Task Center 的 `agent_id` 字段。

注意：当前 live bridge 已证明 workspace 隔离和阶段命令执行；2026-04-25 22:06 的 nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 里，命令阶段均记录为 `runtime-agent-workspace` / `isolated-agent-workspace`。native 多 agent fan-out 仍需以独立宿主 session/run id 为准。

## nofx profile SOUL 刷新

本仓库维护两个 UTF-8 模板：

- `config/nofx-hermes-profiles/arbitrageagent/SOUL.md`
- `config/nofx-hermes-profiles/spreadagent/SOUL.md`

刷新步骤：

1. 上传模板到 `/home/arbops/.hermes/profiles/<profile>/SOUL.md`，上传前备份原文件。
2. 避免通过 PowerShell 内联中文重写远程文件；用 SFTP 或 scp 按字节上传。
3. 确认 `SOUL.md` 内入口是绝对路径 `/home/arbops/.local/bin/smart-arb-pipeline`，不要依赖 gateway 的 `PATH`。
4. 重启 tmux 会话：
   - `hermes-discord-arbitrage` 通过 `/home/arbops/.hermes/profiles/arbitrageagent/start-gateway.sh`
   - `hermes-discord-spread` 通过 `/home/arbops/.hermes/profiles/spreadagent/start-gateway.sh`
5. profile `.env` 必须保持 `arbops:arbops` 且 `0600`；如果通过 root/SFTP 写回 `.env`，必须再 `chown arbops:arbops`，否则 gateway 会因读不到 `.env` 立即退出。
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

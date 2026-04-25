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
3. 重启 tmux 会话：
   - `hermes-discord-arbitrage`
   - `hermes-discord-spread`
4. 验证：
   - `tmux ls`
   - `cat /home/arbops/.hermes/profiles/<profile>/gateway_state.json`
   - 读取 `SOUL.md` 前 10 行确认中文不是问号乱码。

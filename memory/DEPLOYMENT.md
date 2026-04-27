# DEPLOYMENT

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
最后验证：2026-04-27 16:39
复用建议：安装前先 `git fetch` 和 `git status --short --branch`；如有脏改动先 `git stash push -u -m pre-pull-hardflow-install-<timestamp>`，再 `git pull --ff-only origin main`。安装后至少检查 runtime installer JSON、`compileall`、定向单测、`/home/arbops/.hermes/ops` 文件、cron jobs、gateway state、内控 API smoke 和 echo smoke。

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

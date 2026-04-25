# PITFALLS

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

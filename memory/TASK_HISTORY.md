# TASK_HISTORY

## 2026-04-27 - nofx 工作流自修闭环修复

类型：task
范围：`pipeline_runner.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、nofx SmartMultiPlatformArbitrage 工作区
事实：修复 nofx Discord 工作流自修循环与未验收业务补丁残留问题。`requirements.md` 保留本轮用户具体需求、禁止范围和安全边界，不再泛化成“构建端到端 pipeline”模板；requirements review 通过后新增 `resolved_requirement.md` 作为下游 handoff，`solution.md` 消费该 handoff；主工作区脏路径与 code patch 路径重叠时拒绝应用，`verification` 或 `code_review` 阻塞时会反向撤回已应用到主项目目录的 code workspace patch 并记录 rollback artifact，回滚失败会升级为 `rollback_cleanup/manual_cleanup_required`；两个 profile SOUL 增加工作流自修例外，避免“修 pipeline 本身”请求再次进入同一个 pipeline。远端 SmartMulti 主工作区中 `_close_position` / `execution_orchestration` 相关未通过 review 的业务漂移已隔离到 stash。
证据：本地 `python -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 共 68 项 OK；`python -m unittest tests.scripts_openclaw_ops.test_project_delivery_runtime_installer tests.scripts_openclaw_ops.test_project_delivery_hermes_profile_smoke tests.scripts_openclaw_ops.test_active_agent_registry` 共 7 项 OK；本地合并定向测试 75 项 OK；`python -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；nofx SmartMulti `git status --short --branch` 回到 `## main...origin/main`，旧业务漂移 stash 为 `pre-workflow-fix-rejected-business-drift-20260427T075431Z`。nofx hardflow 已拉到 `429ce994` 并重装 runtime；远端 `compileall` 通过，75 项定向 unittest OK；live profile `SOUL.md` 已同步自修例外并重启 gateway，`arbitrageagent` / `spreadagent` 均为 `running` / Discord `connected`；内控 API `/health` 与 `/api/strategy/status` smoke 通过。
最后验证：2026-04-27 16:39
复用建议：后续 workflow runtime 自修先走外部 SSH/operator，不让 Discord profile 自己改自身；业务 patch 只有 verification/code_review 通过后才允许进入发布链路，失败时应检查 `rollback_*` artifact 和主工作区状态。

## 2026-04-27 - nofx 拉取并安装最新 hardflow runtime

类型：deploy
范围：`/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、`/home/arbops/.hermes/profiles/{arbitrageagent,spreadagent}`、Task Center
事实：nofx hardflow 仓库已从 `44b4dae` fast-forward 到 `578b3f0`；本次远端工作区无脏改动，未创建 stash。runtime installer 已把最新项目交付 runtime 安装到 `/home/arbops/.hermes`，包括 `backlog_runner.py`、`repo_hygiene_reviewer.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 和 cron jobs。`arbitrageagent` / `spreadagent` gateway 已重启并恢复 connected。
证据：runtime installer JSON 返回 `ok=true`、`changed=true`；`compileall` 通过；定向单测 53 项 OK；cron 检查命中 `backlog_runner_30m`、`repo_hygiene_reviewer_2d`、`source_registry_watcher`；内控 API `/health` 与 `/api/strategy/status` smoke 通过；echo smoke `install-smoke-arbitrageagent-20260427T065537Z` 写入 Task Center 且状态 `passed`；受控 backlog runner smoke 任务 `todo-hardflow-install-smoke-20260427T070123Z` 被标记 `passed`，并写入 1 条 `backlog_runner_attempt`；`smart-arb-api` 最终 cwd 核对为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 15:01
复用建议：以后用户说“进入服务器安装最新代码”时，默认按 `DEPLOYMENT.md` 的 nofx 安装命令执行，并在测试后复核 gateway state、cron jobs、Task Center smoke 和 `smart-arb-api` cwd。

## 2026-04-27 - Task Center 待办持续推进 runner

类型：task
范围：`scripts/openclaw-ops/backlog_runner.py`、`cron/jobs.json`、`skills/library/project-delivery-pipeline/scripts/runtime_installer.py`、`tests/scripts_openclaw_ops/test_backlog_runner.py`
事实：新增 `backlog_runner.py`，将 Task Center 中可安全执行的 backlog 转交给 runtime 内安装的 pipeline 入口继续推进；默认每 30 分钟由 `backlog_runner_30m` 最多推进 1 个低风险、无需人工确认、无需澄清任务。pending 任务仅允许指定来源或 `todo-*`；failed 任务必须显式 `--include-failed`，且 `next_action` 在允许列表内。高风险、需确认、需澄清、人工升级任务不自动执行。runtime installer 已同步安装该脚本，cron `--pipeline-command` 指向 runtime `ops/smart_arb_pipeline_entry.py`，避免自定义 runtime home 下路径失效。
证据：新增测试覆盖 dry-run 只选择安全任务、真实执行时调用 pipeline 并把任务标记 passed、pipeline 启动失败不会卡在 running、安装器安装 `ops/backlog_runner.py`、自定义 runtime home 下 backlog cron payload 指向 runtime entry；相关测试 9 项 OK。
最后验证：2026-04-27 12:00
复用建议：该 runner 是“持续推进”入口，不是人工确认替代品。若 backlog 没有推进，先看任务是否被安全门禁跳过，再看是否达到 `max_attempts_per_task`，最后查 pipeline run id 对应的 `pipeline_state.json`。

## 2026-04-27 - 工作流合规收敛：风险分流、9 owner、双 reviewer

类型：task
范围：`deadline_to_task_bridge.py`、`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`openclaw.json`、`openclaw/openclaw.json`、`cron/jobs.json`
事实：到期 TODO 不再全部转人工确认；低风险到期项创建 `risk_level=low`、`need_human_confirm=false`、`action=dispatch_pipeline`、`assignee=coordinator` 的候选任务，由 backlog runner 继续推进；高风险、生产、部署、资金、凭证、删除等仍创建 `await_human_confirm` 人工候选。active agent 配置收敛为 9 个 workflow owner，cron 只挂 `coordinator/project-agent`。需求、方案、代码审查都必须有两条不同命令、不同 `reviewer_role`（`reviewer-a`/`reviewer-b`）的 reviewer command report，且 verdict 全部匹配才放行。
证据：相关测试覆盖低风险/高风险 TODO 分流、单 reviewer 阻塞、重复 reviewer role 阻塞、重复 command 阻塞、两 reviewer 放行、Hermes smoke 双 reviewer 同步、live bridge 三类 review verdict、entry 默认注入 reviewer-a/reviewer-b、active registry 与 cron owner 合规。
最后验证：2026-04-27
复用建议：后续回答“是不是 9 个 agent、是否双 AI 审核、低风险 TODO 是否自动推进”时，以 active registry 测试、pipeline command artifacts（含 `reviewer_role`）和 Task Center payload 为准，不再沿用旧 cron owner 口径。

## 2026-04-27 - nofx agent 口径与模型快照修正

类型：task
范围：`agents/`、`openclaw.json`、`openclaw/openclaw.json`、`memory/INDEX.md`、`memory/RUNBOOK.md`、`docs/核心主工作流/项目交付优先工作流/`、`docs/基础设施/多Agent体系/README.md`、`todo.md`
事实：修正关于 nofx “14 个常驻 agent”的误导口径。当前 nofx live 入口只有两个 Hermes Discord profile：`arbitrageagent` 与 `spreadagent`，两者模型均为 `openai-codex/gpt-5.5` 且 gateway running；真正执行链路是 `/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`。本仓库 active workflow owner 严格为 9 个：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`，它们是阶段 owner / workspace / Task Center 标签，不是独立常驻 agent；前端/UI/页面/交互类代码执行可通过 `--code-agent frontend-dev` 或入口自动推断切到 `frontend-dev` workspace。定时任务层只挂 `coordinator/project-agent`，`ops-agent/optimization-agent` 已退出 active 配置。2026-03 的 14 Agent 文档保留为历史 OpenClaw 注册表快照，不再作为 nofx 运行态结论；`git_publish` 是 `coordinator` 负责的发布门禁，不再单独建 `git-master` agent。
证据：2026-04-27 nofx 远程核对 profile config、gateway_state、tmux 会话、缺失常驻 agent 目录、cron/jobs 和 hardflow 仓库 HEAD；本地 `openclaw.json`、`openclaw/openclaw.json`、pipeline runner、entry、live bridge 与文档已统一为 2 个入口 profile、9 个 active workflow owner、2 类 cron owner；新增 active registry 测试保证配置和 cron 不再引用 `ops-agent/optimization-agent`。文档已同步标注当前 server runtime 仍在 `44b4dae`，尚未安装本仓库最新运行态。
最后验证：2026-04-27 11:14
复用建议：后续沟通一律使用“四层口径”：入口 profile、workflow runner、阶段 owner 标签、cron 责任标签；模型只对真实 profile 或明确 provider command 声明，不把标签误写成独立模型。

## 2026-04-27 - 2 天仓库精简巡检与 Git 发布门禁

类型：task
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、`source_registry_watcher.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：新增 `repo_hygiene_reviewer.py` 只读仓库精简巡检，默认每 2 天由 `coordinator` 执行；`source_registry_watcher` 频率也调整为每 2 天并修复 `--base-path` 生效；项目交付流水线新增 `git_publish` 可选阶段，默认 live entry 会注入该命令，提交说明必须中文且脱敏，失败回流 `fix_git_publish`；发布输入会优先采用 `memory_writeback` 隔离工作区 patch，避免漏掉文档/记忆写回变更，并禁止夹带 `command_cwd` 未验收脏改动。本轮修复仓库精简脚本对内联冲突标记示例的误报，并删除已跟踪的 `cron/jobs.json.bak.20260422220950` 备份文件。
证据：相关测试覆盖 pipeline git_publish 成功/失败、写回后 patch 进入发布工作区、未验收脏改动不进入发布工作区、entry 默认注入/可跳过、live bridge 中文 commit/push 与 commit message 脱敏、repo hygiene 只读扫描、冲突标记误报防护、source watcher base path、runtime installer 安装新脚本。
最后验证：2026-04-27 11:14 相关单元测试与 repo hygiene smoke 通过
复用建议：仓库治理候选不直接删除；通过人工确认后再进入交付流水线。Git 发布不替代部署，deployment 仍只做内控服务 smoke；真正生产部署需按对应项目 RUNBOOK 执行。

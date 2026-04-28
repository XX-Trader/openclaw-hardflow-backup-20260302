# TASK_HISTORY

## 2026-04-28 - DeliveryPlan 结构化方案契约与 revise_solution 回流

类型：bugfix
范围：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`、`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：修复 nofx pipeline 方案阶段总被 `solution_review` 拦住的结构性问题。`solution_package` 现在生成通用 `delivery_plan.json` 作为交付契约，`solution.md` 只从契约渲染，避免靠 Markdown 文案过 reviewer。契约字段覆盖任务类型、owner、切片、目标文件/定位策略、实施步骤、验证命令、发布/回滚门禁、人工阻塞条件和安全边界；`solution_review`、`code_execution` 和后续阶段上下文都会读取该契约。`revise_solution` 加入自动回流白名单；否定式安全边界如 “do not set PRODUCTION_TRADING_ENABLED=true” 不再误判为 high risk，正向启用真实交易/下单/资金/凭证仍 hard block。
证据：`compile_delivery_plan()`、`delivery_plan.json` artifact、`PIPELINE_DELIVERY_PLAN_FILE`、`stage_context_files()` 和 `REPAIRABLE_NEXT_ACTIONS` 已更新；新增/更新单测覆盖结构化契约、prompt 注入、非代码 stage 隔离 artifact 写入路径、`revise_solution` 自动回流和真实交易正向表达 hard block。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_smart_arb_live_bridge` 96 项 OK；nofx 已安装 `3a44f0b0`，远端 `compileall` 与 67 项定向单测 OK
复用建议：方案评审要求 `requires_revision` 时先看 `delivery_plan.json` 和 `solution_review.md` 的结构化缺口，不要放松 reviewer。修 pipeline/runtime 自身继续绕过 Discord workflow，走外部 Codex/SSH/operator 改 hardflow、测试后再安装。

## 2026-04-28 - nofx Discord 证据短标签与 cron 群投递

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`cron/jobs.json`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_runtime_installer.py`
事实：Discord 状态卡中的证据项不再直接显示 `solution_review.md`、`command-runs/external_research-1.json` 这类文件名，而是显示 20 字以内中文短说明，例如“方案评审报告”“外部资料核对命令2”。完整证据目录和文件仍保留在 pipeline run 目录。`cron/jobs.json` 的 announce / failureAlert 投递目标已从旧 Telegram 群切到 spreadagent Discord 群 `1494595527181078578`，让定时任务结果和失败告警进入群里。2026-04-28 后续部署已把包含该变更的 `3a44f0b0` 安装到 nofx live runtime，并同步两个 profile `SOUL.md`。
证据：新增证据短标签映射和单测；安装器测试校验 selected cron job 安装后的 delivery/failureAlert 指向 Discord 群；两个 nofx profile SOUL 要求状态卡证据项保持 20 字以内中文短说明；远端 `arbops@43.153.157.46` SSH 低频重试返回 `kex_exchange_identification: read: Connection reset by peer`。
最后验证：2026-04-28 本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 36 项 OK；`python -B -m json.tool cron/jobs.json`、`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline`、`git diff --check` 通过
复用建议：如果用户反馈状态卡证据看不懂，优先补 `ARTIFACT_EVIDENCE_LABELS` 的中文短标签；如果要换定时任务群，更新 `cron/jobs.json` 后重跑 runtime installer，不要改任务 payload。远端 SSH 恢复后按 nofx installer 流程同步本仓库到 `/home/arbops/.hermes`。

## 2026-04-28 - nofx 拉取并安装 3a44f0b0 hardflow runtime

类型：deploy
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、nofx profile `SOUL.md`、runtime installer、cron jobs、内控 API
事实：本机提交 `3a44f0b0` 已推送到 `origin/main`；nofx hardflow 仓库已对齐该提交，工作树 clean，`HEAD...origin/main=0 0`。runtime installer 返回 `ok=true`、`changed=true`，安装态 ops 文件与仓库源码 SHA256 对齐。两个 live profile `SOUL.md` 已同步仓库模板并备份为 `SOUL.md.bak-20260428T143343`，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
证据：远端 `compileall` 通过；远端 `python3 -B -m unittest tests.scripts_openclaw_ops.test_project_delivery_pipeline_runner tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry tests.scripts_openclaw_ops.test_project_delivery_runtime_installer` 67 项 OK；`smart-arb-pipeline --help` 正常；两个 gateway 均为 `running/connected`；内控 API `/health` 为 `status=ok`，`/api/strategy/status` 为 `running=false`。
最后验证：2026-04-28 14:34
复用建议：nofx 安装请求完成后要同时检查仓库 HEAD、runtime ops SHA256、profile `SOUL.md` SHA256、gateway connected 和内控 API；若 profile 模板有变更，安装器之外必须同步 live profile 并重启 gateway。

## 2026-04-27 - nofx 拉取并安装 067fbc43 hardflow runtime

类型：deploy
范围：nofx `/home/arbops/projects/openclaw-hardflow-backup-20260302`、`/home/arbops/.hermes/ops`、`/home/arbops/.hermes/cron/jobs.json`、Task Center、内控 API
事实：按“不要走工作流”的自修边界，从外部 Codex/SSH 直接完成 nofx hardflow 拉取与 runtime 安装。远端仓库已对齐 `067fbc43`，安装前备份 runtime 目标文件到 `/home/arbops/.hermes/ops/install/backups/pre-hardflow-install-20260427T151242Z`；安装后 `pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py` 的安装态 SHA256 与仓库源码一致。echo smoke 使用 `--skip-deployment-command` 与 `--skip-git-publish-command`，不重启服务、不执行 git publish、不触发真实 Hermes chat。
证据：远端 `git rev-list --left-right --count HEAD...origin/main` 为 `0 0`；`smart-arb-pipeline --help` 正常；远端安装态 `py_compile`、仓库 `compileall` 通过；远端定向 `unittest` 98 项 OK；cron 命中三项治理任务；两个 gateway `running/connected`；内控 API `/health` 为 `status=ok`，`/api/strategy/status` 为 `running=false`；echo smoke `install-smoke-arbitrageagent-20260427T151733781612Z` 完成且 Task Center `passed`；`smart-arb-api` cwd 为 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`。
最后验证：2026-04-27 23:17
复用建议：workflow/runtime 自修时继续用外部 SSH/operator，不让 Discord profile 自己改自身；安装后必须复核安装态 hash、入口 help、Task Center smoke 和 `smart-arb-api` cwd。

## 2026-04-27 - nofx Discord 输出降噪与工作流状态卡

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/config.yaml`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`
事实：聊天频道不再默认展示 `[Background process ... finished]`、Hermes `Still working...` 心跳、tool progress、reviewer/tester/terminal stdout/stderr 或旧版“关键证据”列表。`smart-arb-pipeline` 的进度卡和最终状态卡保留 `agent 分工与完成情况`、`阶段命令状态`、`阻塞原因`、`自动修复判断` 和证据目录；命令状态默认只含 stage/agent/returncode/证据文件，调试时才用 `SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT=1` / `--chat-include-command-output` 展开脱敏摘要。两个 nofx profile 模板新增 `agent.gateway_notify_interval: 0`、`display.tool_progress: off`、`display.background_process_notifications: off`，让长任务反馈由 pipeline 中文状态卡负责。
证据：`report_line()` 默认只输出 stage/agent/returncode/证据文件，`render_progress_update()` 使用 `## 最近命令状态`，`render_chat_summary()` 使用 `## 阶段命令状态`，`--chat-include-command-output` 和 `--chat-show-key-artifacts` 作为显式调试开关；两个 nofx profile 模板关闭 `gateway_notify_interval`、`tool_progress` 和 `background_process_notifications`。本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 32 项 OK；`python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；`git diff --check` 通过。
最后验证：2026-04-27 20:05
复用建议：以后用户反馈 Discord 输出太吵时，先区分 Hermes runtime 噪音和 pipeline 状态卡；通用心跳/background wrapper 在 profile config 关闭，业务进度只保留 `# nofx 任务执行进度` / `# nofx 任务执行状态`。不要把 command report 的原始 stdout/stderr 直接转发到聊天频道。

## 2026-04-27 - nofx Discord 运行中进度卡

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`config/nofx-hermes-profiles/{arbitrageagent,spreadagent}/SOUL.md`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`
事实：Discord 入口不再只依赖 Hermes 自带 `Still working...` 心跳。`smart-arb-pipeline` 默认每 60 秒输出 `# nofx 任务执行进度`，展示 run id、已运行时间、阶段进度、当前阶段、最近命令状态和证据目录；`--emit-json` / no chat summary 模式会关闭运行中进度卡。runner 在长命令开始前写 `pipeline_state.json`，加入临时 `running` stage，命令完成后再刷新最终 stage record。进度卡输出会先脱敏，覆盖 header、普通赋值、JSON/TOML quoted sensitive key、常见短 secret 和长 token；预脱敏的 API key 占位文本在“需要凭证”上下文仍保持 high-risk，不自动回流。
证据：新增/更新 `test_render_progress_update_shows_current_stage_and_recent_output`、`test_live_command_writes_running_pipeline_state_before_completion`、`test_redact_text_handles_quoted_sensitive_assignments`、`test_redacted_secret_request_stays_high_risk`；完整相关 unittest 通过；`python -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过；Codex code-reviewer 最终复审 `APPROVED`。
最后验证：2026-04-27 19:10
复用建议：后续 Discord 仍只显示 `Still working...` 时，先看 profile 是否调用了带 `--progress-interval-seconds` 的 `/home/arbops/.local/bin/smart-arb-pipeline`，再看对应 run 的 `pipeline_state.json` 是否在命令执行期间刷新，最后看 profile 是否把 stdout 分段回传到频道。不要把未脱敏的 `command-runs/*.json` 原文直接贴进聊天频道。

## 2026-04-27 - git_publish secret scan 误报修复

类型：bugfix
范围：`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、`tests/scripts_openclaw_ops/test_smart_arb_pipeline_entry.py`、`docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`
事实：`git_publish` 的 staged diff secret scan 改为只检查新增行，并对 value 上下文做区分：真实 token 形态、真实 cookie / Authorization 值、OAuth secret、交易所 API key、`.env` 实值、高熵长随机串、PEM private key marker/material 仍 hard block；`DASHBOARD_BASIC_PASS`、`BASIC_PASS` 这类环境变量名、`os.getenv(...)` 空默认值、`rotatable-pass` 测试假密码、`Authorization: Basic Auth` 测试说明、Markdown 行内 `Authorization: Bearer <token>` 占位说明和“替换为实际强密码”文档占位不再误报。扫描器新增结构化 finding，包含脱敏 `file/line/rule/risk/blocking/snippet`；非占位的 `sample-*`、`*-example` 等敏感赋值仍按 high 阻断；`os.getenv(..., '真实 token')` 与真实短 `Authorization` payload 不会被环境变量或 test/example only 文本上下文放行。`fix_git_publish` 自动回流会识别 `Secret Scan Findings` 中的 high/blocking finding，真实 secret evidence 仍停人工。
证据：新增/更新测试 `test_staged_diff_secret_scan_allows_env_names_and_test_placeholders`、`test_staged_diff_secret_scan_allows_markdown_inline_basic_auth_placeholder`、`test_staged_diff_secret_scan_blocks_markdown_inline_real_authorization_value`、`test_staged_diff_secret_scan_blocks_real_secret_shapes`、`test_staged_diff_secret_scan_blocks_short_real_values_in_example_contexts`、`test_staged_diff_secret_scan_blocks_short_getenv_fallback_secret`、`test_staged_diff_secret_scan_blocks_unquoted_high_entropy_assignment`、`test_staged_diff_secret_scan_blocks_non_placeholder_example_assignments`、`test_staged_diff_secret_scan_blocks_hardcoded_getenv_fallback_secret`、`test_staged_diff_secret_scan_blocks_pem_private_key_lines`、`test_staged_diff_secret_scan_reports_redacted_file_line_and_rule`、`test_git_publish_blocks_real_secret_with_redacted_findings`、`test_staged_diff_secret_scan_allows_basic_auth_test_placeholders`、`test_staged_diff_secret_scan_ignores_removed_secret_lines`、`test_staged_diff_secret_scan_allows_scanner_code_diff`、`test_fix_git_publish_can_auto_repair_without_secret_evidence`、`test_fix_git_publish_stays_high_risk_with_secret_evidence`、`test_fix_git_publish_stays_high_risk_with_secret_scan_findings`；本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过。
最后验证：2026-04-27 19:10
复用建议：以后处理 `Secret-like content detected in staged diff` 时，先打开 `command-runs/git_publish-*.json` 与 staged diff finding，区分“新增真实密钥值”和“环境变量名/测试占位/文档说明”；不要通过关闭 `git_publish` 或移除安全扫描绕过真实 secret hard block。

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

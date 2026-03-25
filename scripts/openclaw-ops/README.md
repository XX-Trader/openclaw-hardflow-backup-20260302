# OpenClaw Ops Scripts

## 标准入口

- 基建输入输出与通信标准收口
- 基建设施输入输出与通信标准
- 基建设施模板文档
- 字段字典

## 2026-03-24 需求包硬门禁（最小版）

- `create-task / route-task / preflight` 现在统一暴露 `requirement_package_gate`
- 当前只对 `request_source=human` 且 `task_type=workflow` 生效
- 当前只在两类场景自动触发：
  - 显式声明 `context_payload.requirement_package_required=true`
  - 命中强项目型需求措辞，例如 `project requirement / requirement package / PRD / 需求文档`
- 普通 `docs / research / ops` 任务里仅出现 `workflow / readme` 这类弱词时，不会再误触发需求包门禁
- 当前最小必填字段：
  - `goal`
  - `success_criteria`
  - `scope.in_scope`
  - `scope.out_of_scope`
- 当需求包不完整时，任务会自动 reroute 到 `clarification_required`，并改派给 `project-agent`
- 运行时观测入口：
  - `selection_inputs.requirement_package_gate`
  - `context_payload.requirement_package_contract`
  - `build_task_preflight(...).requirement_package_gate`

## 2026-03-24 ExecutionEnvelope 主链扩展

- `task_center.py` 现在会为任务自动补齐最小 `execution_envelope` 快照
- `task_outputs / task_incidents / benchmark_runs` 现在会自动继承：
  - `trace_id`
  - `attempt_id`
  - `execution_envelope`
- `task_report(...)` 现在会直接返回顶层 `execution_envelope`
- `report_agent_result` 生成的 `standard_output` 现在也会带：
  - `trace_id`
  - `attempt_id`
  - `execution_envelope`

## 2026-03-24 删环节候选证据门槛收口

- `control_plane_optimization_advisor.py` 现在会为 `stage_simplification_candidate` 生成结构化 `evidence`
- `control_plane_optimization_review_runner.py` 现在会基于 `task_count / benchmark_promoted_count / incident / human_assistance / clarification` 评审是否允许进入 `profile_update`
- `control_plane_profile_update_applier.py` 现在会对 `stage_simplification_candidate` 二次检查 `profile_update_guard`，避免无证据候选直接回写 candidate registry
- `simplification_hint` 当前只会以 `deletion_mode=suggest_only` 写入 candidate，仍然属于“删环节建议”，不是直接自动删 stage

## 2026-03-24 Capability 声明式装配快照扩展

- `task_capability_binding.py` 现在会返回完整的声明式装配快照：
  - `capability_declarations`
  - `capability_contracts`
  - `resolved_agent_profile`
- `create-task` 现在会把这份快照写入 `selection_inputs.capability_binding`
- `execution_envelope.capability_binding` 现在也会继承这份装配结果，不再只保留 `runtime / tool`
- `build_task_preflight(...)` 现在会直接暴露：
  - `resolved_assignee`
  - `resolved_agent_profile`
  - `capability_declarations`
  - `capability_contracts`
- 这一批的目标是把 `task -> output -> incident -> benchmark -> report` 这条主链继续统一，给后面的统一 logger 和真实 live 验收打底

## 2026-03-23 工作流进化闭环收口
- 删环节 / 并行自适应 统一归类为工作流进化闭环，不新增第 5 条 workflow。
- 高级负载均衡已从当前主线移除；现阶段只保留全局并发上限、stage 并发上限与 retry/backoff。
- `stage_execution_strategy` 当前只汇总：
  - parallel_execution
  - simplification_hint
  - optimization_hints
- `stage_simplification_candidate` 属于工作流进化模块中的正式优化策略，按“建议 -> 派单 -> 回写 candidate -> benchmark 验证”执行。

## 2026-03-23 基建输入输出与通信标准收口
- 从这一批开始，后续所有 workflow、agent、benchmark、公告链、profile 升级都必须优先遵循这三份 SSOT：
  - [基建设施输入输出与通信标准](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/adr/2026-03-23-openclaw-foundation-contract-standard.md)
  - [基建设施模板文档](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/templates/openclaw-foundation-contract-templates.md)
  - [字段字典](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)
- 当前统一范围已经正式覆盖：
  - 人类需求输入模板
  - workflow 任务输入模板
  - agent 执行输入模板
  - agent 间通信模板
  - agent 结果输出模板
  - 标准输出包
  - incident 模板
  - benchmark 结果模板

## 2026-03-23 阶段优化提示进入运行时主链
- `policy_enforcer.py`
  - 现在会读取 workflow stage 上的 `clarification_required_fields / parallel_execution / simplification_hint / optimization_hints`
  - 当阶段要求的澄清字段缺失时，会把任务从 `workflow` 自动改派为 `clarification_required`
  - `selection_inputs` 现在会保留 `stage_context_gate / stage_parallel_execution / stage_simplification_hint / stage_optimization_hints`
- `task_executor_runner.py`
  - preflight 与执行 prompt 现在能直接看到上述阶段优化提示
- 这批改动的目标是：让 `profile_update_apply` 写回 registry 后，优化结果第一次真正影响 task intake 和执行预检查

## 2026-03-23 控制面 ROI 分层与 install-surface job 回放落地
- `control_plane_dashboard.py` 现在除了总览 ROI，还会输出：
  - `workflow_roi_breakdown`
  - `stage_roi_breakdown`
  - Markdown / HTML 中对应的 `Workflow ROI` 与 `Stage ROI` 分层视图
- `control_plane_optimization_advisor.py` 现在会同步输出 `stage_roi_breakdown`
  - recommendation 已带 `roi_context`
  - Markdown 已补 `Stage ROI` 分层摘要
- `control_plane_live_acceptance_runner.py` 现在在隔离安装面生成 `jobs.json` 后，会继续回放一组关键 install-surface job
  - 已验证 `summary / dashboard / optimization / profile_update / acceptance` 关键 job 命令可实际执行

## 2026-03-23 控制面 dashboard HTML 产品层落地
- `control_plane_dashboard.py` 现在除了 `json + markdown`，还会输出静态 `html` 看板
- `cron_setup.py` 的 dashboard job 已新增 `--html-output`
- `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-dashboard-html-output`
- `control_plane_acceptance_runner.py` 与 `control_plane_live_acceptance_runner.py` 已把 HTML 产物纳入契约与实跑校验

当前主链状态：
- 已打通 `selector -> profile -> stage -> capability -> profile_update_apply -> targeted validation -> dashboard html`

## 2026-03-23 控制面 profile update 定向 benchmark 验证落地
- 已新增 `control_plane_profile_update_validation_runner.py`
  - 读取 `control-plane-profile-update-apply/latest-report.json`
  - 按受影响 `workflow_profile_id` 定向匹配 benchmark suite
  - 对已回写的 candidate profile 运行验证，并用 `change_id` 做去重
- 已接入 `cron_setup.py`、`install_workflow_profile.py`、`control_plane_acceptance_runner.py`、`control_plane_live_acceptance_runner.py`
  - 默认 job 名称 `ops_control_plane_profile_update_validation_12h`

## 2026-03-23 控制面 profile update 回写闭环落地
- 已新增 `control_plane_profile_update_applier.py`
  - 扫描最近已完成的 `workflow_profile_update` 任务
  - 对通过控制面门禁的任务，把变更安全回写到目标 `workflow-profile-registry.json`
  - 当前默认回写到 `candidate` channel，并在 registry 中记录 `profile_update_history`
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_profile_update_apply_job(...)`
  - 默认 job 名称 `ops_control_plane_profile_update_apply_12h`
  - 默认每 12 小时执行一次，默认延迟 `660000ms`
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-profile-update-apply` job
  - 默认输出 `ops/control-plane-profile-update-apply/latest-report.json`
  - 默认同步输出 `ops/control-plane-profile-update-apply/latest-report.md`
- 已接入 `control_plane_acceptance_runner.py` 与 `control_plane_live_acceptance_runner.py`
  - 静态验收会校验 apply job 是否已安装
  - live acceptance 现在会实跑 `profile_update_apply`

## 2026-03-23 控制面看板趋势层升级
- `control_plane_dashboard.py` 已升级为“快照 + 趋势”双层视图
  - 修复了 dashboard 直接输出链上的高频中文乱码文案
  - 新增最近 7 天趋势汇总：benchmark 次数、晋升/阻断、incident、critical incident、人工协助
  - 新增按 workflow 的历史分布汇总，便于横向比较 `coding-default / research-default / docs-default / ops-default`
- dashboard CLI 现支持 `--trend-days`
  - 不传时默认最近 7 天
  - 继续兼容现有 `cron_setup.py` 与 `install_workflow_profile.py` 的 dashboard job
- 已补并通过 `test_control_plane_dashboard.py`
  - 覆盖趋势统计
  - 覆盖 workflow 分布
  - 覆盖 Markdown 中文输出

## 2026-03-23 控制面长链路验收 runner 落地
- 已新增 `control_plane_acceptance_runner.py`
  - 读取安装后的 `jobs.json`
  - 校验关键控制面 job 是否存在、是否启用、`delivery.mode` 是否符合预期
  - 校验命令消息里是否包含关键脚本和核心参数契约
  - 输出 `latest-report.json + latest-report.md`
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_acceptance_job(...)`
  - 默认 job 名称为 `ops_control_plane_acceptance_12h`
  - 默认每 12 小时运行一次，默认延迟 `420000ms`
  - `delivery.mode=none`，先把验收结果稳定落盘
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-acceptance` job
  - 默认读取 `cron/jobs.json`
  - 默认输出到 `ops/control-plane-acceptance/latest-report.json`
  - 默认同时写出 `ops/control-plane-acceptance/latest-report.md`

## 2026-03-23 中文显示链 CLI UTF-8 守护落地
- 这批直接对人输出中文摘要的 CLI 入口已统一接入 `configure_process_utf8_stdio()`
  - `control_plane_summary_runner.py`
  - `control_plane_dashboard.py`
  - `control_plane_optimization_advisor.py`
  - `control_plane_acceptance_runner.py`
  - `task_output_consumer.py`
  - `benchmark_output_consumer.py`
  - `task_output_broadcast_runner.py`
  - `benchmark_orchestrator.py`
- 目标是统一 `stdout/stderr` 与子进程默认编码，降低 Windows 终端链路出现中文乱码的概率
- 已补 UTF-8 entrypoint 守护测试，后续新增人类可读输出脚本时会被回归测试拦住

## 2026-03-23 能力声明式自动装配最小闭环落地
- `task_capability_binding.py` 已新增 `resolve_task_capability_binding(...)`
  - 基于 `required_capabilities / required_skills / allowed_agents` 推导默认 assignee
  - 输出合并后的 capability、skill、allowlist 与解析原因
- `policy_enforcer.py` 的 `create-task` 已接入这条绑定逻辑
  - 未显式指定 assignee 时，`implement` 阶段可自动落到 `backend-dev`
  - `review` 阶段可按 `requesting-code-review` 自动落到 `reviewer`
  - `selection_inputs.capability_binding` 会留下绑定来源与候选信息，便于审计

## 2026-03-23 控制面优化建议层落地
- 已新增 `control_plane_optimization_advisor.py`
  - 基于最近 `task / incident / benchmark / promotion` 信号生成优化建议
  - 输出 `report.json + report.md`
  - 给出环节裁剪、并行候选、澄清补强、门禁强化等建议
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_optimization_job(...)`
  - 默认每 12 小时运行一次
  - 默认延迟 `360000ms`
  - `delivery.mode=none`，先稳定落盘，再由上层消费
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-optimization` job
  - 默认输出到 `ops/control-plane-optimization/latest-report.json`
  - 默认同时写出 `ops/control-plane-optimization/latest-report.md`

## 2026-03-23 控制面看板快照层落地
- 已新增 `control_plane_dashboard.py`
  - 复用 `control_plane_summary_runner.py` 的聚合结果
  - 输出静态 `dashboard.json + dashboard.md`
  - 汇总最近 `task / incident / benchmark / promotion` 信号
- 看板快照当前包含：
  - 总览指标：incident、人工协助、benchmark、token、cost
  - 重点任务：workflow/channel/stage 与重点风险徽标
  - benchmark 概览：最近 sweep 的 suite、成功/失败、晋升/阻断结果
- 当前先提供静态快照 CLI，不急着接前端页面

## 2026-03-22 控制面汇总 job 落地
- 已新增 `control_plane_summary_runner.py`
  - 聚合最近 `task / incident / benchmark / promotion` 信号
  - 输出统一 `event + human_text`
  - 使用 state 文件做去重，避免重复公告
- `workflow_views.py` 已新增 `build_control_plane_summary_event(...)`
  - 统一渲染控制面汇总的人类视图、结构化事件和公告文本
- `cron_setup.py` 已新增 `build_control_plane_summary_job(...)`
  - `delivery.mode=announce`
  - 默认每 6 小时运行一次，默认延迟 `180000ms`
- `install_workflow_profile.py` 生成的默认 cron setup 命令，现已自动安装 `control-plane-summary` job

## 2026-03-22 task 控制面广播 job 落地
- 已新增 `task_output_broadcast_runner.py`
  - 扫描最近有控制面变化的 task
  - 复用 `task_output_consumer.py` 渲染单 task 统一事件
  - 通过 state 文件去重，只广播新的可见事件
- `cron_setup.py` 现已新增 `build_task_output_broadcast_job(...)`
  - `delivery.mode=announce`
  - 默认每 15 分钟运行一次，默认延迟 `120000ms`
- `install_workflow_profile.py` 生成的默认 cron setup 命令，现已自动安装 `task-output-broadcast` job

## 2026-03-22 benchmark 输出通知 job 落地
- `cron_setup.py` 现已新增 `build_benchmark_output_job(...)`
  - 独立读取 `benchmark-sweeps/sweeps/latest-summary.json`
  - 通过 `benchmark_output_consumer.py` 渲染统一 `human_text`
  - `delivery.mode=announce`，用于走正式 cron delivery 通道
- `install_workflow_profile.py` 生成的默认 cron setup 命令，现已自动安装 `benchmark-output` job
  - 默认每 24 小时执行一次
  - 默认延迟 `300000ms`，避免与 benchmark sweep 同时触发

## 2026-03-22 benchmark 输出进入调度主链
- `cron_setup.py` 的 `build_benchmark_sweep_job(...)` 现在会在 benchmark sweep 完成后继续调用 `benchmark_output_consumer.py`
  - 默认读取 `benchmark-sweeps/sweeps/latest-summary.json`
  - 默认写入 `benchmark-sweeps/output/latest-event.json`
  - 默认使用 `--notify-on error`
- `install_workflow_profile.py` 生成的默认 cron setup 命令也已经自动接入这组 `benchmark-sweep-output-*` 参数

这个目录用于维护 OpenClaw 的工作流运行时、定时任务和控制面脚本。

## 2026-03-22 当前主链状态

- 已完成正式 workflow：`coding-default`、`research-default`、`docs-default`、`ops-default`
- 已完成控制面主链：workflow selector、profile/stage manifest、capability registry、output/human gate/incident、benchmark suite、promotion/rollback
- 已新增 `benchmark_orchestrator.py`
  - 支持 `list-suites`、`run-suite`、`run-all`
  - 单 suite 默认写入 `output_root/suites/<suite_id>`
  - sweep 总摘要默认写入 `output_root/sweeps/latest-summary.json`
- 已新增 benchmark sweep 定时任务接线
  - `cron_setup.py` 现在支持 `--install-benchmark-sweep-job`
  - `install_workflow_profile.py` 默认会把 benchmark sweep job 一起装上
  - 默认跑 4 个正式 suite，但保守模式下不自动批量创建任务、也不自动批量晋升
- 已新增 benchmark sweep 统一输出消费层
  - `workflow_views.py` 已支持 `build_benchmark_sweep_event(...)`
  - `benchmark_output_consumer.py` 可把 sweep summary 渲染成统一 `event + human_text`
- 所有自动消息输出与运行记录应统一包含 `sender_identity`，并默认使用 UTF-8 无 BOM 落盘

这个目录用于维护 OpenClaw 工作流、定时任务和运维巡检脚本。

所有自动消息输出与运行记录统一包含 `sender_identity` 字段，便于排查是谁发送、链路是否正常。
对外聊天文案统一使用中文卡片，不直接展示文件路径，改为展示“留痕编号”。
所有 cron 直接执行的 Python 入口都会强制把 `stdout/stderr` 统一为 UTF-8，并把 `PYTHONIOENCODING/PYTHONUTF8` 传给子进程，避免 Windows 上中文摘要在 Telegram/日志里出现乱码。

- `policy/task_center.py`
  - 对外读取任务、stage run、module log、module communication、agent task report、planner summary、daily summary 等接口时，默认返回展示安全视图，只展示中文留痕编号。
  - 如需原始存储值用于内部回写、底层审计或数据修复，显式传入 `display_safe=False`。
  - 现已新增 `task_outputs`、`task_incidents` 两张统一控制面表，用于沉淀标准化输出包、人工协助/异常升级记录。
  - `task_report(...)` 现在会额外带出 `task_outputs`、`task_incidents`、`benchmark_runs`、`control_plane` 四段控制面视图，便于直接审计人机协助、open incident 与 benchmark 结果。
  - `update_task_incident(...)` 支持把 incident 从 `open` 推进到 `acked/resolved/suppressed`，并自动留下事件审计。
  - `report_agent_result` 会自动写入统一 `standard_output`，其中包含 `workflow`、`outcome`、`human_gate`、`telemetry`、`contracts`、`delivery` 六段结构。
- `task_output_consumer.py`
  - 统一消费 `task_report` 里的控制面数据，输出标准 `event` + `human_text`。
  - 复用 `workflow_views.py` 的 `human/agent/external/storage` 四视图结构，不再单独定义一套聊天格式。
  - 适合给后续 Telegram、钉钉、面板、webhook 当统一出口层。
- `policy/capability-registry.json`
  - 定义 runtime `Capability Registry`，统一收口 `capability_id -> allowed_agents/default_agent/contracts`。
  - 同时维护 `agent_defaults`，把现有 `assignee -> required_capabilities/required_skills/allowed_agents` 默认推断收进正式 registry。
  - `policy_enforcer init` / `validate-runtime` / `create-task` 已经接入这份 registry，未知 capability 会 fail-fast。
- `policy/benchmark-suite-registry.json`
  - 定义 runtime `Benchmark Suite Registry`，统一收口 `suite_id -> workflow_target/skill_name/window/channel`。
  - `policy_enforcer init` 现会自动写出默认 `coding-default-core`、`research-default-core`、`docs-default-core` 与 `ops-default-core` 基准集。
  - `upgrade_feedback_runner.py` 已支持读取该文件，并把 suite 信息固化到 `benchmark_suite` 与 `promotion_bundle`。
  - `cron_setup.py` / `install_workflow_profile.py` 现在会默认把这份 registry 作为 `upgrade feedback` 定时任务的 benchmark 输入。
- `policy/workflow-profile-registry.json`
  - 现在除了 profile/channel 之外，也正式维护 `default_stage_id`、`task_type_stage_map`、`stages`。
  - 当前正式 profile 已包含 `coding-default`、`research-default`、`docs-default` 与 `ops-default`，四者都具备 `stable/candidate` 双通道。
  - `create-task` 会根据 workflow profile 自动解析 `stage_id`，并把 stage 的 `required_capabilities/required_skills` 合并进任务约束。
  - 每个 stage 现在还能声明 `score_gate`、`min_evidence_count`、`output_contract`、`verification_contract`。
  - `task_center` 与 `task_executor_runner` 已支持透传 `stage_id` 和 stage 合同字段，便于后续做 stage 级审计、评分和证据校验。
  - `task_executor_runner` 现在会在执行后生成 stage evidence、校验 deliverable / verification contract，并把评估结果写入 `stage_runs.details.stage_contract`。
  - 当 `stage_contract.contract_passed = false` 时，`report_agent_result` 会自动把原本 `passed` 的结果降级为 `partial + retry`，并在升级分析里统计 `stage_contract_failure_count`。
  - 当任务需要人工协助、澄清、升级或 stage contract 失败时，`report_agent_result` 还会自动生成 `task_incidents` 记录，后续可直接接通知与 benchmark 审计。
  - `complete-task` 现会读取统一 `task_outputs/task_incidents` 门禁；若仍存在 `requires_human_assistance` 或 open critical incident，则不会再被高分直接判通过。

## TODO 巡检

- `todo_patrol.py`
  - 读取 coordinator 的 TODO 与执行看板。
  - 仅对 `UNASSIGNED` 项请求分配。
  - 自动合并 tester 失败项（去重）。
- `install_todo_patrol_job.py`
  - 安装/更新 `TODO 巡检（15分钟）` 到 `~/.openclaw/cron/jobs.json`。

## Web Intel

- `web_intel_collect_runner.py`
  - HTTP 优先，浏览器兜底支持 `playwright -> selenium`。
  - 会识别 `403/429/503` 与 `Cloudflare/captcha/turnstile/checking your browser` 反爬页面。
  - 采集失败不再只聊天告警，会自动写入 task-center 修复任务，后续由 `task_executor_runner.py` 消费。
  - 内部摘要与任务包不再直出 `report/raw/parsed` 文件路径，统一改为中文字段与留痕编号。
- `web_intel_review_runner.py`
  - 对解析后的网页情报做 optimization/project-doc 两种复核。
  - 发现变化后会自动打包 follow-up 任务到 task-center，而不是只输出摘要。
  - 复核摘要与 follow-up 任务包统一使用中文留痕编号，不再暴露 `report_file/parsed_file` 路径。
- `install_web_intel_jobs.py`
  - 安装 web-intel cron 时会显式带上 `--db ~/.openclaw/ops/task-center/task_center.db`，接入统一闭环。

## Cron 工作流

- `ops_cron_runner.py`
  - 统一执行 `incremental/full/daily` 三种模式。
  - 记录增量读取位置（checkpoint）、问题次数、open/resolved/reopened 状态。
  - 增量异常可自动回退全量扫描。
  - 对失败工作流不再只写 `TODO.md`；会同时自动派生指派给 `optimization-agent` 的 `task-center` 修复任务，后续由 `task_executor_runner.py` 消费。
  - 支持每个技能日志开关：`silent`（静默）/`chat`（发聊天）。
  - 高风险始终提醒，不受普通日志开关影响。
- `cron_setup.py`
  - 一键安装 OpenClaw cron jobs（增量监控/全量校准/每日日报）。
  - 可选安装系统定时审计 job（系统 cron + systemd timer + openclaw jobs）。
  - 自动推断 delivery channel/to。
  - 内部维护型 job 默认走官方 `delivery.mode=none`，避免 isolated run 文本直接投递到聊天框；高频维护任务默认不再额外写入 `failureAlert`，只在巡检汇总里保留高价值异常。
  - 自动写入 `~/.openclaw/ops/cron-monitor-config.json` 的技能日志开关。
- `system_schedule_snapshot.py`
  - 采集系统定时与 OpenClaw 定时快照。
  - 对比历史状态，识别变更与高风险项。
  - 输出 `NO_REPLY` 或中文告警摘要（仅展示留痕编号，不展示证据路径）。
- `api_test_audit.py`
  - 接口巡检采用单次执行，不做重复重测循环。
  - 支持 `http/playwright/selenium` 模式（浏览器检查可用 playwright/selenium）。
  - 检查接口是否有返回值、必填字段、JSON 合法性、数据时效（旧数据自动高风险）。
  - 空返回值和旧数据都会归类为高风险并落盘证据。
- `daily_work_report.py`
  - 每日从任务中心提取 TODO/DONE，并合并仓库根目录 `todo.md/TODO.md` 中尚未入任务中心的待办。
  - 仅发送新增记录，不重复发送历史 TODO/DONE。
  - 支持钉钉 webhook 通知；同时输出统一中文群聊摘要（无新增记录且无异常时输出 `NO_REPLY`）。
  - 群聊里的优先任务默认按“任务 / 要求 / 状态 / 值得做”四段展示，要求优先取任务中心的 `requirement + acceptance`，避免只剩任务 ID 或机械字段罗列。
  - 对 `failed / escalated` 的任务，会额外展示精简后的失败信息与执行概况：失败原因、失败次数、最近耗时、模型、token、cost；不会展示原始堆栈、完整 `failed_items`、文件路径或原始 JSON。
- `daily_todo_digest.py`
  - 每日 TODO/DONE 摘要（仅聊天输出，不做外部 webhook 推送）。
  - 用于替代历史 `workspace/scripts/daily_todo_digest.py` 的不稳定路径依赖。
  - 现在会优先展示新增待办里的焦点任务，按“任务 / 要求 / 状态 / 值得做”输出；若任务已失败，会补充失败原因、失败次数、最近耗时、模型、token、cost。
  - 异常仍只展示人能判断的摘要，不暴露文件路径、原始 JSON 或底层堆栈。
- `self_evolution_todo.py`
  - 周度全量复盘历史任务/流程指标。
  - 只产出“建议与任务包”，禁止自动修改工作流与技能。
  - 任务统一写入 TODO（低优先级、高风险、需人工确认），并带 `scheduled_at`。
  - 按 FIFO 时间顺序入队，且每次运行限制最大产出数量，避免批量风险。
- `governance_evolution_runner.py`
  - 工作流仓库增量扫描（默认关注 `scripts/openclaw-ops/`、`hooks/`、`openclaw/`、`setup.py`）。
  - 支持通过 `openclaw.json + project-registry` 自动定位本地 git 仓库（`--repo-path` 可选）。
  - 扫描前可自动执行本地 git 更新（`--auto-git-update` + `--git-update-strategy`）。
  - 支持任务清晰度分流（`--task-clarity auto/clear/ambiguous`）。
  - 需求不明确时可启用 `project-agent` 前置上下文门（`--project-context-gate`）。
  - 自动创建 `optimization-agent` 优化任务，支持可选创建 `reviewer` 审查任务。
  - 可选自动 PR（需要 `gh auth` 与干净工作区），并输出报告与状态。
  - 默认排除记忆/会话文件（`openclaw-memory/`、`.workflow/experience/`、`.workflow/sessions/`、`memory/`、`MEMORY.md`）。
- `github_web_evolution_runner.py`
  - 定时搜索 GitHub 高质量仓库并沉淀到 `~/.openclaw/web/github/`。
  - 自动落盘仓库元数据、README、方法片段、运行报告与目录索引（`CATALOG.md`）。
  - 按增量变化打包 `github_web_evolution` TODO 任务，支持质量阈值、去重与分批建单。
  - 仅产出任务包，不直接执行高风险改动。
- `reviewer_cron_runner.py`
  - Reviewer 定时审查执行器，支持 `hourly_git / daily_incremental / bi_daily_recurring / weekly_structure` 四种模式。
  - 内置问题去重与生命周期：`open / resolved / reopened`。
  - 每次执行落盘历史证据，支持 `NO_REPLY` 降噪输出。
- `install_reviewer_scan_jobs.py`
  - 一键安装 Reviewer 四层审查任务（1小时、每日4点、每2天、每周）。
  - 自动推断 delivery channel/to 并写入 `~/.openclaw/cron/jobs.json`。

## 风险动态更新

- `policy/risk_rule_sync.py`
  - 支持聊天驱动的高低风险关键词更新。
  - 典型高风险：`api变更/参数变更/逻辑变更/流程变更/结构变更`。
  - 典型低风险：`代码bug/配置错误/网络失败/资源告警/重复进程`。

## Policy Enforcer 同步

- `sync_policy_enforcer_to_servers.sh`
- `sync_policy_enforcer_to_servers.ps1`

## Telegram / OpenViking 运行手册

- [docs/2026-03-16-pm-website-telegram-openviking-runbook.md](../../docs/2026-03-16-pm-website-telegram-openviking-runbook.md)
  - 记录了 `pm-website` 上 Telegram 私聊、`coordinator`、`memory-openviking`、错误群目标清理、坏会话清理、workspace 污染修复、HardFlow guard 补齐、以及“记忆优先但轻量召回”的已验证实施顺序。
  - 其他服务器要复用本次方案时，先按这份 runbook 做基线，再按其中的故障分支做额外补救，不要直接照搬临时排障动作。

## pm-website Cron 基线

- [docs/2026-03-17-pm-website-cron-baseline.md](../../docs/2026-03-17-pm-website-cron-baseline.md)
  - 记录了 `pm-website` 上推荐保留/关闭的 cron 策略、`project_index_maintainer_4h` 的 git HEAD 留痕与 4 小时兜底策略、以及 reviewer 只保留周审查的实施口径。

## PR 审查 / 自动合并改造方案

- [docs/plans/2026-03-17-pr-review-merge-gate-implementation-plan.md](../../docs/plans/2026-03-17-pr-review-merge-gate-implementation-plan.md)
  - 记录了如何把 `governance evolution -> create/update PR -> reviewer 审查 -> approval gate 自动合并` 这条链落到代码和运行态，包括职责边界、代码改造点、灰度步骤、验收与回滚要求。

## 多项目服务器模板

- [docs/2026-03-17-multi-project-server-template.md](../../docs/2026-03-17-multi-project-server-template.md)
  - 记录了“一台服务器承载多个项目”时的推荐任务分层：哪些整机共享，哪些必须按项目拆分，以及当前安装器对多仓 `governance auto-pr / reviewer PR gate` 的真实支持边界。
- `install_workflow_profile.py` 现已支持：
  - `--install-multi-project-governance-jobs`
  - `--install-multi-project-reviewer-pr-gates`
  - `--install-multi-project-git-sync-jobs`
  - `--install-multi-project-auto-update-install-jobs`
  - `--multi-project-auto-update-install-cmd-template`
  - 会基于 `project-registry.json` 为额外 `business` 项目派生 per-repo governance / reviewer PR gate / git sync / auto update install job。
- [project-registry.example.json](./policy/project-registry.example.json)
  - 多项目 registry 样例，包含 `discovery`、`projects`、`doc_sources`、`runtime_monitoring`，以及可选的 `git_sync` / `auto_update_install_cmd` 字段。
- [reviewer-merge-approval.multi-project.example.json](./reviewer-merge-approval.multi-project.example.json)
  - 多项目 reviewer merge approval 样例，推荐按 `repo + head_prefix + base` 做审批规则，而不是按 PR 编号硬编码。

## 远程安全更新

- `remote_safe_update.py`
  - 远程检查或同步 `openclaw-hardflow-backup-20260302`
  - 默认排除 `google-us`
  - 支持三种冲突策略：`runtime-reset`、`stash-nonvolatile`、`snapshot-branch`
- `remote_safe_update.ps1`
- `remote_safe_update.sh`

## 常用命令

```bash
# 安装 cron 工作流（含系统定时审计技能）
python3 scripts/openclaw-ops/cron_setup.py \
  --install-system-schedule-job \
  --install-api-test-job \
  --api-test-engine playwright \
  --api-test-expr "*/15 * * * *" \
  --install-daily-work-job \
  --daily-work-expr "15 0 * * *" \
  --install-self-evolution-job \
  --self-evolution-expr "30 3 * * 1" \
  --self-evolution-lookback-days 30 \
  --self-evolution-min-interval-days 7 \
  --self-evolution-max-tasks-per-run 3 \
  --self-evolution-agent-score-threshold 70 \
  --self-evolution-agent-score-min-reports 3 \
  --self-evolution-agent-score-top-n 12 \
  --install-governance-evolution-job \
  --governance-evolution-openclaw-config ~/.openclaw/openclaw.json \
  --governance-evolution-project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --governance-evolution-repo-id openclaw-hardflow-backup-20260302 \
  --governance-evolution-auto-git-update \
  --governance-evolution-git-update-strategy fetch \
  --governance-evolution-git-fetch-timeout 120 \
  --governance-evolution-every-ms 21600000 \
  --governance-evolution-log-mode silent \
  --governance-evolution-max-files 120 \
  --governance-evolution-min-interval-minutes 180 \
  --governance-evolution-task-clarity ambiguous \
  --governance-evolution-project-context-gate \
  --governance-evolution-project-context-assignee project-agent \
  --governance-evolution-create-review-task \
  --no-governance-evolution-auto-pr \
  --install-github-web-evolution-job \
  --github-web-evolution-openclaw-home ~/.openclaw \
  --github-web-evolution-web-root ~/.openclaw/web/github \
  --github-web-evolution-every-ms 43200000 \
  --github-web-evolution-min-interval-minutes 360 \
  --github-web-evolution-max-queries 5 \
  --github-web-evolution-max-repos-per-query 20 \
  --github-web-evolution-max-total-repos 40 \
  --github-web-evolution-min-stars 80 \
  --github-web-evolution-min-quality-score 45 \
  --github-web-evolution-min-new-or-updated 2 \
  --github-web-evolution-recent-dedupe-days 14 \
  --github-web-evolution-max-tasks-per-run 2 \
  --github-web-evolution-schedule-gap-minutes 90 \
  --github-web-evolution-assignee optimization-agent \
  --github-web-evolution-github-token-env GITHUB_TOKEN \
  --dingtalk-webhook-env DINGTALK_WEBHOOK_URL \
  --dingtalk-secret-env DINGTALK_SECRET \
  --incremental-log-mode silent \
  --full-log-mode silent \
  --daily-log-mode silent \
  --system-log-mode silent \
  --api-test-log-mode silent \
  --daily-work-log-mode silent \
  --self-evolution-log-mode silent \
  --github-web-evolution-log-mode silent

# 手动执行一次增量巡检
python3 scripts/openclaw-ops/ops_cron_runner.py --mode incremental

# 手动执行一次接口单次全量巡检
python3 scripts/openclaw-ops/api_test_audit.py \
  --config-file ~/.openclaw/ops/api-test-config.json \
  --engine playwright-real \
  --normal-log-mode silent

# 动态调整风险规则（示例）
python3 scripts/openclaw-ops/policy/risk_rule_sync.py batch \
  --apply-default-preset \
  --add-high "api契约升级" \
  --add-low "临时网络抖动"

# 先检查远程仓库冲突
python3 scripts/openclaw-ops/remote_safe_update.py --mode inspect

# 只清理运行态冲突再同步
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy runtime-reset

# 非运行态改动先 stash 再同步
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy stash-nonvolatile

# 手动执行一次每日工作钉钉报告（仅新增 todo/done）
python3 scripts/openclaw-ops/daily_work_report.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --todo-file ./todo.md \
  --todo-file ./TODO.md \
  --normal-log-mode silent

# 手动执行一次周度自我进化复盘（只产出 TODO 任务包）
python3 scripts/openclaw-ops/self_evolution_todo.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --lookback-days 30 \
  --min-review-interval-days 7 \
  --max-tasks-per-run 3 \
  --agent-score-threshold 70 \
  --agent-score-min-reports 3 \
  --agent-score-top-n 12 \
  --normal-log-mode silent

# 手动执行一次治理进化增量扫描（可选创建 reviewer 任务）
python3 scripts/openclaw-ops/governance_evolution_runner.py \
  --openclaw-config ~/.openclaw/openclaw.json \
  --project-registry ~/.openclaw/ops/task-center/project-registry.json \
  --repo-id openclaw-hardflow-backup-20260302 \
  --auto-git-update \
  --git-update-strategy fetch \
  --git-fetch-timeout 120 \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --state-file ~/.openclaw/ops/governance-evolution/state.json \
  --report-dir ~/.openclaw/ops/governance-evolution/reports \
  --task-clarity ambiguous \
  --project-context-gate \
  --project-context-assignee project-agent \
  --create-review-task \
  --normal-log-mode silent

# 手动执行一次 GitHub 网络资源进化扫描（只沉淀 + 打包 TODO）
python3 scripts/openclaw-ops/github_web_evolution_runner.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --openclaw-home ~/.openclaw \
  --web-root ~/.openclaw/web/github \
  --state-file ~/.openclaw/ops/github-web-evolution/state.json \
  --report-dir ~/.openclaw/ops/github-web-evolution/reports \
  --min-interval-minutes 360 \
  --max-queries 5 \
  --max-repos-per-query 20 \
  --max-total-repos 40 \
  --min-stars 80 \
  --min-quality-score 45 \
  --min-new-or-updated 2 \
  --recent-dedupe-days 14 \
  --max-tasks-per-run 2 \
  --schedule-gap-minutes 90 \
  --assignee optimization-agent \
  --github-token-env GITHUB_TOKEN \
  --normal-log-mode silent

# 手动执行一次系统定时快照审计
python3 scripts/openclaw-ops/system_schedule_snapshot.py --normal-log-mode silent

# 安装 Reviewer 四层定时审查任务
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/reviewer_cron_runner.py \
  --workspace ~/openclaw-hardflow-backup-20260302 \
  --state-file ~/.openclaw/ops/reviewer-scan-state.json \
  --history-dir ~/.openclaw/ops/reviewer-scan-runs \
  --normal-log-mode silent \
  --daily-fix-command "python3 ~/.openclaw/ops/policy/policy_enforcer.py next-todo --limit 5"
```

## New Docs

- Context gate and source split: scripts/openclaw-ops/policy/CONTEXT_GATE.md


## Reviewer Scheduler Update (2026-03-03)

`install_reviewer_scan_jobs.py` now supports hourly git fetch / PR scan / approved merge flow:

```bash
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/reviewer_cron_runner.py \
  --workspace ~/openclaw-hardflow-backup-20260302 \
  --state-file ~/.openclaw/ops/reviewer-scan-state.json \
  --history-dir ~/.openclaw/ops/reviewer-scan-runs \
  --normal-log-mode silent \
  --daily-fix-command "python3 ~/.openclaw/ops/policy/policy_enforcer.py next-todo --limit 5" \
  --hourly-git-fetch \
  --hourly-check-pr \
  --no-hourly-allow-merge
```

To enable approved auto merge:

```bash
python3 scripts/openclaw-ops/install_reviewer_scan_jobs.py \
  ... \
  --hourly-allow-merge \
  --hourly-merge-approval-file ~/.openclaw/ops/reviewer-merge-approval.json
```

注意：
- reviewer 的 `--workspace` 必须指向真实 git 仓库根目录，不能指向 `~/.openclaw/workspace`
- 否则 PR gate 会报 `no git remotes found`，看不到 open PR，也不会执行 merge gate

`reviewer_cron_runner.py` modes:
- `hourly_git`: branch sync + PR check + optional approved merge
- `daily_incremental`: incremental scan + optional fix command
- `bi_daily_recurring`: recurring issue scan with dedupe
- `weekly_structure`: coupling/duplication/config/I-O contract audit
- built-in security heuristics: hardcoded secret / eval-exec / shell=True / verify=False / unsafe JS exec & DOM writes

## Guardrail Upgrades (2026-03-03)

1. `api_test_audit.py` now supports `playwright-real` engine.
2. `api_test_audit.py` supports browser `steps` for click/fill/press/wait E2E flows.
3. Browser checks always produce screenshots and mark `visual_review_mode=native_ai_vision`.
4. Config supports:
   - `forbid_http_engine=true` (block curl-only fake-pass checks)
   - `require_browser_checks=true`
   - `endpoint_engine=http` (API contract checks can stay HTTP while UI uses real browser)
   - `freshness_auto_detect=true` + `freshness_candidate_fields=[...]`
   - endpoint `freshness_required=true` to fail when no valid freshness timestamp is available
   - `real_browser.user_data_dir/profile_directory/channel/headless`
5. `init_api_test_config.py` now generates real-browser defaults and click-step templates.
6. `project_index_maintainer.py` now maintains runtime index artifacts under `.workflow/project-index-local/` by default:
   - `doc-knowledge.json`
   - `doc-search-index.json`
   - `DOC_KNOWLEDGE.md`
   - docs update-check state in `doc-knowledge-state.json`
   - direct-fetch cache under `doc-source-cache/*.txt`
   - `reviewer_cron_runner.py` prefers `project-index-local/project-index.json` and falls back to legacy `.workflow/project-index/project-index.json`
   - both `.workflow/project-index-local/` and `.workflow/project-index/` are runtime-only and should stay out of Git tracking
7. Browser checks now export DevTools-like evidence:
   - `history/devtools/<run>/check-id.json` includes console/network/xhr-fetch response excerpts
   - scoring fields: `min_score`, `require_api_output`, `api_expectations`, `expect_selectors`
   - high-risk output includes screenshot path + devtools log path for manual F12-style audit

## Memory Restore (2026-03-03)

- 新增脚本：`scripts/openclaw-ops/restore_openclaw_memory.py`
- 作用：把项目内记忆目录（默认 `openclaw-memory/`）复制恢复到 OpenClaw workspace。
- source 缺失不会直接失败，会在输出里给 warning（用于提醒“memory 尚未同步”）。

```bash
python3 scripts/openclaw-ops/restore_openclaw_memory.py \
  --project-root /path/to/project \
  --openclaw-home ~/.openclaw \
  --emit-json
```

## Cron Global Switch (2026-03-03)

- 新增脚本：`scripts/openclaw-ops/cron_switch.py`
- 用途：运行期一键暂停/恢复定时任务，减少 token 消耗与消息推送。

```bash
# 查看状态
python3 scripts/openclaw-ops/cron_switch.py status --emit-json

# 关闭全部定时任务
python3 scripts/openclaw-ops/cron_switch.py off --scope all --emit-json

# 恢复定时任务（默认只恢复由 switch 关闭的任务）
python3 scripts/openclaw-ops/cron_switch.py on --scope all --emit-json
```

## Reviewer Scan Scope (2026-03-03)

- `reviewer_cron_runner.py` 已排除记忆相关路径，不再审查这些文件：
  - `.workflow/experience/`
  - `.workflow/sessions/`
  - `openclaw-memory/`
  - `MEMORY.md`

## Reviewer Context Gate (2026-03-03)

- `reviewer_cron_runner.py` 在 `daily_incremental / bi_daily_recurring / weekly_structure` 模式下默认开启项目上下文门：
  - 审查前会先创建 `project-agent` 上下文任务（`reviewer_project_context_preflight`）。
  - 上下文未就绪时，reviewer 全量审查会被阻断并提示人工处理。
- 可通过参数关闭（不推荐）：`--no-project-context-gate`

## Conversation Evolution Channel (2026-03-03)

新增脚本：`scripts/openclaw-ops/conversation_evolution_runner.py`

作用：定时扫描近期对话/会话/记忆记录，提炼以下信号并打包为 TODO 任务：
- bug / 异常 / 失败线索
- 工作流与路由问题
- 未闭环事项（pending/todo/blocked）
- 优化机会（稳定性/成本/token）

`cron_setup.py` 新增参数：
- `--install-conversation-evolution-job`
- `--conversation-evolution-openclaw-home`
- `--conversation-evolution-every-ms`
- `--conversation-evolution-log-mode`
- `--conversation-evolution-lookback-hours`
- `--conversation-evolution-min-interval-minutes`
- `--conversation-evolution-max-files`
- `--conversation-evolution-max-tasks-per-run`
- `--conversation-evolution-schedule-gap-minutes`
- `--conversation-evolution-assignee`

示例（安装时开启该通道）：
```bash
python3 scripts/openclaw-ops/cron_setup.py \
  --install-conversation-evolution-job \
  --conversation-evolution-openclaw-home ~/.openclaw \
  --conversation-evolution-every-ms 21600000 \
  --conversation-evolution-lookback-hours 72 \
  --conversation-evolution-min-interval-minutes 180 \
  --conversation-evolution-max-files 120 \
  --conversation-evolution-max-tasks-per-run 3 \
  --conversation-evolution-schedule-gap-minutes 90 \
  --conversation-evolution-assignee optimization-agent
```

示例（手动执行一次）：
```bash
python3 scripts/openclaw-ops/conversation_evolution_runner.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --openclaw-home ~/.openclaw \
  --state-file ~/.openclaw/ops/conversation-evolution/state.json \
  --report-dir ~/.openclaw/ops/conversation-evolution/reports \
  --lookback-hours 72 \
  --min-interval-minutes 180 \
  --max-files 120 \
  --max-tasks-per-run 3 \
  --assignee optimization-agent \
  --normal-log-mode silent
```

## Conversation Evolution Quality Gate (2026-03-03)

为减少“低质量建议/重复建议/需求漂移”，`conversation_evolution_runner.py` 已增加硬门禁：

- 质量门禁：候选建议必须同时满足
  - `min_evidence_lines`
  - `min_unique_files`
  - `min_quality_score`
- 去重门禁：写入 `[dedupe_key:...]`，并按 `recent_dedupe_days` 防止短期重复创建同类 TODO。

`cron_setup.py` 新增参数：

- `--conversation-evolution-max-evidence-per-candidate` (default: `24`)
- `--conversation-evolution-min-evidence-lines` (default: `3`)
- `--conversation-evolution-min-unique-files` (default: `1`)
- `--conversation-evolution-min-quality-score` (default: `55`)
- `--conversation-evolution-recent-dedupe-days` (default: `14`)

示例（更严格）：

```bash
python3 scripts/openclaw-ops/cron_setup.py \
  --install-conversation-evolution-job \
  --conversation-evolution-openclaw-home ~/.openclaw \
  --conversation-evolution-lookback-hours 72 \
  --conversation-evolution-min-interval-minutes 180 \
  --conversation-evolution-max-files 120 \
  --conversation-evolution-max-evidence-per-candidate 30 \
  --conversation-evolution-min-evidence-lines 4 \
  --conversation-evolution-min-unique-files 2 \
  --conversation-evolution-min-quality-score 65 \
  --conversation-evolution-recent-dedupe-days 21 \
  --conversation-evolution-max-tasks-per-run 3 \
  --conversation-evolution-assignee optimization-agent
```

## GitHub Web Evolution Channel (2026-03-04)

新增脚本：`scripts/openclaw-ops/github_web_evolution_runner.py`

用途：定时从 GitHub 搜索与你工作流相关的高信号仓库，沉淀知识并触发“人工审核后再优化”的任务链路。

落盘目录（默认）：
- `~/.openclaw/web/github/repos/*.json`：仓库元数据
- `~/.openclaw/web/github/readmes/*.md`：README 原文快照
- `~/.openclaw/web/github/methods/*.md`：抽取的方法片段
- `~/.openclaw/web/github/runs/<timestamp_runid>/`：单次运行明细
- `~/.openclaw/web/github/index.json` / `CATALOG.md`：累计索引与目录

任务策略：
- 只对新增/更新仓库建 TODO（`task_type=github_web_evolution`）。
- 默认 `source=github-web-evolution-agent`，`need_human_confirm=true`。
- 去重维度：`fingerprint` + `dedupe_key`，避免短期重复建单。
- 支持 `max_tasks_per_run` 分批建单；单批仍受 `min_new_or_updated` 门槛控制。

`cron_setup.py` 新增参数：
- `--install-github-web-evolution-job`
- `--github-web-evolution-openclaw-home`
- `--github-web-evolution-web-root`
- `--github-web-evolution-every-ms`
- `--github-web-evolution-log-mode`
- `--github-web-evolution-min-interval-minutes`
- `--github-web-evolution-max-queries`
- `--github-web-evolution-max-repos-per-query`
- `--github-web-evolution-max-total-repos`
- `--github-web-evolution-min-stars`
- `--github-web-evolution-min-quality-score`
- `--github-web-evolution-min-new-or-updated`
- `--github-web-evolution-recent-dedupe-days`
- `--github-web-evolution-max-tasks-per-run`
- `--github-web-evolution-schedule-gap-minutes`
- `--github-web-evolution-assignee`
- `--github-web-evolution-github-token-env`

建议：
- 设置环境变量 `GITHUB_TOKEN` 提升 GitHub API 速率上限。
- 网络侧建议默认“先沉淀再审核”，不要直接自动改代码。

## Cron/Reviewer 安装策略更新（2026-03-04）

### 1) `cron_setup.py` 新增安装策略与去重治理

- `--install-profile {legacy,minimal,standard,aggressive}`
  - `legacy`：保持历史行为（默认）
  - `minimal`：降频并优先启用本仓库进化主链（自进化 + 治理进化，条件满足时）
  - `standard`：在 `minimal` 基础上可启用对话进化
  - `aggressive`：尽量启用全部进化任务（前提路径可用）
- `--legacy-optimize-jobs-mode {auto,keep,disable,remove}`
  - 默认 `auto`：`legacy` 保留，其他 profile 自动禁用旧 `optimize_*` 任务
- `--daily-report-dedupe-mode {auto,keep,disable-digest,disable-daily-work}`
  - 默认 `auto`：非 `legacy` 且检测到日总结任务时，自动禁用 `daily_todo_digest`，避免重复提醒

### 2) `cron_setup.py` 默认进化脚本路径优先级

以下参数默认优先使用当前仓库 `scripts/openclaw-ops/` 下脚本，缺失时回退到 `~/.openclaw/ops/`：

- `--self-evolution-py`
- `--conversation-evolution-py`
- `--governance-evolution-py`
- `--github-web-evolution-py`

### 3) `install_reviewer_scan_jobs.py` 新增 reviewer profile

- `--reviewer-profile {legacy,minimal,standard,aggressive}`（默认 `legacy`）
- 新增可调度参数：
  - `--hourly-every-ms`
  - `--daily-expr`
  - `--bi-daily-expr`
  - `--weekly-expr`
  - `--enable-hourly/--no-enable-hourly`
  - `--enable-daily/--no-enable-daily`
  - `--enable-bi-daily/--no-enable-bi-daily`
  - `--enable-weekly/--no-enable-weekly`
- `minimal` 默认关闭 bi-daily 并降低 hourly 频率，减少定时任务噪音。

## 本地 OpenClaw Git 备份（仅本地提交，不推远程）

新增脚本：
- `scripts/openclaw-ops/local_git_backup_runner.py`
- `scripts/openclaw-ops/install_local_openclaw_backup_job.py`

用途：
- 将 `~/.openclaw` 作为本地 git 仓库维护。
- 定时执行 `git add/commit`，不执行任何 `push`。
- 默认过滤高频日志与会话目录，避免仓库膨胀过快。

安装定时任务：

```bash
python3 scripts/openclaw-ops/install_local_openclaw_backup_job.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --runner-py ~/.openclaw/ops/local_git_backup_runner.py \
  --openclaw-home ~/.openclaw \
  --every-ms 3600000
```

手动执行一次（用于首轮初始化）：

```bash
python3 scripts/openclaw-ops/local_git_backup_runner.py \
  --repo-path ~/.openclaw \
  --task-id manual:openclaw-local-backup \
  --normal-log-mode silent
```

## Upstream Runtime Boundary (2026-03-06)

- `install_workflow_profile.py` 现在会把仓库 overlay 配置合并到 `~/.openclaw/openclaw.json`，并把仓库 `hooks/`、`skills/` 动态注入官方 loader。
- `install_workflow_profile.py` 安装时还会顺手执行 `normalize_runtime_binding_tasks.py`、`recover_stale_cron_running_state.py` 和 `policy/gateway_service_manager.py`，分别清理历史 runtime binding backlog、超过阈值的僵尸 `runningAtMs`，以及把 Gateway supervisor 收敛到 canonical `openclaw-gateway.service` / systemd user service。
- `uninstall_workflow_profile.py` 按“精确删除已知安装产物”的方式卸载 runtime workflow，只清理受安装器管理的 cron jobs、runtime bridge 注入项和 `ops` manifest 文件。
- `sync_openclaw_ops_files.py` 的职责明确为 `ops-only`，不再负责 hooks runtime 同步。
- `cron_setup.py`、`install_project_index_job.py`、`install_reviewer_scan_jobs.py`、`install_task_executor_job.py` 会显式输出官方 `openclaw cron` 验证命令；业务定义仍保留在 `jobs.json`。
- Python 治理逻辑继续留在 `scripts/openclaw-ops/policy/*`，通过官方 cron/hooks/webhook surface 触发。

桥接文档：

- `integration/openclaw-bridge/runtime-boundary.md`
- `integration/openclaw-bridge/hooks-install.md`
- `integration/openclaw-bridge/governance-bridge.md`
- `integration/openclaw-bridge/plugin-policy.md`
- `docs/2026-03-14-doc-map-agent-workflow.md`
- `docs/2026-03-14-agent-skill-hook-绑定现状与优化清单.md`
- `docs/plans/2026-03-14-agent-skill-hook-implementation-plan.md`

## Cron Quiet Defaults (2026-03-06)

- `install_task_executor_job.py` 现在默认写入 `--notify-on error`，不再让 `task_executor_runner.py` 的常规 JSON 结果直接刷到群里。
- `task_executor_runner.py` 保留 `--emit-json` 机器输出模式；非 `--emit-json` 模式新增 `--notify-on {error,activity,always}`，静默成功时输出 `NO_REPLY`。
- `task_executor_runner.py` 遇到明确的模型限流/`429` 会做有限次退避重试；可用 `--agent-max-retries` 与 `--agent-retry-delay-sec` 调整。
- `task_executor_runner.py` 现在按 assignee 读取 `policy-config.json` 里的 `agent_model_overrides`，并按 `model_thinking_overrides` 对 Codex 显式使用 `xhigh`，其他模型统一走 `high`。
- `install_task_executor_job.py` 默认给 `task_executor_10m` 写入 `lightContext: true`，让 isolated cron run 只保留轻量 bootstrap，避免无关工作区上下文拖慢首轮 `exec`。
- `ops_daily_work_report_dingtalk`、`ops_local_openclaw_git_backup`、reviewer 系列维护型 cron job 安装时会显式写入稳定模型和 `payload.lightContext: true`，避免跟随默认 `openai-codex` 造成 isolated session 启动超时。
- cron 安装器写入的 scheduled-runner 提示词现在要求：首次只允许一个 `exec`；如果工具返回 `Command still running`，只能对同一 session 使用 `process poll` 等到进程退出，禁止再开第二个 `exec`，避免后台悬挂命令继续占用 `task_center.db`。
- `install_task_executor_job.py` 额外要求每次 `process poll` 的 `timeout` 不得超过 `15000` ms，并在收到 `Process still running` 后立即短轮询，避免长轮询把 gateway ws tick 拖到超时。
- `ops_runtime_cron` 绑定任务现在创建即标记为 `passed/action=runtime_binding`；安装流程会额外执行 `normalize_runtime_binding_tasks.py`，把历史遗留的 runtime binding backlog 一次性归正，避免它们被误判成待执行任务或已完成摘要。
- `install_project_index_job.py` 安装的 cron 任务默认不再追加 `--git-pull`。仓库拉取由 `ops_auto_update_install_hourly` 统一负责；如需人工排障，可显式传 `--git-pull`。
- `web_intel_collect_runner.py` 与 `web_intel_review_runner.py` 新增 `--notify-on`，可选 `error/change/always`。
- `install_web_intel_jobs.py` 新增 `--collect-notify-on` 与 `--review-notify-on`，在只想保留异常告警时传 `error`。
- `integration/openclaw-bridge/acceptance-checklist.md`

推荐验证命令：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path . --dry-run --emit-json
python scripts/openclaw-ops/uninstall_workflow_profile.py --profile all --workflow-repo-path . --dry-run --emit-json
openclaw hooks list --json
openclaw hooks check --json
openclaw plugins list
openclaw config get channels.telegram
# `channels.telegram.allowFrom` 控制 Telegram 私聊允许发起对话的用户 ID 白名单。
```

如果要验证官方 cron surface，请先运行：

```bash
openclaw gateway run
```

## Scrapling Integration Update (2026-03-07)

- `web_intel_collect_runner.py` now uses browser fallback in this order: `scrapling-stealth -> playwright -> selenium`.
- `api_test_audit.py` now supports `http/playwright/playwright-real/selenium/scrapling/scrapling-stealth`.
- `scrapling` is treated as an optional dependency for anti-bot and lightweight browser fetching. If it is unavailable, the workflow still falls back to Playwright/Selenium instead of failing the whole job.
- To enable the new path explicitly, install `scrapling` in the runtime environment: `pip install scrapling`.
- `github_web_evolution_runner.py` now keeps the search scope on project-relevant third-party repositories and libraries, and excludes infrastructure repositories such as `python/cpython`, `nodejs/node`, `golang/go`, and similar runtime/compiler foundations.
- Repositories such as `microsoft/playwright`, `D4Vinci/Scrapling`, and your own project-related third-party dependencies remain in scope.

## Project Doc And Skill Evolution Update (2026-03-09)

- `web_intel_collect_runner.py` now merges three source layers at runtime:
  - `web/sources.json`
  - `web/project_docs_sources.json`
  - `project-registry.json` dynamic `doc_sources`, vendor hints, and per-project `doc-knowledge.json`

## Human-Friendly Cron Alert Update (2026-03-13)

- Human-facing cron / workflow messages are now normalized to one compact Chinese headline:
  - format: `YYYY-MM-DD HH:MM:SS UTC+8 事件：摘要`
  - body lines stay in Chinese and keep only operator-relevant fields such as task id, run id, counts, and trace id
  - `NO_REPLY` remains machine-only quiet success and should not be expanded into explanatory chat text
- Scheduled-runner install prompts now explicitly require passthrough of the finished human-facing output:
  - preserve original Chinese text and `UTC+8` timestamps exactly
  - never add process filler such as `Let me run it again`, `I understand`, or similar wrapper commentary
- `task_executor_runner.py` / `workflow_views.py` chat output now keeps one compact headline and then展开为:
  - `结果`: selected / executed / skipped / unresolved counts
  - `原因解析`: grouped root-cause counts such as `任务仅部分完成 2 个`
  - `修复进展`: executed / partial / failed counts in one line
  - `任务N / 要求N / 状态N / 值得做N`: focus tasks no longer expose raw `todo-...` IDs
  - `失败信息N / 执行概况N`: only for failed or partially-failed tasks, showing failure reason, failure count, duration, model, token, cost
- `todo_patrol.py` verbose human output now also uses the same structured task summary, so newly dispatched tasks are shown as “任务 / 要求 / 状态 / 值得做” instead of raw machine fields.
- For failed workflow alerts, human-facing output now prefers the task purpose plus the failure reason (for example `Git 同步推送：网络错误`) instead of exposing only internal cron job names.
- Human-facing task names now prefer contextual Chinese labels with cadence when known, for example `任务执行器（10分钟）` and `运维增量巡检（15分钟）`, while raw internal IDs remain only in storage facts.
- `ops_cron_runner.py` incremental/full alerts now add:
  - `结论`: how many workflow jobs are still failing, and how many are stale/unrecovered
  - `原因解析`: grouped failure causes such as timeout, network error, auth error, missing detail
  - `修复进展`: newly created follow-up repair tasks and already-existing repair tasks
- The original detailed lists are still preserved, so operators can first read the conclusion and then drill into job-level details only when needed.
- `project-registry.json` now supports a top-level `discovery` block. If enabled, runtime will auto-discover additional local git projects under configured scan roots and merge them with explicit registry entries, while skipping internal repos such as `.openclaw/skills` and runner worktrees.
- Auto-discovered and explicit projects are normalized with a `project_role` plus `vendor_monitoring.enabled`. Only `business` projects participate in vendor doc / repo monitoring by default; `workflow-ops`, `openclaw-runtime`, and upstream reference repos stay indexed but do not trigger vendor scans unless explicitly overridden.
- `project_index_maintainer.py` now extracts external API URLs from actual project source files and writes vendor-aware `doc_sources` plus `repo_sources` into `.workflow/project-index-local/doc-knowledge.json`.
- If an external API host is not in the built-in vendor catalog, project indexing still emits fallback repo search queries from the host tokens (for example `api.polybaymax.com` -> `polybaymax api sdk archived:false`) so GitHub evolution can keep scanning adjacent SDK/client repos automatically.
- `project-registry.example.json` now documents `doc_sources` and `integrations`. If a project declares `binance`, runtime sources automatically include official Binance Spot API docs and changelog. If the code itself contains `https://api.binance.com/...`, the project index will infer the same vendor sources automatically even without manual `doc_sources`.
- `web_intel_review_runner.py` in `project-doc` mode now compares the latest parsed doc against the previous raw snapshot and writes two structured fields into each review item and markdown summary: `new_information` for newly observed content highlights, and `updated_interfaces` for added/removed/changed API endpoints such as `GET /path` or `POST /path`.
- `github_web_evolution_runner.py` default queries now prioritize `openclaw` / `skills` / `hooks` / `plugins` / `workflow` instead of generic OpenAI-adjacent terms.
- `github_web_evolution_runner.py` now also reads project-derived `repo_sources`, appends vendor repo queries, and directly scans official repositories such as Binance connectors/docs repos.
- If `skill4agent` exists in PATH, `github_web_evolution_runner.py` will additionally search skill catalogs and fold new/updated skills into the same evolution report/catalog/task packaging flow.
- Runtime install command for the optional provider:

```bash
npm install -g @skill4agent/cli
```

## Upgrade Scoring And Review (2026-03-22)

- `upgrade_analysis.py`
  - 统一装载 executor-style reports，并输出升级归因所需的聚合指标。
  - 内置 `architecture_gap / workflow_gap / skill_gap / runtime_gap` 分类、workflow/skill 评分口径与晋升判断。
- `workflow_upgrade_scoring.py`
  - 把 baseline / candidate executor reports 转成 workflow scorecard JSON。
  - 适合判断 job 频率、runner、installer、preflight 链路的升级是否值得晋升为新基线。
  - 现会额外统计 `human_assistance_count`、`open_incident_count`、`critical_incident_count`，并在必要时写入 `decision.veto_reasons`。
- `skill_evolution_review.py`
  - 把 baseline / candidate executor reports 转成 skill review markdown / JSON。
  - 适合判断 skill 指令是否补足了触发条件、边界说明、验证动作与失败回流。
- `upgrade_feedback_runner.py`
  - 从 `executor-runs` 自动切 baseline / candidate 窗口。
  - 同时产出 workflow scorecard、skill review 和 summary JSON。
  - 支持把低分或未晋升候选自动包装成 task-center 任务，生成 `workflow_upgrade` / `skill_upgrade` 待办并用 `change_id` 去重。
  - 现支持 `benchmark-suite-registry.json`，可把这次对比绑定到正式 `benchmark_suite`。
  - `cron_setup.py` 安装出的默认 maintenance job 会自动携带 `--benchmark-suite-file` 与 `--benchmark-suite-id coding-default-core`。
  - 若提供 `task-db`，会自动把对比结果写入 `task_center.benchmark_runs`，形成可审计的 benchmark run 记录。
  - summary 现会额外产出 `benchmark_suite`、`benchmark_run`、`promotion_bundle` 三段结构。
  - 支持在满足 `promote_to_new_baseline = true` 时自动回写 `workflow-profile-registry.json`，形成 registry 级 stable/candidate 晋升记录。
  - 适合作为低风险的升级反馈主链，先沉淀证据，再把明确的升级缺口推入 task-center。

- `policy_enforcer.py`
  - 新增 `update-task-incident` CLI，可推进 incident 生命周期并写审计事件。
  - `task-report` 现在会直接返回任务控制面视图，方便消费端后续接聊天、面板或 webhook。
- `workflow_views.py`
  - 现已新增 `build_task_control_plane_event(...)`，把 `task_outputs/task_incidents/benchmark_runs` 统一成人类可读事件。
## 2026-03-23 控制面优化建议派发层落地
- 已新增 `control_plane_optimization_dispatcher.py`
  - 读取 `control_plane_optimization_advisor.py` 生成的优化报告
  - 将 recommendation 去重包装为 task-center 正式任务
  - 默认以 `coding-default@stable` 作为执行 workflow，并保留目标 workflow/stage 审计信息
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_optimization_dispatch_job(...)`
  - 默认 job 名称 `ops_control_plane_optimization_dispatch_12h`
  - 默认延迟 `480000ms`，保证晚于 optimization advisor job 运行
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-optimization-dispatch` job
  - 默认输出 `ops/control-plane-optimization-dispatch/latest-report.json`
  - 默认同步输出 `ops/control-plane-optimization-dispatch/latest-report.md`
## 2026-03-23 控制面 live 验收层落地
- 已新增 `control_plane_live_acceptance_runner.py`
  - 在隔离工作区播种样本 task-center 数据
  - 顺序实跑 optimization advisor、dispatcher、optimization review、profile update dispatch、summary、task output consumer、benchmark output consumer、dashboard、acceptance
  - 输出 `latest-report.json + latest-report.md`
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_live_acceptance_job(...)`
  - 默认 job 名称 `ops_control_plane_live_acceptance_24h`
  - 默认延迟 `540000ms`
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-live-acceptance` job
  - 默认工作区 `ops/control-plane-live-acceptance`
## 2026-03-23 控制面 profile update 派发层落地
- 已新增 `control_plane_profile_update_dispatcher.py`
  - 读取 `control_plane_optimization_review_runner.py` 生成的评审报告
  - 仅对 `ready_for_profile_update=true` 的项创建 `workflow_profile_update` 正式任务
  - 按 `change_id` 去重，避免重复派发相同 profile update
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_profile_update_dispatch_job(...)`
  - 默认 job 名称 `ops_control_plane_profile_update_dispatch_12h`
  - 默认延迟 `600000ms`，保证晚于 optimization review job 运行
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-profile-update-dispatch` job
  - 默认输出 `ops/control-plane-profile-update-dispatch/latest-report.json`
  - 默认同步输出 `ops/control-plane-profile-update-dispatch/latest-report.md`
## 2026-03-23 Trace 与 ExecutionEnvelope 最小闭环
- `create-task` 现在会统一生成或继承 `trace_id / attempt_id`
- `selection_inputs` 现在固定补齐：
  - `trace_id`
  - `attempt_id`
  - `execution_envelope`
- `task-center` 现在会让 `task_outputs / task_incidents / benchmark_runs` 继承任务级 `trace_id`
- `preflight` 现在会透传：
  - `trace_id`
  - `attempt_id`
  - `execution_envelope`
- 当前目标是先把 `task -> output -> incident -> benchmark -> preflight` 主链统一起来，为后续统一 logger、真实 live 验收、工作流进化闭环打底

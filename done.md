# DONE

- 第四十批基建输入输出与通信标准收口
- 基建设施输入输出与通信标准
- 基建设施模板文档
- 字段字典

- 2026-03-24 第四十四批需求包硬门禁最小收口：
  - `policy_enforcer.py` 新增 `requirement_package_gate` 最小门禁，并统一写入 `selection_inputs / context_payload / route_task(...)`
  - `task_executor_runner.py` 的 `build_task_preflight(...)` 现在会透传 `requirement_package_gate`
  - 仅显式 `requirement_package_required=true` 或强项目型需求措辞会自动触发需求包门禁
  - 普通 `docs / research / ops` 任务里的弱词 `workflow / readme` 不再误触发 `clarification_required`
  - 定向回归 `test_policy_task_capability_args + test_task_executor_preflight + test_workflow_selector` 已通过
- 2026-03-24 第四十五批 ExecutionEnvelope 主链扩展：
  - `task_center.py` 现在会为任务自动补齐最小 `execution_envelope` 快照
  - `task_outputs / task_incidents / benchmark_runs` 现在会自动继承 `trace_id / attempt_id / execution_envelope`
  - `task_report(...)` 现在直接返回顶层 `execution_envelope`
  - `policy_enforcer.py` 的 `standard_output` 现在也会带 `trace_id / attempt_id / execution_envelope`
  - 定向回归 `test_task_center_capability_fields + test_policy_task_capability_args` 与扩展回归已通过
- 2026-03-24 第四十六批 删环节候选证据门槛收口：
  - `control_plane_optimization_advisor.py` 现在会为 `stage_simplification_candidate` 生成结构化 `evidence`
  - `control_plane_optimization_review_runner.py` 现在会基于结构化证据生成 `profile_update_guard`
  - `control_plane_profile_update_applier.py` 对删环节候选新增 `profile_update_guard_not_ready` 兜底跳过
  - `simplification_hint` 回写时新增 `deletion_mode=suggest_only / evidence_snapshot / profile_update_guard`
  - 定向回归 `test_control_plane_optimization_advisor + test_control_plane_optimization_review_runner + test_control_plane_profile_update_applier` 已通过
- 2026-03-24 第四十七批 Capability 声明式装配快照扩展：
  - `task_capability_binding.py` 现在会返回 `capability_declarations / capability_contracts / resolved_agent_profile`
  - `policy_enforcer.py` 现在会把这份装配快照写入 `selection_inputs.capability_binding`
  - `execution_envelope.capability_binding` 现在也同步保留这份声明式装配结果
  - `task_executor_runner.py` 的 `preflight` 现在会直接暴露 `resolved_assignee / resolved_agent_profile / capability_declarations / capability_contracts`
  - 定向回归 `test_policy_task_capability_args + test_task_executor_preflight` 已通过

- 2026-03-23 第四十二批 工作流进化闭环收口：
  - 从当前主线移除高级负载均衡，不再生成 `load_balance_stage_candidate`
  - `control_plane_profile_update_applier.py` 对历史负载均衡推荐改为安全跳过，避免旧任务阻塞回写链
  - `stage_execution_strategy` 收紧为 `parallel_execution + simplification_hint + optimization_hints`
  - 明确 `stage_simplification_candidate` 属于工作流进化闭环中的正式优化策略
  - 定向测试已通过：advisor / dispatcher / applier / preflight / create-task / docs clean

- 2026-03-23 第四十一批 控制面执行策略层新增负载均衡提示
  - control_plane_optimization_advisor.py 新增 load_balance_stage_candidate
  - control_plane_profile_update_applier.py 已支持回写 load_balancing_hint
  - policy_enforcer.py 已把 stage_load_balancing_hint / stage_execution_strategy 接进 selection_inputs
  - 	ask_executor_runner.py 已把上述字段透传到 preflight 与执行 prompt
  - 定向测试已通过：advisor / dispatcher / applier / preflight / create-task

- 2026-03-23 第四十批基建输入输出与通信标准收口：
  - 新增正式 ADR：[基建设施输入输出与通信标准](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/adr/2026-03-23-openclaw-foundation-contract-standard.md)
  - 新增正式模板文档：[基建设施模板文档](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/templates/openclaw-foundation-contract-templates.md)
  - 重写 [FIELD_DICTIONARY.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)，把 task / stage / output / incident / benchmark / workflow selection 的关键字段收成可读版字段字典
  - 在 [scripts/openclaw-ops/README.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/README.md) 顶部建立统一 SSOT 入口
  - 在 [2026-03-22-workflow-selection-runtime-implementation-plan.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/plans/2026-03-22-workflow-selection-runtime-implementation-plan.md) 顶部建立标准化批次记录
  - 明确后续所有新增 workflow、agent、benchmark、公告链、profile 升级必须优先遵循统一契约文档，再进入实现

- 2026-03-23 第三十九批 阶段优化提示进入运行时主链：
  - `scripts/openclaw-ops/policy/policy_enforcer.py` 已消费 workflow stage 上的 `clarification_required_fields / parallel_execution / simplification_hint / optimization_hints`
  - 缺少阶段要求澄清字段时，`create-task` 现在会自动 reroute 到 `clarification_required`
  - `scripts/openclaw-ops/policy/task_executor_runner.py` 的 preflight 与执行 prompt 已透传 `stage_context_gate / stage_parallel_execution / stage_simplification_hint / stage_optimization_hints`
  - 定向回归 `test_policy_task_capability_args + test_task_executor_preflight` 已通过
  - 扩展回归待继续跑全链验证

- 2026-03-23 第三十八批 ROI 分层与 install-surface job 回放落地：
  - `scripts/openclaw-ops/control_plane_dashboard.py` 已新增 `workflow_roi_breakdown / stage_roi_breakdown`
  - dashboard Markdown / HTML 已补 `Workflow ROI / Stage ROI` 分层视图
  - `scripts/openclaw-ops/control_plane_optimization_advisor.py` 已新增 `stage_roi_breakdown`
  - recommendation 已挂接对应 `roi_context`
  - `scripts/openclaw-ops/control_plane_live_acceptance_runner.py` 已新增 `installed_job_replay`
  - live acceptance 现在会在 install-surface 真实生成 `jobs.json` 后继续回放关键控制面 job
  - 已通过 dashboard / advisor / live acceptance / acceptance / upgrade feedback / UTF-8 / docs clean 共 55 项相关回归

- 2026-03-23 第三十七批 dashboard HTML 产品层落地：
  - `scripts/openclaw-ops/control_plane_dashboard.py` 已新增静态 HTML 看板输出
  - `cron_setup.py` 的 dashboard job 已新增 `--html-output`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-dashboard-html-output`
  - `control_plane_acceptance_runner.py` 已校验 dashboard HTML 契约
  - `control_plane_live_acceptance_runner.py` 已实跑并检查 dashboard HTML 产物
  - 已通过 dashboard / acceptance / live acceptance / install 相关专项回归

- 2026-03-23 第三十六批 profile update 定向 benchmark 验证落地：
  - 已新增 `scripts/openclaw-ops/control_plane_profile_update_validation_runner.py`
  - 已打通 `profile_update_apply -> targeted benchmark validation`
  - `cron_setup.py` 已新增 `build_control_plane_profile_update_validation_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-profile-update-validation-*` 参数
  - `control_plane_acceptance_runner.py` 与 `control_plane_live_acceptance_runner.py` 已纳入 validation job 与实跑步骤
  - 已通过 validation / acceptance / live acceptance / install / UTF-8 相关专项回归

- 2026-03-23 第三十五批 profile update 回写闭环落地：
  - 已新增 `scripts/openclaw-ops/control_plane_profile_update_applier.py`
  - 已完成 `workflow_profile_update -> workflow-profile-registry.json` 的安全回写闭环
  - `cron_setup.py` 已新增 `build_control_plane_profile_update_apply_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-profile-update-apply-*` 参数
  - `control_plane_acceptance_runner.py` 现在会校验 `ops_control_plane_profile_update_apply_12h`
  - `control_plane_live_acceptance_runner.py` 现在会继续实跑 `profile_update_apply`
  - 已通过 applier / acceptance / live acceptance / install / UTF-8 相关专项回归

- 2026-03-23 第三十四批 profile update 派发层落地：
  - 已新增 `scripts/openclaw-ops/control_plane_profile_update_dispatcher.py`
  - `control_plane_optimization_review_runner.py` 产出的 ready 项现在会被自动派发成 `workflow_profile_update` 正式任务
  - `cron_setup.py` 已新增 `build_control_plane_profile_update_dispatch_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-profile-update-dispatch-*` 参数
  - `control_plane_live_acceptance_runner.py` 现在会继续实跑 `profile_update_dispatch`
  - 已补并通过 dispatcher / acceptance / live acceptance / install / UTF-8 专项测试

- 2026-03-23 第三十三批 optimization review 闭环修正：
  - `control_plane_optimization_review_runner.py` 已修正 `blocked_count` 统计口径，不再把 pending 项误算为阻塞
  - 已修正 review job 的 cron 构造断言
  - 已把 `control_plane_optimization_review_runner.py` 纳入 UTF-8 CLI 入口守护测试

- 2026-03-23 第三十二批控制面看板趋势层落地：
  - `scripts/openclaw-ops/control_plane_dashboard.py` 已升级为“快照 + 趋势”双层视图
  - 新增最近 7 天 benchmark / incident / human_assistance 趋势统计
  - 新增按 workflow 的历史分布汇总
  - 修复 dashboard 输出链的高频中文乱码文案
  - 已补并通过 `tests/scripts_openclaw_ops/test_control_plane_dashboard.py`

- 2026-03-23 第三十批控制面长链路验收 runner 落地：
  - 已新增 `scripts/openclaw-ops/control_plane_acceptance_runner.py`
  - 已补 `tests/scripts_openclaw_ops/test_control_plane_acceptance_runner.py`
  - `cron_setup.py` 已新增 `build_control_plane_acceptance_job(...)` 与 `control-plane-acceptance-*` 参数
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动安装 `control-plane-acceptance` job
  - 已补并通过 acceptance runner / install command / UTF-8 entrypoint 专项测试

- 2026-03-23 第二十九批中文显示链 CLI UTF-8 守护落地：
  - 7 个直接输出中文摘要的 CLI 入口已统一接入 `configure_process_utf8_stdio()`
  - 已新增 `tests/scripts_openclaw_ops/test_utf8_cli_entrypoints.py`
  - 已通过 UTF-8 entrypoint 守护测试与相关输出链回归测试

- 2026-03-23 第二十八批能力声明式自动装配最小闭环落地：
  - `task_capability_binding.py` 已新增 `resolve_task_capability_binding(...)`
  - `policy_enforcer.py` 的 `create-task` 已按 stage + capability 自动推导默认 assignee
  - `implement` 阶段现在可自动绑定 `backend-dev`
  - `review` 阶段现在可自动绑定 `reviewer`
  - 已补并通过 capability auto-binding 的 create-task 专项测试

- 2026-03-23 第二十七批控制面优化建议层落地：
  - 已新增 `control_plane_optimization_advisor.py`
  - `cron_setup.py` 已新增 `build_control_plane_optimization_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-optimization-*` 参数
  - 已补并通过 optimization job 的 install/cron 专项测试

- 2026-03-23 第二十六批控制面看板快照层落地：
  - 已新增 `control_plane_dashboard.py`
  - `control_plane_summary_runner.py` 已抽出 `collect_control_plane_summary(...)`
  - 看板快照现可输出 `dashboard.json + dashboard.md`
  - 已补并通过 dashboard 的 summary / markdown / CLI 专项测试

- 2026-03-22 第二十五批控制面汇总 job 落地：
  - 已新增 `control_plane_summary_runner.py`，用于聚合最近 `task / incident / benchmark / promotion` 信号
  - `workflow_views.py` 已新增 `build_control_plane_summary_event(...)`
  - `cron_setup.py` 已新增 `build_control_plane_summary_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `control-plane-summary-*` 参数
  - 已补并通过 control-plane summary 的 runner / event / install / cron 专项测试

- 2026-03-22 第二十四批 task 控制面广播 job 落地：
  - 已新增 `task_output_broadcast_runner.py`，扫描最近有控制面变化的 task，并通过 state 文件去重广播
  - `task_center.py` 已新增 `recent_control_plane_task_ids(...)`
  - `cron_setup.py` 已新增 `build_task_output_broadcast_job(...)`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `task-output-broadcast-*` 参数
  - 已补 task output broadcast runner 与 install/cron 专项测试

- 2026-03-22 第二十三批 benchmark 输出通知 job 落地：
  - `cron_setup.py` 已新增 `build_benchmark_output_job(...)`
  - benchmark 输出现在可以通过独立 `announce` delivery job 进入正式 cron 通知通道
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `benchmark-output-*` 参数
  - 已补 benchmark output job 与 install 命令专项测试

- 2026-03-22 第二十二批 benchmark 输出调度接线：
  - `cron_setup.py` 的 `build_benchmark_sweep_job(...)` 现在会在 benchmark sweep 完成后继续调用 `benchmark_output_consumer.py`
  - 默认消费 `benchmark-sweeps/sweeps/latest-summary.json`，并把统一 payload 写入 `benchmark-sweeps/output/latest-event.json`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 `benchmark-sweep-output-*` 参数
  - 已补 benchmark sweep job 与 install 命令专项测试

- 2026-03-22 第二十一批 benchmark sweep 统一输出消费层落地：
  - `workflow_views.py` 已新增 `build_benchmark_sweep_event(...)`
  - 新增 `scripts/openclaw-ops/benchmark_output_consumer.py`
  - benchmark sweep 结果现在可以统一输出 `event + human_text`
  - 已补 `test_benchmark_output_consumer.py` 与对应 `workflow_views` 专项测试

- 2026-03-22 第二十批 benchmark sweep 定时任务接线：
  - `cron_setup.py` 已新增 `build_benchmark_sweep_job(...)`
  - 新增 `--install-benchmark-sweep-job` 与对应 `benchmark-sweep-*` CLI 参数
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 benchmark sweep job
  - 默认会覆盖 `coding-default-core`、`research-default-core`、`docs-default-core`、`ops-default-core`
  - 默认策略为“只跑基准与记录结果”，不自动批量创建任务，也不自动批量晋升

- 2026-03-22 第十九批 benchmark 编排控制面落地：
  - 新增 `scripts/openclaw-ops/benchmark_orchestrator.py`
  - 支持 `list-suites`、`run-suite`、`run-all` 三个入口
  - 每个 suite 独立写入 `output_root/suites/<suite_id>` 与 `state_root/<suite_id>.json`
  - sweep 结果会统一写入 `output_root/sweeps/latest-summary.json`
  - 已补 `test_benchmark_orchestrator.py`，覆盖 suite 列表、单 suite 执行、批量 sweep

- 2026-03-22 第十八批第四个正式 workflow profile 落地：
  - `ops-default` 已成为第四个正式 workflow profile，包含 `stable/candidate` 双通道
  - selector 已支持按 `ops_task` 关键词组自动切换到 `ops-default`
  - `workflow-profile-registry.json` 与 `benchmark-suite-registry.json` 已同步扩展到 ops workflow
  - `upgrade_feedback_runner.py` 内置 benchmark suite 默认值已同步补齐 `ops-default-core`
  - 已补齐并通过回归测试，覆盖 init 写 registry、selector 路由、create-task 自动选 stage、runner 默认 suite

- 2026-03-22 第十七批第三个正式 workflow profile 落地：
  - `docs-default` 已成为第三个正式 workflow profile，包含 `stable/candidate` 双通道
  - selector 已支持按 `docs_task` 关键词组自动切换到 `docs-default`
  - `workflow-profile-registry.json` 与 `benchmark-suite-registry.json` 已同步扩展到 docs workflow
  - `upgrade_feedback_runner.py` 内置 benchmark suite 默认值已同步补齐 `docs-default-core`
  - 已补齐并通过回归测试，覆盖 init 写 registry、selector 路由、create-task 自动选 stage、runner 默认 suite

- 2026-03-22 第十六批第二个正式 workflow profile 落地：
  - `research-default` 已成为第二个正式 workflow profile，包含 `stable/candidate` 双通道
  - selector 已支持按 `research_task` 关键词组自动切换到 `research-default`
  - `workflow-profile-registry.json` 与 `benchmark-suite-registry.json` 已同步扩展到 research workflow
  - `upgrade_feedback_runner.py` 内置 benchmark suite 默认值已同步补齐 `research-default-core`
  - 已补齐并通过回归测试，覆盖 init 写 registry、selector 路由、create-task 自动选 stage、runner 默认 suite

- 2026-03-22 第十五批统一输出消费层最小落地：
  - `workflow_views.py` 已新增 `build_task_control_plane_event(...)`
  - 新增 `task_output_consumer.py`，统一消费 `task_report` 里的控制面数据
  - 现在可把 `task_outputs/task_incidents/benchmark_runs` 统一输出成 `human/agent/external/storage` 事件
  - 已补齐并通过回归测试，覆盖 control-plane human view 与 consumer payload

- 2026-03-22 第十四批 benchmark 默认接线 + incident 生命周期 + task-report 控制面视图：
  - `cron_setup.py` 的 upgrade feedback job 已默认支持 `--benchmark-suite-file`、`--benchmark-suite-id`
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动接入 runtime `benchmark-suite-registry.json`
  - `task_center` 已新增 `update_task_incident(...)`，支持 `acked/resolved/suppressed` 生命周期
  - `policy_enforcer.py` 已新增 `update-task-incident` CLI
  - `task_report(...)` 已带出 `task_outputs`、`task_incidents`、`benchmark_runs`、`control_plane`
  - 已补齐并通过回归测试，覆盖 benchmark 默认参数、incident 生命周期与 task-report 展示安全视图

- 2026-03-22 第十三批 benchmark suite / benchmark runs 最小落地：
  - 新增 runtime `benchmark-suite-registry.json`，正式定义默认 `coding-default-core` benchmark suite
  - `policy_enforcer init` 现会自动写出 benchmark suite registry
  - `task_center` 已新增 `benchmark_runs` 表和查询/落盘接口
  - `upgrade_feedback_runner` 现支持 `benchmark_suite_file / benchmark_suite_id`
  - summary 已新增 `benchmark_suite`、`benchmark_run`、`promotion_bundle`
  - 当提供 `task-db` 时，runner 会自动把 benchmark run 写入 `task_center`
  - 已补齐并通过回归测试，覆盖 init、task_center 落盘、upgrade feedback benchmark bundle 三条链

- 2026-03-22 第十二批统一输出信号接入 complete-task 与 promotion veto：
  - `complete-task` 现会读取统一 `task_outputs/task_incidents` 门禁，不再只看分数
  - 若仍存在 `requires_human_assistance` 或 open critical incident，则高分也不能直接通过
  - `upgrade_analysis` / `workflow_upgrade_scoring` 已支持统计 `human_assistance_count`、`open_incident_count`、`critical_incident_count`
  - 当 candidate 仍有 critical incident，或 human assistance / open incident 没有改善时，会写入 `decision.veto_reasons` 并阻止晋升
  - `task_executor_runner` 的结果摘要已附带 `standard_output`、`human_gate`、`incident`，供后续 benchmark 直接复用
  - 已补齐并通过回归测试，覆盖 complete-task 硬门禁与 promotion veto

- 2026-03-22 第十一批统一输出 / 人工协助 / incident 最小落地：
  - 已修复主链高置信中文乱码，覆盖 `policy_enforcer.py`、`todo_patrol.py`、`web_intel_collect_runner.py`
  - `task_center` 已新增 `task_outputs`、`task_incidents` 两张控制面表
  - `report_agent_result` 现会自动生成统一 `standard_output`，沉淀 `workflow/outcome/human_gate/telemetry/contracts/delivery`
  - 当任务需要人工协助、澄清、升级或 stage contract 失败时，会自动记录 `task_incidents`
  - 已补齐并通过回归测试，覆盖 stage contract 失败时的输出包与 incident 落盘

- 2026-03-22 第十批 stage contract gate 接入结果判定与升级分析：
  - `report_agent_result` 已支持根据 `stage_contract.contract_passed` 自动降级 `passed -> partial + retry`
  - 会自动补齐 `stage_contract_failed`、缺失 deliverable、失败 check 到 `failed_items`
  - `task_executor_runner` 的执行结果现会显式写 `reason=stage_contract_failed`
  - `upgrade_analysis` / `workflow_upgrade_scoring` 已支持统计 `stage_contract_failure_count`
  - 已补齐专项单测，覆盖结果降级与 scorecard 统计

- 2026-03-22 第九批 stage contract 运行时评估最小落地：
  - `task_executor_runner` 已支持根据 agent 回报生成 `stage evidence`
  - `task_executor_runner` 已支持校验 `min_evidence_count`、`deliverables`、`verification checks`
  - `post_stage` 已支持接收 `details_json`，并将 `stage_contract` 合并写入 `stage_runs.details`
  - `report-agent-result details_json` 也会带上 `stage_contract`
  - 已补齐专项单测，覆盖 stage contract 评估与 stage run 落盘

- 2026-03-22 第八批 stage gate / score / evidence contract 最小落地：
  - `workflow-profile-registry.json` 的 stage 现已支持 `score_gate`、`min_evidence_count`
  - `workflow-profile-registry.json` 的 stage 现已支持 `output_contract`、`verification_contract`
  - `policy_enforcer create-task` 会把 stage 合同字段写入任务
  - `task_center` / `task_executor_runner` 已支持 stage 合同字段持久化与透传
  - 已补齐专项单测，覆盖 registry 初始化、task 入库、preflight 读取

- 2026-03-22 第七批 workflow stage manifest 最小落地：
  - `workflow-profile-registry.json` 现已支持 `default_stage_id`、`task_type_stage_map`、`stages`
  - `policy_enforcer create-task` 会按 workflow profile 自动解析 `stage_id`
  - stage 的 `required_capabilities/required_skills` 会并入任务约束，并落到 task-center
  - `task_center` / `task_executor_runner` 已支持 `stage_id` 透传
  - 已补齐专项单测，覆盖 workflow registry stage manifest、task `stage_id` 持久化、preflight stage 透传

- 2026-03-22 第六批 capability registry 最小落地：
  - 新增 runtime `capability-registry.json`，正式定义 `capability_id -> allowed_agents/default_agent/contracts`
  - `task_capability_binding.py` 已从散落的硬编码映射收口为 `Capability Registry + agent_defaults`
  - `policy_enforcer init` / `validate-runtime` / `create-task` 已接入 capability registry
  - `create-task` 现在会对 `required_capabilities` 做 fail-fast 校验，未知 capability 直接拒绝入库
  - 已补齐专项单测，覆盖 capability registry 初始化与未知 capability 拒绝

- 2026-03-22 第五批 upgrade feedback install/cron registry promotion 接线：
  - `cron_setup.py` 的 upgrade feedback job 已新增 `workflow_profile_registry`、`auto_apply_workflow_promotion`、`promotion_operator` 三个参数透传
  - `install_workflow_profile.py` 生成的 cron 安装命令现会默认接入 runtime `policy/workflow-profile-registry.json`
  - 默认安装出的 upgrade feedback job 会开启 registry 自动晋升，并把 operator 记为 `cron-upgrade-feedback`
  - `README.md` 已补充 upgrade feedback runner 的 registry 自动回写说明
  - 已补齐并通过对应专项单测，覆盖 cron job 构造与 install 命令渲染

- 2026-03-22 第四批 workflow promotion / rollback control plane 落地：
  - 新增 `workflow_promotion_controller.py`，正式提供 `promote` / `rollback` CLI 与 registry 级 stable/candidate 切换能力
  - `upgrade_feedback_runner.py` 现已支持 `--workflow-profile-registry`、`--auto-apply-workflow-promotion`、`--promotion-operator`
  - 当 workflow scorecard 判定 `promote_to_new_baseline = true` 时，可自动把 candidate 结果写回 workflow profile registry
  - registry 会持久化 `promotion_history`、`last_promotion`、`rollback_history`、`last_rollback`，用于审计与回滚
  - 已补齐专项单测，覆盖 promotion、rollback、runner 自动晋升三条关键链路

- 2026-03-22 第三批 workflow selector 落地：
  - 新增 `select-workflow` 入口，并让 `route-task` / `create-task` 共用同一套 selector
  - selector 当前按最小规则工作：`workflow` / `clarification_required` 默认进入 `coding-default@stable`，`ops_runtime_cron` 继续跳过 workflow
  - selector 会返回结构化输入摘要，包括 `selector_state`、`matched_keyword_groups`、`matched_keywords`、`context_fields`
  - 补充 selector 单测，覆盖默认编码选择、runtime skip、route-task 透传 workflow 选择三条路径

- 2026-03-22 第二批 workflow profile registry 落地：
  - 新增运行时 `workflow-profile-registry.json`，把 `coding-default@stable` / `coding-default@candidate` 变成正式 registry 项
  - `policy_enforcer init` / `validate-runtime` 已纳入 registry 文件生成与校验
  - `policy_enforcer create-task` 会基于 registry 校验默认和显式 workflow 选择，未知 profile/channel 直接 fail-fast
  - 补充单测覆盖 init 写 registry、显式 candidate、非法 profile 拒绝三条关键路径

## 2026-03-22

- 完成默认编码工作流架构文档收口：
  - 明确 `HardFlow Core` 是共享底座
  - 明确 `coding-default` 是唯一默认 workflow profile
  - 明确 workflow / capability / skill / hook 的分层边界
- 完成平台总入口逻辑收口：
  - 明确整体顺序是“需求澄清 -> 任务拆分 -> workflow 选择 -> 执行”
  - 明确 `coding-default` 是默认执行工作流，不是平台第一步
- 完成工作流地图与升级路线图同步：
  - 把当前默认入口解释为 `coding-default@stable`
  - 把后续路线收口到 `stable/candidate` 晋升机制
  - 明确“当前只做仓内自升级，不做外部下载市场”
- 新增基建规格文档：
  - 明确哪些属于平台基建，哪些属于 workflow 配置
  - 明确“评分框架放基建，评分标准放 workflow”
  - 明确“输出框架放基建，输出内容放 workflow”
  - 明确“人工介入机制放基建，触发策略可由 workflow/policy 决定”
  - 明确“异常处理框架放基建，异常策略可由 workflow 覆盖”
  - 明确“监控计量放基建，用于后续负载均衡与环节裁剪”
  - 补齐最小 manifest 字段表
- 新增 ADR：
  - `ADR 2026-03-22：默认编码工作流与 HardFlow Core 收口决策`
- 更新任务记录：
  - 把默认 workflow profile manifest、晋升规则、任务层 `workflow_profile_id`、workflow selector 入口列入后续待办
- 完成第一批 workflow 选择链路代码落地：
  - `task_center` 已支持 `workflow_profile_id / workflow_channel / selection_reason / selection_inputs`
  - 新增 `workflow_selection_records`，把 workflow 选择从任务字段提升为独立审计记录
  - `policy_enforcer create-task` 已能按默认规则写入 `coding-default@stable`
  - `task_executor_runner` 的 preflight 与执行 prompt 已透传 workflow 归属信息
  - 完成对应单测补充与通过验证

## 2026-03-17

- 完成 `pm-website` 的 Telegram / OpenViking / cron 稳定运行基线。
- 完成 `pm-website` 的 `governance auto-pr -> reviewer 审查 -> approval gate 自动合并` 闭环验证。
- 补齐 `大白pm / nofx / coingod / tokyo-claw` 的 HardFlow 核心文件集。
- 完成多项目服务器模板文档、审批样例和 registry 样例入口。
- 完成多项目第二阶段本地实现：
  - per-repo governance job
  - per-repo reviewer PR gate job
  - per-repo git sync job
  - per-repo auto update install job
- 完成相关定向测试与样例 JSON 校验。
- 完成多项目第二阶段提交并推送到 GitHub 主线：
  - `b627851 feat: support multi-project repo job installation`
- 完成 `pm-website` 远端多项目 dry-run：
  - 使用临时 sample registry
  - 关闭 `discovery.enabled`
  - 成功派生并验证 `lobster` 与 `openclaw-hardflow-backup-20260302-deploy` 的 governance / reviewer / git sync / auto update job
- 完成 `pm-website` 首个正式多项目节点落地：
  - 正式 `project-registry.json` 已写入
  - `lobster` 的 per-repo governance / reviewer PR gate 已正式安装
  - `project_index_maintainer_30m` 已切到正式 registry
  - `schedule-registry.json` 已重新导出
  - `openclaw-hardflow-backup-20260302-deploy` 因与 workflow repo 共享 remote，未纳入正式 PR gate
- 完成 `lobster` 的一次手动闭环演练：
  - governance 已触发
  - reviewer gate 已触发
  - governance 实际停在 `changes_scoped_count = 0` 后的 `invalid_branch_for_pr`
  - reviewer 成功读取 16 个 open PR，但没有命中 approval 规则，因此未 merge
- 完成 `lobster` governance scoped 规则修复：
  - 修正 `changes_scoped_count = 0` 时仍尝试 auto-pr 的逻辑
  - `install_governance_evolution_job.py` 支持 `--watch-prefix / --exclude-prefix`
  - `install_workflow_profile.py` 支持从 `project-registry` 读取 per-repo `governance.watch_prefixes / exclude_prefixes / auto_pr_enabled`
  - `pm-website` 上 `lobster` 正式 registry 已写入治理范围配置
  - 远端重跑后 `changes_scoped_count = 14`
  - `auto_pr.attempted = false`
  - `invalid_branch_for_pr` 已消失
- 完成 `lobster` 外部只读仓收口：
  - 确认 `XX-Trader` 对 `openclaw/lobster` 只有 `READ`
  - `lobster.governance.watch_prefixes` 移除 `package-lock.json`
  - 保留 `.workflow/` 在 `exclude_prefixes`
  - `lobster.governance.auto_pr_enabled = false`
  - 关闭 `reviewer_git_update_hourly:lobster`
  - 重新导出 `schedule-registry.json`
- 完成 5 台服务器最新版本部署：
  - `pm-website / 大白pm / nofx / coingod / tokyo-claw` 全部同步到 `7ed232f`
  - 全部执行 `install_workflow_profile.py --profile core`
  - 全部确认 `openclaw-gateway.service = active`
  - 本轮只做部署与存活校验，不做功能测试
- 完成 `task_executor_10m` 通知收口：
  - 首报后转增量
  - 无变化静默
  - 人类摘要压缩为“事项 / 负责人 / 进展 / 问题 / 待补”
- 2026-03-23 第三十一批控制面优化建议派发层落地：
  - 已新增 `scripts/openclaw-ops/control_plane_optimization_dispatcher.py`
  - `cron_setup.py` 已新增 `build_control_plane_optimization_dispatch_job(...)` 与 `control-plane-optimization-dispatch-*` 参数
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动安装 `control-plane-optimization-dispatch` job
  - optimization recommendation 现在可去重包装为 task-center 正式任务，并保留目标 workflow/stage 审计信息
  - 已补并通过 dispatcher / install / acceptance / UTF-8 entrypoint 专项测试
- 2026-03-23 第三十二批控制面 live 验收层落地：
  - 已新增 `scripts/openclaw-ops/control_plane_live_acceptance_runner.py`
  - `cron_setup.py` 已新增 `build_control_plane_live_acceptance_job(...)` 与 `control-plane-live-acceptance-*` 参数
  - `install_workflow_profile.py` 生成的默认 cron setup 命令已自动安装 `control-plane-live-acceptance` job
  - live acceptance 现在会在隔离工作区实跑 advisor / dispatch / summary / consumer / dashboard / acceptance 主链
  - 已补并通过 live acceptance / install / UTF-8 entrypoint 专项测试
- 2026-03-23 第四十三批 trace_id 与 ExecutionEnvelope 最小主链闭环：
  - `create-task` 现在会统一生成或继承 `trace_id / attempt_id`
  - `selection_inputs` 现在固定补齐 `trace_id / attempt_id / execution_envelope`
  - `task_center.py` 现在让 `task_outputs / task_incidents / benchmark_runs` 继承任务级 `trace_id`
  - `task_report(...)` 现在会直接返回顶层 `trace_id / attempt_id`
  - `task_executor_runner.py` 的 `build_task_preflight(...)` 现在会透传 `trace_id / attempt_id / execution_envelope`
  - 定向回归 `test_task_center_capability_fields + test_task_executor_preflight + test_policy_task_capability_args` 已通过

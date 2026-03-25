# Workflow Selection Runtime Implementation Plan

## 标准入口

- 第四十批基建输入输出与通信标准收口
- 基建设施输入输出与通信标准
- 基建设施模板文档
- ExecutionEnvelope

## 2026-03-24 第四十四批需求包硬门禁最小收口

- `create-task / route-task / preflight` 现在统一暴露 `requirement_package_gate`
- 当前门禁范围收紧到：
  - `request_source=human`
  - `task_type=workflow`
- 自动触发只认两类高置信信号：
  - 显式 `requirement_package_required=true`
  - 强项目型需求措辞，例如 `project requirement / requirement package / PRD / 需求文档`
- `workflow / readme` 这类弱词不再单独触发门禁，避免误伤普通 `docs / research / ops` 任务
- 当前最小必填需求包字段：
  - `goal`
  - `success_criteria`
  - `scope.in_scope`
  - `scope.out_of_scope`
- 缺失时自动 reroute 到 `clarification_required` 并交给 `project-agent`

## 2026-03-24 第四十五批 ExecutionEnvelope 主链扩展

- `TaskCenter` 现在会为任务自动补齐最小 `execution_envelope` 快照
- `task_output / incident / benchmark_run` 现在统一继承：
  - `trace_id`
  - `attempt_id`
  - `execution_envelope`
- `task_report(...)` 现在直接暴露顶层 `execution_envelope`
- `report_agent_result` 生成的 `standard_output` 现在也带 `trace_id / attempt_id / execution_envelope`
- 这一步把统一执行信封从“create-task / preflight”继续推进到了“output / incident / benchmark / report”

## 2026-03-24 第四十六批 删环节候选证据门槛收口

- `stage_simplification_candidate` 现在不再只是低风险建议文本，而是会携带结构化 `evidence`
- `optimization review` 现在会根据 `task_count / benchmark_promoted_count / incident / human_assistance / clarification` 生成 `profile_update_guard`
- 只有 guard 通过的删环节候选，才允许继续进入 `profile_update_dispatch`
- `profile_update_apply` 对删环节候选新增第二道兜底门槛：缺少 guard 或 guard 未通过时，不允许回写 candidate registry
- 当前回写策略仍然是 `deletion_mode=suggest_only`，属于候选优化，不是直接自动删除 stage

## 2026-03-24 第四十七批 Capability 声明式装配快照扩展

- `resolve_task_capability_binding(...)` 现在会返回完整装配快照，而不只是不透明的 runtime/tool 合并结果
- 新增装配快照字段：
  - `capability_declarations`
  - `capability_contracts`
  - `resolved_agent_profile`
- `create-task` 现在会把这份装配快照写入 `selection_inputs.capability_binding`
- `execution_envelope.capability_binding` 现在同步继承这份快照
- `preflight` 现在直接暴露 `resolved_assignee / resolved_agent_profile / capability_declarations / capability_contracts`

## 2026-03-23 第四十二批 工作流进化闭环收口
- 从当前主线移除高级负载均衡，不再继续推进 `load_balance_stage_candidate`
- `stage_execution_strategy` 收紧为：
  - `parallel_execution`
  - `simplification_hint`
  - `optimization_hints`
- `stage_simplification_candidate` 明确归类为工作流进化闭环中的优化策略，不视为新的业务 workflow
- 历史 `load_balance_stage_candidate` 任务在 `profile_update_apply` 中改为安全跳过，避免旧任务阻塞回写链

## 2026-03-23 ????? ????????????????
- ? `??? / ???? / ?????` ?????????????????? 5 ? workflow?
- ?? recommendation?`load_balance_stage_candidate`
- ?? stage ???`load_balancing_hint`
- ?? runtime ???`stage_execution_strategy`
- ???????`ExecutionEnvelope`
- ??????advisor -> dispatcher -> apply -> create-task -> preflight -> executor prompt

## 2026-03-23 第四十批基建输入输出与通信标准收口
- 新增正式 ADR：
  - [基建设施输入输出与通信标准](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/adr/2026-03-23-openclaw-foundation-contract-standard.md)
- 新增正式模板文档：
  - [基建设施模板文档](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/templates/openclaw-foundation-contract-templates.md)
- 重写可读版运行时字段字典：
  - [FIELD_DICTIONARY.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)
- 这批收口的目标是把当前已经落在代码里的对象统一成正式基建标准：
  - `HumanRequestEnvelope`
  - `TaskEnvelope`
  - `AgentExecutionInput`
  - `AgentMessageEnvelope`
  - `AgentResultEnvelope`
  - `StandardOutputPacket`
  - `IncidentEnvelope`
  - `BenchmarkRunEnvelope`
- 同时明确后续必须继续补齐：
  - `trace_id` 全链路统一
  - `ExecutionEnvelope`
  - 统一错误码与结构化 logger 规范

## 2026-03-23 第三十九批 阶段优化提示进入运行时主链
- `policy_enforcer.py`
  - 新增 `evaluate_stage_context_gate(...)`
  - 新增 `apply_stage_selection_inputs(...)`
  - `create-task` 现在会消费 stage 上的 `clarification_required_fields / parallel_execution / simplification_hint / optimization_hints`
  - 当 implement 等执行阶段缺少必要澄清字段时，会自动 reroute 到 `clarification_required`
- `task_executor_runner.py`
  - preflight 现在会透传 `stage_context_gate / stage_parallel_execution / stage_simplification_hint / stage_optimization_hints`
  - 执行 prompt 已同步展示这些字段
- 目标：把 `profile_update_apply -> workflow-profile-registry.json` 的变更真正接进运行时主链，而不是只停留在 registry

## 2026-03-23 第三十八批 ROI 分层与 install-surface job 回放落地
- `control_plane_dashboard.py` 已新增 `workflow_roi_breakdown / stage_roi_breakdown`
  - Markdown 新增 `Workflow ROI / Stage ROI`
  - HTML 看板也已同步展示这两层分布
- `control_plane_optimization_advisor.py` 已新增 `stage_roi_breakdown`
  - recommendation 现在会挂接对应 `roi_context`
  - Markdown 已补 `Stage ROI` 分层摘要
- `control_plane_live_acceptance_runner.py` 已新增 `installed_job_replay`
  - 在 install-surface 真实生成 `jobs.json` 后，继续回放关键控制面 job
  - 当前已覆盖 `summary / dashboard / optimization / profile_update / acceptance` 关键链路

## 2026-03-23 第三十七批 dashboard HTML 产品层落地
- `control_plane_dashboard.py` 现在会同步输出静态 HTML 看板
- 已接入 `cron_setup.py`、`install_workflow_profile.py`
  - dashboard job 新增 `--html-output`
- 已接入 `control_plane_acceptance_runner.py` 与 `control_plane_live_acceptance_runner.py`
  - acceptance 会校验 HTML 参数契约
  - live acceptance 会实跑并检查 HTML 产物存在

## 2026-03-23 第三十六批 profile update 定向 benchmark 验证落地
- 已新增 `control_plane_profile_update_validation_runner.py`
  - 读取 `profile_update_apply` 报告
  - 只对受影响 workflow 触发定向 benchmark suite 验证
  - 使用 `change_id` 状态文件做去重，避免重复验证
- 已接入 `cron_setup.py`、`install_workflow_profile.py`、`control_plane_acceptance_runner.py`、`control_plane_live_acceptance_runner.py`
  - 新增正式 job：`ops_control_plane_profile_update_validation_12h`

## 2026-03-23 第三十五批 profile update 回写闭环落地
- 已新增 `control_plane_profile_update_applier.py`
  - 读取最近已完成的 `workflow_profile_update` 任务
  - 对通过控制面门禁的任务，把变更回写到目标 workflow registry
  - 当前默认只回写 `candidate` channel，并记录 `profile_update_history`
- 已接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_profile_update_apply_job(...)`
  - 默认安装 `ops_control_plane_profile_update_apply_12h`
- 已接入 `control_plane_acceptance_runner.py`
  - 静态验收现在会校验 apply job
- 已接入 `control_plane_live_acceptance_runner.py`
  - live acceptance 现在会在 `profile_update_dispatch` 之后继续实跑 `profile_update_apply`
- 已补专项测试
  - `test_control_plane_profile_update_applier.py`
  - `test_control_plane_acceptance_runner.py`
  - `test_control_plane_live_acceptance_runner.py`
  - `test_upgrade_feedback_runner.py`
  - `test_utf8_cli_entrypoints.py`

## 2026-03-23 第三十四批 profile update 派发层落地
- 已新增 `control_plane_profile_update_dispatcher.py`
  - 读取 `control_plane_optimization_review_runner.py` 生成的 review report
  - 仅对 `ready_for_profile_update=true` 的项创建 `workflow_profile_update` 正式任务
  - 对相同 `change_id` 做 open-task 去重，避免重复派发
- 已接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_profile_update_dispatch_job(...)`
  - 默认安装 `control-plane-profile-update-dispatch` job
  - 默认每 12 小时运行一次，默认延迟 `600000ms`
- 已把这条链接进 `control_plane_live_acceptance_runner.py`
  - live acceptance 现在会在 optimization review 之后继续实跑 profile update dispatch
- 已补专项测试
  - `test_control_plane_profile_update_dispatcher.py`
  - `test_control_plane_acceptance_runner.py`
  - `test_control_plane_live_acceptance_runner.py`
  - `test_upgrade_feedback_runner.py`
  - `test_utf8_cli_entrypoints.py`

## 2026-03-23 第三十三批 optimization review 闭环修正
- `control_plane_optimization_review_runner.py` 现把 `pending` 与 `blocked` 口径分开
  - `pending_count` 只统计待执行项
  - `blocked_count` 不再把 `pending` 混入阻塞项
- 已修正 review job 的 cron/install 断言
- 已补 `control_plane_optimization_review_runner.py` 的 UTF-8 入口守护测试覆盖

## 2026-03-23 第三十二批控制面看板趋势层落地
- `control_plane_dashboard.py` 已从静态快照升级为趋势看板快照
  - 新增最近 N 天趋势统计，默认最近 7 天
  - 新增按 workflow 的历史分布视图
  - 修复 dashboard 输出链上的高频中文乱码文案
- CLI 现支持 `--trend-days`
  - 现有 dashboard cron job 不需要改命令，默认就会输出趋势层
- 已补 `test_control_plane_dashboard.py`
  - 覆盖 benchmark / incident / human_assistance 趋势统计
  - 覆盖 workflow 分布
  - 覆盖 Markdown 中文输出与 CLI 参数

## 2026-03-23 第三十批控制面长链路验收 runner 落地
- 已新增 `control_plane_acceptance_runner.py`
  - 读取安装后的 `jobs.json`
  - 校验 6 条关键控制面 job 的存在性、启用状态、`delivery.mode` 与命令参数契约
  - 生成 `report.json + report.md`
- 已接入 `cron_setup.py`
  - 新增 `build_control_plane_acceptance_job(...)`
  - 新增 `control-plane-acceptance-*` 参数族
  - 默认每 12 小时执行一次，默认延迟 `420000ms`
- 已接入 `install_workflow_profile.py`
  - 默认安装 `control-plane-acceptance` job
  - 默认读取 `cron/jobs.json`
  - 默认输出到 `ops/control-plane-acceptance/latest-report.json`
  - 默认同时写出 `ops/control-plane-acceptance/latest-report.md`
- 已补测试
  - `test_control_plane_acceptance_runner.py`
  - `test_upgrade_feedback_runner.py`
  - `test_utf8_cli_entrypoints.py`

## 2026-03-23 第二十九批中文显示链 CLI UTF-8 守护落地
- 已给 7 个直接输出中文摘要的 CLI 入口统一补上 `configure_process_utf8_stdio()`
  - `control_plane_summary_runner.py`
  - `control_plane_dashboard.py`
  - `control_plane_optimization_advisor.py`
  - `control_plane_acceptance_runner.py`
  - `task_output_consumer.py`
  - `benchmark_output_consumer.py`
  - `task_output_broadcast_runner.py`
  - `benchmark_orchestrator.py`
- 已补 `test_utf8_cli_entrypoints.py`
  - 守护这些入口必须显式启用 UTF-8 stdio
  - 防止后续新增控制面输出脚本时再次漏掉编码保护

## 2026-03-23 第二十八批能力声明式自动装配最小闭环落地
- `task_capability_binding.py` 已新增 `resolve_task_capability_binding(...)`
  - 基于 stage 所需 capability/skill 推导 assignee、allowlist 和解析原因
  - 保留 `capability_default_agents`、`skill_matched_agents` 作为审计线索
- `policy_enforcer.py` 的 `create-task` 已接入这条绑定逻辑
  - 未显式指定 assignee 时，`implement` 阶段自动绑定 `backend-dev`
  - `review` 阶段自动绑定 `reviewer`
  - 绑定结果写入 `selection_inputs.capability_binding`
- 已补 create-task 专项测试
  - 覆盖 implement 阶段默认执行角色
  - 覆盖 review 阶段默认评审角色

## 2026-03-23 第二十七批控制面优化建议层落地
- 已新增 `control_plane_optimization_advisor.py`
  - 基于最近 `task / incident / benchmark / promotion` 信号输出优化建议
  - 生成 `report.json + report.md`
  - 覆盖门禁强化、澄清补强、并行候选、环节裁剪候选
- 已接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_optimization_job(...)`
  - 默认安装 `control-plane-optimization` job
  - 默认每 12 小时运行一次，默认延迟 `360000ms`
- 已补 install/cron 专项测试
  - 覆盖 job 构造
  - 覆盖默认安装命令接线

## 2026-03-23 第二十六批控制面看板快照层落地
- 已新增 `control_plane_dashboard.py`
  - 复用 `collect_control_plane_summary(...)`
  - 生成静态 `dashboard.json + dashboard.md`
  - 汇总最近 `task / incident / benchmark / promotion` 信号
- 已把控制面汇总逻辑抽成纯收集函数
  - `control_plane_summary_runner.py` 新增 `collect_control_plane_summary(...)`
  - dashboard 与 summary runner 复用同一份事实来源
- 已补 dashboard 专项测试
  - 覆盖总览指标
  - 覆盖重点任务 Markdown
  - 覆盖 benchmark 概览
  - 覆盖 CLI 输出 JSON/Markdown

## 2026-03-22 第二十五批控制面汇总 job 落地
- 已新增 `control_plane_summary_runner.py`
  - 聚合最近 `task / incident / benchmark / promotion` 信号
  - 生成统一 `summary / event / human_text`
  - 使用 state 文件去重，避免重复公告
- 已在 `workflow_views.py` 新增 `build_control_plane_summary_event(...)`
  - 统一输出控制面汇总的人类视图和结构化事件
- 已把这条汇总链接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_summary_job(...)`
  - 默认安装 `control-plane-summary` announce job
  - 默认每 6 小时运行一次，默认延迟 `180000ms`
- 已补 runner / event / install / cron 专项测试
  - 覆盖事件渲染
  - 覆盖去重逻辑
  - 覆盖默认安装命令接线

## 2026-03-22 第二十四批 task 控制面广播 job 落地
- 已新增 `task_output_broadcast_runner.py`
  - 扫描最近有控制面变化的 task
  - 复用 `task_output_consumer.py` 渲染单 task 输出
  - 通过 state 文件去重，只广播新的可见事件
- 已在 `task_center.py` 新增 `recent_control_plane_task_ids(...)`
  - 按 `tasks/task_outputs/task_incidents/benchmark_runs` 四类控制面信号聚合最近 task 候选
- 已把这条广播链接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_task_output_broadcast_job(...)`
  - 默认安装 `task-output-broadcast` announce job
- 已补 runner/cron/install 专项测试
  - 覆盖去重逻辑
  - 覆盖 job delivery 模式与默认安装命令接线

## 2026-03-22 第二十三批 benchmark 输出通知 job 落地
- 已新增独立 `benchmark output` 定时任务
  - `cron_setup.py` 新增 `build_benchmark_output_job(...)`
  - 使用 `benchmark_output_consumer.py` 渲染统一通知文本
  - `delivery.mode=announce`，走正式 cron delivery 通道
- 已把这条 job 接进 `install_workflow_profile.py`
  - 默认启用 `--install-benchmark-output-job`
  - 默认读取 `benchmark-sweeps/sweeps/latest-summary.json`
  - 默认把统一 payload 写入 `benchmark-sweeps/output/latest-event.json`
  - 默认延迟 `300000ms`，避开 benchmark sweep 本体
- 已补 install/cron 专项测试
  - 覆盖 benchmark output job 构造
  - 覆盖默认安装命令接线

## 2026-03-22 第二十二批 benchmark 输出调度接线
- 已把 benchmark 输出 consumer 接进 benchmark sweep job 主链
  - `cron_setup.py` 的 `build_benchmark_sweep_job(...)` 现在会在 sweep 完成后继续调用 `benchmark_output_consumer.py`
  - 默认消费 `benchmark-sweeps/sweeps/latest-summary.json`
  - 默认把统一 payload 写入 `benchmark-sweeps/output/latest-event.json`
- 已把这组参数接进 `install_workflow_profile.py`
  - 默认 cron setup 命令会自动带上 `benchmark-sweep-output-*`
- 已补 install/cron 专项测试
  - 覆盖 benchmark sweep job 命令已包含 output consumer
  - 覆盖默认安装命令已包含 consumer 相关参数

## 2026-03-22 第二十一批 benchmark sweep 统一输出消费层落地

- 已把 benchmark sweep 结果接入统一事件视图
  - `workflow_views.py` 新增 `build_benchmark_sweep_event(...)`
  - sweep summary 现在也能复用 `human/agent/external/storage` 四视图
- 已新增 `benchmark_output_consumer.py`
  - 读取 benchmark sweep summary
  - 输出统一 `event + human_text`
  - 支持 `--emit-json`
- 已补专项测试
  - 覆盖 benchmark sweep 人类摘要
  - 覆盖 benchmark output consumer payload 与 CLI

## 2026-03-22 第二十批 benchmark sweep 定时任务接线

- 已把 `benchmark_orchestrator.py` 接进 `cron_setup.py`
  - 新增 `build_benchmark_sweep_job(...)`
  - 新增 `--install-benchmark-sweep-job`
  - 新增 `benchmark-sweep-*` 参数族
- 已把 benchmark sweep 接进 `install_workflow_profile.py`
  - 默认 cron setup 命令会自动带上 benchmark sweep job
  - 默认覆盖 `coding-default-core`、`research-default-core`、`docs-default-core`、`ops-default-core`
  - 默认保守运行：`--no-benchmark-sweep-auto-create-tasks`、`--no-benchmark-sweep-auto-apply-workflow-promotion`
- 已补 install/cron 专项测试
  - 覆盖 benchmark sweep job 命令渲染
  - 覆盖默认安装命令接线

## 2026-03-22 第十九批 benchmark 编排控制面落地

- 已新增 `scripts/openclaw-ops/benchmark_orchestrator.py`
  - 支持 `list-suites`、`run-suite`、`run-all`
  - 复用 `upgrade_feedback_runner.py`，不重复实现评分、任务派发与晋升逻辑
- 已把 benchmark 执行从“只有 registry + runner”推进到“有独立控制器入口”
  - 单 suite 结果写入 `output_root/suites/<suite_id>`
  - 单 suite 状态写入 `state_root/<suite_id>.json`
  - sweep 总摘要写入 `output_root/sweeps/latest-summary.json`
- 已补 benchmark controller 专项测试
  - 覆盖 suite 列表
  - 覆盖单 suite 执行
  - 覆盖多 suite sweep

## 2026-03-22 第十八批第四个正式 workflow profile 落地

- 已把 `ops-default` 落成第四个正式 workflow profile
  - `workflow-profile-registry.json` 现新增 `ops-default@stable` / `ops-default@candidate`
  - ops workflow 现具备 `clarify -> stabilize -> verify` 三个 stage
  - `stabilize` stage 绑定 `task_execution + routing`
- 已把 selector 扩展到 ops 关键词组自动选 profile
  - 命中 `ops_task` 时会自动路由到 `ops-default@stable`
  - 默认编码、研究、文档 workflow 的既有路由行为保持不变
- 已把 benchmark registry 扩展到第四个正式 workflow
  - 默认 benchmark suite 现在同时包含 `coding-default-core`、`research-default-core`、`docs-default-core`、`ops-default-core`
  - `upgrade_feedback_runner.py` 内置默认 suite 也已同步
- 已补齐专项验证
  - 覆盖 `cmd_init` 写出第四个 workflow profile 与第四个 benchmark suite
  - 覆盖 selector 命中 ops 关键词后的自动路由
  - 覆盖 `create-task` 自动选 ops workflow 并落 `stabilize` stage

## 2026-03-22 第十七批第三个正式 workflow profile 落地

- 已把 `docs-default` 落成第三个正式 workflow profile
  - `workflow-profile-registry.json` 现新增 `docs-default@stable` / `docs-default@candidate`
  - docs workflow 现具备 `clarify -> draft -> review` 三个 stage
  - `draft` stage 绑定 `project_context + skill_backed + routing`
- 已把 selector 扩展到 docs 关键词组自动选 profile
  - 命中 `docs_task` 时会自动路由到 `docs-default@stable`
  - 默认编码与研究 workflow 的既有路由行为保持不变
- 已把 benchmark registry 扩展到第三个正式 workflow
  - 默认 benchmark suite 现在同时包含 `coding-default-core`、`research-default-core`、`docs-default-core`
  - `upgrade_feedback_runner.py` 内置默认 suite 也已同步
- 已补齐专项验证
  - 覆盖 `cmd_init` 写出第三个 workflow profile 与第三个 benchmark suite
  - 覆盖 selector 命中 docs 关键词后的自动路由
  - 覆盖 `create-task` 自动选 docs workflow 并落 `draft` stage

## 2026-03-22 第十六批第二个正式 workflow profile 落地

- 已把 `research-default` 落成第二个正式 workflow profile
  - `workflow-profile-registry.json` 现新增 `research-default@stable` / `research-default@candidate`
  - research workflow 现具备 `clarify -> investigate -> synthesize` 三个 stage
  - `investigate` stage 绑定 `project_context + skill_backed + routing`
- 已把 selector 从“只识别关键词”推进到“按关键词组选 profile”
  - `workflow_selection_policy` 现支持 `keyword_group_priority`
  - `workflow_selection_policy` 现支持 `keyword_group_profile_map`
  - 命中 `research_task` 时会自动路由到 `research-default@stable`
- 已把 benchmark registry 扩展到多正式 workflow
  - 默认 benchmark suite 现在同时包含 `coding-default-core` 与 `research-default-core`
  - `upgrade_feedback_runner.py` 内置默认 suite 也已同步
- 已补齐专项验证
  - 覆盖 `cmd_init` 写出第二个 workflow profile 与第二个 benchmark suite
  - 覆盖 selector 命中 research 关键词后的自动路由
  - 覆盖 `create-task` 自动选 research workflow 并落 `investigate` stage

## 2026-03-22 第八批 stage gate / score / evidence contract 落地记录

- 已把 workflow stage 的最小合同字段接进 manifest
  - runtime `workflow-profile-registry.json` 的每个 stage 新增 `score_gate`
  - runtime `workflow-profile-registry.json` 的每个 stage 新增 `min_evidence_count`
  - runtime `workflow-profile-registry.json` 的每个 stage 新增 `output_contract`
  - runtime `workflow-profile-registry.json` 的每个 stage 新增 `verification_contract`
- 已把 stage 合同字段接入任务主链
  - `policy_enforcer create-task` 会把 stage 合同写入 task payload
  - `task_center` 会持久化 `stage_score_gate`、`stage_min_evidence_count`
  - `task_center` 会持久化 `stage_output_contract`、`stage_verification_contract`
  - `task_executor_runner` preflight 与 prompt 会透传 stage 合同
- 已补齐专项验证
  - workflow registry 初始化会写出 stage gate / evidence contract
  - create-task 会把 stage 合同落到 task-center
  - preflight 可以读取并透传 stage 合同

## 2026-03-22 第九批 stage contract 运行时评估落地记录

- 已把 stage 合同从静态字段推进到运行时评估
  - `task_executor_runner` 会根据 agent 结构化回报生成 `stage evidence`
  - `task_executor_runner` 会校验 `min_evidence_count`
  - `task_executor_runner` 会校验 `output_contract.deliverables`
  - `task_executor_runner` 会校验 `verification_contract.checks`
- 已把运行时评估结果接入审计主链
  - `post_stage` 现在支持透传 `details_json`
  - `stage_runs.details` 现可落 `stage_contract`
  - `report-agent-result details_json` 也会带上 `stage_contract`
- 已补齐专项验证
  - 覆盖 `evaluate_stage_contract(...)` 正常通过场景
  - 覆盖缺少验证证据时的失败场景
  - 覆盖 `post_stage` 将 `stage_contract` 合并写入 `stage_runs.details`

## 2026-03-22 第十批 stage contract gate 接入结果判定与升级分析

- 已把 `stage_contract` 接入结果判定主链
  - `report_agent_result` 现在会检查 `details_json.stage_contract`
  - 当 `contract_passed = false` 且原始结果不是 `failed/escalated` 时，会自动降级成 `partial`
  - 同时会把 task action 收口到 `retry`
  - 会自动补齐 `stage_contract_failed`、`stage_contract_missing_deliverable:*`、`stage_contract_failed_check:*`
- 已把 `stage_contract` 接入升级分析
  - `task_executor_runner` 的执行结果现在会显式写 `reason=stage_contract_failed`
  - `upgrade_analysis` 现在会统计 `stage_contract_failure_count`
  - `workflow_upgrade_scoring` 已能在 baseline/candidate 对比中看到这类失败
- 已补齐专项验证
  - 覆盖 `report_agent_result` 降级为 `partial + retry`
  - 覆盖 `workflow upgrade scorecard` 统计 `stage_contract_failure_count`

## 2026-03-22 第十二批统一输出信号接入 complete-task 与 promotion veto

- 已把统一输出 / incident 信号接入任务完成门禁
  - `complete-task` 现在会读取最近一条 `agent_report` 输出包中的 `human_gate`
  - `complete-task` 现在会读取 open `task_incidents`
  - 若仍存在 `requires_human_assistance` 或 open critical incident，则不会被高分直接判通过
- 已把统一输出 / incident 信号接入 workflow promotion veto
  - `upgrade_analysis` 新增 `human_assistance_count`、`incident_count`、`open_incident_count`、`critical_incident_count`
  - `workflow_upgrade_scoring` / `skill_evolution_review` 现在会把这些信号带入 `build_promotion_decision`
  - 当 candidate 仍有 critical incident，或 human assistance / open incident 没有改善时，会写入 `decision.veto_reasons`
- 已把这些信号透传回 executor report
  - `task_executor_runner` 的结果摘要现在会附带 `standard_output`、`human_gate`、`incident`
- 已补齐专项验证
  - 覆盖 `complete-task` 遇到 open critical incident 时强制升级
  - 覆盖 `workflow scorecard` 因 human assistance + critical incident 被 veto

## 2026-03-22 第十三批 benchmark suite / benchmark runs 最小落地

- 已把 benchmark suite 正式落成运行时对象
  - 新增 `benchmark-suite-registry.json`
  - `policy_enforcer init` 现会写出默认 `coding-default-core` benchmark suite
- 已把 benchmark run 接入任务中心
  - `task_center` 新增 `benchmark_runs` 表
  - 新增 `record_benchmark_run(...)` / `list_benchmark_runs(...)` / `list_benchmark_runs_by_suite(...)`
- 已把 benchmark suite 接入 upgrade feedback 主链
  - `upgrade_feedback_runner` 支持 `--benchmark-suite-file` / `--benchmark-suite-id`
  - runner summary 现会包含 `benchmark_suite`、`benchmark_run`、`promotion_bundle`
  - 当提供 `task-db` 时，会自动把 benchmark run 写入 `task_center`
- 已补齐专项验证
  - 覆盖 `cmd_init` 写 benchmark suite registry
  - 覆盖 `task_center` benchmark run 落盘与查询
  - 覆盖 `upgrade_feedback_runner` 的 benchmark bundle 和 task_center benchmark run 记录

## 2026-03-22 第十四批 benchmark 默认接线 + incident 生命周期 + task-report 控制面视图

- 已把 benchmark suite 默认接到安装与 cron 主链
  - `cron_setup.py` 的 upgrade feedback job 现在支持 `--benchmark-suite-file` / `--benchmark-suite-id`
  - `install_workflow_profile.py` 构建出的默认 cron setup 命令会自动传入 runtime `benchmark-suite-registry.json`
  - 默认 suite 固定为 `coding-default-core`
- 已把 incident 生命周期推进到可人工闭环
  - `task_center` 新增 `update_task_incident(...)`
  - `policy_enforcer` 新增 `update-task-incident` CLI
  - 现在可把 incident 从 `open` 推进到 `acked/resolved/suppressed`
- 已把 task-report 扩成控制面统一视图
  - `task_report(...)` 现在会带出 `task_outputs`
  - `task_report(...)` 现在会带出 `task_incidents`
  - `task_report(...)` 现在会带出 `benchmark_runs`
  - `task_report(...)` 现在会带出 `control_plane` 摘要，直接给出最近输出、最近 incident、open incident、benchmark suite
- 已补齐专项验证
  - 覆盖 upgrade feedback cron job 带 benchmark suite 参数
  - 覆盖 install workflow profile 生成的 cron setup 命令带 benchmark suite 参数
  - 覆盖 incident lifecycle 从 `open -> acked -> resolved`
  - 覆盖 task-report 扩展后仍保持展示安全视图

## 2026-03-22 第十五批统一输出消费层最小落地

- 已把 task 控制面接入统一视图模型
  - `workflow_views.py` 新增 `build_task_control_plane_event(...)`
  - 会把 `task_outputs/task_incidents/benchmark_runs/control_plane` 统一为 `human/agent/external/storage` 四视图
- 已新增统一输出消费脚本
  - 新增 `task_output_consumer.py`
  - 读取 `task_center.task_report(...)`
  - 输出标准 `event` 与 `human_text`
- 已补齐专项验证
  - 覆盖 open critical incident + benchmark veto 的人类摘要
  - 覆盖 clean task 在 `notify_on=error` 下返回 `NO_REPLY`
  - 覆盖 `task_output_consumer.py` 输出结构化 payload
  - 覆盖 `task_output_consumer.py --emit-json`

## 2026-03-22 第五批 workflow stage manifest 落地记录

- 已把 `workflow profile -> stage -> required_capabilities` 接成正式 manifest
  - runtime `workflow-profile-registry.json` 新增 `default_stage_id`
  - runtime `workflow-profile-registry.json` 新增 `task_type_stage_map`
  - runtime `workflow-profile-registry.json` 新增 `stages`
- 已把 `stage_id` 接入任务主链
  - `policy_enforcer create-task` 会自动解析 stage
  - `task_center` 会持久化 `stage_id`
  - `task_executor_runner` preflight 与 prompt 会透传 `stage_id`
- 已补齐专项验证
  - workflow registry 初始化会写出 stage manifest
  - create-task 会自动合并 stage capability
  - task center / preflight 均能看到 `stage_id`

## 2026-03-22 第四批 capability registry 最小落地记录

- 已新增 runtime `scripts/openclaw-ops/policy/capability-registry.json`
  - 正式收口 `capability_id -> allowed_agents/default_agent/contracts`
  - 同时维护 `agent_defaults`，承接现有 assignee 默认约束推断
- 已把 `policy_enforcer.py` 接入 capability registry
  - `init` 会写出 `capability-registry.json`
  - `validate-runtime` 会校验 capability registry 文件存在
  - `create-task` 会在入库前校验 `required_capabilities`
- 已把 `task_capability_binding.py` 从散落硬编码收口成 registry helper
  - 保持 direct task backfill 现有输出不变
  - 对未知 capability 改为 fail-fast

## 2026-03-22 第三批 selector 落地记录

- 已新增 `select-workflow` 入口，并让 `route-task` / `create-task` 共用同一套 workflow selector。
- selector 当前先按最小规则工作：
  - `workflow` / `clarification_required` 默认进入 `coding-default@stable`
  - `ops_runtime_cron` 跳过 workflow 归属
- selector 会在 `selection_inputs` 中附带结构化摘要，包括 `selector_state`、`matched_keyword_groups`、`matched_keywords`、`context_fields`。
- 已补充单测覆盖：
  - selector 默认编码工作流
  - runtime binding skip
  - route-task 透传 workflow 选择结果

## 2026-03-22 第二批落地记录

- 已新增运行时 `workflow-profile-registry.json`，并把 `coding-default@stable` / `coding-default@candidate` 固化为正式 registry 项。
- `policy_enforcer init` 现在会自动写出 registry 文件，`validate-runtime` 也会校验 registry 默认项与 promotion target。
- `policy_enforcer create-task` 现在会基于 registry 校验显式或默认 workflow 选择，未知 profile/channel 会直接 fail-fast。
- 已补充单测覆盖：
  - init 自动生成 registry
  - 显式 candidate workflow 可创建任务
  - 未知 workflow profile 被拒绝

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 `workflow_profile_id / selection_reason / selection_inputs` 从文档口径落到任务中心与创建入口，实现默认 `coding-default@stable` 的最小可执行归属链路。

**Architecture:** 先在 `task_center` 增加 workflow 归属字段与选择记录存储，再把 `policy_enforcer create-task` 补成默认 workflow 选择入口，最后让执行前 preflight 能看到这些字段。当前阶段不实现完整多 workflow selector，只实现稳定默认链路与兼容迁移。

**Tech Stack:** Python 3、SQLite、argparse、unittest

---

### Task 1: 扩展任务中心 schema 与任务序列化

**Files:**
- Modify: `scripts/openclaw-ops/policy/task_center.py`
- Test: `tests/scripts_openclaw_ops/test_task_center_capability_fields.py`

**Step 1: 写失败测试**
- 为任务创建/更新补 `workflow_profile_id`、`workflow_channel`、`selection_reason`、`selection_inputs`
- 断言读取结果能返回结构化值

**Step 2: 实现最小 schema**
- 给 `tasks` 增加 workflow 归属字段
- 给任务行读取增加统一反序列化

**Step 3: 增加 workflow 选择记录存储**
- 新增 `workflow_selection_records` 表
- 任务创建时按字段自动写选择记录

**Step 4: 跑任务中心测试**
- 运行任务中心相关单测

### Task 2: 把 create-task 入口补成默认 workflow 选择入口

**Files:**
- Modify: `scripts/openclaw-ops/policy/policy_enforcer.py`
- Test: `tests/scripts_openclaw_ops/test_policy_task_capability_args.py`
- Test: `tests/scripts_openclaw_ops/test_runtime_binding_task_normalization.py`

**Step 1: 写失败测试**
- CLI 创建任务时未显式传入 workflow 信息，也要得到 `coding-default@stable`
- runtime binding 等特殊任务不强行绑定默认 coding workflow

**Step 2: 实现最小默认规则**
- 增加 CLI 参数
- 增加默认 workflow 推断
- 把 workflow 选择元数据写入 task payload

**Step 3: 跑入口测试**
- 运行 policy enforcer 相关单测

### Task 3: 执行前显示 workflow 归属信息

**Files:**
- Modify: `scripts/openclaw-ops/policy/task_executor_runner.py`
- Test: `tests/scripts_openclaw_ops/test_task_executor_preflight.py`

**Step 1: 写失败测试**
- preflight 返回结果里包含 workflow 归属

**Step 2: 实现最小透传**
- 让 preflight 和执行 prompt 带上 workflow 字段

**Step 3: 跑 preflight 测试**
- 运行执行前检查相关单测

### Task 4: 文档与字段字典同步

**Files:**
- Modify: `scripts/openclaw-ops/policy/FIELD_DICTIONARY.md`
- Modify: `done.md`

**Step 1: 补字段说明**
- 标明 workflow 归属字段与选择记录字段

**Step 2: 记录完成情况**
- 更新 `done.md`
## 2026-03-23 第三十一批控制面优化建议派发层落地
- 已新增 `control_plane_optimization_dispatcher.py`
  - 读取 optimization advisor 的 `report.json`
  - 将 recommendation 去重派发为 task-center 正式任务
  - 默认以 `coding-default@stable` 作为执行 workflow，并在 `context_payload/selection_inputs` 中保留目标 workflow/stage
- 已接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_optimization_dispatch_job(...)`
  - 默认安装 `control-plane-optimization-dispatch` job
  - 默认每 12 小时运行一次，默认延迟 `480000ms`
- 已补专项测试
  - `test_control_plane_optimization_dispatcher.py`
  - `test_control_plane_acceptance_runner.py`
  - `test_upgrade_feedback_runner.py`
  - `test_utf8_cli_entrypoints.py`
## 2026-03-23 第三十二批控制面 live 验收层落地
- 已新增 `control_plane_live_acceptance_runner.py`
  - 使用隔离工作区与独立 task-center 样本库
  - 实跑 advisor、dispatch、summary、task output consumer、benchmark output consumer、dashboard、acceptance
  - 输出结构化 `report.json + report.md`
- 已接入 `cron_setup.py` 与 `install_workflow_profile.py`
  - 新增 `build_control_plane_live_acceptance_job(...)`
  - 默认安装 `control-plane-live-acceptance` job
  - 默认每 24 小时运行一次，默认延迟 `540000ms`
- 已补专项测试
  - `test_control_plane_live_acceptance_runner.py`
  - `test_upgrade_feedback_runner.py`
  - `test_utf8_cli_entrypoints.py`
## 2026-03-23 第四十三批 trace_id 与 ExecutionEnvelope 最小主链闭环
- `policy_enforcer.py`
  - `create-task` 现在会统一生成或继承 `trace_id / attempt_id`
  - `selection_inputs` 现在固定补齐 `trace_id / attempt_id / execution_envelope`
- `task_center.py`
  - `tasks / task_outputs / task_incidents / benchmark_runs` 现在都带 `trace_id`
  - `task_report(...)` 现在会直接返回顶层 `trace_id / attempt_id`
- `task_executor_runner.py`
  - `build_task_preflight(...)` 现在会透传 `trace_id / attempt_id / execution_envelope`
- 这一步的目标是先把最小执行追踪链做成 SSOT，为后续统一 logger、真实 live 验收、工作流进化执行器做准备

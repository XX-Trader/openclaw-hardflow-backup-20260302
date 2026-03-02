# OpenClaw 工作流整合报告（行情中心）

生成时间：2026-03-02 13:59:00 UTC+8

## 一、当前在运行的工作流

### A. OpenClaw cron（8个）
1. d8... log-watcher：日志巡检、异常告警、低风险自动修复
2. 16cb... todo-patrol：TODO + tester 失败项入池（todo/jobs）
3. 8752... ops-summary：归档、token采集、日报、系统摘要
4. 57ac... agent-factory：agent gap 扫描与自动创建（P1/P2）
5. 948d... optimize-governance：增量治理巡检
6. 8f91... optimize-frequency-manager：频率策略管理
7. 22b1... optimize-self-evolution：自我进化总结
8. 7e12... optimize-full-calibration：全量校准与修复

### B. crontab（用户级）
1. daily_todo_digest（每日）
2. hardflow experience maintain（daily/weekly/monthly）
3. timeout watchdog（每5分钟）

说明：旧 AGENT GAP WORKFLOW crontab 链路已删除，避免与 openclaw cron 的 gent-factory 双跑。

## 二、task-center 是否是一整套工作流

是。	ask-center 已具备完整闭环：
- 任务入池（todo/jobs）
- 分配（task_dispatcher）
- 状态流转
- 失败计数与升级人工
- token/cost 汇总
- 需求-结果-验收-评分-动作（通过/重试/升级人工）
- 每日汇总与留痕

结论：	ask-center 作为 统一任务中枢成立。

## 三、与其他工作流的重复点

1. **优化巡检重复**
- optimize-agent（结构/文件层）
- workflow_optimizer_review.py（运行输入输出层）

判定：不冲突，分层互补。建议都保留，但统一由 task-center 入池。

2. **任务治理入口重复**
- 	odo_patrol.py 与 ops_monitor_summary.py 都会建任务。

判定：可接受；已统一写入 task-center 且使用同一任务模型。

3. **日志留痕分散**
- cron/runs/*.jsonl（原始运行）
- 	ask-center/agents/*（按 agent 归档）
- 	ask-center/workflow-io/*（输入/输出结构化日志）

判定：已形成分层日志，定位效率高于单日志模式。

## 四、效率与可维护性评估

优先级建议：
1. **task-center + workflow-io（当前最高效）**
- 优点：结构化、可统计、可自动入池、便于定位问题。
- 修改成本低：核心集中在 ~/.openclaw/ops/*.py。

2. **optimize-agent（次优）**
- 优点：擅长增量扫描和治理策略。
- 缺点：与任务中枢不完全同源，需要通过 task-center 对齐。

3. **hardflow 经验维护（保留但边界明确）**
- 优点：经验沉淀与知识维护。
- 缺点：不是任务编排主链路，不应承载任务分配主逻辑。

## 五、已执行的去旧代码清理

已删除（历史迁移/安装脚本，不在运行链路）：
- workflows/openclaw-ops/install_agent_gap_cron.sh
- workflows/openclaw-ops/install_timeout_watchdog_cron.sh
- workflows/openclaw-ops/migrate_ops_workspace.sh
- workflows/openclaw-ops/migrate_workspace_ops_paths.sh

已删除（本轮死链路与死脚本）：
- crontab AGENT GAP WORKFLOW 块
- workflows/openclaw-ops/run_agent_gap_cron.sh
- workflows/openclaw-ops/coordinator_fallback_audit.py
- workspace/scripts/hardflow/agent-gap-v1.lobster.yaml
- workspace/scripts/hardflow/AGENT_GAP_WORKFLOW.md

已删除（历史备份配置）：
- ~/.openclaw/hardflow/hardflow.env.backup.*
- ~/.openclaw/hardflow/hardflow.env.bak.*

## 六、后续建议（单一主线）

1. 以 	ask-center 作为唯一任务状态源（SSOT）。
2. 所有工作流仅负责发现/执行，结果统一回写 task-center。
3. 运行日志统一沉淀到 	ask-center/workflow-io，日报固定读取该目录。
4. 对于不再运行的脚本，持续做引用扫描 + 清理。

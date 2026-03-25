# 内部反馈升级

## 目标

把 OpenClaw 内部运行留下来的日志、报告、失败模式和闭环情况，统一映射成：

- 问题摘要
- 归因分类
- 评分结果
- 升级落点

重点不是“把日志读一遍”，而是把问题稳定地指向应该修改的层。

## 优先读取的证据

- `~/.openclaw/ops/task-center/executor-runs/*.json`
- `~/.openclaw/ops/cron-runs/*.json`
- `~/.openclaw/ops/reviewer-scan-runs/*.json`
- `~/.openclaw/ops/system-schedule/snapshots/*.json`
- `~/.openclaw/ops/daily-work/reports/*`
- `~/.openclaw/ops/web-intel/reports/*`
- self / governance / conversation evolution 报告
- 任务中心里重复出现的 `fingerprint`、`dedupe_key`、`need_human_confirm`、`preflight` 失败

## 归因分类

固定先归到这 4 类之一，再决定落点：

1. `architecture_gap`
   - 问题边界不清
   - 不知道该改 repo 模板、runtime、skill 还是 workflow
   - SSOT 不明确，多个索引或状态互相漂移
2. `workflow_gap`
   - job 频率不对
   - runner、task-center、executor 的链路不顺
   - human confirm、git push、review gate、preflight 放错层
3. `skill_gap`
   - agent 不知道先看什么、怎么验证、哪里不能改
   - 同类失误重复出现
   - 输出结构、证据质量、边界控制不稳定
4. `runtime_gap`
   - manifest 路径错
   - gateway/auth/config 漂移
   - 线上安装态和仓库模板不一致

## 建议评分维度

### Workflow 评分

- `structure_clarity`
- `change_locality`
- `execution_stability`
- `closure_rate`
- `evidence_quality`
- `runtime_drift_control`
- `reuse_value`

### Skill 评分

- `trigger_precision`
- `instruction_clarity`
- `boundary_clarity`
- `verification_discipline`
- `failure_reduction`
- `operational_reuse`

## 最小可写面判定

优先顺序固定为：

1. 地图与设计文档
2. skill 规范与 references
3. manifest / binding / installer
4. runner / executor / policy
5. runtime overlay
6. 运行态现值

如果问题能在更高层收口，就不要先改更低层。

## 推荐输出格式

### 1. 问题摘要

- 哪一类 run 失败最多
- 哪些问题重复出现
- 哪些低分没有闭环

### 2. 证据

- 关键 run / report / log 路径
- 关键 warning / reason / failure_signals

### 3. 归因

- 属于 `architecture_gap` / `workflow_gap` / `skill_gap` / `runtime_gap`

### 4. 升级落点

- 应优先修改的文件
- 不建议先改的文件

### 5. 评分比较

- `baseline_score`
- `candidate_score`
- `delta`

## 脚本入口

当需要把这套流程固化成可重复执行的产物时，优先使用：

- `scripts/openclaw-ops/workflow_upgrade_scoring.py`
  - 输入 baseline / candidate reports
  - 输出 workflow scorecard JSON
- `scripts/openclaw-ops/skill_evolution_review.py`
  - 输入 baseline / candidate reports
  - 输出 skill review markdown / JSON
- `scripts/openclaw-ops/upgrade_feedback_runner.py`
  - 读取 executor-runs 目录
  - 自动切 baseline / candidate 窗口
  - 输出 scorecard、review 与 summary
  - 可按阈值把低分候选自动建成 `workflow_upgrade` / `skill_upgrade` 任务，并用 `change_id` 去重
- `scripts/openclaw-ops/upgrade_analysis.py`
  - 统一承载报告解析、根因分类、评分、晋升判断

## 何时判定“应该升级 skill”

满足任一条件就优先考虑 skill 升级，而不是只修一次结果：

- 同类错误连续两轮以上出现
- agent 总在相同步骤失误
- workflow 已正确，但 agent 输出仍不稳定
- 证据不足、越界修改、验证遗漏重复出现

## 何时判定“应该升级 workflow”

满足任一条件就优先考虑 workflow 升级：

- job 频率、依赖或执行顺序经常导致问题
- task-center 和 executor 的边界不清
- push / PR / human confirm / review gate 放错层
- 任务发现、派单、执行、回写链条经常断开

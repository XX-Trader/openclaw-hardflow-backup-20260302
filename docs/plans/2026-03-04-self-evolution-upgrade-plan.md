# 自我进化机制升级实施计划（Phase 1）

日期：2026-03-04  
负责人：Codex（执行）  
范围：先落地“记忆分层 + 积分账本 + 保底派单”，不做破坏性重构

## 1. 目标与验收标准

### 1.1 目标
- 记忆不再全量无差别召回，改为按优先级层级召回。
- 每个 agent 有独立记忆视图（同仓库内按 `agentId` 分桶）。
- 任务完成后自动生成积分流水，用于后续调度优化。
- 低分 agent 在 TODO 队列中有保底任务机会，避免长期“饿死”。

### 1.2 验收标准
- 召回阶段优先读取优先级桶文件；桶缺失时才降级为旧逻辑。
- 经验卡新增 `memoryTier/priorityScore/agentId` 字段（兼容旧数据）。
- `planner-summary` 保持可用；新增积分统计接口不影响旧接口。
- `next-todo` 返回结果中体现保底调度信息（命中与否、原因）。

## 2. 实施阶段

### 阶段 A：记忆分层与优先级召回
- 修改文件：
  - `hooks/_lib/experience.ts`
  - `hooks/hardflow-experience-capture/handler.ts`
  - `hooks/hardflow-experience-recall/handler.ts`
  - `scripts/hardflow/experience-maintain.mjs`
- 关键改动：
  - 经验卡增加层级字段：`reflex | long_term | recent | archive`。
  - 维护脚本输出优先级桶：`maintenance/priority-buckets.json`。
  - 召回优先使用桶 + agent 维度过滤。

### 阶段 B：积分账本与奖惩计算
- 修改文件：
  - `scripts/openclaw-ops/policy/task_center.py`
  - `scripts/openclaw-ops/policy/policy_enforcer.py`
  - `scripts/openclaw-ops/policy/policy-config.json`
- 关键改动：
  - 新增积分流水表（agent + planner 两类）。
  - `report-agent-result` 后自动入账积分。
  - 新增积分汇总查询（供调度使用）。

### 阶段 C：低分 agent 保底派单
- 修改文件：
  - `scripts/openclaw-ops/policy/policy_enforcer.py`
  - `scripts/openclaw-ops/policy/policy-config.json`
- 关键改动：
  - `next-todo` 引入“保底配额 + 低分优先”策略。
  - 在返回结果中附带调度解释字段，便于审计。

## 3. 风险与回滚

### 3.1 风险
- 旧经验数据无新字段，可能导致排序偏移。
- 积分算法若过于激进，短期会影响派单稳定性。
- 保底策略可能与严格 FIFO 冲突，需控制为“轻度干预”。

### 3.2 回滚策略
- 保留旧逻辑降级路径：
  - 记忆桶缺失时回退到 `rankCards` 全量评分。
  - 积分异常时可通过配置关闭积分驱动（仅记录不参与调度）。
  - 保底策略通过配置开关关闭，恢复原 FIFO。

## 4. 本次提交边界

本次只做 Phase 1 可运行版本，不引入新的外部服务，不改现有核心流程入口，不删除旧代码路径。

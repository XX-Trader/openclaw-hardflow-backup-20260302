# 自我进化升级计划（Phase 2：知识连接）

日期：2026-03-04  
负责人：Codex（执行）  
范围：在现有 Experience 机制上增加“信号 -> 记忆卡 -> 结果”的连接图谱闭环，不引入新服务。

## 1. 目标与验收

### 1.1 目标
- 让召回不只依赖静态文本相关性，还参考历史结果反馈。
- 把一次召回（attempt）和最终结果（outcome）沉淀为可复用连接信号。
- 兼容旧 runtime 结构，避免破坏已有流程。

### 1.2 验收标准
- recall 阶段写入 `attempt` 图谱事件。
- evolve 阶段写入 `outcome` 图谱事件。
- `rankCards` 能接入图谱加权分数（boost）。
- `hook-selftest` 覆盖 runtime `queryKey` 和 linkgraph 事件检查。

## 2. 执行清单

- [x] 扩展 `hooks/_lib/experience.ts`：
  - 增加 `buildSignalKeyFromQuery`
  - 增加 `appendLinkGraphEvent`
  - 增加 `readLinkGraphBoosts`
  - 增加 `readRuntimeRecallPayload`
  - `readRuntimeRecall` 保持兼容
  - `rankCards` 接入 `graphBoosts`
- [x] 扩展 `hardflow-experience-recall`：
  - 读取图谱 boost 参与排序
  - 写 runtime `queryKey/agentId`
  - 追加 `attempt` 事件
- [x] 扩展 `hardflow-experience-evolve`：
  - 读取 runtime payload
  - 回写 `outcome` 事件
- [x] 扩展 `scripts/hardflow/hook-selftest.mjs`：
  - 校验 runtime queryKey/cardIds
  - 校验 attempt/outcome 事件写入
- [x] 运行自测验证

## 3. 与 EvoMap 思路映射

参考：<https://github.com/EvoMap/evolver/blob/main/README.zh-CN.md>

- Signal 抽取：通过 `query -> queryKey` 做稳定信号键。
- Event 固化：将 `attempt/outcome` 事件落盘到 `events.jsonl`。
- Selector 思路：在召回排序中加入图谱历史反馈（boost），相当于轻量选择器。
- 结果闭环：一次召回后由 stop 阶段结果反哺后续召回。

## 4. 后续（Phase 3 候选）

- 引入衰减窗口和噪声抑制（避免某次异常把权重打偏）。
- 引入跨任务相似 queryKey 聚类（不是只看完全相同 key）。
- 增加策略模式（balanced/harden/repair-only）配置化开关。


# Self-Evolution Phase 2 变更说明

日期：2026-03-04

## 1. 目标

在不改变主流程入口的前提下，为经验召回新增“知识连接”反馈回路：
- 召回时记录尝试（attempt）
- 结束时记录结果（outcome）
- 下次召回时根据历史结果动态加权

## 2. 代码变更

### 2.1 `hooks/_lib/experience.ts`

- 新增常量：
  - `.workflow/experience/linkgraph/events.jsonl`
- 新增类型：
  - `RuntimeRecallPayload`
  - `LinkGraphEvent`
- 新增函数：
  - `buildSignalKeyFromQuery(query)`
  - `appendLinkGraphEvent({ workspaceDir, event })`
  - `readLinkGraphBoosts({ workspaceDir, queryKey, agentId, maxEvents })`
  - `readRuntimeRecallPayload(workspaceDir, sessionKey)`
- 兼容改造：
  - `writeRuntimeRecall` 新增 `queryKey/agentId` 字段写入
  - `readRuntimeRecall` 改为基于 payload 读取，保持旧接口不变
  - `rankCards` 新增 `graphBoosts` 参数并纳入最终分数

### 2.2 `hooks/hardflow-experience-recall/handler.ts`

- 新增召回链路：
  - 通过 `query` 生成 `queryKey`
  - 读取 linkgraph boost
  - 将 boost 传入 `rankCards`
  - 写 runtime payload（含 queryKey/agentId）
  - 追加 `attempt` 事件

### 2.3 `hooks/hardflow-experience-evolve/handler.ts`

- 新增演化链路：
  - 读取 `readRuntimeRecallPayload`
  - 在统计 success/failure 后，写入 `outcome` 事件
  - 清理 runtime 文件保持原行为

### 2.4 `scripts/hardflow/hook-selftest.mjs`

- 新增断言：
  - runtime 文件存在且包含 `queryKey/cardIds`
  - recall 后存在 `attempt` 事件
  - evolve 后存在 `outcome` 事件

## 3. 验证

已通过：

```bash
node --check scripts/hardflow/hook-selftest.mjs
node --experimental-strip-types --check hooks/_lib/experience.ts
node --experimental-strip-types --check hooks/hardflow-experience-recall/handler.ts
node --experimental-strip-types --check hooks/hardflow-experience-evolve/handler.ts
node --experimental-strip-types scripts/hardflow/hook-selftest.mjs --hooks-dir hooks --workspace .workflow/tmp-hook-selftest
```

结果：`[hook-selftest] ok`

## 4. 兼容性与风险

- 兼容性：
  - 旧 runtime 文件缺少 `queryKey/agentId` 时会自动补全。
  - 无 linkgraph 文件时自动降级为空 boost，不影响召回。
- 风险：
  - 当前是轻量分数叠加，极端历史样本可能产生偏置。
  - 建议后续引入策略模式与更细粒度衰减参数。


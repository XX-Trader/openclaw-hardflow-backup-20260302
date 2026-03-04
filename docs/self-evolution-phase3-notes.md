# Self-Evolution Phase 3 变更说明

日期：2026-03-04

## 1. 本次目标

完成 recall 端策略化：把 linkgraph 的加权逻辑由固定值改为可配置策略。

## 2. 代码变更

### 2.1 `hooks/_lib/experience.ts`

- 新增类型：
  - `EvolutionStrategy`
  - `LinkGraphStrategyPolicy`
- 新增函数：
  - `normalizeEvolutionStrategy(...)`
  - `resolveLinkGraphStrategyPolicy(...)`
- 改造：
  - `readLinkGraphBoosts(...)` 新增 `strategy/decayDays/maxEvents` 参数，并按策略计算事件权重
  - `rankCards(...)` 新增 `graphWeight` 参数，支持策略化融合强度
  - `recencyWeightByTs(...)` 支持外部传入衰减天数

### 2.2 `hooks/hardflow-experience-recall/handler.ts`

- `RecallOptions` 新增：
  - `graphStrategy`
  - `graphDecayDays`
  - `graphMaxEvents`
  - `graphWeight`
- 新增策略解析与注入：
  - 优先读取 hook 配置
  - 回退到环境变量 `EVOLVE_STRATEGY`
  - 最终回退 `balanced`
- 将策略参数同时传入：
  - `readLinkGraphBoosts(...)`
  - `rankCards(...)`

### 2.3 `scripts/hardflow/remote-enable-evolution-hooks.py`

- 默认回填 recall 配置：
  - `graphStrategy=balanced`
  - `graphDecayDays=30`
  - `graphMaxEvents=2000`

### 2.4 `scripts/hardflow/hook-selftest.mjs`

- recall 测试配置增加策略参数（harden + 自定义 decay/maxEvents/weight），验证链路可运行。

## 3. 验证

已通过：

```bash
node --experimental-strip-types --check hooks/_lib/experience.ts
node --experimental-strip-types --check hooks/hardflow-experience-recall/handler.ts
node --experimental-strip-types --check hooks/hardflow-experience-evolve/handler.ts
python -m py_compile scripts/hardflow/remote-enable-evolution-hooks.py
node --check scripts/hardflow/hook-selftest.mjs
node --experimental-strip-types scripts/hardflow/hook-selftest.mjs --hooks-dir hooks --workspace .workflow/tmp-hook-selftest
```

结果：`[hook-selftest] ok`

## 4. 参数示例

```json
{
  "hardflow-experience-recall": {
    "enabled": true,
    "topK": 5,
    "graphStrategy": "harden",
    "graphDecayDays": 21,
    "graphMaxEvents": 1800,
    "graphWeight": 0.3
  }
}
```


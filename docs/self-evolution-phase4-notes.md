# Self-Evolution Phase 4 变更说明

日期：2026-03-04

## 1. 本次补齐内容

1. 反模式库（失败案例）
2. 每 N 轮自动反思（reflection）并调整策略比例

## 2. 代码变更

### 2.1 `hooks/_lib/experience.ts`

- 新增文件：
  - `.workflow/experience/linkgraph/anti-patterns.json`
  - `.workflow/experience/linkgraph/reflection-state.json`
- 新增能力：
  - `updateAntiPatternLibrary(...)`
  - `readAntiPatternPenalties(...)`
  - `resolveAdaptiveGraphStrategy(...)`
- 排序增强：
  - `rankCards(...)` 支持 `antiPatternPenalties/antiPatternWeight`
- recall 文档增强：
  - 输出策略模式、反思比例、失败率窗口
  - 对高风险卡片输出 `Anti-pattern risk`

### 2.2 `hooks/hardflow-experience-recall/handler.ts`

- `graphStrategy` 支持 `auto`
- 新增配置：
  - `antiPatternWeight`
  - `antiPatternMaxPenalty`
  - `reflectionEnabled`
  - `reflectionRoundInterval`
  - `reflectionWindowDays`
  - `reflectionMinOutcomes`
  - `reflectionMaxEvents`
- 召回链路新增：
  - 自动反思策略解析
  - 反模式惩罚读取并参与排序

### 2.3 `hooks/hardflow-experience-evolve/handler.ts`

- outcome 回写后新增：
  - `updateAntiPatternLibrary(...)`

### 2.4 `scripts/hardflow/remote-enable-evolution-hooks.py`

- recall 默认值更新：
  - `graphStrategy=auto`
  - `graphWeight=0.25`
  - `antiPatternWeight=0.36`
  - `antiPatternMaxPenalty=0.85`
  - `reflectionEnabled=true`
  - `reflectionRoundInterval=8`
  - `reflectionWindowDays=7`
  - `reflectionMinOutcomes=6`
  - `reflectionMaxEvents=2000`

### 2.5 `scripts/hardflow/hook-selftest.mjs`

- 新增断言：
  - `reflection-state.json` 存在且 strategy 有效
  - 失败回合后 `anti-patterns.json` 存在且 `failureCount>=1`

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


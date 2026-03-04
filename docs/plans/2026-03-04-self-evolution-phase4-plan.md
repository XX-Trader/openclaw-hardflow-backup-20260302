# 自我进化升级计划（Phase 4：反模式库与自动反思）

日期：2026-03-04  
负责人：Codex（执行）  
范围：补齐剩余两项能力：反模式库（失败案例）与每 N 轮自动 reflection 策略调整。

## 1. 目标与验收

### 1.1 目标
- 建立失败案例反模式库，避免重复踩坑。
- 在 recall 侧引入周期性反思，自动调整 repair/optimize/innovate 比例并映射到策略。
- 保持默认兼容，不破坏原有流程。

### 1.2 验收标准
- failure outcome 会落地到 `anti-patterns.json`。
- recall 排序可读取反模式惩罚并降权高风险卡片。
- 每 N 次 recall 会更新 `reflection-state.json`，输出当前策略与比例。
- hook 自测覆盖上述行为并通过。

## 2. 执行清单

- [x] `experience.ts` 新增反模式库读写能力
- [x] `experience.ts` 新增反思状态计算与持久化能力
- [x] recall hook 接入反模式惩罚与 auto 策略解析
- [x] evolve hook 在 outcome 后写入反模式库
- [x] 远程启用脚本补默认配置
- [x] hook-selftest 增加反模式/反思断言
- [x] 语法检查 + 自测通过


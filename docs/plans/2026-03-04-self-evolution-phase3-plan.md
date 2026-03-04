# 自我进化升级计划（Phase 3：策略模式与图谱衰减参数）

日期：2026-03-04  
负责人：Codex（执行）  
范围：给 recall 阶段增加策略模式（balanced/harden/repair-only）和可配置衰减参数，不改主流程入口。

## 1. 目标与验收

### 1.1 目标
- 支持按策略切换图谱反馈强度，避免单一固定权重。
- 支持按环境调节衰减窗口与事件扫描规模。
- 保持旧配置兼容，未配置时自动使用默认策略。

### 1.2 验收标准
- `hardflow-experience-recall` 支持新参数：
  - `graphStrategy`
  - `graphDecayDays`
  - `graphMaxEvents`
  - `graphWeight`
- `readLinkGraphBoosts` 根据策略和衰减参数计算 boost。
- `rankCards` 支持外部传入图谱融合权重。
- hook 自测通过。

## 2. 执行清单

- [x] 在 `hooks/_lib/experience.ts` 增加策略模型与参数归一化
- [x] 改造 `readLinkGraphBoosts` 使用策略参数
- [x] 改造 `rankCards` 支持 `graphWeight`
- [x] 在 `hardflow-experience-recall` 接入策略参数
- [x] 更新远程启用脚本默认配置
- [x] 跑语法检查与 hook 自测

## 3. 默认策略

- `balanced`（默认）
- `harden`（稳定优先，失败惩罚更强）
- `repair-only`（修复优先，几乎只强化失败反馈）

## 4. 兼容性

- 若未配置新参数，行为默认等价于此前 `balanced`。
- 若 `EVOLVE_STRATEGY` 设置为上述三种之一，可直接生效。


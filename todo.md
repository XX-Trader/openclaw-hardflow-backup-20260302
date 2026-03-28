# TODO

> 策略：先在 **nofx 单机** 验证所有变更稳定后，再推广到其他 4 台服务器。
> 更新时间：2026-03-28

## P2 — 推广与治理

- [⏰ 2026-05-01] [🟡 P2] nofx 验证通过后，推广到其余 4 台服务器
- [⏰ 2026-05-01] [🟡 P2] 调整 Lobster 仓库配置为 `external_readonly`
- [⏰ 2026-05-05] [🟡 P2] 把默认 `coding-default` workflow profile 的 manifest、安装入口正式落地
- [⏰ 2026-05-05] [🟡 P2] 为 `upgrade feedback` 补齐晋升/回滚规则
- [⏰ 2026-05-10] [✅ 完成] ~~拆分 `policy_enforcer.py`（5970行巨型单体）为独立模块~~ → 2026-03-28 已完成

## P3 — 长期优化

- [🟢 P3] `algo_micro_optimizer` 方案 B：Workflow Scorecard 综合分驱动自动优化
- [🟢 P3] 核心 registry 配置 JSON Schema 强校验
- [🟢 P3] MetaClaw 跨次学习闭环：`lesson_to_skill.py`
- [🟢 P3] CLI 交互体验优化（交互式引导 + 自动补全）
- [🟢 P3] 多 workflow 负载均衡与环节裁剪策略
- [🟢 P3] 外部 workflow / skill 下载与安装市场
- [🟢 P3] `project-registry` 扩展：项目级独立配置

## Agent 模型配置

> ✅ 2026-03-28 已全部更新

| Agent | 配置 | 状态 |
|-------|------|------|
| coordinator | `openai-codex/gpt-5.4` | ✅ |
| tester | `kimicode/Doubao-Seed-2.0-pro` | ✅ |
| doc-writer | `kimicode/Doubao-Seed-2.0-pro` | ✅ |
| explorer | `openai-codex/gpt-5.4-mini` | ✅ 新增 |

---
## 参考文档
完整执行计划与细节见：[docs/execution-roadmap.md](docs/execution-roadmap.md)

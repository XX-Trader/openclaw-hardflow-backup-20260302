# TODO

> 策略：先在 **nofx 单机** 验证所有变更稳定后，再推广到其他 4 台服务器。
> 更新时间：2026-04-24

## P0 — 项目交付优先工作流（核心战略落地）

> 详细文档：[docs/核心主工作流/项目交付优先工作流/](docs/核心主工作流/项目交付优先工作流/)

### Phase 1：双 AI 对抗式审查文档
- [x] [🔴 P0] `skills/library/dual-ai-review/SKILL.md` 主 Skill
- [x] [🔴 P0] 需求审查模板 `requirements_review.md`
- [x] [🔴 P0] 方案审查模板 `solution_review.md`
- [x] [🔴 P0] 代码审查模板 `code_review.md`
- [x] [🔴 P0] 门禁映射契约 `review-gate-contract.md`
- [x] [🔴 P0] 共识规则 `consensus-rules.md`
- [x] [🔴 P0] 实现 `review_gate_enforcer.py`
- [x] [🔴 P0] 升级 reviewer SOUL.md（双 AI 对抗审查调度器）
- [x] [🔴 P0] 升级 coordinator SOUL.md（项目交付优先调度链路）
- [x] [🔴 P0] 端到端集成测试全部通过（7/7）

### Phase 1.5：失败学习回写机制文档
- [x] [🔴 P0] `skills/library/failure-learning/SKILL.md` 主 Skill
- [x] [🔴 P0] 失败分析报告模板 `failure_analysis.md`
- [x] [🔴 P0] 实现 `failure_tracker.py`

### Phase 2：project-agent 升级（文档+代码完成）
- [x] [🟡 P1] `skills/library/project-profile-manager/SKILL.md`
- [x] [🟡 P1] 项目画像模板 `PROJECT_PROFILE.md`
- [x] [🟡 P1] `skills/library/api-registry-manager/SKILL.md`
- [x] [🟡 P1] API 注册表模板 `API_REGISTRY.json`
- [x] [🟡 P1] 来源注册表模板 `SOURCE_REGISTRY.json`
- [x] [🟡 P1] 实现 `project_memory_writer.py`

### Phase 3：项目级记忆模块（文档+代码完成）
- [x] [🟡 P1] 项目记忆目录结构定义
- [x] [🟡 P1] 注入器接口规范
- [x] [🟡 P1] 实现 `project_memory_injector.py`

### Phase 4：第三方 API 定期更新（文档+代码完成）
- [x] [🟢 P2] API watch 操作手册
- [x] [🟢 P2] 实现 `source_registry_watcher.py`
- [x] [🟢 P2] 注册 cron job

### Phase 5：自进化完全移除（文档+代码完成）
- [x] [🟢 P2] cron 裁剪执行清单
- [x] [🟢 P2] 修改 `cron/jobs.json` 移除自进化类 job
- [x] [🟢 P2] 删除旧 `install_workflow_profile.py` 主体逻辑，不保留兼容入口
- [x] [🟢 P2] 删除继续引用 `cron_setup.py` 的旧 `SETUP_WORKFLOW.md`

### Phase 6：端到端编码流水线编排（下一阶段主任务）
- [x] [🔴 P0] 新建 `skills/library/project-delivery-pipeline/SKILL.md`
- [x] [🔴 P0] 新建 `skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`
- [x] [🔴 P0] 定义 `.workflow/pipeline-runs/<run_id>/` 产物目录
- [x] [🔴 P0] 定义 `run_meta.json`、`context_snapshot.md`、`research_report.md`
- [x] [🔴 P0] 定义 `requirements.md`、`solution.md`（含 implementation plan）、`patch_summary.md`
- [x] [🔴 P0] 固化双 AI 需求/方案/代码审查产物契约与 verdict gate
- [x] [🔴 P0] 接入 HardFlow Core / ACP 可配置编码命令适配（`--code-command`）
- [x] [🔴 P0] 接入 lint、typecheck、unit、integration、smoke、部署验证命令证据收集（`--verification-command`）
- [x] [🔴 P0] 实现失败回退和 failure-learning 触发产物
- [x] [🔴 P0] 实现文档、done/todo、项目记忆回写建议报告
- [x] [🔴 P0] 实现通用 runtime adapter MVP
- [x] [🔴 P0] 新增通用 `runtime_installer.py`，支持任意 `--runtime-home/--runtime-name`
- [x] [🔴 P0] 增加 dry-run 状态机集成测试
- [x] [🔴 P0] 增加项目记忆定位门禁，生成 `.workflow/project-memory/<project_key>/`
- [x] [🔴 P0] 增加 Task Center 镜像，记录状态、阶段、通信、输出和 incident
- [x] [🔴 P0] 增加 `pipeline_runner.py view` 人工查看入口
- [x] [🔴 P0] 增加到期 TODO → Task Center 候选任务桥接（人工确认后执行）
- [x] [🔴 P0] 增加异常日志 → 运维任务/incident 桥接（critical 默认转人工确认）
- [x] [🔴 P0] 增加 `human_inbox.py` 人工队列，统一处理确认、拒绝、澄清和升级任务
- [x] [🔴 P0] 接入 runtime/Hermes 可配置 agent 命令适配（research/code/verify/review/writeback）
- [x] [🔴 P0] 接入真实联网 research agent 命令入口，并把 source URLs / 命令输出写入 `research_report.md`
- [x] [🔴 P0] 通过 `project_memory_writer.py` 执行真实项目记忆回写
- [x] [🔴 P0] 在 Hermes native profile 中做一次 live 多 agent smoke（非 dry-run）：`hermes-profile-smoke-20260424T135014Z`
- [x] [🟡 P1] 用 `hybrid-single-chat` 替代多次冷启动 Hermes smoke，避免每阶段 `hermes chat` 超时
- [ ] [🟡 P1] 清理 `tests/scripts_openclaw_ops` 中仍指向旧 `scripts/openclaw-ops/*` 主体入口的历史测试，恢复目录级 discover 作为有效门禁

---

## P0 — 评分系统升级（解封 HardFlow 门禁管道）

> 详细文档：[docs/核心主工作流/ACP全链路编码工作流/评分系统升级/](docs/核心主工作流/ACP全链路编码工作流/评分系统升级/README.md)

- [x] [🔴 P0] 替换 `score-gate.sh` → 真实评分聚合器 `score-aggregator.sh`
- [x] [🔴 P0] scorecard 输出含 findings + deduction_reasons + evidence_sources
- [ ] [🔴 P0] 验证 `score-gate-audit.ndjson` 正常产出（需部署后验证）
- [x] [🟡 P1] 新建 `hardflow-score-rubric` Skill（G0-G6 共 7 个 rubric + few-shot 示例）
- [x] [🟡 P1] 绑定 Skill 到 reviewer Agent（5→6 skills）
- [x] [🟡 P1] 替换 `improve-gate.sh` 空壳 → 真实改进引擎 `improve-evaluator.sh`
- [x] [🟡 P1] 接通 HardFlow 评分 → evolution-upgrader 闭环 (`hardflow_score_adapter.py`)

## P0 — 技能化架构迁移（Phase 1-5 ✅ 全部完成）

> 详细文档：[docs/基础设施/技能化架构/](docs/基础设施/技能化架构/README.md)

- [x] [🔴 P0] SKILL.md 对标官方 frontmatter 规范
- [x] [🔴 P0] HardFlow SKILL.md 重写（269行操作手册 + 10 脚本 + 7 文档）
- [x] [🔴 P0] 9 个新运维 Skill 创建（16 能力域全覆盖）
- [x] [🔴 P0] jobs.json 21 个 Job 全部 skill_ref 绑定
- [x] [🔴 P0] 98 个脚本 + 13 目录归并为自包含 Skill
- [x] [🔴 P0] 旧 Bash 脚本(14个) + 旧安装器(11个) + scripts/hardflow/ 物理删除
- [x] [🔴 P0] coordinator / reviewer / ops-agent manifest 绑定
- [x] [🔴 P0] docs 三件套 v3.0 + INDEX.md 同步
- [ ] [🟡 P1] 端到端验证三条调用路径
- [ ] [🟡 P1] 远程服务器部署（4台）

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

> ✅ 2026-03-29 已全部更新

| Agent | 配置 | 状态 |
|-------|------|------|
| coordinator | `openai-codex/gpt-5.4` | ✅ |
| tester | `kimicode/Doubao-Seed-2.0-pro` | ✅ |
| doc-writer | `kimicode/Doubao-Seed-2.0-pro` | ✅ |
| explorer | `openai-codex/gpt-5.4-mini` | ✅ 新增 |

---
## 参考文档
- 完整执行计划与细节见：[docs/execution-roadmap.md](docs/execution-roadmap.md)
- 功能文档索引见：[docs/INDEX.md](docs/INDEX.md)
- 已完成清单见：[done.md](done.md)

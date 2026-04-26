# DONE — 已完成功能清单

> 所有已完成并上线的功能记录在此。每项包含：完成时间、功能描述、关键实现细节。
> 与 `todo.md` 配合使用，形成完整的项目进度管理视图。

---

## 2026-04-26 已完成

- [x] [2026-04-26] **nofx Discord pipeline 默认 live 与 profile 写权限修复**
  - `smart_arb_pipeline_entry.py` 改为固定 live coordinator pipeline；项目入口不再提供 simulation/dry-run 模式。
  - 两个 nofx Discord profile 提示词改为“执行类需求默认真实执行”，并新增仓库级 `config.yaml` 模板，关闭命令审批和 security scan。
  - nofx `spreadagent/config.yaml`、`arbitrageagent/config.yaml` 从 `root:root 0600` 修回 `arbops:arbops 0600`，解决 `/sethome` 写 profile 配置失败。
  - nofx 写入 `/etc/sudoers.d/90-arbops-hermes`，允许 `arbops` 无密码 sudo，满足早期 workflow 服务器级执行权限。
  - 同步 runbook、pitfalls 和 nofx live bridge 文档，保留 `PRODUCTION_TRADING_ENABLED=false` 与真实交易禁止边界。

## 2026-04-25 已完成

- [x] [2026-04-25] **nofx live bridge per-agent workspace 隔离**
  - `pipeline_runner.py` 固定使用 Git worktree 隔离，新增 `agent-workspaces/manifest.json`、`PIPELINE_AGENT_*` 环境变量注入、command report workspace 留痕和 Task Center `agent_execution` 详情；不再暴露 `shared` / `copy` 模式。
  - `code_execution` 默认在 `backend-dev` 独立 workspace 内执行；成功后导出 `command-runs/code_execution-1.patch`，应用回主项目目录，并注入后续 `tester`、`reviewer`、`deployer` workspace。
  - `smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为 Hermes 阶段项目目录。
  - workspace root 若被配置到项目目录内部，会直接报错要求移到 `--command-cwd` 外部，不再静默降级。
  - 新增回归测试覆盖 worktree 隔离、diff 回流、两条 verification 命令共享 workspace 时不重复 apply patch、后续 reviewer workspace 注入、嵌套 workspace 拒绝和 nofx entry 不再传 workspace mode；nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 已通过。

- [x] [2026-04-25] **nofx Hermes profile 提示词修复与 fan-out 边界澄清**
  - 复核 nofx 发现 `spreadagent` 19:10 Discord 会话没有创建新的 `smart-arb-pipeline` run，而是在 Hermes profile 会话里直接规划任务；同时两个 profile 的 `SOUL.md` 主体为问号乱码，coordinator pipeline 约束不稳定。
  - 新增仓库模板 `config/nofx-hermes-profiles/arbitrageagent/SOUL.md` 与 `config/nofx-hermes-profiles/spreadagent/SOUL.md`，按字节上传到 nofx 并备份原文件，随后重启 `hermes-discord-arbitrage` 与 `hermes-discord-spread`。
  - 验证两个 profile 均为 `gateway_state=running`、`discord=connected`，且 `SOUL.md` 中文可读；标准入口 dry-run smoke `codex-prompt-smoke-spreadagent-20260425T112013223220Z` 返回 `completed`。
  - 同步文档和项目记忆，明确当前 live bridge 是 Hermes 单会话 stage bridge，不是真实 native 多 agent fan-out；真实 fan-out 已记录到 `todo.md`。

## 2026-04-24 已完成

- [x] [2026-04-24] **Hermes profile 非 dry-run smoke 验收**
  - 新增 `hermes_profile_smoke.py`，支持 `echo`、`hybrid`、`hermes-chat` 三种 smoke 模式
  - 修复原 `hybrid` 每阶段冷启动 `hermes chat` 导致的 3-10 分钟耗时；现在一次 `hermes chat` 生成 research/code/review bundle，再由本地 stage command 读取缓存
  - WSL `/home/ubuntu/.hermes` 已完成 `hybrid-single-chat` smoke：真实 `hermes chat --provider zai` 50 秒完成 bundle，verification 走确定性本地命令
  - 验收证据：run_id=`hermes-profile-smoke-20260424T135014Z`，Task Center task=`project-delivery:hermes-profile-smoke-20260424T135014Z`，状态 `completed`
  - `hermes-chat` 全阶段模式保留为 provider 诊断入口，不作为默认 smoke 门禁

- [x] [2026-04-24] **Project Delivery Pipeline live 命令适配层**
  - `pipeline_runner.py` 新增 `--research-command`、`--code-command`、`--verification-command`、`--code-review-command`、`--memory-write-command`、`--write-project-memory`
  - live 模式会把每个命令的 cwd、退出码、stdout/stderr 写入 `command-runs/*.json`，失败时按阶段回退
  - `--write-project-memory` 已调用 `project_memory_writer.py` 写入项目记忆；安装器同步 `project_memory_writer.py` 与 `project_memory_injector.py`
  - 新增单元测试覆盖完整 live command adapter happy path

- [x] [2026-04-24] **运营事件入任务中心 + 人工队列闭环**
  - 新增 `deadline_to_task_bridge.py`：到期/超期 TODO 自动生成 `todo_deadline_candidate`，默认 `need_human_confirm=true`，等待用户确认后才执行
  - 新增 `exception_to_task_bridge.py`：增量扫描日志异常，按 fingerprint 去重创建 `ops_exception` 运维任务，并写入 `task_incidents`
  - 新增 `human_inbox.py`：统一列出、确认、拒绝、澄清 `need_human_confirm`、`needs_clarification`、`escalated`、`escalate_human` 任务
  - 更新 `cron/jobs.json`：注册 `todo_deadline_to_task_bridge_daily` 与 `system_exception_to_task_bridge`
  - 新增单元测试：`test_deadline_to_task_bridge.py`、`test_exception_to_task_bridge.py`、`test_human_inbox.py`

- [x] [2026-04-24] **Project Delivery Pipeline 可控性收口**
  - `pipeline_runner.py` 新增项目记忆定位门禁，自动生成 `.workflow/project-memory/<project_key>/PROJECT_PROFILE.md`、`DECISIONS.md`、`DELIVERY_RULES.md`、`API_REGISTRY.json`、`SOURCE_REGISTRY.json`、`IMPACT_MAP.json`、`RETRIEVAL_MANIFEST.json`
  - 新增 `--record-task-center` / `--task-center-db` / `--task-center-task-id`，将流水线镜像到 Task Center 的 `tasks`、`stage_runs`、`module_communications`、`task_outputs`、`task_incidents`
  - 新增 `pipeline_runner.py view` 查看入口，快速定位 run 状态、下一步、失败阶段、关键产物和 Task Center 引用
  - 修复技能化迁移后的任务查看工具 import path：`task_output_consumer.py`、`task_output_broadcast_runner.py`、`policy_enforcer.py`
  - 技术裁决：默认 hybrid local-first 项目记忆 + keyword/symbol 检索；向量 RAG 与 GraphRAG 做可插拔增强，不默认引入重服务

- [x] [2026-04-24] **Project Delivery Pipeline Phase 6 MVP**
  - 新增 `skills/library/project-delivery-pipeline/`：Skill 入口、状态机 runner、模板、state-machine 与 runtime-adapter 参考文档
  - `pipeline_runner.py` 支持需求输入、外部 research 产物、需求/方案/代码 review gate、dry-run 编码交付、测试验收、失败回退、writeback 报告
  - 明确 Hermes/OpenClaw 只是 runtime host 示例；默认通用 runtime 为 `~/.hardflow-runtime`，也支持任意 `--runtime-home`
  - 新增 `runtime_installer.py` 并将根目录 `setup.py` 切换到新入口，旧 `workflow_setup.py` / `install_workflow_profile.py` 不再保留兼容入口
  - 新增测试 `tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py`，覆盖 happy path、需求失败回退、验收需求失败回退、Hermes runtime home

- [x] [2026-04-24] **项目交付优先工作流收束为端到端编码交付流水线**
  - 明确真实目标：自动探索需求、需求包、方案包、编码、测试、代码审核、修复、验收、文档/记忆回写
  - 新增 Phase 6：`project-delivery-pipeline` 状态机与 runtime adapter
  - 明确不用做：不恢复 `cron_setup.py`，不恢复 `install_*_job.py`，不维护多套 runtime 业务流程，不新增平行编码引擎，不恢复默认自进化链
  - 删除旧 `install_workflow_profile.py` 主体逻辑，不保留兼容入口
  - 删除旧 Hermes 适配测试、`SETUP_WORKFLOW.md`、旧控制面 live acceptance runner、失效 root CLI 入口测试和旧 shared human output 测试
  - 同步文档：`docs/核心主工作流/项目交付优先工作流/`、`docs/INDEX.md`、`docs/核心主工作流/README.md`、`todo.md`

---

## 2026-04-23 已完成

- [x] [2026-04-23] **Multica Managed Agents 平台调研**
  - 核对 `multica-ai/multica` 最新 GitHub 仓库、release 资产、CLI/daemon、自部署、桌面端和 Web 控制台结构
  - 明确 `exe` 分为 CLI 二进制与 Desktop 安装包，GitHub 仓库才是完整源码
  - 结论：不迁移 OpenClaw 手机/Discord 主链；仅借鉴 runtime registry、任务状态机、transcript、Skill 绑定、daemon 健康检查和 Autopilot 触发模型
  - 文档路径：`docs/研究参考/multica-managed-agents-平台研究.md`

---

## 2026-03-29 已完成

### 配置自动进化体系搭建（阶段四 4.2/4.3）

- [x] [2026-03-29] **B 层 Clone 修复**
  - 服务器 `git clone` 创建 `/root/openclaw-hardflow-backup-20260302/`
  - 验证 hooks/skills 目录可达，GitHub SSH 认证正常

- [x] [2026-03-29] **C 层同步通道确认**
  - 确认 `ops_git_sync_push`、`governance_evolution`、`auto_update_daily` 三个 cron 的 `repo-path` 均已指向 B 层
  - C 层 `.gitignore` 已有基础排除规则

- [x] [2026-03-29] **每小时本地快照** — `local_snapshot_runner.py`（新建）
  - 白名单同步：`openclaw.json`、`hooks/`、`skills/`、`agents/`、`cron/`、`ops/`
  - 排除列表：`sessions/`、`auth-profiles`、`.bak`、`skills/library/`、`exception-reports/`
  - 仅内容变化时复制，支持 dry-run 和 JSON 输出
  - 注册 `local_config_snapshot` cron（每小时，id=`70a5f20a`）
  - 脚本路径：`scripts/openclaw-ops/local_snapshot_runner.py`

- [x] [2026-03-29] **auto_update_daily 安装修复**
  - 发现 cron 只执行 `git pull` 但缺少 `--install-cmd`，pull 后不安装
  - 确认 `workflow_setup.py` 已支持 `--yes` 非交互模式（第 1382 行）
  - Patch cron：添加 `--install-cmd "python3 setup.py --yes ..."` 参数
  - 现在 pull 后自动执行 `setup.py --yes` 安装到 `.openclaw/`

### Cron 任务批量修复

- [x] [2026-03-29] **Telegram 群 ID 批量替换**
  - 25 处旧群 ID (`-1003333097130`) → 新 ID (`-1003758974925`)
  - 清除 5 条过期 `lastError` 记录

### Agent 模型配置同步

- [x] [2026-03-29] **模型绑定更新**（同步 `openclaw.json` 和 `openclaw/openclaw.json`）
  - coordinator → `gpt-5.4`
  - tester → `Doubao-Seed-2.0-pro`
  - doc-writer → `Doubao-Seed-2.0-pro`
  - explorer → 新增 `gpt-5.4-mini`

### 文档体系重构

- [x] [2026-03-29] **多层级文档目录结构**
  - 建立 `docs/INDEX.md` 顶层功能索引
  - 创建 `docs/自动进化/` 父级目录 + `配置自动进化/` 子功能目录
  - 功能文件夹标准三件套：`README.md` + `architecture.md` + `implementation-plan.md`
  - 固化文档编写规范（每个功能一个文件夹，索引只写目录引用）

- [x] [2026-03-29] **Telegram 输出规范文档化**
  - `docs/telegram-output-format-spec.md`：多列表格格式标准

### OpenClaw 启动修复

- [x] [2026-03-29] **Gateway 守护进程排查**
  - 确认正确启动命令为 `openclaw gateway`（而非 `openclaw daemon`）
  - 通过 tmux 会话在 nofx 服务器正常运行

### 任务执行器 Bugfix（3项）

- [x] [2026-03-29] **失败原因输出修复** — `workflow_views.py`
  - 问题：`humanize_executor_reason()` 在 `reason` 为空时，兜底返回泛化的"任务执行失败"，丢失真实错误
  - 修复：增加 `resolution_summary` 回退读取，自动识别 Gateway 连接失败、执行超时、网络错误
  - 效果：NOFX-bot 通知现在展示 `Gateway 连接失败` 而非 `任务执行失败`

- [x] [2026-03-29] **异常日志巡检 Auto-Discover** — `unified_exception_logger.py`
  - 问题：ops-agent 调用时自行推理 `--log-dirs /root/.openclaw/sessions/`，该目录不存在
  - 修复：新增 `--auto-discover` 参数 + `discover_log_dirs()` 函数
  - 自动扫描 7 类目录：`agents/*/sessions`、`ops/task-center/executor-runs`、`logs` 等
  - Agent 只需传 `--auto-discover`，不需要猜测路径

- [x] [2026-03-29] **TASK_STATUSES 未定义** — `policy_enforcer.py`
  - 问题：`from task_center import TASK_STATUSES` 在 gateway 异常时 import 失败
  - 状态：gateway 重启后自愈，已确认最近 4 轮执行均正常

---

## 2026-03-28 已完成

### 阶段 6.5：PolicyEnforcer 二次深度拆分（Mixin 架构）

- **目标**: 将 4,526 行单体 `PolicyEnforcer` 拆分为 5 个 Mixin + 1 个组合类
- **结果**:
  - `policy_scoring.py` (ScoringMixin, 234行/8方法)
  - `policy_workflow.py` (WorkflowMixin, 848行/14方法)
  - `policy_context.py` (ContextMixin, 514行/11方法)
  - `policy_task.py` (TaskLifecycleMixin, 2029行/35方法)
  - `policy_observe.py` (ObservabilityMixin, 951行/21方法)
  - `policy_enforcer.py` (组合类, 180行/24属性)
- **验证**: 9/9 语法通过 + CLI 28 子命令 + validate-runtime 正常执行
- **提交**: `13887bc9` → `02ed03e1` → `28d66869` → `10f6af92`

### 阶段一～五：自进化系统全面优化（部署完成）

- [x] [2026-03-28] **Cron Job 清理**：删除 12 个冗余/禁用 Job（原 33 → 21）
  - 删除 9 个冗余 Job + 3 个禁用 Job（agent-factory 自动、治理巡检、全量校准）
  - 删除废弃脚本：`benchmark_orchestrator.py` + `benchmark_output_consumer.py`
  - 启用 `daily_todo_digest_daily`，降频 `algo_micro_optimizer` → 24h

- [x] [2026-03-28] **安全加固**：`git_sync_push_runner.py` 三层审核
  - 第一层：路径过滤（已有）
  - 第二层：6 类敏感信息内容正则扫描（API Key / Token / Private Key / Password / Bearer / Generic Token）
  - 第三层：Agent 审核摘要（`.workflow/sync-reviews/` 异步复查）

- [x] [2026-03-28] **外部进化通道**：注册 3 个每日 Cron Job
  - `auto_update_daily`（上游社区，03:00）
  - `web_intel_collect_daily`（情报采集，03:30）  
  - `github_web_evolution_daily`（开源项目，04:00）

- [x] [2026-03-28] **异常巡检增强**：`unified_exception_logger.py`
  - 新增第 7 类异常分类：`path_validation_error`（路径校验错误）
  - `--abnormal-dir`：统一归档到 `/root/.openclaw/logs/abnormal/`
  - `--cleanup`：7 天 gzip 压缩 / 30 天自动删除

- [x] [2026-03-28] **advisor→TODO 自动写入**：`control_plane_optimization_advisor.py`
  - `--todo-file` 参数：自动追加建议到 TODO.md
  - MD5 指纹去重（重复建议不重复写入）
  - 风险标记：🔴高/🟡中/🟢低 + `🚨需人工审核`

- [x] [2026-03-28] **新增脚本**
  - `memory_to_skill_extractor.py`：记忆→Skill/Hook 自动封装（draft 模式，需人工激活）
  - `todo_deadline_checker.py`：截止时间解析 + 超期自动标记（`[截止:YYYY-MM-DD]` 格式）

- [x] [2026-03-28] **新增 Cron Job**
  - `advisor_todo_daily`（每日 04:15，自动派发优化建议→TODO）
  - `todo_deadline_checker_daily`（每日 00:00，截止时间检测）

- [x] [2026-03-28] **协议文档化**
  - `docs/trace_id_protocol.md`：trace_id 全链路注入协议
  - `docs/task_dispatch_protocol.md`：任务派发 5 要素确认协议
  - `docs/error_driven_evolution.md`：错误驱动进化协议 + fault_kb 结构
  - `docs/execution-roadmap.md`：6 阶段执行路线图

- [x] [2026-03-28] **索引重建**
  - `CRON_TASK_INDEX.md`：5 功能大类完整索引
  - `jobs_agent_mapping.md`：4 Agent 分组映射

- [x] [2026-03-28] **Agent 模型配置更新**
  - coordinator：`gpt-5.4-mini` → `gpt-5.4`
  - tester：`gpt-5.4-mini` → `Doubao-Seed-2.0-pro`
  - doc-writer：`gpt-5.4-mini` → `Doubao-Seed-2.0-pro`
  - explorer：新增 `gpt-5.4-mini`

- [x] [2026-03-28] **policy_enforcer.py 模块拆分**（阶段 6.4）
  - 5970 行巨型单体 → 4 个独立模块（总计减少 24%）
  - `policy_defaults.py`（946行）：DEFAULT_* 配置常量
  - `policy_utils.py`（129行）：工具函数和数据类
  - `policy_cli.py`（429行）：CLI 解析器和 main() 入口
  - `policy_enforcer.py`（4526行）：PolicyEnforcer 类核心逻辑
  - 零功能变更，完全向后兼容

---

## 2026-03 已完成

### 核心自进化闭环（4 层循环）

- [x] [2026-03-25] **`ops_governance_evolution_incremental`** — 经验提取引擎
  - 每 6 小时自动扫描运行日志 / 记忆 / 错误记录
  - 提取可优化的通用流程、BUG、最佳实践
  - 脚本：`governance_evolution_runner.py`（69KB）

- [x] [2026-03-25] **`optimize_self_evolution_summary`** — 行为蒸馏器
  - 每天凌晨 4:37 自动执行
  - 仅有新增优化项时才产出通知（NO_REPLY 机制）

- [x] [2026-03-25] **`reviewer_incremental_daily_4am`** — 评审落地器

- [x] [2026-03-25] **`ops_git_sync_push`** — 仓库同步器
  - 路径过滤（第一层审核）：排除 sessions/experience/memory/runtime 等目录

### 任务管理系统

- [x] [2026-03-25] **`todo_patrol`** — TODO 巡检与自动派发
- [x] [2026-03-25] **`task_center`** — 任务中心数据库（SQLite，4 张核心表含 trace_id）

### 异常巡检

- [x] [2026-03-25] **`unified_exception_logger`** — 系统异常分类巡检（6 类分类 + MD5 指纹去重）

### HardFlow 多角色工作流

- [x] [2026-03-25] **多角色 Agent 体系** — 13 个专业 Agent
- [x] [2026-03-25] **HardFlow 门禁系统** — G0-G6 七道门禁
- [x] [2026-03-25] **PUA 行为执行器** — Pressure/Urgency/Agency 机制

### 可观测性基础设施

- [x] [2026-03-25] **`chat_output` 通知框架** — 统一消息输出 + NO_REPLY 机制
- [x] [2026-03-25] **`workflow_views`** — 工作流可视化视图

### 安全与治理

- [x] [2026-03-25] **仓库隔离架构** — `.openclaw`（本地）与 backup（同步）严格分离
- [x] [2026-03-25] **`claim_verification_auditor`** — 反幻觉审计器

### 反馈与进化

- [x] [2026-03-25] **`upgrade_feedback_runner`** — 升级反馈收集器
- [x] [2026-03-27] **`fault_knowledge_base`** — 故障知识库
- [x] [2026-03-27] **`workflow_builder`** — 工作流模板生成器

### 外部进化

- [x] [2026-03-25] **`auto_update_install_runner.py`** — 上游社区更新检测脚本
- [x] [2026-03-25] **`web_intel_collect_runner.py`** — 情报采集脚本
- [x] [2026-03-25] **`github_web_evolution_runner.py`** — 开源项目进化脚本

---

## 参考

- 待办事项 → [todo.md](todo.md)
- 定时任务索引 → [scripts/openclaw-ops/CRON_TASK_INDEX.md](scripts/openclaw-ops/CRON_TASK_INDEX.md)
- Agent 映射 → [cron/jobs_agent_mapping.md](cron/jobs_agent_mapping.md)
- 执行路线图 → [docs/execution-roadmap.md](docs/execution-roadmap.md)
- 2026-04-24: 修复 project delivery runtime 安装器的 ops 根目录 runner 命名兼容；`runtime_installer.py` 现在同时安装 `pipeline_runner.py` 与 `project_delivery_pipeline.py`，`pipeline_runner.py` 会在安装态优先解析同级 `ops/policy`，确保安装到 Hermes runtime 后的 `ops/hermes_profile_smoke.py` 可以按同目录加载 runner 并完成 echo smoke，新增回归断言覆盖两个入口文件与安装态 smoke。
- 2026-04-25: 将 SmartMultiPlatformArbitrage nofx Discord live evidence bridge 的归属文档迁入 hardflow：新增 `docs/核心主工作流/项目交付优先工作流/smart-arb-nofx-live-evidence-bridge.md`，明确工作流代码归 hardflow、套利业务代码归 SmartMultiPlatformArbitrage，并记录 nofx runtime 路径、live 阶段证据、deployment 边界和验收 run id。
- 2026-04-25: 修复 nofx Discord Hermes live pipeline 卡顿与入口不稳：profile SOUL 改为绝对 `/home/arbops/.local/bin/smart-arb-pipeline`，`smart_arb_live_bridge.py` verification 默认收敛为 `git diff --check` + `compileall -q scripts strategy_runtime`，新增显式 `--verification-command-timeout-seconds`，并在 nofx 安装态通过 echo live smoke `codex-spreadagent-20260425T154609125415Z` 与真实 verification smoke。

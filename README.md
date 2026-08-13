# OpenClaw HardFlow

面向多运行时的项目交付流水线与运维治理仓库。项目把需求澄清、资料核验、方案评审、隔离实现、测试、代码审查、部署验收、项目记忆写回和可选 Git 发布串成可审计的闭环，并提供 OpenClaw、Hermes 及自定义 Runtime 的安装入口。

> 本仓库位于量化交易资料目录中，但自身是工作流基础设施与配置备份，不包含行情、回测或交易执行程序。

## 核心能力

- **Project Delivery Pipeline**：按固定状态机推进项目，从需求到验收和记忆写回均保留结构化产物。
- **HardFlow G0–G6 门禁**：覆盖需求、方案、实现、安全、发布准备与最终验收。
- **多 Agent 分工**：协调、项目分析、资料核验、前后端实现、测试、审查、部署和文档写回各有明确 owner。
- **隔离代码工作区**：实现命令在每次运行的独立 Git workspace 中执行，通过验证和审查后再应用补丁。
- **控制面治理**：提供任务中心、Cron 开关、配置巡检、日志监控、claim audit 和故障知识库。
- **跨运行时安装**：根目录 `setup.py` 是统一入口，可将 Skills、运维脚本和 Cron 模板安装到指定 Runtime Home。
- **项目记忆**：将已验收事实、约束和失败经验写回项目级 memory，供后续流水线复用。

## 交付流程

```mermaid
flowchart LR
    A[需求输入] --> B[Coordinator 路由]
    B --> C[项目上下文 / Memory / Research]
    C --> D[需求包与双人评审]
    D --> E[Delivery Plan 与双人评审]
    E --> F[隔离工作区实现]
    F --> G[验证与代码审查]
    G -->|通过| H[部署与验收]
    G -->|失败| F
    H --> I[项目记忆写回]
    I --> J[可选 Git 发布]
```

流水线产物默认写入 `.workflow/pipeline-runs/<run_id>/`。实现、验证、审查和发布命令均会留下报告；失败阶段会记录 `failed_stage`、`next_action` 与修复回流点。

当前主要 workflow owner：

| Owner | 职责 |
| --- | --- |
| `coordinator` | 流程协调和 Git 发布门禁 |
| `project-agent` | 项目记忆、需求包和方案包 |
| `web-agent` | 外部资料与官方来源核验 |
| `backend-dev` / `frontend-dev` | 后端、脚本、服务、页面和交互实现 |
| `reviewer` | 需求、方案和代码独立审查 |
| `tester` | 测试、验证和验收 |
| `deployer` | 内控 deployment smoke |
| `doc-writer` | 文档和项目记忆写回 |

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `setup.py` | 跨运行时安装与 Cron 管理统一入口 |
| `agents/` | Agent owner、能力和运行时绑定清单 |
| `skills/library/project-delivery-pipeline/` | 项目交付状态机、Runtime 安装器与参考资料 |
| `skills/openclaw-hardflow-automation/` | HardFlow G0–G6 门禁、评分与回流工具 |
| `skills/library/control-plane-ops/` | 任务中心、策略、Cron 与运维脚本 |
| `skills/library/openclaw-workflow-manager/` | OpenClaw 工作流同步、漂移检查与运行态管理 |
| `hooks/` | 命令守卫、审计、门禁提醒和经验沉淀 Hooks |
| `cron/` | Cron 模板与任务 owner 映射 |
| `integration/openclaw-bridge/` | 本地适配层及与上游 Runtime 的边界说明 |
| `openclaw/` | 合并到本机运行态的 OpenClaw overlay |
| `vendor/openclaw-official/` | 上游 OpenClaw Git 子模块 |
| `tests/` | 流水线、安装器、控制面与 Skill 契约测试 |
| `docs/` | 架构、部署、工作流、ADR、计划和历史资料 |
| `todo.md` / `done.md` | 待办与完成事项总账 |

## 环境要求

- Git（包含 submodule 与 worktree 支持）
- Python 3.11 或兼容版本
- PowerShell 7；Windows 命令统一由 `pwsh` 进入
- Node.js 与 Bash；执行 HardFlow 的 `.mjs`、`.sh` 门禁时使用
- 目标 Runtime CLI；仅在连接对应 OpenClaw、Hermes 或自定义运行时时使用

## 快速开始

### 1. 获取子模块

```powershell
pwsh -NoProfile -Command 'git submodule update --init --recursive'
```

### 2. 查看统一安装入口

```powershell
pwsh -NoProfile -Command 'python .\setup.py --help'
```

### 3. 在仓库内做安装演练

```powershell
pwsh -NoProfile -Command 'python .\setup.py --dry-run --runtime-home .\.codex-tmp\runtime-smoke --runtime-name local-agent --emit-json'
```

演练会报告将安装的 Skills、运维脚本、Cron job 和目标路径，不会写入目标 Runtime Home。

### 4. 安装到指定 Runtime Home

```powershell
pwsh -NoProfile -Command 'python .\setup.py --runtime-home "$HOME\.hardflow-runtime" --runtime-name local-agent --emit-json'
```

常见目标示例：

```powershell
pwsh -NoProfile -Command 'python .\setup.py --runtime-home "$HOME\.openclaw" --runtime-name openclaw --emit-json'
pwsh -NoProfile -Command 'python .\setup.py --runtime-home "$HOME\.hermes" --runtime-name hermes --emit-json'
```

### 5. 演练项目交付流水线

```powershell
pwsh -NoProfile -Command 'python .\skills\library\project-delivery-pipeline\scripts\pipeline_runner.py --project-key demo --requirement "为示例项目补充健康检查" --dry-run --emit-json'
```

真实执行时按阶段传入可信命令，例如 `--research-command`、`--code-command`、`--verification-command`、`--code-review-command` 和 `--deployment-command`。涉及实现的运行应设置 `--command-cwd`，流水线会创建隔离 workspace 并检查补丁与当前工作树的重叠情况。

### 6. 查看或切换 Cron

```powershell
pwsh -NoProfile -Command 'python .\setup.py cron-status --emit-json'
pwsh -NoProfile -Command 'python .\setup.py cron-off --dry-run --emit-json'
pwsh -NoProfile -Command 'python .\setup.py cron-on --dry-run --emit-json'
```

正式切换前先检查输出中的 Runtime Home、`jobs_file` 和变更摘要，并保留原配置作为回滚点。

## HardFlow 门禁

| Gate | 目标 |
| --- | --- |
| G0 | 需求边界、验收标准与风险分析 |
| G1 | 方案设计与可行性 |
| G2 | 前端或文档实现质量 |
| G3 | 后端、接口与数据流质量 |
| G3.5 | 迭代优化与回归覆盖 |
| G4 | 安全审查与高风险项闭环 |
| G5 | 发布、回滚与可观测性准备 |
| G6 | 最终验收与交付一致性 |

每个 Gate 由执行证据、独立 Reviewer 评价和确定性评分脚本组成。典型产物位于：

```text
.workflow/runs/<run_id>/scorecards/<gate>.json
.workflow/runs/<run_id>/gate-results/<gate>.json
.workflow/audit/gate-audit.ndjson
```

完整规则见 [HardFlow 操作手册](skills/openclaw-hardflow-automation/SKILL.md)。

## 配置与运行态边界

- `openclaw/openclaw.json`：仓库 overlay 源。
- `$HOME/.openclaw/openclaw.json`：OpenClaw 运行态配置。
- `cron/jobs.json`：仓库中的调度模板。
- `$HOME/.openclaw/cron/jobs.json`：机器上的实际调度状态。
- `.workflow/`：流水线运行记录、证据和临时状态。
- `vendor/openclaw-official/`：上游实现来源；本地适配优先放在 `integration/openclaw-bridge/`。

仓库模板、机器运行态和业务终态需要分层核验。命令退出码、HTTP 成功或配置写入只代表对应层级完成；交付结论还应包含测试报告、审查结果和验收证据。

## 开发与验证

先执行语法和集成检查：

```powershell
pwsh -NoProfile -Command 'python -m compileall -q setup.py scripts skills tests'
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\integration_test.py'
```

再按改动范围运行定向测试。例如：

```powershell
pwsh -NoProfile -Command 'python -m pytest -q .\tests\scripts_openclaw_ops\test_project_delivery_runtime_installer.py .\tests\scripts_openclaw_ops\test_project_delivery_hermes_profile_smoke.py'
```

`pytest.ini` 将默认收集范围限制在当前源码测试目录，避开归档快照、vendor、Runtime 缓存和流水线产物。历史测试仍可能引用已经迁移的旧脚本路径，维护时应将断言更新到对应 Skill 的正式实现。

## 文档导航

- [文档总索引](docs/INDEX.md)
- [Project Delivery Pipeline](skills/library/project-delivery-pipeline/SKILL.md)
- [HardFlow 操作手册](skills/openclaw-hardflow-automation/SKILL.md)
- [控制面运维手册](skills/library/control-plane-ops/SKILL.md)
- [工作流管理手册](skills/library/openclaw-workflow-manager/SKILL.md)
- [OpenClaw Bridge](integration/openclaw-bridge/README.md)
- [部署与运维](docs/基础设施/部署与运维/README.md)
- [待办事项](todo.md)
- [已完成事项](done.md)

## 维护约定

1. 新任务先更新 `todo.md`，完成后迁移到 `done.md`。
2. 新功能在 `docs/INDEX.md` 登记，并补齐所属工作流文档。
3. 修改运行态前先执行 `--dry-run`，记录目标、变更范围和回滚路径。
4. `agents/agent_index.md` 等生成文件通过对应生成器更新。
5. 提交前检查配置、日志和运行产物中的 Token、Webhook、账号及机器专属路径。
6. 混合工作树只暂存本次明确修改的文件或 hunk，并在推送后回读远端 SHA。

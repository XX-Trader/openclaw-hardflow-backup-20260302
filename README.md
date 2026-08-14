# OpenClaw HardFlow

OpenClaw HardFlow 是一个面向任意软件仓库的项目交付流水线与运行配置备份。它把需求澄清、上下文收集、方案评审、隔离实现、测试、代码审查、部署验收、项目记忆写回和可选 Git 发布连接成可审计闭环。

> 本仓库只负责通用工作流基础设施、配置模板与可审计交付能力。仓库边界由自身代码和接口契约定义，与本机父目录名称无关。

## 核心能力

- **项目交付状态机**：固化从需求到验收的阶段、产物、回流点与终态。
- **多 Agent 分工**：协调、分析、外部资料核验、实现、测试、审查、部署和写回职责分离。
- **隔离实现**：代码阶段在独立工作区运行，通过验证和审查后再应用补丁。
- **证据化交付**：记录命令、退出码、测试、审查结论、部署烟测、提交和远端回读。
- **跨运行时安装**：通过统一安装器将 Skills、运维脚本与 Cron 模板安装到任意 Runtime Home。
- **通用项目记忆**：保存稳定事实、决策、交付规则与失败经验，不绑定项目名称或目录结构。
- **控制面治理**：覆盖 Task Center、Cron、路由、配置漂移、日志巡检与故障学习。

## 交付流程

```mermaid
flowchart LR
    A[需求输入] --> B[路由与上下文]
    B --> C[需求包与独立评审]
    C --> D[交付计划与独立评审]
    D --> E[隔离工作区实现]
    E --> F[验证与代码审查]
    F -->|通过| G[可选部署与验收]
    F -->|失败| E
    G --> H[项目记忆写回]
    H --> I[可选 Git 发布]
```

默认运行产物位于 `.workflow/pipeline-runs/<run_id>/`。失败会记录 `failed_stage`、`next_action` 和具体证据，后续只重跑对应失败链。

## 目录

| 路径 | 用途 |
| --- | --- |
| `setup.py` | Runtime 安装与 Cron 管理统一入口 |
| `agents/` | Agent owner、能力和运行时绑定清单 |
| `config/runtime-profiles/` | 可通过环境变量覆盖的通用 Profile 模板 |
| `scripts/openclaw-ops/` | 流水线入口、运行证据桥和运维工具 |
| `skills/library/project-delivery-pipeline/` | 项目交付状态机与安装器 |
| `skills/openclaw-hardflow-automation/` | G0-G6 门禁与评分工具 |
| `skills/library/control-plane-ops/` | Task Center、策略、Cron 与控制面脚本 |
| `hooks/` | 命令守卫、审计和经验沉淀 Hook |
| `cron/` | 调度模板与 owner 映射 |
| `integration/openclaw-bridge/` | 本地适配层与上游边界 |
| `tests/` | 流水线、安装器、控制面和 Skill 契约测试 |
| `docs/` | 架构、部署、治理、ADR 与计划 |
| `requirements.md` | 当前唯一需求基线 |
| `CHANGELOG.md` | 面向维护者的变更记录 |

## 环境要求

- Python 3.11 或兼容版本
- Git，含 submodule 与 worktree 支持
- PowerShell 7，Windows 命令统一由 `pwsh` 进入
- Node.js 与 Bash，仅在运行对应门禁脚本时需要
- 目标 Runtime CLI，仅在连接该 Runtime 时需要

## 快速开始

### 1. 初始化子模块

```powershell
pwsh -NoProfile -Command 'git submodule update --init --recursive'
```

### 2. 查看安装参数

```powershell
pwsh -NoProfile -Command 'python .\setup.py --help'
```

### 3. 安装演练

```powershell
pwsh -NoProfile -Command 'python .\setup.py --dry-run --runtime-home .\.codex-tmp\runtime-smoke --runtime-name local --emit-json'
```

### 4. 仓库策略检查

```powershell
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\repository_policy_check.py --tracked-only --emit-json'
```

该检查使用 NUL 分隔的 Git 路径清单，覆盖中文文件名，并检查领域耦合、凭证形态、机器专属路径和已退役 owner 引用。

### 5. 安装到自定义 Runtime Home

```powershell
pwsh -NoProfile -Command 'python .\setup.py --runtime-home "$HOME\.hardflow-runtime" --runtime-name local --emit-json'
```

每次产生实际变更的安装都会先保存受管文件快照；无变化的重复安装复用原快照。需要恢复最近一次变更前状态时运行：

```powershell
pwsh -NoProfile -Command 'python .\setup.py rollback --runtime-home "$HOME\.hardflow-runtime" --runtime-name local --emit-json'
```

回滚逐个恢复或移除清单中的受管文件，保留 Runtime 中的非托管内容；连续执行可沿安装快照逐次回退。

### 6. 演练通用项目流水线

```powershell
pwsh -NoProfile -Command 'python .\skills\library\project-delivery-pipeline\scripts\pipeline_runner.py --project-key demo --requirement "为示例服务补充健康检查和回归测试" --dry-run --emit-json'
```

真实执行阶段通过 `--research-command`、`--code-command`、`--verification-command`、`--code-review-command`、`--deployment-command` 和 `--git-publish-command` 注入项目自己的命令。部署阶段只在需求明确要求且已配置命令时进入。

## 通用配置

| 环境变量 | 含义 | 默认值 |
| --- | --- | --- |
| `PROJECT_PIPELINE_PROJECT_DIR` | 目标项目目录 | 当前仓库根目录 |
| `PROJECT_PIPELINE_PROJECT_KEY` | 项目记忆键 | `generic-project` |
| `HARDFLOW_RUNTIME_HOME` | Runtime 状态目录 | `$HOME/.hardflow-runtime` |
| `HARDFLOW_WORKFLOW_REPO` | 工作流仓库目录 | 当前仓库根目录 |
| `PROJECT_PIPELINE_RUNTIME_HOST` | Runtime 标识 | `local` |
| `PROJECT_PIPELINE_DEPLOYMENT_COMMAND` | 项目部署命令 | 空 |
| `PROJECT_PIPELINE_SMOKE_COMMANDS` | 以 `;;` 分隔的部署烟测命令 | 空 |
| `PROJECT_PIPELINE_LIVE_BRIDGE_TEST_COMMAND` | 项目自定义验证命令 | 空 |

未知环境值使用 `TARGET_PROJECT`、`TARGET_RUNTIME`、`TARGET_CHANNEL` 等占位符；仓库模板不保存机器专属路径、账号或凭证。

## 开发与验证

```powershell
pwsh -NoProfile -Command 'python -m pip install -r requirements-dev.txt'
pwsh -NoProfile -Command 'python -m compileall -q setup.py scripts skills tests'
pwsh -NoProfile -Command 'python -m pytest -q -m quick'
pwsh -NoProfile -Command 'python -m pytest -q -m integration'
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\generic_fixture_e2e.py --kind all --emit-json'
pwsh -NoProfile -Command 'git diff --check'
```

`quick` 覆盖策略、入口、路由与配置解析，`integration` 覆盖其余组件和端到端路径；两组测试穷尽全部用例且互不重复。`pytest.ini` 会排除 vendor、缓存和运行产物。提交前还应检查：

1. 修改是否属于 `requirements.md` 当前范围。
2. 测试是否证明修复而非只证明命令启动。
3. 文档、配置模板和测试是否仍保持领域中立。
4. 暂存区是否只包含本次文件，没有运行产物或凭证。
5. 推送后远端分支是否包含本地提交。

## 文档入口

- [当前需求](requirements.md)
- [变更记录](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [MIT 许可证](LICENSE)
- [第三方声明](THIRD_PARTY_NOTICES.md)
- [文档索引](docs/INDEX.md)
- [运行手册](memory/RUNBOOK.md)
- [部署说明](memory/DEPLOYMENT.md)
- [持久决策](memory/DECISIONS.md)
- [常见陷阱](memory/PITFALLS.md)
- [待办](todo.md)
- [已完成](done.md)

## 维护约定

1. 新需求先更新 `requirements.md`，行为变化同步 `CHANGELOG.md`。
2. `todo.md` 只保留未完成事项，完成项转入 `done.md`。
3. 机器运行态与仓库模板分开管理；机器差异通过环境变量或未跟踪 overlay 注入。
4. 命令退出码、HTTP 成功、进程存活和配置写入都是分层证据，最终结论以验收条件为准。
5. 混合工作树只暂存明确文件或 hunk，推送后回读远端 SHA。

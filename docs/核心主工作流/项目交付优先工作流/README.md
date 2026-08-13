# 项目交付优先工作流

该工作流面向任意软件仓库，将需求、方案、实现、验证、审查、部署、知识写回与 Git 发布组织为可审计状态机。项目类型、目录、命令和运行环境均由参数或环境变量注入。

## 阶段

1. `intake`：记录原始需求、来源和运行标识。
2. `context_collection`：读取仓库规则、项目记忆、源码、测试和必要的外部资料。
3. `requirements_discussion`：形成范围、非目标、约束和验收标准。
4. `requirements_review`：由独立 reviewer 检查需求完整性。
5. `solution_design`：生成结构化 `delivery_plan.json`。
6. `solution_review`：检查目标文件、步骤、验证、回滚和边界。
7. `code_execution`：在隔离工作区修改代码并生成补丁。
8. `verification`：运行明确配置的测试与静态检查。
9. `code_review`：检查正确性、回归风险和需求覆盖。
10. `deployment`：仅在需求明确要求且已注入部署命令时执行。
11. `acceptance`：依据验收条件汇总证据。
12. `memory_writeback`：写回稳定事实、决策和失败经验。
13. `git_publish`：在前序门禁通过后按配置提交和推送。

## 通用约束

- `target_files`、`reference_files`、`required_checks`、`forbidden_targets` 和 `runtime_contracts` 分开记录。
- 不按行业关键词生成隐式目标文件，也不内置项目名、服务名、端口或主机路径。
- 代码阶段默认使用独立工作区；补丁经验证和审查后再应用到目标仓库。
- 失败必须记录 `failed_stage`、证据和 `next_action`，后续从对应阶段回流。
- 部署、烟测和发布均由调用方显式注入命令；空配置表示跳过该阶段。
- Git 发布前检查暂存差异，只发布本次已验收文件。

## 入口

```powershell
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\project_pipeline_entry.py --profile projectagent --source cli --route-choice coding_workflow --requirement "为示例服务补充健康检查"'
```

直接调用执行器：

```powershell
pwsh -NoProfile -Command 'python .\skills\library\project-delivery-pipeline\scripts\pipeline_runner.py --project-key demo-service --requirement "修复分页边界并补回归测试" --dry-run --emit-json'
```

## 主要产物

| 产物 | 用途 |
| --- | --- |
| `run_meta.json` | 运行身份、来源与时间 |
| `requirements.md` | 当前运行的需求包 |
| `delivery_plan.json` | 结构化交付契约 |
| `verification_report.md` | 命令、退出码与结果 |
| `code_review.md` | 审查结论与阻塞项 |
| `pipeline_state.json` | 阶段状态、失败点和下一动作 |
| `delivery_evidence.md` | 验收、部署与发布证据摘要 |

默认产物目录为 `.workflow/pipeline-runs/<run_id>/`，也可通过 `--workspace-root` 覆盖。

## 验收

- 同一需求在不同目录和 Runtime Home 下可生成一致结构的计划。
- 未明确要求部署时，入口不注入部署阶段。
- 配置部署命令后，烟测结果写入独立证据文件。
- 验证或审查失败后只回流失败链，不重复已确认阶段。
- 本地提交、远端分支和交付摘要中的 SHA 可相互核对。

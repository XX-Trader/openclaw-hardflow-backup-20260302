# 通用运行证据桥

`scripts/openclaw-ops/live_runtime_bridge.py` 将流水线阶段映射到实际 Agent、验证命令、部署命令与证据文件。桥接器只负责阶段执行和证据采集，不内置任何目标项目的业务逻辑。

## 输入

- `--stage`：流水线阶段。
- `--profile`：运行 Profile。
- `--provider` / `--model`：执行模型。
- `--project-dir`：目标仓库，默认由 `PROJECT_PIPELINE_PROJECT_DIR` 或当前仓库推断。
- `--verification-command`：可重复的项目验证命令。
- `--deployment-command`：部署命令。
- `--smoke-command`：可重复的部署后烟测命令。
- `--allow-deployment`：部署阶段的显式许可。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `PROJECT_PIPELINE_PROJECT_DIR` | 目标仓库 |
| `HARDFLOW_WORKFLOW_REPO` | 工作流仓库 |
| `PROJECT_PIPELINE_CONNECTOR_PROFILE` | 连接器 Profile |
| `PROJECT_PIPELINE_LIVE_BRIDGE_TEST_COMMAND` | 默认验证命令 |
| `PROJECT_PIPELINE_DEPLOYMENT_COMMAND` | 默认部署命令 |
| `PROJECT_PIPELINE_SMOKE_COMMANDS` | 以 `;;` 分隔的烟测命令 |

## 阶段行为

- 研究、需求、方案、实现和审查阶段调用配置的 Agent，并将标准输出、标准错误和退出码写入产物。
- 验证阶段优先运行显式命令；未配置时使用项目自身可发现的测试入口。
- 部署阶段同时满足显式许可和非空部署命令才执行，随后按顺序运行烟测。
- 写回阶段只更新结构化事实；发布阶段只处理已验收差异。

## 证据要求

每条命令记录：工作目录、启动时间、完成时间、退出码、标准输出摘要和错误摘要。HTTP、进程或配置状态只作为分层证据，最终结果由项目验收条件决定。

## 示例

```powershell
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\live_runtime_bridge.py --stage verification --project-dir TARGET_PROJECT --verification-command "python -m pytest -q"'
```

```powershell
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\live_runtime_bridge.py --stage deployment --project-dir TARGET_PROJECT --allow-deployment --deployment-command "TARGET_DEPLOY_COMMAND" --smoke-command "TARGET_SMOKE_COMMAND"'
```

未知值使用 `TARGET_PROJECT`、`TARGET_DEPLOY_COMMAND`、`TARGET_SMOKE_COMMAND` 等占位符，实际值由调用环境提供。

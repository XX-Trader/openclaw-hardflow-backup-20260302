# 多 Agent Runtime 当前基线

## 目标

在任意软件仓库中以角色分离方式完成需求澄清、实现、验证、审查和交付，并保证每个结论可回溯到产物和命令。

## 角色

| 角色 | 责任 | 禁止替代的终态 |
| --- | --- | --- |
| `coordinator` | 编排状态、依赖与回流 | 不代替实现或审查 |
| `project-agent` | 需求、范围和验收 | 不直接认定代码通过 |
| `web-agent` | 外部资料核验 | 不把搜索摘要当实现证据 |
| `backend-dev` / `frontend-dev` | 隔离实现与补丁 | 不自行跳过测试 |
| `tester` | 执行验证并保存证据 | 不以命令启动代替成功 |
| `reviewer` | 独立需求、方案和代码审查 | 不复用作者结论 |
| `deployer` | 按注入命令部署和烟测 | 不猜测服务、端口或目标环境 |
| `doc-writer` | 文档与项目记忆写回 | 不改写未确认事实 |

## 当前入口

- `scripts/openclaw-ops/project_pipeline_entry.py`
- `scripts/openclaw-ops/live_runtime_bridge.py`
- `skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`
- `skills/library/project-delivery-pipeline/scripts/runtime_installer.py`

## 不变量

1. 项目目录、Runtime Home、Profile、命令和连接器均可注入。
2. 目标文件来自需求与仓库证据，不来自历史项目关键词。
3. 实现阶段使用隔离工作区，补丁合入前必须通过验证与审查。
4. 部署默认关闭，只由明确需求和已配置命令共同开启。
5. 失败保存具体证据和回流动作；已完成阶段不重复执行。
6. 会话转录、运行缓存、真实账号和机器凭证不进入版本库。

## 最小回归

```powershell
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_project_pipeline_entry.py tests/scripts_openclaw_ops/test_live_runtime_bridge.py'
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py'
```

## 已知边界

- 外部运行时、连接器和部署系统由各环境负责安装与鉴权。
- 默认模板只提供结构和占位符，不携带机器差异。
- 项目验收命令由目标仓库声明；缺失时执行器只运行可证明安全且可发现的基础检查。

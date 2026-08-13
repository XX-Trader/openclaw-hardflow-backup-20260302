# 部署说明

## 变量

```text
PROJECT_PIPELINE_PROJECT_DIR=<target repository>
PROJECT_PIPELINE_PROJECT_KEY=<stable project key>
HARDFLOW_RUNTIME_HOME=<runtime state directory>
HARDFLOW_WORKFLOW_REPO=<this workflow repository>
PROJECT_PIPELINE_RUNTIME_HOST=<runtime label>
PROJECT_PIPELINE_DEPLOYMENT_COMMAND=<project deployment command>
PROJECT_PIPELINE_SMOKE_COMMANDS=<command 1;;command 2>
```

模板中只保存变量名，不保存凭证或机器专属值。

## 安装演练

```powershell
pwsh -NoProfile -Command 'python .\setup.py --dry-run --runtime-home .\.codex-tmp\runtime-smoke --runtime-name local --emit-json'
```

核对输出中的源仓库、Runtime Home、将写入的 Skills、运维脚本、Cron job 和状态目录。

## 正式安装

```powershell
pwsh -NoProfile -Command 'python .\setup.py --runtime-home "$HOME\.hardflow-runtime" --runtime-name local --emit-json'
```

安装后至少验证：

1. 安装器返回成功且目标文件 SHA 与仓库源一致。
2. `project_pipeline_entry.py --help` 和 `live_runtime_bridge.py --help` 可运行。
3. Runtime Profile 配置解析成功。
4. dry-run 流水线生成完整阶段与结构化产物。
5. 若启用部署，项目命令和烟测命令均留下真实结果。

## 升级

1. 记录当前提交、Runtime 配置备份位置和回滚命令。
2. 快进或应用已审查提交。
3. 重跑安装器，只同步本次 owner 文件。
4. 运行语法检查、定向测试和安装态 smoke。
5. 读取目标 Runtime 中的文件 SHA，确认与仓库一致。

## 回滚

- 代码：回到升级前提交或反向应用本次补丁。
- Runtime 文件：恢复安装前备份，随后重启对应 Runtime。
- Cron：恢复原 jobs 文件并复核启用状态。
- 部署：执行目标项目提供的回滚命令；工作流不猜测服务管理方式。

回滚完成后重新验证入口、配置、任务状态和项目烟测，不以命令返回零替代终态检查。

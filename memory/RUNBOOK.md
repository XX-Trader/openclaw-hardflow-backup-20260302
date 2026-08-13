# 运行手册

## 1. 开始前

```powershell
pwsh -NoProfile -Command 'git status --short --branch'
pwsh -NoProfile -Command 'git rev-parse HEAD'
pwsh -NoProfile -Command 'git remote -v'
```

读取项目内 `AGENTS.md`、`requirements.md`、相关 docs、memory、代码和测试。确认目标、验收、非目标、回滚与混合工作树边界。

## 2. 语法和配置检查

```powershell
pwsh -NoProfile -Command 'python -m compileall -q setup.py scripts skills tests'
pwsh -NoProfile -Command 'python .\setup.py --help'
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\project_pipeline_entry.py --help'
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\live_runtime_bridge.py --help'
```

## 3. 流水线演练

```powershell
pwsh -NoProfile -Command 'python .\skills\library\project-delivery-pipeline\scripts\pipeline_runner.py --project-key demo --requirement "修复示例服务并补回归测试" --dry-run --emit-json'
```

检查 `pipeline_state.json`、`delivery_plan.json`、审查产物、验证命令和 `next_action`。确认目标列表中没有绝对路径、运行产物、凭证文件或自然语言接口。

## 4. 定向测试

```powershell
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_project_delivery_pipeline_runner.py'
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_project_pipeline_entry.py'
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_live_runtime_bridge.py'
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_runtime_profile_templates.py'
```

长测试使用文件重定向保存结果，分别记录通过数、失败数、耗时与超时边界。

## 5. 部署阶段

设置 `PROJECT_PIPELINE_DEPLOYMENT_COMMAND`，可选设置 `PROJECT_PIPELINE_SMOKE_COMMANDS`。入口只在需求明确包含部署动作时注入该阶段。

若部署命令失败，记录命令、返回码、输出和下一动作；若烟测失败，只重跑烟测或对应部署链，不重做已通过的研究与实现阶段。

## 6. Git 发布

```powershell
pwsh -NoProfile -Command 'git diff --check'
pwsh -NoProfile -Command 'git diff --name-only'
pwsh -NoProfile -Command 'git status --short'
```

只暂存本次文件，检查 staged diff 和敏感信息扫描，再提交、推送并执行：

```powershell
pwsh -NoProfile -Command 'git fetch origin main --prune; git rev-list --left-right --count HEAD...origin/main; git branch -r --contains HEAD'
```

## 7. 故障定位

按层检查：入口参数 → 路由 → Runtime 命令 → Agent 工作区 → 补丁回流 → 验证 → 审查 → 部署 → 写回 → 发布。每次只修当前失败层，并保留可复现命令。

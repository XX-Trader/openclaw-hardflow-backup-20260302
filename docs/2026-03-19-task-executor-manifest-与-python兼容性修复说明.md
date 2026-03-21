# 2026-03-19 Task Executor Manifest 与 Python 兼容性修复说明

## 背景

本次修复聚焦两个真实运行时问题：

1. `task_executor_runner.py` 在运行时默认读取 `OPENCLAW_HOME/ops/agents/agent_capability_manifest.json`，但现有安装链路没有显式把 manifest 路径传给任务执行器 job，导致部分服务器出现 `assignee_not_registered`、`required_capabilities_unmet`、`preflight_strict_blocked`。
2. 部分服务器仍在使用 Python 3.9，运行 `@dataclass(slots=True)` 时会抛出：

```text
TypeError: dataclass() got an unexpected keyword argument 'slots'
```

## 修复内容

### 1. task executor 安装参数补齐

- `scripts/openclaw-ops/install_task_executor_job.py` 新增可选参数：
  - `--agent-capability-manifest`
- `scripts/openclaw-ops/install_workflow_profile.py` 在安装 task executor job 时，显式传入：
  - `<workflow_repo_path>/agents/agent_capability_manifest.json`

这样运行时不再依赖错误的默认相对路径推导。

### 2. Python 3.9 dataclass 兼容层

新增兼容模块：

- `scripts/openclaw-ops/dataclass_compat.py`
- `scripts/openclaw-ops/policy/dataclass_compat.py`

兼容策略：

- Python 3.10 及以上：保留 `slots=True`
- Python 3.9 及以下：自动移除 `slots` 参数，避免运行时崩溃

已覆盖当前使用 `@dataclass(slots=True)` 的运行时脚本：

- `scripts/openclaw-ops/ops_cron_runner.py`
- `scripts/openclaw-ops/reviewer_cron_runner.py`
- `scripts/openclaw-ops/todo_patrol.py`
- `scripts/openclaw-ops/policy/bootstrap_multi_project.py`
- `scripts/openclaw-ops/policy/policy_enforcer.py`
- `scripts/openclaw-ops/policy/project_index_maintainer.py`
- `scripts/openclaw-ops/policy/task_center.py`
- `scripts/openclaw-ops/policy/workflow_setup.py`

## 预期效果

- `coordinator` 在 task preflight 阶段能够正确识别 `project-agent` / `optimization-agent` 的 `role_only` 能力。
- 旧版本 Python 不再因为 `dataclass(slots=True)` 直接退出。
- 重新安装或更新 workflow 后，相关 cron/job 可以恢复正常派发。

## 后续落地建议

服务器侧应用这次修复后，建议按顺序执行：

1. 重新同步 `openclaw-ops` 运行时文件
2. 重新安装 task executor job
3. 再观察 `preflight_warning` / `preflight_blocked` 是否明显下降
4. 最后再定向清理确认为旧噪音的遗留任务

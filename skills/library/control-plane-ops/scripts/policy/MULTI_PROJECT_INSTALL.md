# Multi Project 安装指南

目标：一套策略运行时统一服务多个项目，任务/评分/token/cost 统一记录，每个项目保留独立 `.workflow` 数据。

如果你的目标不只是“统一安装多项目运行时”，还包括：

- 一台服务器同时托管多个业务仓库
- 保留统一运维任务
- 但把 `governance auto-pr / reviewer PR gate / git sync` 按项目拆开

请同时参考：

- [docs/2026-03-17-multi-project-server-template.md](../../../docs/2026-03-17-multi-project-server-template.md)
- [project-registry.example.json](./project-registry.example.json)
- [reviewer-merge-approval.multi-project.example.json](../reviewer-merge-approval.multi-project.example.json)

## 1. 前置检查

需要满足：

- `python3` 可用
- `git` 在 `PATH`
- `OPENCLAW_HOME` 可写（默认 `~/.openclaw`）
- 每个项目目录可写（用于生成 `.workflow`）

查看帮助：

```bash
python3 skills/library/control-plane-ops/scripts/policy/bootstrap_multi_project.py --help
```

## 2. 准备项目清单（推荐）

复制并编辑：

- `scripts/openclaw-ops/policy/projects.example.json`

字段说明：

- `name`：项目名
- `path`：项目绝对路径
- `remote_name`：git 远端名（默认 `origin`）
- `expected_remote`：期望远端 URL（可选）
- `check_remote`：是否执行远端连通校验（默认 `true`）

## 3. 执行安装

方式 A：项目清单文件

```bash
python3 skills/library/control-plane-ops/scripts/policy/bootstrap_multi_project.py \
  --projects-file scripts/openclaw-ops/policy/projects.example.json \
  --openclaw-home ~/.openclaw \
  --strict-git-remote
```

方式 B：直接传多个项目路径

```bash
python3 skills/library/control-plane-ops/scripts/policy/bootstrap_multi_project.py \
  --project-root /srv/project-a \
  --project-root /srv/project-b \
  --openclaw-home ~/.openclaw
```

## 4. 安装器会做什么

1. 同步策略运行时到 `${OPENCLAW_HOME}/ops/policy`
2. 检查环境：`git`、目录权限、远端连通
3. 为每个项目生成并初始化：
   - `.workflow/task-center/task_center.db`
   - `.workflow/policy.env`
   - `.workflow/project-index/project-registry.json`（运行时本地配置，不入 Git）
4. 写入环境变量：
   - `OPENCLAW_HOME`
   - `TASK_CENTER_DIR`
   - `WORKFLOW_IO_DIR`
   - `AGENT_LOG_ROOT`
   - `PROJECT_REGISTRY`
   - `TOKEN_PRICING_FILE`
   - `POLICY_*`
5. 执行 `policy_enforcer init` 和 `validate-runtime`
6. 输出报告：
   - JSON：`.workflow/task-center/multi-project-bootstrap-report.json`
   - Markdown：`.workflow/task-center/multi-project-bootstrap-report.md`

## 5. Project-Agent 索引维护

每个项目安装后可执行：

```bash
python3 "$PROJECT_INDEX_MAINTAINER_PY" \
  --registry "$PROJECT_INDEX_REGISTRY" \
  --git-pull \
  --emit-json
```

会自动维护：

- `.workflow/project-index-local/PROJECT_INDEX.md`
- `.workflow/project-index-local/project-index.json`

## 6. 安装后核查（强烈建议）

```bash
python3 skills/library/control-plane-ops/scripts/policy/policy_enforcer.py check-config \
  --openclaw-config "$OPENCLAW_HOME/openclaw.json" \
  --project-registry "$PROJECT_REGISTRY" \
  --strict
```

## 7. 常见问题

- `git not found in PATH`：安装 git 并确认 `git --version` 可执行。
- `project path not writable`：修正目录权限或更换可写路径。
- `git remote unreachable`：修复 SSH key/token 或网络后重试。
- `git remote mismatch`：检查 `expected_remote` 是否配置错误。

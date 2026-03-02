# Multi Project 安装指南

目标：一套策略运行时，服务多个项目目录，统一记录任务和 token，同时每个项目保留独立 `.workflow` 数据。

## 1. 安装前检查

需要满足：

- Python 可执行（建议 `python3`）
- `git` 在 PATH 中
- OpenClaw 根目录可写（默认 `~/.openclaw`，可自定义）
- 每个项目目录可写（用于创建 `.workflow/policy.env` 和 `task_center.db`）

可先查看帮助：

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py --help
```

## 2. 准备项目清单（推荐）

复制并修改：`projects.example.json`。

字段说明：

- `name`: 项目标识名（用于报告展示）
- `path`: 项目绝对路径
- `remote_name`: Git 远端名，默认 `origin`
- `expected_remote`: 期望远端 URL（可选）
- `check_remote`: 是否做 `git ls-remote` 连通检查（默认 `true`）

## 3. 执行安装

方式 A：用清单文件

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py \
  --projects-file scripts/openclaw-ops/policy/projects.example.json \
  --openclaw-home ~/.openclaw \
  --strict-git-remote
```

方式 B：直接传多个路径

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py \
  --project-root /srv/project-a \
  --project-root /srv/project-b \
  --openclaw-home ~/.openclaw
```

## 4. 脚本会做什么

1. 同步策略运行时到 `${OPENCLAW_HOME}/ops/policy`
2. 检查环境信息：`git` 路径与版本、OpenClaw 目录可写性
3. 对每个项目执行：
   - 路径有效性检查
   - 可写权限检查
   - Git 仓库检查（根目录、远端地址、远端连通）
   - 初始化 `.workflow/task-center/task_center.db`
   - 生成 `.workflow/policy.env`
   - 执行 `policy_enforcer init` + `validate-runtime`
4. 输出报告：
   - JSON：`.workflow/task-center/multi-project-bootstrap-report.json`
   - Markdown：`.workflow/task-center/multi-project-bootstrap-report.md`

## 5. 常见问题

`git not found in PATH`：
- 安装 git 并确保命令行可执行 `git --version`。

`project path not writable`：
- 当前用户对该目录没有写权限，需改权限或改用可写目录。

`git remote unreachable or permission denied`：
- 仓库凭据/网络不可用，先修复 SSH key 或 token，再重跑。
- 若仅内网临时不可达，可先不加 `--strict-git-remote`，记录为 note。

`git remote mismatch`：
- 项目清单 `expected_remote` 与实际远端不同，需确认仓库是否填错。


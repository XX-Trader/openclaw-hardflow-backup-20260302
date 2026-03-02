# Policy Enforcer（OpenClaw 强约束）

本目录提供 OpenClaw 的 fail-close 策略控制和任务中心能力。

## 文件说明

- `policy_enforcer.py`
  - 策略入口 CLI。
  - 负责任务字段校验、风险确认、模型白名单、失败升级、token 记账。
- `task_center.py`
  - SQLite 任务中心（原子化）。
  - 记录任务、事件、token 使用量、每日汇总。
- `policy-config.json`
  - 核心策略配置。
- `routing-rules.json`
  - 路由规则（可热更新）。
- `token-pricing.json`
  - 模型单价表（本地估算，不依赖外网）。
- `bootstrap_multi_project.py`
  - 多项目自适应安装器。
  - 检查项目路径、权限、Git 仓库与远端连通，并为每个项目生成 `.workflow/policy.env`。

## 快速开始（单项目）

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py init \
  --db .workflow/task-center/task_center.db \
  --policy-file scripts/openclaw-ops/policy/policy-config.json \
  --routing-file scripts/openclaw-ops/policy/routing-rules.json \
  --pricing-file scripts/openclaw-ops/policy/token-pricing.json
```

## 多项目安装（推荐）

优先看文档：`MULTI_PROJECT_INSTALL.md`。

最小命令（直接传多个项目路径）：

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py \
  --project-root /srv/project-a \
  --project-root /srv/project-b \
  --openclaw-home ~/.openclaw
```

使用项目清单文件：

```bash
python3 scripts/openclaw-ops/policy/bootstrap_multi_project.py \
  --projects-file scripts/openclaw-ops/policy/projects.example.json \
  --openclaw-home ~/.openclaw \
  --strict-git-remote
```

## 常用命令

创建任务：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py create-task \
  --db .workflow/task-center/task_center.db \
  --reason "修复 cron 超时" \
  --source "cron" \
  --priority high \
  --risk-level high \
  --requirement "目标任务超时时间改为 30 分钟" \
  --result-output "任务状态 passed，日志无超时" \
  --acceptance "连续 3 次调度成功"
```

按规则路由任务：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py route-task \
  --description "生产 cron 连续失败，需要立即修复" \
  --source "ops"
```

记录 token：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py record-token \
  --task-id <TASK_ID> \
  --agent-id backend-dev \
  --model glmcode/glm-5 \
  --input-tokens 12000 \
  --output-tokens 8000
```

生成日报：

```bash
python3 scripts/openclaw-ops/policy/policy_enforcer.py daily-summary \
  --date 2026-03-02 \
  --output done.md
```


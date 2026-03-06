# Python 治理桥接契约

## 目标

保留 Python 治理层，不把业务治理逻辑强行迁入官方核心；官方 OpenClaw 只负责稳定触发面和运行时加载。

## 职责边界

官方 surface 负责：

- `cron`
- `hooks`
- `plugins`
- `skills`
- `webhook/gateway`

本仓库 Python 治理层负责：

- `policy_enforcer.py`
- `task_center.py`
- `project_index_maintainer.py`
- `task_executor_runner.py`
- 其他 reviewer/evolution/patrol runner

## 触发约束

治理脚本的正式入口只允许来自以下桥接点：

- 官方 `openclaw cron`
- 官方 hooks loader
- 官方 gateway/webhook

不允许的做法：

- 直接修改 `vendor/openclaw-official` 内部状态文件格式
- 通过私有 patch 把治理逻辑嵌入 vendor 核心

## 输出契约

- `policy_enforcer.py`：结构化 JSON CLI。
- `project_index_maintainer.py`：`--emit-json` 时输出 JSON；静默成功输出 `NO_REPLY`。
- `task_executor_runner.py`：面向机器消费输出 JSON summary。
- 上层 cron/hook 触发链路应把上述输出原样传回，不再包装额外说明文本。

## 任务执行器附加约束

- `task_executor_runner.py` 在未显式传入 `--model` 时，默认从同目录 `policy-config.json` 解析 `primary_model` / `allowed_models`，避免 cron job 写死已被策略禁用的模型。
- `task_executor_10m` 这类 cron prompt 必须要求首轮回复只包含一次 `exec` 工具调用，并原样返回命令 stdout/stderr，不能先输出解释性文本。

## 验证

```bash
python scripts/openclaw-ops/policy/policy_enforcer.py next-todo --limit 3
python scripts/openclaw-ops/policy/policy_enforcer.py report-agent-result --help
python scripts/openclaw-ops/policy/project_index_maintainer.py --help
python scripts/openclaw-ops/policy/task_executor_runner.py --help
```

预期：

- 帮助文本中明确说明官方触发面与输出契约。
- Python 治理脚本仍可独立运行，不依赖 vendor 私有实现细节。

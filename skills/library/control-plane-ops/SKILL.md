---
name: control-plane-ops
description: 通用控制面巡检技能，用于 Task Center、Cron、调度注册表、运行快照和故障恢复。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}}}
---

# 控制面运维

## Owner

- `scripts/export_schedule_registry.py`：导出调度事实。
- `scripts/recover_stale_cron_running_state.py`：恢复过期 running 状态。
- `scripts/system_schedule_snapshot.py`：生成系统调度快照。
- `scripts/ops_cron_runner.py`：增量/全量巡检。
- `scripts/policy/`：Task Center 与策略门禁。

## 操作顺序

1. 读取 `cron/jobs.json` 和 Runtime 状态。
2. 先执行只读或 dry-run。
3. 仅修复已确认的失败链。
4. 以任务终态、结构化输出和运行证据验收。

Runtime 安装边界使用仓库根目录 `python setup.py --dry-run --emit-json` 核对。

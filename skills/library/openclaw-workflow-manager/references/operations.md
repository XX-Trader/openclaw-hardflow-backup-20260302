# Runtime 运维入口

| 能力 | 入口 |
| --- | --- |
| 安装预检 | `python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --dry-run --emit-json` |
| 正式安装 | `python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --emit-json` |
| 技能补齐 | `skills/library/openclaw-workflow-manager/scripts/ensure_runtime_skills.py` |
| 调度导出 | `skills/library/control-plane-ops/scripts/export_schedule_registry.py` |
| 卡住恢复 | `skills/library/control-plane-ops/scripts/recover_stale_cron_running_state.py` |
| 健康检查 | `skills/library/log-monitor/scripts/runtime_profile_healthcheck.py` |
| 卸载 | `skills/library/openclaw-workflow-manager/scripts/uninstall_workflow_profile.py` |

所有有写入的命令先在临时 Runtime Home 或 dry-run 模式验证，并保留输出作为回滚基线。

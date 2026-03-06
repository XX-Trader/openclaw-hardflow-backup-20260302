# 上游迁移验收清单

## 前置条件

- `vendor/openclaw-official` 已固定到预期 tag。
- 本次改动未直接写入 `vendor/openclaw-official`。
- 如需使用 `openclaw cron status/run`，先确保官方 gateway 已运行。

启动网关示例：

```bash
openclaw gateway run
```

## 验收项

1. 上游绑定正常

```bash
python scripts/openclaw-ops/openclaw_upstream_binding.py status
```

预期：

- `vendor_exists=true`
- `is_submodule=true`
- `vendor_ref_exact_tag=v2026.3.2`

2. overlay 运行时边界正常

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path . --dry-run --emit-json
```

预期：

- 包含 `sync_overlay_openclaw_config (runtime boundary)` 步骤。
- `runtime_bridge.hooks` / `runtime_bridge.skills` 信息存在。

3. cron 走官方 surface

```bash
openclaw cron status --json
openclaw cron run <job-id> --force
openclaw cron runs --id <job-id> --limit 20
```

预期：

- 官方 CLI 能看到并触发已安装任务。

4. hooks 走官方 loader

```bash
openclaw hooks list --json
openclaw hooks check --json
```

预期：

- 能看到 hardflow hooks。
- 无缺失 handler。

5. channels/plugins 走官方 surface

```bash
openclaw plugins list
openclaw config get channels.telegram
```

6. Python 治理层仍可独立运行

```bash
python scripts/openclaw-ops/policy/policy_enforcer.py next-todo --limit 3
python scripts/openclaw-ops/policy/policy_enforcer.py report-agent-result --help
```

7. vendor 未被污染

```bash
git diff -- vendor/openclaw-official
```

预期：

- 空输出。

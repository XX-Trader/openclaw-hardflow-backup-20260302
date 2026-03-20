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

5.1 OpenViking 记忆链路标准化检查

```bash
python scripts/openclaw-ops/check_openviking_stack.py --workspace-root .
```

预期：

- 输出 `mode=official-default` 或 `mode=openviking`
- 若为 `openviking`：
  - `routing_layer.passed=true`
  - `plugin_layer.passed=true`
  - `service_layer.passed=true`
- 会产出当前 run 的 `openviking-stack.json` 与 `openviking_stack.json` gate 文件

说明：

- `check-deployment-acceptance.sh` 会自动优先使用 `python3`，不存在时回退到 `python`
- `check_openviking_stack.py` 会优先读取运行时 `memory-openviking` 的 URL / 端口配置，再回退到环境变量和默认端口

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

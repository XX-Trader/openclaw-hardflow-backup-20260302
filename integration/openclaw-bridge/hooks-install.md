# OpenClaw Hooks 安装桥接说明

## 目标

把本仓库的 hooks 明确收敛到官方 hooks loader/surface 管理，避免再通过手工复制文件到 `~/.openclaw` 或 `~/.claude` 维持运行时。

## 默认策略

- 部署/运行时默认策略：由 `scripts/openclaw-ops/install_workflow_profile.py` 把仓库 `hooks/` 目录写入 `~/.openclaw/openclaw.json` 的 `hooks.internal.load.extraDirs`。
- 官方运行时负责发现、加载、检查这些 hooks。
- `scripts/openclaw-ops/sync_openclaw_ops_files.py` 只同步 `ops/` 脚本，不再承担 hooks runtime 同步职责。

## 当前核心 hooks

- `hardflow-command-guard`
- `hardflow-audit`
- `hardflow-stop-gate-reminder`
- `hardflow-policy-enforcer`

这些 hooks 继续保留在仓库中，但职责只限于本地增强逻辑，不再负责运行时安装编排。

## 本地开发可选策略

如需在本地显式 link 单个 hook，可使用官方命令：

```bash
openclaw hooks install -l <repo>/hooks/hardflow-command-guard
openclaw hooks install -l <repo>/hooks/hardflow-audit
openclaw hooks install -l <repo>/hooks/hardflow-stop-gate-reminder
openclaw hooks install -l <repo>/hooks/hardflow-policy-enforcer
```

说明：

- `-l/--link` 更适合本地开发时即时调试单个 hook。
- 批量部署时，优先使用 `hooks.internal.load.extraDirs`，这样边界更稳定，也不会把运行时状态分散到多个位置。

## 验证

```bash
openclaw hooks list --json
openclaw hooks check --json
```

预期：

- 能看到本地 hardflow hooks 与内置 hooks。
- `hooks check` 无缺失 handler/入口错误。

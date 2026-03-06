# OpenClaw Runtime Boundary

## 目标

冻结“官方运行时”和“本地 workflow overlay”的职责边界，先收敛入口，再逐步迁移 cron、hooks、plugins 等能力。

## 单一运行时入口

- 官方运行时根目录固定为 `vendor/openclaw-official/`。
- 本仓不是 OpenClaw 主程序仓库，不承载官方核心源码复制、拼装、补丁落地。
- 上游版本绑定以 `.workflow/openclaw-upstream-binding.json` 和 `python scripts/openclaw-ops/openclaw_upstream_binding.py status` 为准。

## Overlay 责任

- `openclaw/openclaw.json`
  - 仓库内 overlay 配置源。
  - 通过 `install_workflow_profile.py` 合并写入 `~/.openclaw/openclaw.json`。
- `scripts/openclaw-ops/`
  - 负责治理脚本、自动化安装、验收与运维入口。
  - 不负责复制 `vendor/openclaw-official/` 核心代码。
- `integration/openclaw-bridge/`
  - 记录 bridge 契约、边界规则和迁移说明。

## install_workflow_profile.py 契约

- 输入：
  - `${workflow_repo_path}/openclaw/openclaw.json`
  - `${workflow_repo_path}/vendor/openclaw-official`
- 输出：
  - `~/.openclaw/openclaw.json`
  - 业务 cron 安装结果
- 明确不做：
  - 复制 `vendor/openclaw-official/*` 到 `~/.openclaw`
  - 修改 `vendor/openclaw-official/*`

## 当前边界内允许的动作

- 调整 overlay 配置。
- 安装或更新本地业务 cron。
- 后续通过官方 hooks/plugins/skills surface 接入本地增强逻辑。
- 编写 bridge 文档和验收清单。

## 当前边界内禁止的动作

- 直接在 `vendor/openclaw-official/` 写业务逻辑。
- 继续扩展“本仓自带运行时副本”方案。
- 让 Python 治理脚本直接依赖官方内部私有文件布局。

## 验证

```bash
python scripts/openclaw-ops/openclaw_upstream_binding.py status
```

期望结果：

- `vendor_exists=true`
- `is_submodule=true`
- `vendor_ref_exact_tag=v2026.3.2`

## Runtime Compatibility Note

- `install_workflow_profile.py` 会在写入 runtime config 时移除 `agents.defaults.outputPolicy`。
- 原因：当前官方 `openclaw 2026.3.2` 会将该键视为非法配置；兼容清理只发生在 runtime 合并阶段，不修改 `vendor/openclaw-official/`。

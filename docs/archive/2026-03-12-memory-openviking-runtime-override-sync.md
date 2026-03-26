# 2026-03-12 memory-openviking Runtime Override Sync

## 目标

把 `memory-openviking` 的 cron prompt 误判修复纳入主仓库安装链路，避免只能靠单机手工覆盖 `~/.openclaw/extensions/memory-openviking/text-utils.ts`。

## 这次变更

- 新增受管目录：`scripts/openclaw-ops/runtime-plugin-overrides/`
- 新增同步脚本：`scripts/openclaw-ops/sync_runtime_plugin_overrides.py`
- `install_workflow_profile.py` 现在默认会执行一次 plugin override 同步

## 受管范围

当前只同步：

- `memory-openviking/text-utils.ts`
- `memory-openviking/text-utils.test.mjs`

目标位置：

- `~/.openclaw/extensions/memory-openviking/`

## 为什么不用手工 scp

- 这样修复才能进入主仓库 `git` 历史
- 服务器只需要 `git pull + install` 就能拿到同一份补丁
- 后续再次安装时，旧的受管 override 文件会按 manifest 自动更新/清理

## 当前边界

- 这不是整插件重新发布；它只负责同步受管补丁文件
- 前提仍然是目标机器已经存在可用的 `memory-openviking` 插件目录
- 如需做全量插件托管，应单独把整个插件源码与依赖安装流程纳入仓库

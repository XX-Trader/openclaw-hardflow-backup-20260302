# OpenClaw Hooks 安装桥接说明

## 目标

把本仓库的 hooks 明确收敛到官方 hooks loader/surface 管理，并且把“源码目录”和“运行时目录”正式分开，避免继续直接把仓库源码目录喂给运行时 loader。

## 默认策略

默认策略已经调整为两步：

1. `scripts/openclaw-ops/sync_openclaw_hooks_files.py`
   - 把仓库 `hooks/` 中的运行时安全文件同步到 `~/.openclaw/hooks-runtime`
2. `scripts/openclaw-ops/install_workflow_profile.py`
   - 把 `~/.openclaw/hooks-runtime` 写入 `~/.openclaw/openclaw.json` 的 `hooks.internal.load.extraDirs`

因此，官方运行时现在加载的是：

- `~/.openclaw/hooks-runtime`

而不是直接加载仓库源码目录。

## 运行时交付规则

运行时 hooks 目录只允许进入“运行时安全文件”：

1. `HOOK.md`
2. `.json`
3. `.js` / `.mjs` / `.cjs`
4. `.py`
5. `.sh`
6. `.yaml` / `.yml`
7. `.txt`

明确禁止直接进入运行时目录的文件：

1. `.ts`
2. `.tsx`
3. `.map`

这条规则的目标是：

1. 不再让 `.ts` 源码裸文件直接充当运行时入口
2. 让 Windows / Linux 上的 hooks loader 行为更稳定
3. 让 hooks 问题更容易区分是“源码问题”还是“运行时拷贝问题”

每个 hook 目录在运行时必须保留至少一个可执行入口：

1. `handler.js`
2. `index.js`

如果仓库里还保留源码层的 `.ts`，也必须在同步到运行时目录前落成可执行的 `.js` 入口。

## 当前核心 hooks

1. `hardflow-command-guard`
2. `hardflow-audit`
3. `hardflow-stop-gate-reminder`
4. `hardflow-policy-enforcer`

这些 hooks 继续保留在仓库 `hooks/` 中作为源码与说明来源，但运行时加载面已经改为 `~/.openclaw/hooks-runtime`。

## 本地开发可选策略

如需在本地显式 link 单个 hook，可使用官方命令：

```bash
openclaw hooks install -l <repo>/hooks/hardflow-command-guard
openclaw hooks install -l <repo>/hooks/hardflow-audit
openclaw hooks install -l <repo>/hooks/hardflow-stop-gate-reminder
openclaw hooks install -l <repo>/hooks/hardflow-policy-enforcer
```

说明：

1. `-l/--link` 更适合本地开发时即时调试单个 hook
2. 批量部署时，优先使用 `hooks.internal.load.extraDirs + hooks-runtime`
3. 不建议在长期运行环境中继续把仓库源码目录直接作为运行时 extraDirs

## 验证

```bash
openclaw hooks list --json
openclaw hooks check --json
```

预期：

1. 能看到 hardflow hooks 与内置 hooks
2. `hooks check` 无缺失 handler/入口错误
3. 运行时路径应指向 `~/.openclaw/hooks-runtime`，而不是仓库源码目录
4. 每个自定义 hook 目录都能在运行时找到 `handler.js` 或 `index.js`

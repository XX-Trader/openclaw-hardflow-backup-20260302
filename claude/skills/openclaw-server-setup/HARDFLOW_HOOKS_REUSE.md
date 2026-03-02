# HardFlow Hooks 复用与多服务器铺设说明

更新时间：2026-03-01 10:30

## 1. 目标

将 HardFlow hooks 统一放在用户目录，做到：

1. 与具体项目解耦（跨项目复用）。
2. 服务器重建后可快速恢复。
3. 与 `openclaw-server-setup` 技能文档一致。

## 2. 统一目录标准（推荐）

主目录（推荐）：

- Ubuntu 用户：`/home/<user>/.claude/hooks`
- root 用户：`/root/.claude/hooks`

兼容目录（可选）：

- `~/.openclaw/hardflow-hooks/hooks`

说明：

1. 当前 6 台服务器已统一存在 `~/.claude/hooks`。
2. 若同时保留兼容目录，`extraDirs` 里主目录放第 1 位即可。

## 3. hooks 清单（7 + _lib）

必须存在：

1. `hardflow-command-guard`
2. `hardflow-audit`
3. `hardflow-stop-gate-reminder`
4. `hardflow-experience-capture`
5. `hardflow-experience-recall`
6. `hardflow-experience-evolve`
7. `hardflow-policy-enforcer`
7. `_lib`

## 4. OpenClaw 配置（单机）

```bash
openclaw config set --json hooks.internal.enabled true
openclaw config set hooks.internal.load.extraDirs[0] ~/.claude/hooks

openclaw config set --json hooks.internal.entries.hardflow-command-guard.enabled true
openclaw config set --json hooks.internal.entries.hardflow-audit.enabled true
openclaw config set --json hooks.internal.entries.hardflow-stop-gate-reminder.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-capture.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-recall.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-evolve.enabled true
openclaw config set --json hooks.internal.entries.hardflow-policy-enforcer.enabled true
```

## 5. 多服务器同步命令模板

```bash
# 本地执行，按你的 ssh_config 别名替换
scp -F "D:/学习资料/ssh_keys/ssh_config" -r .claude/hardflow/hooks/* <server>:/home/ubuntu/.claude/hooks/
# root 服务器用：
scp -F "D:/学习资料/ssh_keys/ssh_config" -r .claude/hardflow/hooks/* <server>:/root/.claude/hooks/
```

## 6. 验收标准

```bash
find ~/.claude/hooks -maxdepth 1 -type d -name 'hardflow-*' | wc -l
openclaw hooks check
openclaw hooks list | grep hardflow
```

通过标准：

1. `hardflow-*` 目录数量为 `6`。
2. `openclaw hooks check` 显示 `Ready: 10, Not ready: 0`。

## 7. 六台服务器复核结果（最新）

1. `hangqing-zhongxin`：通过（6 hooks，Ready 10/10）
2. `pm-website`：通过（6 hooks，Ready 10/10）
3. `coingod`：通过（6 hooks，Ready 10/10）
4. `nofx`：通过（6 hooks，Ready 10/10）
5. `tokyo-claw`：通过（6 hooks，Ready 10/10）
6. `大白pm`：通过（6 hooks，Ready 10/10）

## 8. 本地备份位置（用户目录）

1. hooks 实际目录：`C:\Users\superma\.claude\hooks`
2. 自动化归档目录：`C:\Users\superma\.claude\skills\openclaw-hardflow-automation`

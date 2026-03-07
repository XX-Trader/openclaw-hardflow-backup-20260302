---
name: openclaw-remote-safe-update
description: Use when remote OpenClaw workflow repositories fail git pull because runtime-generated files are dirty, or when multi-server deployment needs a safe update workflow with runtime reset, stash, or snapshot behavior while excluding google-us by default.
description_zh: openclaw-remote-safe-update 技能，处理远程 pull 冲突，支持 runtime-reset、stash 和 snapshot 三种策略。
---

# OpenClaw Remote Safe Update

这个技能处理远程服务器上 `openclaw-hardflow-backup-20260302` 仓库的更新冲突。重点不是“无脑自动合并”，而是先区分冲突来源，再选策略。

## 推荐原则

- 运行态自动生成文件不要合并。
- 人工改动不要默认丢弃。
- 默认排除 `google-us`。
- 默认同步方式始终是 `git fetch` + `git pull --ff-only`。

## 三档策略

### 1. `runtime-reset`（默认，推荐）

只清理这些运行态目录，然后再拉取：

- `.workflow/project-index/`
- `.workflow/project-index-local/`
- `.workflow/experience/`
- `.workflow/sessions/`
- `scripts/openclaw-ops/policy/runtime/`
- `openclaw-memory/`
- `memory/`

如果存在白名单之外的改动，直接停止。

适合：

- 远程机器只是被索引、memory、session 文件弄脏。
- 目标是把服务器快速对齐到远端最新代码。

### 2. `stash-nonvolatile`

把白名单之外的人工改动先 `stash`，拉取完成后再 `stash pop`。

适合：

- 确实有少量人工改动想保留。
- 接受 `stash pop` 可能再次冲突，需要人工收尾。

注意：

- 这不是默认策略。
- 如果 `stash pop` 失败，脚本会停在 `stash_pop_conflict`。

### 3. `snapshot-branch`

先把当前工作区保存到时间戳分支，再切回主分支执行同步。

适合：

- 服务器上有一批本地改动，但你不想直接丢，也不想立即合并。
- 想先“封存现场”，再把主分支恢复到可部署状态。

## 默认阻断条件

出现以下状态时，不继续自动同步：

- `ambiguous_repo`
- `missing_repo`
- `blocked_branch`
- `blocked_diverged`
- `blocked_local_commits`
- `blocked_dirty_nonvolatile`

## 常用命令

先检查：

```bash
python3 scripts/openclaw-ops/remote_safe_update.py --mode inspect
```

只清理运行态后同步：

```bash
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy runtime-reset
```

先 stash 再拉取：

```bash
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy stash-nonvolatile
```

先快照到分支再拉取：

```bash
python3 scripts/openclaw-ops/remote_safe_update.py --mode sync --strategy snapshot-branch
```

像 `大白pm` 这种同机两份 repo 的机器，需要显式路径：

```bash
python3 scripts/openclaw-ops/remote_safe_update.py \
  --mode sync \
  --servers 大白pm \
  --repo-path ~/openclaw-hardflow-backup-20260302
```

## 什么时候不要用“自动合并”

- 冲突文件是索引、session、memory、runtime json。
- 这些文件每台机器本地状态不同，合并只会把噪音重新带回来。
- 这类文件正确处理方式是：恢复或清理，不是 merge。

## 相关实现

- `scripts/openclaw-ops/remote_safe_update.py`
- `scripts/openclaw-ops/remote_safe_update.ps1`
- `scripts/openclaw-ops/remote_safe_update.sh`

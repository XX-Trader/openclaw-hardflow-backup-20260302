---
name: git-sync
description: 通用 Git 快照、提交备份与远端同步技能，强调显式范围、验证和回滚。
metadata: {"openclaw": {"requires": {"bins": ["python3", "git"]}}}
---

# Git 同步与备份

## Owner

- `scripts/local_snapshot_runner.py`
- `scripts/local_git_backup_runner.py`
- `scripts/git_sync_push_runner.py`
- 跨节点分发由 `skills/library/fleet-sync/` 负责。

## 规则

1. 先确认仓库、分支、远端和回滚提交。
2. 混合工作树只暂存明确文件或 hunk。
3. 本地备份与远端推送分层记录。
4. 推送后 fetch 并比较本地与远端提交。

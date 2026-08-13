# 代码优化 Backlog

当前唯一待办事实源是仓库根目录的 [`todo.md`](../../todo.md)，当前需求事实源是 [`requirements.md`](../../requirements.md)。本文件只保留治理规则，避免形成第二套任务账本。

## 收录规则

1. 每项必须包含 owner、依赖、触发条件、验收命令和回滚点。
2. 已删除 owner 的脚本、测试和安装命令不继续作为待办基线。
3. 运行缓存、会话转录、凭证和机器专属路径不进入仓库。
4. 新能力优先扩展现有 Skill owner，不在 `scripts/openclaw-ops/` 重建重复入口。
5. 完成项同步到 `done.md` 和 `CHANGELOG.md`。

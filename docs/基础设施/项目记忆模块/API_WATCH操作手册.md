# API Watch 操作手册

> 版本：v1.0 | 2026-04-22
> 关联文档：[项目交付优先工作流架构设计](../../核心主工作流/项目交付优先工作流/项目交付优先工作流架构设计.md)

---

## 1. 职责

定期检查项目声明过的第三方依赖来源（官方 docs / changelog / repo），发现变更时记录并通知。

**核心原则**：只检查项目显式声明过的来源，不做全局泛化扫描。

## 2. 执行方式

- **频率**：每周一次（低频，token 消耗极低）
- **触发**：cron job
- **范围**：按项目逐个检查 `SOURCE_REGISTRY.json`

## 3. 检查逻辑

```bash
source_registry_watcher.py \
  --project-key <key> \
  --registry-path .workflow/project-memory/<key>/SOURCE_REGISTRY.json \
  --output-path .workflow/project-memory/<key>/CHANGELOG.ndjson \
  --notify-on-change true
```

### 3.1 检查步骤

1. 读取 `SOURCE_REGISTRY.json` 中每个来源的 `docs_urls` / `changelog_urls` / `repo_urls`
2. 对 `changelog_urls` 做 HTTP HEAD 检查 `Last-Modified` / `ETag`
3. 对 `repo_urls` 调 GitHub API 检查最新 release tag
4. 对比 `current_version`，发现变更则写入 `CHANGELOG.ndjson`

### 3.2 变更记录格式

```json
{
  "timestamp": "2026-04-22T10:00:00Z",
  "source_id": "freqtrade-official",
  "change_type": "version_update",
  "old_version": "2024.4",
  "new_version": "2024.5",
  "details": "https://github.com/freqtrade/freqtrade/releases/tag/2024.5",
  "change_policy": "notify_and_update",
  "action_required": true
}
```

## 4. 按策略处理变更

| change_policy | 行为 |
|---------------|------|
| `ignore` | 记录到 CHANGELOG，不通知 |
| `notify_only` | 记录 + 通知项目 owner |
| `notify_and_update` | 记录 + 通知 + 生成修订任务 |
| `notify_and_block` | 记录 + 通知 + 标记为阻塞（需人工处理） |

## 5. 错误处理

| 错误 | 处理 |
|------|------|
| 来源不可访问 | 记录失败，重试 3 次后告警 |
| GitHub API 限流 | 延迟后重试，使用 token 池轮换 |
| 版本解析失败 | 记录原始数据，人工标注 |

## 6. 与 api-registry-manager 的联动

发现 API 变更后：
1. 更新 `SOURCE_REGISTRY.json` 中的 `current_version` 和 `last_checked`
2. 如 `change_policy` 为 `notify_and_update`，触发 api-registry-manager 的 `check` 动作
3. 如需修改 API 调用代码，生成修订任务给 coordinator

## 7. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-22 | 初始版本，定义 API watch 执行逻辑 |

# source_registry_watcher.py — 接口规范

> 版本：v1.1 | 2026-04-27
> 实现者：HardFlow
> 审核者：code-reviewer

---

## 1. 职责

定期检查项目声明过的第三方来源，发现变更时记录并通知。

**铁律**：只检查项目显式声明过的来源，不做全局泛化扫描。

## 2. 命令行接口

```bash
# 检查单个项目
python source_registry_watcher.py \
  --project-key <key> \
  --registry-path <path/to/SOURCE_REGISTRY.json> \
  --output-path <path/to/CHANGELOG.ndjson> \
  [--notify-on-change]

# 检查所有项目
python source_registry_watcher.py \
  --scan-all \
  --base-path .workflow/project-memory/ \
  [--notify-on-change]
```

`--base-path` 是安装态事实源入口；传入 runtime 项目记忆目录时，脚本必须按该目录扫描，不能回落到脚本默认目录。

## 3. 检查逻辑

### 3.1 检查流程

```python
for source in SOURCE_REGISTRY.sources:
    # 1. 检查 docs_url
    head_response = http_head(source.urls.docs)
    if head_response.last_modified > source.last_checked:
        record_change(source, "docs_updated")

    # 2. 检查 changelog_url
    head_response = http_head(source.urls.changelog)
    if head_response.last_modified > source.last_checked:
        record_change(source, "changelog_updated")

    # 3. 检查 repo_url 的 release
    if source.urls.repo and is_github_repo(source.urls.repo):
        latest_release = github_api_latest_release(source.urls.repo)
        if latest_release.tag_name > source.current_version:
            record_change(source, "version_update",
                         old=source.current_version,
                         new=latest_release.tag_name)

    # 4. 更新 last_checked
    source.last_checked = now()
```

### 3.2 变更记录格式

```json
{
  "timestamp": "2026-04-22T10:00:00Z",
  "project_key": "demo-service",
  "source_id": "example-service-official",
  "change_type": "version_update|docs_updated|changelog_updated|unavailable",
  "old_version": "2024.4",
  "new_version": "2024.5",
  "details": "https://example.com/releases/v2.0.0",
  "change_policy": "notify_and_update",
  "action_required": true
}
```

## 4. 输出

```json
{
  "project_key": "demo-service",
  "checked_sources": 5,
  "changes_found": 2,
  "changes": [
    {
      "source_id": "example-service-official",
      "change_type": "version_update",
      "new_version": "2024.5"
    }
  ],
  "errors": [],
  "timestamp": "2026-04-22T10:00:00Z"
}
```

## 5. 错误处理

| 错误 | 处理 |
|------|------|
| 来源不可访问 | 重试 3 次，仍失败则记录为 unavailable |
| GitHub API 限流 | 延迟后重试，使用 token 池轮换 |
| 版本解析失败 | 记录原始数据，标记人工确认 |
| 注册表不存在 | 跳过，记录警告 |

## 6. 与 cron 的集成

```json
// cron/jobs.json
{
  "job_id": "source_registry_watcher",
  "schedule": "every 2 days",
  "command": "python scripts/openclaw-ops/source_registry_watcher.py --scan-all --base-path .workflow/project-memory/ --notify-on-change",
  "enabled": true
}
```

## 7. 测试用例

### TC-1: 发现版本更新
- 设置：SOURCE_REGISTRY 中 示例服务当前版本 v1.9.0，发布源最新是 v2.0.0
- 输入：watcher 检查
- 期望：记录 version_update 变更

### TC-2: 无变更
- 设置：所有来源均为最新版本
- 输入：watcher 检查
- 期望：changes_found=0

### TC-3: 来源不可访问
- 设置：mock HTTP 返回 500
- 输入：watcher 检查
- 期望：重试 3 次后记录为 unavailable

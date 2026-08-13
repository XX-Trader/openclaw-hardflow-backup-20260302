# project_memory_writer.py — 接口规范

> 版本：v1.0 | 2026-04-22
> 实现者：待分配
> 审核者：Claude Code

---

## 1. 职责

消费记忆蒸馏产物，按 `project_key` 路由写入项目记忆目录。

**铁律**：同一条经验不允许同时出现在全局记忆和项目记忆中。

## 2. 命令行接口

```bash
python project_memory_writer.py \
  --distill-report <path/to/distill_report.md> \
  [--dry-run]

# 或直接指定产物
python project_memory_writer.py \
  --project-key <key> \
  --artifact-type profile|decision|api|rule \
  --content <content_or_path> \
  [--source distill|manual]
```

## 3. 输入

### 3.1 蒸馏报告格式

蒸馏产物中带 `project_key` 的条目示例：

```markdown
## 项目路由产物

- project_key: demo-service
- artifact_type: decision
- priority: high

### 内容
...

### 来源
- 会话 ID: sess-001
- 时间: 2026-04-22
```

### 3.2 路由规则

| artifact_type | 目标文件 | 写入方式 |
|--------------|----------|---------|
| profile | PROJECT_PROFILE.md | 覆盖更新 |
| decision | DECISIONS.md | 追加到文件末尾 |
| api | API_REGISTRY.json | 合并 JSON |
| source | SOURCE_REGISTRY.json | 合并 JSON |
| rule | DELIVERY_RULES.md | 覆盖更新 |
| changelog | CHANGELOG.ndjson | 追加 NDJSON 行 |

## 4. 输出

```json
{
  "processed": 5,
  "routed": 4,
  "skipped": 1,
  "skipped_reason": "missing_project_key",
  "routes": [
    {
      "project_key": "demo-service",
      "artifact_type": "decision",
      "target_file": ".workflow/project-memory/demo-service/DECISIONS.md",
      "status": "written"
    }
  ],
  "timestamp": "2026-04-22T10:00:00Z"
}
```

## 5. 冲突解决

| 场景 | 处理 |
|------|------|
| 目标文件不存在 | 自动创建（含基础模板） |
| 与现有内容冲突 | 按时间戳保留最新版 |
| 无 project_key | 跳过，记录到日志 |
| 无效 artifact_type | 报错，不写入 |

## 6. 测试用例

### TC-1: 正常路由
- 输入：蒸馏报告含 4 个带 project_key 的条目
- 期望：4 个全部写入对应项目目录

### TC-2: 无 project_key
- 输入：1 个无 project_key 的条目
- 期望：跳过，记录 skipped_reason

### TC-3: 目标文件不存在
- 输入：project_key = "new-project" 的 decision 条目
- 期望：自动创建 `.workflow/project-memory/new-project/` 目录和 DECISIONS.md

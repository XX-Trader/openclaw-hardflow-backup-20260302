---
name: api-registry-manager
description: >
  API 注册表管理 Skill。负责项目外部 API 和来源的注册、查询、更新、删除。
  每个项目维护独立的 API_REGISTRY.json 和 SOURCE_REGISTRY.json，
  记录第三方依赖的接口定义、文档地址、版本信息。
  是 project-agent 的核心组件之一，也是 API watch 的数据源。
metadata:
  openclaw:
    actions: ["add", "remove", "list", "check"]
---

# API 注册表管理 — 操作手册

## 1. 何时使用

- 项目接入新的第三方 API 时，注册到 API_REGISTRY
- 项目依赖的官方来源变更时，更新 SOURCE_REGISTRY
- API watch 执行前，查询已注册来源
- 审查时需要验证 API 来源是否充分

## 2. 不适用场景

- 调用第三方 API → 由 backend-dev 在代码中实现
- 检索外部方案 → 由 web-agent 执行
- 监控 API 变更 → 由 source_registry_watcher.py 执行

## 3. 核心原则

### 3.1 一个项目一套注册表

每个活跃项目必须有独立的：

```
.workflow/project-memory/<project_key>/
├── API_REGISTRY.json      # API 接口定义
└── SOURCE_REGISTRY.json   # 官方来源信息
```

### 3.2 注册即承诺

注册到 API_REGISTRY 的接口，意味着项目正式依赖该接口。
变更时必须同步更新注册表，确保注册表始终反映真实依赖。

### 3.3 来源单一化

每个外部依赖只保留一个官方来源，不允许多个冲突的来源并存。

## 4. 动作定义

### 4.1 add — 注册 API/来源

**触发条件**：
- 项目新增第三方依赖
- 发现新的官方文档地址
- 版本升级后接口变更

**输入**：
- `project_key`
- `registry_type`：`api` 或 `source`
- `entry`：JSON 格式的注册条目

**输出**：
- 更新 `API_REGISTRY.json` 或 `SOURCE_REGISTRY.json`
- 校验 schema 合规性

**示例**：
```bash
api-registry-manager add \
  --project-key demo-service \
  --registry-type api \
  --entry '{
    "api_id": "example-service-rest",
    "provider_id": "example-service",
    "base_url": "http://localhost:8080/api/v1",
    "docs_url": "https://example.com/api/docs",
    "version": "2024.4",
    "endpoints": [...],
    "auth_type": "bearer",
    "change_policy": "notify_and_update"
  }'
```

### 4.2 remove — 移除 API/来源

**触发条件**：
- 项目不再依赖某个第三方 API
- 来源已废弃或合并

**输入**：
- `project_key`
- `registry_type`
- `id`：要移除的条目 ID

**输出**：
- 从注册表中移除条目
- 记录移除原因到 CHANGELOG.ndjson

### 4.3 list — 列出注册表

**触发条件**：
- 查看项目依赖了哪些 API
- API watch 执行前获取来源列表
- 审查时验证来源充分性

**输入**：
- `project_key`
- `registry_type`（可选，不指定则列出全部）

**输出**：
- 注册表内容或摘要

### 4.4 check — 检查来源健康

**触发条件**：
- 手动验证来源是否可访问
- 排查 API 调用失败问题

**输入**：
- `project_key`
- `api_id`（可选，不指定则检查全部）

**输出**：
- 每个来源的健康状态（可访问 / 不可访问 / 版本已变更）

## 5. 注册表 Schema

### 5.1 API_REGISTRY.json

```json
{
  "project_key": "demo-service",
  "version": "1.0.0",
  "last_updated": "2026-04-22T10:00:00Z",
  "apis": [
    {
      "api_id": "example-service-rest",
      "provider_id": "example-service",
      "base_url": "http://localhost:8080/api/v1",
      "docs_url": "https://example.com/api/docs",
      "changelog_url": "https://example.com/releases",
      "repo_url": "https://example.com/repository",
      "version": "2024.4",
      "endpoints": [
        {
          "path": "/profit",
          "method": "GET",
          "description": "获取收益统计",
          "parameters": [...],
          "responses": {...}
        }
      ],
      "auth_type": "bearer",
      "rate_limit": "100/min",
      "change_policy": "notify_and_update",
      "owned_by_project_agent": true
    }
  ]
}
```

### 5.2 SOURCE_REGISTRY.json

```json
{
  "project_key": "demo-service",
  "version": "1.0.0",
  "last_updated": "2026-04-22T10:00:00Z",
  "sources": [
    {
      "source_id": "example-service-official",
      "provider_id": "example-service",
      "source_type": "github_repo",
      "urls": {
        "docs": "https://example.com/docs",
        "changelog": "https://example.com/releases",
        "repo": "https://example.com/repository",
        "sdk": ""
      },
      "current_version": "2024.4",
      "last_checked": "2026-04-22T10:00:00Z",
      "check_frequency": "weekly",
      "change_policy": "notify_and_update",
      "owned_by_project_agent": true
    }
  ]
}
```

## 6. 与 API watch 的接口

`source_registry_watcher.py`（API watch cron 脚本）读取 `SOURCE_REGISTRY.json`，
按 `check_frequency` 检查每个来源的变更。

发现变更时：
1. 更新 `SOURCE_REGISTRY.json` 中的 `current_version` 和 `last_checked`
2. 写入 `CHANGELOG.ndjson`
3. 按 `change_policy` 决定是否生成修订任务

## 7. 评分与问责

| 指标 | 计算方式 |
|------|----------|
| 注册覆盖率 | 有注册表的活跃项目数 / 总活跃项目数 |
| 来源健康率 | 可访问来源数 / 总注册来源数 |
| 信息完整度 | 必填字段非空率 |

**问责**：来源健康率 < 80% 时，必须排查失效来源并更新注册表。

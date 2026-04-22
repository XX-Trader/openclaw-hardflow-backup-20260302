---
name: project-profile-manager
description: >
  项目画像管理 Skill。负责项目的创建、查询、更新、删除操作。
  每个项目有独立的画像文件（PROJECT_PROFILE.md），包含项目介绍、模块边界、API surface、
  部署方式、规划等关键信息。是 project-agent 的核心组件之一。
  coordinator 在项目任务分配前，必须先调用此 Skill 查询项目画像。
metadata:
  openclaw:
    actions: ["init", "update", "show", "list"]
---

# 项目画像管理 — 操作手册

## 1. 何时使用

- 新项目启动时，初始化项目画像
- 项目任务分配前，查询项目上下文
- 项目架构变更后，更新项目画像
- 需要查看所有活跃项目列表时

## 2. 不适用场景

- 修改业务代码 → 由 backend-dev / frontend-dev 执行
- 审查代码/方案 → 由 dual-ai-review 执行
- 检索外部方案 → 由 web-agent 执行

## 3. 核心原则

### 3.1 项目画像 = 项目的事实源

项目画像是项目维护的单一权威来源。当用户问"这个项目现在逻辑是什么样"时，
project-agent 必须能直接输出项目画像中的结构化信息，而不是翻聊天记录。

### 3.2 画像维护责任

- **project-agent** 负责维护画像的准确性和完整性
- **coordinator** 在分配项目任务前必须查询画像
- **backend-dev / frontend-dev** 实现代码时以画像中的架构边界为准

### 3.3 一个项目一个画像

每个活跃项目必须有且只有一个 `PROJECT_PROFILE.md`，存放在：

```
.workflow/project-memory/<project_key>/PROJECT_PROFILE.md
```

## 4. 动作定义

### 4.1 init — 初始化项目画像

**触发条件**：新项目首次进入系统。

**输入**：
- `project_key`：项目唯一标识（如 `xx-trader`、`openclaw-hardflow`）
- `project_name`：项目显示名
- `project_type`：项目类型（webapp / api / cli / lib / other）
- `initial_description`：项目初始描述（由用户提供或从 README 提取）

**输出**：
- 创建 `.workflow/project-memory/<project_key>/PROJECT_PROFILE.md`
- 使用模板：`templates/PROJECT_PROFILE.md`

**示例**：
```bash
# 由 coordinator 调用
project-profile-manager init \
  --project-key xx-trader \
  --project-name "XX 量化交易系统" \
  --project-type webapp \
  --initial-description "基于 freqtrade 的量化交易平台..."
```

### 4.2 update — 更新项目画像

**触发条件**：
- 项目架构变更后
- 新增/删除模块后
- API surface 变更后
- 部署方式变更后
- 规划更新后

**输入**：
- `project_key`
- `field`：要更新的字段（支持嵌套路径，如 `modules.trading`）
- `value`：新值

**输出**：
- 更新 `PROJECT_PROFILE.md`
- 在 `CHANGELOG.ndjson` 中记录变更

**禁止**：不允许删除已有字段，只允许更新和追加。

### 4.3 show — 查看项目画像

**触发条件**：
- coordinator 分配项目任务前
- 用户询问项目信息时
- 双 AI 审查需要项目上下文时

**输入**：
- `project_key`
- `--format`：输出格式（markdown / json / summary）

**输出**：
- 完整项目画像或摘要

**示例**：
```bash
project-profile-manager show xx-trader --format summary
```

### 4.4 list — 列出所有项目

**触发条件**：
- 查看系统中有哪些活跃项目
- 检查项目画像覆盖率

**输出**：
- 项目列表（project_key、project_name、最后更新时间、画像完整度）

## 5. 项目画像模板

使用模板：`templates/PROJECT_PROFILE.md`

画像必须包含以下字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| project_key | 是 | 项目唯一标识 |
| project_name | 是 | 项目显示名 |
| project_type | 是 | webapp / api / cli / lib / other |
| description | 是 | 项目一句话描述 |
| tech_stack | 是 | 技术栈清单 |
| modules | 是 | 模块边界与职责 |
| entry_points | 是 | 主要入口（URL / 命令 / 函数） |
| api_surface | 否 | API 概览（链接到 API_REGISTRY.json） |
| deployment | 否 | 部署方式与环境 |
| dependencies | 否 | 关键外部依赖 |
| planning | 否 | 当前规划与路线图 |
| decisions | 否 | 关键架构决策（链接到 DECISIONS.md） |
| delivery_rules | 否 | 项目特殊交付规则 |
| last_updated | 是 | 最后更新时间 |

## 6. 与记忆蒸馏的接口

记忆蒸馏产物中，带 `project_key` 的条目由 `project_memory_writer.py` 消费，
按 project_key 路由写入项目记忆目录。

project-profile-manager 不直接消费蒸馏产物，
而是通过 `project_memory_writer.py` 间接更新。

## 7. 评分与问责

| 指标 | 计算方式 |
|------|----------|
| 画像覆盖率 | 有画像的活跃项目数 / 总活跃项目数 |
| 画像完整度 | 必填字段非空率 |
| 画像新鲜度 | 最后更新时间在 7 天内的项目数 / 总项目数 |

**问责**：画像覆盖率 < 100% 时，必须强制为无画像项目执行 init。

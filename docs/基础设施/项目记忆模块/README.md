# 项目级记忆模块 — 操作手册

> 版本：v1.0 | 2026-04-22
> 关联文档：[项目交付优先工作流架构设计](../../核心主工作流/项目交付优先工作流/项目交付优先工作流架构设计.md)

---

## 1. 目录结构

每个项目独立记忆模块：

```
.workflow/project-memory/<project_key>/
├── PROJECT_PROFILE.md          # 项目画像（由 project-profile-manager 维护）
├── DECISIONS.md                # 项目级决策记录
├── API_REGISTRY.json           # API 注册表（由 api-registry-manager 维护）
├── SOURCE_REGISTRY.json        # 来源注册表（由 api-registry-manager 维护）
├── DELIVERY_RULES.md           # 项目交付规则
├── CHANGELOG.ndjson            # 变更日志（按行追加的 JSON）
└── MODEL_PERFORMANCE.json      # 模型性能记录（可选）
```

## 2. 记忆注入策略

### 2.1 会话启动时注入

`project_memory_injector.py` 在 coordinator 初始化会话时执行：

```python
# 伪代码示意
def inject_project_memory(project_key: str) -> str:
    profile = load(f".workflow/project-memory/{project_key}/PROJECT_PROFILE.md")
    rules = load(f".workflow/project-memory/{project_key}/DELIVERY_RULES.md")
    decisions_summary = summarize(f".workflow/project-memory/{project_key}/DECISIONS.md")
    
    return f"""
    【项目上下文】
    {profile}
    
    【交付规则】
    {rules}
    
    【关键决策】
    {decisions_summary}
    """
```

### 2.2 注入内容分级

| 优先级 | 文件 | 是否注入 | 说明 |
|--------|------|----------|------|
| P0 | PROJECT_PROFILE.md | 是 | 项目基本信息，必须注入 |
| P0 | DELIVERY_RULES.md | 是 | 交付规则，必须注入 |
| P1 | DECISIONS.md 摘要 | 是 | 最近 5 条关键决策 |
| P2 | API_REGISTRY.json | 否 | 不整份注入，按需查询 |
| P2 | SOURCE_REGISTRY.json | 否 | 不整份注入，API watch 时读取 |
| P3 | CHANGELOG.ndjson | 否 | 不注入，变更追踪用 |

### 2.3 全局记忆隔离

全局 `MEMORY.md` 仅保留：
- 跨项目通用规则
- 宿主环境事实
- 官方 runtime 边界

**铁律**：同一条经验不允许同时出现在全局记忆和项目记忆中。

## 3. 注入器接口规范

### 3.1 输入

```json
{
  "project_key": "xx-trader",
  "session_id": "sess-20260422-001",
  "inject_level": "full|summary|minimal"
}
```

### 3.2 输出

```json
{
  "project_key": "xx-trader",
  "session_id": "sess-20260422-001",
  "injected_files": ["PROJECT_PROFILE.md", "DELIVERY_RULES.md"],
  "injected_tokens": 2048,
  "status": "success",
  "memory_summary": "项目上下文摘要..."
}
```

### 3.3 错误处理

| 错误 | 处理 |
|------|------|
| 项目不存在 | 返回空上下文，coordinator 决定是否创建新项目 |
| 画像文件缺失 | 告警，使用最小注入（仅 project_key） |
| 文件读取失败 | Fail-fast，上报错误 |

## 4. 与记忆蒸馏的集成

### 4.1 蒸馏产物路由

```text
蒸馏产物（带 project_key）
    │
    ▼
project_memory_writer.py
    │
    ├── 类型 = 项目画像更新 → 写入 PROJECT_PROFILE.md
    ├── 类型 = API 变更 → 写入 API_REGISTRY.json
    ├── 类型 = 决策记录 → 写入 DECISIONS.md
    └── 类型 = 交付规则 → 写入 DELIVERY_RULES.md
```

### 4.2 写入规则

- **追加优先**：DECISIONS.md、CHANGELOG.ndjson 只追加不修改历史
- **覆盖优先**：PROJECT_PROFILE.md、API_REGISTRY.json 允许覆盖更新
- **冲突检测**：同一条记录已存在时，检查时间戳，保留最新版本

## 5. 项目切换

当用户从项目 A 切换到项目 B 时：

1. 清除当前会话中的项目 A 上下文
2. 注入项目 B 的上下文
3. 记录切换事件到会话日志

## 6. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-22 | 初始版本，定义项目记忆模块目录结构与注入策略 |

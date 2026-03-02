# 显式调用快速参考卡

> **打印建议**: 将此卡片放在显眼位置，便于随时查阅

---

## 🎯 三种调用格式

### 格式 1 - 技能调用
```markdown
[调用技能: <技能名>] 执行 <任务描述>
```

**常用技能**:
- `pdf` - PDF 处理
- `docx` - Word 文档
- `xlsx` - Excel 表格
- `frontend-design` - 前端设计
- `auto-fix` - 自动修复

---

### 格式 2 - Subagent 调用
```markdown
[调用 Subagent: <Agent 类型>] 执行 <任务描述>
```

**常用 Agent**:
- `smart-flow:python-expert` - Python 专家
- `smart-flow:backend-developer` - 后端开发
- `smart-flow:database-architect` - 数据库架构
- `pr-review-toolkit:code-reviewer` - 代码审查

---

### 格式 3 - 组合调用
```markdown
[调用组合: <组合名>] 执行 <任务描述>
```

**可用组合**:
- `量化交易组合` - 策略分析
- `全栈开发组合` - 完整功能开发
- `代码审查组合` - PR 审查
- `性能分析组合` - 性能优化

---

## 📋 实战示例

### 文档处理
```markdown
[调用技能: pdf] 提取第 1-10 页的所有表格并保存为 CSV
```

### 代码优化
```markdown
[调用 Subagent: smart-flow:python-expert]
优化以下代码的时间复杂度从 O(n²) 降到 O(n)
```

### 复杂任务
```markdown
[调用组合: 全栈开发组合]
开发一个用户认证系统：
- 前端：登录/注册表单（Vue3）
- 后端：JWT 认证 API（Django）
- 数据库：用户表设计
```

---

## ⚠️ 常见错误

| 错误示例 | 正确示例 |
|---------|---------|
| `［调用技能：pdf］` | `[调用技能: pdf]` |
| `[调用技能: excel]` | `[调用技能: xlsx]` |
| `提取 PDF 数据` | `[调用技能: pdf] 提取数据` |
| `[调用技能: pdf] [调用技能: docx]` | 分别调用 |

---

## 🔍 故障排查

**问题**: 调用被忽略
- ✅ 检查是否使用半角符号 `[ ] :`
- ✅ 检查技能名称拼写
- ✅ 查阅 SKILLS_INDEX.md 确认技能存在

**问题**: 调用了错误的技能
- ✅ 确认技能名称正确（如 `xlsx` 不是 `excel`）
- ✅ 使用显式调用避免关键词误匹配

---

## 📚 相关资源

- **完整文档**: [EXPLICIT_CALL_GUIDE.md](docs/EXPLICIT_CALL_GUIDE.md)
- **技能索引**: [SKILLS_INDEX.md](../../SKILLS_INDEX.md)
- **系统配置**: [config/intent_patterns.json](config/intent_patterns.json)

---

**版本**: 1.0.0 | **更新**: 2026-01-25

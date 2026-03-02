# Auto-Fix 命令说明

## 命令调用

在 Claude Code 中使用以下命令：

```
/auto-fix
```

或直接说：

```
使用 auto-fix 技能
```

```
运行自动修复
```

## 参数

### --init-config

初始化配置文件：

```
/auto-fix --init-config
```

## 快速使用

```bash
# 1. 初始化配置（首次使用）
/auto-fix --init-config

# 2. 运行自动修复
/auto-fix
```

## 工作流程

1. **文档检查** - 验证 CLAUDE.md、INDEX.md 等文档
2. **创建分支** - 创建 `auto-fix-{timestamp}` 分支
3. **运行测试** - 调用 deployment-test 技能
4. **分析问题** - 分类为 config/database/api/frontend
5. **三阶段修复** - 配置 → 后端链 → 前端
6. **Git 提交** - 每个类别修复后独立提交
7. **循环验证** - 修复 → 测试 → 验证，直到全部通过
8. **合并主分支** - 成功后自动合并到 main 分支

## 配置文件

首次运行会生成 `auto-fix.config.json` 配置文件：

```json
{
  "version": "1.0",
  "project": {
    "root": "Project",
    "backendPath": "Project/ShengBeiDjango",
    "frontendPath": "Project/ShengBeiVue"
  },
  "test": {
    "configPath": "test.config.json",
    "reportDir": "test_reports"
  },
  "fix": {
    "autoCommit": true,
    "maxIterations": 10,
    "strategy": "balanced"
  },
  "git": {
    "branchPrefix": "auto-fix",
    "autoMerge": true
  }
}
```

根据项目实际情况修改配置后即可使用。

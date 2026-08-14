# 显式调用指南

更新时间：2026-08-14

显式调用用于在任务文本中指定候选 Skill、Agent 或组合。路由器会先解析声明并校验名称；它本身不启动目标。

## 格式

### Skill

```text
[调用技能: <skill>] <任务描述>
```

```text
[调用技能: pdf] 提取第 1 至 5 页的表格
```

目标必须对应 `skills_dir` 中包含 `SKILL.md` 的目录。带命名空间的名称按最后一段校验。

### Agent

```text
[调用 Subagent: <agent>] <任务描述>
```

```text
[调用 Subagent: python-expert] 优化解析函数并补边界测试
```

目标必须在 `config/agent_registry.json` 中声明为可用。该校验只证明配置一致；分发方还需核对目标 Runtime 的实际清单。

### 组合

```text
[调用组合: <combo>] <任务描述>
```

```text
[调用组合: 性能分析组合] 分析批处理耗时并给出可复测的优化方案
```

组合必须出现在 `config/intent_patterns.json` 的 `allowed_combos` 中。

## 优先级与回退

1. 有效显式调用；
2. 按 `priority` 升序排列的关键词规则；
3. 按 `priority` 升序排列的文件类型规则；
4. 默认由主调用方处理。

失效的显式名称不会作为成功路由返回。例如，若任务文本为：

```text
[调用技能: missing-owner] 修复 bug 并补测试
```

路由器会忽略失效 Skill，再根据“修复 bug”匹配到 `debugger`。

## 任务描述

- 声明后的内容会作为 `task` 返回；
- `执行`、`来处理` 是可选连接词；
- 任务为空时保留完整输入，长度受配置中的 `max_length` 限制；
- 一次输入只解析首个匹配的显式调用。

## 常见问题

### 返回默认路由

依次检查：

1. 是否使用半角 `[ ] :`；
2. Skill 目录是否含 `SKILL.md`；
3. Agent 是否登记为 `available=true`；
4. 组合是否在允许列表；
5. 关键词或文件类型是否存在对应规则。

### 路由目标与 Runtime 不一致

`agent_registry.json` 是候选目标配置。调用方应在真正分发前读取 Runtime 的能力清单；目标缺失时回到协调 owner 或主调用方，而不是记录已执行。

## 验证

```powershell
pwsh -NoProfile -Command 'python .\skills\library\intelligent-router\router_engine.py'
pwsh -NoProfile -Command 'python -m pytest -q .\tests\scripts_openclaw_ops\test_intelligent_router.py'
```

相关文件：

- [Skill 说明](../SKILL.md)
- [路由器 README](../README.md)
- [显式调用配置](../config/intent_patterns.json)

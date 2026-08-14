# 显式调用快速参考

## 三种格式

```text
[调用技能: <skill>] <任务>
[调用 Subagent: <agent>] <任务>
[调用组合: <combo>] <任务>
```

示例：

```text
[调用技能: pdf] 提取文档中的表格
[调用 Subagent: python-expert] 优化函数并补性能测试
[调用组合: 代码审查组合] 检查变更的质量、安全性和回归风险
```

## 校验与回退

- Skill 名称必须对应 `skills_dir/<skill>/SKILL.md`。
- Agent 名称必须在 `agent_registry.json` 中声明为可用。
- 组合名称必须在 `intent_patterns.json` 的 `allowed_combos` 中。
- 名称失效时继续尝试关键词和文件类型规则，最终回退到主调用方。
- 路由结果只代表候选目标；实际分发前还需检查目标 Runtime。

## 排查

1. 使用半角 `[ ] :`。
2. 核对名称拼写以及目标是否登记。
3. 运行 `router_engine.py` 查看基础示例。
4. 运行路由测试，确认优先级、扩展名和回退行为。

## 相关资源

- [完整指南](docs/EXPLICIT_CALL_GUIDE.md)
- [Skill 索引](../../README.md)
- [显式调用配置](config/intent_patterns.json)

版本：1.0.1；更新：2026-08-14

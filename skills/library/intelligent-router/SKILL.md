---
name: "intelligent-router"
description: "根据显式调用、关键词和文件上下文生成可校验的通用任务路由决策"
description_zh: "通用任务路由决策器；只选择目标，不执行分发"
version: "1.0.1"
triggers:
  keywords:
    - "智能路由"
    - "任务路由"
    - "subagent"
    - "自动路由"
  auto_trigger: true
  confidence_threshold: 0.7
---

# Intelligent Router

## 适用范围

在调用方已经掌握 Skill 目录、目标 Runtime Agent 目录和任务上下文时，用本 Skill 生成一个结构化路由决策。Agent 启动、并行编排、结果合并和业务验收由调用方负责。

## 路由协议

输入：

- `user_input`：任务文本；
- `file_context`：可选文件名或扩展名；
- `skills_dir`：包含各 Skill 目录的路径；
- `config_dir`：本 Skill 的 `config/` 路径。
- `agents_dir`：目标 Runtime 的实际 Agent 能力目录；也可使用 `HARDFLOW_AGENTS_DIR` 注入。

输出：

- `method`：命中层级；
- `target`：已通过配置校验的候选目标；
- `task`：交给后续调用方的任务文本；
- `confidence`：规则置信度。

## 执行步骤

1. 先检查三种显式格式：
   - `[调用技能: <skill>] <task>`
   - `[调用 Subagent: <agent>] <task>`
   - `[调用组合: <combo>] <task>`
2. 校验显式目标：Skill 必须有 `SKILL.md`，Agent 必须同时登记并从 Runtime 目录发现，组合的全部成员必须可用。
3. 显式目标失效时继续关键词匹配，不输出虚假成功。
4. 关键词规则按 `priority` 升序匹配；同优先级保持 JSON 中的顺序。
5. 未命中关键词时匹配完整文件名、带点扩展名和不带点扩展名。
6. 全部未命中时返回默认决策，由主调用方处理。

## 约束

- 默认路由只表达通用任务类型，不固定仓库、框架、主机或部署命令。
- `agents_dir` 提供运行时能力真值，注册表只保存元数据；两者不一致时目标回退。
- 本 Skill 不自行提交代码、不执行部署，也不把路由命中当作任务完成。
- 修改配置后必须运行路由回归，并检查所有规则目标均可解析。

## 验证命令

```powershell
pwsh -NoProfile -Command 'python .\skills\library\intelligent-router\router_engine.py'
pwsh -NoProfile -Command 'python -m pytest -q .\tests\scripts_openclaw_ops\test_intelligent_router.py'
```

更多示例见 [README](README.md) 与 [显式调用指南](docs/EXPLICIT_CALL_GUIDE.md)。

# Intelligent Router

`intelligent-router` 根据显式调用、任务关键词和文件上下文生成结构化路由决策。它只负责**选择目标**，不负责启动 Agent、并行执行任务或证明目标 Runtime 中的 Agent 已安装。

## 输入与输出

```python
from router_engine import IntelligentRouter

router = IntelligentRouter(
    skills_dir="<skills-dir>",
    config_dir="<config-dir>",
)
decision = router.route("请修复 bug 并补回归测试", file_context="src/service.py")
```

返回值包含：

- `method`：`explicit`、`keyword`、`file_type` 或 `default`；
- `target`：已通过本地配置校验的 Skill 或 Agent 名称；
- `task`：原始或显式调用中提取的任务；
- `confidence`：当前规则给出的置信度。

未命中规则或目标未登记时，返回 `method=default`、`target=None`，由调用方继续处理。

## 决策顺序

1. 解析 `[调用技能: ...]`、`[调用 Subagent: ...]` 和 `[调用组合: ...]`；
2. 按 `priority` 从小到大匹配关键词，同优先级保持配置顺序；
3. 按相同规则匹配文件名或扩展名；
4. 回退到默认处理。

显式 Skill 会对 `skills_dir` 下真实存在且包含 `SKILL.md` 的目录进行校验。显式 Agent 会对 `agent_registry.json` 中 `available=true` 的声明进行校验。组合名称必须位于 `intent_patterns.json` 的允许列表中。

> Agent 注册表是路由配置，不等同于 Runtime 安装证据。调用方在分发前仍需核对目标 Runtime 的实际能力清单。

## 通用路由示例

| 输入或上下文 | 目标 | 原因 |
| --- | --- | --- |
| `请修复 bug 并补测试` | `debugger` | 使用受控的复现、修复与验证流程 |
| `新增功能并补验收` | `coordinator` | 由协调 owner 按目标仓库契约选择实现角色 |
| `部署项目并保留回滚证据` | `deployment-engineer` | 部署方式由项目命令注入 |
| `src/service.py` | `python-expert` | Python 文件类型规则 |
| `src/model.ts` | `typescript-expert` | TypeScript 文件类型规则 |
| `Dockerfile` | `deployment-engineer` | 完整文件名规则 |

默认规则不绑定仓库名、主机路径、账号、固定技术栈或部署命令。

## 配置文件

| 文件 | 作用 |
| --- | --- |
| `config/intent_patterns.json` | 显式调用语法、校验开关和组合允许列表 |
| `config/keyword_routes.json` | 关键词到目标的有序规则 |
| `config/file_type_routes.json` | 文件名或扩展名到目标的有序规则 |
| `config/agent_registry.json` | 可供路由器校验的 Agent 声明 |

新增或修改规则时，应同时确认：

1. 目标 Skill 真实存在，或 Agent 已登记且在目标 Runtime 可用；
2. 规则使用通用任务语义，不嵌入历史项目配置；
3. 更高优先级规则不会被更早的低优先级规则遮蔽；
4. `tests/scripts_openclaw_ops/test_intelligent_router.py` 覆盖新增分支。

## 验证

```powershell
pwsh -NoProfile -Command 'python .\skills\library\intelligent-router\router_engine.py'
pwsh -NoProfile -Command 'python -m pytest -q .\tests\scripts_openclaw_ops\test_intelligent_router.py'
```

## 相关文档

- [Skill 说明](SKILL.md)
- [显式调用快速参考](QUICK_REFERENCE.md)
- [显式调用指南](docs/EXPLICIT_CALL_GUIDE.md)

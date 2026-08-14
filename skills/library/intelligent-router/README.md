# Intelligent Router

`intelligent-router` 根据显式调用、任务关键词和文件上下文生成结构化路由决策。它只负责**选择目标**，不负责启动 Agent、并行执行任务或证明目标 Runtime 中的 Agent 已安装。

## 输入与输出

```python
from router_engine import IntelligentRouter

router = IntelligentRouter(
    skills_dir="<skills-dir>",
    config_dir="<config-dir>",
    agents_dir="<runtime-agents-dir>",
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

显式 Skill 会对 `skills_dir` 下真实存在且包含 `SKILL.md` 的目录进行校验。显式 Agent 必须同时存在于 `agents_dir` 的实际能力目录与 `agent_registry.json` 元数据中。组合的全部成员也必须已被 Runtime 发现。

> `agents_dir` 是本次路由的能力真值；注册表只提供受控元数据。路由结果仍不代表 Agent 已执行任务。

## 通用路由示例

| 输入或上下文 | 目标 | 原因 |
| --- | --- | --- |
| `请修复 bug 并补测试` | `project-agent` | 收集复现证据并分派实现与验证 owner |
| `新增功能并补验收` | `project-agent` | 按目标仓库契约组织交付 |
| `部署项目并保留回滚证据` | `deployer` | 部署方式由项目命令注入 |
| `src/service.py` | `backend-dev` | 通用源码规则 |
| `src/model.ts` | `frontend-dev` | 前端源码规则 |
| `Dockerfile` | `deployer` | 完整文件名规则 |

默认规则不绑定仓库名、主机路径、账号、固定技术栈或部署命令。

## 配置文件

| 文件 | 作用 |
| --- | --- |
| `config/intent_patterns.json` | 显式调用语法、校验开关和组合允许列表 |
| `config/keyword_routes.json` | 关键词到目标的有序规则 |
| `config/file_type_routes.json` | 文件名或扩展名到目标的有序规则 |
| `config/agent_registry.json` | 与能力目录对齐的 Agent 元数据 |

新增或修改规则时，应同时确认：

1. 目标 Skill 真实存在，或 Agent 已登记且能从目标 Runtime 目录发现；
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

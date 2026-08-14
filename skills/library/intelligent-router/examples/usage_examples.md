# 路由使用示例

## 初始化

```python
from router_engine import IntelligentRouter

router = IntelligentRouter(
    skills_dir="<skills-dir>",
    config_dir="<config-dir>",
    agents_dir="<runtime-agents-dir>",
)
```

`agents_dir` 必须指向目标 Runtime 的实际 Agent 能力目录。目录缺失或目标未发现时，Agent 路由回退到主调用方。

## 关键词

```python
router.route("新增功能并补回归")
# target: project-agent

router.route("请审查代码和安全边界")
# target: reviewer

router.route("部署项目并保留回滚证据")
# target: deployer
```

## 文件上下文

```python
router.route("检查实现", file_context="src/service.py")
# target: backend-dev

router.route("检查交互", file_context="src/page.tsx")
# target: frontend-dev

router.route("检查构建", file_context="Dockerfile")
# target: deployer
```

## 显式调用

```text
[调用技能: pdf] 提取文档表格
[调用 Subagent: backend-dev] 优化解析函数并补测试
[调用组合: 代码审查组合] 审查补丁和回归证据
```

有效组合会同时返回 `target` 和实际 `targets` 列表。组合成员全部来自已发现的 Runtime Agent；任一成员缺失时该组合失效并继续执行关键词回退。

## 缺失目标

```python
router.route("[调用 Subagent: missing-owner] 执行任务")
# method: default
# target: None
```

路由决策只选择候选 owner，真正执行、验收和结果合并由调用方负责。

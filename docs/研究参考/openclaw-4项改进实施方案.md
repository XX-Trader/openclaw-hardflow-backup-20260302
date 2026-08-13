# 通用工作流改进参考

## 四项原则

1. **上下文完整**：需求、约束、验收和影响范围先结构化。
2. **失败可恢复**：阶段状态、证据和重试边界可回读。
3. **变更可审查**：实现、测试和审查由明确 owner 承担。
4. **运行可验证**：dry-run、实际样本、远端回读和回滚形成闭环。

落地入口为 `skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`，具体项目差异通过项目契约注入。

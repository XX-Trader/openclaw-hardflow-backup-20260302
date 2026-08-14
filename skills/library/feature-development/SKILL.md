---
name: feature-development
displayName: "通用功能交付"
version: "2.0.0"
description: "兼容入口：按目标仓库契约完成需求、方案、实现、验证和审查"
description_zh: "通用功能交付兼容入口"
updated_at: "2026-08-14"
triggers:
  keywords:
    - "新增功能"
    - "实现需求"
    - "功能开发"
---

# 通用功能交付

本 Skill 保留 `feature-development` 名称以兼容现有 Agent 与控制面绑定，阶段编排统一委托给 [project-delivery-pipeline](../project-delivery-pipeline/SKILL.md)。

## 必备产物

1. 需求包：目标、范围、非目标、约束和验收条件。
2. 方案包：受影响组件、接口或数据契约、失败模式和回滚路径。
3. 隔离补丁：只修改需求允许的文件，并记录补丁摘要。
4. 验证报告：项目自己的格式、静态检查、单元测试、集成测试或端到端命令。
5. 独立审查：代码质量与需求符合性分别给出结论。
6. 写回与发布：仅在前述门禁通过后进入。

## 通用化约束

- 技术栈、目录、命令、端口和外部服务均从目标仓库发现或显式注入。
- 示例只使用 `TARGET_PROJECT`、`APP_MODULE`、`API_PATH` 等类型化占位符。
- 简单任务可以减少文档篇幅，但保留需求、验证和回滚三类证据。

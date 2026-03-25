# 2026-03-24 Requirement Package Gate Standard

## 摘要

本文件补充定义 `requirement_package_gate` 与 `requirement_package_contract` 的最小运行时标准。
它用于复杂人类工作流任务在正式拆解、分派和执行前的需求包硬门禁。

## 适用范围

- `request_source=human`
- `task_type=workflow`

## 触发规则

当前仅在以下两类场景自动触发：

1. 显式声明 `context_payload.requirement_package_required=true`
2. 命中强项目型需求措辞，例如：
   - `project requirement`
   - `product requirement`
   - `requirement package`
   - `requirements document`
   - `PRD`
   - `需求文档`
   - `需求包`

以下弱词不会单独触发门禁：

- `workflow`
- `readme`
- `module`
- `architecture`

## 最小必填字段

- `goal`
- `success_criteria`
- `scope.in_scope`
- `scope.out_of_scope`

## requirement_package_gate

所属对象：

- `selection_inputs`
- `route_task(...)` 返回值
- `build_task_preflight(...)` 返回值

固定字段：

- `required`
- `package_ready`
- `triggered_by`
- `required_fields`
- `recommended_fields`
- `missing_fields`
- `missing_recommended_fields`
- `clarification_reason`

## requirement_package_contract

所属对象：

- `context_payload`

固定字段：

- `required`
- `required_fields`
- `recommended_fields`
- `missing_fields`
- `missing_recommended_fields`
- `triggered_by`

## 失败行为

当需求包不完整时：

- 任务自动 reroute 到 `clarification_required`
- 默认改派给 `project-agent`
- `clarification_reason` 必须包含 `requirement_package_incomplete`

## 设计边界

- 这是一层最小硬门禁，不负责自动生成需求文档
- 这层门禁优先保证“减少误伤”，而不是“最大覆盖所有复杂任务”
- 后续如需扩大适用范围，应先更新标准文档，再修改运行时代码

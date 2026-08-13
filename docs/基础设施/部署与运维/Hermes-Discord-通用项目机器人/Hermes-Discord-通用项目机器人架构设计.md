# Hermes Discord 通用项目机器人架构设计

## 组件

```text
Discord connector
  -> Profile router
  -> project_pipeline_entry.py
  -> pipeline_runner.py
  -> live_runtime_bridge.py
  -> target project commands
  -> evidence and status reply
```

## 配置层

1. 仓库层：保存通用 Profile 模板、路由契约和测试。
2. Runtime 层：保存模型、连接器和运行目录。
3. 本地 overlay：保存账号、频道、令牌和机器路径。
4. 项目层：声明验证、部署、烟测与回滚命令。

## 隔离原则

- Profile 之间不共享会话状态。
- 连接器消息先完成路由选择，再进入具体工作流。
- 实现阶段使用隔离工作区，主工作树只接收已验证补丁。
- 运行证据按 run_id 保存，不写入 Profile 模板。
- 并发上限由 Runtime 配置，模板不假定机器资源。

## 故障处理

- 路由缺失：返回选择卡。
- Agent 失败：记录退出码和摘要，按 `next_action` 回流。
- 验证失败：保留已完成阶段，只重跑实现与验证链。
- 部署失败：执行项目声明的回滚并保留烟测证据。
- 发布失败：修复暂存范围或远端状态后重跑发布阶段。

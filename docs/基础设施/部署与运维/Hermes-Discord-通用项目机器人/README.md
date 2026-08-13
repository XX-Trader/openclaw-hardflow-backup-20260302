# Hermes Discord 通用项目机器人

该目录描述一个独立 Hermes Profile 如何接入 Discord，并将软件项目需求路由到通用交付流水线。所有账号、频道、目录和模型配置均由部署环境注入。

## 边界

- Profile 名称：`deliveryagent` 或自定义 `TARGET_PROFILE`。
- 项目目录：`${PROJECT_PIPELINE_PROJECT_DIR}`。
- Runtime Home：`${HARDFLOW_RUNTIME_HOME}`。
- Discord 频道与 mention 规则：由未跟踪的本地 overlay 提供。
- 项目部署与烟测：由命令参数或环境变量提供。

## 路由

- `direct_run`：处理只读查询或已定义的轻量操作。
- `requirement_discussion`：只澄清需求和验收标准。
- `specified_agent`：分配给明确 owner。
- `coding_workflow`：进入完整项目交付流水线。
- `todo_auto_candidate`：经确认后进入受控待办执行。

## 验收

1. 只有配置的频道与 mention 规则触发。
2. 无路由选择时只返回选择卡，不启动编码链路。
3. 运行产物记录来源、Profile、run_id、阶段和下一动作。
4. 任何机器账号、频道 ID、令牌和绝对路径均不进入仓库。

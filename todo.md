# TODO

更新时间：2026-08-14

## P1 通用化收口

- [ ] 清理或参数化 `auto-fix`、`db-deploy`、`deployment-test`、`feature-development` 中的历史项目 fixture。Owner：`coordinator`；依赖：确定逐个迁移或整体归档；验收：当前审计发现的 24 个文件、98 处历史名称归零，修复器不再生成待补业务逻辑的代码，也不默认自动合并。
- [ ] 将 `intelligent-router` 的 54 个静态 Agent 声明与目标 Runtime 的真实能力清单对齐。Owner：`coordinator`；依赖：定义 Runtime 能力发现接口；验收：缺失目标回退，已安装目标可分发，注册表不再作为运行成功证据。

## P1 运行态复验

- [ ] 在空白 Python fixture 仓库执行完整 live 流水线。Owner：`project-agent`；依赖：准备可丢弃 fixture 和远端；验收：隔离补丁、验证、审查、写回与可选发布均有终态证据。
- [ ] 在前端 fixture 仓库执行同样流程。Owner：`project-agent`；依赖：项目自定义安装、构建和测试命令；验收：owner 推断与注入命令真实生效。
- [ ] 在第二种操作系统或容器中复验 Runtime 安装与回滚。Owner：`ops-agent`；依赖：可用隔离环境；验收：首次安装、重复安装、升级和回滚均可复测。

## P2 治理

- [ ] 拆分全套测试的快速门禁与长时集成门禁。Owner：`tester`；依赖：记录多次耗时分布；验收：快速门禁覆盖策略、入口和配置解析，长时门禁单独报告且不重复执行。
- [ ] 若仓库进入公开分发，补齐许可证、贡献说明、安全报告入口和持续集成。Owner：`coordinator`；依赖：先确认发布方式与许可证选择；验收：治理文件与自动门禁均可由新环境复现。

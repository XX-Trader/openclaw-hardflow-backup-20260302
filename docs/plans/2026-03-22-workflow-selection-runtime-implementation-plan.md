# 工作流选择与 Runtime 实施计划（已收口）

原计划中的旧基准编排器和 profile 安装器已经退役。当前实现由以下 owner 组成：

1. `project_pipeline_entry.py` 解析通用项目输入。
2. `pipeline_runner.py` 负责阶段选择、失败回流和交付证据。
3. `runtime_installer.py` 通过 `setup.py` 安装跨 Runtime 文件与 Cron 模板。
4. `live_runtime_bridge.py` 连接项目验证命令与运行证据。
5. `workflow_selector.py` 与控制面策略负责通用工作流路由。

新变更以 `requirements.md` 为基线，并在 `CHANGELOG.md` 记录兼容性和回滚方式。

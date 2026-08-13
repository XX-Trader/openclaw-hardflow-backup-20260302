# 架构升级路线图（已收口）

本历史路线已由当前通用架构承接，现行事实源如下：

- 需求：`requirements.md`
- 状态机：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`
- Runtime 安装：`setup.py`
- Profile：`config/runtime-profiles/`
- 调度注册表：`skills/library/control-plane-ops/scripts/export_schedule_registry.py`
- 健康检查：`skills/library/log-monitor/scripts/runtime_profile_healthcheck.py`

后续架构任务统一进入 `todo.md`，验收至少包含 owner 测试、dry-run、实际样本、版本记录和回滚点。

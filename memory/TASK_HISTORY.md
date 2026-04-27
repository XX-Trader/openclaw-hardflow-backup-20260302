# TASK_HISTORY

## 2026-04-27 - 2 天仓库精简巡检与 Git 发布门禁

类型：task
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、`source_registry_watcher.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`、`pipeline_runner.py`
事实：新增 `repo_hygiene_reviewer.py` 只读仓库精简巡检，默认每 2 天由 `optimization-agent` 执行；`source_registry_watcher` 频率也调整为每 2 天并修复 `--base-path` 生效；项目交付流水线新增 `git_publish` 可选阶段，默认 live entry 会注入该命令，提交说明必须中文且脱敏，失败回流 `fix_git_publish`；发布输入会优先采用 `memory_writeback` 隔离工作区 patch，避免漏掉文档/记忆写回变更，并禁止夹带 `command_cwd` 未验收脏改动。
证据：相关测试覆盖 pipeline git_publish 成功/失败、写回后 patch 进入发布工作区、未验收脏改动不进入发布工作区、entry 默认注入/可跳过、live bridge 中文 commit/push 与 commit message 脱敏、repo hygiene 只读扫描、source watcher base path、runtime installer 安装新脚本。
最后验证：2026-04-27 相关单元测试 62 项 OK
复用建议：仓库治理候选不直接删除；通过人工确认后再进入交付流水线。Git 发布不替代部署，deployment 仍只做内控服务 smoke；真正生产部署需按对应项目 RUNBOOK 执行。

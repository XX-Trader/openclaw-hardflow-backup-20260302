# Hermes Discord 通用项目机器人实施规划

## 1. Profile

- 从 `config/runtime-profiles/` 选择模板。
- 通过环境变量设置 Runtime Home、目标项目和模型。
- 将账号、频道和令牌放入未跟踪 overlay。

## 2. 路由

- 验证 `direct_run`、`requirement_discussion`、`specified_agent`、`coding_workflow` 和 `todo_auto_candidate`。
- 无人工选择时只输出路由卡。
- 所有编码任务生成唯一 run_id。

## 3. 证据

- 保存阶段命令、退出码、标准输出和错误摘要。
- 群回传只包含脱敏摘要与下一动作。
- 原始运行产物留在 Runtime 工作目录。

## 4. 验证

```powershell
pwsh -NoProfile -Command 'python -m pytest -q tests/scripts_openclaw_ops/test_runtime_profile_templates.py tests/scripts_openclaw_ops/test_project_pipeline_entry.py tests/scripts_openclaw_ops/test_live_runtime_bridge.py'
```

## 5. 发布

- 检查暂存区范围和敏感值。
- 使用中文提交说明。
- 推送后回读远端 SHA，并将结果写入交付摘要。

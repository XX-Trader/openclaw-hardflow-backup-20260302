# Agent / Skill / Hook 治理实施验收报告

## 时间

- 验收时间：2026-03-14 晚

## 结论

- 计划内剩余缺口已收口完成。
- 当前 runtime 绑定巡检结果：
  - `agent_count=13`
  - `declared_skill_count=35`
  - `missing_skill_count=0`
  - `hook_count=8`
  - `cron_binding_count=17`

## 已完成项

- `inspect_runtime_bindings.py` 已稳定输出 agent / skill / hook / cron 绑定报告
- `agent_capability_manifest.json`、`hook_event_matrix.json`、`cron_agent_capability_matrix.json` 已生成
- `agent_index.md` 已标注 generated / do not edit manually
- `main` 的缺失 skill 声明已移除
- 零 skill agent 已显式标注 `capability_mode=role_only`
- `frontend-design -> frontend-design-ultimate` 替换映射已进入 manifest
- 任务层 `required_capabilities / required_skills / allowed_agents` 已落地
- preflight 已支持 planner `allowAgents` 自动校验
- `task-capability-coverage` 覆盖率统计命令已落地
- follow-up task 不再被 runtime runner 提前回写成 `passed`

## 验收命令

```bash
python -m unittest \
  tests.scripts_openclaw_ops.test_inspect_runtime_bindings \
  tests.scripts_openclaw_ops.test_generate_runtime_binding_manifests \
  tests.scripts_openclaw_ops.test_runtime_binding_repo_contract \
  tests.scripts_openclaw_ops.test_ensure_runtime_skills \
  tests.scripts_openclaw_ops.test_task_center_capability_fields \
  tests.scripts_openclaw_ops.test_policy_task_capability_args \
  tests.scripts_openclaw_ops.test_task_executor_preflight \
  tests.scripts_openclaw_ops.test_task_executor_output_contract \
  tests.scripts_openclaw_ops.test_direct_task_constraint_backfill \
  tests.scripts_openclaw_ops.test_follow_up_tasks_remain_pending \
  tests.scripts_openclaw_ops.test_workflow_views
```

```bash
python scripts/openclaw-ops/inspect_runtime_bindings.py --emit-json
python scripts/openclaw-ops/generate_runtime_binding_manifests.py
python scripts/openclaw-ops/policy/policy_enforcer.py task-capability-coverage
python scripts/openclaw-ops/ensure_runtime_skills.py --dry-run --emit-json
python scripts/openclaw-ops/bootstrap_runtime_agents.py --dry-run
openclaw hooks list --json
openclaw hooks check --json
openclaw agents list
```

## 结果摘要

- 单测：通过
- `inspect_runtime_bindings.py --emit-json`：通过，`missing_skills=[]`
- `generate_runtime_binding_manifests.py`：通过，生成产物与仓库一致
- `policy_enforcer.py task-capability-coverage`：通过，可输出任务升级覆盖率
- `ensure_runtime_skills.py --dry-run --emit-json`：通过
- `bootstrap_runtime_agents.py --dry-run`：通过
- `openclaw hooks list --json`：通过，包含 builtin + custom hooks
- `openclaw hooks check --json`：通过
- `openclaw agents list`：通过，13 个 agent 可见

## 备注

- 当前工作区仍保留用户自己的 `scripts/openclaw-ops/README.md` 未提交改动，本轮未修改。

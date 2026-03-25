# OpenClaw 基建设施模板文档

本文档给出后续统一遵循的标准模板。模板里的字段分为两类：

- `必填`: 新实现必须提供
- `选填`: 当前阶段允许为空，但应保留字段位

## 1. 人类需求输入模板 `HumanRequestEnvelope`

适用场景：

- 用户提需求
- 外部系统创建任务
- 后续 workflow selector 的标准入口

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "request_id": "request-20260323120000-001",
  "source": "human",
  "sender_identity": "user/direct",
  "goal": "修复策略回测页面的时间区间错误",
  "constraints": [
    "不能引入新依赖",
    "必须兼容现有 API"
  ],
  "success_criteria": [
    "回测页面时间区间正确展示",
    "现有测试全部通过"
  ],
  "scope": {
    "in_scope": [
      "前端显示修复",
      "相关接口验证"
    ],
    "out_of_scope": [
      "重做整个回测模块"
    ]
  },
  "context_payload": {
    "project_id": "openclaw",
    "repo_path": "D:/学习资料/量化交易/openclaw-hardflow-backup-20260302"
  }
}
```

## 2. 工作流任务输入模板 `TaskEnvelope`

适用场景：

- selector 完成后写入 task-center
- workflow stage 派发到执行器

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "attempt_id": "attempt-001",
  "task_id": "task-20260323120500-a1b2c3",
  "task_type": "workflow",
  "assignee": "backend-dev",
  "planner_id": "coordinator",
  "workflow_profile_id": "coding-default",
  "workflow_channel": "stable",
  "stage_id": "implement",
  "selection_reason": "default_coding_route",
  "selection_inputs": {
    "selector_state": "matched",
    "matched_keyword_groups": [
      "coding"
    ],
    "matched_keywords": [
      "修复",
      "bug"
    ]
  },
  "reason": "修复时间区间错误",
  "requirement": "修复回测页面时间区间显示异常",
  "acceptance": "页面展示正确，相关验证通过",
  "observable_outputs": [
    "diff summary",
    "test evidence"
  ],
  "acceptance_thresholds": {
    "quality_score_min": 80
  },
  "required_capabilities": [
    "task_execution"
  ],
  "required_skills": [
    "feature-development"
  ],
  "allowed_agents": [
    "backend-dev"
  ],
  "required_runtime": [
    "task-center"
  ],
  "tool_requirements": [
    "filesystem",
    "shell"
  ],
  "context_payload": {
    "ticket_id": "BT-1001",
    "stage_required_fields": []
  }
}
```

## 3. Agent 执行输入模板 `AgentExecutionInput`

适用场景：

- `task_executor_runner.py` 对执行代理下发标准输入

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "attempt_id": "attempt-001",
  "task_id": "task-20260323120500-a1b2c3",
  "workflow": {
    "profile_id": "coding-default",
    "channel": "stable",
    "stage_id": "implement"
  },
  "task": {
    "reason": "修复时间区间错误",
    "requirement": "修复回测页面时间区间显示异常",
    "acceptance": "页面展示正确，相关验证通过"
  },
  "contracts": {
    "stage_output_contract": {
      "deliverables": [
        "code_changes",
        "verification_result"
      ]
    },
    "stage_verification_contract": {
      "checks": [
        "tests_or_validation_recorded"
      ]
    }
  },
  "capability_binding": {
    "required_capabilities": [
      "task_execution"
    ],
    "required_skills": [
      "feature-development"
    ],
    "required_runtime": [
      "task-center"
    ],
    "tool_requirements": [
      "filesystem",
      "shell"
    ]
  },
  "stage_hints": {
    "stage_context_gate": {},
    "stage_parallel_execution": {},
    "stage_simplification_hint": {},
    "stage_optimization_hints": {}
  }
}
```

## 4. Agent 间通信模板 `AgentMessageEnvelope`

适用场景：

- `log-communication`
- dispatcher -> reviewer
- reviewer -> applier
- benchmark / summary / announce 中间转交

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "correlation_id": "corr-20260323121000-001",
  "task_id": "task-20260323120500-a1b2c3",
  "from_module": "coordinator/workflow-selector",
  "to_module": "backend-dev/task-executor",
  "protocol": "task-center",
  "message_type": "task_dispatch",
  "status": "sent",
  "latency_ms": 42,
  "payload_ref": "task_center.tasks.task-20260323120500-a1b2c3",
  "details": {
    "workflow_profile_id": "coding-default",
    "stage_id": "implement"
  }
}
```

## 5. Agent 结果输出模板 `AgentResultEnvelope`

适用场景：

- `report-agent-result`
- 执行代理回传 planner / task-center

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "task_id": "task-20260323120500-a1b2c3",
  "agent_id": "backend-dev",
  "planner_id": "coordinator",
  "status": "passed",
  "solved": true,
  "resolution_summary": "已修复时间区间显示逻辑，并补充验证",
  "resolution_steps": [
    "定位时间区间映射错误",
    "修复转换逻辑",
    "补跑验证"
  ],
  "resolved_issues": [
    "time_range_display_bug"
  ],
  "failed_items": [],
  "failure_count": 0,
  "quality_score": 90,
  "quality_grade": "a",
  "need_clarification": false,
  "clarification_reason": "",
  "context_fields_missing": [],
  "duration_ms": 9123,
  "model_id": "gpt-5",
  "input_tokens": 1234,
  "output_tokens": 456,
  "total_tokens": 1690,
  "cost_estimate": 0.0231,
  "details": {
    "stage_contract": {
      "contract_passed": true,
      "evidence_count": 2,
      "missing_deliverables": [],
      "failed_checks": []
    }
  }
}
```

## 6. 标准输出包模板 `StandardOutputPacket`

适用场景：

- `task_outputs.payload_json`
- 公告链、summary、dashboard、外部通知消费

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "task_id": "task-20260323120500-a1b2c3",
  "workflow": {
    "profile_id": "coding-default",
    "channel": "stable",
    "stage_id": "implement",
    "score_gate": "backend"
  },
  "outcome": {
    "report_status": "passed",
    "task_status_before": "queued",
    "task_status_after": "passed",
    "task_action_after": "close",
    "solved": true,
    "failure_count": 0,
    "failed_items": [],
    "quality_score": 90,
    "quality_grade": "a"
  },
  "human_gate": {
    "need_human_confirm": false,
    "human_confirmed": false,
    "needs_clarification": false,
    "clarification_reason": "",
    "requires_human_assistance": false,
    "notify_chat": false
  },
  "telemetry": {
    "duration_ms": 9123,
    "model_id": "gpt-5",
    "input_tokens": 1234,
    "output_tokens": 456,
    "total_tokens": 1690,
    "cost_estimate": 0.0231
  },
  "contracts": {
    "stage_output_contract": {},
    "stage_verification_contract": {},
    "stage_contract": {},
    "stage_contract_gate": {}
  },
  "delivery": {
    "channel": "none",
    "status": "suppressed",
    "human_summary": "已修复并验证",
    "machine_summary": {
      "report_id": "report-001",
      "report_ts": "2026-03-23T12:10:00+08:00"
    }
  }
}
```

## 7. 对人通信模板 `HumanOutputCardEnvelope`

适用场景：

- 聊天公告
- dashboard 卡片
- 日报、summary、控制面公告

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "kind": "task_control_plane",
  "audience": "human",
  "severity": "info",
  "title": "coding-default / implement 已完成",
  "summary": "时间区间显示问题已修复，验证通过",
  "facts": {
    "task_id": "task-20260323120500-a1b2c3",
    "workflow_profile_id": "coding-default",
    "stage_id": "implement",
    "quality_score": 90,
    "incident_count": 0
  },
  "actions": [
    "查看 task_report",
    "查看 benchmark 对比"
  ],
  "human_text": "任务已完成：coding-default / implement，质量分 90，无 open incident。"
}
```

## 8. Incident 模板 `IncidentEnvelope`

适用场景：

- `task_incidents`
- 人工介入
- stage contract 失败
- 升级 veto

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323120000-001",
  "task_id": "task-20260323120500-a1b2c3",
  "incident_type": "stage_contract_failed",
  "severity": "warning",
  "status": "open",
  "reason": "retry",
  "summary": "阶段交付合同未满足，需要重试",
  "owner": "coordinator",
  "details": {
    "stage_id": "implement",
    "missing_deliverables": [
      "verification_result"
    ],
    "failed_checks": [
      "tests_or_validation_recorded"
    ]
  }
}
```

## 9. Benchmark 结果模板 `BenchmarkRunEnvelope`

适用场景：

- `benchmark_runs`
- promotion / rollback 分析

```json
{
  "schema_version": "2026-03-23",
  "trace_id": "trace-20260323130000-001",
  "benchmark_run_id": "benchmark-run-20260323130000-001",
  "benchmark_suite_id": "coding-default-core",
  "workflow_profile_id": "coding-default",
  "workflow_channel": "candidate",
  "target_kind": "workflow",
  "target_id": "coding-default",
  "baseline_run_ids": [
    "baseline-001",
    "baseline-002"
  ],
  "candidate_run_ids": [
    "candidate-001",
    "candidate-002"
  ],
  "decision": {
    "promote_to_new_baseline": false,
    "veto_reasons": [
      "critical_incident_count_not_improved"
    ]
  },
  "artifacts": {
    "summary_file": "ops/benchmark-sweeps/sweeps/latest-summary.json",
    "scorecard_file": "ops/benchmark-sweeps/sweeps/latest-scorecard.json"
  }
}
```

## 10. 工作流阶段模板 `WorkflowStageManifest`

适用场景：

- `workflow-profile-registry.json`
- 所有 workflow/stage 的声明式配置

```json
{
  "stage_id": "implement",
  "display_name": "实现与验证",
  "score_gate": "backend",
  "min_evidence_count": 3,
  "output_contract": {
    "deliverables": [
      "code_changes",
      "verification_result"
    ],
    "observable_outputs": [
      "diff summary",
      "test evidence"
    ]
  },
  "verification_contract": {
    "checks": [
      "tests_or_validation_recorded"
    ]
  },
  "required_capabilities": [
    "task_execution",
    "routing"
  ],
  "required_skills": [],
  "clarification_required_fields": [],
  "parallel_execution": {},
  "simplification_hint": {},
  "optimization_hints": {}
}
```

## 11. 我建议后续再补齐的统一模板

为了支撑真正的“全自动删环节 / 负载均衡 / 并行自适应”，后续还应再正式化这两个对象：

1. `ExecutionEnvelope`
2. `TraceContract`

原因很简单：

- 现在已经有很多结构化字段
- 但还没有一份真正全链路强制的执行信封
- 这会影响后面自动优化的稳定性和可回放性

## 12. 关联文档

- [OpenClaw 基建设施输入输出与通信标准](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/docs/adr/2026-03-23-openclaw-foundation-contract-standard.md)
- [FIELD_DICTIONARY.md](/d:/学习资料/量化交易/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/policy/FIELD_DICTIONARY.md)

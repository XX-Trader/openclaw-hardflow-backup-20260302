import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        sys.path.pop(0)


class WorkflowViewsTests(unittest.TestCase):
    def test_control_plane_summary_event_summarizes_incidents_and_vetoes(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "generated_at": "2026-03-22T15:00:00+00:00",
            "lookback_hours": 24,
            "scanned_task_count": 3,
            "open_incident_count": 2,
            "critical_open_incident_count": 1,
            "human_assistance_task_count": 1,
            "waiting_human_confirm_task_count": 1,
            "needs_clarification_task_count": 0,
            "benchmark_run_task_count": 2,
            "benchmark_promoted_count": 1,
            "benchmark_blocked_count": 1,
            "total_tokens": 12345,
            "total_cost_estimate": 1.2345,
            "veto_reason_counts": [
                {"reason": "critical_incidents_present", "count": 1},
            ],
            "top_tasks": [
                {
                    "task_id": "todo-1",
                    "workflow_profile_id": "coding-default",
                    "workflow_channel": "candidate",
                    "stage_id": "review",
                    "open_incident_count": 1,
                    "critical_open_incident_count": 1,
                    "requires_human_assistance": True,
                    "waiting_human_confirm": False,
                    "needs_clarification": False,
                }
            ],
        }

        event = module.build_control_plane_summary_event(summary, notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertEqual(event["kind"], "control_plane_summary")
        self.assertTrue(event["views"]["human"]["visible"])
        self.assertIn("控制面当前仍有待处理风险", text)
        self.assertIn("窗口：最近 24 小时，扫描 3 个 task", text)
        self.assertIn("未闭环 incident 2 个（critical 1 个）", text)
        self.assertIn("benchmark：最近有结果 2 个 task，允许晋升 1 个，未通过 1 个", text)
        self.assertIn("critical_incidents_present x1", text)
        self.assertIn("todo-1 coding-default@candidate / 评审", text)

    def test_benchmark_sweep_event_summarizes_failures_and_promotions(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "status": "partial_failure",
            "generated_at": "2026-03-22T12:00:00+00:00",
            "requested_suite_ids": ["coding-default-core", "research-default-core"],
            "success_count": 1,
            "failure_count": 1,
            "results": [
                {
                    "suite_id": "coding-default-core",
                    "status": "ok",
                    "summary": {
                        "workflow_scorecard": {
                            "decision": {
                                "promote_to_new_baseline": True,
                                "veto_reasons": [],
                            }
                        }
                    },
                }
            ],
            "failures": [
                {
                    "suite_id": "research-default-core",
                    "error_type": "ValueError",
                    "error": "benchmark suite not found: research-default-core",
                }
            ],
        }

        event = module.build_benchmark_sweep_event(summary, notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertEqual(event["kind"], "benchmark_sweep")
        self.assertTrue(event["views"]["human"]["visible"])
        self.assertIn("基准批跑出现 1 个失败", text)
        self.assertIn("请求基准集：coding-default-core, research-default-core", text)
        self.assertIn("成功 1 个，失败 1 个", text)
        self.assertIn("coding-default-core -> 允许晋升", text)
        self.assertIn("research-default-core -> ValueError", text)

    def test_task_control_plane_event_summarizes_open_incident_and_benchmark(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        report = {
            "task": {
                "task_id": "todo-control-1",
                "status": "running",
                "action": "retry",
                "workflow_profile_id": "coding-default",
                "workflow_channel": "candidate",
                "stage_id": "implement",
            },
            "control_plane": {
                "latest_output": {
                    "output_type": "agent_report",
                    "summary": "需要人工协助",
                    "payload": {
                        "human_gate": {
                            "requires_human_assistance": True,
                            "need_human_confirm": False,
                            "human_confirmed": True,
                            "needs_clarification": False,
                        }
                    },
                },
                "latest_incident": {
                    "incident_type": "stage_contract_failed",
                    "severity": "critical",
                    "status": "open",
                    "summary": "仍需人工复核",
                },
                "latest_benchmark_run": {
                    "benchmark_suite_id": "coding-default-core",
                    "workflow_channel": "candidate",
                    "decision": {
                        "promote_to_new_baseline": False,
                        "veto_reasons": ["critical_incidents_present"],
                    },
                },
                "open_incidents": [
                    {
                        "incident_type": "stage_contract_failed",
                        "severity": "critical",
                        "status": "open",
                        "summary": "仍需人工复核",
                    }
                ],
                "open_incident_count": 1,
                "critical_open_incident_count": 1,
                "requires_human_assistance": True,
                "waiting_human_confirm": False,
                "needs_clarification": False,
                "benchmark_suite_ids": ["coding-default-core"],
            },
            "diagnostics": {
                "task_output_count": 1,
                "incident_count": 1,
                "benchmark_run_count": 1,
            },
            "timing": {"completed_at": "", "started_at": "2026-03-22T10:00:00+00:00"},
        }

        event = module.build_task_control_plane_event(report, notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertEqual(event["kind"], "task_control_plane")
        self.assertTrue(event["views"]["human"]["visible"])
        self.assertIn("当前有 1 个未闭环事件，其中 1 个为 critical。", text)
        self.assertIn("工作流：coding-default@candidate / 实现", text)
        self.assertIn("人工门禁：需要人工协助", text)
        self.assertIn("stage_contract_failed（critical/open） -> 仍需人工复核", text)
        self.assertIn("最近基准：coding-default-core -> 未通过晋升", text)
        self.assertIn("critical_incidents_present", text)

    def test_task_control_plane_event_error_mode_hides_clean_task(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        report = {
            "task": {
                "task_id": "todo-control-clean-1",
                "status": "passed",
                "action": "complete",
                "workflow_profile_id": "coding-default",
                "workflow_channel": "stable",
                "stage_id": "review",
            },
            "control_plane": {
                "latest_output": {
                    "output_type": "agent_report",
                    "summary": "任务已完成",
                    "payload": {
                        "human_gate": {
                            "requires_human_assistance": False,
                            "need_human_confirm": False,
                            "human_confirmed": True,
                            "needs_clarification": False,
                        }
                    },
                },
                "latest_incident": {},
                "latest_benchmark_run": {},
                "open_incidents": [],
                "open_incident_count": 0,
                "critical_open_incident_count": 0,
                "requires_human_assistance": False,
                "waiting_human_confirm": False,
                "needs_clarification": False,
                "benchmark_suite_ids": [],
            },
            "diagnostics": {
                "task_output_count": 1,
                "incident_count": 0,
                "benchmark_run_count": 0,
            },
            "timing": {"completed_at": "2026-03-22T11:00:00+00:00", "started_at": "2026-03-22T10:30:00+00:00"},
        }

        event = module.build_task_control_plane_event(report, notify_on="error")
        self.assertFalse(event["views"]["human"]["visible"])
        self.assertEqual(module.render_human_view(event["views"]["human"]), "NO_REPLY")

    def test_task_executor_human_view_shows_structured_task_details_and_progress(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "started_at": "2026-03-13T03:18:25+00:00",
            "run_id": "exec-20260313_031825-1124f6ed",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 3,
            "tasks_executed": 3,
            "tasks_skipped": 0,
            "results": [
                {
                    "task_id": "todo-a",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "report_status": "failed",
                    "reason": "call_agent_exception:timeout",
                    "task_requirement": "补齐任务执行器的人类摘要，失败任务要带失败原因和执行概况。",
                    "failure_count": 2,
                    "duration_ms": 14500,
                    "input_tokens": 1200,
                    "output_tokens": 2000,
                    "cost_estimate": 0.01234,
                    "failed_items": ["dingtalk webhook request timeout"],
                    "model": "openai-codex/gpt-5",
                },
                {
                    "task_id": "todo-b",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "report_status": "partial",
                    "reason": "partial",
                    "task_requirement": "让等待人工确认的任务也显示任务内容，而不是只显示 task_id。",
                },
                {
                    "task_id": "todo-c",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "report_status": "failed",
                    "reason": "failed",
                    "task_requirement": "把未闭环任务统一成人看的卡片格式。",
                },
            ],
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        human = event["views"]["human"]
        text = module.render_human_view(human)

        self.assertEqual(event["kind"], "task_executor")
        self.assertEqual(human["title"], "任务执行器（10分钟）")
        self.assertIn("首次发现 3 个未闭环任务。", text)
        self.assertIn("本轮变化：新增 3 个，变化 0 个，已闭环 0 个，仍未闭环 3 个。", text)
        self.assertIn("事项1：补齐任务执行器的人类摘要", text)
        self.assertIn("执行人1：optimization-agent", text)
        self.assertIn("执行结论1：执行失败", text)
        self.assertIn("失败原因1：调用执行代理失败", text)
        self.assertIn("需要协助1：超时", text)
        self.assertIn("执行概况1：模型=openai-codex · gpt-5；tokens=总=0.0032M（输入=0.0012M，输出=0.0020M）；耗时=14.5秒；成本≈$0.012340", text)
        self.assertNotIn("optimization-agent：未命名任务", text)

    def test_task_executor_error_notify_hides_success_run_from_human_view(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "started_at": "2026-03-13T03:58:13+00:00",
            "run_id": "exec-20260313_035813-cd9e93f0",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "results": [
                {
                    "task_id": "todo-ok",
                    "assignee": "optimization-agent",
                    "status": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                }
            ],
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        human = event["views"]["human"]

        self.assertFalse(human["visible"])
        self.assertEqual(module.render_human_view(human), "NO_REPLY")

    def test_task_executor_human_view_explains_preflight_blocked_reassign(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "started_at": "2026-03-14T07:20:00+00:00",
            "run_id": "exec-20260314_072000-aaaa1111",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 1,
            "tasks_executed": 0,
            "tasks_skipped": 1,
            "preflight_warning_tasks": 1,
            "preflight_blocked_tasks": 1,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "backend-dev",
                    "task_type": "governance_evolution_optimize",
                    "status": "failed",
                    "reason": "preflight_strict_blocked",
                    "preflight_reassign": {
                        "recommended_agents": ["optimization-agent"],
                    },
                }
            ],
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertIn("首次发现 1 个未闭环任务。", text)
        self.assertIn("事项1：governance_evolution_optimize 任务", text)
        self.assertIn("执行人1：backend-dev", text)
        self.assertIn("执行结论1：未执行", text)
        self.assertIn("失败原因1：派单能力不匹配", text)
        self.assertIn("需要协助1：改派给 optimization-agent", text)

    def test_task_executor_human_view_uses_compact_problem_cards(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "started_at": "2026-03-17T05:42:11+00:00",
            "finished_at": "2026-03-17T05:42:11+00:00",
            "run_id": "exec-20260317_054211-697478b5",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 2,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "project-agent",
                    "stage": "plan",
                    "status": "failed",
                    "reason": "preflight_strict_blocked",
                    "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                    "preflight_reassign": {
                        "recommended_agents": ["project-agent"],
                    },
                },
                {
                    "task_id": "todo-risk-2",
                    "assignee": "optimization-agent",
                    "stage": "implement",
                    "status": "failed",
                    "reason": "needs_clarification",
                    "task_requirement": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                },
            ],
            "task_change_notify": {
                "suppressed": False,
                "mode": "initial",
                "new_count": 2,
                "changed_count": 0,
                "resolved_count": 0,
                "open_count": 2,
                "focus_task_ids": ["todo-risk-1", "todo-risk-2"],
                "resolved_items": [],
            },
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertIn("首次发现 2 个未闭环任务。", text)
        self.assertIn("本轮变化：新增 2 个，变化 0 个，已闭环 0 个，仍未闭环 2 个。", text)
        self.assertIn("事项1：补齐项目索引治理方案，并确认是否纳入本周计划。", text)
        self.assertIn("执行人1：project-agent（规划）", text)
        self.assertIn("执行结论1：未执行", text)
        self.assertIn("失败原因1：派单能力不匹配", text)
        self.assertIn("需要协助1：改派给 project-agent", text)
        self.assertNotIn("执行概况1", text)
        self.assertNotIn("值得做1", text)

    def test_task_executor_human_view_delta_only_shows_changed_items(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "started_at": "2026-03-17T06:03:24+00:00",
            "finished_at": "2026-03-17T06:03:24+00:00",
            "run_id": "exec-20260317_060324-08861d20",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 2,
            "tasks_executed": 1,
            "tasks_skipped": 1,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "project-agent",
                    "stage": "plan",
                    "status": "failed",
                    "reason": "waiting_human_confirm",
                    "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                },
                {
                    "task_id": "todo-risk-2",
                    "assignee": "optimization-agent",
                    "stage": "implement",
                    "status": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "task_requirement": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                },
            ],
            "task_change_notify": {
                "suppressed": False,
                "mode": "delta",
                "new_count": 0,
                "changed_count": 1,
                "resolved_count": 1,
                "open_count": 1,
                "focus_task_ids": ["todo-risk-1"],
                "resolved_items": [
                    {
                        "task_id": "todo-risk-2",
                        "subject": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                        "assignee": "optimization-agent",
                        "stage": "implement",
                    }
                ],
            },
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        text = module.render_human_view(event["views"]["human"])

        self.assertIn("1 个任务有变化，1 个任务已闭环。", text)
        self.assertIn("本轮变化：新增 0 个，变化 1 个，已闭环 1 个，仍未闭环 1 个。", text)
        self.assertIn("事项1：补齐项目索引治理方案，并确认是否纳入本周计划。", text)
        self.assertIn("执行结论1：等待人工确认", text)
        self.assertIn("失败原因1：等待人工确认", text)
        self.assertIn("需要协助1：人工确认后才能继续执行", text)
        self.assertIn("已闭环1：梳理任务执行器的人类摘要模板，避免重复刷屏。 -> optimization-agent（实现）", text)
        self.assertNotIn("任务2：", text)

    def test_ops_scan_human_view_summarizes_failure_reason_and_repair_progress(self):
        module = load_module(
            "workflow_views",
            "skills/library/openclaw-workflow-manager/scripts/workflow_views.py",
        )

        record = {
            "task_id": "cron:ops-incremental-monitor",
            "mode": "incremental",
            "time": "2026-03-13T03:26:41+00:00",
            "run_id": "8a7f6c15ed5a",
            "risk_reasons": [
                "workflow_job_error=3",
                "workflow_job_error_stale=3",
            ],
            "workflow_health": {
                "failed_jobs": [
                    {
                        "id": "9873ab34-c4af-4db0-8cd5-40df68f92efd",
                        "name": "ops_daily_work_report_dingtalk",
                        "consecutive_errors": 3,
                        "last_status": "error",
                        "last_error": "Error: cron: job execution timed out",
                    },
                    {
                        "id": "31f0c650-53d2-4b86-9d8b-6ad8e8f0d053",
                        "name": "ops_local_openclaw_git_backup",
                        "consecutive_errors": 11,
                        "last_status": "error",
                        "last_error": "",
                    },
                    {
                        "id": "0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a",
                        "name": "reviewer_incremental_daily_4am",
                        "consecutive_errors": 3,
                        "last_status": "error",
                        "last_error": "cron: job execution timed out",
                    },
                ],
            },
            "workflow_follow_up_summary": {
                "created_count": 1,
                "pending_count": 2,
            },
        }

        event = module.build_ops_scan_event(record)
        human = event["views"]["human"]
        text = module.render_human_view(human)

        self.assertEqual(event["kind"], "ops_scan")
        self.assertIn("发现 3 个工作流失败，3 个持续失败。", text)
        self.assertIn("原因解析：超时 2 项；缺少明确错误详情 1 项。", text)
        self.assertIn("修复进展: 新建修复任务 1 条，已有待处理修复任务 2 条。", text)
        self.assertIn("工作日报汇总", text)


if __name__ == "__main__":
    unittest.main()

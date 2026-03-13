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
    def test_task_executor_human_view_shows_conclusion_reason_and_progress(self):
        module = load_module(
            "workflow_views",
            "scripts/openclaw-ops/workflow_views.py",
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
                    "report_status": "partial",
                    "reason": "partial",
                },
                {
                    "task_id": "todo-b",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "report_status": "partial",
                    "reason": "partial",
                },
                {
                    "task_id": "todo-c",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "report_status": "failed",
                    "reason": "failed",
                },
            ],
        }

        event = module.build_task_executor_event(summary, Path("/tmp/report.json"), notify_on="error")
        human = event["views"]["human"]
        text = module.render_human_view(human)

        self.assertEqual(event["kind"], "task_executor")
        self.assertEqual(human["title"], "任务执行异常")
        self.assertIn("结论: 本轮选中的 3 个任务均未闭环。", text)
        self.assertIn("原因解析: 任务仅部分完成 2 个；任务执行失败 1 个。", text)
        self.assertIn("修复进展: 已执行 3/3，已闭环 0，部分推进 2，失败 1。", text)
        self.assertIn("失败明细:", text)
        self.assertIn("todo-c", text)

    def test_task_executor_error_notify_hides_success_run_from_human_view(self):
        module = load_module(
            "workflow_views",
            "scripts/openclaw-ops/workflow_views.py",
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

    def test_ops_scan_human_view_summarizes_failure_reason_and_repair_progress(self):
        module = load_module(
            "workflow_views",
            "scripts/openclaw-ops/workflow_views.py",
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
        self.assertIn("结论: 当前有 3 个工作流失败，其中 3 个持续失败仍未恢复。", text)
        self.assertIn("原因解析: 超时 2 项；缺少明确错误详情 1 项。", text)
        self.assertIn("修复进展: 新建修复任务 1 条，已有待处理修复任务 2 条。", text)
        self.assertIn("ops_daily_work_report_dingtalk", text)


if __name__ == "__main__":
    unittest.main()

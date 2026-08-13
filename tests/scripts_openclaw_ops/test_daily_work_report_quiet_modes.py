import io
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


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


class DailyWorkReportQuietModeTests(unittest.TestCase):
    def test_daily_work_report_stays_quiet_without_exceptions(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-07T00:15:00+08:00",
            new_todo=[],
            new_done=[],
            todo_file_pending=[],
            planner_summary={},
            exception_reasons=[],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertEqual(output, "NO_REPLY")

    def test_daily_work_report_exception_output_is_human_friendly_chinese(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-07T00:15:00+08:00",
            new_todo=[],
            new_done=[],
            todo_file_pending=[],
            planner_summary={},
            exception_reasons=[
                "dingtalk_post_failed:timeout",
                "webhook_missing:DINGTALK_WEBHOOK_URL",
            ],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertIn("每日工作报告异常", output.splitlines()[0])
        self.assertIn("钉钉发送失败", output)
        self.assertIn("Webhook 未配置", output)
        self.assertIn("留痕编号", output)
        self.assertNotIn("/tmp/daily_work_report.json", output)
        self.assertNotIn(".json", output)
        self.assertNotIn("# 每日工作报告", output)

    def test_daily_work_report_uses_human_judgement_when_exception_and_backlog_exist(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-15T00:15:35+08:00",
            new_todo=[
                {
                    "task_id": "todo-high-risk",
                    "reason": "补齐日报收敛策略",
                    "requirement": "统一日报中的任务摘要结构，只保留任务、要求、状态和值得做四个字段。",
                    "acceptance": "人工看到日报后，可以直接判断先做什么，不需要再读任务中心原始记录。",
                    "priority": "high",
                    "risk_level": "high",
                    "assignee": "ops-agent",
                    "status": "pending",
                }
            ],
            new_done=[],
            todo_file_pending=[],
            planner_summary={
                "report_count": 8,
                "task_count": 8,
                "failed_task_count": 1,
            },
            exception_reasons=[
                "webhook_missing:DINGTALK_WEBHOOK_URL;checked_env_files=/tmp/runtime.env",
            ],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertIn("人工判断：异常优先，先恢复钉钉触达，再看待办推进。", output)
        self.assertIn("当前判断：钉钉 Webhook 未配置，今天最先要补的是告警出口。", output)
        self.assertIn("任务1：补齐日报收敛策略", output)
        self.assertIn("要求1：统一日报中的任务摘要结构", output)
        self.assertIn("状态1：任务中心待处理", output)
        self.assertIn("值得做1：", output)
        self.assertNotIn("checked_env_files", output)
        self.assertLess(output.index("当前判断：钉钉 Webhook 未配置"), output.index("任务1：补齐日报收敛策略"))

    def test_daily_work_report_shows_failure_reason_and_execution_metrics_for_failed_task(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-15T00:15:35+08:00",
            new_todo=[
                {
                    "task_id": "todo-failed-task",
                    "reason": "修复日报发送失败问题",
                    "requirement": "恢复钉钉日报发送，并确保失败任务展示完整执行信息。",
                    "acceptance": "人工能直接看到失败原因、失败次数、耗时和执行模型。",
                    "priority": "high",
                    "risk_level": "high",
                    "assignee": "ops-agent",
                    "status": "failed",
                    "failure_count": 2,
                    "retry_count": 1,
                    "latest_report": {
                        "failed_items": ["dingtalk webhook request timeout"],
                        "duration_ms": 14500,
                        "model_id": "openai-codex/gpt-5",
                        "input_tokens": 1200,
                        "output_tokens": 2000,
                        "total_tokens": 3200,
                        "cost_estimate": 0.01234,
                    },
                }
            ],
            new_done=[],
            todo_file_pending=[],
            planner_summary={},
            exception_reasons=[],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertIn("状态1：任务中心执行失败", output)
        self.assertIn(
            "失败信息1：原因=dingtalk webhook request timeout；失败次数=2次；最近耗时=14.5秒；已重试=1次",
            output,
        )
        self.assertIn(
            "执行概况1：模型=openai-codex · gpt-5；tokens=总=3200（输入=1200，输出=2000）；成本≈$0.012340",
            output,
        )

    def test_daily_work_report_main_uses_digest_notify_without_name_error(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        invoked: list[list[str]] = []

        def fake_invoke(_db_path, args, timeout=30):
            invoked.append(list(args))
            if args and args[0] == "planner-summary":
                return True, {"ok": True, "summary": {"planner_id": "coordinator", "report_count": 0}}, ""
            if args and args[0] in {"log-module", "log-communication", "report-agent-result"}:
                return True, {"ok": True, "result": {"planner_payload": {"report_status": "passed", "notify_chat": False, "failure_count": 0}}}, ""
            return True, {"ok": True}, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            state_path = tmp / "state.json"
            report_dir = tmp / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            argv = [
                "daily_work_report.py",
                "--db",
                str(db_path),
                "--state-file",
                str(state_path),
                "--report-dir",
                str(report_dir),
                "--task-id",
                "cron:ops-daily-work-report",
                "--dingtalk-webhook",
                "https://example.invalid/hook",
                "--dingtalk-secret",
                "dummy-secret",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(
                    module,
                    "load_tasks",
                    return_value=[{"task_id": "todo-1", "status": "pending", "updated_at": "2026-03-08T00:10:00+08:00"}],
                ):
                    with mock.patch.object(module, "collect_observability_stats", return_value={}):
                        with mock.patch.object(module, "ensure_task_binding", return_value=("cron:ops-daily-work-report", "")):
                            with mock.patch.object(module, "invoke_policy_enforcer", side_effect=fake_invoke):
                                with mock.patch.object(module, "post_dingtalk", return_value=(True, "ok")):
                                    with redirect_stdout(stdout):
                                        rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertTrue(payload["notify"])
        self.assertNotEqual(payload["output"], "NO_REPLY")
        self.assertIn("todo-1", payload["output"])
        self.assertTrue(any(args and args[0] == "log-module" for args in invoked))
        self.assertTrue(any(args and args[0] == "log-communication" for args in invoked))

        details_payloads = []
        for args in invoked:
            if args and args[0] in {"log-module", "log-communication"}:
                idx = args.index("--details-json")
                details_payloads.append(json.loads(args[idx + 1]))
        self.assertTrue(details_payloads)
        self.assertTrue(all(item.get("notify") is True for item in details_payloads if "notify" in item))

    def test_daily_work_report_main_includes_todo_markdown_backlog_in_digest(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )
        invoked: list[list[str]] = []

        def fake_invoke(_db_path, args, timeout=30):
            invoked.append(list(args))
            if args and args[0] == "planner-summary":
                return True, {"ok": True, "summary": {"planner_id": "coordinator", "report_count": 0}}, ""
            if args and args[0] in {"log-module", "log-communication", "report-agent-result"}:
                return True, {"ok": True, "result": {"planner_payload": {"report_status": "passed", "notify_chat": True, "failure_count": 0}}}, ""
            return True, {"ok": True}, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            state_path = tmp / "state.json"
            report_dir = tmp / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            todo_file = tmp / "todo.md"
            todo_file.write_text("# todo\n\n## 重要不紧急\n- [ ] sync-report-rule P2\n", encoding="utf-8")

            argv = [
                "daily_work_report.py",
                "--db",
                str(db_path),
                "--state-file",
                str(state_path),
                "--report-dir",
                str(report_dir),
                "--task-id",
                "cron:ops-daily-work-report",
                "--todo-file",
                str(todo_file),
                "--dingtalk-webhook",
                "https://example.invalid/hook",
                "--dingtalk-secret",
                "dummy-secret",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(module, "load_tasks", return_value=[]):
                    with mock.patch.object(module, "collect_observability_stats", return_value={}):
                        with mock.patch.object(module, "ensure_task_binding", return_value=("cron:ops-daily-work-report", "")):
                            with mock.patch.object(module, "invoke_policy_enforcer", side_effect=fake_invoke):
                                with mock.patch.object(module, "post_dingtalk", return_value=(True, "ok")):
                                    with redirect_stdout(stdout):
                                        rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertTrue(payload["notify"])
        self.assertIn("sync-report-rule", payload["output"])
        self.assertNotEqual(payload["output"], "NO_REPLY")


    def test_daily_work_report_main_ignores_runtime_binding_tasks(self):
        module = load_module(
            "daily_work_report",
            "skills/library/task-cost-analytics/scripts/daily_work_report.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            state_path = tmp / "state.json"
            report_dir = tmp / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            argv = [
                "daily_work_report.py",
                "--db",
                str(db_path),
                "--state-file",
                str(state_path),
                "--report-dir",
                str(report_dir),
                "--task-id",
                "cron:ops-daily-work-report",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(
                    module,
                    "load_tasks",
                    return_value=[
                        {
                            "task_id": "cron:ops-daily-summary",
                            "task_type": "ops_runtime_cron",
                            "reason": "[CRON_RUNTIME] bind cron:ops-daily-summary",
                            "status": "pending",
                            "updated_at": "2026-03-12T23:00:00+08:00",
                        },
                        {
                            "task_id": "cron:ops-daily-work-report",
                            "task_type": "ops_runtime_cron",
                            "reason": "[CRON_RUNTIME] bind cron:ops-daily-work-report",
                            "status": "passed",
                            "updated_at": "2026-03-12T23:00:00+08:00",
                        },
                    ],
                ):
                    with mock.patch.object(module, "collect_observability_stats", return_value={}):
                        with mock.patch.object(
                            module,
                            "ensure_task_binding",
                            return_value=("cron:ops-daily-work-report", ""),
                        ):
                            with mock.patch.object(module, "invoke_policy_enforcer", return_value=(True, {"ok": True}, "")):
                                with redirect_stdout(stdout):
                                    rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertFalse(payload["notify"])
        self.assertEqual(payload["output"], "NO_REPLY")


if __name__ == "__main__":
    unittest.main()

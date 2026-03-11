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
            "scripts/openclaw-ops/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-07T00:15:00+08:00",
            exception_reasons=[],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertEqual(output, "NO_REPLY")

    def test_daily_work_report_exception_output_is_human_friendly_chinese(self):
        module = load_module(
            "daily_work_report",
            "scripts/openclaw-ops/daily_work_report.py",
        )
        output = module.build_chat_output(
            sender_identity="ops-agent/daily-work-report",
            task_id="cron:ops-daily-work-report",
            run_time="2026-03-07T00:15:00+08:00",
            exception_reasons=[
                "dingtalk_post_failed:timeout",
                "webhook_missing:DINGTALK_WEBHOOK_URL",
            ],
            report_file=Path("/tmp/daily_work_report.json"),
        )
        self.assertEqual(output.splitlines()[0], "每日工作报告异常")
        self.assertIn("钉钉发送失败", output)
        self.assertIn("Webhook 未配置", output)
        self.assertIn("留痕编号", output)
        self.assertNotIn("/tmp/daily_work_report.json", output)
        self.assertNotIn(".json", output)
        self.assertNotIn("# 每日工作报告", output)

    def test_daily_work_report_main_uses_digest_notify_without_name_error(self):
        module = load_module(
            "daily_work_report",
            "scripts/openclaw-ops/daily_work_report.py",
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
        self.assertFalse(payload["notify"])
        self.assertEqual(payload["output"], "NO_REPLY")
        self.assertTrue(any(args and args[0] == "log-module" for args in invoked))
        self.assertTrue(any(args and args[0] == "log-communication" for args in invoked))

        details_payloads = []
        for args in invoked:
            if args and args[0] in {"log-module", "log-communication"}:
                idx = args.index("--details-json")
                details_payloads.append(json.loads(args[idx + 1]))
        self.assertTrue(details_payloads)
        self.assertTrue(all(item.get("notify") is True for item in details_payloads if "notify" in item))


if __name__ == "__main__":
    unittest.main()

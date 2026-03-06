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
        self.assertIn("daily_work_report.json", output)
        self.assertNotIn("# 每日工作报告", output)


if __name__ == "__main__":
    unittest.main()

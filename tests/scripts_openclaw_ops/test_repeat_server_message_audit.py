import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
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


class RepeatServerMessageAuditTests(unittest.TestCase):
    def test_classify_summary_detects_unsuitable_message_types(self):
        module = load_module(
            "repeat_server_message_audit",
            "skills/library/openclaw-security-audit/scripts/repeat_server_message_audit.py",
        )
        self.assertEqual(module.classify_summary('{"ok": true, "run_id": "exec-1"}'), "json_误发")
        self.assertEqual(module.classify_summary("Let's run the scheduled command."), "英文废话误发")
        self.assertEqual(module.classify_summary("# local-git-backup\nrepo: /home/runtime-user/.openclaw"), "正常信息误发")
        self.assertEqual(module.classify_summary("```\n# local-git-backup\n```"), "正常信息误发")
        self.assertIsNone(module.classify_summary("任务执行异常\n问题: 模型被策略拦截"))

    def test_summarize_entries_marks_current_unsuitable_messages(self):
        module = load_module(
            "repeat_server_message_audit",
            "skills/library/openclaw-security-audit/scripts/repeat_server_message_audit.py",
        )
        entries = [
            {"ts_sort": 40, "delivered": False, "summary": "", "job_name": "ops_incremental_monitor"},
            {"ts_sort": 39, "delivered": True, "summary": "Let's run the scheduled command.", "job_name": "todo_patrol_15m"},
            {"ts_sort": 38, "delivered": True, "summary": "# local-git-backup", "job_name": "ops_local_openclaw_git_backup"},
            {"ts_sort": 37, "delivered": False, "summary": "", "job_name": "project_index_maintainer_4h"},
        ]
        summary = module.summarize_entries(entries, recent_limit=50, latest_limit=20)
        self.assertEqual(summary["recent_delivered_checked"], 2)
        self.assertEqual(summary["unsuitable_count"], 2)
        self.assertEqual(summary["latest20_total"], 4)
        self.assertEqual(summary["latest20_quiet_ok"], 2)
        self.assertEqual(summary["latest20_unsuitable_count"], 2)
        self.assertEqual(len(summary["samples"]), 2)
        self.assertEqual(summary["samples"][0]["kind"], "英文废话误发")

    def test_summarize_entries_separates_historical_only_messages(self):
        module = load_module(
            "repeat_server_message_audit",
            "skills/library/openclaw-security-audit/scripts/repeat_server_message_audit.py",
        )
        entries = []
        for idx in range(20):
            entries.append(
                {
                    "ts_sort": 100 - idx,
                    "delivered": False,
                    "summary": "",
                    "job_name": f"quiet-{idx}",
                }
            )
        entries.append(
            {
                "ts_sort": 70,
                "delivered": True,
                "summary": '{"ok": true, "run_id": "exec-2"}',
                "job_name": "task_executor_10m",
            }
        )
        summary = module.summarize_entries(entries, recent_limit=50, latest_limit=20)
        self.assertEqual(summary["unsuitable_count"], 1)
        self.assertEqual(summary["latest20_unsuitable_count"], 0)
        self.assertEqual(summary["latest20_quiet_ok"], 20)

    def test_compute_round_schedule_starts_immediately_then_every_three_hours(self):
        module = load_module(
            "repeat_server_message_audit",
            "skills/library/openclaw-security-audit/scripts/repeat_server_message_audit.py",
        )
        start = datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc)
        schedule = module.compute_round_schedule(start, total_rounds=4, interval_seconds=3 * 60 * 60)
        self.assertEqual(len(schedule), 4)
        self.assertEqual(schedule[0], start)
        self.assertEqual(schedule[1], start + timedelta(hours=3))
        self.assertEqual(schedule[3], start + timedelta(hours=9))

    def test_remote_scripts_use_generic_repository_contract(self):
        module = load_module(
            "repeat_server_message_audit",
            "skills/library/openclaw-security-audit/scripts/repeat_server_message_audit.py",
        )
        probe = module.build_remote_probe_script("HOST_A", "~/workflow-infra")
        remediation = module.build_remote_remediation_script(
            "HOST_A", "/home/runtime-user/workflow-infra", "/home/runtime-user/.openclaw"
        )
        self.assertIn("skills/library/project-delivery-pipeline", probe)
        self.assertIn("~/workflow-infra", probe)
        self.assertIn("setup.py", remediation)
        self.assertIn("--runtime-home", remediation)
        self.assertNotIn("sync_openclaw_ops_files.py", remediation)
        self.assertNotIn("install_workflow_profile.py", remediation)


if __name__ == "__main__":
    unittest.main()

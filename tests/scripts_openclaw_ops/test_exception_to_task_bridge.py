import importlib.util
import sys
import tempfile
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


class ExceptionToTaskBridgeTests(unittest.TestCase):
    def test_critical_exception_creates_ops_task_and_incident(self):
        bridge = load_module(
            "exception_to_task_bridge",
            "skills/library/log-monitor/scripts/exception_to_task_bridge.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log_dir = root / "logs"
            log_dir.mkdir()
            (log_dir / "agent.log").write_text(
                "\n".join(
                    [
                        "2026-04-24 ERROR out of memory while dispatching worker",
                        "2026-04-24 ERROR out of memory while dispatching worker",
                        "2026-04-24 ERROR out of memory while dispatching worker",
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "task_center.db"
            report_dir = root / "reports"

            scan = bridge.scan_exceptions([log_dir], scan_since_hours=24)
            reports = bridge.write_reports(
                scan_result=scan,
                output_dir=report_dir,
                abnormal_dir=None,
                task_id="test",
                cleanup=False,
            )
            summary = bridge.create_exception_tasks(
                scan_result=scan,
                task_db=db_path,
                report_paths=reports,
                actor="test",
                assignee="ops-agent",
                human_assignee="human-inbox",
                min_alert_level="info",
                max_tasks=5,
                dry_run=False,
            )

            self.assertEqual(summary["alert_level"], "critical")
            self.assertEqual(len(summary["created"]), 1)
            task_id = summary["created"][0]
            center = task_center_module.TaskCenter(db_path)
            try:
                task = center.get_task(task_id, display_safe=False)
                incidents = center.list_task_incidents(task_id, display_safe=False)
                outputs = center.list_task_outputs(task_id, display_safe=False)
            finally:
                center.close()
            report_exists = Path(reports["json"]).exists()

        self.assertEqual(task["task_type"], "ops_exception")
        self.assertEqual(task["assignee"], "human-inbox")
        self.assertTrue(task["need_human_confirm"])
        self.assertEqual(incidents[-1]["severity"], "critical")
        self.assertEqual(outputs[-1]["output_type"], "human_question")
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()

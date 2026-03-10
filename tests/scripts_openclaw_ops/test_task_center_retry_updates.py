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


class TaskCenterRetryUpdateTests(unittest.TestCase):
    def test_update_task_allows_retry_and_failure_counters(self):
        module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "cron:ops-daily-work-report",
                        "pool": "jobs",
                        "task_type": "workflow",
                        "reason": "retry regression coverage",
                        "source": "openclaw",
                        "request_source": "ai",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "requirement": "Allow retry metadata updates.",
                        "result_output": "Persist updated retry counters.",
                        "acceptance": "retry_count and failure_count are stored.",
                        "observable_outputs": "Updated task row is queryable.",
                        "acceptance_thresholds": "Counters match requested values.",
                    },
                    actor="test",
                )

                updated = task_center.update_task(
                    "cron:ops-daily-work-report",
                    actor="test",
                    fields={
                        "retry_count": 1,
                        "failure_count": 2,
                        "status": "failed",
                    },
                )
            finally:
                task_center.close()

        self.assertEqual(updated["retry_count"], 1)
        self.assertEqual(updated["failure_count"], 2)
        self.assertEqual(updated["status"], "failed")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import sys
import tempfile
import unittest
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


class TaskCenterRetryUpdateTests(unittest.TestCase):
    @staticmethod
    def _task_payload(task_id: str = "cron:ops-daily-work-report") -> dict[str, str]:
        return {
            "task_id": task_id,
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
        }

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
                task_center.create_task(self._task_payload(), actor="test")

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

    def test_create_task_routes_writes_through_retry_transaction(self):
        module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                with mock.patch.object(
                    task_center,
                    "_run_write_with_retry",
                    side_effect=lambda operation: operation(),
                ) as retry_mock:
                    task_center.create_task(self._task_payload("cron:ops-summary"), actor="test")
            finally:
                task_center.close()

        retry_mock.assert_called_once()

    def test_transition_status_and_add_event_route_writes_through_retry_transaction(self):
        module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(self._task_payload("cron:ops-transition"), actor="test")

                with mock.patch.object(
                    task_center,
                    "_run_write_with_retry",
                    side_effect=lambda operation: operation(),
                ) as retry_mock:
                    task_center.transition_status(
                        "cron:ops-transition",
                        new_status="running",
                        actor="test",
                        stage="implement",
                        allowed_from={"pending"},
                    )
                    self.assertEqual(retry_mock.call_count, 1)

                    retry_mock.reset_mock()
                    task_center.add_event(
                        "cron:ops-transition",
                        actor="test",
                        event_type="manual_note",
                        stage="observe",
                        details={"message": "standalone event"},
                    )
                    self.assertEqual(retry_mock.call_count, 1)
            finally:
                task_center.close()


if __name__ == "__main__":
    unittest.main()

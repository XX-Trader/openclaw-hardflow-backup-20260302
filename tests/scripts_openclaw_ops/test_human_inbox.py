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


class HumanInboxTests(unittest.TestCase):
    def test_list_and_confirm_human_gate_task(self):
        inbox = load_module(
            "human_inbox",
            "skills/library/control-plane-ops/scripts/policy/human_inbox.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            center = task_center_module.TaskCenter(db_path)
            try:
                center.init_schema()
                center.create_task(
                    {
                        "task_id": "todo-human-1",
                        "pool": "todo",
                        "task_type": "todo_deadline_candidate",
                        "reason": "Confirm due TODO",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "high",
                        "risk_level": "high",
                        "assignee": "human-inbox",
                        "status": "pending",
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "requirement": "Ask a human before execution.",
                        "result_output": "Confirmed task.",
                        "acceptance": "Human confirms the task.",
                        "observable_outputs": "human inbox row",
                        "acceptance_thresholds": "human_confirmed becomes true",
                    },
                    actor="test",
                )
            finally:
                center.close()

            items = inbox.list_inbox(db_path)
            self.assertEqual(len(items), 1)
            self.assertIn("waiting_confirm", items[0]["human_inbox_reasons"])

            confirmed = inbox.confirm_task(
                db_path,
                "todo-human-1",
                actor="human",
                assignee="project-agent",
            )
            remaining = inbox.list_inbox(db_path)

        self.assertTrue(confirmed["human_confirmed"])
        self.assertEqual(confirmed["action"], "confirmed_for_execution")
        self.assertEqual(confirmed["assignee"], "project-agent")
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()

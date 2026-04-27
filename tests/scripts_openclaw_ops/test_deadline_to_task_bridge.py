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


class DeadlineToTaskBridgeTests(unittest.TestCase):
    def test_due_todo_routes_low_risk_to_auto_queue_once(self):
        bridge = load_module(
            "deadline_to_task_bridge",
            "skills/library/todo-patrol/scripts/deadline_to_task_bridge.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "todo.md"
            todo_file.write_text(
                "\n".join(
                    [
                        "- [ ] Update README docs [due:2026-04-23]",
                        "- [x] Completed item [due:2026-04-23]",
                        "- [ ] Future item [due:2026-04-30]",
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "task_center.db"

            summary = bridge.create_due_candidates(
                todo_file=todo_file,
                task_db=db_path,
                actor="test",
                assignee="human-inbox",
                include_upcoming_days=0,
                dry_run=False,
            )
            second = bridge.create_due_candidates(
                todo_file=todo_file,
                task_db=db_path,
                actor="test",
                assignee="human-inbox",
                include_upcoming_days=0,
                dry_run=False,
            )

            self.assertEqual(len(summary["created"]), 1)
            self.assertEqual(len(second["existing"]), 1)
            task_id = summary["created"][0]
            center = task_center_module.TaskCenter(db_path)
            try:
                task = center.get_task(task_id, display_safe=False)
                outputs = center.list_task_outputs(task_id, display_safe=False)
            finally:
                center.close()

        self.assertEqual(task["task_type"], "todo_deadline_candidate")
        self.assertEqual(task["risk_level"], "low")
        self.assertFalse(task["need_human_confirm"])
        self.assertFalse(task["human_confirmed"])
        self.assertEqual(task["action"], "dispatch_pipeline")
        self.assertEqual(task["assignee"], "coordinator")
        self.assertEqual(outputs[-1]["output_type"], "deadline_auto_dispatch_ready")

    def test_due_high_risk_todo_creates_human_confirmed_candidate(self):
        bridge = load_module(
            "deadline_to_task_bridge_high_risk",
            "skills/library/todo-patrol/scripts/deadline_to_task_bridge.py",
        )
        task_center_module = load_module(
            "task_center_high_risk",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            todo_file = root / "todo.md"
            todo_file.write_text(
                "- [ ] [P1] 部署生产服务并重启 gateway [due:2026-04-23]",
                encoding="utf-8",
            )
            db_path = root / "task_center.db"

            summary = bridge.create_due_candidates(
                todo_file=todo_file,
                task_db=db_path,
                actor="test",
                assignee="human-inbox",
                include_upcoming_days=0,
                dry_run=False,
            )

            task_id = summary["created"][0]
            center = task_center_module.TaskCenter(db_path)
            try:
                task = center.get_task(task_id, display_safe=False)
                outputs = center.list_task_outputs(task_id, display_safe=False)
            finally:
                center.close()

        self.assertEqual(task["risk_level"], "high")
        self.assertTrue(task["need_human_confirm"])
        self.assertEqual(task["action"], "await_human_confirm")
        self.assertEqual(outputs[-1]["output_type"], "human_question")


if __name__ == "__main__":
    unittest.main()

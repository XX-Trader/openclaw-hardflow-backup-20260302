import importlib.util
import io
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
                        "context_payload": {
                            "route_selection": {
                                "mode": "manual_selection",
                                "recommended_route": "coding_workflow",
                            }
                        },
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
        self.assertEqual(confirmed["context_payload"]["route_selection"]["selected_route"], "coding_workflow")
        self.assertEqual(remaining, [])

    def test_confirm_can_record_non_pipeline_route_choice(self):
        inbox = load_module(
            "human_inbox_direct_route",
            "skills/library/control-plane-ops/scripts/policy/human_inbox.py",
        )
        task_center_module = load_module(
            "task_center_direct_route",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            center = task_center_module.TaskCenter(db_path)
            try:
                center.init_schema()
                center.create_task(
                    {
                        "task_id": "todo-human-direct",
                        "pool": "todo",
                        "task_type": "todo_deadline_candidate",
                        "reason": "Select route",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "human-inbox",
                        "status": "pending",
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "context_payload": {
                            "route_selection": {
                                "mode": "manual_selection",
                                "recommended_route": "todo_auto_candidate",
                            }
                        },
                        "requirement": "Ask a human before execution.",
                        "result_output": "Selected route.",
                        "acceptance": "Human selects route.",
                        "observable_outputs": "human inbox row",
                        "acceptance_thresholds": "human_confirmed becomes true",
                    },
                    actor="test",
                )
            finally:
                center.close()

            confirmed = inbox.confirm_task(
                db_path,
                "todo-human-direct",
                actor="human",
                route_choice="direct_run",
            )

        self.assertTrue(confirmed["human_confirmed"])
        self.assertEqual(confirmed["action"], "manual_direct_run_requested")
        self.assertEqual(confirmed["context_payload"]["route_selection"]["selected_route"], "direct_run")

    def test_confirm_specified_agent_requires_assignee(self):
        inbox = load_module(
            "human_inbox_specified_agent",
            "skills/library/control-plane-ops/scripts/policy/human_inbox.py",
        )
        task_center_module = load_module(
            "task_center_specified_agent",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            center = task_center_module.TaskCenter(db_path)
            try:
                center.init_schema()
                center.create_task(
                    {
                        "task_id": "todo-human-agent",
                        "pool": "todo",
                        "task_type": "todo_deadline_candidate",
                        "reason": "Select specified agent",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "human-inbox",
                        "status": "pending",
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "context_payload": {
                            "route_selection": {
                                "mode": "manual_selection",
                                "recommended_route": "specified_agent",
                            }
                        },
                        "requirement": "Ask a human before execution.",
                        "result_output": "Selected agent.",
                        "acceptance": "Human selects a concrete agent.",
                        "observable_outputs": "human inbox row",
                        "acceptance_thresholds": "human_confirmed becomes true only with assignee",
                    },
                    actor="test",
                )
            finally:
                center.close()

            with self.assertRaises(inbox.TaskCenterError):
                inbox.confirm_task(
                    db_path,
                    "todo-human-agent",
                    actor="human",
                    route_choice="specified_agent",
                )
            still_waiting = inbox.list_inbox(db_path)
            confirmed = inbox.confirm_task(
                db_path,
                "todo-human-agent",
                actor="human",
                route_choice="specified_agent",
                assignee="researcher",
            )

        self.assertEqual(len(still_waiting), 1)
        self.assertTrue(confirmed["human_confirmed"])
        self.assertEqual(confirmed["action"], "specified_agent_requested")
        self.assertEqual(confirmed["assignee"], "researcher")
        self.assertEqual(confirmed["context_payload"]["route_selection"]["selected_route"], "specified_agent")

    def test_cli_confirm_accepts_recommended_route_choice(self):
        inbox = load_module(
            "human_inbox_cli_recommended",
            "skills/library/control-plane-ops/scripts/policy/human_inbox.py",
        )
        task_center_module = load_module(
            "task_center_cli_recommended",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            center = task_center_module.TaskCenter(db_path)
            try:
                center.init_schema()
                center.create_task(
                    {
                        "task_id": "todo-human-recommended",
                        "pool": "todo",
                        "task_type": "todo_deadline_candidate",
                        "reason": "Select recommended route",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "human-inbox",
                        "status": "pending",
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "context_payload": {
                            "route_selection": {
                                "mode": "manual_selection",
                                "required": True,
                                "recommended_route": "todo_auto_candidate",
                            }
                        },
                        "requirement": "Ask a human before execution.",
                        "result_output": "Selected recommended route.",
                        "acceptance": "CLI accepts recommended route choice.",
                        "observable_outputs": "human inbox CLI",
                        "acceptance_thresholds": "human_confirmed becomes true",
                    },
                    actor="test",
                )
            finally:
                center.close()

            argv = [
                "human_inbox.py",
                "confirm",
                "--task-db",
                str(db_path),
                "--task-id",
                "todo-human-recommended",
                "--route-choice",
                "recommended",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", new_callable=io.StringIO):
                exit_code = inbox.main()

            center = task_center_module.TaskCenter(db_path)
            try:
                confirmed = center.get_task("todo-human-recommended", display_safe=False)
            finally:
                center.close()

        self.assertEqual(exit_code, 0)
        self.assertTrue(confirmed["human_confirmed"])
        self.assertEqual(confirmed["action"], "confirmed_for_execution")
        self.assertEqual(
            confirmed["context_payload"]["route_selection"]["selected_route"],
            "todo_auto_candidate",
        )


if __name__ == "__main__":
    unittest.main()

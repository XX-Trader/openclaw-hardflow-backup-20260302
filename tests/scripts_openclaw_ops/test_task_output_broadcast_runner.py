import importlib.util
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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


class TaskOutputBroadcastRunnerTests(unittest.TestCase):
    def test_build_payload_only_emits_changed_visible_tasks(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        runner_module = load_module(
            "task_output_broadcast_runner",
            "skills/library/task-cost-analytics/scripts/task_output_broadcast_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            state_path = Path(tmpdir) / "task-output-broadcast-state.json"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "task-broadcast-visible",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Need human review",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "running",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "review",
                        "requirement": "Broadcast changed task output.",
                        "result_output": "Task output batch consumer should emit.",
                        "acceptance": "Visible control plane event is announced.",
                        "observable_outputs": "task control plane broadcast",
                        "acceptance_thresholds": "human notify",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="task-broadcast-visible",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工复核",
                    payload={
                        "human_gate": {
                            "requires_human_assistance": True,
                            "human_confirmed": False,
                        }
                    },
                    actor="backend-dev",
                )
                task_center.record_task_incident(
                    task_id="task-broadcast-visible",
                    incident_type="task_escalated",
                    severity="critical",
                    status="open",
                    reason="human_review_needed",
                    summary="仍需人工处理",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                task_center.create_task(
                    {
                        "task_id": "task-broadcast-clean",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Already clean",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "requirement": "Clean task should stay quiet.",
                        "result_output": "No announcement needed.",
                        "acceptance": "NO_REPLY when no visible signal.",
                        "observable_outputs": "silent task output",
                        "acceptance_thresholds": "quiet",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="task-broadcast-clean",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="任务已完成",
                    payload={"human_gate": {"requires_human_assistance": False}},
                    actor="backend-dev",
                )
            finally:
                task_center.close()

            first = runner_module.build_task_output_broadcast_payload(
                db_file=db_path,
                state_file=state_path,
                lookback_hours=24,
                limit=10,
                event_limit=200,
                notify_on="error",
            )
            second = runner_module.build_task_output_broadcast_payload(
                db_file=db_path,
                state_file=state_path,
                lookback_hours=24,
                limit=10,
                event_limit=200,
                notify_on="error",
            )

        self.assertTrue(first["notify"])
        self.assertEqual(first["notified_task_count"], 1)
        self.assertEqual(first["items"][0]["task_id"], "task-broadcast-visible")
        self.assertIn("task-broadcast-visible", first["human_text"])
        self.assertFalse(second["notify"])
        self.assertEqual(second["human_text"], "NO_REPLY")

    def test_main_emit_json_returns_structured_payload(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        runner_module = load_module(
            "task_output_broadcast_runner",
            "skills/library/task-cost-analytics/scripts/task_output_broadcast_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            state_path = Path(tmpdir) / "state.json"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "task-broadcast-json",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "JSON output",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "failed",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "implement",
                        "requirement": "Return JSON payload.",
                        "result_output": "emit-json should work.",
                        "acceptance": "structured payload",
                        "observable_outputs": "stdout json",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_incident(
                    task_id="task-broadcast-json",
                    incident_type="stage_contract_failed",
                    severity="critical",
                    status="open",
                    reason="contract_failed",
                    summary="交付契约未满足",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = runner_module.main(
                    [
                        "--db",
                        str(db_path),
                        "--state-file",
                        str(state_path),
                        "--emit-json",
                    ]
                )

        self.assertTrue(payload["notify"])
        self.assertEqual(payload["notified_task_count"], 1)
        self.assertEqual(payload["items"][0]["task_id"], "task-broadcast-json")


if __name__ == "__main__":
    unittest.main()

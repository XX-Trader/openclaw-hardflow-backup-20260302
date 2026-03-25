import importlib.util
import json
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


class TaskOutputConsumerTests(unittest.TestCase):
    def test_build_task_output_consumer_payload_returns_human_event(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        consumer_module = load_module(
            "task_output_consumer",
            "scripts/openclaw-ops/task_output_consumer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-consumer-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Render control plane event",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "high",
                        "assignee": "backend-dev",
                        "status": "running",
                        "action": "retry",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "implement",
                        "human_confirmed": True,
                        "requirement": "Need a unified output consumer.",
                        "result_output": "Consumer returns event + text.",
                        "acceptance": "Control-plane signals are rendered.",
                        "observable_outputs": "task-output-consumer payload",
                        "acceptance_thresholds": "visible human text",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="todo-consumer-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工协助",
                    payload={
                        "human_gate": {
                            "requires_human_assistance": True,
                            "need_human_confirm": False,
                            "human_confirmed": True,
                            "needs_clarification": False,
                        }
                    },
                    actor="backend-dev",
                )
                task_center.record_task_incident(
                    task_id="todo-consumer-1",
                    incident_type="task_escalated",
                    severity="critical",
                    status="open",
                    reason="stage_contract_failed",
                    summary="仍需人工复核",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                task_center.record_benchmark_run(
                    task_id="todo-consumer-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="benchmark-consumer-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    baseline_run_ids=["baseline-1"],
                    candidate_run_ids=["candidate-1"],
                    summary_file="reports/latest-summary.json",
                    scorecard_file="reports/latest-workflow-scorecard.json",
                    decision={"promote_to_new_baseline": False, "veto_reasons": ["critical_incidents_present"]},
                    actor="upgrade-feedback-runner",
                )
            finally:
                task_center.close()

            payload = consumer_module.build_task_output_consumer_payload(
                db_file=db_path,
                task_id="todo-consumer-1",
                notify_on="error",
            )

        self.assertTrue(payload["notify"])
        self.assertEqual(payload["event"]["kind"], "task_control_plane")
        self.assertIn("当前有 1 个未闭环事件，其中 1 个为 critical。", payload["human_text"])
        self.assertIn("最近基准：coding-default-core -> 未通过晋升", payload["human_text"])

    def test_main_emit_json_returns_structured_payload(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        consumer_module = load_module(
            "task_output_consumer",
            "scripts/openclaw-ops/task_output_consumer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-consumer-2",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Emit JSON",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "human_confirmed": True,
                        "requirement": "Return structured JSON.",
                        "result_output": "emit-json returns payload",
                        "acceptance": "machine output present",
                        "observable_outputs": "stdout json",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="todo-consumer-2",
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

            with redirect_stdout(StringIO()):
                result = consumer_module.main(
                    [
                        "--db",
                        str(db_path),
                        "--task-id",
                        "todo-consumer-2",
                        "--emit-json",
                    ]
                )

        self.assertEqual(result["task_id"], "todo-consumer-2")
        self.assertEqual(result["event"]["kind"], "task_control_plane")
        self.assertIn("human_text", result)


if __name__ == "__main__":
    unittest.main()

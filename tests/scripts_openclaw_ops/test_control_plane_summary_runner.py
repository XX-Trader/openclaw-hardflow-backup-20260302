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


class ControlPlaneSummaryRunnerTests(unittest.TestCase):
    def test_build_payload_dedupes_same_summary(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        runner_module = load_module(
            "control_plane_summary_runner",
            "scripts/openclaw-ops/control_plane_summary_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            state_path = Path(tmpdir) / "control-plane-summary-state.json"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-summary-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Need operational summary",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "running",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "review",
                        "requirement": "Summarize control plane.",
                        "result_output": "Should aggregate incidents and benchmark vetoes.",
                        "acceptance": "summary visible",
                        "observable_outputs": "control plane summary",
                        "acceptance_thresholds": "visible human summary",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="todo-summary-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工协助",
                    payload={"human_gate": {"requires_human_assistance": True}},
                    actor="backend-dev",
                )
                task_center.record_task_incident(
                    task_id="todo-summary-1",
                    incident_type="stage_contract_failed",
                    severity="critical",
                    status="open",
                    reason="contract_failed",
                    summary="仍需人工复核",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                task_center.record_benchmark_run(
                    task_id="todo-summary-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="summary-benchmark-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    baseline_run_ids=["baseline-1"],
                    candidate_run_ids=["candidate-1"],
                    summary_file="reports/latest-summary.json",
                    scorecard_file="reports/latest-scorecard.json",
                    decision={"promote_to_new_baseline": False, "veto_reasons": ["critical_incidents_present"]},
                    actor="upgrade-feedback-runner",
                )
            finally:
                task_center.close()

            first = runner_module.build_control_plane_summary_payload(
                db_file=db_path,
                state_file=state_path,
                lookback_hours=24,
                limit=10,
                notify_on="error",
            )
            second = runner_module.build_control_plane_summary_payload(
                db_file=db_path,
                state_file=state_path,
                lookback_hours=24,
                limit=10,
                notify_on="error",
            )

        self.assertTrue(first["notify"])
        self.assertEqual(first["summary"]["critical_open_incident_count"], 1)
        self.assertEqual(first["summary"]["benchmark_blocked_count"], 1)
        self.assertIn("critical_incidents_present", first["human_text"])
        self.assertFalse(second["notify"])
        self.assertEqual(second["human_text"], "NO_REPLY")

    def test_main_emit_json_returns_structured_payload(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        runner_module = load_module(
            "control_plane_summary_runner",
            "scripts/openclaw-ops/control_plane_summary_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            state_path = Path(tmpdir) / "control-plane-summary-state.json"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-summary-2",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Need JSON summary",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "docs-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "requirement": "Return structured payload.",
                        "result_output": "emit-json should work.",
                        "acceptance": "structured summary",
                        "observable_outputs": "stdout json",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_benchmark_run(
                    task_id="todo-summary-2",
                    benchmark_suite_id="docs-default-core",
                    benchmark_run_id="summary-benchmark-2",
                    workflow_profile_id="docs-default",
                    workflow_channel="stable",
                    target_kind="workflow",
                    target_id="docs-default",
                    baseline_run_ids=["baseline-1"],
                    candidate_run_ids=["candidate-1"],
                    summary_file="reports/latest-summary.json",
                    scorecard_file="reports/latest-scorecard.json",
                    decision={"promote_to_new_baseline": True, "veto_reasons": []},
                    actor="upgrade-feedback-runner",
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

        self.assertIn("summary", payload)
        self.assertIn("event", payload)
        self.assertIn("human_text", payload)


if __name__ == "__main__":
    unittest.main()

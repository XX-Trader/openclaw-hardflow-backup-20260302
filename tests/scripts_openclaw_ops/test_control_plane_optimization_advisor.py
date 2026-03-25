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


class ControlPlaneOptimizationAdvisorTests(unittest.TestCase):
    def test_build_report_generates_stage_recommendations_and_roi(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        advisor_module = load_module(
            "control_plane_optimization_advisor",
            "scripts/openclaw-ops/control_plane_optimization_advisor.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()

                task_center.create_task(
                    {
                        "task_id": "opt-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "review risky",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "running",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "review",
                        "requirement": "Need stronger review gate",
                        "result_output": "review blocked",
                        "acceptance": "gate recommendation",
                        "observable_outputs": "advisor report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="opt-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工协助",
                    payload={"human_gate": {"requires_human_assistance": True}},
                    actor="backend-dev",
                )
                task_center.record_task_incident(
                    task_id="opt-1",
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
                    task_id="opt-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="opt-bench-1",
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

                for task_id in ("opt-2", "opt-3", "opt-4"):
                    task_center.create_task(
                        {
                            "task_id": task_id,
                            "pool": "todo",
                            "task_type": "workflow",
                            "reason": "draft stable",
                            "source": "unit-test",
                            "priority": "medium",
                            "risk_level": "low",
                            "status": "passed",
                            "workflow_profile_id": "docs-default",
                            "workflow_channel": "stable",
                            "stage_id": "draft",
                            "requirement": "Draft stage looks stable",
                            "result_output": "Can consider simplification",
                            "acceptance": "advisor recommendation",
                            "observable_outputs": "advisor report",
                            "acceptance_thresholds": "ok",
                        },
                        actor="test",
                    )
                    task_center.record_benchmark_run(
                        task_id=task_id,
                        benchmark_suite_id="docs-default-core",
                        benchmark_run_id=f"{task_id}-bench",
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

                task_center.create_task(
                    {
                        "task_id": "opt-5",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "clarify unstable",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "running",
                        "workflow_profile_id": "research-default",
                        "workflow_channel": "candidate",
                        "stage_id": "clarify",
                        "requirement": "Need better clarification",
                        "result_output": "clarify still asks human",
                        "acceptance": "clarification recommendation",
                        "observable_outputs": "advisor report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="opt-5",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="等待补充上下文",
                    payload={"human_gate": {"requires_human_assistance": True}},
                    actor="researcher",
                )
            finally:
                task_center.close()

            report = advisor_module.build_control_plane_optimization_report(
                db_file=db_path,
                lookback_hours=24,
                limit=20,
            )

        recommendation_types = [item["type"] for item in report["recommendations"]]
        self.assertIn("strengthen_stage_gate", recommendation_types)
        self.assertIn("parallelize_stage_candidate", recommendation_types)
        self.assertIn("clarification_upgrade_needed", recommendation_types)
        self.assertNotIn("load_balance_stage_candidate", recommendation_types)
        self.assertIn("roi_snapshot", report)
        self.assertIn("stage_roi_breakdown", report)
        coding_review = next(
            item for item in report["recommendations"] if item["workflow_profile_id"] == "coding-default" and item["stage_id"] == "review"
        )
        self.assertIn("roi_context", coding_review)
        simplification_candidate = next(
            item
            for item in report["recommendations"]
            if item["type"] == "stage_simplification_candidate"
            and item["workflow_profile_id"] == "docs-default"
            and item["stage_id"] == "draft"
        )
        self.assertEqual(simplification_candidate["evidence"]["policy"], "workflow_evolution.stage_simplification.v1")
        self.assertEqual(simplification_candidate["evidence"]["task_count"], 3)
        self.assertEqual(simplification_candidate["evidence"]["benchmark_promoted_count"], 3)
        self.assertIn("# OpenClaw Control Plane Optimization Advisor", report["markdown"])
        self.assertIn("coding-default / 评审", report["markdown"])
        self.assertIn("docs-default / 文档草拟", report["markdown"])
        self.assertIn("## ROI 摘要", report["markdown"])
        self.assertIn("## Stage ROI", report["markdown"])

    def test_main_writes_json_and_markdown_outputs(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        advisor_module = load_module(
            "control_plane_optimization_advisor",
            "scripts/openclaw-ops/control_plane_optimization_advisor.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            json_output = Path(tmpdir) / "advisor.json"
            markdown_output = Path(tmpdir) / "advisor.md"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "opt-main-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "simple stable task",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "ops-default",
                        "workflow_channel": "stable",
                        "stage_id": "verify",
                        "requirement": "write outputs",
                        "result_output": "advisor outputs",
                        "acceptance": "files created",
                        "observable_outputs": "json markdown",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = advisor_module.main(
                    [
                        "--db",
                        str(db_path),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertIn("report", payload)
        self.assertIn("generated_at", json_payload["report"])
        self.assertIn("roi_snapshot", json_payload["report"])
        self.assertIn("stage_roi_breakdown", json_payload["report"])
        self.assertIn("# OpenClaw Control Plane Optimization Advisor", markdown_text)
        self.assertIn("## Stage ROI", markdown_text)


if __name__ == "__main__":
    unittest.main()

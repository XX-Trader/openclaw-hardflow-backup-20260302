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


class ControlPlaneOptimizationReviewRunnerTests(unittest.TestCase):
    def test_build_report_summarizes_ready_blocked_and_pending_tasks(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        review_module = load_module(
            "control_plane_optimization_review_runner",
            "skills/library/control-plane-ops/scripts/control_plane_optimization_review_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-opt-ready",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "ready optimization",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-optimization:ready",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "parallelize_stage_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "recommendation": {
                                "type": "parallelize_stage_candidate",
                                "severity": "medium",
                            },
                        },
                        "requirement": "apply optimization",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-opt-blocked",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "blocked optimization",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "failed",
                        "assignee": "reviewer",
                        "change_id": "control-plane-optimization:blocked",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "strengthen_stage_gate",
                            "target_workflow_profile_id": "coding-default",
                            "target_stage_id": "review",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "coding-default",
                            "target_stage_id": "review",
                            "target_stage_label": "评审",
                            "recommendation": {
                                "type": "strengthen_stage_gate",
                                "severity": "high",
                            },
                        },
                        "requirement": "apply review hardening",
                        "result_output": "blocked",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_incident(
                    task_id="todo-opt-blocked",
                    incident_type="stage_contract_failed",
                    severity="critical",
                    status="open",
                    reason="contract_failed",
                    summary="仍需人工复核",
                    owner="reviewer",
                    details={"source": "unit-test"},
                    actor="reviewer",
                )
                task_center.record_task_output(
                    task_id="todo-opt-blocked",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工协助",
                    payload={"human_gate": {"requires_human_assistance": True}},
                    actor="reviewer",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-opt-pending",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "pending optimization",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "assignee": "project-agent",
                        "change_id": "control-plane-optimization:pending",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "clarify",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "clarification_upgrade_needed",
                            "target_workflow_profile_id": "research-default",
                            "target_stage_id": "clarify",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "research-default",
                            "target_stage_id": "clarify",
                            "target_stage_label": "需求澄清",
                            "recommendation": {
                                "type": "clarification_upgrade_needed",
                                "severity": "high",
                            },
                        },
                        "requirement": "improve clarification",
                        "result_output": "queued",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            report = review_module.build_control_plane_optimization_review_report(
                task_db=db_path,
                lookback_hours=48,
                limit=10,
            )

        self.assertEqual(report["summary"]["task_count"], 3)
        self.assertEqual(report["summary"]["ready_for_profile_update_count"], 1)
        self.assertEqual(report["summary"]["blocked_count"], 1)
        self.assertEqual(report["summary"]["pending_count"], 1)
        self.assertEqual(report["summary"]["status_counts"]["passed"], 1)
        self.assertEqual(report["summary"]["status_counts"]["failed"], 1)
        self.assertEqual(report["summary"]["status_counts"]["pending"], 1)
        self.assertEqual(report["summary"]["recommendation_type_counts"]["parallelize_stage_candidate"], 1)
        ready_item = next(item for item in report["items"] if item["task_id"] == "todo-opt-ready")
        blocked_item = next(item for item in report["items"] if item["task_id"] == "todo-opt-blocked")
        pending_item = next(item for item in report["items"] if item["task_id"] == "todo-opt-pending")
        self.assertTrue(ready_item["ready_for_profile_update"])
        self.assertIn("critical_incidents", blocked_item["blocking_reasons"])
        self.assertIn("requires_human_assistance", blocked_item["blocking_reasons"])
        self.assertIn("pending_execution", pending_item["blocking_reasons"])
        self.assertIn("# OpenClaw Control Plane Optimization Review", report["markdown"])
        self.assertIn("todo-opt-ready", report["markdown"])
        self.assertIn("docs-default / draft", report["markdown"])

    def test_stage_simplification_requires_evidence_guard_before_profile_update(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        review_module = load_module(
            "control_plane_optimization_review_runner",
            "skills/library/control-plane-ops/scripts/control_plane_optimization_review_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-opt-simplify-ready",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "ready simplification optimization",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "low",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-optimization:simplify-ready",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "stage_simplification_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "recommendation": {
                                "type": "stage_simplification_candidate",
                                "severity": "low",
                                "evidence": {
                                    "policy": "workflow_evolution.stage_simplification.v1",
                                    "task_count": 4,
                                    "benchmark_promoted_count": 3,
                                    "open_incident_task_count": 0,
                                    "human_assistance_task_count": 0,
                                    "benchmark_blocked_count": 0,
                                    "waiting_human_confirm_task_count": 0,
                                    "needs_clarification_task_count": 0,
                                },
                            },
                        },
                        "requirement": "evaluate simplification",
                        "result_output": "ready",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-opt-simplify-blocked",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "blocked simplification optimization",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "low",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-optimization:simplify-blocked",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "stage_simplification_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "recommendation": {
                                "type": "stage_simplification_candidate",
                                "severity": "low",
                                "evidence": {
                                    "policy": "workflow_evolution.stage_simplification.v1",
                                    "task_count": 2,
                                    "benchmark_promoted_count": 1,
                                    "open_incident_task_count": 0,
                                    "human_assistance_task_count": 0,
                                    "benchmark_blocked_count": 0,
                                    "waiting_human_confirm_task_count": 0,
                                    "needs_clarification_task_count": 0,
                                },
                            },
                        },
                        "requirement": "evaluate simplification",
                        "result_output": "blocked",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            report = review_module.build_control_plane_optimization_review_report(
                task_db=db_path,
                lookback_hours=48,
                limit=10,
            )

        ready_item = next(item for item in report["items"] if item["task_id"] == "todo-opt-simplify-ready")
        blocked_item = next(item for item in report["items"] if item["task_id"] == "todo-opt-simplify-blocked")
        self.assertTrue(ready_item["ready_for_profile_update"])
        self.assertTrue(ready_item["profile_update_guard"]["ready"])
        self.assertEqual(ready_item["evidence_snapshot"]["task_count"], 4)
        self.assertFalse(blocked_item["ready_for_profile_update"])
        self.assertFalse(blocked_item["profile_update_guard"]["ready"])
        self.assertIn("insufficient_simplification_task_count", blocked_item["blocking_reasons"])
        self.assertIn("insufficient_simplification_benchmark_promotions", blocked_item["blocking_reasons"])

    def test_main_writes_json_and_markdown_outputs(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        review_module = load_module(
            "control_plane_optimization_review_runner",
            "skills/library/control-plane-ops/scripts/control_plane_optimization_review_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            json_output = Path(tmpdir) / "optimization-review.json"
            markdown_output = Path(tmpdir) / "optimization-review.md"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-opt-cli",
                        "pool": "todo",
                        "task_type": "workflow_optimization",
                        "reason": "cli output",
                        "source": "control-plane-optimization-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-optimization:cli",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_optimization_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "stage_simplification_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "recommendation": {
                                "type": "stage_simplification_candidate",
                                "severity": "low",
                            },
                        },
                        "requirement": "review output",
                        "result_output": "report",
                        "acceptance": "ok",
                        "observable_outputs": "report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = review_module.main(
                    [
                        "--task-db",
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
        self.assertEqual(json_payload["report"]["summary"]["task_count"], 1)
        self.assertIn("# OpenClaw Control Plane Optimization Review", markdown_text)


if __name__ == "__main__":
    unittest.main()

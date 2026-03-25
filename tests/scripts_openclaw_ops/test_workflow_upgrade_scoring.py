import importlib.util
import json
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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkflowUpgradeScoringTests(unittest.TestCase):
    def test_build_workflow_upgrade_scorecard_detects_runtime_gap_and_positive_delta(self):
        module = load_module(
            "workflow_upgrade_scoring",
            "scripts/openclaw-ops/workflow_upgrade_scoring.py",
        )

        baseline_payload = {
            "run_id": "exec-baseline-1",
            "started_at": "2026-03-21T10:00:00+00:00",
            "finished_at": "2026-03-21T10:10:00+00:00",
            "tasks_selected": 3,
            "tasks_executed": 2,
            "tasks_skipped": 1,
            "tasks_failed": 2,
            "preflight_warning_tasks": 1,
            "preflight_blocked_tasks": 1,
            "results": [
                {
                    "task_id": "todo-1",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "failed",
                    "report_status": "failed",
                    "reason": "call_agent_exception:timeout",
                    "quality_score": 46,
                    "solved": False,
                    "resolution_summary": "gateway timeout",
                    "duration_ms": 13600,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
                {
                    "task_id": "todo-2",
                    "task_type": "governance_evolution_context_preflight",
                    "assignee": "project-agent",
                    "status": "failed",
                    "task_status_after": "failed",
                    "report_status": "failed",
                    "reason": "preflight_strict_blocked",
                    "quality_score": 0,
                    "solved": False,
                    "resolution_summary": "manifest mismatch",
                },
                {
                    "task_id": "todo-3",
                    "task_type": "governance_evolution_review",
                    "assignee": "reviewer",
                    "status": "executed",
                    "task_status_after": "partial",
                    "report_status": "partial",
                    "reason": "report_failed:timeout",
                    "quality_score": 58,
                    "solved": False,
                    "resolution_summary": "writeback timeout",
                    "duration_ms": 9200,
                    "input_tokens": 1800,
                    "output_tokens": 120,
                },
            ],
        }
        candidate_payload = {
            "run_id": "exec-candidate-1",
            "started_at": "2026-03-22T10:00:00+00:00",
            "finished_at": "2026-03-22T10:09:00+00:00",
            "tasks_selected": 3,
            "tasks_executed": 3,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-1",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 91,
                    "solved": True,
                    "resolution_summary": "optimization complete",
                    "duration_ms": 8400,
                    "input_tokens": 2100,
                    "output_tokens": 380,
                },
                {
                    "task_id": "todo-2",
                    "task_type": "governance_evolution_context_preflight",
                    "assignee": "project-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 88,
                    "solved": True,
                    "resolution_summary": "context prepared",
                    "duration_ms": 6000,
                    "input_tokens": 900,
                    "output_tokens": 220,
                },
                {
                    "task_id": "todo-3",
                    "task_type": "governance_evolution_review",
                    "assignee": "reviewer",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 90,
                    "solved": True,
                    "resolution_summary": "review closed",
                    "duration_ms": 7200,
                    "input_tokens": 1100,
                    "output_tokens": 260,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            baseline_file = tmp / "baseline.json"
            candidate_file = tmp / "candidate.json"
            write_json(baseline_file, baseline_payload)
            write_json(candidate_file, candidate_payload)

            scorecard = module.build_workflow_upgrade_scorecard(
                baseline_inputs=[baseline_file],
                candidate_inputs=[candidate_file],
                target_name="task_executor_10m",
            )

        self.assertEqual(scorecard["upgrade_type"], "workflow")
        self.assertEqual(scorecard["target_name"], "task_executor_10m")
        self.assertEqual(scorecard["classification"]["root_cause_type"], "runtime_gap")
        self.assertIn(
            "scripts/openclaw-ops/install_workflow_profile.py",
            scorecard["classification"]["minimal_writable_surface"],
        )
        self.assertGreater(
            scorecard["candidate_score"]["execution_stability"],
            scorecard["baseline_score"]["execution_stability"],
        )
        self.assertGreater(scorecard["delta"]["closure_rate"], 0)
        self.assertGreater(scorecard["delta"]["runtime_drift_control"], 0)
        self.assertTrue(scorecard["decision"]["promote_to_new_baseline"])
        self.assertTrue(scorecard["top_regressions"])
        self.assertTrue(scorecard["top_improvements"])

    def test_build_workflow_upgrade_scorecard_counts_stage_contract_failures(self):
        module = load_module(
            "workflow_upgrade_scoring",
            "scripts/openclaw-ops/workflow_upgrade_scoring.py",
        )

        baseline_payload = {
            "run_id": "exec-baseline-stage-contract",
            "started_at": "2026-03-21T11:00:00+00:00",
            "finished_at": "2026-03-21T11:05:00+00:00",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "tasks_failed": 1,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-stage-contract-1",
                    "task_type": "workflow",
                    "assignee": "backend-dev",
                    "status": "executed",
                    "task_status_after": "running",
                    "report_status": "partial",
                    "reason": "stage_contract_failed",
                    "quality_score": 69,
                    "solved": False,
                    "resolution_summary": "Implemented API fix.",
                    "stage_contract": {
                        "contract_passed": False,
                        "missing_deliverables": ["verification_result"],
                        "failed_checks": ["tests_or_validation_recorded"],
                    },
                }
            ],
        }
        candidate_payload = {
            "run_id": "exec-candidate-stage-contract",
            "started_at": "2026-03-22T11:00:00+00:00",
            "finished_at": "2026-03-22T11:05:00+00:00",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-stage-contract-1",
                    "task_type": "workflow",
                    "assignee": "backend-dev",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 91,
                    "solved": True,
                    "resolution_summary": "Implemented API fix and ran pytest -q.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            baseline_file = tmp / "baseline-stage-contract.json"
            candidate_file = tmp / "candidate-stage-contract.json"
            write_json(baseline_file, baseline_payload)
            write_json(candidate_file, candidate_payload)

            scorecard = module.build_workflow_upgrade_scorecard(
                baseline_inputs=[baseline_file],
                candidate_inputs=[candidate_file],
                target_name="task_executor_10m",
            )

        self.assertEqual(scorecard["baseline_metrics"]["stage_contract_failure_count"], 1)
        self.assertEqual(scorecard["baseline_metrics"]["failure_reason_counter"]["stage_contract_failed"], 1)
        self.assertGreater(scorecard["delta"]["execution_stability"], 0)

    def test_build_workflow_upgrade_scorecard_vetoes_promotion_on_human_assistance_incident(self):
        module = load_module(
            "workflow_upgrade_scoring",
            "scripts/openclaw-ops/workflow_upgrade_scoring.py",
        )

        baseline_payload = {
            "run_id": "exec-baseline-human-gate",
            "started_at": "2026-03-21T12:00:00+00:00",
            "finished_at": "2026-03-21T12:06:00+00:00",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-human-gate-1",
                    "task_type": "workflow",
                    "assignee": "backend-dev",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 88,
                    "solved": True,
                    "resolution_summary": "Implemented and verified change.",
                }
            ],
        }
        candidate_payload = {
            "run_id": "exec-candidate-human-gate",
            "started_at": "2026-03-22T12:00:00+00:00",
            "finished_at": "2026-03-22T12:05:00+00:00",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-human-gate-1",
                    "task_type": "workflow",
                    "assignee": "backend-dev",
                    "status": "executed",
                    "task_status_after": "escalated",
                    "report_status": "escalated",
                    "reason": "escalate_human",
                    "quality_score": 93,
                    "solved": False,
                    "resolution_summary": "需要人工确认发布窗口。",
                    "human_gate": {
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "needs_clarification": False,
                        "requires_human_assistance": True,
                    },
                    "incident": {
                        "incident_type": "task_escalated",
                        "severity": "critical",
                        "status": "open",
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            baseline_file = tmp / "baseline-human-gate.json"
            candidate_file = tmp / "candidate-human-gate.json"
            write_json(baseline_file, baseline_payload)
            write_json(candidate_file, candidate_payload)

            scorecard = module.build_workflow_upgrade_scorecard(
                baseline_inputs=[baseline_file],
                candidate_inputs=[candidate_file],
                target_name="task_executor_10m",
            )

        self.assertEqual(scorecard["candidate_metrics"]["human_assistance_count"], 1)
        self.assertEqual(scorecard["candidate_metrics"]["critical_incident_count"], 1)
        self.assertFalse(scorecard["decision"]["promote_to_new_baseline"])
        self.assertIn("critical_incidents_present", scorecard["decision"]["veto_reasons"])


if __name__ == "__main__":
    unittest.main()

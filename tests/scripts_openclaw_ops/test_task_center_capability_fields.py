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


class TaskCenterCapabilityFieldTests(unittest.TestCase):
    def test_create_and_update_task_normalize_capability_fields(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                created = task_center.create_task(
                    {
                        "task_id": "todo-capability-1",
                        "pool": "todo",
                        "task_type": "capability_validation",
                        "reason": "Validate capability fields",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "high",
                        "assignee": "coordinator",
                        "status": "pending",
                        "requirement": "Store task capability metadata.",
                        "result_output": "Persisted task payload.",
                        "acceptance": "Capability fields are normalized.",
                        "observable_outputs": "task_center row",
                        "acceptance_thresholds": "required_capabilities and required_skills are lists",
                        "required_capabilities": ["task_execution", "task_execution", "routing"],
                        "required_skills": "requirements-clarity, task-decomposer",
                        "allowed_agents": ("coordinator", "main", "coordinator"),
                        "stage_id": "implement",
                        "stage_score_gate": "backend",
                        "stage_min_evidence_count": 3,
                        "stage_output_contract": {
                            "deliverables": ["code_changes", "verification_result"],
                            "observable_outputs": ["diff summary", "test evidence"],
                        },
                        "stage_verification_contract": {
                            "checks": ["tests_or_validation_recorded"],
                        },
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "selection_reason": "default_coding_workflow_for_execution",
                        "selection_inputs": {"task_type": "workflow", "request_source": "human"},
                    },
                    actor="test",
                )

                updated = task_center.update_task(
                    "todo-capability-1",
                    actor="test",
                    fields={
                        "required_capabilities": "project_context, routing",
                        "required_skills": ["smart-workflow", "smart-workflow", "requirements-clarity"],
                        "allowed_agents": "project-agent, coordinator",
                        "stage_id": "review",
                        "stage_score_gate": "final",
                        "stage_min_evidence_count": 2,
                        "stage_output_contract": {"deliverables": ["review_decision"]},
                        "stage_verification_contract": {"checks": ["review_completed"]},
                        "workflow_channel": "candidate",
                        "selection_reason": "benchmark_candidate_upgrade",
                        "selection_inputs": {"task_type": "workflow", "channel": "candidate"},
                    },
                )
                selection = task_center.get_workflow_selection_record("todo-capability-1")
            finally:
                task_center.close()

        self.assertEqual(created["required_capabilities"], ["task_execution", "routing"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertEqual(created["allowed_agents"], ["coordinator", "main"])
        self.assertEqual(created["stage_id"], "implement")
        self.assertEqual(created["stage_score_gate"], "backend")
        self.assertEqual(created["stage_min_evidence_count"], 3)
        self.assertEqual(created["stage_output_contract"]["deliverables"], ["code_changes", "verification_result"])
        self.assertEqual(created["stage_verification_contract"]["checks"], ["tests_or_validation_recorded"])
        self.assertEqual(created["workflow_profile_id"], "coding-default")
        self.assertEqual(created["workflow_channel"], "stable")
        self.assertEqual(created["selection_reason"], "default_coding_workflow_for_execution")
        self.assertEqual(created["selection_inputs"]["request_source"], "human")
        self.assertEqual(updated["required_capabilities"], ["project_context", "routing"])
        self.assertEqual(updated["required_skills"], ["smart-workflow", "requirements-clarity"])
        self.assertEqual(updated["allowed_agents"], ["project-agent", "coordinator"])
        self.assertEqual(updated["stage_id"], "review")
        self.assertEqual(updated["stage_score_gate"], "final")
        self.assertEqual(updated["stage_min_evidence_count"], 2)
        self.assertEqual(updated["stage_output_contract"]["deliverables"], ["review_decision"])
        self.assertEqual(updated["stage_verification_contract"]["checks"], ["review_completed"])
        self.assertEqual(updated["workflow_channel"], "candidate")
        self.assertEqual(updated["selection_reason"], "benchmark_candidate_upgrade")
        self.assertEqual(updated["selection_inputs"]["channel"], "candidate")
        self.assertEqual(selection["workflow_profile_id"], "coding-default")
        self.assertEqual(selection["workflow_channel"], "candidate")
        self.assertEqual(selection["selection_reason"], "benchmark_candidate_upgrade")
        self.assertTrue(str(created["trace_id"]).startswith("trace-"))
        self.assertEqual(created["attempt_id"], "attempt-001")
        self.assertEqual(updated["trace_id"], created["trace_id"])
        self.assertEqual(updated["attempt_id"], "attempt-001")

    def test_record_and_list_benchmark_runs(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-benchmark-1",
                        "pool": "todo",
                        "task_type": "workflow_upgrade",
                        "reason": "Record benchmark run",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "coordinator",
                        "status": "pending",
                        "requirement": "Persist benchmark run metadata.",
                        "result_output": "Benchmark run stored.",
                        "acceptance": "Benchmark run can be queried.",
                        "observable_outputs": "benchmark run row",
                        "acceptance_thresholds": "benchmark_run is queryable",
                    },
                    actor="test",
                )
                recorded = task_center.record_benchmark_run(
                    task_id="todo-benchmark-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="benchmark-run-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    baseline_run_ids=["exec-baseline-1", "exec-baseline-2"],
                    candidate_run_ids=["exec-candidate-1", "exec-candidate-2"],
                    summary_file="reports/latest-summary.json",
                    scorecard_file="reports/latest-workflow-scorecard.json",
                    decision={"promote_to_new_baseline": False, "veto_reasons": ["critical_incidents_present"]},
                    actor="upgrade-feedback-runner",
                )
                listed = task_center.list_benchmark_runs("todo-benchmark-1", display_safe=False)
            finally:
                task_center.close()

        self.assertEqual(recorded["benchmark_suite_id"], "coding-default-core")
        self.assertEqual(recorded["workflow_profile_id"], "coding-default")
        self.assertEqual(recorded["workflow_channel"], "candidate")
        self.assertEqual(recorded["target_kind"], "workflow")
        self.assertEqual(recorded["target_id"], "coding-default")
        self.assertEqual(recorded["baseline_run_ids"], ["exec-baseline-1", "exec-baseline-2"])
        self.assertEqual(recorded["candidate_run_ids"], ["exec-candidate-1", "exec-candidate-2"])
        self.assertEqual(recorded["decision"]["veto_reasons"], ["critical_incidents_present"])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["benchmark_run_id"], "benchmark-run-1")
        self.assertEqual(recorded["trace_id"], listed[0]["trace_id"])
        self.assertTrue(str(recorded["trace_id"]).startswith("trace-"))

    def test_update_task_incident_supports_lifecycle_transitions(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-incident-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Track incident lifecycle",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "high",
                        "assignee": "coordinator",
                        "status": "running",
                        "requirement": "Need ack/resolved incident lifecycle.",
                        "result_output": "Incident can be updated.",
                        "acceptance": "Incident status changes are persisted.",
                        "observable_outputs": "task_incidents row",
                        "acceptance_thresholds": "acked then resolved",
                    },
                    actor="test",
                )
                incident = task_center.record_task_incident(
                    task_id="todo-incident-1",
                    incident_type="task_escalated",
                    severity="critical",
                    status="open",
                    reason="needs_handoff",
                    summary="Need manual help",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                acked = task_center.update_task_incident(
                    int(incident["id"]),
                    status="acked",
                    summary="已确认处理中",
                    details={"operator_note": "triaged"},
                    actor="coordinator",
                )
                resolved = task_center.update_task_incident(
                    int(incident["id"]),
                    status="resolved",
                    reason="manual_fix_done",
                    actor="coordinator",
                )
            finally:
                task_center.close()

        self.assertEqual(acked["status"], "acked")
        self.assertEqual(acked["summary"], "已确认处理中")
        self.assertEqual(acked["details"]["operator_note"], "triaged")
        self.assertEqual(acked["details"]["last_status_updated_by"], "coordinator")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["reason"], "manual_fix_done")
        self.assertEqual(resolved["details"]["last_status_updated_by"], "coordinator")
        self.assertTrue(str(incident["trace_id"]).startswith("trace-"))
        self.assertEqual(incident["trace_id"], acked["trace_id"])
        self.assertEqual(incident["trace_id"], resolved["trace_id"])

    def test_task_output_incident_and_benchmark_inherit_task_trace_id(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                created = task_center.create_task(
                    {
                        "task_id": "todo-trace-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "trace propagation regression",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "backend-dev",
                        "status": "running",
                        "requirement": "trace_id should propagate to control-plane records.",
                        "result_output": "trace chain stored.",
                        "acceptance": "outputs incidents and benchmark share one trace_id.",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "same trace_id",
                    },
                    actor="test",
                )
                output = task_center.record_task_output(
                    task_id="todo-trace-1",
                    output_type="agent_report",
                    audience="human",
                    status="prepared",
                    summary="trace output",
                    payload={"summary": "ok"},
                    actor="backend-dev",
                )
                incident = task_center.record_task_incident(
                    task_id="todo-trace-1",
                    incident_type="needs_clarification",
                    severity="warning",
                    status="open",
                    summary="trace incident",
                    actor="backend-dev",
                )
                benchmark = task_center.record_benchmark_run(
                    task_id="todo-trace-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="trace-benchmark-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    actor="benchmark-runner",
                )
                report = task_center.task_report("todo-trace-1", display_safe=False)
            finally:
                task_center.close()

        self.assertEqual(output["trace_id"], created["trace_id"])
        self.assertEqual(incident["trace_id"], created["trace_id"])
        self.assertEqual(benchmark["trace_id"], created["trace_id"])
        self.assertEqual(output["payload"]["attempt_id"], created["attempt_id"])
        self.assertEqual(incident["details"]["attempt_id"], created["attempt_id"])
        self.assertEqual(benchmark["details"]["attempt_id"], created["attempt_id"])
        self.assertEqual(
            output["payload"]["execution_envelope"]["trace_id"],
            created["trace_id"],
        )
        self.assertEqual(
            incident["details"]["execution_envelope"]["task_id"],
            "todo-trace-1",
        )
        self.assertEqual(
            benchmark["details"]["execution_envelope"]["attempt_id"],
            created["attempt_id"],
        )
        self.assertEqual(report["trace_id"], created["trace_id"])
        self.assertEqual(report["attempt_id"], created["attempt_id"])
        self.assertEqual(report["execution_envelope"]["trace_id"], created["trace_id"])
        self.assertEqual(report["task_outputs"][0]["trace_id"], created["trace_id"])
        self.assertEqual(report["task_incidents"][0]["trace_id"], created["trace_id"])
        self.assertEqual(report["benchmark_runs"][0]["trace_id"], created["trace_id"])
        self.assertEqual(
            report["task_outputs"][0]["payload"]["execution_envelope"]["task"]["task_type"],
            "workflow",
        )
        self.assertEqual(
            report["task_incidents"][0]["details"]["execution_envelope"]["task_id"],
            "todo-trace-1",
        )
        self.assertEqual(
            report["benchmark_runs"][0]["details"]["execution_envelope"]["trace_id"],
            created["trace_id"],
        )


if __name__ == "__main__":
    unittest.main()

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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ControlPlaneProfileUpdateApplierTests(unittest.TestCase):
    def _registry_payload(self) -> dict:
        return {
            "schema_version": "2026-03-22",
            "default_profile_id": "coding-default",
            "default_channel": "stable",
            "profiles": [
                {
                    "profile_id": "docs-default",
                    "channel": "stable",
                    "enabled": True,
                    "version": "stable-v1",
                    "default_stage_id": "draft",
                    "stages": [
                        {
                            "stage_id": "draft",
                            "display_name": "文档草拟",
                            "score_gate": "solution",
                            "min_evidence_count": 2,
                            "output_contract": {"deliverables": ["document_draft"]},
                            "verification_contract": {"checks": ["review_completed"]},
                        }
                    ],
                },
                {
                    "profile_id": "docs-default",
                    "channel": "candidate",
                    "enabled": True,
                    "version": "candidate-v1",
                    "default_stage_id": "draft",
                    "stages": [
                        {
                            "stage_id": "draft",
                            "display_name": "文档草拟",
                            "score_gate": "solution",
                            "min_evidence_count": 2,
                            "output_contract": {"deliverables": ["document_draft"]},
                            "verification_contract": {"checks": ["review_completed"]},
                        }
                    ],
                },
            ],
            "profile_update_history": [
                {
                    "change_id": "control-plane-profile-update:control-plane-optimization:duplicate",
                    "task_id": "todo-existing-applied",
                }
            ],
        }

    def test_apply_profile_updates_mutates_candidate_registry_and_skips_duplicates(self):
        applier_module = load_module(
            "control_plane_profile_update_applier",
            "skills/library/control-plane-ops/scripts/control_plane_profile_update_applier.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "workflow-profile-registry.json"
            task_db = Path(tmpdir) / "task_center.db"
            write_json(registry_file, self._registry_payload())

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-ready",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "ready profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:ready",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "strengthen_stage_gate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "review_item": {
                                "task_id": "todo-opt-ready",
                                "recommendation_type": "strengthen_stage_gate",
                            },
                        },
                        "requirement": "apply profile update",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-load-balance",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "deprecated load balance profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:load-balance",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "load_balance_stage_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                        },
                        "requirement": "deprecated load balance patch should be skipped",
                        "result_output": "skip",
                        "acceptance": "deprecated recommendation is ignored",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-duplicate",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "duplicate profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:duplicate",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "parallelize_stage_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                        },
                        "requirement": "duplicate",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-blocked",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "blocked profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "passed",
                        "assignee": "reviewer",
                        "change_id": "control-plane-profile-update:control-plane-optimization:blocked",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "clarification_upgrade_needed",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                        },
                        "requirement": "blocked",
                        "result_output": "blocked",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.record_task_incident(
                    task_id="todo-profile-update-blocked",
                    incident_type="profile_update_blocked",
                    severity="critical",
                    status="open",
                    reason="critical_incident",
                    summary="仍有阻塞 incident",
                    owner="reviewer",
                    details={"source": "unit-test"},
                    actor="reviewer",
                )
            finally:
                task_center.close()

            result = applier_module.apply_control_plane_profile_updates(
                task_db=task_db,
                registry_file=registry_file,
                lookback_hours=72,
                limit=20,
                target_channel="candidate",
            )
            updated_registry = json.loads(registry_file.read_text(encoding="utf-8"))

        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(result["skipped_count"], 3)
        self.assertEqual(
            {item["task_id"] for item in result["applied"]},
            {"todo-profile-update-ready"},
        )
        stage = updated_registry["profiles"][1]["stages"][0]
        self.assertEqual(stage["min_evidence_count"], 3)
        self.assertEqual(stage["optimization_hints"]["strengthen_stage_gate"]["source_task_id"], "todo-profile-update-ready")
        skipped = {item["task_id"]: item["reason"] for item in result["skipped"]}
        self.assertEqual(skipped["todo-profile-update-load-balance"], "deprecated_recommendation_type")
        self.assertEqual(skipped["todo-profile-update-duplicate"], "duplicate_applied_change_id")
        self.assertEqual(skipped["todo-profile-update-blocked"], "control_plane_gate_blocked")
        self.assertEqual(len(updated_registry["profile_update_history"]), 2)
        self.assertIn("# OpenClaw Control Plane Profile Update Apply", result["markdown"])

    def test_main_writes_json_and_markdown_outputs(self):
        applier_module = load_module(
            "control_plane_profile_update_applier",
            "skills/library/control-plane-ops/scripts/control_plane_profile_update_applier.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "workflow-profile-registry.json"
            task_db = Path(tmpdir) / "task_center.db"
            json_output = Path(tmpdir) / "apply.json"
            markdown_output = Path(tmpdir) / "apply.md"
            write_json(registry_file, self._registry_payload())

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-cli",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "cli profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "low",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:cli",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "parallelize_stage_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                        },
                        "requirement": "apply",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = applier_module.main(
                    [
                        "--task-db",
                        str(task_db),
                        "--registry-file",
                        str(registry_file),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertIn("result", payload)
        self.assertEqual(json_payload["result"]["applied_count"], 1)
        self.assertIn("# OpenClaw Control Plane Profile Update Apply", markdown_text)

    def test_stage_simplification_requires_profile_update_guard(self):
        applier_module = load_module(
            "control_plane_profile_update_applier",
            "skills/library/control-plane-ops/scripts/control_plane_profile_update_applier.py",
        )
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "workflow-profile-registry.json"
            task_db = Path(tmpdir) / "task_center.db"
            write_json(registry_file, self._registry_payload())

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-simplify-ready",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "ready simplification profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "low",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:simplify-ready",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "stage_simplification_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "review_item": {
                                "task_id": "todo-opt-simplify-ready",
                                "recommendation_type": "stage_simplification_candidate",
                                "profile_update_guard": {
                                    "policy": "workflow_evolution.stage_simplification.v1",
                                    "ready": True,
                                    "reasons": [],
                                },
                                "evidence_snapshot": {
                                    "task_count": 4,
                                    "benchmark_promoted_count": 3,
                                },
                            },
                        },
                        "requirement": "apply simplification candidate",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-profile-update-simplify-blocked",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "blocked simplification profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "low",
                        "risk_level": "low",
                        "status": "passed",
                        "assignee": "backend-dev",
                        "change_id": "control-plane-profile-update:control-plane-optimization:simplify-blocked",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "implement",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "recommendation_type": "stage_simplification_candidate",
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                        },
                        "context_payload": {
                            "target_workflow_profile_id": "docs-default",
                            "target_stage_id": "draft",
                            "target_stage_label": "文档草拟",
                            "review_item": {
                                "task_id": "todo-opt-simplify-blocked",
                                "recommendation_type": "stage_simplification_candidate",
                                "profile_update_guard": {
                                    "policy": "workflow_evolution.stage_simplification.v1",
                                    "ready": False,
                                    "reasons": ["insufficient_simplification_task_count"],
                                },
                                "evidence_snapshot": {
                                    "task_count": 2,
                                    "benchmark_promoted_count": 1,
                                },
                            },
                        },
                        "requirement": "blocked simplification candidate",
                        "result_output": "done",
                        "acceptance": "ok",
                        "observable_outputs": "task report",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            result = applier_module.apply_control_plane_profile_updates(
                task_db=task_db,
                registry_file=registry_file,
                lookback_hours=72,
                limit=20,
                target_channel="candidate",
            )
            updated_registry = json.loads(registry_file.read_text(encoding="utf-8"))

        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["applied"][0]["task_id"], "todo-profile-update-simplify-ready")
        skipped = {item["task_id"]: item for item in result["skipped"]}
        self.assertEqual(skipped["todo-profile-update-simplify-blocked"]["reason"], "profile_update_guard_not_ready")
        self.assertIn("insufficient_simplification_task_count", skipped["todo-profile-update-simplify-blocked"]["blocking_reasons"])
        stage = updated_registry["profiles"][1]["stages"][0]
        self.assertEqual(stage["simplification_hint"]["mode"], "candidate")
        self.assertEqual(stage["simplification_hint"]["deletion_mode"], "suggest_only")
        self.assertEqual(stage["simplification_hint"]["evidence_snapshot"]["task_count"], 4)


if __name__ == "__main__":
    unittest.main()

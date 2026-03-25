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


class TaskExecutorPreflightTests(unittest.TestCase):
    def test_preflight_warn_only_detects_skill_and_agent_mismatch(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_file = Path(tmpdir) / "agent_capability_manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "agents": [
                            {
                                "agent_id": "coordinator",
                                "declared_skills": ["task-decomposer", "requirements-clarity"],
                                "capability_mode": "skill_backed",
                            },
                            {
                                "agent_id": "backend-dev",
                                "declared_skills": ["feature-development"],
                                "capability_mode": "skill_backed",
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            capability_index = module.load_agent_capability_index(manifest_file)

        preflight = module.build_task_preflight(
            {
                "assignee": "backend-dev",
                "required_skills": ["task-decomposer"],
                "required_capabilities": ["project_context"],
                "allowed_agents": ["coordinator"],
            },
            capability_index,
        )

        self.assertFalse(preflight["ok"])
        self.assertEqual(preflight["assignee"], "backend-dev")
        self.assertEqual(preflight["missing_skills"], ["task-decomposer"])
        self.assertEqual(preflight["missing_capabilities"], ["project_context"])
        self.assertIn("assignee_not_allowed", preflight["warnings"])
        self.assertIn("required_skills_unmet", preflight["warnings"])
        self.assertIn("required_capabilities_unmet", preflight["warnings"])

    def test_preflight_passes_when_constraints_match(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        capability_index = {
            "coordinator": {
                "agent_id": "coordinator",
                "declared_skills": ["task-decomposer", "requirements-clarity"],
                "capability_mode": "skill_backed",
                "declared_runtime": ["task-center", "skills"],
                "available_tools": ["filesystem", "shell"],
            }
        }
        preflight = module.build_task_preflight(
            {
                "assignee": "coordinator",
                "required_skills": ["task-decomposer"],
                "required_capabilities": ["skill_backed"],
                "allowed_agents": ["coordinator", "main"],
                "stage_id": "implement",
                "stage_score_gate": "backend",
                "stage_min_evidence_count": 3,
                "stage_output_contract": {"deliverables": ["code_changes", "verification_result"]},
                "stage_verification_contract": {"checks": ["tests_or_validation_recorded"]},
                "workflow_profile_id": "coding-default",
                "workflow_channel": "stable",
                "trace_id": "trace-test-001",
                "attempt_id": "attempt-003",
                "selection_reason": "default_coding_workflow_for_execution",
                "selection_inputs": {
                    "task_type": "workflow",
                    "execution_envelope": {
                        "trace_id": "trace-test-001",
                        "attempt_id": "attempt-003",
                        "workflow": {"profile_id": "coding-default", "channel": "stable", "stage_id": "implement"},
                    },
                    "capability_binding": {
                        "required_runtime": ["task-center", "skills"],
                        "tool_requirements": ["filesystem", "shell"],
                        "resolved_assignee": "coordinator",
                        "resolved_agent_profile": {
                            "agent_id": "coordinator",
                            "required_capabilities": ["skill_backed"],
                            "required_skills": ["requirements-clarity", "task-decomposer"],
                            "allowed_agents": ["coordinator"],
                        },
                        "capability_declarations": [
                            {
                                "capability_id": "skill_backed",
                                "owner_domain": "workflow",
                                "default_agent": "coordinator",
                                "required_runtime": ["task-center", "skills"],
                                "tool_requirements": [],
                            },
                            {
                                "capability_id": "task_execution",
                                "owner_domain": "execution",
                                "default_agent": "backend-dev",
                                "required_runtime": ["task-center"],
                                "tool_requirements": ["filesystem", "shell"],
                            },
                        ],
                        "capability_contracts": {
                            "input_contracts": ["skill contract"],
                            "output_contracts": ["execution output"],
                            "verification_contracts": ["verification contract"],
                            "failure_modes": ["required_skills_unmet"],
                            "owner_domains": ["workflow", "execution"],
                        },
                    },
                },
            },
            capability_index,
        )

        self.assertTrue(preflight["ok"])
        self.assertEqual(preflight["warnings"], [])
        self.assertEqual(preflight["missing_skills"], [])
        self.assertEqual(preflight["missing_capabilities"], [])
        self.assertEqual(preflight["stage_id"], "implement")
        self.assertEqual(preflight["stage_score_gate"], "backend")
        self.assertEqual(preflight["stage_min_evidence_count"], 3)
        self.assertEqual(preflight["stage_output_contract"]["deliverables"], ["code_changes", "verification_result"])
        self.assertEqual(preflight["stage_verification_contract"]["checks"], ["tests_or_validation_recorded"])
        self.assertEqual(preflight["workflow_profile_id"], "coding-default")
        self.assertEqual(preflight["workflow_channel"], "stable")
        self.assertEqual(preflight["selection_reason"], "default_coding_workflow_for_execution")
        self.assertEqual(preflight["selection_inputs"]["task_type"], "workflow")
        self.assertEqual(preflight["trace_id"], "trace-test-001")
        self.assertEqual(preflight["attempt_id"], "attempt-003")
        self.assertEqual(preflight["execution_envelope"]["trace_id"], "trace-test-001")
        self.assertEqual(preflight["execution_envelope"]["attempt_id"], "attempt-003")
        self.assertEqual(preflight["execution_envelope"]["workflow"]["profile_id"], "coding-default")
        self.assertEqual(preflight["resolved_assignee"], "coordinator")
        self.assertEqual(preflight["resolved_agent_profile"]["agent_id"], "coordinator")
        self.assertEqual(len(preflight["capability_declarations"]), 2)
        self.assertEqual(
            preflight["capability_contracts"]["owner_domains"],
            ["workflow", "execution"],
        )
        self.assertEqual(
            preflight["execution_envelope"]["capability_binding"]["resolved_agent_profile"]["agent_id"],
            "coordinator",
        )
        self.assertEqual(preflight["required_runtime"], ["task-center", "skills"])
        self.assertEqual(preflight["tool_requirements"], ["filesystem", "shell"])
        self.assertEqual(preflight["missing_runtime_requirements"], [])
        self.assertEqual(preflight["missing_tool_requirements"], [])

    def test_preflight_warns_when_runtime_or_tools_missing(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        capability_index = {
            "backend-dev": {
                "agent_id": "backend-dev",
                "declared_skills": ["feature-development"],
                "capability_mode": "skill_backed",
                "declared_runtime": ["task-center"],
                "available_tools": ["filesystem"],
            }
        }
        preflight = module.build_task_preflight(
            {
                "assignee": "backend-dev",
                "required_skills": ["feature-development"],
                "required_capabilities": ["skill_backed"],
                "allowed_agents": ["backend-dev"],
                "selection_inputs": {
                    "capability_binding": {
                        "required_runtime": ["task-center", "skills"],
                        "tool_requirements": ["filesystem", "shell"],
                    }
                },
            },
            capability_index,
        )

        self.assertFalse(preflight["ok"])
        self.assertEqual(preflight["required_runtime"], ["task-center", "skills"])
        self.assertEqual(preflight["tool_requirements"], ["filesystem", "shell"])
        self.assertEqual(preflight["missing_runtime_requirements"], ["skills"])
        self.assertEqual(preflight["missing_tool_requirements"], ["shell"])
        self.assertIn("required_runtime_unmet", preflight["warnings"])
        self.assertIn("tool_requirements_unmet", preflight["warnings"])

    def test_preflight_exposes_stage_context_gate_and_execution_hints(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        capability_index = {
            "backend-dev": {
                "agent_id": "backend-dev",
                "declared_skills": ["feature-development"],
                "capability_mode": "skill_backed",
                "declared_runtime": ["task-center"],
                "available_tools": ["filesystem", "shell"],
            }
        }
        preflight = module.build_task_preflight(
            {
                "assignee": "backend-dev",
                "required_skills": ["feature-development"],
                "required_capabilities": ["skill_backed"],
                "allowed_agents": ["backend-dev"],
                "selection_inputs": {
                    "capability_binding": {
                        "required_runtime": ["task-center"],
                        "tool_requirements": ["filesystem", "shell"],
                    },
                    "stage_context_gate": {
                        "evaluated_stage_id": "implement",
                        "required_fields": ["objective", "constraints", "acceptance"],
                        "missing_fields": ["objective"],
                        "needs_clarification": True,
                    },
                    "stage_parallel_execution": {
                        "enabled": True,
                        "mode": "candidate",
                        "suggested_batch_size": 3,
                    },
                    "stage_simplification_hint": {
                        "enabled": True,
                        "mode": "candidate",
                        "strategy": "sample_or_merge",
                    },
                    "stage_optimization_hints": {
                        "parallelize_stage_candidate": {"enabled": True},
                    },
                },
            },
            capability_index,
        )

        self.assertTrue(preflight["ok"])
        self.assertEqual(preflight["stage_context_gate"]["evaluated_stage_id"], "implement")
        self.assertEqual(preflight["stage_context_gate"]["missing_fields"], ["objective"])
        self.assertTrue(preflight["stage_context_gate"]["needs_clarification"])
        self.assertEqual(preflight["stage_parallel_execution"]["mode"], "candidate")
        self.assertEqual(preflight["stage_parallel_execution"]["suggested_batch_size"], 3)
        self.assertEqual(preflight["stage_execution_strategy"]["parallel_execution"]["mode"], "candidate")
        self.assertNotIn("load_balancing_hint", preflight["stage_execution_strategy"])
        self.assertEqual(preflight["stage_simplification_hint"]["strategy"], "sample_or_merge")
        self.assertTrue(preflight["stage_optimization_hints"]["parallelize_stage_candidate"]["enabled"])

    def test_preflight_exposes_requirement_package_gate(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        capability_index = {
            "project-agent": {
                "agent_id": "project-agent",
                "declared_skills": ["requirements-clarity"],
                "capability_mode": "skill_backed",
                "declared_runtime": ["task-center"],
                "available_tools": ["filesystem"],
            }
        }
        preflight = module.build_task_preflight(
            {
                "task_id": "task-requirement-gate-1",
                "assignee": "project-agent",
                "required_skills": ["requirements-clarity"],
                "required_capabilities": ["skill_backed"],
                "allowed_agents": ["project-agent"],
                "selection_inputs": {
                    "requirement_package_gate": {
                        "required": True,
                        "package_ready": False,
                        "triggered_by": "explicit_flag",
                        "required_fields": ["goal", "success_criteria"],
                        "missing_fields": ["goal"],
                    }
                },
            },
            capability_index,
        )

        self.assertTrue(preflight["ok"])
        self.assertTrue(preflight["requirement_package_gate"]["required"])
        self.assertFalse(preflight["requirement_package_gate"]["package_ready"])
        self.assertEqual(preflight["requirement_package_gate"]["missing_fields"], ["goal"])

    def test_preflight_warns_when_assignee_outside_planner_allowlist(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        capability_index = {
            "main": {
                "agent_id": "main",
                "declared_skills": ["requirements-clarity"],
                "capability_mode": "skill_backed",
                "allow_agents": ["frontend-dev"],
            },
            "backend-dev": {
                "agent_id": "backend-dev",
                "declared_skills": ["feature-development"],
                "capability_mode": "skill_backed",
            },
        }
        preflight = module.build_task_preflight(
            {
                "assignee": "backend-dev",
                "required_skills": [],
                "required_capabilities": [],
                "allowed_agents": [],
            },
            capability_index,
            planner_id="main",
        )

        self.assertFalse(preflight["ok"])
        self.assertIn("assignee_not_in_planner_allowlist", preflight["warnings"])
        self.assertEqual(preflight["planner_id"], "main")
        self.assertEqual(preflight["recommended_agents"], ["frontend-dev"])

    def test_preflight_rollup_tracks_warning_and_block_counts(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        summary = {
            "preflight_warning_tasks": 0,
            "preflight_warning_by_task_type": {},
            "preflight_warning_by_assignee": {},
            "preflight_warning_codes": {},
            "preflight_blocked_tasks": 0,
            "preflight_blocked_by_task_type": {},
            "preflight_blocked_by_assignee": {},
        }
        decision = module.record_preflight_observation(
            summary,
            task_type="self_evolution",
            assignee="backend-dev",
            preflight={
                "warnings": ["assignee_not_allowed", "required_skills_unmet"],
                "missing_skills": ["task-decomposer"],
                "missing_capabilities": [],
                "allowed_agents": ["coordinator"],
            },
            strict_task_types={"self_evolution"},
        )

        self.assertTrue(decision["has_warnings"])
        self.assertTrue(decision["strict_blocked"])
        self.assertEqual(summary["preflight_warning_tasks"], 1)
        self.assertEqual(summary["preflight_warning_by_task_type"]["self_evolution"], 1)
        self.assertEqual(summary["preflight_warning_by_assignee"]["backend-dev"], 1)
        self.assertEqual(summary["preflight_warning_codes"]["assignee_not_allowed"], 1)
        self.assertEqual(summary["preflight_warning_codes"]["required_skills_unmet"], 1)
        self.assertEqual(summary["preflight_blocked_tasks"], 1)
        self.assertEqual(summary["preflight_blocked_by_task_type"]["self_evolution"], 1)
        self.assertEqual(summary["preflight_blocked_by_assignee"]["backend-dev"], 1)

    def test_preflight_reassign_payload_prefers_allowed_agents(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        payload = module.build_preflight_reassign_payload(
            {
                "task_id": "todo-high-risk-1",
                "task_type": "governance_evolution_optimize",
                "assignee": "backend-dev",
            },
            {
                "warnings": ["assignee_not_allowed", "required_capabilities_unmet"],
                "missing_skills": [],
                "missing_capabilities": ["role_only"],
                "allowed_agents": ["optimization-agent"],
                "required_skills": [],
                "required_capabilities": ["role_only"],
            },
        )

        self.assertTrue(payload["need_reassign"])
        self.assertEqual(payload["reason_code"], "preflight_strict_blocked")
        self.assertEqual(payload["recommended_agents"], ["optimization-agent"])
        self.assertEqual(payload["missing_capabilities"], ["role_only"])
        self.assertIn("high-risk", payload["summary"].lower())


if __name__ == "__main__":
    unittest.main()

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
            }
        }
        preflight = module.build_task_preflight(
            {
                "assignee": "coordinator",
                "required_skills": ["task-decomposer"],
                "required_capabilities": ["skill_backed"],
                "allowed_agents": ["coordinator", "main"],
            },
            capability_index,
        )

        self.assertTrue(preflight["ok"])
        self.assertEqual(preflight["warnings"], [])
        self.assertEqual(preflight["missing_skills"], [])
        self.assertEqual(preflight["missing_capabilities"], [])

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

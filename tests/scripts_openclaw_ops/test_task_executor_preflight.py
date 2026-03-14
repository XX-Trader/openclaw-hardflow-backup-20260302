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


if __name__ == "__main__":
    unittest.main()

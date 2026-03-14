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
            "scripts/openclaw-ops/policy/task_center.py",
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
                    },
                )
            finally:
                task_center.close()

        self.assertEqual(created["required_capabilities"], ["task_execution", "routing"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertEqual(created["allowed_agents"], ["coordinator", "main"])
        self.assertEqual(updated["required_capabilities"], ["project_context", "routing"])
        self.assertEqual(updated["required_skills"], ["smart-workflow", "requirements-clarity"])
        self.assertEqual(updated["allowed_agents"], ["project-agent", "coordinator"])


if __name__ == "__main__":
    unittest.main()

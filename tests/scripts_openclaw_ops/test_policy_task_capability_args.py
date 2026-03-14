import argparse
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


class PolicyTaskCapabilityArgsTests(unittest.TestCase):
    def test_policy_enforcer_create_task_persists_capability_constraints(self):
        module = load_module(
            "policy_enforcer",
            "scripts/openclaw-ops/policy/policy_enforcer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = module.RuntimePaths(
                db=root / "task_center.db",
                policy_file=root / "policy-config.json",
                routing_file=root / "routing-rules.json",
                pricing_file=root / "token-pricing.json",
            )
            module.cmd_init(paths, force=True)
            enforcer = module.PolicyEnforcer(paths)
            try:
                args = argparse.Namespace(
                    task_id="todo-capability-cli-1",
                    task_type="workflow",
                    reason="[TEST] capability fields",
                    source="unit-test",
                    request_source="ai",
                    priority="medium",
                    risk_level="high",
                    pool="todo",
                    assignee="coordinator",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Persist CLI capability fields.",
                    result_output="Task stored.",
                    acceptance="Capability fields survive create-task.",
                    observable_outputs="task_center row",
                    acceptance_thresholds="fields are normalized",
                    required_capabilities="skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    context_json="",
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["required_capabilities"], ["skill_backed"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertEqual(created["allowed_agents"], ["coordinator", "main"])


if __name__ == "__main__":
    unittest.main()

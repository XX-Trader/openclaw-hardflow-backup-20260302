import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_ENFORCER_PATH = ROOT / "skills" / "library" / "control-plane-ops" / "scripts" / "policy" / "policy_enforcer.py"


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def init_runtime(paths):
    cli = load_module(
        "policy_cli_manual_route",
        ROOT / "skills" / "library" / "control-plane-ops" / "scripts" / "policy" / "policy_cli.py",
    )
    cli.cmd_init(paths, force=True)


class PolicyTaskManualRouteTests(unittest.TestCase):
    def test_create_task_defaults_to_manual_route_selection(self):
        module = load_module("policy_enforcer_manual_route", POLICY_ENFORCER_PATH)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = module.RuntimePaths(
                db=root / "task_center.db",
                policy_file=root / "policy-config.json",
                routing_file=root / "routing-rules.json",
                pricing_file=root / "token-pricing.json",
            )
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                created = enforcer.create_task(
                    argparse.Namespace(
                        task_id="todo-manual-route-1",
                        task_type="workflow",
                        reason="[TEST] manual route",
                        source="unit-test",
                        request_source="ai",
                        priority="medium",
                        risk_level="low",
                        pool="todo",
                        assignee="",
                        owner="",
                        change_id="",
                        entry_agent="",
                        need_human_confirm="false",
                        human_confirmed="true",
                        requirement="Fix workflow selector regression.",
                        result_output="Task stored.",
                        acceptance="Manual route selection is required.",
                        observable_outputs="task_center row",
                        acceptance_thresholds="route_selection required",
                        required_capabilities="",
                        required_skills="",
                        allowed_agents="",
                        context_json=json.dumps(
                            {
                                "problem": "Manual route selection should gate task execution.",
                                "location": "skills/library/control-plane-ops/scripts/policy/policy_task.py",
                                "impact": "Backlog runner could execute without human route choice.",
                                "operation_path": "policy_enforcer create-task",
                                "reproduction_steps": "create a low-risk AI task",
                                "scope": "Task Center route selection",
                                "acceptance_criteria": "created task waits for human route choice",
                            },
                            ensure_ascii=False,
                        ),
                        context_file="",
                        force_needs_clarification="false",
                        clarification_reason="",
                        scheduled_at="",
                        actor="policy-enforcer",
                    )
                )
            finally:
                enforcer.close()

        self.assertTrue(created["need_human_confirm"])
        self.assertFalse(created["human_confirmed"])
        self.assertEqual(created["assignee"], "human-inbox")
        self.assertEqual(created["action"], "await_route_selection")
        route_selection = created["context_payload"]["route_selection"]
        self.assertTrue(route_selection["required"])
        self.assertEqual(route_selection["mode"], "manual_selection")
        self.assertIn(route_selection["recommended_route"], {"coding_workflow", "requirement_discussion"})

    def test_confirm_risk_rejects_unselected_route_task(self):
        module = load_module("policy_enforcer_manual_route_confirm", POLICY_ENFORCER_PATH)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = module.RuntimePaths(
                db=root / "task_center.db",
                policy_file=root / "policy-config.json",
                routing_file=root / "routing-rules.json",
                pricing_file=root / "token-pricing.json",
            )
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                created = enforcer.db.create_task(
                    {
                        "task_id": "todo-route-confirm-risk",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Route choice required",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "human-inbox",
                        "status": "pending",
                        "need_human_confirm": True,
                        "human_confirmed": False,
                        "action": "await_route_selection",
                        "context_payload": {
                            "route_selection": {
                                "mode": "manual_selection",
                                "required": True,
                                "recommended_route": "coding_workflow",
                            }
                        },
                        "requirement": "Select a route first.",
                        "result_output": "Selected route.",
                        "acceptance": "Confirm-risk cannot hide the task.",
                        "observable_outputs": "policy error",
                        "acceptance_thresholds": "route choice required",
                    },
                    actor="test",
                )
                snapshot = enforcer.task_confirmation_snapshot(created)
                with self.assertRaises(module.PolicyError) as raised:
                    enforcer.confirm_risk(
                        argparse.Namespace(
                            task_id="todo-route-confirm-risk",
                            confirmed="true",
                            actor="human",
                        )
                    )
            finally:
                enforcer.close()

        self.assertIn("human_inbox.py", snapshot["confirm_command"])
        self.assertIn("--route-choice recommended", snapshot["confirm_command"])
        self.assertIn("requires route selection", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

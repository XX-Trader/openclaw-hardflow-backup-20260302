import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    if not path.exists() and rel_path == "scripts/openclaw-ops/policy/policy_enforcer.py":
        path = ROOT / "skills" / "library" / "control-plane-ops" / "scripts" / "policy" / "policy_enforcer.py"
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


def init_runtime(paths):
    cli = load_module(
        "policy_cli_workflow_selector",
        "skills/library/control-plane-ops/scripts/policy/policy_cli.py",
    )
    cli.cmd_init(paths, force=True)


class WorkflowSelectorTests(unittest.TestCase):
    def test_select_workflow_defaults_to_coding_default_for_coding_request(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                selected = enforcer.select_workflow(
                    argparse.Namespace(
                        description="Fix API bug and add regression tests for the workflow gate.",
                        task_type="workflow",
                        source="openclaw",
                        request_source="human",
                        assignee="coordinator",
                        needs_clarification="false",
                        workflow_profile_id="",
                        workflow_channel="",
                        workflow_selection_reason="",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(selected["workflow_profile_id"], "coding-default")
        self.assertEqual(selected["workflow_channel"], "stable")
        self.assertEqual(selected["selection_reason"], "default_coding_workflow_for_execution")
        self.assertEqual(selected["selection_inputs"]["selector_state"], "selected")
        self.assertIn("coding_task", selected["selection_inputs"]["matched_keyword_groups"])

    def test_select_workflow_switches_to_research_default_for_research_request(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                selected = enforcer.select_workflow(
                    argparse.Namespace(
                        description="Research competitor APIs and analyze the latest integration constraints.",
                        task_type="workflow",
                        source="openclaw",
                        request_source="human",
                        assignee="coordinator",
                        needs_clarification="false",
                        workflow_profile_id="",
                        workflow_channel="",
                        workflow_selection_reason="",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(selected["workflow_profile_id"], "research-default")
        self.assertEqual(selected["workflow_channel"], "stable")
        self.assertEqual(selected["selection_reason"], "keyword_group_workflow_selection:research_task")
        self.assertEqual(selected["selection_inputs"]["selector_state"], "keyword_group_override")
        self.assertEqual(selected["selection_inputs"]["selected_keyword_group"], "research_task")
        self.assertIn("research_task", selected["selection_inputs"]["matched_keyword_groups"])

    def test_select_workflow_switches_to_docs_default_for_docs_request(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                selected = enforcer.select_workflow(
                    argparse.Namespace(
                        description="Draft ADR docs and update README for workflow changes.",
                        task_type="workflow",
                        source="openclaw",
                        request_source="human",
                        assignee="coordinator",
                        needs_clarification="false",
                        workflow_profile_id="",
                        workflow_channel="",
                        workflow_selection_reason="",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(selected["workflow_profile_id"], "docs-default")
        self.assertEqual(selected["workflow_channel"], "stable")
        self.assertEqual(selected["selection_reason"], "keyword_group_workflow_selection:docs_task")
        self.assertEqual(selected["selection_inputs"]["selector_state"], "keyword_group_override")
        self.assertEqual(selected["selection_inputs"]["selected_keyword_group"], "docs_task")
        self.assertIn("docs_task", selected["selection_inputs"]["matched_keyword_groups"])

    def test_select_workflow_switches_to_ops_default_for_ops_request(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                selected = enforcer.select_workflow(
                    argparse.Namespace(
                        description="Stabilize cron monitor service and fix infra alert spikes.",
                        task_type="workflow",
                        source="openclaw",
                        request_source="human",
                        assignee="coordinator",
                        needs_clarification="false",
                        workflow_profile_id="",
                        workflow_channel="",
                        workflow_selection_reason="",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(selected["workflow_profile_id"], "ops-default")
        self.assertEqual(selected["workflow_channel"], "stable")
        self.assertEqual(selected["selection_reason"], "keyword_group_workflow_selection:ops_task")
        self.assertEqual(selected["selection_inputs"]["selector_state"], "keyword_group_override")
        self.assertEqual(selected["selection_inputs"]["selected_keyword_group"], "ops_task")
        self.assertIn("ops_task", selected["selection_inputs"]["matched_keyword_groups"])

    def test_select_workflow_skips_runtime_binding_task_type(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                selected = enforcer.select_workflow(
                    argparse.Namespace(
                        description="Bind runtime observability for cron watchdog.",
                        task_type="ops_runtime_cron",
                        source="ops-cron",
                        request_source="ai",
                        assignee="ops-agent",
                        needs_clarification="false",
                        workflow_profile_id="",
                        workflow_channel="",
                        workflow_selection_reason="",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(selected["workflow_profile_id"], "")
        self.assertEqual(selected["workflow_channel"], "")
        self.assertEqual(selected["selection_reason"], "")
        self.assertEqual(selected["selection_inputs"], {})

    def test_route_task_includes_workflow_selection(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                routed = enforcer.route_task(
                    argparse.Namespace(
                        description="Implement workflow selector support for coding tasks.",
                        source="openclaw",
                        request_source="human",
                        task_type="workflow",
                        context_json="",
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertIn("workflow_selection", routed)
        self.assertEqual(routed["workflow_selection"]["workflow_profile_id"], "coding-default")
        self.assertEqual(routed["workflow_selection"]["workflow_channel"], "stable")
        self.assertTrue(routed["route_selection"]["required"])
        self.assertEqual(routed["execution_strategy"]["mode"], "manual_route_selection")
        self.assertEqual(routed["route_selection"]["recommended_route"], "coding_workflow")

    def test_route_task_flags_requirement_package_gap_for_complex_human_request(self):
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
            init_runtime(paths)
            enforcer = module.PolicyEnforcer(paths)
            try:
                routed = enforcer.route_task(
                    argparse.Namespace(
                        description="Project requirement for evolving the workflow control plane.",
                        source="openclaw",
                        request_source="human",
                        task_type="workflow",
                        context_json=json.dumps({"requirement_package_required": True}, ensure_ascii=False),
                        context_file="",
                    )
                )
            finally:
                enforcer.close()

        self.assertTrue(routed["needs_clarification"])
        self.assertIn("requirement_package_incomplete", routed["clarification_reason"])
        self.assertEqual(routed["assignee"], "project-agent")
        self.assertEqual(
            routed["requirement_package_gate"]["missing_fields"],
            ["goal", "success_criteria", "scope.in_scope", "scope.out_of_scope"],
        )


if __name__ == "__main__":
    unittest.main()

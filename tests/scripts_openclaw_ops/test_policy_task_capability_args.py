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
    def test_cmd_init_writes_capability_registry_file(self):
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
            result = module.cmd_init(paths, force=True)
            registry_file = root / "capability-registry.json"
            registry = json.loads(registry_file.read_text(encoding="utf-8"))

        self.assertEqual(result["capability_registry_file"], str(registry_file))
        self.assertEqual(registry["schema_version"], "2026-03-22")
        self.assertGreaterEqual(len(registry["capabilities"]), 5)
        self.assertGreaterEqual(len(registry["agent_defaults"]), 5)

    def test_cmd_init_writes_workflow_profile_registry_file(self):
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
            result = module.cmd_init(paths, force=True)
            registry_file = root / "workflow-profile-registry.json"
            registry = json.loads(registry_file.read_text(encoding="utf-8"))

        self.assertEqual(result["workflow_profile_registry_file"], str(registry_file))
        self.assertEqual(registry["default_profile_id"], "coding-default")
        self.assertEqual(registry["default_channel"], "stable")
        self.assertEqual(len(registry["profiles"]), 8)
        self.assertEqual(registry["profiles"][0]["default_stage_id"], "implement")
        self.assertEqual(registry["profiles"][0]["task_type_stage_map"]["clarification_required"], "clarify")
        self.assertEqual(registry["profiles"][0]["stages"][0]["stage_id"], "clarify")
        self.assertEqual(registry["profiles"][0]["stages"][0]["score_gate"], "requirements")
        self.assertEqual(registry["profiles"][0]["stages"][1]["score_gate"], "backend")
        self.assertEqual(registry["profiles"][0]["stages"][1]["min_evidence_count"], 3)
        self.assertEqual(
            registry["profiles"][0]["stages"][1]["output_contract"]["deliverables"],
            ["code_changes", "verification_result"],
        )
        research_stable = next(
            item
            for item in registry["profiles"]
            if item["profile_id"] == "research-default" and item["channel"] == "stable"
        )
        self.assertEqual(research_stable["default_stage_id"], "investigate")
        self.assertEqual(research_stable["task_type_stage_map"]["workflow"], "investigate")
        self.assertEqual(research_stable["stages"][1]["stage_id"], "investigate")
        self.assertEqual(research_stable["stages"][1]["score_gate"], "solution")
        self.assertEqual(research_stable["stages"][1]["required_skills"], ["content-research-writer"])
        docs_stable = next(
            item
            for item in registry["profiles"]
            if item["profile_id"] == "docs-default" and item["channel"] == "stable"
        )
        self.assertEqual(docs_stable["default_stage_id"], "draft")
        self.assertEqual(docs_stable["task_type_stage_map"]["workflow"], "draft")
        self.assertEqual(docs_stable["stages"][1]["stage_id"], "draft")
        self.assertEqual(docs_stable["stages"][1]["score_gate"], "solution")
        self.assertEqual(docs_stable["stages"][1]["required_skills"], ["writing-plans"])
        ops_stable = next(
            item
            for item in registry["profiles"]
            if item["profile_id"] == "ops-default" and item["channel"] == "stable"
        )
        self.assertEqual(ops_stable["default_stage_id"], "stabilize")
        self.assertEqual(ops_stable["task_type_stage_map"]["workflow"], "stabilize")
        self.assertEqual(ops_stable["stages"][1]["stage_id"], "stabilize")
        self.assertEqual(ops_stable["stages"][1]["score_gate"], "release")
        self.assertEqual(ops_stable["stages"][2]["required_skills"], ["deployment-test"])

    def test_cmd_init_writes_benchmark_suite_registry_file(self):
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
            result = module.cmd_init(paths, force=True)
            registry_file = root / "benchmark-suite-registry.json"
            registry = json.loads(registry_file.read_text(encoding="utf-8"))

        self.assertEqual(result["benchmark_suite_registry_file"], str(registry_file))
        self.assertEqual(registry["default_suite_id"], "coding-default-core")
        self.assertEqual(len(registry["suites"]), 4)
        self.assertEqual(registry["suites"][0]["workflow_profile_id"], "coding-default")
        self.assertEqual(registry["suites"][0]["workflow_target"], "task_executor_10m")
        research_suite = next(item for item in registry["suites"] if item["suite_id"] == "research-default-core")
        self.assertEqual(research_suite["workflow_profile_id"], "research-default")
        self.assertEqual(research_suite["candidate_channel"], "candidate")
        docs_suite = next(item for item in registry["suites"] if item["suite_id"] == "docs-default-core")
        self.assertEqual(docs_suite["workflow_profile_id"], "docs-default")
        self.assertEqual(docs_suite["candidate_channel"], "candidate")
        ops_suite = next(item for item in registry["suites"] if item["suite_id"] == "ops-default-core")
        self.assertEqual(ops_suite["workflow_profile_id"], "ops-default")
        self.assertEqual(ops_suite["candidate_channel"], "candidate")

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
                    context_json=json.dumps(
                        {
                            "problem": "Need to persist CLI capability fields.",
                            "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                            "first_seen_at": "2026-03-22T12:00:00+08:00",
                            "impact": "create-task constraints would be lost",
                            "evidence": "unit-test",
                            "current_state": "fields are provided via CLI",
                            "expected_state": "task_center stores normalized values",
                            "operation_path": "policy_enforcer create-task",
                            "reproduction_steps": "run create-task with capability flags",
                            "scope": "policy runtime",
                            "constraints": "keep compatibility with task_center",
                            "acceptance_criteria": "created task contains normalized constraints",
                            "full_background": "workflow/capability runtime refactor",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["stage_id"], "implement")
        self.assertEqual(created["required_capabilities"], ["skill_backed", "task_execution", "routing"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertEqual(created["allowed_agents"], ["coordinator", "main"])
        self.assertEqual(created["stage_score_gate"], "backend")
        self.assertEqual(created["stage_min_evidence_count"], 3)
        self.assertEqual(created["stage_output_contract"]["deliverables"], ["code_changes", "verification_result"])
        self.assertEqual(created["stage_verification_contract"]["checks"], ["tests_or_validation_recorded"])
        self.assertEqual(created["workflow_profile_id"], "coding-default")
        self.assertEqual(created["workflow_channel"], "stable")
        self.assertEqual(created["selection_reason"], "default_coding_workflow_for_execution")
        self.assertEqual(created["selection_inputs"]["task_type"], created["task_type"])
        self.assertEqual(created["selection_inputs"]["workflow_profile_id"], "coding-default")
        self.assertEqual(created["selection_inputs"]["selector_state"], "selected")
        self.assertEqual(created["selection_inputs"]["stage_id"], "implement")
        self.assertEqual(created["selection_inputs"]["stage_score_gate"], "backend")
        self.assertIn("coding_task", created["selection_inputs"]["matched_keyword_groups"])
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["required_runtime"],
            ["task-center", "skills"],
        )
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["tool_requirements"],
            ["filesystem", "shell"],
        )
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["resolved_assignee"],
            "coordinator",
        )
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["resolved_agent_profile"]["agent_id"],
            "coordinator",
        )
        self.assertGreaterEqual(
            len(created["selection_inputs"]["capability_binding"]["capability_declarations"]),
            2,
        )
        self.assertIn(
            "skill_backed",
            [
                item["capability_id"]
                for item in created["selection_inputs"]["capability_binding"]["capability_declarations"]
            ],
        )
        self.assertIn(
            "task_execution",
            [
                item["capability_id"]
                for item in created["selection_inputs"]["capability_binding"]["capability_declarations"]
            ],
        )
        self.assertGreaterEqual(
            len(created["selection_inputs"]["capability_binding"]["capability_contracts"]["input_contracts"]),
            1,
        )
        self.assertGreaterEqual(
            len(created["selection_inputs"]["capability_binding"]["capability_contracts"]["verification_contracts"]),
            1,
        )

    def test_policy_enforcer_create_task_routes_research_request_to_research_workflow(self):
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
                    task_id="todo-research-workflow-cli-1",
                    task_type="workflow",
                    reason="[TEST] research workflow routing",
                    source="unit-test",
                    request_source="human",
                    priority="medium",
                    risk_level="low",
                    pool="todo",
                    assignee="coordinator",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Research competitor APIs and analyze integration tradeoffs.",
                    result_output="Task stored.",
                    acceptance="Research workflow selection survives create-task.",
                    observable_outputs="workflow selection + task row",
                    acceptance_thresholds="research workflow stage is normalized",
                    required_capabilities="",
                    required_skills="",
                    allowed_agents="",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need a research-oriented workflow route.",
                            "scope": "workflow runtime",
                            "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                            "constraints": "keep coding workflow default unchanged",
                            "acceptance_criteria": "research requests select research-default",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["workflow_profile_id"], "research-default")
        self.assertEqual(created["workflow_channel"], "stable")
        self.assertEqual(created["selection_reason"], "keyword_group_workflow_selection:research_task")
        self.assertEqual(created["stage_id"], "investigate")
        self.assertEqual(created["stage_score_gate"], "solution")
        self.assertEqual(created["stage_output_contract"]["deliverables"], ["research_findings", "source_summary"])
        self.assertEqual(created["required_capabilities"], ["skill_backed", "project_context", "routing"])
        self.assertEqual(
            created["required_skills"],
            ["requirements-clarity", "task-decomposer", "content-research-writer"],
        )
        self.assertIn("research_task", created["selection_inputs"]["matched_keyword_groups"])
        self.assertEqual(created["selection_inputs"]["selected_keyword_group"], "research_task")
        self.assertEqual(created["selection_inputs"]["selector_state"], "keyword_group_override")
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["required_runtime"],
            ["task-center", "skills"],
        )
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["tool_requirements"],
            ["filesystem"],
        )

    def test_policy_enforcer_create_task_routes_docs_request_to_docs_workflow(self):
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
                    task_id="todo-docs-workflow-cli-1",
                    task_type="workflow",
                    reason="[TEST] docs workflow routing",
                    source="unit-test",
                    request_source="human",
                    priority="medium",
                    risk_level="low",
                    pool="todo",
                    assignee="coordinator",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Update README docs and draft an ADR for workflow selection changes.",
                    result_output="Task stored.",
                    acceptance="Docs workflow selection survives create-task.",
                    observable_outputs="workflow selection + task row",
                    acceptance_thresholds="docs workflow stage is normalized",
                    required_capabilities="",
                    required_skills="",
                    allowed_agents="",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need a docs-oriented workflow route.",
                            "scope": "workflow runtime",
                            "location": "docs/ and README updates",
                            "constraints": "keep coding and research workflows unchanged",
                            "acceptance_criteria": "docs requests select docs-default",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["workflow_profile_id"], "docs-default")
        self.assertEqual(created["workflow_channel"], "stable")
        self.assertEqual(created["selection_reason"], "keyword_group_workflow_selection:docs_task")
        self.assertEqual(created["stage_id"], "draft")
        self.assertEqual(created["stage_score_gate"], "solution")
        self.assertEqual(created["stage_output_contract"]["deliverables"], ["draft_document", "change_summary"])
        self.assertEqual(created["required_capabilities"], ["skill_backed", "project_context", "routing"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer", "writing-plans"])
        self.assertIn("docs_task", created["selection_inputs"]["matched_keyword_groups"])
        self.assertEqual(created["selection_inputs"]["selected_keyword_group"], "docs_task")
        self.assertEqual(created["selection_inputs"]["selector_state"], "keyword_group_override")

    def test_policy_enforcer_create_task_routes_ops_request_to_ops_workflow(self):
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
                    task_id="todo-ops-workflow-cli-1",
                    task_type="workflow",
                    reason="[TEST] ops workflow routing",
                    source="unit-test",
                    request_source="human",
                    priority="medium",
                    risk_level="low",
                    pool="todo",
                    assignee="coordinator",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Stabilize cron monitor service and fix infra alert noise.",
                    result_output="Task stored.",
                    acceptance="Ops workflow selection survives create-task.",
                    observable_outputs="workflow selection + task row",
                    acceptance_thresholds="ops workflow stage is normalized",
                    required_capabilities="",
                    required_skills="",
                    allowed_agents="",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need an ops-oriented workflow route.",
                            "scope": "workflow runtime",
                            "location": "cron/service monitoring",
                            "constraints": "keep coding/research/docs workflows unchanged",
                            "acceptance_criteria": "ops requests select ops-default",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["workflow_profile_id"], "ops-default")
        self.assertEqual(created["workflow_channel"], "stable")
        self.assertEqual(created["selection_reason"], "keyword_group_workflow_selection:ops_task")
        self.assertEqual(created["stage_id"], "stabilize")
        self.assertEqual(created["stage_score_gate"], "release")
        self.assertEqual(
            created["stage_output_contract"]["deliverables"],
            ["ops_change", "service_health_evidence"],
        )
        self.assertEqual(created["required_capabilities"], ["skill_backed", "task_execution", "routing"])
        self.assertEqual(created["required_skills"], ["requirements-clarity", "task-decomposer"])
        self.assertIn("ops_task", created["selection_inputs"]["matched_keyword_groups"])
        self.assertEqual(created["selection_inputs"]["selected_keyword_group"], "ops_task")
        self.assertEqual(created["selection_inputs"]["selector_state"], "keyword_group_override")

    def test_policy_enforcer_create_task_reroutes_when_stage_clarification_fields_are_missing(self):
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
            registry_file = root / "workflow-profile-registry.json"
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
            coding_stable = next(
                item
                for item in registry["profiles"]
                if item["profile_id"] == "coding-default" and item["channel"] == "stable"
            )
            implement_stage = next(
                stage for stage in coding_stable["stages"] if stage["stage_id"] == "implement"
            )
            implement_stage["clarification_required_fields"] = ["objective", "constraints", "acceptance"]
            registry_file.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            enforcer = module.PolicyEnforcer(paths)
            try:
                args = argparse.Namespace(
                    task_id="todo-stage-clarification-cli-1",
                    task_type="workflow",
                    reason="[TEST] stage clarification gate",
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
                    requirement="Implement workflow change after clarification gate.",
                    result_output="Task stored.",
                    acceptance="Missing stage clarification fields reroute task.",
                    observable_outputs="task row + selection inputs",
                    acceptance_thresholds="task becomes clarification_required",
                    required_capabilities="skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need stage-aware clarification gate.",
                            "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                            "first_seen_at": "2026-03-23T10:00:00+08:00",
                            "impact": "optimization-applied profile updates would never affect intake",
                            "evidence": "unit-test",
                            "current_state": "stage clarification fields are ignored",
                            "expected_state": "missing stage-required fields reroute task",
                            "operation_path": "policy_enforcer create-task",
                            "reproduction_steps": "run create-task with missing objective",
                            "scope": "workflow runtime",
                            "constraints": "keep workflow selector stable",
                            "acceptance_criteria": "task becomes clarification_required when objective is missing",
                            "full_background": "profile update apply adds clarification_required_fields to implement stage",
                            "acceptance": "task reroutes to clarify stage",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["task_type"], "clarification_required")
        self.assertTrue(created["needs_clarification"])
        self.assertEqual(created["assignee"], "project-agent")
        self.assertEqual(created["stage_id"], "clarify")
        self.assertEqual(created["stage_score_gate"], "requirements")
        self.assertIn("objective", created["context_fields_missing"])
        self.assertIn("stage_context_incomplete", created["clarification_reason"])
        self.assertEqual(
            created["selection_inputs"]["stage_context_gate"]["evaluated_stage_id"],
            "implement",
        )
        self.assertEqual(
            created["selection_inputs"]["stage_context_gate"]["required_fields"],
            ["objective", "constraints", "acceptance"],
        )
        self.assertEqual(
            created["selection_inputs"]["stage_context_gate"]["missing_fields"],
            ["objective"],
        )
        self.assertEqual(
            created["selection_inputs"]["stage_context_gate"]["rerouted_task_type"],
            "clarification_required",
        )

    def test_policy_enforcer_create_task_requires_requirement_package_for_complex_human_workflow(self):
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
                    task_id="todo-requirement-package-cli-1",
                    task_type="workflow",
                    reason="[TEST] complex human workflow requirement package",
                    source="unit-test",
                    request_source="human",
                    priority="medium",
                    risk_level="high",
                    pool="todo",
                    assignee="",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Upgrade workflow evolution loop for complex multi-step delivery.",
                    result_output="Task stored.",
                    acceptance="Requirement package gate reroutes the task before execution.",
                    observable_outputs="task row + requirement package gate",
                    acceptance_thresholds="task becomes clarification_required",
                    required_capabilities="task_execution",
                    required_skills="feature-development",
                    allowed_agents="backend-dev,project-agent",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need a safer requirement package gate for complex human workflow intake.",
                            "requirement_package_required": True,
                            "constraints": ["keep current workflow registry compatible"],
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["task_type"], "clarification_required")
        self.assertTrue(created["needs_clarification"])
        self.assertEqual(created["assignee"], "project-agent")
        self.assertIn("requirement_package_incomplete", created["clarification_reason"])
        self.assertEqual(
            created["selection_inputs"]["requirement_package_gate"]["missing_fields"],
            ["goal", "success_criteria", "scope.in_scope", "scope.out_of_scope"],
        )
        self.assertTrue(created["selection_inputs"]["requirement_package_gate"]["required"])
        self.assertEqual(
            created["selection_inputs"]["requirement_package_gate"]["triggered_by"],
            "explicit_flag",
        )

    def test_policy_enforcer_create_task_persists_stage_execution_hints(self):
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
            registry_file = root / "workflow-profile-registry.json"
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
            coding_stable = next(
                item
                for item in registry["profiles"]
                if item["profile_id"] == "coding-default" and item["channel"] == "stable"
            )
            implement_stage = next(
                stage for stage in coding_stable["stages"] if stage["stage_id"] == "implement"
            )
            implement_stage["parallel_execution"] = {
                "enabled": True,
                "mode": "candidate",
                "suggested_batch_size": 3,
            }
            implement_stage["simplification_hint"] = {
                "enabled": True,
                "mode": "candidate",
                "strategy": "sample_or_merge",
            }
            implement_stage["optimization_hints"] = {
                "parallelize_stage_candidate": {"enabled": True},
                "stage_simplification_candidate": {"enabled": True},
            }
            registry_file.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            enforcer = module.PolicyEnforcer(paths)
            try:
                args = argparse.Namespace(
                    task_id="todo-stage-hints-cli-1",
                    task_type="workflow",
                    reason="[TEST] stage execution hints",
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
                    requirement="Surface stage execution hints to task runtime.",
                    result_output="Task stored.",
                    acceptance="Stage execution hints survive create-task.",
                    observable_outputs="task row + selection inputs",
                    acceptance_thresholds="parallel/simplification hints are preserved",
                    required_capabilities="skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json=json.dumps(
                        {
                            "problem": "Need runtime to see optimization hints.",
                            "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                            "first_seen_at": "2026-03-23T10:05:00+08:00",
                            "impact": "candidate profile hints stay trapped in registry",
                            "evidence": "unit-test",
                            "current_state": "selection_inputs omit stage execution hints",
                            "expected_state": "parallel and simplification hints reach runtime",
                            "operation_path": "policy_enforcer create-task",
                            "reproduction_steps": "run create-task with optimization-applied stage",
                            "scope": "workflow runtime",
                            "constraints": "keep workflow selector stable",
                            "acceptance_criteria": "selection_inputs exposes stage execution hints",
                            "full_background": "profile update apply writes parallel_execution and simplification_hint",
                            "objective": "Surface candidate execution hints into runtime payload",
                            "acceptance": "task runtime can read optimization hints",
                        },
                        ensure_ascii=False,
                    ),
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["task_type"], "workflow")
        self.assertEqual(created["stage_id"], "implement")
        self.assertTrue(str(created["trace_id"]).startswith("trace-"))
        self.assertEqual(created["attempt_id"], "attempt-001")
        self.assertEqual(created["selection_inputs"]["trace_id"], created["trace_id"])
        self.assertEqual(created["selection_inputs"]["attempt_id"], created["attempt_id"])
        self.assertEqual(
            created["selection_inputs"]["execution_envelope"]["trace_id"],
            created["trace_id"],
        )
        self.assertEqual(
            created["selection_inputs"]["execution_envelope"]["attempt_id"],
            "attempt-001",
        )
        self.assertEqual(
            created["selection_inputs"]["execution_envelope"]["workflow"]["stage_id"],
            "implement",
        )
        self.assertEqual(created["selection_inputs"]["stage_parallel_execution"]["mode"], "candidate")
        self.assertEqual(created["selection_inputs"]["stage_parallel_execution"]["suggested_batch_size"], 3)
        self.assertEqual(
            created["selection_inputs"]["stage_simplification_hint"]["strategy"],
            "sample_or_merge",
        )
        self.assertNotIn("stage_load_balancing_hint", created["selection_inputs"])
        self.assertTrue(
            created["selection_inputs"]["stage_optimization_hints"]["parallelize_stage_candidate"]["enabled"]
        )
        self.assertEqual(created["selection_inputs"]["stage_context_gate"]["missing_fields"], [])

    def test_policy_enforcer_task_capability_coverage_reports_upgrade_ratio(self):
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
                for task_id, assignee, required_skills in (
                    ("todo-coverage-1", "coordinator", ["requirements-clarity"]),
                    ("todo-coverage-2", "", []),
                ):
                    payload = {
                        "task_id": task_id,
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "[TEST] coverage fields",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": assignee,
                        "status": "pending",
                        "need_human_confirm": False,
                        "human_confirmed": True,
                        "requirement": "Persist coverage fields.",
                        "result_output": "Task stored.",
                        "acceptance": "Coverage fields can be summarized.",
                        "observable_outputs": "task_center row",
                        "acceptance_thresholds": "coverage summary returns expected counts",
                        "required_capabilities": (["skill_backed"] if required_skills else []),
                        "required_skills": required_skills,
                        "allowed_agents": (["coordinator"] if required_skills else []),
                    }
                    enforcer.db.create_task(payload, actor="policy-enforcer")

                summary = enforcer.task_capability_coverage(
                    argparse.Namespace(
                        since="",
                        task_type="",
                        assignee="",
                        status="",
                        pool="",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["upgraded_tasks"], 1)
        self.assertEqual(summary["upgrade_ratio_pct"], 50.0)
        self.assertEqual(summary["with_required_skills"], 1)
        self.assertEqual(summary["with_required_capabilities"], 1)
        self.assertEqual(summary["with_allowed_agents"], 1)

    def test_policy_enforcer_create_task_accepts_explicit_candidate_workflow(self):
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
                    task_id="todo-candidate-cli-1",
                    task_type="workflow",
                    reason="[TEST] explicit candidate workflow",
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
                    requirement="Allow explicit candidate workflow.",
                    result_output="Task stored.",
                    acceptance="Candidate workflow selection survives create-task.",
                    observable_outputs="task_center row",
                    acceptance_thresholds="candidate workflow is normalized",
                    required_capabilities="skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    workflow_selection_reason="benchmark_candidate_upgrade",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
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

        self.assertEqual(created["workflow_profile_id"], "coding-default")
        self.assertEqual(created["workflow_channel"], "candidate")
        self.assertEqual(created["selection_reason"], "benchmark_candidate_upgrade")

    def test_post_stage_merges_stage_contract_details_into_stage_run(self):
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
                enforcer.db.create_task(
                    {
                        "task_id": "todo-stage-contract-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "[TEST] stage contract merge",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "backend-dev",
                        "status": "pending",
                        "human_confirmed": True,
                        "requirement": "Persist stage contract details.",
                        "result_output": "stage run contains assessment",
                        "acceptance": "stage run details merged",
                        "observable_outputs": "stage run details",
                        "acceptance_thresholds": "stage contract is present",
                    },
                    actor="unit-test",
                )
                enforcer.pre_stage(
                    argparse.Namespace(
                        task_id="todo-stage-contract-1",
                        stage="implement",
                        agent_id="backend-dev",
                        model="openai-codex/gpt-5.4",
                        input_ref="input.log",
                        actor="unit-test",
                    )
                )
                enforcer.post_stage(
                    argparse.Namespace(
                        task_id="todo-stage-contract-1",
                        stage="implement",
                        exit_code="0",
                        reason="ok",
                        output_ref="output.log",
                        details_json=json.dumps(
                            {
                                "stage_contract": {
                                    "score_gate": "backend",
                                    "contract_passed": False,
                                    "failed_checks": ["tests_or_validation_recorded"],
                                }
                            },
                            ensure_ascii=False,
                        ),
                        actor="unit-test",
                    )
                )
                stage_runs = enforcer.db.list_stage_runs("todo-stage-contract-1", display_safe=False)
            finally:
                enforcer.close()

        self.assertEqual(len(stage_runs), 1)
        self.assertEqual(stage_runs[0]["status"], "passed")
        self.assertEqual(stage_runs[0]["details"]["reason"], "ok")
        self.assertEqual(stage_runs[0]["details"]["stage_contract"]["score_gate"], "backend")
        self.assertFalse(stage_runs[0]["details"]["stage_contract"]["contract_passed"])
        self.assertEqual(
            stage_runs[0]["details"]["stage_contract"]["failed_checks"],
            ["tests_or_validation_recorded"],
        )

    def test_report_agent_result_downgrades_failed_stage_contract_to_partial_retry(self):
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
                enforcer.db.create_task(
                    {
                        "task_id": "todo-stage-gate-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "[TEST] report stage contract gate",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "low",
                        "assignee": "backend-dev",
                        "status": "running",
                        "human_confirmed": True,
                        "requirement": "Stage contract should affect report status.",
                        "result_output": "Report is downgraded.",
                        "acceptance": "stage contract failure becomes partial retry",
                        "observable_outputs": "report + task status sync",
                        "acceptance_thresholds": "partial + retry",
                    },
                    actor="unit-test",
                )
                result = enforcer.report_agent_result(
                    argparse.Namespace(
                        task_id="todo-stage-gate-1",
                        agent_id="backend-dev",
                        planner_id="coordinator",
                        status="passed",
                        solved="true",
                        resolved_issues="fixed endpoint regression",
                        resolution_summary="Implemented API fix.",
                        resolution_steps="updated service handler",
                        failed_items="",
                        failure_count="0",
                        duration_ms="1200",
                        model="openai-codex/gpt-5.4",
                        input_tokens="100",
                        output_tokens="20",
                        cost_estimate="0",
                        quality_score="92",
                        quality_grade="a",
                        notify_chat="false",
                        details_json=json.dumps(
                            {
                                "stage_contract": {
                                    "score_gate": "backend",
                                    "contract_passed": False,
                                    "missing_deliverables": ["verification_result"],
                                    "failed_checks": ["tests_or_validation_recorded"],
                                }
                            },
                            ensure_ascii=False,
                        ),
                        actor="backend-dev",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(result["report"]["status"], "partial")
        self.assertFalse(result["planner_payload"]["solved"])
        self.assertEqual(result["planner_payload"]["report_status"], "partial")
        self.assertEqual(result["task_status_sync"]["task_status_after"], "running")
        self.assertEqual(result["task_status_sync"]["task_action_after"], "retry")
        self.assertEqual(result["planner_payload"]["quality_score"], 69.0)
        self.assertIn("stage_contract_failed", result["planner_payload"]["failed_items"])
        self.assertIn(
            "stage_contract_missing_deliverable:verification_result",
            result["planner_payload"]["failed_items"],
        )
        self.assertIn(
            "stage_contract_failed_check:tests_or_validation_recorded",
            result["planner_payload"]["failed_items"],
        )
        self.assertEqual(result["output_record"]["output_type"], "agent_report")
        self.assertEqual(result["output_record"]["audience"], "human")
        self.assertEqual(result["output_record"]["status"], "suppressed")
        self.assertEqual(result["standard_output"]["human_gate"]["requires_human_assistance"], True)
        self.assertEqual(result["standard_output"]["trace_id"], result["output_record"]["trace_id"])
        self.assertEqual(
            result["standard_output"]["execution_envelope"]["task_id"],
            "todo-stage-gate-1",
        )
        self.assertEqual(
            result["output_record"]["payload"]["execution_envelope"]["task_id"],
            "todo-stage-gate-1",
        )
        self.assertEqual(result["incident"]["incident_type"], "stage_contract_failed")
        self.assertEqual(result["incident"]["severity"], "warning")
        self.assertEqual(
            result["incident"]["details"]["execution_envelope"]["task_id"],
            "todo-stage-gate-1",
        )
        self.assertEqual(result["planner_payload"]["delivery"]["status"], "suppressed")
        self.assertTrue(result["planner_payload"]["incident"]["recorded"])

    def test_policy_enforcer_create_task_rejects_unknown_workflow_profile(self):
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
                    task_id="todo-invalid-workflow-cli-1",
                    task_type="workflow",
                    reason="[TEST] invalid workflow",
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
                    requirement="Unknown workflow must fail.",
                    result_output="Task rejected.",
                    acceptance="Unknown workflow profile triggers PolicyError.",
                    observable_outputs="policy error",
                    acceptance_thresholds="unknown profile is rejected",
                    required_capabilities="skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    workflow_profile_id="unknown-workflow-profile",
                    workflow_channel="stable",
                    workflow_selection_reason="explicit_workflow_selection",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json="",
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                with self.assertRaises(module.PolicyError):
                    enforcer.create_task(args)
            finally:
                enforcer.close()

    def test_complete_task_escalates_when_open_critical_incident_requires_human_help(self):
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
                enforcer.db.create_task(
                    {
                        "task_id": "todo-complete-gate-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "[TEST] complete-task incident gate",
                        "source": "unit-test",
                        "request_source": "human",
                        "priority": "medium",
                        "risk_level": "high",
                        "assignee": "backend-dev",
                        "status": "running",
                        "human_confirmed": True,
                        "requirement": "Critical incident should block task completion.",
                        "result_output": "Task completion is vetoed.",
                        "acceptance": "Open critical incident forces escalation.",
                        "observable_outputs": "task incident + standard output",
                        "acceptance_thresholds": "target_status=escalated",
                    },
                    actor="unit-test",
                )
                enforcer.db.record_token_usage(
                    task_id="todo-complete-gate-1",
                    agent_id="backend-dev",
                    model_id="openai-codex/gpt-5.4",
                    input_tokens=120,
                    output_tokens=30,
                    cost_estimate=0.0,
                    details={},
                )
                enforcer.db.record_task_output(
                    task_id="todo-complete-gate-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="suppressed",
                    summary="需要人工协助",
                    payload={
                        "human_gate": {
                            "need_human_confirm": False,
                            "human_confirmed": True,
                            "needs_clarification": False,
                            "clarification_reason": "",
                            "requires_human_assistance": True,
                            "notify_chat": False,
                        }
                    },
                    actor="backend-dev",
                )
                enforcer.db.record_task_incident(
                    task_id="todo-complete-gate-1",
                    incident_type="task_escalated",
                    severity="critical",
                    status="open",
                    reason="stage_contract_failed",
                    summary="仍需人工复核",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )

                updated = enforcer.complete_task(
                    argparse.Namespace(
                        task_id="todo-complete-gate-1",
                        result_score="96",
                        stability_score="95",
                        critical_pass="true",
                        actor="coordinator",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(updated["status"], "escalated")
        self.assertEqual(updated["action"], "escalate_human")
        self.assertFalse(updated["score_payload"]["critical_pass"])
        self.assertEqual(updated["score_payload"]["control_plane_gate"]["open_incident_count"], 1)
        self.assertEqual(updated["score_payload"]["control_plane_gate"]["critical_open_incident_count"], 1)
        self.assertTrue(updated["score_payload"]["control_plane_gate"]["requires_human_assistance"])

    def test_policy_enforcer_can_update_task_incident_status(self):
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
                enforcer.db.create_task(
                    {
                        "task_id": "todo-incident-cli-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "[TEST] update incident",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "high",
                        "assignee": "backend-dev",
                        "status": "running",
                        "human_confirmed": True,
                        "requirement": "Incident lifecycle should be editable.",
                        "result_output": "Incident updated.",
                        "acceptance": "Status changes survive CLI method.",
                        "observable_outputs": "task_incident row",
                        "acceptance_thresholds": "status=resolved",
                    },
                    actor="unit-test",
                )
                incident = enforcer.db.record_task_incident(
                    task_id="todo-incident-cli-1",
                    incident_type="stage_contract_failed",
                    severity="warning",
                    status="open",
                    reason="missing_verification",
                    summary="Need follow-up",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                updated = enforcer.update_task_incident(
                    argparse.Namespace(
                        incident_id=str(incident["id"]),
                        status="resolved",
                        reason="manual_verification_completed",
                        summary="已补齐验证",
                        owner="coordinator",
                        details_json=json.dumps({"resolution_note": "validated manually"}, ensure_ascii=False),
                        actor="coordinator",
                    )
                )
            finally:
                enforcer.close()

        self.assertEqual(updated["status"], "resolved")
        self.assertEqual(updated["reason"], "manual_verification_completed")
        self.assertEqual(updated["owner"], "coordinator")
        self.assertEqual(updated["details"]["resolution_note"], "validated manually")

    def test_policy_enforcer_create_task_auto_assigns_backend_dev_from_stage_capabilities(self):
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
                created = enforcer.create_task(
                    argparse.Namespace(
                        task_id="todo-capability-autobind-implement-1",
                        task_type="workflow",
                        reason="[TEST] capability auto binding implement",
                        source="unit-test",
                        request_source="human",
                        priority="medium",
                        risk_level="high",
                        pool="todo",
                        assignee="",
                        owner="",
                        change_id="",
                        entry_agent="",
                        need_human_confirm="false",
                        human_confirmed="true",
                        requirement="Need stage-driven task execution binding.",
                        result_output="Task created.",
                        acceptance="Implement stage should choose backend-dev by capability defaults.",
                        observable_outputs="resolved assignee + capability constraints",
                        acceptance_thresholds="assignee=backend-dev",
                        required_capabilities="",
                        required_skills="",
                        allowed_agents="",
                        workflow_profile_id="coding-default",
                        workflow_channel="stable",
                        workflow_selection_reason="explicit_workflow_selection",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        stage_id="implement",
                        context_json=json.dumps(
                            {
                                "problem": "Need implement-stage capability binding.",
                                "scope": "workflow runtime",
                                "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                                "constraints": "auto-select execution assignee from capability registry",
                                "acceptance_criteria": "implement stage binds to backend-dev",
                                "first_seen_at": "2026-03-23T00:00:00+08:00",
                                "impact": "implement stage stays on dispatcher instead of executor",
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

        self.assertEqual(created["assignee"], "backend-dev")
        self.assertEqual(created["stage_id"], "implement")
        self.assertIn("skill_backed", created["required_capabilities"])
        self.assertIn("task_execution", created["required_capabilities"])
        self.assertIn("routing", created["required_capabilities"])
        self.assertIn("backend-dev", created["allowed_agents"])
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["resolution_reason"],
            "capability_default_agent",
        )

    def test_policy_enforcer_create_task_auto_assigns_reviewer_from_review_stage_skills(self):
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
                created = enforcer.create_task(
                    argparse.Namespace(
                        task_id="todo-capability-autobind-review-1",
                        task_type="workflow",
                        reason="[TEST] capability auto binding review",
                        source="unit-test",
                        request_source="human",
                        priority="medium",
                        risk_level="high",
                        pool="todo",
                        assignee="",
                        owner="",
                        change_id="",
                        entry_agent="",
                        need_human_confirm="false",
                        human_confirmed="true",
                        requirement="Need stage-driven review binding.",
                        result_output="Task created.",
                        acceptance="Review stage should choose reviewer by required skills.",
                        observable_outputs="resolved assignee + review skill binding",
                        acceptance_thresholds="assignee=reviewer",
                        required_capabilities="",
                        required_skills="",
                        allowed_agents="",
                        workflow_profile_id="coding-default",
                        workflow_channel="stable",
                        workflow_selection_reason="explicit_workflow_selection",
                        workflow_selection_inputs_json="",
                        workflow_selection_inputs_file="",
                        stage_id="review",
                        context_json=json.dumps(
                            {
                                "problem": "Need review-stage capability binding.",
                                "scope": "workflow runtime",
                                "location": "scripts/openclaw-ops/policy/policy_enforcer.py",
                                "constraints": "auto-select reviewer from required review skill",
                                "acceptance_criteria": "review stage binds to reviewer",
                                "first_seen_at": "2026-03-23T00:00:00+08:00",
                                "impact": "review stage stays on dispatcher instead of reviewer",
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

        self.assertEqual(created["assignee"], "reviewer")
        self.assertEqual(created["stage_id"], "review")
        self.assertIn("skill_backed", created["required_capabilities"])
        self.assertIn("requesting-code-review", created["required_skills"])
        self.assertEqual(created["allowed_agents"], ["reviewer"])
        self.assertEqual(
            created["selection_inputs"]["capability_binding"]["resolution_reason"],
            "required_skills_binding",
        )

    def test_policy_enforcer_create_task_rejects_unknown_required_capability(self):
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
                    task_id="todo-invalid-capability-cli-1",
                    task_type="workflow",
                    reason="[TEST] invalid capability",
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
                    requirement="Unknown capability must fail.",
                    result_output="Task rejected.",
                    acceptance="Unknown capability triggers PolicyError.",
                    observable_outputs="policy error",
                    acceptance_thresholds="unknown capability is rejected",
                    required_capabilities="unknown_capability,skill_backed",
                    required_skills="requirements-clarity,task-decomposer",
                    allowed_agents="coordinator,main",
                    workflow_profile_id="",
                    workflow_channel="",
                    workflow_selection_reason="",
                    workflow_selection_inputs_json="",
                    workflow_selection_inputs_file="",
                    context_json="",
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="",
                    actor="policy-enforcer",
                )
                with self.assertRaises(module.PolicyError):
                    enforcer.create_task(args)
            finally:
                enforcer.close()


if __name__ == "__main__":
    unittest.main()

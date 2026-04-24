import argparse
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    ROOT
    / "skills"
    / "library"
    / "project-delivery-pipeline"
    / "scripts"
    / "pipeline_runner.py"
)
POLICY_WORKFLOW_PATH = (
    ROOT
    / "skills"
    / "library"
    / "control-plane-ops"
    / "scripts"
    / "policy"
    / "policy_workflow.py"
)
_spec = importlib.util.spec_from_file_location("project_delivery_pipeline_runner", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

PipelineConfig = _mod.PipelineConfig
run_pipeline = _mod.run_pipeline


def load_policy_workflow_module():
    sys.path.insert(0, str(POLICY_WORKFLOW_PATH.parent))
    try:
        spec = importlib.util.spec_from_file_location("project_delivery_policy_workflow", POLICY_WORKFLOW_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("project_delivery_policy_workflow", None)
        sys.path.pop(0)


class ProjectDeliveryPipelineRunnerTests(unittest.TestCase):
    def test_dry_run_happy_path_creates_required_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the full coding delivery pipeline.",
                    workspace_root=Path(tmp),
                    run_id="happy",
                    dry_run=True,
                )
            )

            run_dir = Path(tmp) / "happy"
            self.assertEqual("completed", state["status"])
            self.assertEqual("none", state["next_action"])
            for name in (
                "run_meta",
                "context_snapshot",
                "project_memory_context",
                "external_research",
                "requirements_package",
                "requirements_review",
                "solution_package",
                "solution_review",
                "code_execution",
                "verification",
                "code_review",
                "acceptance",
                "writeback",
                "failure_learning_check",
            ):
                self.assertIn(name, state["artifacts"])
                self.assertTrue(Path(state["artifacts"][name]).exists(), name)
            self.assertTrue((run_dir / "pipeline_state.json").exists())
            memory_dir = Path(tmp) / "project-memory" / "demo"
            self.assertTrue((memory_dir / "RETRIEVAL_MANIFEST.json").exists())

    def test_requirements_failure_routes_back_to_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build something ambiguous.",
                    workspace_root=Path(tmp),
                    run_id="requirements-failure",
                    dry_run=True,
                    simulate_failure_stage="requirements",
                )
            )

            run_dir = Path(tmp) / "requirements-failure"
            self.assertEqual("blocked", state["status"])
            self.assertEqual("requirements_review", state["failed_stage"])
            self.assertEqual("revise_requirements", state["next_action"])
            self.assertTrue((run_dir / "requirements_review.md").exists())
            self.assertFalse((run_dir / "solution.md").exists())

    def test_acceptance_requirement_failure_routes_to_requirement_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline but acceptance criteria are wrong.",
                    workspace_root=Path(tmp),
                    run_id="acceptance-requirement-failure",
                    dry_run=True,
                    simulate_failure_stage="acceptance_requirement",
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("acceptance", state["failed_stage"])
            self.assertEqual("revise_requirements", state["next_action"])
            self.assertIn("delivery_evidence", state["artifacts"])

    def test_hermes_runtime_home_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline in Hermes.",
                    workspace_root=Path(tmp),
                    run_id="hermes-runtime",
                    runtime_host="hermes",
                    runtime_home="/home/ubuntu/.hermes",
                    dry_run=True,
                )
            )

            runtime = state["runtime_context"]
            self.assertEqual("hermes", runtime["host"])
            self.assertEqual("/home/ubuntu/.hermes", runtime["runtime_home"])
            self.assertEqual("/home/ubuntu/.hermes/.workflow/pipeline-runs", runtime["state_dir"])

    def test_custom_runtime_host_with_explicit_home_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline in a custom runtime.",
                    workspace_root=Path(tmp),
                    run_id="custom-runtime",
                    runtime_host="my-runtime",
                    runtime_home="/srv/my-runtime",
                    dry_run=True,
                )
            )

            runtime = state["runtime_context"]
            self.assertEqual("my-runtime", runtime["host"])
            self.assertEqual("/srv/my-runtime", runtime["runtime_home"])
            self.assertEqual("/srv/my-runtime/.workflow/pipeline-runs", runtime["state_dir"])

    def test_project_memory_module_is_bootstrapped_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_root = Path(tmp) / "project-memory"
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Add a project memory retrieval gate.",
                    workspace_root=Path(tmp) / "runs",
                    project_memory_root=memory_root,
                    run_id="memory",
                    dry_run=True,
                )
            )

            memory_dir = memory_root / "demo"
            self.assertEqual("completed", state["status"])
            for name in (
                "PROJECT_PROFILE.md",
                "DECISIONS.md",
                "DELIVERY_RULES.md",
                "API_REGISTRY.json",
                "SOURCE_REGISTRY.json",
                "IMPACT_MAP.json",
                "RETRIEVAL_MANIFEST.json",
            ):
                self.assertTrue((memory_dir / name).exists(), name)
            context = Path(state["artifacts"]["project_memory_context"]).read_text(encoding="utf-8")
            self.assertIn("Anti Local-Optimum Rule", context)

    def test_task_center_mirror_records_pipeline_task_and_stage_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "task_center.db"
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Record pipeline runs in task center.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="task-center",
                    dry_run=True,
                    record_task_center=True,
                    task_center_db=db_path,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertEqual("project-delivery:task-center", state["task_center"]["task_id"])
            conn = sqlite3.connect(db_path)
            try:
                task_count = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                stage_count = conn.execute(
                    "SELECT COUNT(*) FROM stage_runs WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                comm_count = conn.execute(
                    "SELECT COUNT(*) FROM module_communications WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                output_count = conn.execute(
                    "SELECT COUNT(*) FROM task_outputs WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(1, task_count)
            self.assertGreaterEqual(stage_count, 13)
            self.assertGreaterEqual(comm_count, 13)
            self.assertEqual(1, output_count)

    def test_legacy_hardflow_score_policy_ref_resolves_after_skillization(self):
        module = load_policy_workflow_module()
        resolved = module.WorkflowMixin._resolve_repo_ref_path("scripts/hardflow/score-policy.json")

        self.assertTrue(resolved.exists())
        self.assertEqual("score-policy.json", resolved.name)
        self.assertIn("openclaw-hardflow-automation", resolved.parts)

    def test_view_without_state_or_task_center_fails_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-runs"
            with self.assertRaises(_mod.PipelineError) as ctx:
                _mod.build_view_payload(
                    argparse.Namespace(
                        workspace_root=missing,
                        run_id=None,
                        task_center_db=None,
                        task_id=None,
                        event_limit=100,
                    )
                )

        self.assertIn("workspace root not found", str(ctx.exception))

    def test_live_command_adapters_complete_and_write_project_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            research_script = scripts_dir / "research.py"
            code_script = scripts_dir / "code.py"
            verify_script = scripts_dir / "verify.py"
            review_script = scripts_dir / "review.py"
            research_script.write_text("print('# Research\\n- Source: official docs checked')\n", encoding="utf-8")
            code_script.write_text("print('# Patch Summary\\n- Implemented by live command adapter')\n", encoding="utf-8")
            verify_script.write_text("print('verification passed')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass\\nConfidence: high')\n", encoding="utf-8")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live command adapters.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="live-adapter",
                    dry_run=False,
                    research_commands=(py_cmd(research_script),),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(verify_script),),
                    code_review_command=py_cmd(review_script),
                    write_project_memory=True,
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertIn("command_external_research_1", state["artifacts"])
            self.assertIn("command_code_execution_1", state["artifacts"])
            self.assertIn("command_verification_1", state["artifacts"])
            self.assertIn("command_code_review_1", state["artifacts"])
            self.assertIn("memory_writeback", state["artifacts"])
            review = Path(state["artifacts"]["code_review"]).read_text(encoding="utf-8")
            self.assertIn("Final verdict: pass", review)
            command_report = json.loads(Path(state["artifacts"]["command_verification_1"]).read_text(encoding="utf-8"))
            self.assertTrue(command_report["ok"])
            changelog = root / "memory" / "demo" / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            self.assertIn("project-delivery:live-adapter", changelog.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

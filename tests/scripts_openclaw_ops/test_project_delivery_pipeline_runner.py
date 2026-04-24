import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "library"
    / "project-delivery-pipeline"
    / "scripts"
    / "pipeline_runner.py"
)
_spec = importlib.util.spec_from_file_location("project_delivery_pipeline_runner", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

PipelineConfig = _mod.PipelineConfig
run_pipeline = _mod.run_pipeline


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


if __name__ == "__main__":
    unittest.main()

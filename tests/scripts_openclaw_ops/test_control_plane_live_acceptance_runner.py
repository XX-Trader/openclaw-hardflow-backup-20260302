import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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


class ControlPlaneLiveAcceptanceRunnerTests(unittest.TestCase):
    def test_main_executes_live_acceptance_chain_and_writes_outputs(self):
        module = load_module(
            "control_plane_live_acceptance_runner",
            "scripts/openclaw-ops/control_plane_live_acceptance_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "live-acceptance"
            json_output = workspace_root / "latest-report.json"
            markdown_output = workspace_root / "latest-report.md"

            with redirect_stdout(StringIO()):
                payload = module.main(
                    [
                        "--workspace-root",
                        str(workspace_root),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")
            report = payload["report"]
            install_surface = report["steps"]["install_surface"]
            install_surface_jobs_file_exists = Path(install_surface["jobs_file"]).exists()
            advisor_exists = Path(report["steps"]["optimization_advisor"]["json_output"]).exists()
            dispatch_exists = Path(report["steps"]["optimization_dispatch"]["json_output"]).exists()
            review_exists = Path(report["steps"]["optimization_review"]["json_output"]).exists()
            profile_update_dispatch_exists = Path(report["steps"]["profile_update_dispatch"]["json_output"]).exists()
            profile_update_apply_exists = Path(report["steps"]["profile_update_apply"]["json_output"]).exists()
            profile_update_validation_exists = Path(report["steps"]["profile_update_validation"]["json_output"]).exists()
            summary_exists = Path(report["steps"]["control_plane_summary"]["output"]).exists()
            task_output_exists = Path(report["steps"]["task_output_consumer"]["output"]).exists()
            benchmark_output_exists = Path(report["steps"]["benchmark_output_consumer"]["output"]).exists()
            dashboard_exists = Path(report["steps"]["control_plane_dashboard"]["json_output"]).exists()
            dashboard_html_exists = Path(report["steps"]["control_plane_dashboard"]["html_output"]).exists()
            acceptance_exists = Path(report["steps"]["control_plane_acceptance"]["json_output"]).exists()
            installed_job_replay = report["steps"]["installed_job_replay"]

        self.assertTrue(report["passed"])
        self.assertEqual(install_surface["status"], "passed")
        self.assertEqual(report["jobs_file_generation_mode"], "install_surface")
        self.assertTrue(install_surface_jobs_file_exists)
        self.assertIn("cron_setup.py", install_surface["install_command"])
        self.assertGreaterEqual(report["dispatch_created_count"], 1)
        self.assertEqual(report["seeded_task_count"], 2)
        self.assertEqual(report["steps"]["optimization_advisor"]["status"], "passed")
        self.assertEqual(report["steps"]["optimization_dispatch"]["status"], "passed")
        self.assertEqual(report["steps"]["optimization_review"]["status"], "passed")
        self.assertEqual(report["steps"]["profile_update_dispatch"]["status"], "passed")
        self.assertEqual(report["steps"]["profile_update_apply"]["status"], "passed")
        self.assertEqual(report["steps"]["profile_update_validation"]["status"], "passed")
        self.assertEqual(report["steps"]["control_plane_summary"]["status"], "passed")
        self.assertEqual(report["steps"]["task_output_consumer"]["status"], "passed")
        self.assertEqual(report["steps"]["benchmark_output_consumer"]["status"], "passed")
        self.assertEqual(report["steps"]["control_plane_dashboard"]["status"], "passed")
        self.assertEqual(report["steps"]["control_plane_acceptance"]["status"], "passed")
        self.assertEqual(installed_job_replay["status"], "passed")
        self.assertGreaterEqual(int(installed_job_replay["executed_job_count"]), 3)
        self.assertGreaterEqual(int(report["installed_job_replay_executed_count"]), 3)
        self.assertIn("ops_control_plane_summary_6h", installed_job_replay["executed_job_names"])
        self.assertIn("ops_control_plane_dashboard_6h", installed_job_replay["executed_job_names"])
        self.assertIn("# OpenClaw Control Plane Live Acceptance", markdown_text)
        self.assertTrue(advisor_exists)
        self.assertTrue(dispatch_exists)
        self.assertTrue(review_exists)
        self.assertTrue(profile_update_dispatch_exists)
        self.assertTrue(profile_update_apply_exists)
        self.assertTrue(profile_update_validation_exists)
        self.assertTrue(summary_exists)
        self.assertTrue(task_output_exists)
        self.assertTrue(benchmark_output_exists)
        self.assertTrue(dashboard_exists)
        self.assertTrue(dashboard_html_exists)
        self.assertTrue(acceptance_exists)
        self.assertIn("report", json_payload)
        self.assertTrue(json_payload["report"]["passed"])


if __name__ == "__main__":
    unittest.main()

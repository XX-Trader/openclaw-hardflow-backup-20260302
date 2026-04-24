import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "skills/library/project-delivery-pipeline/scripts/runtime_installer.py"


def load_module():
    spec = importlib.util.spec_from_file_location("project_delivery_runtime_installer", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProjectDeliveryRuntimeInstallerTests(unittest.TestCase):
    def test_install_runtime_accepts_arbitrary_runtime_home_and_merges_jobs(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_home = tmp / "my-runtime"
            cron_file = runtime_home / "cron" / "jobs.json"
            cron_file.parent.mkdir(parents=True, exist_ok=True)
            cron_file.write_text(
                json.dumps(
                    {
                        "version": "existing",
                        "jobs": [
                            {
                                "id": "keep-me",
                                "name": "existing_job",
                                "payload": {"message": "Run command only: python3 keep.py"},
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            config = module.InstallConfig(
                runtime_home=runtime_home,
                runtime_name="my-runtime",
                repo_root=ROOT,
                skills_dir=runtime_home / "skills",
                ops_dir=runtime_home / "ops",
                cron_file=cron_file,
                state_dir=runtime_home / ".workflow" / "pipeline-runs",
                project_memory_dir=runtime_home / ".workflow" / "project-memory",
                task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
                job_names=("system_exception_to_task_bridge", "todo_deadline_to_task_bridge_daily"),
            )
            report = module.install_runtime(config)

            self.assertTrue(report.ok)
            self.assertTrue((runtime_home / "skills" / "project-delivery-pipeline" / "SKILL.md").exists())
            self.assertTrue((runtime_home / "skills" / "control-plane-ops" / "scripts" / "policy" / "task_center.py").exists())
            self.assertTrue((runtime_home / "ops" / "pipeline_runner.py").exists())
            self.assertTrue((runtime_home / "ops" / "project_delivery_pipeline.py").exists())
            self.assertTrue((runtime_home / "ops" / "hermes_profile_smoke.py").exists())
            self.assertTrue((runtime_home / "ops" / "deadline_to_task_bridge.py").exists())
            self.assertTrue((runtime_home / "ops" / "exception_to_task_bridge.py").exists())
            self.assertTrue((runtime_home / "ops" / "project_memory_writer.py").exists())
            self.assertTrue((runtime_home / "ops" / "policy" / "human_inbox.py").exists())

            jobs = json.loads(cron_file.read_text(encoding="utf-8"))["jobs"]
            names = {job["name"] for job in jobs}
            self.assertIn("existing_job", names)
            self.assertIn("system_exception_to_task_bridge", names)
            self.assertIn("todo_deadline_to_task_bridge_daily", names)
            rendered = "\n".join(str((job.get("payload") or {}).get("message", "")) for job in jobs)
            self.assertIn(str(runtime_home).replace("\\", "/"), rendered)
            self.assertNotIn("$HOME/.openclaw", rendered)

    def test_dry_run_does_not_create_runtime_home(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_home = Path(tmpdir) / "dry-runtime"
            config = module.InstallConfig(
                runtime_home=runtime_home,
                runtime_name="dry-runtime",
                repo_root=ROOT,
                skills_dir=runtime_home / "skills",
                ops_dir=runtime_home / "ops",
                cron_file=runtime_home / "cron" / "jobs.json",
                state_dir=runtime_home / ".workflow" / "pipeline-runs",
                project_memory_dir=runtime_home / ".workflow" / "project-memory",
                task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
                dry_run=True,
            )
            report = module.install_runtime(config)

            self.assertTrue(report.ok)
            self.assertTrue(report.changed)
            self.assertFalse(runtime_home.exists())


if __name__ == "__main__":
    unittest.main()

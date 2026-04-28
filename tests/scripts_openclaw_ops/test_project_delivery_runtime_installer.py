import importlib.util
import json
import os
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


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
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
                job_names=(
                    "system_exception_to_task_bridge",
                    "todo_deadline_to_task_bridge_daily",
                    "backlog_runner_30m（持续推进待办）",
                ),
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
            self.assertTrue((runtime_home / "ops" / "repo_hygiene_reviewer.py").exists())
            self.assertTrue((runtime_home / "ops" / "backlog_runner.py").exists())
            self.assertTrue((runtime_home / "ops" / "project_memory_writer.py").exists())
            self.assertTrue((runtime_home / "ops" / "smart_arb_live_bridge.py").exists())
            self.assertTrue((runtime_home / "ops" / "smart_arb_pipeline_entry.py").exists())
            self.assertTrue((runtime_home / "ops" / "chat_output.py").exists())
            self.assertTrue((runtime_home / "ops" / "utf8_runtime.py").exists())
            self.assertTrue((runtime_home / "ops" / "workflow_views.py").exists())
            self.assertTrue(os.access(runtime_home / "ops" / "smart_arb_pipeline_entry.py", os.X_OK))
            self.assertTrue((runtime_home / "ops" / "policy" / "human_inbox.py").exists())

            jobs = json.loads(cron_file.read_text(encoding="utf-8"))["jobs"]
            names = {job["name"] for job in jobs}
            self.assertIn("existing_job", names)
            self.assertIn("system_exception_to_task_bridge", names)
            self.assertIn("todo_deadline_to_task_bridge_daily", names)
            self.assertIn("backlog_runner_30m（持续推进待办）", names)
            installed_jobs = [
                job
                for job in jobs
                if job["name"]
                in {
                    "system_exception_to_task_bridge",
                    "todo_deadline_to_task_bridge_daily",
                    "backlog_runner_30m（持续推进待办）",
                }
            ]
            self.assertEqual(3, len(installed_jobs))
            for job in installed_jobs:
                self.assertEqual("discord", job.get("delivery", {}).get("channel"))
                self.assertEqual("1494595527181078578", job.get("delivery", {}).get("to"))
                self.assertEqual("discord", job.get("failureAlert", {}).get("channel"))
                self.assertEqual("1494595527181078578", job.get("failureAlert", {}).get("to"))
            rendered = "\n".join(str((job.get("payload") or {}).get("message", "")) for job in jobs)
            runtime_text = str(runtime_home).replace("\\", "/")
            self.assertIn(runtime_text, rendered)
            self.assertNotIn("$HOME/.openclaw", rendered)
            self.assertNotIn("../.local/bin/smart-arb-pipeline", rendered)
            self.assertIn(
                f'--pipeline-command "python3 {runtime_text}/ops/smart_arb_pipeline_entry.py"',
                rendered,
            )

    def test_installed_ops_smoke_resolves_ops_policy_dir(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_home = tmp / "hermes"
            fixture_repo = tmp / "repo"
            fixture_repo.mkdir()
            (fixture_repo / "README.md").write_text("# Smoke\n", encoding="utf-8")
            import subprocess

            git_kwargs = {"cwd": fixture_repo, "check": True, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
            subprocess.run(["git", "init", "-b", "main"], **git_kwargs)
            subprocess.run(["git", "config", "user.name", "HardFlow Test"], **git_kwargs)
            subprocess.run(["git", "config", "user.email", "hardflow-test@example.invalid"], **git_kwargs)
            subprocess.run(["git", "add", "."], **git_kwargs)
            subprocess.run(["git", "commit", "-m", "初始化"], **git_kwargs)
            config = module.InstallConfig(
                runtime_home=runtime_home,
                runtime_name="hermes",
                repo_root=ROOT,
                skills_dir=runtime_home / "skills",
                ops_dir=runtime_home / "ops",
                cron_file=runtime_home / "cron" / "jobs.json",
                state_dir=runtime_home / ".workflow" / "pipeline-runs",
                project_memory_dir=runtime_home / ".workflow" / "project-memory",
                task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
            )
            report = module.install_runtime(config)
            self.assertTrue(report.ok)

            for module_name in (
                "task_executor_runner",
                "policy_enforcer",
                "policy_cli",
                "policy_utils",
                "task_center",
                "utf8_runtime",
                "chat_output",
                "workflow_views",
            ):
                sys.modules.pop(module_name, None)
            installed_task_executor = load_module_from_path(
                "task_executor_runner",
                runtime_home / "ops" / "policy" / "task_executor_runner.py",
            )
            self.assertEqual(
                "agent_returned_no_structured_output",
                installed_task_executor.contract_from_agent_result(0, "", "")[0]["resolution_summary"],
            )

            installed_runner = load_module_from_path(
                "installed_project_delivery_pipeline_runner",
                runtime_home / "ops" / "pipeline_runner.py",
            )
            self.assertEqual(
                (runtime_home / "ops" / "policy").resolve(),
                installed_runner.policy_dir().resolve(),
            )

            installed_smoke = load_module_from_path(
                "installed_project_delivery_hermes_profile_smoke",
                runtime_home / "ops" / "hermes_profile_smoke.py",
            )
            smoke_report = installed_smoke.run_smoke(
                installed_smoke.SmokeConfig(
                    project_key="demo",
                    runtime_home=runtime_home,
                    workspace_root=tmp / "runs",
                    project_memory_root=runtime_home / ".workflow" / "project-memory",
                    task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
                    run_id="s",
                    command_cwd=fixture_repo,
                    agent_mode="echo",
                )
            )

            self.assertTrue(smoke_report["ok"])

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

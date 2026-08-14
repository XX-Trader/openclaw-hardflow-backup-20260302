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
                notification_channel="test-channel",
                notification_target="test-target",
                timezone="Etc/UTC",
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
            self.assertTrue((runtime_home / "ops" / "live_runtime_bridge.py").exists())
            self.assertTrue((runtime_home / "ops" / "project_pipeline_entry.py").exists())
            self.assertTrue((runtime_home / "ops" / "chat_output.py").exists())
            self.assertTrue((runtime_home / "ops" / "utf8_runtime.py").exists())
            self.assertTrue((runtime_home / "ops" / "workflow_views.py").exists())
            self.assertTrue(os.access(runtime_home / "ops" / "project_pipeline_entry.py", os.X_OK))
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
                self.assertEqual("test-channel", job.get("delivery", {}).get("channel"))
                self.assertEqual("test-target", job.get("delivery", {}).get("to"))
                self.assertEqual("test-channel", job.get("failureAlert", {}).get("channel"))
                self.assertEqual("test-target", job.get("failureAlert", {}).get("to"))
            cron_jobs = [job for job in installed_jobs if (job.get("schedule") or {}).get("kind") == "cron"]
            self.assertTrue(cron_jobs)
            self.assertTrue(all(job["schedule"]["tz"] == "Etc/UTC" for job in cron_jobs))
            rendered = "\n".join(str((job.get("payload") or {}).get("message", "")) for job in jobs)
            runtime_text = str(runtime_home).replace("\\", "/")
            self.assertIn(runtime_text, rendered)
            self.assertNotIn("$HOME/.openclaw", rendered)
            self.assertNotIn("../.local/bin/project-delivery-pipeline", rendered)
            self.assertIn(
                f'--pipeline-command "python3 {runtime_text}/ops/project_pipeline_entry.py"',
                rendered,
            )
            self.assertIn("--allow-confirmed-high-risk", rendered)

            first_manifest = Path(report.manifest_file).read_text(encoding="utf-8")
            second_report = module.install_runtime(config)
            second_manifest = Path(second_report.manifest_file).read_text(encoding="utf-8")
            self.assertTrue(second_report.ok)
            self.assertFalse(second_report.changed)
            self.assertEqual(first_manifest, second_manifest)
            self.assertIn("task_center.py", second_report.installed_policy_files)

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
            installed_jobs = json.loads(config.cron_file.read_text(encoding="utf-8"))["jobs"]
            self.assertTrue(installed_jobs)
            self.assertTrue(all("delivery" not in job and "failureAlert" not in job for job in installed_jobs))

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

    def test_install_upgrade_and_chained_rollback_restore_previous_state(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_home = tmp / "rollback-runtime"
            config = module.InstallConfig(
                runtime_home=runtime_home,
                runtime_name="rollback-runtime",
                repo_root=ROOT,
                skills_dir=runtime_home / "skills",
                ops_dir=runtime_home / "ops",
                cron_file=runtime_home / "cron" / "jobs.json",
                state_dir=runtime_home / ".workflow" / "pipeline-runs",
                project_memory_dir=runtime_home / ".workflow" / "project-memory",
                task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
            )

            first = module.install_runtime(config)
            self.assertTrue(first.ok)
            self.assertTrue(first.changed)
            self.assertTrue(Path(first.rollback_snapshot, "snapshot.json").is_file())
            target = runtime_home / "ops" / "project_pipeline_entry.py"
            original = target.read_text(encoding="utf-8")
            unrelated = runtime_home / "keep.txt"
            unrelated.write_text("preserve me\n", encoding="utf-8")

            repeated = module.install_runtime(config)
            self.assertTrue(repeated.ok)
            self.assertFalse(repeated.changed)
            self.assertEqual(first.rollback_snapshot, repeated.rollback_snapshot)

            upgraded_source = tmp / "project_pipeline_entry_v2.py"
            upgraded_source.write_text(original + "\n# fixture upgrade\n", encoding="utf-8")
            module.OPS_SCRIPT_MAP = dict(module.OPS_SCRIPT_MAP)
            module.OPS_SCRIPT_MAP["project_pipeline_entry.py"] = str(upgraded_source)
            upgraded = module.install_runtime(config)
            self.assertTrue(upgraded.ok)
            self.assertTrue(upgraded.changed)
            self.assertNotEqual(first.rollback_snapshot, upgraded.rollback_snapshot)
            self.assertIn("# fixture upgrade", target.read_text(encoding="utf-8"))

            restored = module.rollback_runtime(config)
            self.assertTrue(restored.ok)
            self.assertTrue(restored.rolled_back)
            self.assertTrue(restored.changed)
            self.assertEqual(original, target.read_text(encoding="utf-8"))
            restored_manifest = json.loads(Path(restored.manifest_file).read_text(encoding="utf-8"))
            self.assertEqual(first.rollback_snapshot, restored_manifest["rollback_snapshot"])
            self.assertEqual("preserve me\n", unrelated.read_text(encoding="utf-8"))

            removed = module.rollback_runtime(config)
            self.assertTrue(removed.ok)
            self.assertTrue(removed.rolled_back)
            self.assertFalse(target.exists())
            self.assertFalse(Path(removed.manifest_file).exists())
            self.assertEqual("preserve me\n", unrelated.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

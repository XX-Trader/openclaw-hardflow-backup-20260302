import importlib.util
import subprocess
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
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class CronQuietModeTests(unittest.TestCase):
    def test_task_executor_quiet_when_no_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "run_id": "exec-1",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 1,
            "tasks_executed": 0,
            "tasks_skipped": 1,
            "tasks_failed": 0,
            "results": [
                {
                    "task_id": "cron:ops-github-web-evolution",
                    "status": "skipped",
                    "reason": "needs_clarification",
                }
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertEqual(output, "NO_REPLY")

    def test_task_executor_reports_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "run_id": "exec-2",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 0,
            "tasks_failed": 2,
            "results": [
                {"task_id": "todo-1", "status": "failed", "reason": "pre_stage_failed:model blocked"},
                {"task_id": "todo-2", "status": "failed", "reason": "report_failed:timeout"},
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertIn("task-executor", output)
        self.assertIn("todo-1", output)
        self.assertIn("report.json", output)

    def test_web_collect_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", failed_count=0, changed_count=3))
        self.assertFalse(module.should_quiet("silent", "error", failed_count=1, changed_count=0))

    def test_web_review_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", changed_count=2))
        self.assertFalse(module.should_quiet("chat", "error", changed_count=2))

    def test_project_index_command_omits_git_pull_by_default(self):
        module = load_module(
            "install_project_index_job",
            "scripts/openclaw-ops/install_project_index_job.py",
        )
        command = module.build_runner_command(
            maintainer_py="/home/ubuntu/.openclaw/ops/policy/project_index_maintainer.py",
            registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            task_id="cron:project-index-maintainer-30m",
            actor="project-agent",
            git_pull=False,
        )
        self.assertNotIn("--git-pull", command)

    def test_task_executor_message_uses_notify_on_error(self):
        module = load_module(
            "install_task_executor_job",
            "scripts/openclaw-ops/install_task_executor_job.py",
        )
        message = module.build_message(
            executor_py="/home/ubuntu/.openclaw/ops/policy/task_executor_runner.py",
            db_path="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            max_tasks=3,
            model="",
            actor="coordinator",
            planner_id="coordinator",
            openclaw_bin="openclaw",
            report_dir="/home/ubuntu/.openclaw/ops/task-center/executor-runs",
            local_agent=True,
            notify_on="error",
        )
        self.assertIn("--notify-on error", message)
        self.assertNotIn("--emit-json", message)

    def test_cron_setup_hardens_project_index_without_git_pull(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        jobs = [
            {
                "id": "job-project-index",
                "name": "project_index_maintainer_30m",
                "enabled": True,
                "payload": {"kind": "agentTurn", "message": "old"},
            }
        ]
        result = module.harden_known_jobs(jobs, Path("/home/ubuntu/.openclaw"))
        self.assertEqual(result["status"]["project_index_maintainer_30m"], "hardened")
        self.assertNotIn("--git-pull", jobs[0]["payload"]["message"])

    def test_install_workflow_profile_task_executor_cmd_pins_error_only_notify(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_task_executor_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            every_ms=600000,
            max_tasks=3,
            model="auto",
            local_agent=True,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--notify-on error", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_project_index_cmd_disables_git_pull(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_project_index_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            project_registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            every_ms=1800000,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--no-git-pull", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_web_intel_cmd_uses_error_only_notify(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_web_intel_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            openclaw_home="/home/ubuntu/.openclaw",
            collect_every_ms=3600000,
            opt_review_every_ms=14400000,
            project_review_every_ms=21600000,
            collect_min_interval_minutes=60,
            review_min_interval_minutes=180,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--collect-notify-on error", rendered)
        self.assertIn("--review-notify-on error", rendered)

    def test_install_workflow_profile_dry_run_uses_hardened_runtime_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            openclaw_home = tmp / "openclaw-home"
            workflow_repo = tmp / "workflow-repo"
            openclaw_home.mkdir(parents=True)
            workflow_repo.mkdir(parents=True)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/openclaw-ops/install_workflow_profile.py"),
                    "--profile",
                    "all",
                    "--jobs-file",
                    str(tmp / "jobs.json"),
                    "--openclaw-home",
                    str(openclaw_home),
                    "--workflow-repo-path",
                    str(workflow_repo),
                    "--project-registry",
                    str(tmp / "project-registry.json"),
                    "--task-db",
                    str(tmp / "task_center.db"),
                    "--channel",
                    "telegram",
                    "--to",
                    "-1003333097130",
                    "--install-web-intel-jobs",
                    "--no-sync-overlay-config",
                    "--no-normalize-openclaw-paths",
                    "--dry-run",
                    "--emit-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=ROOT,
            )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("--notify-on error", proc.stdout)
        self.assertIn("--no-git-pull", proc.stdout)
        self.assertIn("--collect-notify-on error", proc.stdout)
        self.assertIn("--review-notify-on error", proc.stdout)


if __name__ == "__main__":
    unittest.main()

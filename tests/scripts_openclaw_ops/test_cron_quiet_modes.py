import contextlib
import io
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


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
        self.assertIn("任务执行异常", output)
        self.assertIn("todo-1", output)
        self.assertIn("report.json", output)

    def test_task_executor_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-2",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 0,
            "tasks_failed": 2,
            "results": [
                {
                    "task_id": "todo-1",
                    "assignee": "backend-dev",
                    "status": "failed",
                    "reason": "pre_stage_failed:model blocked by policy: volcengine/kimi-k2.5",
                },
                {
                    "task_id": "todo-2",
                    "assignee": "backend-dev",
                    "status": "failed",
                    "reason": "report_failed:timeout",
                },
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertIn("任务执行异常", output)
        self.assertIn("模型被策略拦截", output)
        self.assertIn("volcengine/kimi-k2.5", output)
        self.assertIn("执行结果回写失败", output)
        self.assertNotIn("# task-executor", output)

    def test_web_collect_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", failed_count=0, changed_count=3))
        self.assertFalse(module.should_quiet("silent", "error", failed_count=1, changed_count=0))

    def test_web_collect_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        output = module.build_output(
            sender_identity="web-agent/web-intel-collect",
            task_id="cron:web-intel-collect",
            started_at="2026-03-06T10:00:00+00:00",
            total=5,
            scanned=3,
            changed=0,
            skipped=2,
            failed=1,
            report_file=Path("/tmp/web_collect.json"),
            changed_ids=[],
            failed_items=[
                {
                    "id": "openai-responses-doc",
                    "status": "failed",
                    "error": "http_error:429",
                    "status_code": 429,
                }
            ],
        )
        self.assertIn("网页情报采集异常", output)
        self.assertIn("openai-responses-doc", output)
        self.assertIn("429", output)
        self.assertEqual(output.splitlines()[0], "网页情报采集异常")

    def test_web_review_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", changed_count=2))
        self.assertFalse(module.should_quiet("chat", "error", changed_count=2))

    def test_web_review_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        output = module.build_failure_output(
            mode="optimization",
            sender_identity="optimization-agent/web-intel-review",
            task_id="cron:web-intel-review-optimization",
            started_at="2026-03-06T10:00:00+00:00",
            error_text="parsed_dir_missing:/home/ubuntu/.openclaw/web/parsed",
        )
        self.assertIn("网页情报复核异常", output)
        self.assertIn("optimization", output)
        self.assertIn("解析结果目录缺失", output)
        self.assertEqual(output.splitlines()[0], "网页情报复核异常")

    def test_local_git_backup_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "local_git_backup_runner",
            "scripts/openclaw-ops/local_git_backup_runner.py",
        )
        output = module.build_chat_output(
            {
                "time": "2026-03-06T10:00:00+00:00",
                "task_id": "cron:ops-local-openclaw-git-backup",
                "repo": "/home/ubuntu/.openclaw",
                "initialized": False,
                "gitignore_updated": False,
                "committed": False,
                "commit_sha": "",
                "eligible_files": [],
                "skipped_files": [],
                "errors": ["git_commit_failed:permission denied"],
            },
            "errors-only",
        )
        self.assertEqual(output.splitlines()[0], "本地 Git 备份异常")
        self.assertIn("Git 提交失败", output)
        self.assertIn("permission denied", output)
        self.assertNotIn("# local-git-backup", output)

    def test_todo_patrol_stays_quiet_when_only_dispatched_tasks_changed(self):
        module = load_module(
            "todo_patrol",
            "scripts/openclaw-ops/todo_patrol.py",
        )
        output = module.format_dispatch_message(
            task="cron:todo-patrol",
            todo_file=Path("/tmp/TODO.md"),
            dispatched=[
                {
                    "task": {
                        "task_id": "todo-1",
                        "assignee": "backend-dev",
                        "priority": "medium",
                        "risk_level": "low",
                        "context_completeness": 100,
                    }
                }
            ],
            skipped_count=0,
            ops_incident_skipped_count=0,
            skip_ops_incidents=True,
            db_path=Path("/tmp/task_center.db"),
            state_file=Path("/tmp/todo_patrol_state.json"),
            dispatch_errors=[],
            planner_summary=None,
            output_mode="summary",
        )
        self.assertEqual(output, "NO_REPLY")

    def test_todo_patrol_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "todo_patrol",
            "scripts/openclaw-ops/todo_patrol.py",
        )
        output = module.format_dispatch_message(
            task="cron:todo-patrol",
            todo_file=Path("/tmp/TODO.md"),
            dispatched=[],
            skipped_count=0,
            ops_incident_skipped_count=0,
            skip_ops_incidents=True,
            db_path=Path("/tmp/task_center.db"),
            state_file=Path("/tmp/todo_patrol_state.json"),
            dispatch_errors=["planner_summary_failed:database locked"],
            planner_summary=None,
            output_mode="summary",
        )
        self.assertEqual(output.splitlines()[0], "任务巡检异常")
        self.assertIn("规划器摘要读取失败", output)
        self.assertIn("database locked", output)
        self.assertNotIn("# todo-patrol", output)
        self.assertNotIn("- error:", output)

    def test_reviewer_context_gate_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        module.discover_git_repos = lambda _workspace: [Path("/tmp/repo-a")]
        module.ensure_project_context_gate = lambda _args, _mode, _repos: {
            "ok": False,
            "blocked": 1,
            "created": 0,
            "pending": 1,
            "ready": 0,
            "error": "task center unavailable",
            "items": [{"repo": "repo-a", "status": "blocked", "task_id": "ctx-1"}],
        }
        args = SimpleNamespace(
            workspace="/tmp",
            task_id="cron:reviewer-daily",
        )
        result = module.run_quality_scan(
            args,
            state={},
            normal_log_mode="silent",
            mode="daily_incremental",
            incremental_from_head=False,
            full_scan_skip_unchanged=False,
            run_fix_command=False,
        )
        self.assertTrue(result.notify)
        self.assertEqual(result.output.splitlines()[0], "代码审查巡检异常")
        self.assertIn("项目上下文门禁阻塞", result.output)
        self.assertIn("原因解析", result.output)
        self.assertIn("project-agent", result.output)
        self.assertIn("task center unavailable", result.output)
        self.assertNotIn("# reviewer-cron/", result.output)

    def test_reviewer_main_output_hides_machine_fields(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            history_dir = Path(tmpdir) / "runs"
            module.run_mode = lambda _args, _state, _normal_log_mode: SimpleNamespace(
                notify=False,
                output="NO_REPLY",
                record={
                    "run_id": "run-test-1",
                    "run_duration_ms": 22,
                    "risk_reasons": ["project_context_gate_blocked"],
                },
            )
            module.emit_policy_observability = lambda _args, _result, _run_file: ({"errors": []}, {})
            argv_backup = list(sys.argv)
            sys.argv = [
                "reviewer_cron_runner.py",
                "--mode",
                "daily_incremental",
                "--task-id",
                "cron:reviewer-daily-incremental",
                "--state-file",
                str(state_file),
                "--history-dir",
                str(history_dir),
            ]
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    rc = module.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(rc, 0)
            output = stdout.getvalue()
        self.assertIn("代码审查巡检异常", output)
        self.assertIn("项目上下文门禁阻塞", output)
        self.assertNotIn("# reviewer-cron/", output)
        self.assertNotIn("exception_count", output)
        self.assertNotIn("- exception:", output)
        self.assertNotIn("evidence:", output)

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

    def test_project_index_job_prompt_requires_single_exec_call(self):
        module = load_module(
            "install_project_index_job",
            "scripts/openclaw-ops/install_project_index_job.py",
        )
        jobs, _ = module.upsert_job(
            jobs=[],
            job_id="job-project-index",
            every_ms=1800000,
            maintainer_py="/home/ubuntu/.openclaw/ops/policy/project_index_maintainer.py",
            registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            task_id="cron:project-index-maintainer-30m",
            actor="project-agent",
            git_pull=False,
            channel="telegram",
            target="-1003333097130",
        )
        message = jobs[0]["payload"]["message"]
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Do not run any follow-up command", message)
        self.assertIn("Never output sentences like 'Let's run ...'", message)

    def test_reviewer_install_message_blocks_follow_up_chatter(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )
        message = module.build_message("python3 /tmp/reviewer_cron_runner.py --mode daily_incremental")
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Do not run any follow-up command", message)
        self.assertIn("Never output sentences like 'Let's run ...'", message)

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

    def test_cron_setup_prompt_requires_single_exec_call(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        message = module.build_message("python3 /tmp/demo.py")
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)

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

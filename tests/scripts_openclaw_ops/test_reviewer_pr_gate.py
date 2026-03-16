import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


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


class ReviewerPrGateTests(unittest.TestCase):
    def test_merge_approved_prs_skips_non_controlled_pr_even_when_approved(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        repo = Path("/tmp/demo-repo")
        prs = [
            {
                "number": 18,
                "title": "manual change",
                "draft": False,
                "mergeable": "MERGEABLE",
                "head": "feature/manual-change",
                "base": "main",
                "updated_at": "2026-03-17T00:00:00Z",
                "url": "https://example.test/pr/18",
            }
        ]
        approvals = [{"repo": "", "number": 18}]

        with mock.patch.object(module, "has_command", return_value=True):
            with mock.patch.object(module, "run_cmd") as run_cmd_mock:
                actions = module.merge_approved_prs(repo, prs, approvals)

        self.assertEqual(
            actions,
            [{"kind": "pr", "number": 18, "ok": False, "reason": "not_controlled_pr"}],
        )
        run_cmd_mock.assert_not_called()

    def test_merge_approved_prs_allows_controlled_pr_after_approval(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        repo = Path("/tmp/demo-repo")
        prs = [
            {
                "number": 19,
                "title": "chore: governance evolution 2026-03-17",
                "draft": False,
                "mergeable": "MERGEABLE",
                "head": "auto/evolution-20260317-abc123",
                "base": "main",
                "updated_at": "2026-03-17T00:00:00Z",
                "url": "https://example.test/pr/19",
            }
        ]
        approvals = [{"repo": "", "number": 19}]

        with mock.patch.object(module, "has_command", return_value=True):
            with mock.patch.object(module, "run_cmd", return_value=(0, "merged", "")) as run_cmd_mock:
                actions = module.merge_approved_prs(repo, prs, approvals)

        self.assertTrue(actions[0]["ok"])
        self.assertEqual(actions[0]["number"], 19)
        run_cmd_mock.assert_called_once()

    def test_build_jobs_exposes_pr_gate_only_hourly_mode(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )

        jobs = module.build_jobs(
            runner_py="/tmp/reviewer.py",
            workspace="/tmp/workspace",
            state_file="/tmp/state.json",
            history_dir="/tmp/history",
            tz_name="Asia/Shanghai",
            hourly_every_ms=3600000,
            daily_expr="0 4 * * *",
            bi_daily_expr="20 4 */2 * *",
            weekly_expr="40 4 * * 1",
            enable_hourly=True,
            enable_daily=True,
            enable_bi_daily=False,
            enable_weekly=True,
            normal_log_mode="silent",
            daily_fix_command="",
            hourly_git_fetch=True,
            hourly_check_pr=True,
            hourly_allow_merge=True,
            hourly_push_after_merge=False,
            hourly_merge_approval_file="/tmp/reviewer-merge-approval.json",
            project_context_gate=True,
            project_context_db="/tmp/task_center.db",
            project_context_assignee="project-agent",
            hourly_pr_gate_only=True,
        )

        hourly_job = jobs[0]
        self.assertIn("PR review gate", hourly_job["description"])
        self.assertIn("--pr-gate-only", hourly_job["payload"]["message"])


if __name__ == "__main__":
    unittest.main()

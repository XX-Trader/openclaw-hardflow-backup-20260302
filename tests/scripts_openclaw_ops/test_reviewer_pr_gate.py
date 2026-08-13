import importlib.util
import json
import sys
import tempfile
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
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
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
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
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

    def test_merge_approved_prs_supports_head_prefix_approval_rules(self):
        module = load_module(
            "reviewer_cron_runner",
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
        )
        repo = Path("/tmp/demo-repo")
        prs = [
            {
                "number": 23,
                "title": "chore: governance evolution 2026-03-17",
                "draft": False,
                "mergeable": "MERGEABLE",
                "head": "auto/evolution-20260317-abcd12",
                "base": "main",
                "updated_at": "2026-03-17T00:00:00Z",
                "url": "https://example.test/pr/23",
            }
        ]
        approvals = [{"repo": "", "head_prefix": "auto/evolution-", "base": "main"}]

        with mock.patch.object(module, "has_command", return_value=True):
            with mock.patch.object(module, "run_cmd", return_value=(0, "merged", "")) as run_cmd_mock:
                actions = module.merge_approved_prs(repo, prs, approvals)

        self.assertEqual(actions[0]["number"], 23)
        self.assertTrue(actions[0]["ok"])
        run_cmd_mock.assert_called_once()

    def test_load_merge_approvals_accepts_pr_head_prefix_rules(self):
        module = load_module(
            "reviewer_cron_runner",
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            approval_file = Path(tmpdir) / "reviewer-merge-approval.json"
            approval_file.write_text(
                json.dumps(
                    {
                        "approved_prs": [
                            {
                                "repo": "workflow-infra",
                                "head_prefix": "auto/evolution-",
                                "base": "main",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            approvals = module.load_merge_approvals(approval_file)

        self.assertEqual(
            approvals["approved_prs"],
            [
                {
                    "repo": "workflow-infra",
                    "head_prefix": "auto/evolution-",
                    "base": "main",
                }
            ],
        )




if __name__ == "__main__":
    unittest.main()

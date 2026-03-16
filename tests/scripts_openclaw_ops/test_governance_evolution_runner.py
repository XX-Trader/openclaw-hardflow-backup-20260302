import importlib.util
import sys
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
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        sys.path.pop(0)


class GovernanceEvolutionRunnerTests(unittest.TestCase):
    def test_attach_auto_pr_context_links_review_follow_up_targets(self):
        module = load_module(
            "governance_evolution_runner",
            "scripts/openclaw-ops/governance_evolution_runner.py",
        )

        task_packaging = {
            "created": [
                {
                    "task_id": "todo-governance-evolution-1",
                    "assignee": "optimization-agent",
                    "type": "governance_evolution_optimize",
                },
                {
                    "task_id": "todo-governance-review-1",
                    "assignee": "reviewer",
                    "type": "governance_evolution_review",
                },
            ],
            "skipped": [],
        }
        auto_pr_result = {
            "attempted": True,
            "ok": True,
            "reason": "ok",
            "branch": "auto/evolution-20260317-abc123",
            "pr_url": "https://github.com/example/repo/pull/42",
            "pr_number": 42,
        }

        enriched = module.attach_auto_pr_context(task_packaging, auto_pr_result)

        self.assertEqual(enriched["auto_pr"]["pr_url"], "https://github.com/example/repo/pull/42")
        self.assertEqual(
            enriched["review_targets"],
            [
                {
                    "task_id": "todo-governance-review-1",
                    "pr_url": "https://github.com/example/repo/pull/42",
                    "pr_number": 42,
                    "branch": "auto/evolution-20260317-abc123",
                }
            ],
        )

    def test_attach_auto_pr_context_keeps_shape_when_pr_not_created(self):
        module = load_module(
            "governance_evolution_runner",
            "scripts/openclaw-ops/governance_evolution_runner.py",
        )

        task_packaging = {
            "created": [
                {
                    "task_id": "todo-governance-review-1",
                    "assignee": "reviewer",
                    "type": "governance_evolution_review",
                }
            ],
            "skipped": [],
        }
        auto_pr_result = {
            "attempted": True,
            "ok": False,
            "reason": "no_commits_ahead_base",
            "branch": "auto/evolution-20260317-abc123",
            "pr_url": "",
            "pr_number": 0,
        }

        enriched = module.attach_auto_pr_context(task_packaging, auto_pr_result)

        self.assertIn("auto_pr", enriched)
        self.assertEqual(enriched["auto_pr"]["reason"], "no_commits_ahead_base")
        self.assertEqual(enriched["review_targets"], [])


if __name__ == "__main__":
    unittest.main()

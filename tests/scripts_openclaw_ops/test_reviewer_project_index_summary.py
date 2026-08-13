import importlib.util
import json
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
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        sys.path.pop(0)


class ReviewerProjectIndexSummaryTests(unittest.TestCase):
    def test_prefers_local_index_summary_when_present(self):
        module = load_module("reviewer_cron_runner", "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            legacy = repo / ".workflow" / "project-index" / "project-index.json"
            local = repo / ".workflow" / "project-index-local" / "project-index.json"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            local.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(
                json.dumps({"generated_at": "legacy", "modules": [1], "apis": [], "scripts": []}),
                encoding="utf-8",
            )
            local.write_text(
                json.dumps({"generated_at": "local", "modules": [], "apis": [1, 2], "scripts": [1]}),
                encoding="utf-8",
            )

            summary = module.load_project_index_summary(repo)

            self.assertTrue(summary["exists"])
            self.assertEqual(summary["generated_at"], "local")
            self.assertEqual(summary["apis_count"], 2)
            self.assertEqual(summary["index_file"], str(local))

    def test_falls_back_to_legacy_index_summary(self):
        module = load_module("reviewer_cron_runner", "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            legacy = repo / ".workflow" / "project-index" / "project-index.json"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(
                json.dumps({"generated_at": "legacy", "modules": [1, 2], "apis": [1], "scripts": []}),
                encoding="utf-8",
            )

            summary = module.load_project_index_summary(repo)

            self.assertTrue(summary["exists"])
            self.assertEqual(summary["generated_at"], "legacy")
            self.assertEqual(summary["modules_count"], 2)
            self.assertEqual(summary["index_file"], str(legacy))


if __name__ == "__main__":
    unittest.main()

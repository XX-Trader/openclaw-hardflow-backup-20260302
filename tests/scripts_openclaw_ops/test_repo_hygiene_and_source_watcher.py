import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HYGIENE_PATH = ROOT / "scripts" / "openclaw-ops" / "repo_hygiene_reviewer.py"
SOURCE_WATCHER_PATH = ROOT / "scripts" / "openclaw-ops" / "source_registry_watcher.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RepoHygieneAndSourceWatcherTests(unittest.TestCase):
    def test_repo_hygiene_scanner_reports_candidates_without_deleting(self):
        module = load_module("repo_hygiene_reviewer_test", HYGIENE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            temp_file = repo / "leftover.tmp"
            temp_file.write_text("temporary\n", encoding="utf-8")
            conflict_file = repo / "conflict.md"
            conflict_file.write_text("<<<<<<< ours\nvalue\n=======\nother\n>>>>>>> theirs\n", encoding="utf-8")
            cache_dir = repo / ".pytest_cache"
            cache_dir.mkdir()

            summary = module.run_review(
                repo_path=repo,
                output_dir=tmp / "reports",
                task_db=None,
                dry_run=True,
            )

            self.assertGreaterEqual(summary["finding_count"], 3)
            categories = {item["category"] for item in summary["findings"]}
            self.assertIn("temporary_or_backup_file", categories)
            self.assertIn("conflict_marker", categories)
            self.assertIn("generated_cache", categories)
            self.assertTrue(temp_file.exists())
            self.assertTrue(conflict_file.exists())
            self.assertTrue(Path(summary["report_path"]).exists())

    def test_source_registry_watcher_honors_base_path(self):
        module = load_module("source_registry_watcher_test", SOURCE_WATCHER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "project-memory"
            project = base / "demo"
            project.mkdir(parents=True)
            (project / "SOURCE_REGISTRY.json").write_text(
                json.dumps({"sources": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                rc = module.main(["--scan-all", "--base-path", str(base)])

            self.assertEqual(0, rc)
            payload = json.loads(out.getvalue())
            self.assertEqual("demo", payload[0]["project_key"])
            self.assertEqual("empty_registry", payload[0]["skipped"])


if __name__ == "__main__":
    unittest.main()

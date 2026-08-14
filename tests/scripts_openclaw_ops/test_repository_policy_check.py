import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/openclaw-ops/repository_policy_check.py"


def load_module():
    spec = importlib.util.spec_from_file_location("repository_policy_check_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class RepositoryPolicyCheckTests(unittest.TestCase):
    def test_chinese_tracked_path_is_scanned_without_quoted_path_loss(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            git(repo, "init", "-q")
            source = repo / "文档" / "说明.md"
            source.parent.mkdir()
            source.write_text("这是" + "量化" + "交易" + "专用实现。\n", encoding="utf-8")
            git(repo, "add", "--", "文档/说明.md")
            report = module.scan_repository(repo, include_untracked=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["path"], "文档/说明.md")
        self.assertEqual(report["findings"][0]["category"], "domain_zh")

    def test_readme_has_no_positioning_exception(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            git(repo, "init", "-q")
            (repo / "README.md").write_text("仓库定位：" + "行" + "情" + "处理。\n", encoding="utf-8")
            git(repo, "add", "--", "README.md")
            report = module.scan_repository(repo, include_untracked=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["path"], "README.md")
        self.assertEqual(report["findings"][0]["category"], "domain_zh")

    def test_domain_identifier_separator_is_normalized(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            git(repo, "init", "-q")
            source = repo / "config.py"
            source.write_text("FUT" + "URES_URL = 'https://example.invalid'\n", encoding="utf-8")
            git(repo, "add", "--", "config.py")
            report = module.scan_repository(repo, include_untracked=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["path"], "config.py")
        self.assertEqual(report["findings"][0]["category"], "domain_en")

    def test_placeholders_pass_and_realistic_secret_shape_is_reported(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            git(repo, "init", "-q")
            (repo / "config.json").write_text(json.dumps({"token": "${RUNTIME_TOKEN}"}) + "\n", encoding="utf-8")
            (repo / "leak.txt").write_text("sk-" + "A" * 24 + "\n", encoding="utf-8")
            git(repo, "add", "--", "config.json", "leak.txt")
            report = module.scan_repository(repo, include_untracked=False)
        self.assertEqual(report["counts"], {"api_token": 1})
        self.assertNotIn("A" * 24, str(report["findings"]))

    def test_current_docs_report_missing_owner_but_archives_do_not(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            git(repo, "init", "-q")
            current = repo / "docs" / "current.md"
            archive = repo / "docs" / "archive" / "old.md"
            archive.parent.mkdir(parents=True)
            current.write_text(
                "Run `scripts/openclaw-ops/" + "removed_runner.py`.\n",
                encoding="utf-8",
            )
            archive.write_text(
                "Run `scripts/openclaw-ops/" + "old_runner.py`.\n",
                encoding="utf-8",
            )
            git(repo, "add", "--", "docs/current.md", "docs/archive/old.md")
            report = module.scan_repository(repo, include_untracked=False)
        self.assertEqual(report["counts"], {"stale_owner_reference": 1})
        self.assertEqual(report["findings"][0]["path"], "docs/current.md")


if __name__ == "__main__":
    unittest.main()

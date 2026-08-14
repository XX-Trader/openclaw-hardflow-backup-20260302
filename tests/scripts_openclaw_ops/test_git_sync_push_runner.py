import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "skills/library/git-sync/scripts/git_sync_push_runner.py"


def load_module():
    spec = importlib.util.spec_from_file_location("git_sync_push_runner_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GitSyncPushRunnerTests(unittest.TestCase):
    def test_source_checkout_help_entrypoint(self):
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--repo", process.stdout)

    def test_sensitive_scan_returns_only_clean_files(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "clean.txt").write_text(
                "MYSQL_PASSWORD=${DB_PASSWORD}\n"
                "APP_PASSWORD=<APP_PASSWORD_SECRET_REF>\n",
                encoding="utf-8",
            )
            secret_sample = "api" + "_key=" + ("a" * 20) + "\n"
            (repo / "secret.txt").write_text(
                secret_sample,
                encoding="utf-8",
            )
            clean, alerts = module.scan_sensitive_content(
                repo,
                ["clean.txt", "secret.txt"],
            )
        self.assertEqual(clean, ["clean.txt"])
        self.assertEqual(alerts[0]["file"], "secret.txt")
        self.assertEqual(alerts[0]["pattern"], "api_key")


if __name__ == "__main__":
    unittest.main()

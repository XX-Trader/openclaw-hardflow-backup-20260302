import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPT = ROOT / "skills/openclaw-hardflow-automation/scripts/check-api-doc-gate.sh"


def find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    candidates = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/bash.exe",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


class ApiDocGateTests(unittest.TestCase):
    @unittest.skipUnless(find_bash(), "bash is required")
    def test_repository_root_and_generic_api_path_detection(self):
        bash = find_bash()
        assert bash
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            script = repo / "skills/openclaw-hardflow-automation/scripts/check-api-doc-gate.sh"
            router = repo / "skills/library/intelligent-router/router_engine.py"
            api_source = repo / "backend/routes/items.py"
            script.parent.mkdir(parents=True)
            router.parent.mkdir(parents=True)
            api_source.parent.mkdir(parents=True)
            shutil.copy2(SOURCE_SCRIPT, script)
            router.write_text("ROUTES = {}\n", encoding="utf-8")
            api_source.write_text("def list_items():\n    return []\n", encoding="utf-8")

            git = lambda *args: subprocess.run(
                ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
            )
            git("init", "-b", "main")
            git("config", "user.name", "Gate Test")
            git("config", "user.email", "gate@example.invalid")
            git("add", ".")
            git("commit", "-m", "initial")

            env = dict(os.environ)
            env["HARDFLOW_REPO_ROOT"] = str(repo)
            router.write_text("ROUTES = {'generic': 'coordinator'}\n", encoding="utf-8")
            unrelated = subprocess.run([bash, str(script)], cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(0, unrelated.returncode, unrelated.stdout + unrelated.stderr)
            gate_file = repo / ".workflow/gates/api_doc.json"
            self.assertTrue(gate_file.is_file())
            self.assertFalse((repo / "skills/.workflow/gates/api_doc.json").exists())

            git("checkout", "--", str(router.relative_to(repo)))
            api_source.write_text("def list_items():\n    return ['ready']\n", encoding="utf-8")
            missing_docs = subprocess.run([bash, str(script)], cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(1, missing_docs.returncode)
            self.assertFalse(json.loads(gate_file.read_text(encoding="utf-8"))["passed"])

            api_docs = repo / "docs/api/items.md"
            api_docs.parent.mkdir(parents=True)
            api_docs.write_text("# Items API\n", encoding="utf-8")
            git("add", str(api_docs.relative_to(repo)))
            documented = subprocess.run([bash, str(script)], cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(0, documented.returncode, documented.stdout + documented.stderr)
            self.assertTrue(json.loads(gate_file.read_text(encoding="utf-8"))["passed"])


if __name__ == "__main__":
    unittest.main()

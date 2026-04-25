import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts/openclaw-ops/smart_arb_live_bridge.py"


class SmartArbLiveBridgeTests(unittest.TestCase):
    def test_echo_code_review_outputs_required_verdict(self):
        proc = subprocess.run(
            [sys.executable, str(BRIDGE), "--stage", "code_review", "--agent-mode", "echo"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("Final verdict: pass", proc.stdout)
        self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)

    def test_memory_writeback_uses_pipeline_memory_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()
            writeback = run_dir / "writeback_report.md"
            writeback.write_text("# Writeback\n\nBridge memory test.\n", encoding="utf-8")
            project_memory_dir = tmp / "memory" / "demo"

            env = dict(os.environ)
            env.update(
                {
                    "PIPELINE_PROJECT_KEY": "demo",
                    "PIPELINE_PROJECT_MEMORY_DIR": str(project_memory_dir),
                    "PIPELINE_WRITEBACK_REPORT_FILE": str(writeback),
                }
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "memory_writeback",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(ROOT),
                    "--python-bin",
                    sys.executable,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)
            changelog = project_memory_dir / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            record = json.loads(changelog.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("Bridge memory test", record["content"])


if __name__ == "__main__":
    unittest.main()

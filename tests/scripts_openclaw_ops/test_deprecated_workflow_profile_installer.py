import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/library/openclaw-workflow-manager/scripts/install_workflow_profile.py"


class DeprecatedWorkflowProfileInstallerTests(unittest.TestCase):
    def test_old_installer_fails_fast_with_replacement_pointer(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--profile",
                "core",
                "--workflow-repo-path",
                ".",
                "--emit-json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["deprecated"])
        self.assertIn("cron_setup.py", payload["reason"])
        self.assertIn("project-delivery-pipeline", payload["replacement"])


if __name__ == "__main__":
    unittest.main()

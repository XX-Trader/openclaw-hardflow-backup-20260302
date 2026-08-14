import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "openclaw-ops" / "generic_fixture_e2e.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generic_fixture_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenericFixtureEndToEndTests(unittest.TestCase):
    def test_python_fixture_isolated_delivery_writeback_and_publish(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = module.run_all(Path(tmpdir) / "evidence", ("python",))

        self.assertTrue(report["ok"])
        self.assertTrue(all(report["results"][0]["checks"].values()))

    @unittest.skipUnless(shutil.which("node") and shutil.which("npm"), "node and npm are required")
    def test_frontend_fixture_uses_project_commands_and_frontend_owner(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = module.run_all(Path(tmpdir) / "evidence", ("frontend",))

        result = report["results"][0]
        self.assertTrue(report["ok"])
        self.assertTrue(all(result["checks"].values()))
        self.assertIn("npm", result["verification_command"].lower())
        self.assertIn("build completed", result["verification_stdout"])


if __name__ == "__main__":
    unittest.main()

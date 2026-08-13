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


class NormalizeOpenClawHomePathsTests(unittest.TestCase):
    def test_normalize_string_supports_windows_home_paths(self):
        module = load_module(
            "normalize_openclaw_home_paths",
            "skills/library/openclaw-workflow-manager/scripts/normalize_openclaw_home_paths.py",
        )

        updated, changed = module.normalize_string(
            "python /home/runtime-user/.openclaw/ops/todo_patrol.py",
            openclaw_home=r"C:\Users\fixture-user\.openclaw",
            claude_home=r"C:\Users\fixture-user\.claude",
        )

        self.assertTrue(changed)
        self.assertEqual(updated, r"python C:\Users\fixture-user\.openclaw/ops/todo_patrol.py")


if __name__ == "__main__":
    unittest.main()

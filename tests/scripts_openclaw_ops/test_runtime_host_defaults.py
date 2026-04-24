import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    if not path.exists():
        raise FileNotFoundError(path)
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


class RuntimeHostDefaultTests(unittest.TestCase):
    def test_distill_runner_default_db_path_follows_selected_host_home(self):
        module = load_module(
            "cross_runtime_distill_runner_runtime_defaults",
            "skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py",
        )

        path = module.resolve_default_db_path(
            ["hermes"],
            {
                "hermes": {
                    "home": "/home/ubuntu/.hermes",
                }
            },
        )

        self.assertEqual(path, "/home/ubuntu/.hermes/ops/distill/distill.db")


if __name__ == "__main__":
    unittest.main()

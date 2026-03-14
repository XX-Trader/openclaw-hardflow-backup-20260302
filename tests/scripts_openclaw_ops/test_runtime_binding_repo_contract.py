import importlib.util
import json
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


class RuntimeBindingRepoContractTests(unittest.TestCase):
    def test_repository_runtime_bindings_have_no_missing_skills(self):
        module = load_module(
            "inspect_runtime_bindings",
            "scripts/openclaw-ops/inspect_runtime_bindings.py",
        )

        report = module.build_runtime_bindings_report(ROOT)
        agents = {item["agent_id"]: item for item in report["agents"]}

        self.assertEqual(report["missing_skills"], [])
        self.assertEqual(agents["main"]["missing_skills"], [])
        self.assertEqual(report["hook_events"]["agent:bootstrap"], ["bootstrap-extra-files"])
        self.assertEqual(report["hook_events"]["gateway:startup"], ["boot-md"])

    def test_generated_indexes_are_marked_and_current(self):
        agent_index_md = (ROOT / "agents/agent_index.md").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "agents/agent_capability_manifest.json").read_text(encoding="utf-8"))
        cron_matrix = json.loads((ROOT / "cron/index/cron_agent_capability_matrix.json").read_text(encoding="utf-8"))

        self.assertIn("Generated file", agent_index_md)
        self.assertIn("Do not edit manually", agent_index_md)
        main = next(item for item in manifest["agents"] if item["agent_id"] == "main")
        self.assertEqual(main["missing_skills"], [])
        self.assertGreaterEqual(len(cron_matrix["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()

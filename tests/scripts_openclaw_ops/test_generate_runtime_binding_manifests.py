import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.scripts_openclaw_ops.test_inspect_runtime_bindings import build_fixture_repo


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


class GenerateRuntimeBindingManifestsTests(unittest.TestCase):
    def test_generate_manifests_writes_expected_outputs(self):
        module = load_module(
            "generate_runtime_binding_manifests",
            "scripts/openclaw-ops/generate_runtime_binding_manifests.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            build_fixture_repo(repo_root)

            changed_files = module.generate_runtime_binding_manifests(repo_root)
            second_run_changed_files = module.generate_runtime_binding_manifests(repo_root)

            manifest = json.loads(
                (repo_root / "agents/agent_capability_manifest.json").read_text(encoding="utf-8")
            )
            hook_matrix = json.loads(
                (repo_root / "hooks/index/hook_event_matrix.json").read_text(encoding="utf-8")
            )
            cron_matrix = json.loads(
                (repo_root / "cron/index/cron_agent_capability_matrix.json").read_text(encoding="utf-8")
            )
            agent_index = json.loads((repo_root / "agents/agent_index.json").read_text(encoding="utf-8"))
            agent_index_md = (repo_root / "agents/agent_index.md").read_text(encoding="utf-8")

        self.assertEqual(
            changed_files,
            [
                "agents/agent_capability_manifest.json",
                "hooks/index/hook_event_matrix.json",
                "cron/index/cron_agent_capability_matrix.json",
                "agents/agent_index.json",
                "agents/agent_index.md",
            ],
        )
        self.assertEqual(second_run_changed_files, [])

        agents = {item["agent_id"]: item for item in manifest["agents"]}
        self.assertTrue(agents["main"]["default"])
        self.assertEqual(agents["main"]["missing_skills"], ["using-superpowers"])
        self.assertEqual(agents["frontend-dev"]["runtime_skill_overrides"][0]["runtime_skill"], "frontend-design-ultimate")
        self.assertEqual(agents["web-agent"]["capability_mode"], "role_only")
        self.assertEqual(
            agents["main"]["hook_events_affected"],
            ["agent:bootstrap", "command", "command:new", "command:reset", "command:stop", "gateway:startup"],
        )

        self.assertEqual(hook_matrix["events"]["agent:bootstrap"], ["bootstrap-extra-files"])
        self.assertEqual(hook_matrix["events"]["command"], ["command-logger"])
        self.assertEqual(hook_matrix["events"]["command:new"], ["hardflow-policy-enforcer", "session-memory"])
        self.assertEqual(hook_matrix["events"]["command:reset"], ["session-memory"])
        self.assertEqual(hook_matrix["events"]["command:stop"], ["hardflow-policy-enforcer"])
        self.assertEqual(hook_matrix["events"]["gateway:startup"], ["boot-md"])

        self.assertEqual(cron_matrix["jobs"][0]["job_id"], "job-1")
        self.assertEqual(cron_matrix["jobs"][0]["agent_id"], "main")
        self.assertEqual(cron_matrix["jobs"][0]["capability_mode"], "skill_backed")
        self.assertEqual(cron_matrix["jobs"][1]["agent_exists"], False)

        self.assertEqual(agent_index[0]["id"], "main")
        self.assertTrue(agent_index[0]["default"])
        self.assertIn("Generated file", agent_index_md)
        self.assertIn("Do not edit manually", agent_index_md)
        self.assertIn("## main", agent_index_md)
        self.assertIn("- default: True", agent_index_md)


if __name__ == "__main__":
    unittest.main()

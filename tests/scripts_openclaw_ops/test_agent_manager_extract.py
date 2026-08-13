import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/library/agent-manager/scripts/extract-agents.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_manager_extract_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AgentManagerExtractTests(unittest.TestCase):
    def test_main_uses_explicit_generic_directories(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            agents_dir = root / "agents"
            output_dir = root / "output"
            (agents_dir / "review").mkdir(parents=True)
            (agents_dir / "review" / "reviewer.md").write_text(
                "---\nname: reviewer\ndescription: Reviews changes\ncategory: quality\n---\n",
                encoding="utf-8",
            )

            rc = module.main(
                [
                    "--agents-dir",
                    str(agents_dir),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            payload = json.loads((output_dir / "agents.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "AGENTS_INDEX.md").read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(payload["total_agents"], 1)
        self.assertEqual(payload["agents"][0]["file"], "review/reviewer")
        self.assertIn("review/reviewer.md", markdown)


if __name__ == "__main__":
    unittest.main()

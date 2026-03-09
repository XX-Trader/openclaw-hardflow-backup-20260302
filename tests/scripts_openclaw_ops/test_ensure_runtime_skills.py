import importlib.util
import json
import sys
import tempfile
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


class EnsureRuntimeSkillsTests(unittest.TestCase):
    def test_ensure_skill_entry_installs_local_skill_and_removes_conflicts(self):
        module = load_module(
            "ensure_runtime_skills",
            "scripts/openclaw-ops/ensure_runtime_skills.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            openclaw_home = tmp / ".openclaw"
            managed_dir = openclaw_home / "skills" / "frontend-design"
            workspace_dir = openclaw_home / "workspace" / "skills" / "frontend-design"
            managed_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir.mkdir(parents=True, exist_ok=True)
            (managed_dir / "SKILL.md").write_text("# old\n", encoding="utf-8")
            (workspace_dir / "SKILL.md").write_text("# old\n", encoding="utf-8")

            source_dir = tmp / "frontend-design-ultimate-src"
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "SKILL.md").write_text("# new\n", encoding="utf-8")

            result = module.ensure_skill_entry(
                {
                    "name": "frontend-design-ultimate",
                    "conflicts": ["frontend-design"],
                    "install": {
                        "targets": ["managed", "workspace"],
                        "source_dir": str(source_dir),
                    },
                },
                openclaw_home=openclaw_home,
                dry_run=False,
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["install_method"], "source-dir")
            self.assertFalse((managed_dir).exists())
            self.assertFalse((workspace_dir).exists())
            self.assertTrue((openclaw_home / "skills" / "frontend-design-ultimate" / "SKILL.md").exists())
            self.assertTrue((openclaw_home / "workspace" / "skills" / "frontend-design-ultimate" / "SKILL.md").exists())

    def test_ensure_command_entry_dry_run_reports_missing_binary_install(self):
        module = load_module(
            "ensure_runtime_skills",
            "scripts/openclaw-ops/ensure_runtime_skills.py",
        )
        result = module.ensure_command_entry(
            {
                "name": "summarize",
                "install": {
                    "command": "definitely-missing-summarize-binary",
                    "npm_package": "@steipete/summarize",
                    "verify_args": ["--version"],
                },
            },
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["present_before"])
        self.assertFalse(result["present_after"])
        self.assertTrue(result["would_install"])

    def test_runtime_required_skills_manifest_includes_frontend_and_summarize(self):
        manifest = json.loads(
            (ROOT / "scripts/openclaw-ops/runtime-required-skills.json").read_text(encoding="utf-8")
        )
        skills = manifest.get("skills") or []
        commands = manifest.get("commands") or []

        self.assertTrue(any(item.get("name") == "frontend-design-ultimate" for item in skills))
        self.assertTrue(any(item.get("name") == "summarize" for item in commands))


if __name__ == "__main__":
    unittest.main()

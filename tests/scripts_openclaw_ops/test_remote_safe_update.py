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


class RemoteSafeUpdateTests(unittest.TestCase):
    def test_parse_ssh_hosts_keeps_order_and_skips_patterns(self):
        module = load_module("remote_safe_update", "skills/library/fleet-sync/scripts/remote_safe_update.py")
        text = "\n".join(
            [
                "Host HOST_A",
                "Host *.internal HOST_F",
                "Host HOST_B HOST_E",
                "Host ?invalid",
            ]
        )
        self.assertEqual(
            module.parse_ssh_hosts(text),
            ["HOST_A", "HOST_F", "HOST_B", "HOST_E"],
        )

    def test_parse_porcelain_entries_handles_untracked_and_rename(self):
        module = load_module("remote_safe_update", "skills/library/fleet-sync/scripts/remote_safe_update.py")
        text = "\n".join(
            [
                " M .workflow/project-index-local/PROJECT_INDEX.md",
                "?? docs/new-note.md",
                "R  old/path.py -> scripts/new_path.py",
            ]
        )
        self.assertEqual(
            module.parse_porcelain_entries(text),
            [
                {"status": " M", "path": ".workflow/project-index-local/PROJECT_INDEX.md"},
                {"status": "??", "path": "docs/new-note.md"},
                {"status": "R ", "path": "scripts/new_path.py"},
            ],
        )

    def test_split_dirty_paths_separates_volatile_and_blocking(self):
        module = load_module("remote_safe_update", "skills/library/fleet-sync/scripts/remote_safe_update.py")
        entries = [
            {"status": " M", "path": ".workflow/project-index-local/PROJECT_INDEX.md"},
            {"status": " M", "path": "memory/cache.json"},
            {"status": "??", "path": "docs/new-note.md"},
        ]
        volatile, blocking = module.split_dirty_paths(
            entries,
            [".workflow/project-index-local/", "memory/"],
        )
        self.assertEqual(
            volatile,
            [
                ".workflow/project-index-local/PROJECT_INDEX.md",
                "memory/cache.json",
            ],
        )
        self.assertEqual(blocking, ["docs/new-note.md"])


if __name__ == "__main__":
    unittest.main()

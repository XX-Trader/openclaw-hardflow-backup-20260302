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


class RuntimePluginOverridesTests(unittest.TestCase):
    def test_sync_plugin_overrides_copies_updates_and_deletes_manifest_tracked_files(self):
        module = load_module(
            "sync_runtime_plugin_overrides",
            "scripts/openclaw-ops/sync_runtime_plugin_overrides.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_dir = tmp / "runtime-plugin-overrides"
            target_extensions_dir = tmp / ".openclaw" / "extensions"
            manifest_file = tmp / ".openclaw" / "ops" / ".runtime-plugin-overrides-manifest.json"

            plugin_dir = source_dir / "memory-openviking"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "text-utils.ts").write_text("export const marker = 'new';\n", encoding="utf-8")
            (plugin_dir / "text-utils.test.mjs").write_text("console.log('ok');\n", encoding="utf-8")

            existing_dir = target_extensions_dir / "memory-openviking"
            existing_dir.mkdir(parents=True, exist_ok=True)
            (existing_dir / "text-utils.ts").write_text("export const marker = 'old';\n", encoding="utf-8")
            (existing_dir / "stale.ts").write_text("stale\n", encoding="utf-8")

            manifest_file.parent.mkdir(parents=True, exist_ok=True)
            manifest_file.write_text(
                json.dumps(
                    {
                        "managed_files": [
                            "memory-openviking/text-utils.ts",
                            "memory-openviking/stale.ts",
                        ]
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = module.sync_plugin_overrides(
                source_dir=source_dir,
                target_extensions_dir=target_extensions_dir,
                manifest_file=manifest_file,
                dry_run=False,
                keep_stale_files=False,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["counts"]["updated"], 1)
            self.assertEqual(result["counts"]["added"], 1)
            self.assertEqual(result["counts"]["deleted"], 1)
            self.assertEqual(
                (existing_dir / "text-utils.ts").read_text(encoding="utf-8"),
                "export const marker = 'new';\n",
            )
            self.assertFalse((existing_dir / "stale.ts").exists())

            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(manifest["managed_plugins"], ["memory-openviking"])
            self.assertEqual(
                sorted(manifest["managed_files"]),
                [
                    "memory-openviking/text-utils.test.mjs",
                    "memory-openviking/text-utils.ts",
                ],
            )


if __name__ == "__main__":
    unittest.main()

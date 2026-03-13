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


class RecoverStaleCronRunningStateTests(unittest.TestCase):
    def test_recover_stale_running_state_clears_only_stale_entries_and_writes_backup(self):
        module = load_module(
            "recover_stale_cron_running_state",
            "scripts/openclaw-ops/recover_stale_cron_running_state.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_file = Path(tmpdir) / "jobs.json"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "name": "stale-job",
                                "state": {"runningAtMs": 1_000_000},
                            },
                            {
                                "name": "fresh-job",
                                "state": {"runningAtMs": 4_000_000},
                            },
                            {
                                "name": "idle-job",
                                "state": {"lastRunStatus": "ok"},
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = module.recover_stale_running_state(
                jobs_file,
                stale_minutes=30,
                dry_run=False,
                now_ms=5_000_000,
            )

            payload = json.loads(jobs_file.read_text(encoding="utf-8"))
            backups = sorted(Path(tmpdir).glob("jobs.json.bak.recover-*"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["updated_jobs"][0]["name"], "stale-job")
        self.assertEqual(payload["jobs"][0]["state"]["runningAtMs"], None)
        self.assertEqual(payload["jobs"][1]["state"]["runningAtMs"], 4_000_000)
        self.assertEqual(len(backups), 1)
        self.assertEqual(result["backup_path"], str(backups[0]))

    def test_recover_stale_running_state_dry_run_preserves_jobs_file(self):
        module = load_module(
            "recover_stale_cron_running_state",
            "scripts/openclaw-ops/recover_stale_cron_running_state.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_file = Path(tmpdir) / "jobs.json"
            original = {
                "jobs": [
                    {
                        "name": "stale-job",
                        "state": {"runningAtMs": 1_000_000},
                    }
                ]
            }
            jobs_file.write_text(json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8")

            result = module.recover_stale_running_state(
                jobs_file,
                stale_minutes=30,
                dry_run=True,
                now_ms=5_000_000,
            )

            payload = json.loads(jobs_file.read_text(encoding="utf-8"))
            backups = sorted(Path(tmpdir).glob("jobs.json.bak.recover-*"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(payload, original)
        self.assertEqual(backups, [])


if __name__ == "__main__":
    unittest.main()

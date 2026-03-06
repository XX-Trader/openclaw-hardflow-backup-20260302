import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/openclaw-ops/uninstall_workflow_profile.py"
CORE_RUNTIME_HOOKS = (
    "hardflow-command-guard",
    "hardflow-audit",
    "hardflow-stop-gate-reminder",
    "hardflow-policy-enforcer",
)


class UninstallWorkflowProfileTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> dict[str, Path]:
        workflow_repo = root / "workflow-repo"
        (workflow_repo / "hooks").mkdir(parents=True, exist_ok=True)
        (workflow_repo / "skills").mkdir(parents=True, exist_ok=True)

        openclaw_home = root / "openclaw-home"
        cron_dir = openclaw_home / "cron"
        cron_dir.mkdir(parents=True, exist_ok=True)
        ops_dir = openclaw_home / "ops"
        (ops_dir / "policy").mkdir(parents=True, exist_ok=True)

        jobs_file = cron_dir / "jobs.json"
        jobs_file.write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "16cb8d03-beb9-4697-927d-35952353bf8e", "name": "todo_patrol_15m", "enabled": True},
                        {"id": "legacy-ops-monitor", "name": "ops_incremental_monitor", "enabled": True},
                        {"id": "web-intel-collect", "name": "web_intel_collect_hourly", "enabled": True},
                        {"id": "keep-job", "name": "keep_me", "enabled": True},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        managed_runner = ops_dir / "policy" / "task_executor_runner.py"
        managed_runner.write_text("print('managed')\n", encoding="utf-8")
        managed_root_file = ops_dir / "todo_patrol.py"
        managed_root_file.write_text("print('managed')\n", encoding="utf-8")
        keep_file = ops_dir / "keep.txt"
        keep_file.write_text("keep\n", encoding="utf-8")

        manifest_file = ops_dir / ".hardflow-sync-manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "schema_version": "2026-03-02",
                    "managed_files": [
                        "todo_patrol.py",
                        "policy/task_executor_runner.py",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        openclaw_json = openclaw_home / "openclaw.json"
        cfg = {
            "env": {
                "vars": {
                    "HARDFLOW_OPENCLAW_OVERLAY_ROLE": "workflow-overlay",
                    "HARDFLOW_OPENCLAW_OFFICIAL_RUNTIME_ROOT": str(openclaw_home),
                    "HARDFLOW_OPENCLAW_OVERLAY_CONFIG_SOURCE": str(workflow_repo / "openclaw" / "openclaw.json"),
                    "HARDFLOW_OPENCLAW_RUNTIME_BOUNDARY_DOC": str(
                        workflow_repo / "integration" / "openclaw-bridge" / "runtime-boundary.md"
                    ),
                    "HARDFLOW_OPENCLAW_HOOKS_SOURCE_DIR": str(workflow_repo / "hooks"),
                    "HARDFLOW_OPENCLAW_SKILLS_SOURCE_DIR": str(workflow_repo / "skills"),
                    "KEEP_ME": "keep",
                }
            },
            "hooks": {
                "internal": {
                    "load": {
                        "extraDirs": [
                            str(workflow_repo / "hooks"),
                            "/opt/custom-hooks",
                        ]
                    },
                    "entries": {
                        "hardflow-command-guard": {"enabled": True},
                        "hardflow-audit": {"enabled": True},
                        "hardflow-stop-gate-reminder": {"enabled": True},
                        "hardflow-policy-enforcer": {"enabled": True},
                        "keep-hook": {"enabled": True, "script": "/opt/custom-hooks/keep.py"},
                    },
                }
            },
            "skills": {
                "load": {
                    "watch": True,
                    "watchDebounceMs": 1200,
                    "extraDirs": [
                        str(workflow_repo / "skills"),
                        "/opt/custom-skills",
                    ],
                }
            },
            "channels": {
                "telegram": {
                    "botToken": "keep",
                }
            },
        }
        openclaw_json.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return {
            "workflow_repo": workflow_repo,
            "openclaw_home": openclaw_home,
            "jobs_file": jobs_file,
            "manifest_file": manifest_file,
            "openclaw_json": openclaw_json,
            "managed_runner": managed_runner,
            "managed_root_file": managed_root_file,
            "keep_file": keep_file,
        }

    def test_uninstall_removes_managed_runtime_artifacts_and_keeps_unrelated_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build_fixture(Path(tmp))
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--openclaw-home",
                    str(fixture["openclaw_home"]),
                    "--jobs-file",
                    str(fixture["jobs_file"]),
                    "--workflow-repo-path",
                    str(fixture["workflow_repo"]),
                    "--emit-json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["jobs"]["removed_count"], 3)
            self.assertEqual(payload["ops_files"]["deleted_count"], 2)
            self.assertTrue(payload["runtime_config"]["changed"])

            jobs_data = json.loads(fixture["jobs_file"].read_text(encoding="utf-8"))
            self.assertEqual([job["name"] for job in jobs_data["jobs"]], ["keep_me"])

            cfg = json.loads(fixture["openclaw_json"].read_text(encoding="utf-8"))
            env_vars = cfg["env"]["vars"]
            self.assertEqual(env_vars, {"KEEP_ME": "keep"})
            self.assertEqual(cfg["hooks"]["internal"]["load"]["extraDirs"], ["/opt/custom-hooks"])
            self.assertEqual(cfg["skills"]["load"]["extraDirs"], ["/opt/custom-skills"])
            self.assertIn("keep-hook", cfg["hooks"]["internal"]["entries"])
            for hook_name in CORE_RUNTIME_HOOKS:
                self.assertNotIn(hook_name, cfg["hooks"]["internal"]["entries"])

            self.assertFalse(fixture["managed_runner"].exists())
            self.assertFalse(fixture["managed_root_file"].exists())
            self.assertTrue(fixture["keep_file"].exists())
            self.assertFalse(fixture["manifest_file"].exists())

    def test_uninstall_dry_run_reports_changes_without_touching_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build_fixture(Path(tmp))
            before_jobs = fixture["jobs_file"].read_text(encoding="utf-8")
            before_config = fixture["openclaw_json"].read_text(encoding="utf-8")
            before_manifest = fixture["manifest_file"].read_text(encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--openclaw-home",
                    str(fixture["openclaw_home"]),
                    "--jobs-file",
                    str(fixture["jobs_file"]),
                    "--workflow-repo-path",
                    str(fixture["workflow_repo"]),
                    "--dry-run",
                    "--emit-json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["jobs"]["removed_count"], 3)
            self.assertEqual(payload["ops_files"]["deleted_count"], 2)
            self.assertFalse(payload["jobs"]["written"])
            self.assertFalse(payload["runtime_config"]["written"])

            self.assertEqual(fixture["jobs_file"].read_text(encoding="utf-8"), before_jobs)
            self.assertEqual(fixture["openclaw_json"].read_text(encoding="utf-8"), before_config)
            self.assertEqual(fixture["manifest_file"].read_text(encoding="utf-8"), before_manifest)
            self.assertTrue(fixture["managed_runner"].exists())
            self.assertTrue(fixture["managed_root_file"].exists())


if __name__ == "__main__":
    unittest.main()

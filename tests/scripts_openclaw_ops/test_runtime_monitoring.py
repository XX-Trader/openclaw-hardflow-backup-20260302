import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


class RuntimeMonitoringTests(unittest.TestCase):
    def test_collect_runtime_project_health_detects_missing_process_and_running_service(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            project_root = tmp / "project-a"
            project_root.mkdir()
            api_log = project_root / "logs" / "api.log"
            api_log.parent.mkdir(parents=True)
            api_log.write_text("boot ok\n", encoding="utf-8")
            registry = tmp / "project-registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "project-a",
                                "name": "project-a",
                                "path": str(project_root),
                                "runtime_monitoring": {
                                    "enabled": True,
                                    "items": [
                                        {
                                            "id": "api",
                                            "name": "market-api",
                                            "type": "process",
                                            "required": True,
                                            "match": "uvicorn market_api:app",
                                            "log_paths": [str(api_log)],
                                            "stop_command": "pkill -f 'uvicorn market_api:app'",
                                        },
                                        {
                                            "id": "worker",
                                            "name": "market-worker",
                                            "type": "service",
                                            "required": True,
                                            "service_unit": "project-a-worker.service",
                                        },
                                    ],
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = module.default_config()
            cfg["runtime_monitor"] = {
                "enabled": True,
                "project_registry": str(registry),
            }

            def fake_run_shell(command: str, timeout: int = 20):
                if "pgrep -af" in command:
                    return 1, "", ""
                self.fail(f"unexpected command: {command}")

            with mock.patch.object(module, "run_shell", side_effect=fake_run_shell):
                result = module.collect_runtime_project_health(
                    cfg,
                    service_snapshot={
                        "project-a-worker": {
                            "unit": "project-a-worker.service",
                            "state": "active/running",
                        }
                    },
                )

        self.assertTrue(result["enabled"])
        self.assertEqual(result["summary"]["project_count"], 1)
        self.assertEqual(result["summary"]["item_count"], 2)
        self.assertEqual(result["summary"]["required_missing_count"], 1)
        self.assertEqual(result["summary"]["running_count"], 1)
        self.assertIn(str(api_log), result["log_paths"])

        project = result["projects"][0]
        item_by_id = {item["id"]: item for item in project["items"]}
        self.assertEqual(item_by_id["api"]["status"], "missing")
        self.assertEqual(item_by_id["worker"]["status"], "running")
        self.assertEqual(result["missing_required"][0]["project_id"], "project-a")
        self.assertEqual(result["missing_required"][0]["item_id"], "api")
        self.assertIn("pkill -f", item_by_id["api"]["stop_command"])

    def test_run_scan_includes_runtime_process_missing_risk_reason(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            project_root = tmp / "project-b"
            project_root.mkdir()
            registry = tmp / "project-registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "project-b",
                                "name": "project-b",
                                "path": str(project_root),
                                "runtime_monitoring": {
                                    "enabled": True,
                                    "items": [
                                        {
                                            "id": "web",
                                            "name": "project-web",
                                            "type": "process",
                                            "required": True,
                                            "match": "python app.py",
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = module.default_config()
            cfg["log_roots"] = []
            cfg["service_monitor"] = {"enabled": False}
            cfg["system_monitor"] = {"enabled": False}
            cfg["workflow_monitor"] = {"enabled": False}
            cfg["token_monitor"] = {"enabled": False}
            cfg["app_usage_monitor"] = {"enabled": False}
            cfg["incident_handoff"] = {"enabled": False}
            cfg["runtime_monitor"] = {
                "enabled": True,
                "project_registry": str(registry),
            }

            def fake_run_shell(command: str, timeout: int = 20):
                if "pgrep -af" in command:
                    return 1, "", ""
                self.fail(f"unexpected command: {command}")

            state = module.default_state()
            with mock.patch.object(module, "run_shell", side_effect=fake_run_shell):
                result = module.run_scan(
                    mode="incremental",
                    cfg=cfg,
                    state=state,
                    task_id="cron:ops-incremental-monitor",
                    daily_major_only=True,
                    force_fallback=False,
                    normal_log_mode_override="",
                )

        self.assertTrue(result.notify)
        self.assertIn("runtime_process_missing=1", result.record["risk_reasons"])
        self.assertEqual(result.record["runtime_health"]["summary"]["required_missing_count"], 1)
        self.assertIn("project-b", result.output)
        self.assertIn("project-web", result.output)

    def test_run_scan_suppresses_same_workflow_failure_across_modes(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jobs_file = tmp / "jobs.json"
            shared_alert_state = tmp / "alert-dedupe-state.json"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "f603d2ac-2dcf-4f7a-9efe-26f0e0f8d24e",
                                "name": "ops_system_schedule_audit",
                                "agentId": "ops-agent",
                                "enabled": True,
                                "state": {
                                    "lastStatus": "error",
                                    "consecutiveErrors": 1,
                                    "lastRunAtMs": 1710112222000,
                                    "lastError": "GrammyError: Call to 'sendMessage' failed! (401: Unauthorized)",
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = module.default_config()
            cfg["log_roots"] = []
            cfg["service_monitor"] = {"enabled": False}
            cfg["system_monitor"] = {"enabled": False}
            cfg["runtime_monitor"] = {"enabled": False}
            cfg["token_monitor"] = {"enabled": False}
            cfg["app_usage_monitor"] = {"enabled": False}
            cfg["incident_handoff"] = {"enabled": False}
            cfg["workflow_monitor"] = {
                "enabled": True,
                "jobs_file": str(jobs_file),
                "max_report_jobs": 8,
                "stale_error_minutes": 30,
                "ignore_job_names": [],
            }
            cfg["notify_policy"]["shared_alert_state_file"] = str(shared_alert_state)

            state = module.default_state()
            with mock.patch.object(module, "collect_services", return_value=({}, "")):
                first = module.run_scan(
                    mode="incremental",
                    cfg=cfg,
                    state=state,
                    task_id="cron:ops-incremental-monitor",
                    daily_major_only=True,
                    force_fallback=False,
                    normal_log_mode_override="",
                )
                second = module.run_scan(
                    mode="full",
                    cfg=cfg,
                    state=state,
                    task_id="cron:ops-full-calibration",
                    daily_major_only=True,
                    force_fallback=False,
                    normal_log_mode_override="",
                )

        self.assertTrue(first.notify)
        self.assertFalse(first.record.get("shared_alert_suppressed", False))
        self.assertFalse(second.notify)
        self.assertTrue(second.record.get("shared_alert_suppressed", False))
        self.assertIn(
            "workflow_repeat_within_cooldown",
            str(second.record.get("shared_alert_suppressed_reason", "")),
        )


if __name__ == "__main__":
    unittest.main()

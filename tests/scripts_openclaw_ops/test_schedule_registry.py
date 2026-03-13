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


class ScheduleRegistryTests(unittest.TestCase):
    def test_build_schedule_registry_covers_openclaw_and_external_surfaces(self):
        module = load_module(
            "export_schedule_registry",
            "scripts/openclaw-ops/export_schedule_registry.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jobs_file = tmp / "jobs.json"
            mapping_file = tmp / "jobs_agent_mapping.md"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "c2c75adf-5e80-4b50-bf18-40ceadfa6bd6",
                                "name": "task_executor_10m",
                                "agentId": "ops-agent",
                                "schedule": {"everyMs": 600000},
                                "payload": {"message": "run task executor"},
                            },
                            {
                                "id": "0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a",
                                "name": "reviewer_incremental_daily_4am",
                                "agentId": "reviewer",
                                "schedule": {"cron": "0 4 * * *"},
                                "payload": {"message": "review code"},
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            mapping_file.write_text(
                "\n".join(
                    [
                        "# OpenClaw Cron -> Agent Mapping",
                        "- c2c75adf-5e80-4b50-bf18-40ceadfa6bd6 | task_executor_10m | agent=ops-agent | exists=True | schedule=600000",
                        "- 0f3ba2df-1af7-4dd7-9b90-a4c9114d8f6a | reviewer_incremental_daily_4am | agent=reviewer | exists=True | schedule=0 4 * * *",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            registry = module.build_schedule_registry(
                jobs_file=jobs_file,
                mapping_file=mapping_file,
                profile="core",
            )

        managed = {item["schedule_name"]: item for item in registry["openclaw_managed"]}
        self.assertIn("task_executor_10m", managed)
        self.assertIn("reviewer_incremental_daily_4am", managed)
        self.assertEqual(managed["task_executor_10m"]["owner_agent"], "ops-agent")
        self.assertEqual(managed["task_executor_10m"]["executor_agent"], "assignee-router")
        self.assertEqual(managed["task_executor_10m"]["capability"], "task_execution_orchestration")
        self.assertEqual(managed["reviewer_incremental_daily_4am"]["surface_type"], "openclaw_cron")
        self.assertEqual(managed["reviewer_incremental_daily_4am"]["trigger"], "0 4 * * *")

        external_types = {item["surface_type"] for item in registry["external_attached"]}
        self.assertEqual(
            external_types,
            {"systemd_timer", "user_crontab", "root_crontab", "cron_d", "saas_scheduler"},
        )

        agents = {item["agent_name"]: item for item in registry["agents"]}
        self.assertIn("ops-agent", agents)
        self.assertIn("reviewer", agents)
        self.assertIn("task_executor_10m", agents["ops-agent"]["owned_schedules"])
        self.assertIn("reviewer_incremental_daily_4am", agents["reviewer"]["owned_schedules"])


if __name__ == "__main__":
    unittest.main()

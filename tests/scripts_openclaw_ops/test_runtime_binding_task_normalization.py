import argparse
import importlib.util
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


class RuntimeBindingTaskNormalizationTests(unittest.TestCase):
    def test_policy_enforcer_create_task_marks_runtime_binding_as_passed(self):
        module = load_module(
            "policy_enforcer",
            "skills/library/control-plane-ops/scripts/policy/policy_enforcer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = module.RuntimePaths(
                db=root / "task_center.db",
                policy_file=root / "policy-config.json",
                routing_file=root / "routing-rules.json",
                pricing_file=root / "token-pricing.json",
            )
            module.cmd_init(paths, force=True)
            enforcer = module.PolicyEnforcer(paths)
            try:
                args = argparse.Namespace(
                    task_id="cron:ops-conversation-evolution",
                    task_type="ops_runtime_cron",
                    reason="[CRON_RUNTIME] bind cron:ops-conversation-evolution",
                    source="project-agent/dialog-review",
                    request_source="ai",
                    priority="low",
                    risk_level="low",
                    pool="jobs",
                    assignee="project-agent",
                    owner="",
                    change_id="",
                    entry_agent="",
                    need_human_confirm="false",
                    human_confirmed="true",
                    requirement="Auto register runtime task for cron:ops-conversation-evolution to bind observability records.",
                    result_output="Runtime task exists and accepts module/communication/report records.",
                    acceptance="Task can be used for cron observability binding without manual action.",
                    observable_outputs="module_logs,module_communications,agent_task_reports,planner_summary",
                    acceptance_thresholds="At least one runtime observability record is bound to this task.",
                    context_json="",
                    context_file="",
                    force_needs_clarification="false",
                    clarification_reason="",
                    scheduled_at="2026-03-12T15:29:11+00:00",
                    actor="project-agent",
                )
                created = enforcer.create_task(args)
            finally:
                enforcer.close()

        self.assertEqual(created["status"], "passed")
        self.assertEqual(created["action"], "runtime_binding")
        self.assertEqual(created["completed_at"], "2026-03-12T15:29:11+00:00")
        self.assertEqual(created["workflow_profile_id"], "")
        self.assertEqual(created["workflow_channel"], "")
        self.assertEqual(created["selection_reason"], "")

    def test_normalize_runtime_binding_tasks_updates_legacy_backlog_rows(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        normalize_module = load_module(
            "normalize_runtime_binding_tasks",
            "skills/library/openclaw-workflow-manager/scripts/normalize_runtime_binding_tasks.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "cron:ops-self-evolution",
                        "pool": "jobs",
                        "task_type": "ops_runtime_cron",
                        "reason": "[CRON_RUNTIME] bind cron:ops-self-evolution",
                        "source": "self-evolution-agent/weekly-review",
                        "request_source": "ai",
                        "priority": "low",
                        "risk_level": "low",
                        "assignee": "self-evolution-agent",
                        "status": "pending",
                        "requirement": "Bind runtime observability for self evolution.",
                        "result_output": "Runtime task exists and accepts module/communication/report records.",
                        "acceptance": "Task can be used for cron observability binding without manual action.",
                        "observable_outputs": "module_logs,module_communications,agent_task_reports,planner_summary",
                        "acceptance_thresholds": "At least one runtime observability record is bound to this task.",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            result = normalize_module.normalize_runtime_binding_tasks(db_path, dry_run=False)

            task_center = task_center_module.TaskCenter(db_path)
            try:
                task = task_center.get_task("cron:ops-self-evolution")
            finally:
                task_center.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(task["status"], "passed")
        self.assertEqual(task["action"], "runtime_binding")
        self.assertTrue(str(task["completed_at"]).strip())

    def test_normalize_runtime_binding_tasks_dry_run_preserves_existing_status(self):
        task_center_module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )
        normalize_module = load_module(
            "normalize_runtime_binding_tasks",
            "skills/library/openclaw-workflow-manager/scripts/normalize_runtime_binding_tasks.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "cron:ops-governance-evolution",
                        "pool": "jobs",
                        "task_type": "ops_runtime_cron",
                        "reason": "[CRON_RUNTIME] bind cron:ops-governance-evolution",
                        "source": "project-agent/governance-review",
                        "request_source": "ai",
                        "priority": "low",
                        "risk_level": "low",
                        "assignee": "project-agent",
                        "status": "pending",
                        "requirement": "Bind runtime observability for governance evolution.",
                        "result_output": "Runtime task exists and accepts module/communication/report records.",
                        "acceptance": "Task can be used for cron observability binding without manual action.",
                        "observable_outputs": "module_logs,module_communications,agent_task_reports,planner_summary",
                        "acceptance_thresholds": "At least one runtime observability record is bound to this task.",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            result = normalize_module.normalize_runtime_binding_tasks(db_path, dry_run=True)

            task_center = task_center_module.TaskCenter(db_path)
            try:
                task = task_center.get_task("cron:ops-governance-evolution")
            finally:
                task_center.close()

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(task["status"], "pending")
        self.assertIsNone(task.get("action"))


if __name__ == "__main__":
    unittest.main()

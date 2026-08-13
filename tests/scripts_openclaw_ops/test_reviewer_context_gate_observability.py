import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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


class ReviewerContextGateObservabilityTests(unittest.TestCase):
    def test_emit_policy_observability_does_not_report_context_gate_task_ids(self):
        module = load_module(
            "reviewer_cron_runner",
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            run_file = Path(tmpdir) / "reviewer-run.json"
            calls: list[list[str]] = []

            def fake_invoke_policy_enforcer(_db_path: Path, args: list[str], timeout: int = 30):
                calls.append(list(args))
                if args and args[0] == "planner-summary":
                    return True, {"ok": True, "summary": {"planner_id": "coordinator"}}, ""
                return True, {"ok": True}, ""

            args = SimpleNamespace(
                project_context_db=str(db_path),
                task_id="cron:reviewer-weekly-structure",
                mode="weekly_structure",
            )
            result = module.RunResult(
                notify=True,
                output="blocked",
                record={
                    "run_id": "run-1",
                    "mode": "weekly_structure",
                    "run_duration_ms": 298,
                    "risk_reasons": ["project_context_gate_blocked"],
                    "change_reasons": [],
                    "issue_stats": {},
                    "context_gate": {
                        "items": [
                            {
                                "task_id": "todo-reviewer-context-20260310201306-e967d2",
                                "status": "pending",
                            }
                        ]
                    },
                },
            )

            with mock.patch.object(
                module,
                "ensure_task_binding",
                return_value=("cron:reviewer-weekly-structure", ""),
            ):
                with mock.patch.object(
                    module,
                    "invoke_policy_enforcer",
                    side_effect=fake_invoke_policy_enforcer,
                ):
                    module.emit_policy_observability(args, result, run_file)

        report_targets = [
            command[command.index("--task-id") + 1]
            for command in calls
            if command and command[0] == "report-agent-result" and "--task-id" in command
        ]

        self.assertEqual(report_targets, ["cron:reviewer-weekly-structure"])


if __name__ == "__main__":
    unittest.main()

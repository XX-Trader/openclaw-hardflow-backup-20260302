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


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class UpgradeFeedbackPromotionTests(unittest.TestCase):
    def test_runner_can_auto_apply_workflow_promotion_to_registry(self):
        module = load_module(
            "upgrade_feedback_runner",
            "scripts/openclaw-ops/upgrade_feedback_runner.py",
        )

        report_payloads = [
            {
                "run_id": "exec-promote-baseline-1",
                "started_at": "2026-03-20T10:00:00+00:00",
                "finished_at": "2026-03-20T10:08:00+00:00",
                "tasks_selected": 2,
                "tasks_executed": 2,
                "tasks_skipped": 0,
                "tasks_failed": 2,
                "preflight_warning_tasks": 1,
                "preflight_blocked_tasks": 1,
                "results": [
                    {
                        "task_id": "todo-1",
                        "task_type": "governance_evolution_context_preflight",
                        "assignee": "project-agent",
                        "status": "failed",
                        "task_status_after": "failed",
                        "report_status": "failed",
                        "reason": "preflight_strict_blocked",
                        "quality_score": 20,
                        "solved": False,
                        "resolution_summary": "manifest mismatch",
                    },
                    {
                        "task_id": "todo-2",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "failed",
                        "report_status": "failed",
                        "reason": "failed",
                        "quality_score": 48,
                        "solved": False,
                        "resolution_summary": "missing evidence",
                    },
                ],
            },
            {
                "run_id": "exec-promote-baseline-2",
                "started_at": "2026-03-20T18:00:00+00:00",
                "finished_at": "2026-03-20T18:09:00+00:00",
                "tasks_selected": 2,
                "tasks_executed": 2,
                "tasks_skipped": 0,
                "tasks_failed": 2,
                "preflight_warning_tasks": 0,
                "preflight_blocked_tasks": 1,
                "results": [
                    {
                        "task_id": "todo-3",
                        "task_type": "governance_evolution_context_preflight",
                        "assignee": "project-agent",
                        "status": "failed",
                        "task_status_after": "failed",
                        "report_status": "failed",
                        "reason": "call_agent_exception:timeout",
                        "quality_score": 24,
                        "solved": False,
                        "resolution_summary": "gateway timeout",
                    },
                    {
                        "task_id": "todo-4",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "partial",
                        "report_status": "partial",
                        "reason": "partial",
                        "quality_score": 50,
                        "solved": False,
                        "resolution_summary": "partial output",
                    },
                ],
            },
            {
                "run_id": "exec-promote-candidate-1",
                "started_at": "2026-03-21T10:00:00+00:00",
                "finished_at": "2026-03-21T10:06:00+00:00",
                "tasks_selected": 2,
                "tasks_executed": 2,
                "tasks_skipped": 0,
                "tasks_failed": 0,
                "preflight_warning_tasks": 0,
                "preflight_blocked_tasks": 0,
                "results": [
                    {
                        "task_id": "todo-5",
                        "task_type": "governance_evolution_context_preflight",
                        "assignee": "project-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 90,
                        "solved": True,
                        "resolution_summary": "context prepared",
                    },
                    {
                        "task_id": "todo-6",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 92,
                        "solved": True,
                        "resolution_summary": "evidence added",
                    },
                ],
            },
            {
                "run_id": "exec-promote-candidate-2",
                "started_at": "2026-03-21T18:00:00+00:00",
                "finished_at": "2026-03-21T18:05:00+00:00",
                "tasks_selected": 2,
                "tasks_executed": 2,
                "tasks_skipped": 0,
                "tasks_failed": 0,
                "preflight_warning_tasks": 0,
                "preflight_blocked_tasks": 0,
                "results": [
                    {
                        "task_id": "todo-7",
                        "task_type": "governance_evolution_context_preflight",
                        "assignee": "project-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 91,
                        "solved": True,
                        "resolution_summary": "context prepared",
                    },
                    {
                        "task_id": "todo-8",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 93,
                        "solved": True,
                        "resolution_summary": "stable structure",
                    },
                ],
            },
        ]

        registry_payload = {
            "schema_version": "2026-03-22",
            "default_profile_id": "coding-default",
            "default_channel": "stable",
            "profiles": [
                {
                    "profile_id": "coding-default",
                    "channel": "stable",
                    "version": "stable-v1",
                    "enabled": True,
                    "display_name": "默认编码工作流",
                    "description": "稳定通道",
                    "entry_task_types": ["workflow"],
                    "promotion_target_channel": "candidate",
                    "score_policy_ref": "stable-score.json",
                    "runtime_entry": "stable-runner",
                },
                {
                    "profile_id": "coding-default",
                    "channel": "candidate",
                    "version": "candidate-v2",
                    "enabled": True,
                    "display_name": "默认编码工作流候选通道",
                    "description": "候选通道",
                    "entry_task_types": ["workflow", "clarification_required"],
                    "promotion_target_channel": "stable",
                    "score_policy_ref": "candidate-score.json",
                    "runtime_entry": "candidate-runner",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "executor-runs"
            output_dir = tmp / "upgrade-feedback"
            state_file = tmp / "state.json"
            registry_file = tmp / "workflow-profile-registry.json"
            run_dir.mkdir(parents=True, exist_ok=True)
            for idx, payload in enumerate(report_payloads, start=1):
                write_json(run_dir / f"run-{idx}.json", payload)
            write_json(registry_file, registry_payload)

            result = module.build_upgrade_feedback_bundle(
                executor_run_dir=run_dir,
                output_dir=output_dir,
                state_file=state_file,
                workflow_target="task_executor_10m",
                skill_name="openclaw-evolution-upgrader",
                skill_assignee="optimization-agent",
                baseline_count=2,
                candidate_count=2,
                workflow_profile_registry=registry_file,
                auto_apply_workflow_promotion=True,
                promotion_operator="upgrade-feedback-runner",
            )

            updated_registry = json.loads(registry_file.read_text(encoding="utf-8"))
            latest_summary = json.loads((output_dir / "latest-summary.json").read_text(encoding="utf-8"))

        stable_entry = next(
            item for item in updated_registry["profiles"] if item["profile_id"] == "coding-default" and item["channel"] == "stable"
        )
        self.assertEqual(result["workflow_registry_promotion"]["status"], "promoted")
        self.assertEqual(latest_summary["workflow_registry_promotion"]["status"], "promoted")
        self.assertEqual(stable_entry["runtime_entry"], "candidate-runner")
        self.assertEqual(stable_entry["score_policy_ref"], "candidate-score.json")
        self.assertEqual(stable_entry["version"], "candidate-v2")
        self.assertEqual(updated_registry["last_promotion"]["operator"], "upgrade-feedback-runner")
        self.assertEqual(len(updated_registry["promotion_history"]), 1)


if __name__ == "__main__":
    unittest.main()

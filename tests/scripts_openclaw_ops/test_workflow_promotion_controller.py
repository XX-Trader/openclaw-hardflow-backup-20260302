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


class WorkflowPromotionControllerTests(unittest.TestCase):
    def test_apply_workflow_promotion_copies_candidate_runtime_fields_into_stable(self):
        module = load_module(
            "workflow_promotion_controller",
            "scripts/openclaw-ops/workflow_promotion_controller.py",
        )

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
        summary_payload = {
            "generated_at": "2026-03-22T06:00:00+00:00",
            "baseline_run_ids": ["baseline-1", "baseline-2"],
            "candidate_run_ids": ["candidate-1", "candidate-2"],
            "workflow_promoted": True,
            "workflow_scorecard": {
                "decision": {
                    "promote_to_new_baseline": True,
                    "baseline_average": 78.0,
                    "candidate_average": 89.0,
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            registry_file = tmp / "workflow-profile-registry.json"
            summary_file = tmp / "latest-summary.json"
            write_json(registry_file, registry_payload)
            write_json(summary_file, summary_payload)

            result = module.apply_workflow_promotion(
                registry_file=registry_file,
                summary_file=summary_file,
                profile_id="coding-default",
                stable_channel="stable",
                candidate_channel="candidate",
                operator="upgrade-feedback-runner",
            )
            updated_registry = json.loads(registry_file.read_text(encoding="utf-8"))

        stable_entry = next(
            item for item in updated_registry["profiles"] if item["profile_id"] == "coding-default" and item["channel"] == "stable"
        )
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(stable_entry["runtime_entry"], "candidate-runner")
        self.assertEqual(stable_entry["score_policy_ref"], "candidate-score.json")
        self.assertEqual(stable_entry["version"], "candidate-v2")
        self.assertEqual(stable_entry["display_name"], "默认编码工作流")
        self.assertEqual(stable_entry["promotion_target_channel"], "candidate")
        self.assertEqual(updated_registry["last_promotion"]["profile_id"], "coding-default")
        self.assertEqual(len(updated_registry["promotion_history"]), 1)

    def test_rollback_workflow_promotion_restores_previous_stable_snapshot(self):
        module = load_module(
            "workflow_promotion_controller",
            "scripts/openclaw-ops/workflow_promotion_controller.py",
        )

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
        summary_payload = {
            "generated_at": "2026-03-22T06:00:00+00:00",
            "baseline_run_ids": ["baseline-1", "baseline-2"],
            "candidate_run_ids": ["candidate-1", "candidate-2"],
            "workflow_promoted": True,
            "workflow_scorecard": {
                "decision": {
                    "promote_to_new_baseline": True,
                    "baseline_average": 78.0,
                    "candidate_average": 89.0,
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            registry_file = tmp / "workflow-profile-registry.json"
            summary_file = tmp / "latest-summary.json"
            write_json(registry_file, registry_payload)
            write_json(summary_file, summary_payload)

            promoted = module.apply_workflow_promotion(
                registry_file=registry_file,
                summary_file=summary_file,
            )
            rolled_back = module.rollback_workflow_promotion(
                registry_file=registry_file,
                profile_id="coding-default",
                stable_channel="stable",
                promotion_id=promoted["promotion_id"],
                operator="human",
            )
            updated_registry = json.loads(registry_file.read_text(encoding="utf-8"))

        stable_entry = next(
            item for item in updated_registry["profiles"] if item["profile_id"] == "coding-default" and item["channel"] == "stable"
        )
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual(stable_entry["runtime_entry"], "stable-runner")
        self.assertEqual(stable_entry["score_policy_ref"], "stable-score.json")
        self.assertEqual(stable_entry["version"], "stable-v1")
        self.assertEqual(stable_entry["last_rollback_promotion_id"], promoted["promotion_id"])
        self.assertEqual(updated_registry["last_rollback"]["promotion_id"], promoted["promotion_id"])
        self.assertEqual(len(updated_registry["rollback_history"]), 1)


if __name__ == "__main__":
    unittest.main()

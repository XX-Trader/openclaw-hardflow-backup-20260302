import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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


class ControlPlaneProfileUpdateDispatcherTests(unittest.TestCase):
    def test_dispatch_creates_profile_update_tasks_only_for_ready_items(self):
        dispatcher_module = load_module(
            "control_plane_profile_update_dispatcher",
            "scripts/openclaw-ops/control_plane_profile_update_dispatcher.py",
        )
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        review_report = {
            "report": {
                "generated_at": "2026-03-23T00:00:00+00:00",
                "summary": {
                    "task_count": 3,
                    "ready_for_profile_update_count": 2,
                    "blocked_count": 1,
                    "pending_count": 0,
                },
                "items": [
                    {
                        "task_id": "todo-opt-ready",
                        "change_id": "control-plane-optimization:ready",
                        "status": "passed",
                        "execution_workflow_profile_id": "coding-default",
                        "execution_workflow_channel": "stable",
                        "execution_stage_id": "implement",
                        "target_workflow_profile_id": "docs-default",
                        "target_stage_id": "draft",
                        "target_stage_label": "文档草拟",
                        "recommendation_type": "parallelize_stage_candidate",
                        "ready_for_profile_update": True,
                        "blocking_reasons": [],
                        "latest_agent_report_summary": "已验证并可回写 profile",
                    },
                    {
                        "task_id": "todo-opt-duplicate",
                        "change_id": "control-plane-optimization:duplicate",
                        "status": "passed",
                        "execution_workflow_profile_id": "coding-default",
                        "execution_workflow_channel": "stable",
                        "execution_stage_id": "review",
                        "target_workflow_profile_id": "coding-default",
                        "target_stage_id": "review",
                        "target_stage_label": "评审",
                        "recommendation_type": "strengthen_stage_gate",
                        "ready_for_profile_update": True,
                        "blocking_reasons": [],
                        "latest_agent_report_summary": "已有待处理 profile update 任务",
                    },
                    {
                        "task_id": "todo-opt-blocked",
                        "change_id": "control-plane-optimization:blocked",
                        "status": "failed",
                        "execution_workflow_profile_id": "coding-default",
                        "execution_workflow_channel": "stable",
                        "execution_stage_id": "review",
                        "target_workflow_profile_id": "coding-default",
                        "target_stage_id": "review",
                        "target_stage_label": "评审",
                        "recommendation_type": "strengthen_stage_gate",
                        "ready_for_profile_update": False,
                        "blocking_reasons": ["critical_incidents"],
                        "latest_agent_report_summary": "仍有 incident",
                    },
                ],
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            review_file = Path(tmpdir) / "review.json"
            task_db = Path(tmpdir) / "task_center.db"
            write_json(review_file, review_report)

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-existing-profile-update",
                        "pool": "todo",
                        "task_type": "workflow_profile_update",
                        "reason": "existing profile update",
                        "source": "control-plane-profile-update-dispatcher",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "assignee": "reviewer",
                        "change_id": "control-plane-profile-update:control-plane-optimization:duplicate",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "selection_reason": "control_plane_profile_update_dispatcher",
                        "selection_inputs": {
                            "origin_task_id": "todo-opt-duplicate",
                        },
                        "requirement": "existing",
                        "result_output": "existing",
                        "acceptance": "existing",
                        "observable_outputs": "existing",
                        "acceptance_thresholds": "existing",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            dispatch = dispatcher_module.dispatch_control_plane_profile_update_tasks(
                review_file=review_file,
                task_db=task_db,
                execution_workflow_profile="coding-default",
                execution_workflow_channel="stable",
                schedule_gap_minutes=45,
            )

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                created_task = task_center.get_task(
                    dispatch["created"][0]["task_id"],
                    display_safe=False,
                )
            finally:
                task_center.close()

        self.assertEqual(dispatch["created_count"], 1)
        self.assertEqual(dispatch["skipped_count"], 2)
        self.assertEqual(dispatch["source_summary"]["ready_for_profile_update_count"], 2)
        self.assertEqual(dispatch["created"][0]["origin_task_id"], "todo-opt-ready")
        self.assertEqual(dispatch["created"][0]["task_type"], "workflow_profile_update")
        self.assertEqual(created_task["source"], "control-plane-profile-update-dispatcher")
        self.assertEqual(created_task["task_type"], "workflow_profile_update")
        self.assertEqual(created_task["workflow_profile_id"], "coding-default")
        self.assertEqual(created_task["workflow_channel"], "stable")
        self.assertEqual(created_task["stage_id"], "implement")
        skipped_reasons = {item["origin_task_id"]: item["reason"] for item in dispatch["skipped"]}
        self.assertEqual(skipped_reasons["todo-opt-duplicate"], "duplicate_open_change_id")
        self.assertEqual(skipped_reasons["todo-opt-blocked"], "not_ready_for_profile_update")
        self.assertIn("# OpenClaw Control Plane Profile Update Dispatcher", dispatch["markdown"])

    def test_main_writes_json_and_markdown_outputs(self):
        dispatcher_module = load_module(
            "control_plane_profile_update_dispatcher",
            "scripts/openclaw-ops/control_plane_profile_update_dispatcher.py",
        )
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        review_report = {
            "report": {
                "generated_at": "2026-03-23T00:00:00+00:00",
                "summary": {
                    "task_count": 1,
                    "ready_for_profile_update_count": 1,
                    "blocked_count": 0,
                    "pending_count": 0,
                },
                "items": [
                    {
                        "task_id": "todo-opt-cli",
                        "change_id": "control-plane-optimization:cli",
                        "status": "passed",
                        "execution_workflow_profile_id": "coding-default",
                        "execution_workflow_channel": "stable",
                        "execution_stage_id": "implement",
                        "target_workflow_profile_id": "docs-default",
                        "target_stage_id": "draft",
                        "target_stage_label": "文档草拟",
                        "recommendation_type": "stage_simplification_candidate",
                        "ready_for_profile_update": True,
                        "blocking_reasons": [],
                        "latest_agent_report_summary": "可继续进入 profile update",
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            review_file = Path(tmpdir) / "review.json"
            task_db = Path(tmpdir) / "task_center.db"
            json_output = Path(tmpdir) / "dispatch.json"
            markdown_output = Path(tmpdir) / "dispatch.md"
            write_json(review_file, review_report)

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = dispatcher_module.main(
                    [
                        "--review-file",
                        str(review_file),
                        "--task-db",
                        str(task_db),
                        "--execution-workflow-profile",
                        "coding-default",
                        "--execution-workflow-channel",
                        "stable",
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertIn("dispatch", payload)
        self.assertEqual(json_payload["dispatch"]["created_count"], 1)
        self.assertIn("# OpenClaw Control Plane Profile Update Dispatcher", markdown_text)


if __name__ == "__main__":
    unittest.main()

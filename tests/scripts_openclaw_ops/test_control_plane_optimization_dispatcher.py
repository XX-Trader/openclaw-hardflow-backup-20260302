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


class ControlPlaneOptimizationDispatcherTests(unittest.TestCase):
    def _build_report_payload(self) -> dict:
        return {
            "generated_at": "2026-03-23T00:00:00+00:00",
            "lookback_hours": 24,
            "summary": {
                "scanned_task_count": 6,
                "open_incident_count": 1,
            },
            "recommendations": [
                {
                    "type": "strengthen_stage_gate",
                    "severity": "high",
                    "workflow_profile_id": "coding-default",
                    "stage_id": "review",
                    "stage_label": "评审",
                    "reason": "critical incident 仍然存在",
                    "action": "补充 gate、证据和验证规则",
                },
                {
                    "type": "clarification_upgrade_needed",
                    "severity": "high",
                    "workflow_profile_id": "research-default",
                    "stage_id": "clarify",
                    "stage_label": "澄清",
                    "reason": "人工协助与待澄清任务偏多",
                    "action": "加强需求澄清模板与上下文收口",
                },
                {
                    "type": "parallelize_stage_candidate",
                    "severity": "medium",
                    "workflow_profile_id": "docs-default",
                    "stage_id": "draft",
                    "stage_label": "草拟",
                    "reason": "阶段稳定且已有多次晋升",
                    "action": "评估并行批次与并发执行策略",
                },
            ],
            "markdown": "# OpenClaw Control Plane Optimization Advisor\n",
        }

    def test_dispatcher_creates_deduplicated_tasks_from_recommendations(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        dispatcher_module = load_module(
            "control_plane_optimization_dispatcher",
            "scripts/openclaw-ops/control_plane_optimization_dispatcher.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = task_center_module.TaskCenter(db_path)
            task_center.init_schema()
            task_center.close()

            report = self._build_report_payload()
            first = dispatcher_module.dispatch_control_plane_optimization_tasks(
                task_db=db_path,
                report=report,
                execution_workflow_profile="coding-default",
                execution_workflow_channel="stable",
                schedule_gap_minutes=30,
            )
            second = dispatcher_module.dispatch_control_plane_optimization_tasks(
                task_db=db_path,
                report=report,
                execution_workflow_profile="coding-default",
                execution_workflow_channel="stable",
                schedule_gap_minutes=30,
            )

            task_center = task_center_module.TaskCenter(db_path)
            try:
                tasks = task_center.conn.execute(
                    """
                    SELECT task_type, assignee, change_id, workflow_profile_id, workflow_channel,
                           stage_id, selection_reason, selection_inputs, context_payload
                    FROM tasks
                    WHERE source = 'control-plane-optimization-dispatcher'
                    ORDER BY rowid ASC
                    """
                ).fetchall()
            finally:
                task_center.close()

        self.assertEqual(first["created_count"], 3)
        self.assertEqual(first["skipped_count"], 0)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["skipped_count"], 3)
        self.assertEqual(len(tasks), 3)

        first_task = tasks[0]
        second_task = tasks[1]
        third_task = tasks[2]
        self.assertEqual(first_task["task_type"], "workflow_optimization")
        self.assertEqual(first_task["assignee"], "reviewer")
        self.assertEqual(first_task["workflow_profile_id"], "coding-default")
        self.assertEqual(first_task["workflow_channel"], "stable")
        self.assertEqual(first_task["stage_id"], "review")
        self.assertTrue(str(first_task["change_id"]).startswith("control-plane-optimization:"))
        self.assertEqual(second_task["assignee"], "project-agent")
        self.assertEqual(second_task["stage_id"], "clarify")
        self.assertEqual(third_task["assignee"], "backend-dev")
        self.assertEqual(third_task["stage_id"], "implement")

        selection_inputs = json.loads(str(first_task["selection_inputs"] or "{}"))
        context_payload = json.loads(str(first_task["context_payload"] or "{}"))
        self.assertEqual(first_task["selection_reason"], "control_plane_optimization_dispatcher")
        self.assertEqual(selection_inputs["dispatch_source"], "control_plane_optimization_report")
        self.assertEqual(selection_inputs["target_workflow_profile_id"], "coding-default")
        self.assertEqual(selection_inputs["recommendation_type"], "strengthen_stage_gate")
        self.assertEqual(context_payload["target_workflow_profile_id"], "coding-default")
        self.assertEqual(context_payload["target_stage_id"], "review")
        self.assertEqual(context_payload["recommendation"]["action"], "补充 gate、证据和验证规则")

    def test_main_writes_json_and_markdown_outputs(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        dispatcher_module = load_module(
            "control_plane_optimization_dispatcher",
            "scripts/openclaw-ops/control_plane_optimization_dispatcher.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            report_file = Path(tmpdir) / "advisor.json"
            json_output = Path(tmpdir) / "dispatch.json"
            markdown_output = Path(tmpdir) / "dispatch.md"
            task_center = task_center_module.TaskCenter(db_path)
            task_center.init_schema()
            task_center.close()
            write_json(report_file, self._build_report_payload())

            with redirect_stdout(StringIO()):
                payload = dispatcher_module.main(
                    [
                        "--report-file",
                        str(report_file),
                        "--task-db",
                        str(db_path),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertEqual(payload["dispatch"]["created_count"], 3)
        self.assertIn("dispatch", json_payload)
        self.assertIn("created_count", json_payload["dispatch"])
        self.assertIn("# OpenClaw Control Plane Optimization Dispatcher", markdown_text)
        self.assertIn("strengthen_stage_gate", markdown_text)


if __name__ == "__main__":
    unittest.main()

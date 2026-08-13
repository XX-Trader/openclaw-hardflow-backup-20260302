import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "openclaw-ops" / "backlog_runner.py"
TASK_CENTER_PATH = ROOT / "skills" / "library" / "control-plane-ops" / "scripts" / "policy" / "task_center.py"


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def create_task(
    center,
    *,
    task_id: str,
    source: str = "todo_patrol",
    risk_level: str = "low",
    status: str = "pending",
    need_human_confirm: bool = False,
    human_confirmed: bool = False,
    action: str = "",
    selected_route: str = "",
):
    context_payload = {}
    if selected_route:
        context_payload = {
            "route_selection": {
                "mode": "manual_selection",
                "required": True,
                "recommended_route": selected_route,
                "selected_route": selected_route,
            }
        }
    center.create_task(
        {
            "task_id": task_id,
            "pool": "todo",
            "task_type": "todo_dispatch",
            "reason": f"处理 {task_id}",
            "source": source,
            "request_source": "human",
            "priority": "medium",
            "risk_level": risk_level,
            "assignee": "coordinator",
            "status": status,
            "need_human_confirm": need_human_confirm,
            "human_confirmed": human_confirmed,
            "action": action,
            "context_payload": context_payload,
            "requirement": f"完成 {task_id}",
            "result_output": "输出执行报告",
            "acceptance": "通过测试和审查",
            "observable_outputs": "测试结果、审查结论",
            "acceptance_thresholds": "任务通过且无高风险门禁绕过",
        },
        actor="test",
    )


class BacklogRunnerTests(unittest.TestCase):
    def test_dry_run_selects_only_safe_pending_tasks(self):
        runner = load_module("backlog_runner_test_select", RUNNER_PATH)
        task_center = load_module("task_center", TASK_CENTER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "task_center.db"
            center = task_center.TaskCenter(db)
            try:
                center.init_schema()
                create_task(
                    center,
                    task_id="todo-safe",
                    need_human_confirm=True,
                    human_confirmed=True,
                    action="confirmed_for_execution",
                    selected_route="todo_auto_candidate",
                )
                create_task(center, task_id="todo-unselected")
                create_task(center, task_id="todo-human", risk_level="high", need_human_confirm=True)
                create_task(
                    center,
                    task_id="todo-direct-route",
                    human_confirmed=True,
                    need_human_confirm=True,
                    action="manual_direct_run_requested",
                )
            finally:
                center.close()

            report = runner.run_backlog(
                Namespace(
                    task_db=str(db),
                    allowed_source="todo_patrol,todo-deadline-bridge",
                    failed_source="hermes",
                    allowed_next_action="return_to_code_execution",
                    include_failed=False,
                    allow_confirmed_high_risk=False,
                    max_attempts_per_task=1,
                    scan_limit=20,
                    max_items=3,
                    dry_run=True,
                    pipeline_command="project-delivery-pipeline",
                    profile="projectagent",
                    source="backlog-runner",
                    pipeline_timeout_seconds=30,
                    actor="test",
                )
            )

        self.assertEqual(["todo-safe"], [item["task_id"] for item in report["selected"]])
        reasons = {item["reason"] for item in report["skipped"]}
        self.assertIn("human_or_clarification_gate", reasons)
        self.assertIn("manual_pipeline_route_required", reasons)
        self.assertIn("manual_route_not_pipeline:manual_direct_run_requested", reasons)
        self.assertTrue(report["dry_run"])

    def test_executes_pipeline_and_marks_task_passed(self):
        runner = load_module("backlog_runner_test_exec", RUNNER_PATH)
        task_center = load_module("task_center", TASK_CENTER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "task_center.db"
            center = task_center.TaskCenter(db)
            try:
                center.init_schema()
                create_task(
                    center,
                    task_id="todo-safe",
                    need_human_confirm=True,
                    human_confirmed=True,
                    action="confirmed_for_execution",
                    selected_route="coding_workflow",
                )
            finally:
                center.close()

            pipeline_state = {"run_id": "backlog-run-1", "status": "completed", "next_action": "none"}
            completed = runner.subprocess.CompletedProcess(
                args=["project-delivery-pipeline"],
                returncode=0,
                stdout=json.dumps(pipeline_state, ensure_ascii=False),
                stderr="",
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed) as run_mock:
                report = runner.run_backlog(
                    Namespace(
                        task_db=str(db),
                        allowed_source="todo_patrol",
                        failed_source="hermes",
                        allowed_next_action="return_to_code_execution",
                        include_failed=False,
                        allow_confirmed_high_risk=False,
                        max_attempts_per_task=1,
                        scan_limit=20,
                        max_items=1,
                        dry_run=False,
                        pipeline_command="project-delivery-pipeline",
                        profile="projectagent",
                        source="backlog-runner",
                        pipeline_timeout_seconds=30,
                        actor="test",
                    )
                )

            center = task_center.TaskCenter(db)
            try:
                task = center.get_task("todo-safe", display_safe=False)
                outputs = center.list_task_outputs("todo-safe", display_safe=False)
            finally:
                center.close()

        self.assertEqual("passed", task["status"])
        self.assertEqual("backlog-run-1", report["executed"][0]["pipeline_run_id"])
        self.assertEqual("backlog_runner_attempt", outputs[-1]["output_type"])
        recorded_cmd = outputs[-1]["payload"]["command"]
        self.assertEqual(1, recorded_cmd.count("--requirement"))
        self.assertIn("[omitted]", recorded_cmd)
        self.assertNotIn("完成 todo-safe", recorded_cmd)
        cmd = run_mock.call_args.args[0]
        self.assertIn("--emit-json", cmd)
        self.assertIn("--requirement", cmd)
        self.assertIn("projectagent", cmd)

    def test_confirmed_high_risk_task_passes_human_risk_flag_to_pipeline(self):
        runner = load_module("backlog_runner_test_high_risk_confirmed", RUNNER_PATH)
        task_center = load_module("task_center", TASK_CENTER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "task_center.db"
            center = task_center.TaskCenter(db)
            try:
                center.init_schema()
                create_task(
                    center,
                    task_id="todo-risky",
                    risk_level="high",
                    need_human_confirm=True,
                    human_confirmed=True,
                    action="confirmed_for_execution",
                    selected_route="coding_workflow",
                )
            finally:
                center.close()

            pipeline_state = {"run_id": "backlog-run-risky", "status": "completed", "next_action": "none"}
            completed = runner.subprocess.CompletedProcess(
                args=["project-delivery-pipeline"],
                returncode=0,
                stdout=json.dumps(pipeline_state, ensure_ascii=False),
                stderr="",
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed) as run_mock:
                report = runner.run_backlog(
                    Namespace(
                        task_db=str(db),
                        allowed_source="todo_patrol",
                        failed_source="hermes",
                        allowed_next_action="return_to_code_execution",
                        include_failed=False,
                        allow_confirmed_high_risk=True,
                        max_attempts_per_task=1,
                        scan_limit=20,
                        max_items=1,
                        dry_run=False,
                        pipeline_command="project-delivery-pipeline",
                        profile="projectagent",
                        source="backlog-runner",
                        pipeline_timeout_seconds=30,
                        actor="test",
                    )
                )

            center = task_center.TaskCenter(db)
            try:
                outputs = center.list_task_outputs("todo-risky", display_safe=False)
            finally:
                center.close()

        self.assertEqual("todo-risky", report["selected"][0]["task_id"])
        self.assertTrue(report["selected"][0]["human_risk_confirmed"])
        cmd = run_mock.call_args.args[0]
        self.assertIn("--human-risk-confirmed", cmd)
        recorded_cmd = outputs[-1]["payload"]["command"]
        self.assertIn("--human-risk-confirmed", recorded_cmd)

    def test_pipeline_launch_failure_marks_task_failed(self):
        runner = load_module("backlog_runner_test_launch_failure", RUNNER_PATH)
        task_center = load_module("task_center", TASK_CENTER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "task_center.db"
            center = task_center.TaskCenter(db)
            try:
                center.init_schema()
                create_task(
                    center,
                    task_id="todo-safe",
                    need_human_confirm=True,
                    human_confirmed=True,
                    action="confirmed_for_execution",
                    selected_route="coding_workflow",
                )
            finally:
                center.close()

            with mock.patch.object(runner.subprocess, "run", side_effect=FileNotFoundError("missing pipeline")):
                report = runner.run_backlog(
                    Namespace(
                        task_db=str(db),
                        allowed_source="todo_patrol",
                        failed_source="hermes",
                        allowed_next_action="return_to_code_execution",
                        include_failed=False,
                        allow_confirmed_high_risk=False,
                        max_attempts_per_task=1,
                        scan_limit=20,
                        max_items=1,
                        dry_run=False,
                        pipeline_command="missing-project-delivery-pipeline",
                        profile="projectagent",
                        source="backlog-runner",
                        pipeline_timeout_seconds=30,
                        actor="test",
                    )
                )

            center = task_center.TaskCenter(db)
            try:
                task = center.get_task("todo-safe", display_safe=False)
                outputs = center.list_task_outputs("todo-safe", display_safe=False)
            finally:
                center.close()

        self.assertEqual("failed", task["status"])
        self.assertEqual("failed", report["executed"][0]["status"])
        self.assertEqual("pipeline_launch_failed", report["executed"][0]["error"])
        self.assertEqual("backlog_runner_attempt", outputs[-1]["output_type"])
        self.assertEqual("failed", outputs[-1]["status"])
        self.assertEqual("FileNotFoundError", outputs[-1]["payload"]["error_type"])
        self.assertIn("fix_backlog_runner_pipeline_command", outputs[-1]["summary"])


if __name__ == "__main__":
    unittest.main()

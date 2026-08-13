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


class TaskCenterDisplaySanitizationTests(unittest.TestCase):
    def test_get_task_and_task_report_default_to_trace_labels(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-display-safe-1",
                        "pool": "todo",
                        "task_type": "web_intel_review_project_doc",
                        "reason": "display sanitization regression",
                        "source": "project-agent/web-doc-review",
                        "request_source": "ai",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "requirement": "查看 /tmp/report.json 与 /tmp/parsed.json 后执行同步。",
                        "result_output": "输出留痕即可。",
                        "acceptance": "群聊和任务中心不再暴露内部文件路径。",
                        "observable_outputs": "report_file=/tmp/report.json,parsed_file=/tmp/parsed.json",
                        "acceptance_thresholds": "保留运行留痕编号与解析留痕编号。",
                        "context_payload": {
                            "evidence": "/tmp/report.json",
                            "reproduction_steps": "查看 /tmp/report.json 与 /tmp/parsed.json，然后复验。",
                        },
                    },
                    actor="test",
                )
                task_center.start_stage_run(
                    "todo-display-safe-1",
                    "review",
                    "project-agent",
                    "gpt-test",
                    input_ref="/tmp/input.json",
                    details={"report_file": "/tmp/report.json"},
                )
                task_center.finish_stage_run(
                    "todo-display-safe-1",
                    "review",
                    "passed",
                    0,
                    output_ref="/tmp/output.json",
                    details={"parsed_file": "/tmp/parsed.json"},
                )
                task_center.record_module_communication(
                    task_id="todo-display-safe-1",
                    from_module="project-agent/web-doc-review",
                    to_module="coordinator",
                    protocol="policy-enforcer",
                    message_type="task_dispatch",
                    status="acked",
                    payload_ref="/tmp/report.json",
                    details={"evidence": "/tmp/report.json"},
                    actor="project-agent",
                )
                task_center.upsert_agent_task_report(
                    task_id="todo-display-safe-1",
                    agent_id="project-agent",
                    planner_id="coordinator",
                    status="passed",
                    solved=True,
                    resolution_summary="已查看 /tmp/report.json 并完成同步。",
                    resolution_steps=["查看 /tmp/report.json", "同步 /tmp/parsed.json"],
                    failed_items=["/tmp/failure.log"],
                    notify_chat=False,
                    details={"payload_ref": "/tmp/report.json"},
                    actor="project-agent",
                )
                task_center.record_task_output(
                    task_id="todo-display-safe-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="请查看 /tmp/output-report.json",
                    payload={"delivery": {"report_file": "/tmp/output-report.json"}},
                    actor="project-agent",
                )
                task_center.record_task_incident(
                    task_id="todo-display-safe-1",
                    incident_type="needs_clarification",
                    severity="warning",
                    status="open",
                    reason="missing_context",
                    summary="参考 /tmp/incident.json",
                    owner="coordinator",
                    details={"report_file": "/tmp/incident.json"},
                    actor="coordinator",
                )
                task_center.record_benchmark_run(
                    task_id="todo-display-safe-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="benchmark-display-safe-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    baseline_run_ids=["/tmp/baseline-1.json"],
                    candidate_run_ids=["/tmp/candidate-1.json"],
                    summary_file="/tmp/benchmark-summary.json",
                    scorecard_file="/tmp/benchmark-scorecard.json",
                    decision={"promote_to_new_baseline": False},
                    details={"report_file": "/tmp/benchmark-details.json"},
                    actor="upgrade-feedback-runner",
                )

                public_task = task_center.get_task("todo-display-safe-1")
                raw_task = task_center.get_task("todo-display-safe-1", display_safe=False)
                public_report = task_center.task_report("todo-display-safe-1")
                raw_report = task_center.task_report("todo-display-safe-1", display_safe=False)
            finally:
                task_center.close()

        self.assertIn("留痕编号", str(public_task))
        self.assertNotIn("/tmp/report.json", str(public_task))
        self.assertNotIn("/tmp/parsed.json", str(public_task))
        self.assertIn("/tmp/report.json", str(raw_task))
        self.assertIn("/tmp/parsed.json", str(raw_task))

        self.assertIn("留痕编号", str(public_report))
        self.assertIn("输入留痕编号", str(public_report))
        self.assertIn("输出留痕编号", str(public_report))
        self.assertNotIn("/tmp/report.json", str(public_report))
        self.assertNotIn("/tmp/parsed.json", str(public_report))
        self.assertNotIn("/tmp/input.json", str(public_report))
        self.assertNotIn("/tmp/output.json", str(public_report))
        self.assertNotIn("/tmp/output-report.json", str(public_report))
        self.assertNotIn("/tmp/incident.json", str(public_report))
        self.assertNotIn("/tmp/benchmark-summary.json", str(public_report))
        self.assertNotIn("/tmp/benchmark-scorecard.json", str(public_report))
        self.assertIn("/tmp/report.json", str(raw_report))
        self.assertIn("/tmp/parsed.json", str(raw_report))
        self.assertIn("/tmp/input.json", str(raw_report))
        self.assertIn("/tmp/output.json", str(raw_report))
        self.assertIn("/tmp/output-report.json", str(raw_report))
        self.assertIn("/tmp/incident.json", str(raw_report))
        self.assertIn("/tmp/benchmark-summary.json", str(raw_report))
        self.assertIn("/tmp/benchmark-scorecard.json", str(raw_report))

    def test_planner_summary_defaults_to_sanitized_report_view(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-display-safe-2",
                        "pool": "todo",
                        "task_type": "web_intel_collect_repair",
                        "reason": "planner summary sanitization",
                        "source": "web-agent/web-intel-collect",
                        "request_source": "ai",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "requirement": "查看 /tmp/report.json",
                        "result_output": "只返回留痕编号。",
                        "acceptance": "planner summary 不暴露原始路径。",
                        "observable_outputs": "report_file=/tmp/report.json",
                        "acceptance_thresholds": "返回中文留痕编号。",
                    },
                    actor="test",
                )
                task_center.upsert_agent_task_report(
                    task_id="todo-display-safe-2",
                    agent_id="web-agent",
                    planner_id="coordinator",
                    status="failed",
                    solved=False,
                    resolution_summary="失败留痕位于 /tmp/report.json",
                    resolution_steps=["查看 /tmp/report.json"],
                    failed_items=["/tmp/runtime-error.log"],
                    notify_chat=True,
                    details={"evidence": "/tmp/report.json"},
                    actor="web-agent",
                )

                public_summary = task_center.planner_summary(planner_id="coordinator")
                raw_summary = task_center.planner_summary(planner_id="coordinator", display_safe=False)
            finally:
                task_center.close()

        self.assertIn("留痕编号", str(public_summary))
        self.assertNotIn("/tmp/report.json", str(public_summary))
        self.assertNotIn("/tmp/runtime-error.log", str(public_summary))
        self.assertIn("/tmp/report.json", str(raw_summary))
        self.assertIn("/tmp/runtime-error.log", str(raw_summary))

    def test_update_clarification_keeps_raw_context_payload_in_storage(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-display-safe-3",
                        "pool": "todo",
                        "task_type": "context_repair",
                        "reason": "context payload storage regression",
                        "source": "ops-agent",
                        "request_source": "ai",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "requirement": "inspect /tmp/report.json",
                        "result_output": "show trace id only",
                        "acceptance": "public view must not expose the stored path",
                        "observable_outputs": "report_file=/tmp/report.json",
                        "acceptance_thresholds": "raw storage still keeps the original path",
                        "context_payload": {
                            "evidence": "/tmp/report.json",
                            "reproduction_steps": "open /tmp/report.json and verify context",
                        },
                    },
                    actor="test",
                )

                task_center.update_clarification(
                    "todo-display-safe-3",
                    actor="test",
                    needs_clarification=True,
                )
                public_task = task_center.get_task("todo-display-safe-3")
                raw_task = task_center.get_task("todo-display-safe-3", display_safe=False)
            finally:
                task_center.close()

        self.assertIn("\u7559\u75d5\u7f16\u53f7", str(public_task))
        self.assertNotIn("/tmp/report.json", str(public_task))
        self.assertEqual(raw_task["context_payload"]["evidence"], "/tmp/report.json")
        self.assertIn("/tmp/report.json", str(raw_task["context_payload"]))

    def test_daily_summary_defaults_to_trace_labels_for_escalated_tasks(self):
        module = load_module(
            "task_center",
            "skills/library/control-plane-ops/scripts/policy/task_center.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            task_center = module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-display-safe-4",
                        "pool": "todo",
                        "task_type": "ops_workflow_repair",
                        "reason": "follow /tmp/report.json to continue triage",
                        "source": "ops-agent",
                        "request_source": "ai",
                        "priority": "high",
                        "risk_level": "low",
                        "status": "escalated",
                        "failure_count": 3,
                        "requirement": "inspect /tmp/report.json before manual takeover",
                        "result_output": "daily summary uses trace labels",
                        "acceptance": "escalated reasons do not expose raw paths",
                        "observable_outputs": "report_file=/tmp/report.json",
                        "acceptance_thresholds": "public view keeps only trace labels",
                    },
                    actor="test",
                )

                target_date = module.parse_utc_iso(module.utc_now_iso()).date()
                public_summary = task_center.daily_summary(target_date)
                raw_summary = task_center.daily_summary(target_date, display_safe=False)
            finally:
                task_center.close()

        self.assertIn("\u7559\u75d5\u7f16\u53f7", str(public_summary))
        self.assertNotIn("/tmp/report.json", str(public_summary))
        self.assertIn("/tmp/report.json", str(raw_summary))


if __name__ == "__main__":
    unittest.main()

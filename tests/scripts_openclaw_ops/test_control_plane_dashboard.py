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


class ControlPlaneDashboardTests(unittest.TestCase):
    def test_build_snapshot_includes_summary_tasks_benchmark_trends_and_roi(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        dashboard_module = load_module(
            "control_plane_dashboard",
            "scripts/openclaw-ops/control_plane_dashboard.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            benchmark_summary_path = Path(tmpdir) / "latest-summary.json"
            benchmark_summary_path.write_text(
                json.dumps(
                    {
                        "status": "partial_failure",
                        "requested_suite_ids": ["coding-default-core", "research-default-core"],
                        "success_count": 1,
                        "failure_count": 1,
                        "results": [
                            {
                                "suite_id": "coding-default-core",
                                "status": "ok",
                                "summary": {
                                    "workflow_scorecard": {
                                        "decision": {
                                            "promote_to_new_baseline": False,
                                            "veto_reasons": ["critical_incidents_present"],
                                        }
                                    }
                                },
                            }
                        ],
                        "failures": [
                            {
                                "suite_id": "research-default-core",
                                "error_type": "ValueError",
                                "error": "benchmark suite not found",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-dashboard-1",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Need dashboard snapshot",
                        "source": "unit-test",
                        "priority": "high",
                        "risk_level": "high",
                        "status": "running",
                        "workflow_profile_id": "coding-default",
                        "workflow_channel": "candidate",
                        "stage_id": "review",
                        "requirement": "Render dashboard summary.",
                        "result_output": "Dashboard should show top task.",
                        "acceptance": "markdown snapshot",
                        "observable_outputs": "dashboard markdown",
                        "acceptance_thresholds": "visible",
                    },
                    actor="test",
                )
                task_center.record_task_output(
                    task_id="todo-dashboard-1",
                    output_type="agent_report",
                    audience="human",
                    channel="none",
                    status="prepared",
                    summary="需要人工协助",
                    payload={"human_gate": {"requires_human_assistance": True}},
                    actor="backend-dev",
                )
                task_center.record_task_incident(
                    task_id="todo-dashboard-1",
                    incident_type="stage_contract_failed",
                    severity="critical",
                    status="open",
                    reason="contract_failed",
                    summary="仍需人工复核",
                    owner="backend-dev",
                    details={"source": "unit-test"},
                    actor="backend-dev",
                )
                task_center.record_benchmark_run(
                    task_id="todo-dashboard-1",
                    benchmark_suite_id="coding-default-core",
                    benchmark_run_id="dashboard-benchmark-1",
                    workflow_profile_id="coding-default",
                    workflow_channel="candidate",
                    target_kind="workflow",
                    target_id="coding-default",
                    baseline_run_ids=["baseline-1"],
                    candidate_run_ids=["candidate-1"],
                    summary_file=str(benchmark_summary_path),
                    scorecard_file="reports/latest-scorecard.json",
                    decision={"promote_to_new_baseline": False, "veto_reasons": ["critical_incidents_present"]},
                    actor="upgrade-feedback-runner",
                )
                task_center.create_task(
                    {
                        "task_id": "todo-dashboard-2",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Need docs workflow trend",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "docs-default",
                        "workflow_channel": "stable",
                        "stage_id": "draft",
                        "requirement": "Track docs trend.",
                        "result_output": "Trend should include docs workflow.",
                        "acceptance": "workflow breakdown",
                        "observable_outputs": "dashboard markdown",
                        "acceptance_thresholds": "visible",
                    },
                    actor="test",
                )
                task_center.record_benchmark_run(
                    task_id="todo-dashboard-2",
                    benchmark_suite_id="docs-default-core",
                    benchmark_run_id="dashboard-benchmark-2",
                    workflow_profile_id="docs-default",
                    workflow_channel="stable",
                    target_kind="workflow",
                    target_id="docs-default",
                    baseline_run_ids=["baseline-2"],
                    candidate_run_ids=["candidate-2"],
                    summary_file=str(benchmark_summary_path),
                    scorecard_file="reports/docs-scorecard.json",
                    decision={"promote_to_new_baseline": True, "veto_reasons": []},
                    actor="upgrade-feedback-runner",
                )
            finally:
                task_center.close()

            snapshot = dashboard_module.build_control_plane_dashboard_snapshot(
                db_file=db_path,
                lookback_hours=24,
                limit=10,
                benchmark_summary_file=benchmark_summary_path,
                trend_days=7,
            )

        self.assertEqual(snapshot["summary"]["critical_open_incident_count"], 1)
        self.assertEqual(snapshot["hotspots"]["top_veto_reasons"][0]["reason"], "critical_incidents_present")
        self.assertEqual(snapshot["benchmark_overview"]["requested_suite_ids"], ["coding-default-core", "research-default-core"])
        self.assertEqual(snapshot["trend_overview"]["lookback_days"], 7)
        self.assertEqual(snapshot["trend_overview"]["totals"]["benchmark_run_count"], 2)
        self.assertEqual(snapshot["trend_overview"]["totals"]["human_assistance_count"], 1)
        self.assertIn("roi_snapshot", snapshot)
        self.assertIn("tokens_per_benchmark_run", snapshot["roi_snapshot"])
        self.assertIn("workflow_roi_breakdown", snapshot)
        self.assertIn("stage_roi_breakdown", snapshot)
        self.assertTrue(any(item["workflow_profile_id"] == "coding-default" for item in snapshot["workflow_roi_breakdown"]))
        self.assertTrue(any(item["stage_id"] == "review" for item in snapshot["stage_roi_breakdown"]))
        self.assertTrue(any(item["workflow_profile_id"] == "coding-default" for item in snapshot["trend_overview"]["workflow_breakdown"]))
        self.assertTrue(any(item["workflow_profile_id"] == "docs-default" for item in snapshot["trend_overview"]["workflow_breakdown"]))
        self.assertIn("# OpenClaw Control Plane Dashboard", snapshot["markdown"])
        self.assertIn("todo-dashboard-1 coding-default@candidate / 评审", snapshot["markdown"])
        self.assertIn("critical_incidents_present x1", snapshot["markdown"])
        self.assertIn("research-default-core", snapshot["markdown"])
        self.assertIn("## 最近趋势", snapshot["markdown"])
        self.assertIn("## Workflow 分布", snapshot["markdown"])
        self.assertIn("## ROI 摘要", snapshot["markdown"])
        self.assertIn("## Workflow ROI", snapshot["markdown"])
        self.assertIn("## Stage ROI", snapshot["markdown"])
        self.assertIn("docs-default", snapshot["markdown"])

    def test_main_writes_json_markdown_and_html_outputs(self):
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )
        dashboard_module = load_module(
            "control_plane_dashboard",
            "scripts/openclaw-ops/control_plane_dashboard.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            json_output = Path(tmpdir) / "dashboard.json"
            markdown_output = Path(tmpdir) / "dashboard.md"
            html_output = Path(tmpdir) / "dashboard.html"
            task_center = task_center_module.TaskCenter(db_path)
            try:
                task_center.init_schema()
                task_center.create_task(
                    {
                        "task_id": "todo-dashboard-3",
                        "pool": "todo",
                        "task_type": "workflow",
                        "reason": "Write dashboard outputs",
                        "source": "unit-test",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "passed",
                        "workflow_profile_id": "docs-default",
                        "workflow_channel": "stable",
                        "stage_id": "review",
                        "requirement": "emit json and markdown",
                        "result_output": "dashboard files",
                        "acceptance": "outputs created",
                        "observable_outputs": "dashboard snapshot files",
                        "acceptance_thresholds": "ok",
                    },
                    actor="test",
                )
            finally:
                task_center.close()

            with redirect_stdout(StringIO()):
                payload = dashboard_module.main(
                    [
                        "--db",
                        str(db_path),
                        "--trend-days",
                        "5",
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--html-output",
                        str(html_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")
            html_text = html_output.read_text(encoding="utf-8")

        self.assertIn("snapshot", payload)
        self.assertEqual(json_payload["snapshot"]["summary"]["scanned_task_count"], 1)
        self.assertEqual(json_payload["snapshot"]["trend_overview"]["lookback_days"], 5)
        self.assertIn("roi_snapshot", json_payload["snapshot"])
        self.assertIn("workflow_roi_breakdown", json_payload["snapshot"])
        self.assertIn("stage_roi_breakdown", json_payload["snapshot"])
        self.assertIn("# OpenClaw Control Plane Dashboard", markdown_text)
        self.assertIn("## ROI 摘要", markdown_text)
        self.assertIn("## Workflow ROI", markdown_text)
        self.assertIn("## Stage ROI", markdown_text)
        self.assertIn("<!DOCTYPE html>", html_text)
        self.assertIn("OpenClaw Control Plane Dashboard", html_text)
        self.assertIn("ROI 摘要", html_text)
        self.assertIn("Workflow ROI", html_text)
        self.assertIn("Stage ROI", html_text)
        self.assertIn("docs-default", html_text)


if __name__ == "__main__":
    unittest.main()

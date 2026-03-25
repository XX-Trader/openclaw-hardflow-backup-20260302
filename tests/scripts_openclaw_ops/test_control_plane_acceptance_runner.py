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


class ControlPlaneAcceptanceRunnerTests(unittest.TestCase):
    def _build_complete_jobs_payload(self, cron_setup_module) -> dict:
        return {
            "jobs": [
                cron_setup_module.build_benchmark_sweep_job(
                    script_py="/tmp/benchmark_orchestrator.py",
                    executor_run_dir="/tmp/task-center/executor-runs",
                    output_root="/tmp/benchmark-sweeps",
                    state_root="/tmp/benchmark-sweeps/state",
                    benchmark_suite_file="/tmp/policy/benchmark-suite-registry.json",
                    workflow_profile_registry="/tmp/policy/workflow-profile-registry.json",
                    task_db="/tmp/task-center/task_center.db",
                    output_consumer_py="/tmp/benchmark_output_consumer.py",
                    summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
                    consumer_output_file="/tmp/benchmark-sweeps/output/latest-event.json",
                    consumer_notify_on="error",
                    every_ms=86400000,
                    log_mode="silent",
                    auto_create_tasks=False,
                    auto_apply_workflow_promotion=False,
                    promotion_operator="cron-benchmark-sweep",
                    task_score_threshold=80.0,
                    task_schedule_gap_minutes=120,
                    suite_ids=["coding-default-core", "research-default-core"],
                ),
                cron_setup_module.build_benchmark_output_job(
                    script_py="/tmp/benchmark_output_consumer.py",
                    summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
                    output_file="/tmp/benchmark-sweeps/output/latest-event.json",
                    notify_on="error",
                    every_ms=86400000,
                    delay_ms=300000,
                    log_mode="silent",
                ),
                cron_setup_module.build_task_output_broadcast_job(
                    script_py="/tmp/task_output_broadcast_runner.py",
                    db_file="/tmp/task-center/task_center.db",
                    state_file="/tmp/task-output/state.json",
                    output_file="/tmp/task-output/latest-event.json",
                    lookback_hours=24,
                    limit=12,
                    event_limit=200,
                    notify_on="error",
                    every_ms=900000,
                    delay_ms=120000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_summary_job(
                    script_py="/tmp/control_plane_summary_runner.py",
                    db_file="/tmp/task-center/task_center.db",
                    state_file="/tmp/control-plane-summary/state.json",
                    output_file="/tmp/control-plane-summary/latest-event.json",
                    lookback_hours=24,
                    limit=20,
                    notify_on="activity",
                    every_ms=21600000,
                    delay_ms=180000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_dashboard_job(
                    script_py="/tmp/control_plane_dashboard.py",
                    db_file="/tmp/task-center/task_center.db",
                    benchmark_summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
                    json_output="/tmp/control-plane-dashboard/latest-dashboard.json",
                    markdown_output="/tmp/control-plane-dashboard/latest-dashboard.md",
                    html_output="/tmp/control-plane-dashboard/latest-dashboard.html",
                    lookback_hours=24,
                    limit=20,
                    every_ms=21600000,
                    delay_ms=240000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_optimization_job(
                    script_py="/tmp/control_plane_optimization_advisor.py",
                    db_file="/tmp/task-center/task_center.db",
                    json_output="/tmp/control-plane-optimization/latest-report.json",
                    markdown_output="/tmp/control-plane-optimization/latest-report.md",
                    lookback_hours=24,
                    limit=20,
                    every_ms=43200000,
                    delay_ms=360000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_optimization_dispatch_job(
                    script_py="/tmp/control_plane_optimization_dispatcher.py",
                    report_file="/tmp/control-plane-optimization/latest-report.json",
                    task_db="/tmp/task-center/task_center.db",
                    json_output="/tmp/control-plane-optimization-dispatch/latest-report.json",
                    markdown_output="/tmp/control-plane-optimization-dispatch/latest-report.md",
                    execution_workflow_profile="coding-default",
                    execution_workflow_channel="stable",
                    schedule_gap_minutes=30,
                    every_ms=43200000,
                    delay_ms=480000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_optimization_review_job(
                    script_py="/tmp/control_plane_optimization_review_runner.py",
                    task_db="/tmp/task-center/task_center.db",
                    json_output="/tmp/control-plane-optimization-review/latest-report.json",
                    markdown_output="/tmp/control-plane-optimization-review/latest-report.md",
                    lookback_hours=72,
                    limit=20,
                    every_ms=43200000,
                    delay_ms=540000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_profile_update_dispatch_job(
                    script_py="/tmp/control_plane_profile_update_dispatcher.py",
                    review_file="/tmp/control-plane-optimization-review/latest-report.json",
                    task_db="/tmp/task-center/task_center.db",
                    json_output="/tmp/control-plane-profile-update-dispatch/latest-report.json",
                    markdown_output="/tmp/control-plane-profile-update-dispatch/latest-report.md",
                    execution_workflow_profile="coding-default",
                    execution_workflow_channel="stable",
                    schedule_gap_minutes=60,
                    every_ms=43200000,
                    delay_ms=600000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_profile_update_apply_job(
                    script_py="/tmp/control_plane_profile_update_applier.py",
                    task_db="/tmp/task-center/task_center.db",
                    registry_file="/tmp/policy/workflow-profile-registry.json",
                    json_output="/tmp/control-plane-profile-update-apply/latest-report.json",
                    markdown_output="/tmp/control-plane-profile-update-apply/latest-report.md",
                    target_channel="candidate",
                    lookback_hours=72,
                    limit=20,
                    every_ms=43200000,
                    delay_ms=660000,
                    log_mode="silent",
                ),
                cron_setup_module.build_control_plane_profile_update_validation_job(
                    script_py="/tmp/control_plane_profile_update_validation_runner.py",
                    apply_file="/tmp/control-plane-profile-update-apply/latest-report.json",
                    benchmark_suite_file="/tmp/policy/benchmark-suite-registry.json",
                    executor_run_dir="/tmp/task-center/executor-runs",
                    output_root="/tmp/control-plane-profile-update-validation",
                    state_file="/tmp/control-plane-profile-update-validation/state.json",
                    task_db="/tmp/task-center/task_center.db",
                    workflow_profile_registry="/tmp/policy/workflow-profile-registry.json",
                    json_output="/tmp/control-plane-profile-update-validation/latest-report.json",
                    markdown_output="/tmp/control-plane-profile-update-validation/latest-report.md",
                    every_ms=43200000,
                    delay_ms=720000,
                    log_mode="silent",
                    auto_create_tasks=False,
                    auto_apply_workflow_promotion=False,
                    promotion_operator="control-plane-validation",
                ),
            ]
        }

    def test_build_report_accepts_complete_control_plane_jobs(self):
        cron_setup_module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        runner_module = load_module(
            "control_plane_acceptance_runner",
            "scripts/openclaw-ops/control_plane_acceptance_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_file = Path(tmpdir) / "jobs.json"
            write_json(jobs_file, self._build_complete_jobs_payload(cron_setup_module))

            report = runner_module.build_control_plane_acceptance_report(jobs_file=jobs_file)

        self.assertTrue(report["passed"])
        self.assertEqual(report["checked_job_count"], 11)
        self.assertEqual(report["present_job_count"], 11)
        self.assertEqual(report["missing_jobs"], [])
        self.assertEqual(report["failed_jobs"], [])
        self.assertIn("# OpenClaw Control Plane Acceptance", report["markdown"])
        self.assertEqual(len(report["job_checks"]), 11)
        self.assertIn("ops_control_plane_dashboard_6h", report["markdown"])
        self.assertIn("ops_control_plane_optimization_dispatch_12h", report["markdown"])
        self.assertIn("ops_control_plane_optimization_review_12h", report["markdown"])
        self.assertIn("ops_control_plane_profile_update_dispatch_12h", report["markdown"])
        self.assertIn("ops_control_plane_profile_update_apply_12h", report["markdown"])
        self.assertIn("ops_control_plane_profile_update_validation_12h", report["markdown"])

    def test_main_writes_outputs_and_reports_missing_job(self):
        cron_setup_module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        runner_module = load_module(
            "control_plane_acceptance_runner",
            "scripts/openclaw-ops/control_plane_acceptance_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_file = Path(tmpdir) / "jobs.json"
            json_output = Path(tmpdir) / "acceptance.json"
            markdown_output = Path(tmpdir) / "acceptance.md"
            payload = self._build_complete_jobs_payload(cron_setup_module)
            payload["jobs"] = [
                item
                for item in payload["jobs"]
                if item.get("name") != "ops_control_plane_optimization_12h"
            ]
            write_json(jobs_file, payload)

            with redirect_stdout(StringIO()):
                result = runner_module.main(
                    [
                        "--jobs-file",
                        str(jobs_file),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ]
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertFalse(result["report"]["passed"])
        self.assertEqual(result["report"]["missing_jobs"], ["ops_control_plane_optimization_12h"])
        self.assertIn("ops_control_plane_optimization_12h", markdown_text)
        self.assertFalse(json_payload["report"]["passed"])


if __name__ == "__main__":
    unittest.main()

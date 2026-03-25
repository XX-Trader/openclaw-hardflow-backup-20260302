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


class UpgradeFeedbackRunnerTests(unittest.TestCase):
    def test_load_default_benchmark_suite_registry_includes_research_suite(self):
        module = load_module(
            "upgrade_feedback_runner",
            "scripts/openclaw-ops/upgrade_feedback_runner.py",
        )

        registry = module.load_benchmark_suite_registry()

        self.assertEqual(registry["default_suite_id"], "coding-default-core")
        research_suite = next(item for item in registry["suites"] if item["suite_id"] == "research-default-core")
        self.assertEqual(research_suite["workflow_profile_id"], "research-default")
        self.assertEqual(research_suite["target_id"], "research-default")
        docs_suite = next(item for item in registry["suites"] if item["suite_id"] == "docs-default-core")
        self.assertEqual(docs_suite["workflow_profile_id"], "docs-default")
        self.assertEqual(docs_suite["target_id"], "docs-default")
        ops_suite = next(item for item in registry["suites"] if item["suite_id"] == "ops-default-core")
        self.assertEqual(ops_suite["workflow_profile_id"], "ops-default")
        self.assertEqual(ops_suite["target_id"], "ops-default")

    def test_runner_builds_feedback_bundle_and_dedupes_same_candidate_window(self):
        module = load_module(
            "upgrade_feedback_runner",
            "scripts/openclaw-ops/upgrade_feedback_runner.py",
        )

        report_payloads = [
            {
                "run_id": "exec-baseline-1",
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
                        "quality_score": 10,
                        "solved": False,
                        "resolution_summary": "manifest mismatch",
                    },
                    {
                        "task_id": "todo-2",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "partial",
                        "report_status": "partial",
                        "reason": "partial",
                        "quality_score": 52,
                        "solved": False,
                        "resolution_summary": "缺少验证证据",
                        "duration_ms": 8000,
                    },
                ],
            },
            {
                "run_id": "exec-baseline-2",
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
                        "quality_score": 30,
                        "solved": False,
                        "resolution_summary": "gateway timeout",
                        "duration_ms": 13000,
                    },
                    {
                        "task_id": "todo-4",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "failed",
                        "report_status": "failed",
                        "reason": "failed",
                        "quality_score": 50,
                        "solved": False,
                        "resolution_summary": "输出不完整",
                        "duration_ms": 7900,
                    },
                ],
            },
            {
                "run_id": "exec-candidate-1",
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
                        "quality_score": 88,
                        "solved": True,
                        "resolution_summary": "context prepared",
                        "duration_ms": 6000,
                        "input_tokens": 900,
                        "output_tokens": 220,
                    },
                    {
                        "task_id": "todo-6",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 89,
                        "solved": True,
                        "resolution_summary": "已补验证证据",
                        "duration_ms": 6200,
                    },
                ],
            },
            {
                "run_id": "exec-candidate-2",
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
                        "duration_ms": 5900,
                        "input_tokens": 1000,
                        "output_tokens": 210,
                    },
                    {
                        "task_id": "todo-8",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 90,
                        "solved": True,
                        "resolution_summary": "结构化输出稳定",
                        "duration_ms": 6100,
                    },
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "executor-runs"
            output_dir = tmp / "upgrade-feedback"
            state_file = tmp / "state.json"
            run_dir.mkdir(parents=True, exist_ok=True)
            for idx, payload in enumerate(report_payloads, start=1):
                write_json(run_dir / f"run-{idx}.json", payload)

            result = module.build_upgrade_feedback_bundle(
                executor_run_dir=run_dir,
                output_dir=output_dir,
                state_file=state_file,
                workflow_target="task_executor_10m",
                skill_name="openclaw-evolution-upgrader",
                skill_assignee="optimization-agent",
                baseline_count=2,
                candidate_count=2,
            )

            second_result = module.build_upgrade_feedback_bundle(
                executor_run_dir=run_dir,
                output_dir=output_dir,
                state_file=state_file,
                workflow_target="task_executor_10m",
                skill_name="openclaw-evolution-upgrader",
                skill_assignee="optimization-agent",
                baseline_count=2,
                candidate_count=2,
            )

            latest_summary = json.loads((output_dir / "latest-summary.json").read_text(encoding="utf-8"))
            latest_scorecard = json.loads((output_dir / "latest-workflow-scorecard.json").read_text(encoding="utf-8"))
            latest_review = (output_dir / "latest-skill-review.md").read_text(encoding="utf-8")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["workflow_scorecard"]["classification"]["root_cause_type"], "runtime_gap")
        self.assertEqual(result["skill_review"]["classification"]["root_cause_type"], "skill_gap")
        self.assertTrue(result["workflow_scorecard"]["decision"]["promote_to_new_baseline"])
        self.assertTrue(result["skill_review"]["decision"]["promote_to_new_baseline"])
        self.assertEqual(
            result["candidate_run_ids"],
            ["exec-candidate-1", "exec-candidate-2"],
        )
        self.assertEqual(latest_summary["candidate_run_ids"], ["exec-candidate-1", "exec-candidate-2"])
        self.assertEqual(latest_scorecard["target_name"], "task_executor_10m")
        self.assertIn("问题分类：`skill_gap`", latest_review)
        self.assertEqual(second_result["status"], "skipped_no_new_candidate_runs")

    def test_runner_records_benchmark_bundle_and_task_center_run(self):
        module = load_module(
            "upgrade_feedback_runner",
            "scripts/openclaw-ops/upgrade_feedback_runner.py",
        )
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        report_payloads = [
            {
                "run_id": "exec-benchmark-baseline-1",
                "started_at": "2026-03-20T10:00:00+00:00",
                "finished_at": "2026-03-20T10:08:00+00:00",
                "tasks_selected": 1,
                "tasks_executed": 1,
                "tasks_skipped": 0,
                "tasks_failed": 1,
                "preflight_warning_tasks": 1,
                "preflight_blocked_tasks": 1,
                "results": [
                    {
                        "task_id": "todo-1",
                        "task_type": "workflow",
                        "assignee": "backend-dev",
                        "status": "failed",
                        "task_status_after": "failed",
                        "report_status": "failed",
                        "reason": "preflight_strict_blocked",
                        "quality_score": 30,
                        "solved": False,
                        "resolution_summary": "manifest mismatch",
                    }
                ],
            },
            {
                "run_id": "exec-benchmark-candidate-1",
                "started_at": "2026-03-21T10:00:00+00:00",
                "finished_at": "2026-03-21T10:08:00+00:00",
                "tasks_selected": 1,
                "tasks_executed": 1,
                "tasks_skipped": 0,
                "tasks_failed": 0,
                "preflight_warning_tasks": 0,
                "preflight_blocked_tasks": 0,
                "results": [
                    {
                        "task_id": "todo-2",
                        "task_type": "workflow",
                        "assignee": "backend-dev",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 92,
                        "solved": True,
                        "resolution_summary": "验证通过",
                    }
                ],
            },
        ]
        benchmark_suite = {
            "schema_version": "2026-03-22",
            "default_suite_id": "coding-default-core",
            "suites": [
                {
                    "suite_id": "coding-default-core",
                    "workflow_profile_id": "coding-default",
                    "workflow_channel": "stable",
                    "workflow_target": "task_executor_10m",
                    "skill_name": "openclaw-evolution-upgrader",
                    "skill_assignee": "optimization-agent",
                    "baseline_count": 1,
                    "candidate_count": 1,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "executor-runs"
            output_dir = tmp / "upgrade-feedback"
            state_file = tmp / "state.json"
            task_db = tmp / "task_center.db"
            benchmark_suite_file = tmp / "benchmark-suite-registry.json"
            run_dir.mkdir(parents=True, exist_ok=True)
            for idx, payload in enumerate(report_payloads, start=1):
                write_json(run_dir / f"run-{idx}.json", payload)
            write_json(benchmark_suite_file, benchmark_suite)

            result = module.build_upgrade_feedback_bundle(
                executor_run_dir=run_dir,
                output_dir=output_dir,
                state_file=state_file,
                workflow_target="ignored-by-suite",
                skill_name="ignored-by-suite",
                skill_assignee="ignored-by-suite",
                baseline_count=3,
                candidate_count=3,
                task_db=task_db,
                benchmark_suite_file=benchmark_suite_file,
                benchmark_suite_id="coding-default-core",
            )

            task_center = task_center_module.TaskCenter(task_db)
            try:
                task_center.init_schema()
                benchmark_runs = task_center.list_benchmark_runs_by_suite("coding-default-core", display_safe=False)
            finally:
                task_center.close()

        self.assertEqual(result["benchmark_suite"]["suite_id"], "coding-default-core")
        self.assertEqual(result["benchmark_suite"]["workflow_target"], "task_executor_10m")
        self.assertEqual(result["promotion_bundle"]["benchmark_suite_id"], "coding-default-core")
        self.assertEqual(result["promotion_bundle"]["target_kind"], "workflow")
        self.assertEqual(result["promotion_bundle"]["baseline_run_ids"], ["exec-benchmark-baseline-1"])
        self.assertEqual(result["promotion_bundle"]["candidate_run_ids"], ["exec-benchmark-candidate-1"])
        self.assertEqual(len(benchmark_runs), 1)
        self.assertEqual(benchmark_runs[0]["benchmark_suite_id"], "coding-default-core")
        self.assertEqual(benchmark_runs[0]["target_id"], "coding-default")

    def test_runner_can_create_upgrade_tasks_in_task_center(self):
        module = load_module(
            "upgrade_feedback_runner",
            "scripts/openclaw-ops/upgrade_feedback_runner.py",
        )
        task_center_module = load_module(
            "task_center",
            "scripts/openclaw-ops/policy/task_center.py",
        )

        report_payloads = [
            {
                "run_id": "exec-low-baseline-1",
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
                        "quality_score": 45,
                        "solved": False,
                        "resolution_summary": "输出不完整",
                        "duration_ms": 8200,
                    },
                ],
            },
            {
                "run_id": "exec-low-baseline-2",
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
                        "quality_score": 25,
                        "solved": False,
                        "resolution_summary": "gateway timeout",
                        "duration_ms": 13000,
                    },
                    {
                        "task_id": "todo-4",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "partial",
                        "report_status": "partial",
                        "reason": "partial",
                        "quality_score": 48,
                        "solved": False,
                        "resolution_summary": "缺少验证证据",
                        "duration_ms": 7900,
                    },
                ],
            },
            {
                "run_id": "exec-low-candidate-1",
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
                        "quality_score": 68,
                        "solved": True,
                        "resolution_summary": "context prepared",
                        "duration_ms": 6100,
                        "input_tokens": 500,
                        "output_tokens": 120,
                    },
                    {
                        "task_id": "todo-6",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 70,
                        "solved": True,
                        "resolution_summary": "已补验证证据",
                        "duration_ms": 6200,
                    },
                ],
            },
            {
                "run_id": "exec-low-candidate-2",
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
                        "quality_score": 69,
                        "solved": True,
                        "resolution_summary": "context prepared",
                        "duration_ms": 5900,
                        "input_tokens": 480,
                        "output_tokens": 110,
                    },
                    {
                        "task_id": "todo-8",
                        "task_type": "governance_evolution_optimize",
                        "assignee": "optimization-agent",
                        "status": "executed",
                        "task_status_after": "passed",
                        "report_status": "passed",
                        "reason": "solved",
                        "quality_score": 71,
                        "solved": True,
                        "resolution_summary": "结构化输出稳定",
                        "duration_ms": 6100,
                    },
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "executor-runs"
            output_dir = tmp / "upgrade-feedback"
            state_file = tmp / "state.json"
            db_path = tmp / "task_center.db"
            run_dir.mkdir(parents=True, exist_ok=True)
            for idx, payload in enumerate(report_payloads, start=1):
                write_json(run_dir / f"run-{idx}.json", payload)

            result = module.build_upgrade_feedback_bundle(
                executor_run_dir=run_dir,
                output_dir=output_dir,
                state_file=state_file,
                workflow_target="task_executor_10m",
                skill_name="openclaw-evolution-upgrader",
                skill_assignee="optimization-agent",
                baseline_count=2,
                candidate_count=2,
                task_db=db_path,
                auto_create_tasks=True,
                task_score_threshold=95.0,
                task_schedule_gap_minutes=45,
            )

            task_center = task_center_module.TaskCenter(db_path)
            try:
                rows = task_center.conn.execute(
                    """
                    SELECT task_id, source, task_type, assignee, status, change_id, requirement
                    FROM tasks
                    WHERE source = 'upgrade-feedback-runner'
                    ORDER BY task_id
                    """
                ).fetchall()
            finally:
                task_center.close()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["created_tasks"]), 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[1]["status"], "pending")
        self.assertTrue(str(rows[0]["change_id"]).startswith("upgrade-feedback:"))
        self.assertIn("[fingerprint:", str(rows[0]["requirement"]))
        self.assertEqual({str(row["task_type"]) for row in rows}, {"workflow_upgrade", "skill_upgrade"})

    def test_cron_setup_builds_upgrade_feedback_job_with_maintenance_defaults(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_upgrade_feedback_job(
            script_py="/tmp/upgrade_feedback_runner.py",
            executor_run_dir="/tmp/executor-runs",
            output_dir="/tmp/upgrade-feedback/reports",
            state_file="/tmp/upgrade-feedback/state.json",
            workflow_profile_registry="/tmp/policy/workflow-profile-registry.json",
            benchmark_suite_file="/tmp/policy/benchmark-suite-registry.json",
            benchmark_suite_id="coding-default-core",
            task_db="/tmp/task-center.db",
            every_ms=86400000,
            log_mode="silent",
            workflow_target="task_executor_10m",
            skill_name="openclaw-evolution-upgrader",
            skill_assignee="optimization-agent",
            baseline_count=2,
            candidate_count=2,
            auto_create_tasks=True,
            auto_apply_workflow_promotion=True,
            promotion_operator="cron-upgrade-feedback",
            task_score_threshold=82.0,
            task_schedule_gap_minutes=45,
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_upgrade_feedback_daily")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertNotIn("failureAlert", job)
        self.assertIn("upgrade_feedback_runner.py", message)
        self.assertIn("--workflow-target task_executor_10m", message)
        self.assertIn("--skill-name openclaw-evolution-upgrader", message)
        self.assertIn("--skill-assignee optimization-agent", message)
        self.assertIn("--baseline-count 2", message)
        self.assertIn("--candidate-count 2", message)
        self.assertIn("--task-db /tmp/task-center.db", message)
        self.assertIn("--workflow-profile-registry /tmp/policy/workflow-profile-registry.json", message)
        self.assertIn("--benchmark-suite-file /tmp/policy/benchmark-suite-registry.json", message)
        self.assertIn("--benchmark-suite-id coding-default-core", message)
        self.assertIn("--auto-create-tasks", message)
        self.assertIn("--auto-apply-workflow-promotion", message)
        self.assertIn("--promotion-operator cron-upgrade-feedback", message)
        self.assertIn("--task-score-threshold 82.0", message)
        self.assertIn("--task-schedule-gap-minutes 45", message)

    def test_cron_setup_builds_benchmark_sweep_job_with_defaults(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_benchmark_sweep_job(
            script_py="/tmp/benchmark_orchestrator.py",
            executor_run_dir="/tmp/executor-runs",
            output_root="/tmp/benchmark-sweeps",
            state_root="/tmp/benchmark-state",
            benchmark_suite_file="/tmp/policy/benchmark-suite-registry.json",
            workflow_profile_registry="/tmp/policy/workflow-profile-registry.json",
            task_db="/tmp/task-center.db",
            output_consumer_py="/tmp/benchmark_output_consumer.py",
            summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
            consumer_output_file="/tmp/benchmark-sweeps/output/latest-event.json",
            consumer_notify_on="error",
            every_ms=86400000,
            log_mode="silent",
            auto_create_tasks=False,
            auto_apply_workflow_promotion=False,
            promotion_operator="cron-benchmark-sweep",
            task_score_threshold=75.0,
            task_schedule_gap_minutes=90,
            suite_ids=["coding-default-core", "research-default-core"],
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_benchmark_sweep_daily")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertNotIn("failureAlert", job)
        self.assertIn("benchmark_orchestrator.py", message)
        self.assertIn("run-all", message)
        self.assertIn("--executor-run-dir", message)
        self.assertIn("/tmp/executor-runs", message)
        self.assertIn("--output-root", message)
        self.assertIn("/tmp/benchmark-sweeps", message)
        self.assertIn("--state-root", message)
        self.assertIn("/tmp/benchmark-state", message)
        self.assertIn("--benchmark-suite-file /tmp/policy/benchmark-suite-registry.json", message)
        self.assertIn("--workflow-profile-registry /tmp/policy/workflow-profile-registry.json", message)
        self.assertIn("--task-db /tmp/task-center.db", message)
        self.assertIn("--no-auto-create-tasks", message)
        self.assertIn("--no-auto-apply-workflow-promotion", message)
        self.assertIn("--promotion-operator cron-benchmark-sweep", message)
        self.assertIn("--task-score-threshold 75.0", message)
        self.assertIn("--task-schedule-gap-minutes 90", message)
        self.assertIn("--suite-id coding-default-core", message)
        self.assertIn("--suite-id research-default-core", message)
        self.assertIn("benchmark_output_consumer.py", message)
        self.assertIn("--summary-file /tmp/benchmark-sweeps/sweeps/latest-summary.json", message)
        self.assertIn("--notify-on error", message)
        self.assertIn("--output /tmp/benchmark-sweeps/output/latest-event.json", message)

    def test_cron_setup_builds_benchmark_output_job_with_announce_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_benchmark_output_job(
            script_py="/tmp/benchmark_output_consumer.py",
            summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
            output_file="/tmp/benchmark-sweeps/output/latest-event.json",
            notify_on="error",
            every_ms=86400000,
            delay_ms=300000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_benchmark_output_daily")
        self.assertEqual(job["delivery"]["mode"], "announce")
        self.assertNotIn("failureAlert", job)
        self.assertIn("benchmark_output_consumer.py", message)
        self.assertIn("--summary-file /tmp/benchmark-sweeps/sweeps/latest-summary.json", message)
        self.assertIn("--output /tmp/benchmark-sweeps/output/latest-event.json", message)
        self.assertIn("--notify-on error", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 300000)

    def test_cron_setup_builds_task_output_broadcast_job_with_announce_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_task_output_broadcast_job(
            script_py="/tmp/task_output_broadcast_runner.py",
            db_file="/tmp/task-center.db",
            state_file="/tmp/task-output/state.json",
            output_file="/tmp/task-output/latest-event.json",
            lookback_hours=24,
            limit=12,
            event_limit=200,
            notify_on="error",
            every_ms=900000,
            delay_ms=120000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_task_output_broadcast_15m")
        self.assertEqual(job["delivery"]["mode"], "announce")
        self.assertNotIn("failureAlert", job)
        self.assertIn("task_output_broadcast_runner.py", message)
        self.assertIn("--db /tmp/task-center.db", message)
        self.assertIn("--state-file /tmp/task-output/state.json", message)
        self.assertIn("--output /tmp/task-output/latest-event.json", message)
        self.assertIn("--lookback-hours 24", message)
        self.assertIn("--limit 12", message)
        self.assertIn("--event-limit 200", message)
        self.assertIn("--notify-on error", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 120000)

    def test_cron_setup_builds_control_plane_summary_job_with_announce_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_summary_job(
            script_py="/tmp/control_plane_summary_runner.py",
            db_file="/tmp/task-center.db",
            state_file="/tmp/control-plane-summary/state.json",
            output_file="/tmp/control-plane-summary/latest-event.json",
            lookback_hours=24,
            limit=20,
            notify_on="activity",
            every_ms=21600000,
            delay_ms=180000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_summary_6h")
        self.assertEqual(job["delivery"]["mode"], "announce")
        self.assertIn("control_plane_summary_runner.py", message)
        self.assertIn("--db /tmp/task-center.db", message)
        self.assertIn("--state-file /tmp/control-plane-summary/state.json", message)
        self.assertIn("--output /tmp/control-plane-summary/latest-event.json", message)
        self.assertIn("--lookback-hours 24", message)
        self.assertIn("--limit 20", message)
        self.assertIn("--notify-on activity", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 180000)

    def test_cron_setup_builds_control_plane_dashboard_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_dashboard_job(
            script_py="/tmp/control_plane_dashboard.py",
            db_file="/tmp/task-center.db",
            benchmark_summary_file="/tmp/benchmark-sweeps/sweeps/latest-summary.json",
            json_output="/tmp/control-plane-dashboard/latest-dashboard.json",
            markdown_output="/tmp/control-plane-dashboard/latest-dashboard.md",
            html_output="/tmp/control-plane-dashboard/latest-dashboard.html",
            lookback_hours=24,
            limit=20,
            every_ms=21600000,
            delay_ms=240000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_dashboard_6h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_dashboard.py", message)
        self.assertIn("--db /tmp/task-center.db", message)
        self.assertIn("--benchmark-summary-file /tmp/benchmark-sweeps/sweeps/latest-summary.json", message)
        self.assertIn("--json-output /tmp/control-plane-dashboard/latest-dashboard.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-dashboard/latest-dashboard.md", message)
        self.assertIn("--html-output /tmp/control-plane-dashboard/latest-dashboard.html", message)
        self.assertIn("--lookback-hours 24", message)
        self.assertIn("--limit 20", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 240000)

    def test_cron_setup_builds_control_plane_optimization_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_optimization_job(
            script_py="/tmp/control_plane_optimization_advisor.py",
            db_file="/tmp/task-center.db",
            json_output="/tmp/control-plane-optimization/latest-report.json",
            markdown_output="/tmp/control-plane-optimization/latest-report.md",
            lookback_hours=24,
            limit=20,
            every_ms=43200000,
            delay_ms=360000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_optimization_12h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_optimization_advisor.py", message)
        self.assertIn("--db /tmp/task-center.db", message)
        self.assertIn("--json-output /tmp/control-plane-optimization/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-optimization/latest-report.md", message)
        self.assertIn("--lookback-hours 24", message)
        self.assertIn("--limit 20", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 360000)

    def test_cron_setup_builds_control_plane_optimization_dispatch_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_optimization_dispatch_job(
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
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_optimization_dispatch_12h")
        self.assertEqual(job["delivery"]["mode"], "none")

    def test_cron_setup_builds_control_plane_optimization_review_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_optimization_review_job(
            script_py="/tmp/control_plane_optimization_review_runner.py",
            task_db="/tmp/task-center/task_center.db",
            json_output="/tmp/control-plane-optimization-review/latest-report.json",
            markdown_output="/tmp/control-plane-optimization-review/latest-report.md",
            lookback_hours=72,
            limit=20,
            every_ms=43200000,
            delay_ms=540000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_optimization_review_12h")
        self.assertIn("control_plane_optimization_review_runner.py", message)
        self.assertIn("--lookback-hours 72", message)
        self.assertIn("--limit 20", message)
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("--task-db /tmp/task-center/task_center.db", message)
        self.assertIn("--json-output /tmp/control-plane-optimization-review/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-optimization-review/latest-report.md", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 540000)

    def test_cron_setup_builds_control_plane_profile_update_dispatch_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_profile_update_dispatch_job(
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
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_profile_update_dispatch_12h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_profile_update_dispatcher.py", message)
        self.assertIn("--review-file /tmp/control-plane-optimization-review/latest-report.json", message)
        self.assertIn("--task-db /tmp/task-center/task_center.db", message)
        self.assertIn("--json-output /tmp/control-plane-profile-update-dispatch/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-profile-update-dispatch/latest-report.md", message)
        self.assertIn("--execution-workflow-profile coding-default", message)
        self.assertIn("--execution-workflow-channel stable", message)
        self.assertIn("--schedule-gap-minutes 60", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 600000)

    def test_cron_setup_builds_control_plane_profile_update_apply_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_profile_update_apply_job(
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
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_profile_update_apply_12h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_profile_update_applier.py", message)
        self.assertIn("--task-db /tmp/task-center/task_center.db", message)
        self.assertIn("--registry-file /tmp/policy/workflow-profile-registry.json", message)
        self.assertIn("--json-output /tmp/control-plane-profile-update-apply/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-profile-update-apply/latest-report.md", message)
        self.assertIn("--target-channel candidate", message)
        self.assertIn("--lookback-hours 72", message)
        self.assertIn("--limit 20", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 660000)

    def test_cron_setup_builds_control_plane_profile_update_validation_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_profile_update_validation_job(
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
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_profile_update_validation_12h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_profile_update_validation_runner.py", message)
        self.assertIn("--apply-file /tmp/control-plane-profile-update-apply/latest-report.json", message)
        self.assertIn("--benchmark-suite-file /tmp/policy/benchmark-suite-registry.json", message)
        self.assertIn("--executor-run-dir /tmp/task-center/executor-runs", message)
        self.assertIn("--output-root /tmp/control-plane-profile-update-validation", message)
        self.assertIn("--state-file /tmp/control-plane-profile-update-validation/state.json", message)
        self.assertIn("--task-db /tmp/task-center/task_center.db", message)
        self.assertIn("--workflow-profile-registry /tmp/policy/workflow-profile-registry.json", message)
        self.assertIn("--json-output /tmp/control-plane-profile-update-validation/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-profile-update-validation/latest-report.md", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 720000)

    def test_cron_setup_builds_control_plane_acceptance_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_acceptance_job(
            script_py="/tmp/control_plane_acceptance_runner.py",
            jobs_file="/tmp/cron/jobs.json",
            json_output="/tmp/control-plane-acceptance/latest-report.json",
            markdown_output="/tmp/control-plane-acceptance/latest-report.md",
            every_ms=43200000,
            delay_ms=420000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_acceptance_12h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_acceptance_runner.py", message)
        self.assertIn("--jobs-file /tmp/cron/jobs.json", message)
        self.assertIn("--json-output /tmp/control-plane-acceptance/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-acceptance/latest-report.md", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 420000)

    def test_cron_setup_builds_control_plane_live_acceptance_job_with_storage_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        job = module.build_control_plane_live_acceptance_job(
            script_py="/tmp/control_plane_live_acceptance_runner.py",
            workspace_root="/tmp/control-plane-live-acceptance",
            jobs_file="/tmp/cron/jobs.json",
            json_output="/tmp/control-plane-live-acceptance/latest-report.json",
            markdown_output="/tmp/control-plane-live-acceptance/latest-report.md",
            lookback_hours=24,
            limit=20,
            every_ms=86400000,
            delay_ms=540000,
            log_mode="silent",
        )

        message = job["payload"]["message"]
        self.assertEqual(job["name"], "ops_control_plane_live_acceptance_24h")
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertIn("control_plane_live_acceptance_runner.py", message)
        self.assertIn("--workspace-root /tmp/control-plane-live-acceptance", message)
        self.assertIn("--jobs-file /tmp/cron/jobs.json", message)
        self.assertIn("--json-output /tmp/control-plane-live-acceptance/latest-report.json", message)
        self.assertIn("--markdown-output /tmp/control-plane-live-acceptance/latest-report.md", message)
        self.assertIn("--lookback-hours 24", message)
        self.assertIn("--limit 20", message)
        self.assertGreaterEqual(job["schedule"]["anchorMs"] - job["createdAtMs"], 540000)

    def test_install_workflow_profile_cron_setup_cmd_installs_upgrade_feedback_job(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )

        cmd = module.build_cron_setup_cmd(
            python_bin="python3",
            script_path="/repo/scripts/openclaw-ops/cron_setup.py",
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            openclaw_home="/home/ubuntu/.openclaw",
            workflow_repo_path="/repo",
            workflow_repo_id="workflow-repo",
            project_registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            incremental_every_ms=900000,
            full_expr="10 3 * * *",
            daily_summary_expr="40 3 * * *",
            daily_work_expr="0 9 * * *",
            self_evolution_expr="30 3 * * 1",
            self_evolution_low_score_guarantee_enabled=True,
            self_evolution_low_score_guarantee_min_agents=2,
            self_evolution_low_score_guarantee_max_agents=6,
            self_evolution_low_score_guarantee_threshold=70.0,
            conversation_every_ms=21600000,
            governance_every_ms=21600000,
            governance_auto_pr=True,
            governance_reviewer_gh_user="reviewer-bot",
            governance_push_before_pr=True,
            git_sync_every_ms=21600000,
            auto_update_install_every_ms=3600000,
            github_web_every_ms=43200000,
            include_github_web=True,
            channel="telegram",
            target="-1003333097130",
        )

        rendered = " ".join(cmd).replace("\\", "/")
        self.assertIn("--install-upgrade-feedback-job", rendered)
        self.assertIn("--upgrade-feedback-py /home/ubuntu/.openclaw/ops/upgrade_feedback_runner.py", rendered)
        self.assertIn("--upgrade-feedback-executor-run-dir /home/ubuntu/.openclaw/ops/task-center/executor-runs", rendered)
        self.assertIn("--upgrade-feedback-output-dir /home/ubuntu/.openclaw/ops/upgrade-feedback/reports", rendered)
        self.assertIn("--upgrade-feedback-state /home/ubuntu/.openclaw/ops/upgrade-feedback/state.json", rendered)
        self.assertIn("--upgrade-feedback-workflow-profile-registry /home/ubuntu/.openclaw/ops/policy/workflow-profile-registry.json", rendered)
        self.assertIn("--upgrade-feedback-benchmark-suite-file /home/ubuntu/.openclaw/ops/policy/benchmark-suite-registry.json", rendered)
        self.assertIn("--upgrade-feedback-benchmark-suite-id coding-default-core", rendered)
        self.assertIn("--upgrade-feedback-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--upgrade-feedback-skill-name openclaw-evolution-upgrader", rendered)
        self.assertIn("--upgrade-feedback-skill-assignee optimization-agent", rendered)
        self.assertIn("--upgrade-feedback-every-ms 86400000", rendered)
        self.assertIn("--upgrade-feedback-auto-create-tasks", rendered)
        self.assertIn("--upgrade-feedback-auto-apply-workflow-promotion", rendered)
        self.assertIn("--upgrade-feedback-promotion-operator cron-upgrade-feedback", rendered)
        self.assertIn("--upgrade-feedback-task-score-threshold 80.0", rendered)
        self.assertIn("--upgrade-feedback-task-schedule-gap-minutes 120", rendered)
        self.assertIn("--install-benchmark-sweep-job", rendered)
        self.assertIn("--benchmark-sweep-py /home/ubuntu/.openclaw/ops/benchmark_orchestrator.py", rendered)
        self.assertIn("--benchmark-sweep-executor-run-dir /home/ubuntu/.openclaw/ops/task-center/executor-runs", rendered)
        self.assertIn("--benchmark-sweep-output-root /home/ubuntu/.openclaw/ops/benchmark-sweeps", rendered)
        self.assertIn("--benchmark-sweep-state-root /home/ubuntu/.openclaw/ops/benchmark-sweeps/state", rendered)
        self.assertIn("--benchmark-sweep-benchmark-suite-file /home/ubuntu/.openclaw/ops/policy/benchmark-suite-registry.json", rendered)
        self.assertIn("--benchmark-sweep-workflow-profile-registry /home/ubuntu/.openclaw/ops/policy/workflow-profile-registry.json", rendered)
        self.assertIn("--benchmark-sweep-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--benchmark-sweep-every-ms 86400000", rendered)
        self.assertIn("--no-benchmark-sweep-auto-create-tasks", rendered)
        self.assertIn("--no-benchmark-sweep-auto-apply-workflow-promotion", rendered)
        self.assertIn("--benchmark-sweep-promotion-operator cron-benchmark-sweep", rendered)
        self.assertIn("--benchmark-sweep-suite-id coding-default-core", rendered)
        self.assertIn("--benchmark-sweep-suite-id research-default-core", rendered)
        self.assertIn("--benchmark-sweep-suite-id docs-default-core", rendered)
        self.assertIn("--benchmark-sweep-suite-id ops-default-core", rendered)
        self.assertIn("--benchmark-sweep-output-py /home/ubuntu/.openclaw/ops/benchmark_output_consumer.py", rendered)
        self.assertIn("--benchmark-sweep-summary-file /home/ubuntu/.openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json", rendered)
        self.assertIn("--benchmark-sweep-consumer-output-file /home/ubuntu/.openclaw/ops/benchmark-sweeps/output/latest-event.json", rendered)
        self.assertIn("--benchmark-sweep-consumer-notify-on error", rendered)
        self.assertIn("--install-benchmark-output-job", rendered)
        self.assertIn("--benchmark-output-py /home/ubuntu/.openclaw/ops/benchmark_output_consumer.py", rendered)
        self.assertIn("--benchmark-output-summary-file /home/ubuntu/.openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json", rendered)
        self.assertIn("--benchmark-output-output-file /home/ubuntu/.openclaw/ops/benchmark-sweeps/output/latest-event.json", rendered)
        self.assertIn("--benchmark-output-notify-on error", rendered)
        self.assertIn("--benchmark-output-every-ms 86400000", rendered)
        self.assertIn("--benchmark-output-delay-ms 300000", rendered)
        self.assertIn("--install-task-output-broadcast-job", rendered)
        self.assertIn("--task-output-broadcast-py /home/ubuntu/.openclaw/ops/task_output_broadcast_runner.py", rendered)
        self.assertIn("--task-output-broadcast-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--task-output-broadcast-state /home/ubuntu/.openclaw/ops/task-output/state.json", rendered)
        self.assertIn("--task-output-broadcast-output /home/ubuntu/.openclaw/ops/task-output/latest-event.json", rendered)
        self.assertIn("--task-output-broadcast-lookback-hours 24", rendered)
        self.assertIn("--task-output-broadcast-limit 12", rendered)
        self.assertIn("--task-output-broadcast-event-limit 200", rendered)
        self.assertIn("--task-output-broadcast-notify-on error", rendered)
        self.assertIn("--task-output-broadcast-every-ms 900000", rendered)
        self.assertIn("--task-output-broadcast-delay-ms 120000", rendered)
        self.assertIn("--install-control-plane-summary-job", rendered)
        self.assertIn("--control-plane-summary-py /home/ubuntu/.openclaw/ops/control_plane_summary_runner.py", rendered)
        self.assertIn("--control-plane-summary-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-summary-state /home/ubuntu/.openclaw/ops/control-plane-summary/state.json", rendered)
        self.assertIn("--control-plane-summary-output /home/ubuntu/.openclaw/ops/control-plane-summary/latest-event.json", rendered)
        self.assertIn("--control-plane-summary-lookback-hours 24", rendered)
        self.assertIn("--control-plane-summary-limit 20", rendered)
        self.assertIn("--control-plane-summary-notify-on activity", rendered)
        self.assertIn("--control-plane-summary-every-ms 21600000", rendered)
        self.assertIn("--control-plane-summary-delay-ms 180000", rendered)
        self.assertIn("--install-control-plane-dashboard-job", rendered)
        self.assertIn("--control-plane-dashboard-py /home/ubuntu/.openclaw/ops/control_plane_dashboard.py", rendered)
        self.assertIn("--control-plane-dashboard-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-dashboard-benchmark-summary-file /home/ubuntu/.openclaw/ops/benchmark-sweeps/sweeps/latest-summary.json", rendered)
        self.assertIn("--control-plane-dashboard-json-output /home/ubuntu/.openclaw/ops/control-plane-dashboard/latest-dashboard.json", rendered)
        self.assertIn("--control-plane-dashboard-markdown-output /home/ubuntu/.openclaw/ops/control-plane-dashboard/latest-dashboard.md", rendered)
        self.assertIn("--control-plane-dashboard-html-output /home/ubuntu/.openclaw/ops/control-plane-dashboard/latest-dashboard.html", rendered)
        self.assertIn("--control-plane-dashboard-lookback-hours 24", rendered)
        self.assertIn("--control-plane-dashboard-limit 20", rendered)
        self.assertIn("--control-plane-dashboard-every-ms 21600000", rendered)
        self.assertIn("--control-plane-dashboard-delay-ms 240000", rendered)
        self.assertIn("--install-control-plane-optimization-job", rendered)
        self.assertIn("--control-plane-optimization-py /home/ubuntu/.openclaw/ops/control_plane_optimization_advisor.py", rendered)
        self.assertIn("--control-plane-optimization-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-optimization-json-output /home/ubuntu/.openclaw/ops/control-plane-optimization/latest-report.json", rendered)
        self.assertIn("--control-plane-optimization-markdown-output /home/ubuntu/.openclaw/ops/control-plane-optimization/latest-report.md", rendered)
        self.assertIn("--control-plane-optimization-lookback-hours 24", rendered)
        self.assertIn("--control-plane-optimization-limit 20", rendered)
        self.assertIn("--control-plane-optimization-every-ms 43200000", rendered)
        self.assertIn("--control-plane-optimization-delay-ms 360000", rendered)
        self.assertIn("--install-control-plane-optimization-dispatch-job", rendered)
        self.assertIn("--control-plane-optimization-dispatch-py /home/ubuntu/.openclaw/ops/control_plane_optimization_dispatcher.py", rendered)
        self.assertIn("--control-plane-optimization-dispatch-report-file /home/ubuntu/.openclaw/ops/control-plane-optimization/latest-report.json", rendered)
        self.assertIn("--control-plane-optimization-dispatch-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-optimization-dispatch-json-output /home/ubuntu/.openclaw/ops/control-plane-optimization-dispatch/latest-report.json", rendered)
        self.assertIn("--control-plane-optimization-dispatch-markdown-output /home/ubuntu/.openclaw/ops/control-plane-optimization-dispatch/latest-report.md", rendered)
        self.assertIn("--control-plane-optimization-dispatch-execution-workflow-profile coding-default", rendered)
        self.assertIn("--control-plane-optimization-dispatch-execution-workflow-channel stable", rendered)
        self.assertIn("--control-plane-optimization-dispatch-schedule-gap-minutes 30", rendered)
        self.assertIn("--control-plane-optimization-dispatch-every-ms 43200000", rendered)
        self.assertIn("--control-plane-optimization-dispatch-delay-ms 480000", rendered)
        self.assertIn("--install-control-plane-optimization-review-job", rendered)
        self.assertIn("--control-plane-optimization-review-py /home/ubuntu/.openclaw/ops/control_plane_optimization_review_runner.py", rendered)
        self.assertIn("--control-plane-optimization-review-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-optimization-review-json-output /home/ubuntu/.openclaw/ops/control-plane-optimization-review/latest-report.json", rendered)
        self.assertIn("--control-plane-optimization-review-markdown-output /home/ubuntu/.openclaw/ops/control-plane-optimization-review/latest-report.md", rendered)
        self.assertIn("--control-plane-optimization-review-lookback-hours 72", rendered)
        self.assertIn("--control-plane-optimization-review-limit 20", rendered)
        self.assertIn("--control-plane-optimization-review-every-ms 43200000", rendered)
        self.assertIn("--control-plane-optimization-review-delay-ms 540000", rendered)
        self.assertIn("--install-control-plane-profile-update-dispatch-job", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-py /home/ubuntu/.openclaw/ops/control_plane_profile_update_dispatcher.py", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-review-file /home/ubuntu/.openclaw/ops/control-plane-optimization-review/latest-report.json", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-json-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-dispatch/latest-report.json", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-markdown-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-dispatch/latest-report.md", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-execution-workflow-profile coding-default", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-execution-workflow-channel stable", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-schedule-gap-minutes 60", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-every-ms 43200000", rendered)
        self.assertIn("--control-plane-profile-update-dispatch-delay-ms 600000", rendered)
        self.assertIn("--install-control-plane-profile-update-apply-job", rendered)
        self.assertIn("--control-plane-profile-update-apply-py /home/ubuntu/.openclaw/ops/control_plane_profile_update_applier.py", rendered)
        self.assertIn("--control-plane-profile-update-apply-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-profile-update-apply-registry-file /home/ubuntu/.openclaw/ops/policy/workflow-profile-registry.json", rendered)
        self.assertIn("--control-plane-profile-update-apply-json-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-apply/latest-report.json", rendered)
        self.assertIn("--control-plane-profile-update-apply-markdown-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-apply/latest-report.md", rendered)
        self.assertIn("--control-plane-profile-update-apply-target-channel candidate", rendered)
        self.assertIn("--control-plane-profile-update-apply-lookback-hours 72", rendered)
        self.assertIn("--control-plane-profile-update-apply-limit 20", rendered)
        self.assertIn("--control-plane-profile-update-apply-every-ms 43200000", rendered)
        self.assertIn("--control-plane-profile-update-apply-delay-ms 660000", rendered)
        self.assertIn("--install-control-plane-profile-update-validation-job", rendered)
        self.assertIn("--control-plane-profile-update-validation-py /home/ubuntu/.openclaw/ops/control_plane_profile_update_validation_runner.py", rendered)
        self.assertIn("--control-plane-profile-update-validation-apply-file /home/ubuntu/.openclaw/ops/control-plane-profile-update-apply/latest-report.json", rendered)
        self.assertIn("--control-plane-profile-update-validation-benchmark-suite-file /home/ubuntu/.openclaw/ops/policy/benchmark-suite-registry.json", rendered)
        self.assertIn("--control-plane-profile-update-validation-executor-run-dir /home/ubuntu/.openclaw/ops/task-center/executor-runs", rendered)
        self.assertIn("--control-plane-profile-update-validation-output-root /home/ubuntu/.openclaw/ops/control-plane-profile-update-validation", rendered)
        self.assertIn("--control-plane-profile-update-validation-state-file /home/ubuntu/.openclaw/ops/control-plane-profile-update-validation/state.json", rendered)
        self.assertIn("--control-plane-profile-update-validation-task-db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--control-plane-profile-update-validation-workflow-profile-registry /home/ubuntu/.openclaw/ops/policy/workflow-profile-registry.json", rendered)
        self.assertIn("--control-plane-profile-update-validation-json-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-validation/latest-report.json", rendered)
        self.assertIn("--control-plane-profile-update-validation-markdown-output /home/ubuntu/.openclaw/ops/control-plane-profile-update-validation/latest-report.md", rendered)
        self.assertIn("--control-plane-profile-update-validation-every-ms 43200000", rendered)
        self.assertIn("--control-plane-profile-update-validation-delay-ms 720000", rendered)
        self.assertIn("--install-control-plane-acceptance-job", rendered)
        self.assertIn("--control-plane-acceptance-py /home/ubuntu/.openclaw/ops/control_plane_acceptance_runner.py", rendered)
        self.assertIn("--control-plane-acceptance-jobs-file /home/ubuntu/.openclaw/cron/jobs.json", rendered)
        self.assertIn("--control-plane-acceptance-json-output /home/ubuntu/.openclaw/ops/control-plane-acceptance/latest-report.json", rendered)
        self.assertIn("--control-plane-acceptance-markdown-output /home/ubuntu/.openclaw/ops/control-plane-acceptance/latest-report.md", rendered)
        self.assertIn("--control-plane-acceptance-every-ms 43200000", rendered)
        self.assertIn("--control-plane-acceptance-delay-ms 420000", rendered)
        self.assertIn("--install-control-plane-live-acceptance-job", rendered)
        self.assertIn("--control-plane-live-acceptance-py /home/ubuntu/.openclaw/ops/control_plane_live_acceptance_runner.py", rendered)
        self.assertIn("--control-plane-live-acceptance-workspace-root /home/ubuntu/.openclaw/ops/control-plane-live-acceptance", rendered)
        self.assertIn("--control-plane-live-acceptance-jobs-file /home/ubuntu/.openclaw/cron/jobs.json", rendered)
        self.assertIn("--control-plane-live-acceptance-json-output /home/ubuntu/.openclaw/ops/control-plane-live-acceptance/latest-report.json", rendered)
        self.assertIn("--control-plane-live-acceptance-markdown-output /home/ubuntu/.openclaw/ops/control-plane-live-acceptance/latest-report.md", rendered)
        self.assertIn("--control-plane-live-acceptance-lookback-hours 24", rendered)
        self.assertIn("--control-plane-live-acceptance-limit 20", rendered)
        self.assertIn("--control-plane-live-acceptance-every-ms 86400000", rendered)
        self.assertIn("--control-plane-live-acceptance-delay-ms 540000", rendered)


if __name__ == "__main__":
    unittest.main()

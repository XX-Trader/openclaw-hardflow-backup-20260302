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


def build_executor_reports() -> list[dict]:
    return [
        {
            "run_id": "exec-baseline-1",
            "started_at": "2026-03-21T10:00:00+00:00",
            "finished_at": "2026-03-21T10:05:00+00:00",
            "tasks_selected": 2,
            "tasks_executed": 2,
            "tasks_skipped": 0,
            "tasks_failed": 1,
            "preflight_warning_tasks": 1,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-baseline-context",
                    "task_type": "governance_evolution_context_preflight",
                    "assignee": "project-agent",
                    "status": "executed",
                    "task_status_after": "partial",
                    "report_status": "partial",
                    "reason": "partial",
                    "quality_score": 58,
                    "solved": False,
                    "resolution_summary": "需求上下文不完整",
                    "duration_ms": 7800,
                },
                {
                    "task_id": "todo-baseline-opt",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "failed",
                    "report_status": "failed",
                    "reason": "failed",
                    "quality_score": 52,
                    "solved": False,
                    "resolution_summary": "缺少验证证据",
                    "duration_ms": 8200,
                },
            ],
        },
        {
            "run_id": "exec-candidate-1",
            "started_at": "2026-03-22T10:00:00+00:00",
            "finished_at": "2026-03-22T10:04:00+00:00",
            "tasks_selected": 2,
            "tasks_executed": 2,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "preflight_warning_tasks": 0,
            "preflight_blocked_tasks": 0,
            "results": [
                {
                    "task_id": "todo-candidate-context",
                    "task_type": "governance_evolution_context_preflight",
                    "assignee": "project-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 88,
                    "solved": True,
                    "resolution_summary": "上下文已补全",
                    "duration_ms": 6100,
                },
                {
                    "task_id": "todo-candidate-opt",
                    "task_type": "governance_evolution_optimize",
                    "assignee": "optimization-agent",
                    "status": "executed",
                    "task_status_after": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "quality_score": 91,
                    "solved": True,
                    "resolution_summary": "交付物与验证证据完整",
                    "duration_ms": 5900,
                    "input_tokens": 1200,
                    "output_tokens": 360,
                },
            ],
        },
    ]


def build_registry_payload() -> dict:
    return {
        "schema_version": "2026-03-22",
        "default_suite_id": "coding-default-core",
        "suites": [
            {
                "suite_id": "coding-default-core",
                "display_name": "默认编码工作流核心基准集",
                "workflow_profile_id": "coding-default",
                "baseline_channel": "stable",
                "candidate_channel": "candidate",
                "workflow_target": "task_executor_10m",
                "skill_name": "openclaw-evolution-upgrader",
                "skill_assignee": "optimization-agent",
                "baseline_count": 1,
                "candidate_count": 1,
                "target_kind": "workflow",
                "target_id": "coding-default",
            },
            {
                "suite_id": "research-default-core",
                "display_name": "默认研究工作流核心基准集",
                "workflow_profile_id": "research-default",
                "baseline_channel": "stable",
                "candidate_channel": "candidate",
                "workflow_target": "task_executor_10m",
                "skill_name": "openclaw-evolution-upgrader",
                "skill_assignee": "optimization-agent",
                "baseline_count": 1,
                "candidate_count": 1,
                "target_kind": "workflow",
                "target_id": "research-default",
            },
        ],
    }


class BenchmarkOrchestratorTests(unittest.TestCase):
    def test_list_benchmark_suites_marks_default_suite(self):
        module = load_module(
            "benchmark_orchestrator",
            "scripts/openclaw-ops/benchmark_orchestrator.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "benchmark-suite-registry.json"
            write_json(registry_file, build_registry_payload())

            listing = module.list_benchmark_suites(registry_file=registry_file)

        self.assertEqual(listing["default_suite_id"], "coding-default-core")
        self.assertEqual([item["suite_id"] for item in listing["suites"]], ["coding-default-core", "research-default-core"])
        self.assertTrue(listing["suites"][0]["is_default"])
        self.assertFalse(listing["suites"][1]["is_default"])

    def test_run_benchmark_suite_writes_suite_summary(self):
        module = load_module(
            "benchmark_orchestrator",
            "scripts/openclaw-ops/benchmark_orchestrator.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            registry_file = tmp / "benchmark-suite-registry.json"
            run_dir = tmp / "executor-runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            for index, payload in enumerate(build_executor_reports(), start=1):
                write_json(run_dir / f"run-{index}.json", payload)
            write_json(registry_file, build_registry_payload())

            result = module.run_benchmark_suite(
                executor_run_dir=run_dir,
                output_root=tmp / "benchmark-output",
                state_root=tmp / "benchmark-state",
                registry_file=registry_file,
                suite_id="coding-default-core",
            )
            output_summary_exists = Path(result["output_dir"]).joinpath("latest-summary.json").exists()
            state_file_exists = Path(result["state_file"]).exists()

        self.assertEqual(result["suite_id"], "coding-default-core")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"]["benchmark_suite"]["suite_id"], "coding-default-core")
        self.assertTrue(output_summary_exists)
        self.assertTrue(state_file_exists)

    def test_run_benchmark_sweep_writes_latest_summary(self):
        module = load_module(
            "benchmark_orchestrator",
            "scripts/openclaw-ops/benchmark_orchestrator.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            registry_file = tmp / "benchmark-suite-registry.json"
            run_dir = tmp / "executor-runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            for index, payload in enumerate(build_executor_reports(), start=1):
                write_json(run_dir / f"run-{index}.json", payload)
            write_json(registry_file, build_registry_payload())

            result = module.run_benchmark_sweep(
                executor_run_dir=run_dir,
                output_root=tmp / "benchmark-output",
                state_root=tmp / "benchmark-state",
                registry_file=registry_file,
                suite_ids=["coding-default-core", "research-default-core"],
            )
            latest_summary_exists = Path(result["latest_summary_file"]).exists()
            latest_summary_payload = json.loads(Path(result["latest_summary_file"]).read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["requested_suite_ids"], ["coding-default-core", "research-default-core"])
        self.assertEqual([item["suite_id"] for item in result["results"]], ["coding-default-core", "research-default-core"])
        self.assertTrue(latest_summary_exists)
        self.assertEqual(latest_summary_payload["requested_suite_ids"], ["coding-default-core", "research-default-core"])


if __name__ == "__main__":
    unittest.main()

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


class ControlPlaneProfileUpdateValidationRunnerTests(unittest.TestCase):
    def _apply_payload(self) -> dict:
        return {
            "result": {
                "generated_at": "2026-03-23T01:00:00+00:00",
                "registry_file": "/tmp/workflow-profile-registry.json",
                "target_channel": "candidate",
                "applied_count": 3,
                "skipped_count": 0,
                "applied": [
                    {
                        "task_id": "todo-profile-update-docs-a",
                        "change_id": "control-plane-profile-update:docs-a",
                        "target_profile_id": "docs-default",
                        "target_stage_id": "draft",
                        "target_channel": "candidate",
                        "recommendation_type": "strengthen_stage_gate",
                    },
                    {
                        "task_id": "todo-profile-update-docs-b",
                        "change_id": "control-plane-profile-update:docs-b",
                        "target_profile_id": "docs-default",
                        "target_stage_id": "review",
                        "target_channel": "candidate",
                        "recommendation_type": "parallelize_stage_candidate",
                    },
                    {
                        "task_id": "todo-profile-update-unknown",
                        "change_id": "control-plane-profile-update:unknown",
                        "target_profile_id": "unknown-default",
                        "target_stage_id": "draft",
                        "target_channel": "candidate",
                        "recommendation_type": "stage_simplification_candidate",
                    },
                ],
                "skipped": [],
            }
        }

    def _benchmark_registry_payload(self) -> dict:
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
                    "baseline_count": 3,
                    "candidate_count": 3,
                    "target_kind": "workflow",
                    "target_id": "coding-default",
                },
                {
                    "suite_id": "docs-default-core",
                    "display_name": "默认文档工作流核心基准集",
                    "workflow_profile_id": "docs-default",
                    "baseline_channel": "stable",
                    "candidate_channel": "candidate",
                    "workflow_target": "task_executor_10m",
                    "skill_name": "openclaw-evolution-upgrader",
                    "skill_assignee": "optimization-agent",
                    "baseline_count": 3,
                    "candidate_count": 3,
                    "target_kind": "workflow",
                    "target_id": "docs-default",
                },
            ],
        }

    def test_validation_runner_executes_affected_suite_and_dedupes_change_ids(self):
        module = load_module(
            "control_plane_profile_update_validation_runner",
            "scripts/openclaw-ops/control_plane_profile_update_validation_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            apply_file = tmp / "apply.json"
            benchmark_suite_file = tmp / "benchmark-suite-registry.json"
            state_file = tmp / "validation-state.json"
            output_root = tmp / "validation-output"
            executor_run_dir = tmp / "executor-runs"
            executor_run_dir.mkdir(parents=True, exist_ok=True)

            write_json(apply_file, self._apply_payload())
            write_json(benchmark_suite_file, self._benchmark_registry_payload())
            write_json(
                state_file,
                {
                    "validated_change_ids": [
                        "control-plane-profile-update:docs-b",
                    ]
                },
            )

            called_suite_ids: list[str] = []

            def suite_runner(**kwargs):
                called_suite_ids.append(str(kwargs["suite_id"]))
                suite_output_dir = Path(kwargs["output_root"]).expanduser() / "suites" / str(kwargs["suite_id"])
                suite_output_dir.mkdir(parents=True, exist_ok=True)
                (suite_output_dir / "latest-summary.json").write_text(
                    json.dumps({"suite_id": kwargs["suite_id"]}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {
                    "status": "ok",
                    "suite_id": str(kwargs["suite_id"]),
                    "output_dir": str(suite_output_dir),
                    "state_file": str(Path(kwargs["state_root"]).expanduser() / f"{kwargs['suite_id']}.json"),
                    "summary": {
                        "workflow_scorecard": {
                            "decision": {
                                "promote_to_new_baseline": False,
                                "veto_reasons": [],
                            }
                        }
                    },
                }

            result = module.run_control_plane_profile_update_validation(
                apply_file=apply_file,
                benchmark_suite_file=benchmark_suite_file,
                executor_run_dir=executor_run_dir,
                output_root=output_root,
                state_file=state_file,
                workflow_profile_registry="",
                task_db="",
                auto_create_tasks=False,
                auto_apply_workflow_promotion=False,
                promotion_operator="control-plane-validation",
                suite_runner=suite_runner,
            )
            updated_state = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(called_suite_ids, ["docs-default-core"])
        self.assertEqual(result["executed_suite_count"], 1)
        self.assertEqual(result["validated_change_count"], 1)
        skipped = {item["change_id"]: item["reason"] for item in result["skipped"]}
        self.assertEqual(skipped["control-plane-profile-update:docs-b"], "already_validated_change_id")
        self.assertEqual(skipped["control-plane-profile-update:unknown"], "no_matching_benchmark_suite")
        self.assertIn("control-plane-profile-update:docs-a", updated_state["validated_change_ids"])
        self.assertIn("# OpenClaw Control Plane Profile Update Validation", result["markdown"])

    def test_main_writes_outputs(self):
        module = load_module(
            "control_plane_profile_update_validation_runner",
            "scripts/openclaw-ops/control_plane_profile_update_validation_runner.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            apply_file = tmp / "apply.json"
            benchmark_suite_file = tmp / "benchmark-suite-registry.json"
            state_file = tmp / "validation-state.json"
            output_root = tmp / "validation-output"
            json_output = tmp / "validation.json"
            markdown_output = tmp / "validation.md"
            executor_run_dir = tmp / "executor-runs"
            executor_run_dir.mkdir(parents=True, exist_ok=True)

            write_json(apply_file, self._apply_payload())
            write_json(benchmark_suite_file, self._benchmark_registry_payload())

            def suite_runner(**kwargs):
                suite_output_dir = Path(kwargs["output_root"]).expanduser() / "suites" / str(kwargs["suite_id"])
                suite_output_dir.mkdir(parents=True, exist_ok=True)
                return {
                    "status": "ok",
                    "suite_id": str(kwargs["suite_id"]),
                    "output_dir": str(suite_output_dir),
                    "state_file": str(Path(kwargs["state_root"]).expanduser() / f"{kwargs['suite_id']}.json"),
                    "summary": {},
                }

            with redirect_stdout(StringIO()):
                payload = module.main(
                    [
                        "--apply-file",
                        str(apply_file),
                        "--benchmark-suite-file",
                        str(benchmark_suite_file),
                        "--executor-run-dir",
                        str(executor_run_dir),
                        "--output-root",
                        str(output_root),
                        "--state-file",
                        str(state_file),
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                        "--emit-json",
                    ],
                    suite_runner=suite_runner,
                )

            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown_text = markdown_output.read_text(encoding="utf-8")

        self.assertIn("result", payload)
        self.assertEqual(json_payload["result"]["executed_suite_count"], 1)
        self.assertIn("# OpenClaw Control Plane Profile Update Validation", markdown_text)


if __name__ == "__main__":
    unittest.main()

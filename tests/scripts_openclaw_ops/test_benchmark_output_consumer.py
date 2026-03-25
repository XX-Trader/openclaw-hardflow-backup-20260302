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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BenchmarkOutputConsumerTests(unittest.TestCase):
    def test_build_benchmark_output_consumer_payload_returns_event_and_human_text(self):
        consumer_module = load_module(
            "benchmark_output_consumer",
            "scripts/openclaw-ops/benchmark_output_consumer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            summary_file = Path(tmpdir) / "benchmark-sweeps/latest-summary.json"
            write_json(
                summary_file,
                {
                    "status": "ok",
                    "generated_at": "2026-03-22T12:10:00+00:00",
                    "requested_suite_ids": ["coding-default-core", "docs-default-core"],
                    "success_count": 2,
                    "failure_count": 0,
                    "results": [
                        {
                            "suite_id": "coding-default-core",
                            "status": "ok",
                            "summary": {
                                "workflow_scorecard": {
                                    "decision": {"promote_to_new_baseline": True, "veto_reasons": []}
                                }
                            },
                        },
                        {
                            "suite_id": "docs-default-core",
                            "status": "ok",
                            "summary": {
                                "workflow_scorecard": {
                                    "decision": {
                                        "promote_to_new_baseline": False,
                                        "veto_reasons": ["human_assistance_not_improved"],
                                    }
                                }
                            },
                        },
                    ],
                    "failures": [],
                },
            )

            payload = consumer_module.build_benchmark_output_consumer_payload(
                summary_file=summary_file,
                notify_on="activity",
            )

        self.assertTrue(payload["notify"])
        self.assertEqual(payload["event"]["kind"], "benchmark_sweep")
        self.assertIn("请求基准集：coding-default-core, docs-default-core", payload["human_text"])
        self.assertIn("docs-default-core -> 未通过晋升", payload["human_text"])

    def test_main_emit_json_returns_structured_payload(self):
        consumer_module = load_module(
            "benchmark_output_consumer",
            "scripts/openclaw-ops/benchmark_output_consumer.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            summary_file = Path(tmpdir) / "benchmark-sweeps/latest-summary.json"
            write_json(
                summary_file,
                {
                    "status": "failed",
                    "generated_at": "2026-03-22T12:20:00+00:00",
                    "requested_suite_ids": ["ops-default-core"],
                    "success_count": 0,
                    "failure_count": 1,
                    "results": [],
                    "failures": [
                        {
                            "suite_id": "ops-default-core",
                            "error_type": "RuntimeError",
                            "error": "executor reports unavailable",
                        }
                    ],
                },
            )

            with redirect_stdout(StringIO()):
                payload = consumer_module.main(
                    [
                        "--summary-file",
                        str(summary_file),
                        "--emit-json",
                    ]
                )

        self.assertEqual(payload["event"]["kind"], "benchmark_sweep")
        self.assertIn("human_text", payload)


if __name__ == "__main__":
    unittest.main()

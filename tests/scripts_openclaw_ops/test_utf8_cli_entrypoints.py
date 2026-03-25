import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Utf8CliEntrypointsTests(unittest.TestCase):
    def test_human_facing_cli_entrypoints_enable_utf8_stdio(self):
        target_files = [
            "scripts/openclaw-ops/control_plane_summary_runner.py",
            "scripts/openclaw-ops/control_plane_dashboard.py",
            "scripts/openclaw-ops/control_plane_optimization_advisor.py",
            "scripts/openclaw-ops/control_plane_optimization_dispatcher.py",
            "scripts/openclaw-ops/control_plane_optimization_review_runner.py",
            "scripts/openclaw-ops/control_plane_profile_update_dispatcher.py",
            "scripts/openclaw-ops/control_plane_profile_update_applier.py",
            "scripts/openclaw-ops/control_plane_profile_update_validation_runner.py",
            "scripts/openclaw-ops/control_plane_acceptance_runner.py",
            "scripts/openclaw-ops/control_plane_live_acceptance_runner.py",
            "scripts/openclaw-ops/task_output_consumer.py",
            "scripts/openclaw-ops/benchmark_output_consumer.py",
            "scripts/openclaw-ops/task_output_broadcast_runner.py",
            "scripts/openclaw-ops/benchmark_orchestrator.py",
        ]

        for rel_path in target_files:
            with self.subTest(rel_path=rel_path):
                text = (ROOT / rel_path).read_text(encoding="utf-8-sig")
                self.assertIn(
                    "from utf8_runtime import configure_process_utf8_stdio",
                    text,
                )
                self.assertIn("configure_process_utf8_stdio()", text)


if __name__ == "__main__":
    unittest.main()

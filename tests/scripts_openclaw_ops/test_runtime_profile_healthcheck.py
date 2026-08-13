import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "skills" / "library" / "log-monitor" / "scripts" / "runtime_profile_healthcheck.py"


def load_module():
    spec = importlib.util.spec_from_file_location("runtime_profile_healthcheck", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeProfileHealthcheckTests(unittest.TestCase):
    def test_run_healthcheck_reports_ok_for_generic_fixture(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime = tmp / "runtime"
            repo = tmp / "repo"
            (runtime / ".workflow" / "pipeline-runs" / "run-demo").mkdir(parents=True)
            (runtime / "logs").mkdir()
            (runtime / "config.yaml").write_text(
                "runtime_name: test-runtime\nterminal:\n  cwd: TARGET_PROJECT\n",
                encoding="utf-8",
            )
            (runtime / "logs" / "startup.log").write_text("INFO connected\n", encoding="utf-8")
            (runtime / "logs" / "errors.log").write_text("", encoding="utf-8")
            state = runtime / ".workflow" / "pipeline-runs" / "run-demo" / "pipeline_state.json"
            state.write_text(
                '{"run_id":"r1","project_key":"demo","status":"passed","runtime":{"runtime_home":"TARGET_RUNTIME"}}',
                encoding="utf-8",
            )
            repo.mkdir()

            with mock.patch.object(
                mod,
                "process_status",
                return_value={"ok": True, "process_count": 1},
            ), mock.patch.object(
                mod,
                "git_status",
                return_value={"ok": True, "branch": "main", "status": ["## main...origin/main"], "remote_ok": True},
            ):
                report = mod.run_healthcheck(
                    mod.HealthConfig(
                        runtime_home=runtime,
                        repo_root=repo,
                        log_tail_lines=20,
                        required_paths=("config.yaml",),
                        process_match="workflow-runtime",
                    )
                )

            self.assertTrue(report["ok"])
            self.assertEqual(str(runtime), report["runtime_home"])
            self.assertEqual(str(runtime / "ops"), report["ops_dir"])
            self.assertEqual("test-runtime", report["checks"]["config"]["runtime_name"])

    def test_log_scan_marks_traceback_as_attention(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir)
            (runtime / "logs").mkdir()
            (runtime / "logs" / "startup.log").write_text("Traceback boom\n", encoding="utf-8")
            result = mod.scan_logs(runtime, ("logs/startup.log",), 20)
            self.assertFalse(result["ok"])
            self.assertEqual(1, result["hard_error_count"])

    def test_optional_runtime_checks_are_skipped_without_specific_configuration(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime = tmp / "runtime"
            repo = tmp / "repo"
            runtime.mkdir()
            repo.mkdir()
            with mock.patch.object(mod, "git_status", return_value={"ok": True}):
                report = mod.run_healthcheck(mod.HealthConfig(runtime_home=runtime, repo_root=repo))
            self.assertTrue(report["ok"])
            self.assertTrue(report["checks"]["config"]["skipped"])
            self.assertTrue(report["checks"]["logs"]["skipped"])
            self.assertTrue(report["checks"]["processes"]["skipped"])
            self.assertTrue(report["checks"]["pipeline_runs"]["skipped"])

    def test_markdown_contains_runtime_paths(self):
        mod = load_module()
        md = mod.to_markdown(
            {
                "ok": True,
                "checked_at": "2026-04-30T00:00:00+00:00",
                "runtime_home": "TARGET_RUNTIME",
                "repo_root": "TARGET_REPO",
                "ops_dir": "TARGET_RUNTIME/ops",
                "checks": {
                    "required_paths": {"ok": True},
                    "config": {"ok": True},
                    "logs": {
                        "ok": True,
                        "hard_error_count": 0,
                        "dns_warning_count": 0,
                        "finding_count": 0,
                    },
                    "processes": {"ok": True},
                    "pipeline_runs": {"ok": True},
                    "repo": {"ok": True},
                },
            }
        )
        self.assertIn("TARGET_RUNTIME/ops", md)
        self.assertIn("工作流 Runtime 健康检查", md)


if __name__ == "__main__":
    unittest.main()

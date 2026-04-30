import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "skills" / "library" / "log-monitor" / "scripts" / "multicorerouter_healthcheck.py"


def load_module():
    spec = importlib.util.spec_from_file_location("multicorerouter_healthcheck", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MulticoreRouterHealthcheckTests(unittest.TestCase):
    def test_run_healthcheck_reports_ok_for_fixture(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profile = tmp / "profile"
            repo = tmp / "repo"
            (profile / "workspace").mkdir(parents=True)
            (profile / ".workflow" / "pipeline-runs" / "20260430T000000Z-demo").mkdir(parents=True)
            (profile / "logs").mkdir()
            (profile / "config.yaml").write_text(
                "discord:\n  require_mention: true\n  allowed_channels: 1,2\nterminal:\n  cwd: /tmp/workspace\nDISCORD_HOME_CHANNEL: '1'\n",
                encoding="utf-8",
            )
            (profile / "start-gateway.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (profile / "logs" / "startup.log").write_text("INFO connected\n", encoding="utf-8")
            (profile / "logs" / "errors.log").write_text("", encoding="utf-8")
            state = profile / ".workflow" / "pipeline-runs" / "20260430T000000Z-demo" / "pipeline_state.json"
            state.write_text('{"run_id":"r1","project_key":"demo","status":"passed","runtime":{"runtime_home":"/tmp/profile"}}', encoding="utf-8")
            (repo / ".git").mkdir(parents=True)

            with mock.patch.object(mod, "process_status", return_value={"ok": True, "gateway_process_count": 1, "screen_present": True}), \
                 mock.patch.object(mod, "git_status", return_value={"ok": True, "branch": "main", "status": ["## main...origin/main"], "remote_ok": True}):
                report = mod.run_healthcheck(mod.HealthConfig(profile_home=profile, repo_root=repo, log_tail_lines=20))

            self.assertTrue(report["ok"])
            self.assertEqual("/home/ubuntu/.hermes", report["install_target_runtime_home"])
            self.assertEqual("/home/ubuntu/.hermes/ops", report["install_target_ops_dir"])
            self.assertEqual("1,2", report["checks"]["config"]["allowed_channels"])

    def test_log_scan_marks_traceback_as_attention(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = Path(tmpdir)
            (profile / "logs").mkdir()
            (profile / "logs" / "startup.log").write_text("Traceback boom\n", encoding="utf-8")
            (profile / "logs" / "errors.log").write_text("", encoding="utf-8")
            result = mod.scan_logs(profile, 20)
            self.assertFalse(result["ok"])
            self.assertEqual(1, result["hard_error_count"])

    def test_markdown_contains_install_target(self):
        mod = load_module()
        md = mod.to_markdown({
            "ok": True,
            "checked_at": "2026-04-30T00:00:00+00:00",
            "profile_home": "/p",
            "repo_root": "/r",
            "install_target_runtime_home": "/home/ubuntu/.hermes",
            "install_target_ops_dir": "/home/ubuntu/.hermes/ops",
            "checks": {
                "required_paths": {"ok": True},
                "config": {"ok": True},
                "logs": {"ok": True, "hard_error_count": 0, "dns_warning_count": 0, "finding_count": 0},
                "processes": {"ok": True},
                "pipeline_runs": {"ok": True},
                "repo": {"ok": True},
            },
        })
        self.assertIn("/home/ubuntu/.hermes/ops", md)


if __name__ == "__main__":
    unittest.main()

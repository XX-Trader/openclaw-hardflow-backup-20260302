import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib import util
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts/openclaw-ops/smart_arb_live_bridge.py"


class SmartArbLiveBridgeTests(unittest.TestCase):
    def _load_bridge_module(self):
        spec = util.spec_from_file_location("smart_arb_live_bridge", BRIDGE)
        module = util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def test_echo_code_review_outputs_required_verdict(self):
        proc = subprocess.run(
            [sys.executable, str(BRIDGE), "--stage", "code_review", "--agent-mode", "echo"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("Final verdict: pass", proc.stdout)
        self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)

    def test_project_dir_defaults_to_pipeline_agent_repo_dir(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(
            os.environ,
            {"PIPELINE_AGENT_REPO_DIR": tmpdir},
            clear=False,
        ):
            parser = bridge.build_parser()
            args = parser.parse_args(["--stage", "external_research", "--agent-mode", "echo"])

        self.assertEqual(Path(tmpdir), args.project_dir)

    def test_memory_writeback_uses_pipeline_memory_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()
            writeback = run_dir / "writeback_report.md"
            writeback.write_text("# Writeback\n\nBridge memory test.\n", encoding="utf-8")
            project_memory_dir = tmp / "memory" / "demo"

            env = dict(os.environ)
            env.update(
                {
                    "PIPELINE_PROJECT_KEY": "demo",
                    "PIPELINE_PROJECT_MEMORY_DIR": str(project_memory_dir),
                    "PIPELINE_WRITEBACK_REPORT_FILE": str(writeback),
                }
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "memory_writeback",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(ROOT),
                    "--python-bin",
                    sys.executable,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)
            changelog = project_memory_dir / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            record = json.loads(changelog.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("Bridge memory test", record["content"])

    def test_deployment_restarts_api_with_new_tmux_session_cwd(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            api_cwd = tmp / "智能多平台套利"
            uvicorn_bin = tmp / "bin" / "uvicorn"
            api_cwd.mkdir()
            uvicorn_bin.parent.mkdir()
            uvicorn_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            args = SimpleNamespace(
                allow_internal_api_restart=True,
                api_cwd=api_cwd,
                uvicorn_bin=uvicorn_bin,
                api_session="smart-arb-api",
                project_dir=tmp,
                deploy_wait_seconds=0,
            )
            calls: list[list[str] | str] = []

            def fake_run_command(command, cwd=None, shell=False):
                calls.append(command)
                if command == ["tmux", "has-session", "-t", "smart-arb-api"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, "{\"status\":\"ok\",\"strategy_running\":false}\n", "")

            with mock.patch.object(bridge, "run_command", side_effect=fake_run_command), mock.patch.object(bridge.time, "sleep"):
                rc = bridge.run_deployment(args)

            self.assertEqual(0, rc)
            self.assertIn(["tmux", "kill-session", "-t", "smart-arb-api"], calls)
            new_session = next(call for call in calls if isinstance(call, list) and call[:4] == ["tmux", "new-session", "-d", "-s"])
            self.assertIn("-c", new_session)
            self.assertEqual(str(api_cwd), new_session[new_session.index("-c") + 1])
            self.assertFalse(any(isinstance(call, list) and "send-keys" in call for call in calls))


if __name__ == "__main__":
    unittest.main()

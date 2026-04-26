import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import util
from io import StringIO
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

    def test_repair_context_can_be_supplied_inline_env(self):
        bridge = self._load_bridge_module()
        with mock.patch.dict(os.environ, {"PIPELINE_REPAIR_CONTEXT": "previous failure evidence"}, clear=False):
            self.assertEqual("previous failure evidence", bridge.repair_context_text())

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

    def test_external_research_prompt_forbids_file_edits_and_allows_local_only_pass(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")

        with mock.patch.dict(os.environ, {}, clear=True):
            prompt = bridge.stage_prompt("external_research", args, "只做本地环境检查")

        self.assertIn("NO_EXTERNAL_LOOKUP_NEEDED", prompt)
        self.assertIn("Do not modify files", prompt)
        self.assertIn("Return the stage evidence in your final answer/stdout only", prompt)
        self.assertNotIn("Stage output file hint", prompt)

    def test_non_code_hermes_env_hides_pipeline_artifact_paths(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(
            home=Path("/tmp/home"),
            hermes_bin=Path("/tmp/hermes/bin/hermes"),
        )
        profile_dir = Path("/tmp/hermes/profile")

        with mock.patch.dict(
            os.environ,
            {
                "PIPELINE_RESEARCH_REPORT_FILE": "/tmp/run/research_report.md",
                "PIPELINE_PATCH_SUMMARY_FILE": "/tmp/run/patch_summary.md",
                "PIPELINE_CODE_REVIEW_FILE": "/tmp/run/code_review.md",
            },
            clear=True,
        ):
            research_env = bridge.bridge_env(args, profile_dir, "external_research")
            review_env = bridge.bridge_env(args, profile_dir, "code_review")
            code_env = bridge.bridge_env(args, profile_dir, "code_execution")

        self.assertNotIn("PIPELINE_RESEARCH_REPORT_FILE", research_env)
        self.assertNotIn("PIPELINE_PATCH_SUMMARY_FILE", research_env)
        self.assertNotIn("PIPELINE_CODE_REVIEW_FILE", review_env)
        self.assertEqual("/tmp/run/research_report.md", code_env["PIPELINE_RESEARCH_REPORT_FILE"])
        self.assertEqual("/tmp/run/patch_summary.md", code_env["PIPELINE_PATCH_SUMMARY_FILE"])

    def test_code_execution_prompt_includes_prior_stage_context(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "research_report.md").write_text("P0 only; do not implement S1\n", encoding="utf-8")
            (run_dir / "solution.md").write_text("Solution says memory first\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"PIPELINE_RUN_DIR": str(run_dir)}, clear=True):
                prompt = bridge.stage_prompt("code_execution", args, "按 P0 顺序执行")

        self.assertIn("Prior accepted stage context", prompt)
        self.assertIn("P0 only; do not implement S1", prompt)
        self.assertIn("Solution says memory first", prompt)
        self.assertIn("Do not implement later-phase strategy work", prompt)

    def test_pipeline_context_redacts_sensitive_context_values(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")
        fake_github_token = "ghp_" + "123456789012345678901234567890123456"

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "research_report.md").write_text(
                "Authorization: Bearer should-not-leak\n"
                "api_key=should-not-leak-either\n"
                f"token only: {fake_github_token}\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"PIPELINE_RUN_DIR": str(run_dir)}, clear=True):
                prompt = bridge.stage_prompt("code_execution", args, "检查上下文脱敏")

        self.assertIn("Authorization: [REDACTED]", prompt)
        self.assertIn("api_key: [REDACTED]", prompt)
        self.assertNotIn("should-not-leak", prompt)
        self.assertNotIn("should-not-leak-either", prompt)
        self.assertNotIn(fake_github_token, prompt)

    def test_run_command_returns_evidence_on_timeout(self):
        bridge = self._load_bridge_module()
        proc = bridge.run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=ROOT,
            timeout=1,
        )

        self.assertEqual(124, proc.returncode)
        self.assertIn("timed out", proc.stderr)

    def test_default_verification_uses_compile_smoke_not_unittest_discover(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, {}, clear=True):
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "demo.py").write_text("value = 1\n", encoding="utf-8")
            tests_dir = tmp / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_demo.py").write_text("raise RuntimeError('should not be discovered')\n", encoding="utf-8")
            args = SimpleNamespace(project_dir=tmp, python_bin=Path(sys.executable), skip_tests=False)

            commands = bridge.verification_commands(args)

        self.assertIn("git diff --check", commands)
        self.assertTrue(any("-m compileall -q scripts" in command for command in commands))
        self.assertFalse(any("unittest discover" in command for command in commands))

    def test_run_verification_reports_timeout_from_cli_argument(self):
        bridge = self._load_bridge_module()
        slow_command = subprocess.list2cmdline([sys.executable, "-c", "import time; time.sleep(5)"])
        args = SimpleNamespace(
            project_dir=ROOT,
            python_bin=Path(sys.executable),
            skip_tests=False,
            verification_command_timeout_seconds=1,
        )
        out = StringIO()

        with mock.patch.dict(os.environ, {"SMART_ARB_LIVE_BRIDGE_TEST_COMMAND": slow_command}, clear=False), redirect_stdout(out):
            rc = bridge.run_verification(args)

        text = out.getvalue()
        self.assertEqual(1, rc)
        self.assertIn("Verification command timeout seconds: 1", text)
        self.assertIn("Command timed out after 1 seconds.", text)
        self.assertIn("LIVE_BRIDGE_STATUS: fail", text)

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

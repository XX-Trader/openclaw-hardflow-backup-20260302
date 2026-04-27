import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "skills/library/project-delivery-pipeline/scripts/hermes_profile_smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("project_delivery_hermes_profile_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def create_fixture_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Smoke\n", encoding="utf-8")
    git_kwargs = {
        "cwd": repo,
        "check": True,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    subprocess.run(["git", "init", "-b", "main"], **git_kwargs)
    subprocess.run(["git", "config", "user.name", "HardFlow Test"], **git_kwargs)
    subprocess.run(["git", "config", "user.email", "hardflow-test@example.invalid"], **git_kwargs)
    subprocess.run(["git", "add", "."], **git_kwargs)
    subprocess.run(["git", "commit", "-m", "初始化"], **git_kwargs)
    return repo


class ProjectDeliveryHermesProfileSmokeTests(unittest.TestCase):
    def test_echo_mode_runs_non_dry_run_hermes_pipeline_and_writes_evidence(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_home = root / "hermes"
            fixture_repo = create_fixture_repo(root)
            report = module.run_smoke(
                module.SmokeConfig(
                    project_key="demo",
                    runtime_home=runtime_home,
                    workspace_root=runtime_home / ".workflow" / "pipeline-runs",
                    project_memory_root=runtime_home / ".workflow" / "project-memory",
                    task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
                    run_id="smoke",
                    command_cwd=fixture_repo,
                    agent_mode="echo",
                )
            )

            self.assertTrue(report["ok"])
            self.assertFalse(report["real_hermes_chat_used"])
            run_dir = Path(report["run_dir"])
            state = json.loads((run_dir / "pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", state["status"])
            self.assertEqual("hermes", state["runtime_context"]["host"])
            self.assertEqual(str(runtime_home.resolve()), state["runtime_context"]["runtime_home"])
            self.assertTrue((run_dir / "command-runs" / "external_research-1.json").exists())
            self.assertTrue((run_dir / "hermes_smoke_report.json").exists())
            self.assertTrue((runtime_home / ".workflow" / "project-memory" / "demo" / "CHANGELOG.ndjson").exists())

    def test_hybrid_mode_uses_single_hermes_bundle_then_cached_stage_commands(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixture_repo = create_fixture_repo(root)
            fake = root / "fake_hermes.py"
            calls = root / "calls.txt"
            fake.write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "import json",
                        "import os",
                        "from pathlib import Path",
                        "Path(os.environ['FAKE_HERMES_CALLS']).write_text('called\\n', encoding='utf-8')",
                        "print(json.dumps({",
                        "    'research': '# Research\\n- bundled research\\n- Source URL: https://github.com/openai/codex',",
                        "    'code': '# Patch Summary\\n- bundled code',",
                        "    'requirements_review': '# Requirements Review\\nFinal verdict: ready_for_solution\\nConfidence: high',",
                        "    'solution_review': '# Solution Review\\nFinal verdict: ready_for_implement\\nConfidence: high',",
                        "    'code_review': '# Code Review\\nFinal verdict: pass\\nConfidence: high',",
                        "}))",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            if os.name == "nt":
                wrapper = root / "fake-hermes.cmd"
                wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
            else:
                wrapper = root / "fake-hermes"
                wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding="utf-8")
                wrapper.chmod(0o755)
            old_env = os.environ.get("FAKE_HERMES_CALLS")
            os.environ["FAKE_HERMES_CALLS"] = str(calls)
            try:
                runtime_home = root / "hermes"
                report = module.run_smoke(
                    module.SmokeConfig(
                        project_key="demo",
                        runtime_home=runtime_home,
                        workspace_root=runtime_home / ".workflow" / "pipeline-runs",
                        project_memory_root=runtime_home / ".workflow" / "project-memory",
                        task_center_db=runtime_home / "ops" / "task-center" / "task_center.db",
                        run_id="hybrid-smoke",
                        command_cwd=fixture_repo,
                        agent_mode="hybrid",
                        hermes_bin=str(wrapper),
                    )
                )
            finally:
                if old_env is None:
                    os.environ.pop("FAKE_HERMES_CALLS", None)
                else:
                    os.environ["FAKE_HERMES_CALLS"] = old_env

            self.assertTrue(report["ok"])
            self.assertTrue(report["real_hermes_chat_used"])
            self.assertEqual("hybrid-single-chat", report["ai_bundle_mode"])
            self.assertEqual("called\n", calls.read_text(encoding="utf-8"))
            bundle = json.loads(Path(report["ai_bundle_file"]).read_text(encoding="utf-8"))
            self.assertTrue(bundle["ok"])
            self.assertEqual("hybrid-single-chat", bundle["mode"])
            self.assertIn("requirements_review", bundle["outputs"])
            self.assertIn("solution_review", bundle["outputs"])
            self.assertIn("code_review", bundle["outputs"])
            run_dir = Path(report["run_dir"])
            research_report = (run_dir / "research_report.md").read_text(encoding="utf-8")
            self.assertIn("bundled research", research_report)
            review_report_1 = json.loads((run_dir / "command-runs" / "code_review-1.json").read_text(encoding="utf-8"))
            review_report_2 = json.loads((run_dir / "command-runs" / "code_review-2.json").read_text(encoding="utf-8"))
            self.assertEqual("reviewer-a", review_report_1["reviewer_role"])
            self.assertEqual("reviewer-b", review_report_2["reviewer_role"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "openclaw-ops" / "smart_arb_pipeline_entry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("smart_arb_pipeline_entry", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def completed_process(module, stdout: str, stderr: str = "", returncode: int = 0):
    return module.subprocess.CompletedProcess(
        args=["pipeline_runner"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class SmartArbPipelineEntryTests(unittest.TestCase):
    def test_parse_runner_state_returns_pipeline_payload(self):
        module = load_module()
        payload = {
            "run_id": "discord-arbitrageagent-test",
            "status": "completed",
            "stages": [],
        }

        self.assertEqual(payload, module.parse_runner_state(json.dumps(payload)))

    def test_utc_run_id_uses_subsecond_precision(self):
        module = load_module()
        run_id = module.utc_run_id("discord/arbitrageagent")

        self.assertRegex(run_id, r"^discord-arbitrageagent-\d{8}T\d{12}Z$")

    def test_render_chat_summary_shows_agents_and_stage_results(self):
        module = load_module()
        state = {
            "run_id": "discord-arbitrageagent-test",
            "status": "completed",
            "next_action": "none",
            "failed_stage": None,
            "run_dir": "/home/arbops/.hermes/pipeline-runs/discord-arbitrageagent-test",
            "task_center": {"task_id": "project-delivery:discord-arbitrageagent-test"},
            "artifacts": {
                "requirements_discussion": "/tmp/requirements_discussion.md",
                "verification": "/tmp/verification_report.md",
                "code_review": "/tmp/code_review.md",
                "deployment": "/tmp/deployment_report.md",
                "acceptance": "/tmp/delivery_evidence.md",
                "writeback": "/tmp/writeback_report.md",
            },
            "stages": [
                {"name": "intake", "status": "completed", "artifact": "/tmp/run_meta.json"},
                {"name": "external_research", "status": "completed", "verdict": "pass", "artifact": "/tmp/research_report.md"},
                {"name": "requirements_discussion", "status": "completed", "verdict": "pass", "artifact": "/tmp/requirements_discussion.md"},
                {"name": "verification", "status": "completed", "verdict": "pass", "score": 100, "artifact": "/tmp/verification_report.md"},
                {"name": "code_review", "status": "completed", "verdict": "pass", "artifact": "/tmp/code_review.md"},
                {"name": "deployment", "status": "completed", "verdict": "pass", "artifact": "/tmp/deployment_report.md"},
                {"name": "writeback", "status": "completed", "artifact": "/tmp/writeback_report.md"},
            ],
        }

        text = module.render_chat_summary(
            state,
            source="discord",
            profile="arbitrageagent",
            returncode=0,
        )

        self.assertIn("# nofx 任务执行状态", text)
        self.assertIn("Run ID: discord-arbitrageagent-test", text)
        self.assertIn("Task Center: project-delivery:discord-arbitrageagent-test", text)
        self.assertIn("任务接入: coordinator -> 完成", text)
        self.assertIn("外部资料核对: web-agent -> 完成", text)
        self.assertIn("双 AI 需求讨论: project-agent,reviewer -> 完成", text)
        self.assertIn("验证: tester -> 完成", text)
        self.assertIn("代码审查: reviewer -> 完成", text)
        self.assertIn("内部部署: deployer -> 完成", text)
        self.assertIn("记忆写回: doc-writer -> 完成", text)
        self.assertIn("关键证据: requirements_discussion, verification, code_review, deployment, acceptance, writeback", text)

    def test_main_default_prints_chat_summary(self):
        module = load_module()
        payload = {
            "run_id": "discord-arbitrageagent-test",
            "status": "completed",
            "next_action": "none",
            "failed_stage": None,
            "run_dir": "/tmp/discord-arbitrageagent-test",
            "task_center": {"task_id": "project-delivery:discord-arbitrageagent-test"},
            "artifacts": {},
            "stages": [
                {"name": "intake", "status": "completed", "artifact": "run_meta.json"},
            ],
        }
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module.subprocess,
            "run",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--profile", "arbitrageagent", "--source", "discord", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertIn("# nofx 任务执行状态", out.getvalue())
        self.assertIn("Run ID: discord-arbitrageagent-test", out.getvalue())
        self.assertIn("任务接入: coordinator -> 完成", out.getvalue())
        runner_cmd = run_mock.call_args.args[0]
        self.assertNotIn("--agent-workspace-mode", runner_cmd)
        self.assertEqual("", err.getvalue())

    def test_main_emit_json_prints_raw_runner_json(self):
        module = load_module()
        raw = '{"status":"completed","stages":[]}\n'
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module.subprocess,
            "run",
            return_value=completed_process(module, raw, stderr="runner warning\n"),
        ), redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--emit-json", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertEqual(raw, out.getvalue())
        self.assertEqual("runner warning\n", err.getvalue())

    def test_main_no_chat_summary_prints_raw_runner_output(self):
        module = load_module()
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module.subprocess,
            "run",
            return_value=completed_process(module, "runner raw output\n", stderr="runner err\n"),
        ), redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--no-chat-summary", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertEqual("runner raw output\n", out.getvalue())
        self.assertEqual("runner err\n", err.getvalue())


if __name__ == "__main__":
    unittest.main()

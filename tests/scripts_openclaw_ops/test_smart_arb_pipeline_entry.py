import importlib.util
import io
import json
import sys
import tempfile
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
        with tempfile.TemporaryDirectory() as tmp:
            command_report = Path(tmp) / "code_execution-1.json"
            command_report.write_text(
                json.dumps(
                    {
                        "stage": "code_execution",
                        "agent_id": "backend-dev",
                        "returncode": 0,
                        "ok": True,
                        "stdout": "changed files: scripts/openclaw-ops/smart_arb_pipeline_entry.py",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = {
                "run_id": "discord-arbitrageagent-test",
                "status": "completed",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "task_center": {"task_id": "project-delivery:discord-arbitrageagent-test"},
                "artifacts": {
                    "command_code_execution_1": str(command_report),
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
        self.assertIn("## agent 输出摘要", text)
        self.assertIn("代码执行: backend-dev -> 通过", text)
        self.assertIn("changed files", text)
        self.assertIn("关键证据: requirements_discussion, verification, code_review, deployment, acceptance, writeback", text)

    def test_render_chat_summary_shows_block_reason_and_repair_decision(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "code_execution-1.json"
            report.write_text(
                json.dumps(
                    {
                        "stage": "code_execution",
                        "agent_id": "backend-dev",
                        "returncode": 1,
                        "ok": False,
                        "stderr": "pytest failed in tests/test_runtime.py",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "code_execution",
                "run_dir": tmp,
                "artifacts": {"command_code_execution_1": str(report)},
                "stages": [
                    {"name": "code_execution", "status": "blocked", "detail": "coding command failed", "next_action": "return_to_code_execution"},
                ],
            }

            text = module.render_chat_summary(state, source="discord", profile="spreadagent", returncode=1)

        self.assertIn("## 阻塞原因", text)
        self.assertIn("卡点: 代码执行", text)
        self.assertIn("pytest failed", text)
        self.assertIn("可自动修复", text)

    def test_render_chat_summary_redacts_sensitive_failure_values(self):
        module = load_module()
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "return_to_code_execution",
            "failed_stage": "code_execution",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "code_execution",
                    "status": "blocked",
                    "detail": (
                        "api_key=short-secret-value caused failure\n"
                        "Authorization: Bearer short-auth-value\n"
                        "Cookie: sid=short-cookie-value\n"
                        "session_id=short-session-value\n"
                        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
                    ),
                    "next_action": "return_to_code_execution",
                },
            ],
        }

        text = module.render_chat_summary(state, source="discord", profile="spreadagent", returncode=1)

        self.assertIn("api_key=[REDACTED]", text)
        self.assertNotIn("short-secret-value", text)
        self.assertNotIn("short-auth-value", text)
        self.assertNotIn("short-cookie-value", text)
        self.assertNotIn("short-session-value", text)
        self.assertNotIn("BEGIN PRIVATE KEY", text)

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
        self.assertNotIn("--dry-run", runner_cmd)
        self.assertIn("--code-command", runner_cmd)
        self.assertNotIn("--agent-workspace-mode", runner_cmd)
        self.assertEqual("", err.getvalue())

    def test_main_auto_repairs_low_risk_blocked_run(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            blocked = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "code_execution",
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "code_execution", "status": "blocked", "detail": "unit test failed", "next_action": "return_to_code_execution"},
                ],
            }
            completed = {
                "run_id": "discord-spreadagent-test",
                "status": "completed",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "code_execution", "status": "completed", "artifact": "patch_summary.md"},
                ],
            }
            out = io.StringIO()
            err = io.StringIO()

            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[
                    completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(completed, ensure_ascii=False), returncode=0),
                ],
            ) as run_mock, redirect_stdout(out), redirect_stderr(err):
                rc = module.main(["--profile", "spreadagent", "--source", "discord", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertEqual(2, run_mock.call_count)
        first_cmd = run_mock.call_args_list[0].args[0]
        second_cmd = run_mock.call_args_list[1].args[0]
        run_id_index = first_cmd.index("--run-id") + 1
        self.assertEqual(first_cmd[run_id_index] + "-repair1", second_cmd[run_id_index])
        self.assertIn("已自动回流 1 次", out.getvalue())
        self.assertIn("自动修复后通过", out.getvalue())
        self.assertEqual("", err.getvalue())

    def test_main_auto_repair_keeps_context_when_context_file_write_fails(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            blocked = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "code_execution",
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "code_execution", "status": "blocked", "detail": "unit test failed", "next_action": "return_to_code_execution"},
                ],
            }
            completed = {
                "run_id": "discord-spreadagent-test-repair1",
                "status": "completed",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "code_execution", "status": "completed", "artifact": "patch_summary.md"},
                ],
            }

            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[
                    completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(completed, ensure_ascii=False), returncode=0),
                ],
            ) as run_mock, mock.patch.object(module, "write_repair_context_file", return_value=None), redirect_stdout(io.StringIO()):
                rc = module.main(["--emit-json", "--profile", "spreadagent", "--source", "discord", "--requirement", "demo"])

        self.assertEqual(0, rc)
        repair_env = run_mock.call_args_list[1].kwargs["env"]
        self.assertIn("PIPELINE_REPAIR_CONTEXT", repair_env)
        self.assertIn("unit test failed", repair_env["PIPELINE_REPAIR_CONTEXT"])
        self.assertNotIn("PIPELINE_REPAIR_CONTEXT_FILE", repair_env)

    def test_main_auto_repair_clears_stale_context_file_between_attempts(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first_context = tmp_path / "auto_repair_context_1.md"
            blocked_1 = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "code_execution",
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "code_execution", "status": "blocked", "detail": "first failure", "next_action": "return_to_code_execution"},
                ],
            }
            blocked_2 = {
                "run_id": "discord-spreadagent-test-repair1",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "verification",
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "verification", "status": "blocked", "detail": "second failure", "next_action": "return_to_code_execution"},
                ],
            }
            completed = {
                "run_id": "discord-spreadagent-test-repair2",
                "status": "completed",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {"name": "verification", "status": "completed", "artifact": "verification_report.md"},
                ],
            }

            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[
                    completed_process(module, json.dumps(blocked_1, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(blocked_2, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(completed, ensure_ascii=False), returncode=0),
                ],
            ) as run_mock, mock.patch.object(
                module,
                "write_repair_context_file",
                side_effect=[first_context, None],
            ), redirect_stdout(io.StringIO()):
                rc = module.main(["--emit-json", "--profile", "spreadagent", "--source", "discord", "--requirement", "demo"])

        self.assertEqual(0, rc)
        second_repair_env = run_mock.call_args_list[2].kwargs["env"]
        self.assertNotIn("PIPELINE_REPAIR_CONTEXT_FILE", second_repair_env)
        self.assertIn("second failure", second_repair_env["PIPELINE_REPAIR_CONTEXT"])
        self.assertNotIn("first failure", second_repair_env["PIPELINE_REPAIR_CONTEXT"])

    def test_negated_safety_terms_do_not_block_external_research_repair(self):
        module = load_module()
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "run_external_research",
            "failed_stage": "external_research",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "external_research",
                    "status": "blocked",
                    "detail": "不得泄露凭证；不得启动真实交易；不下单不划转",
                    "next_action": "run_external_research",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: run_external_research", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流动作: run_external_research", repair_reasons)

    def test_positive_credential_or_trading_request_still_high_risk(self):
        module = load_module()
        fake_openai_key = "sk-" + "1234567890abcdefghijklmnop"
        for detail in (
            "需要读取凭证并启用真实交易授权",
            "needs credentials to continue",
            "needs fund movement to continue",
            "requires funds operation before proceeding",
            "需要资金操作后继续",
            "do not use credentials, but needs fund movement to continue",
            "do not use credentials and needs fund movement to continue",
            "no credentials required and enable live trading",
            "不要读取凭证，但需要资金操作后继续",
            "不要读取凭证并且需要资金操作后继续",
            f"api_key={fake_openai_key} and continue",
            "password=hunter2 and continue",
            "credential=session-cookie and continue",
            "transfer funds to continue",
            "withdraw to continue",
            "place order now",
            "下单后继续",
            "提现后继续",
            "划转资金后继续",
            "no credentials required and transfer funds",
            "no credentials required and place order now",
        ):
            with self.subTest(detail=detail):
                state = {
                    "run_id": "discord-spreadagent-test",
                    "status": "blocked",
                    "next_action": "run_external_research",
                    "failed_stage": "external_research",
                    "run_dir": "",
                    "artifacts": {},
                    "stages": [
                        {
                            "name": "external_research",
                            "status": "blocked",
                            "detail": detail,
                            "next_action": "run_external_research",
                        },
                    ],
                }

                risk, reasons = module.classify_repair_risk(state)
                should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

                self.assertEqual("high", risk)
                self.assertTrue(reasons)
                self.assertFalse(should_repair)
                self.assertEqual("high", repair_risk)
                self.assertEqual(reasons, repair_reasons)

    def test_negated_english_safety_terms_do_not_block_repair(self):
        module = load_module()
        for detail in (
            "do not use credentials or transfer funds; keep live trading disabled",
            "do not transfer funds",
            "do not withdraw",
            "do not submit orders",
            "do not enable live trading",
            "do not use credentials or withdraw",
            "不提现",
            "不出金",
            "不转账",
            "不要下单",
            "不要读取凭证或转账",
            "不要泄露密钥以及提现",
        ):
            with self.subTest(detail=detail):
                state = {
                    "run_id": "discord-spreadagent-test",
                    "status": "blocked",
                    "next_action": "run_external_research",
                    "failed_stage": "external_research",
                    "run_dir": "",
                    "artifacts": {},
                    "stages": [
                        {
                            "name": "external_research",
                            "status": "blocked",
                            "detail": detail,
                            "next_action": "run_external_research",
                        },
                    ],
                }

                risk, reasons = module.classify_repair_risk(state)
                should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

                self.assertEqual("medium", risk)
                self.assertIn("可回流动作: run_external_research", reasons)
                self.assertTrue(should_repair)
                self.assertEqual("medium", repair_risk)

    def test_redacts_short_known_secret_shapes_from_failure_evidence(self):
        module = load_module()
        fake_github_token = "ghp_" + "123456789012345678901234567890123456"
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "return_to_code_execution",
            "failed_stage": "code_execution",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "code_execution",
                    "status": "blocked",
                    "detail": f"token only: {fake_github_token}",
                    "next_action": "return_to_code_execution",
                },
            ],
        }

        text = module.render_chat_summary(state, source="discord", profile="spreadagent", returncode=1)

        self.assertIn("[REDACTED]", text)
        self.assertNotIn(fake_github_token, text)

    def test_main_does_not_auto_repair_high_risk_blocked_run(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            blocked = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "return_to_code_execution",
                "failed_stage": "code_execution",
                "run_dir": tmp,
                "artifacts": {},
                "stages": [
                    {
                        "name": "code_execution",
                        "status": "blocked",
                        "detail": "requires real trading authorization before placing orders",
                        "next_action": "return_to_code_execution",
                    },
                ],
            }
            out = io.StringIO()

            with mock.patch.object(
                module.subprocess,
                "run",
                return_value=completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
            ) as run_mock, redirect_stdout(out):
                rc = module.main(["--profile", "spreadagent", "--source", "discord", "--requirement", "demo"])

        self.assertEqual(1, rc)
        self.assertEqual(1, run_mock.call_count)
        self.assertIn("需要人工确认", out.getvalue())

    def test_main_dry_run_flag_is_rejected(self):
        module = load_module()
        err = io.StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(err):
            module.main(["--emit-json", "--dry-run", "--requirement", "demo"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("dry-run is disabled", err.getvalue())

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

    def test_live_bridge_injects_explicit_verification_command_timeout(self):
        module = load_module()
        raw = '{"status":"completed","stages":[]}\n'

        with mock.patch.object(
            module.subprocess,
            "run",
            return_value=completed_process(module, raw),
        ) as run_mock:
            rc = module.main(
                [
                    "--emit-json",
                    "--live",
                    "--profile",
                    "spreadagent",
                    "--live-bridge-agent-mode",
                    "echo",
                    "--live-bridge-verification-command-timeout-seconds",
                    "17",
                    "--requirement",
                    "demo",
                ]
            )

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        verification_index = runner_cmd.index("--verification-command") + 1
        self.assertIn("--stage verification", runner_cmd[verification_index])
        self.assertIn("--verification-command-timeout-seconds 17", runner_cmd[verification_index])


if __name__ == "__main__":
    unittest.main()

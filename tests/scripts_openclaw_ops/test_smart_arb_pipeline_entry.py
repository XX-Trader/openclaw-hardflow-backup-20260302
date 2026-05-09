import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
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

    def test_parser_defaults_to_four_auto_repair_attempts(self):
        module = load_module()
        args = module.build_parser().parse_args([
            "--profile", "spreadagent",
            "--source", "discord",
            "--route-choice", "coding_workflow",
            "--requirement", "demo",
        ])

        self.assertEqual(4, args.auto_repair_attempts)

    def test_solution_review_negative_risk_boundaries_are_repairable(self):
        module = load_module()
        state = {
            "status": "blocked",
            "failed_stage": "solution_review",
            "next_action": "revise_solution",
            "run_dir": "",
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "artifact": "",
                    "detail": "\n".join(
                        [
                            "solution review did not allow implementation after iterative reviewer repair loop",
                            "Blocker: risk_boundaries contradict the accepted requirement.",
                            "delivery_plan.json target_files and verification_commands are good.",
                            "Required revised plan: replace risk_boundaries with task-specific boundaries:",
                            "- credentials allowed = false",
                            "- funds_and_orders allowed = false; any 下单、划转、提现 must stop.",
                            r"reason=\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?)\b\s*[:=]",
                        ]
                    ),
                }
            ],
        }

        risk, reasons = module.classify_repair_risk(state)

        self.assertEqual("medium", risk)
        self.assertTrue(any("回流" in reason or "revise_solution" in reason for reason in reasons))

    def test_solution_review_negated_credential_evidence_is_repairable(self):
        module = load_module()
        state = {
            "status": "blocked",
            "failed_stage": "solution_review",
            "next_action": "revise_solution",
            "run_dir": "",
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "artifact": "",
                    "detail": (
                        "solution review did not allow implementation after iterative reviewer repair loop\n"
                        "本轮没有发现真实凭证泄露、读取 cookie/token/auth 文件、真实交易/下单/划转/提现、或破坏性操作的硬停证据；"
                        "阻塞原因属于 plan-quality / scope-convergence。\n"
                        "Blocker: delivery_plan.json 仍把 execution_guard.json 错误提升为必改目标。\n"
                        "Blocker: target_files 包含自然语言伪目标 Binance/Bybit/Kraken/Gate/MEXC/Bitget/OKX public snapshot。\n"
                    ),
                }
            ],
        }

        risk, reasons = module.classify_repair_risk(state)

        self.assertEqual("medium", risk)
        self.assertNotIn("high", " ".join(reasons).lower())

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
                    "git_publish": "/tmp/git_publish_report.md",
                },
                "stages": [
                    {"name": "intake", "status": "completed", "artifact": "/tmp/run_meta.json"},
                    {"name": "external_research", "status": "completed", "verdict": "pass", "artifact": "/tmp/research_report.md"},
                    {"name": "requirements_discussion", "status": "completed", "verdict": "pass", "artifact": "/tmp/requirements_discussion.md"},
                    {"name": "verification", "status": "completed", "verdict": "pass", "score": 100, "artifact": "/tmp/verification_report.md"},
                    {"name": "code_review", "status": "completed", "verdict": "pass", "artifact": "/tmp/code_review.md"},
                    {"name": "deployment", "status": "completed", "verdict": "pass", "artifact": "/tmp/deployment_report.md"},
                    {"name": "writeback", "status": "completed", "artifact": "/tmp/writeback_report.md"},
                    {"name": "git_publish", "status": "completed", "verdict": "pass", "artifact": "/tmp/git_publish_report.md"},
                ],
            }

            text = module.render_chat_summary(
                state,
                source="discord",
                profile="arbitrageagent",
                returncode=0,
            )

        self.assertIn("# nofx 项目任务执行状态", text)
        self.assertIn("任务名称: 项目任务", text)
        self.assertIn("Run ID: discord-arbitrageagent-test", text)
        self.assertIn("回答状态: 已回答完毕", text)
        self.assertIn("Task Center: project-delivery:discord-arbitrageagent-test", text)
        self.assertIn("任务接入: coordinator -> 完成", text)
        self.assertIn("外部资料核对: web-agent -> 完成", text)
        self.assertIn("双 AI 需求讨论: project-agent,reviewer -> 完成", text)
        self.assertIn("验证: tester -> 完成", text)
        self.assertIn("代码审查: reviewer -> 完成", text)
        self.assertIn("内部部署: deployer -> 完成", text)
        self.assertIn("记忆写回: doc-writer -> 完成", text)
        self.assertIn("Git 发布: coordinator -> 完成", text)
        self.assertIn("## 阶段命令状态", text)
        self.assertIn("代码执行: backend-dev -> 通过；returncode=0；证据=代码执行命令1", text)
        self.assertNotIn("changed files", text)
        self.assertNotIn("关键证据:", text)

    def test_evidence_labels_are_short_human_summaries(self):
        module = load_module()

        self.assertEqual(
            "方案评审报告",
            module.stage_artifact_name({"name": "solution_review", "artifact": "/tmp/solution_review.md"}),
        )
        self.assertLessEqual(len(module.stage_artifact_name({"name": "solution_review", "artifact": "/tmp/solution_review.md"})), 20)
        self.assertEqual(
            "外部资料核对命令2",
            module.report_artifact_name(
                {
                    "stage": "external_research",
                    "index": 2,
                    "_artifact_path": "/tmp/command-runs/external_research-2.json",
                }
            ),
        )
        self.assertLessEqual(
            len(
                module.report_artifact_name(
                    {
                        "stage": "requirements_discussion",
                        "index": 1,
                        "_artifact_path": "/tmp/command-runs/requirements_discussion-1.json",
                    }
                )
            ),
            20,
        )

    def test_render_chat_summary_can_include_command_output_for_debug(self):
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
                "artifacts": {
                    "command_code_execution_1": str(command_report),
                    "verification": "/tmp/verification_report.md",
                },
                "stages": [{"name": "code_execution", "status": "completed", "artifact": "/tmp/patch_summary.md"}],
            }

            text = module.render_chat_summary(
                state,
                source="discord",
                profile="arbitrageagent",
                returncode=0,
                include_command_output=True,
                show_key_artifacts=True,
            )

        self.assertIn("摘要=changed files", text)
        self.assertIn("关键证据: verification", text)

    def test_render_chat_summary_shows_agent_runtime_refs(self):
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
                        "agent_session_id": "sess-123",
                        "agent_run_id": "run-456",
                        "agent_session_key": "agent:backend-dev:run:task-1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = {
                "run_id": "discord-spreadagent-test",
                "status": "completed",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "artifacts": {"command_code_execution_1": str(command_report)},
                "agent_invocations": [
                    {
                        "stage": "code_execution",
                        "agent_id": "backend-dev",
                        "session_id": "sess-123",
                        "run_id": "run-456",
                        "completed": True,
                    }
                ],
                "stages": [{"name": "code_execution", "status": "completed", "artifact": "/tmp/patch_summary.md"}],
            }

            text = module.render_chat_summary(state, source="discord", profile="spreadagent", returncode=0)

        self.assertIn("代码执行: backend-dev -> 完成；session=sess-123；run=run-456", text)
        self.assertIn("## 被调用 agent 明细", text)
        self.assertIn("session=sess-123；run=run-456；当前阶段=代码执行；是否完成=完成", text)
        self.assertIn("代码执行: backend-dev -> 通过；returncode=0；session=sess-123；run=run-456", text)

    def test_specified_agent_route_creates_task_and_renders_ids(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_home = tmp_path / "runtime"
            module.RUNTIME_HOME = runtime_home
            module.OPS_DIR = runtime_home / "ops"
            module.TASK_EXECUTOR_RUNNER = module.OPS_DIR / "policy" / "task_executor_runner.py"
            module.PROJECT_DIR = tmp_path / "project"
            module.HARDFLOW_REPO_DIR = tmp_path / "hardflow"
            (runtime_home / "profiles" / "spreadagent").mkdir(parents=True)
            (tmp_path / ".local" / "bin").mkdir(parents=True)
            (tmp_path / ".local" / "bin" / "hermes").write_text("#!/bin/sh\n", encoding="utf-8")
            module.PROJECT_DIR.mkdir()
            (
                module.HARDFLOW_REPO_DIR
                / "skills"
                / "library"
                / "control-plane-ops"
                / "scripts"
                / "policy"
            ).mkdir(parents=True)
            (
                module.HARDFLOW_REPO_DIR
                / "skills"
                / "library"
                / "control-plane-ops"
                / "scripts"
                / "policy"
                / "policy_workflow.py"
            ).write_text("# marker\n", encoding="utf-8")
            db_path = Path(tmp) / "task_center.db"
            module.TASK_CENTER_DB = db_path
            args = SimpleNamespace(
                source="discord",
                profile="spreadagent",
                assignee="tester",
                openclaw_bin="openclaw",
                specified_agent_timeout_seconds=30,
            )
            summary = {
                "run_id": "exec-1",
                "results": [
                    {
                        "task_id": "placeholder",
                        "assignee": "tester",
                        "stage": "test-loop",
                        "status": "executed",
                        "task_status_after": "passed",
                        "solved": False,
                        "executor_run_id": "exec-1",
                        "session_id": "task-session-1",
                        "agent_run_id": "agent-run-1",
                        "agent_session_key": "agent:tester:cron:task-executor:run:task-session-1",
                    }
                ],
            }
            completed = module.subprocess.CompletedProcess(
                args=["task_executor_runner"],
                returncode=0,
                stdout=json.dumps(summary, ensure_ascii=False),
                stderr="",
            )
            snapshot_task = {"task_id": "placeholder", "status": "passed", "assignee": "tester"}
            snapshot_reports = [
                {
                    "status": "passed",
                    "solved": False,
                    "details": {
                        "run_id": "exec-1",
                        "session_id": "task-session-1",
                        "agent_run_id": "agent-run-1",
                        "agent_session_key": "agent:tester:cron:task-executor:run:task-session-1",
                    }
                }
            ]
            with mock.patch.object(module.subprocess, "run", return_value=completed) as mocked_run, mock.patch.object(
                module,
                "task_center_snapshot",
                return_value=(snapshot_task, snapshot_reports),
            ), mock.patch.dict(module.os.environ, {"HOME": "/root"}, clear=False):
                payload = module.run_specified_agent_route(args, "请测试一次", "spreadagent")

            TaskCenter, _TaskCenterError = module.load_task_center_classes()
            task_center = TaskCenter(db_path)
            try:
                task = task_center.get_task(payload["task_id"], display_safe=False)
            finally:
                task_center.close()

        self.assertEqual("tester", task["assignee"])
        self.assertEqual("specified_agent_dispatch", task["task_type"])
        self.assertIn("指定 agent 按用户任务返回结构化结果", task["acceptance"])
        self.assertIn("执行器负责记录 session/run id", task["acceptance"])
        self.assertTrue(payload["completed"])
        self.assertEqual("agent-run-1", payload["refs"]["agent_run_id"])
        rendered = module.render_specified_agent_card(payload)
        self.assertIn("被调用 agent: tester", rendered)
        self.assertIn("agent session id: task-session-1", rendered)
        self.assertIn("agent run id: agent-run-1", rendered)
        self.assertIn("总状态: task=passed；report=passed", rendered)
        executor_cmd = mocked_run.call_args.args[0]
        self.assertIn("--only-task-id", executor_cmd)
        self.assertIn(payload["task_id"], executor_cmd)
        call_kwargs = mocked_run.call_args.kwargs
        self.assertEqual(str(module.PROJECT_DIR), call_kwargs["cwd"])
        self.assertEqual(str(module.RUNTIME_HOME), call_kwargs["env"]["OPENCLAW_HOME"])
        self.assertEqual(str(module.OPS_DIR / "task-center"), call_kwargs["env"]["TASK_CENTER_DIR"])
        self.assertEqual(str(module.OPS_DIR / "policy"), call_kwargs["env"]["OPENCLAW_POLICY_ROOT"])
        self.assertEqual(str(module.HARDFLOW_REPO_DIR.resolve()), call_kwargs["env"]["HARDFLOW_WORKFLOW_REPO"])
        self.assertEqual(str(module.HARDFLOW_REPO_DIR.resolve()), call_kwargs["env"]["OPENCLAW_WORKFLOW_REPO"])
        self.assertEqual(str(runtime_home.parent), call_kwargs["env"]["HOME"])
        self.assertEqual(str(runtime_home / "profiles" / "spreadagent"), call_kwargs["env"]["HERMES_HOME"])

    def test_specified_agent_executor_drops_root_to_runtime_user_when_available(self):
        module = load_module()
        with mock.patch.object(module.os, "geteuid", return_value=0, create=True), mock.patch.object(
            module.shutil,
            "which",
            return_value="/usr/sbin/runuser",
        ):
            cmd = module.specified_agent_executor_command(["/root/miniconda3/bin/python3", "runner.py"])

        self.assertEqual(["runuser", "-u", "arbops", "--", "python3", "runner.py"], cmd)

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
        self.assertIn("回答状态: 未回答完毕，等待人工确认或自动修复", text)
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

    def test_render_progress_update_shows_current_stage_and_recent_output(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            command_report = Path(tmp) / "code_execution-1.json"
            field_one_label = "api" + "_key"
            field_two_label = "pass" + "word"
            command_report.write_text(
                json.dumps(
                    {
                        "stage": "code_execution",
                        "agent_id": "backend-dev",
                        "returncode": 0,
                        "ok": True,
                        "stdout": "\n".join(
                            [
                                f"完成 basic_auth_proxy 修复，{field_one_label}=short-secret-value 已脱敏",
                                json.dumps(
                                    {field_one_label: "json-live-secret", field_two_label: "json-local-doc-example"},
                                    ensure_ascii=False,
                                ),
                                f'"{field_two_label}" = "toml-local-doc-example"',
                            ]
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = {
                "run_id": "discord-spreadagent-test",
                "status": "running",
                "next_action": "none",
                "failed_stage": None,
                "run_dir": tmp,
                "artifacts": {"command_code_execution_1": str(command_report)},
                "stages": [
                    {"name": "intake", "status": "completed", "artifact": "run_meta.json"},
                    {"name": "requirements_review", "status": "completed", "verdict": "pass", "artifact": "requirements_review.md"},
                    {"name": "code_execution", "status": "running", "detail": "正在修改代理脚本"},
                ],
            }

            text = module.render_progress_update(
                state,
                source="discord",
                profile="spreadagent",
                elapsed_seconds=125,
            )
            text_with_output = module.render_progress_update(
                state,
                source="discord",
                profile="spreadagent",
                elapsed_seconds=125,
                include_command_output=True,
            )

        self.assertIn("# nofx 项目任务执行进度", text)
        self.assertIn("任务名称: 项目任务", text)
        self.assertIn("回答状态: 正在回复/执行中", text)
        self.assertIn("总状态: 运行中", text)
        self.assertIn("已运行: 2分5秒", text)
        self.assertIn("阶段进度: 2/3 完成", text)
        self.assertIn("当前阶段: 代码执行: backend-dev -> running", text)
        self.assertIn("## 最近命令状态", text)
        self.assertIn("代码执行: backend-dev -> 通过；returncode=0；证据=代码执行命令1", text)
        self.assertNotIn("api_key=[REDACTED]", text)
        self.assertNotIn("short-secret-value", text)
        self.assertNotIn("json-live-secret", text)
        self.assertNotIn("json-local-doc-example", text)
        self.assertNotIn("toml-local-doc-example", text)

        self.assertIn("api_key=[REDACTED]", text_with_output)
        self.assertNotIn("short-secret-value", text_with_output)

    def test_render_progress_start_shows_answer_status(self):
        module = load_module()

        text = module.render_progress_start("discord-spreadagent-test", source="discord", profile="spreadagent")

        self.assertIn("# nofx 项目任务执行进度", text)
        self.assertIn("任务名称: 项目任务", text)
        self.assertIn("回答状态: 正在回复/执行中", text)
        self.assertIn("状态: 已启动 coordinator pipeline", text)

    def test_render_progress_start_uses_specific_task_title(self):
        module = load_module()
        requirement = "按用户确认的顺序依次推进 SmartMultiPlatformArbitrage：第一轮先执行 P0 口径修正。修正当前业务口径"

        text = module.render_progress_start(
            "discord-spreadagent-test",
            source="discord",
            profile="spreadagent",
            requirement=requirement,
        )

        self.assertIn("# nofx P0 口径修正执行进度", text)
        self.assertIn("任务名称: P0 口径修正", text)
        self.assertNotIn("# nofx 任务执行进度", text)

    def test_discord_source_without_route_choice_prints_selection_card(self):
        module = load_module()
        out = io.StringIO()

        with mock.patch.object(module, "run_pipeline_command") as run_mock, redirect_stdout(out):
            rc = module.main(["--profile", "spreadagent", "--source", "discord", "--requirement", "帮我拉取最新代码"])

        self.assertEqual(0, rc)
        self.assertFalse(run_mock.called)
        text = out.getvalue()
        self.assertIn("# nofx 执行链路选择", text)
        self.assertIn("推荐链路: direct_run", text)
        self.assertIn("回答状态: 等待人工选择", text)
        self.assertIn("已阻止直接启动 `smart-arb-pipeline`", text)

    def test_discord_source_with_non_pipeline_route_choice_skips_pipeline(self):
        module = load_module()
        out = io.StringIO()

        with mock.patch.object(module, "run_pipeline_command") as run_mock, redirect_stdout(out):
            rc = module.main(
                [
                    "--profile",
                    "spreadagent",
                    "--source",
                    "discord",
                    "--route-choice",
                    "direct_run",
                    "--emit-json",
                    "--requirement",
                    "不要走工作流，查一下状态",
                ]
            )

        self.assertEqual(0, rc)
        self.assertFalse(run_mock.called)
        payload = json.loads(out.getvalue())
        self.assertEqual("skipped", payload["status"])
        self.assertEqual("manual_route_not_pipeline:direct_run", payload["next_action"])

    def test_render_chat_summary_marks_unparsed_output_not_finished(self):
        module = load_module()

        text = module.render_chat_summary(
            None,
            source="discord",
            profile="spreadagent",
            returncode=1,
            raw_stderr="runner traceback",
        )

        self.assertIn("回答状态: 未回答完毕，无法解析执行结果", text)
        self.assertIn("returncode=1", text)

    def test_latest_command_reports_orders_by_command_timestamps(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            older = tmp_path / "verification-1.json"
            newer = tmp_path / "git_publish-1.json"
            older.write_text(
                json.dumps(
                    {
                        "stage": "verification",
                        "index": 1,
                        "ended_at": "2026-04-27T08:00:00+00:00",
                        "returncode": 0,
                        "ok": True,
                        "stdout": "verification ok",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            newer.write_text(
                json.dumps(
                    {
                        "stage": "git_publish",
                        "index": 1,
                        "ended_at": "2026-04-27T08:05:00+00:00",
                        "returncode": 0,
                        "ok": True,
                        "stdout": "git publish ok",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = {
                "run_dir": tmp,
                "artifacts": {
                    "command_git_publish_1": str(newer),
                    "command_verification_1": str(older),
                },
            }

            reports = module.latest_command_reports(state, limit=1)

        self.assertEqual("git_publish", reports[0]["stage"])

    def test_render_chat_summary_includes_group_plan_and_failure_summary(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan = tmp_path / "group_plan_publish.md"
            plan.write_text("# 群回传执行方案\n\n## 风险判断\n- low\n\n## 目标文件\n- `todo.md`\n", encoding="utf-8")
            risk = tmp_path / "pre_execution_risk.json"
            risk.write_text(
                json.dumps(
                    {
                        "risk_level": "guarded",
                        "execution_decision": "guarded_execute",
                        "human_confirmation_required": False,
                        "hard_stop_required": False,
                        "guarded_action_reasons": ["place_order"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            failure = tmp_path / "failure_summary.md"
            failure.write_text("# 失败步骤群回传摘要\n\n## 失败阶段\n- stage: `risk_gate`\n", encoding="utf-8")
            state = {
                "run_id": "discord-spreadagent-plan",
                "status": "blocked",
                "next_action": "fix_execution_guard",
                "failed_stage": "risk_gate",
                "run_dir": str(tmp_path),
                "artifacts": {
                    "plan_publish": str(plan),
                    "pre_execution_risk": str(risk),
                    "failure_summary": str(failure),
                },
                "stages": [
                    {"name": "plan_publish", "status": "completed", "artifact": "group_plan_publish.md"},
                    {"name": "risk_gate", "status": "blocked", "artifact": "group_plan_publish.md"},
                ],
            }

            text = module.render_chat_summary(state, source="discord", profile="spreadagent", returncode=0)

        self.assertIn("## 群回传执行方案", text)
        self.assertIn("risk=guarded; decision=guarded_execute", text)
        self.assertIn("group_plan_publish.md", text)
        self.assertIn("## 群回传失败摘要", text)
        self.assertIn("failure_summary.md", text)
        self.assertIn("风险门禁", text)

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
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main([
                "--profile", "arbitrageagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo",
                "--reviewer-a-provider", "openai-codex", "--reviewer-a-model", "gpt-5.5",
                "--reviewer-b-provider", "glm", "--reviewer-b-model", "glm-5.1",
            ])

        self.assertEqual(0, rc)
        self.assertIn("# nofx 项目任务执行状态", out.getvalue())
        self.assertIn("任务名称: 项目任务", out.getvalue())
        self.assertIn("Run ID: discord-arbitrageagent-test", out.getvalue())
        self.assertIn("任务接入: coordinator -> 完成", out.getvalue())
        runner_cmd = run_mock.call_args.args[0]
        self.assertNotIn("--dry-run", runner_cmd)
        self.assertIn("--code-command", runner_cmd)
        self.assertIn("--deployment-command", runner_cmd)
        self.assertIn("--git-publish-command", runner_cmd)
        self.assertEqual(2, runner_cmd.count("--requirements-review-command"))
        self.assertEqual(2, runner_cmd.count("--solution-review-command"))
        self.assertEqual(2, runner_cmd.count("--code-review-command"))
        review_commands = [
            runner_cmd[index + 1]
            for index, value in enumerate(runner_cmd)
            if value in {"--requirements-review-command", "--solution-review-command", "--code-review-command"}
        ]
        self.assertTrue(any("--reviewer-role reviewer-a" in command for command in review_commands))
        self.assertTrue(any("--reviewer-role reviewer-b" in command for command in review_commands))
        self.assertTrue(any("--reviewer-role reviewer-a" in command and "--model gpt-5.5" in command for command in review_commands))
        self.assertTrue(any("--reviewer-role reviewer-b" in command and "--provider glm" in command and "--model glm-5.1" in command for command in review_commands))
        self.assertTrue(all("--reviewer-fallback-models" in command for command in review_commands))
        self.assertNotIn("--agent-workspace-mode", runner_cmd)
        self.assertEqual(60, run_mock.call_args.kwargs["progress_interval_seconds"])
        self.assertEqual(8, run_mock.call_args.kwargs["progress_stage_limit"])
        self.assertEqual(3, run_mock.call_args.kwargs["progress_command_limit"])
        self.assertEqual("", err.getvalue())

    def test_main_defaults_reviewer_b_to_distinct_model(self):
        module = load_module()
        payload = {"run_id": "discord-spreadagent-test", "status": "completed", "next_action": "none", "stages": []}

        with mock.patch.dict(
            os.environ,
            {
                "SMART_ARB_LIVE_BRIDGE_PROVIDER": "openai-codex",
                "SMART_ARB_LIVE_BRIDGE_MODEL": "gpt-5.5",
                "SMART_ARB_REVIEWER_A_PROVIDER": "",
                "SMART_ARB_REVIEWER_A_MODEL": "",
                "SMART_ARB_REVIEWER_B_PROVIDER": "",
                "SMART_ARB_REVIEWER_B_MODEL": "",
            },
            clear=False,
        ), mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock:
            rc = module.main(["--emit-json", "--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo"])

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        review_commands = [
            runner_cmd[index + 1]
            for index, value in enumerate(runner_cmd)
            if value in {"--requirements-review-command", "--solution-review-command", "--code-review-command"}
        ]
        self.assertTrue(any("--reviewer-role reviewer-a" in command and "--provider openai-codex" in command and "--model gpt-5.5" in command for command in review_commands))
        self.assertTrue(any("--reviewer-role reviewer-b" in command and "--provider kimi-coding" in command and "--model kimi-k2.6" in command for command in review_commands))
        self.assertTrue(any("--reviewer-fallback-models" in command and "zai/glm-5.1" in command and "openai-codex/gpt-5.5" in command for command in review_commands))

    def test_main_passes_human_risk_confirmation_to_runner(self):
        module = load_module()
        payload = {"run_id": "discord-spreadagent-test", "status": "completed", "next_action": "none", "stages": []}

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock:
            rc = module.main([
                "--emit-json",
                "--profile",
                "spreadagent",
                "--source",
                "discord",
                "--route-choice",
                "coding_workflow",
                "--human-risk-confirmed",
                "--requirement",
                "已确认允许真实交易策略执行",
            ])

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        self.assertIn("--human-risk-confirmed", runner_cmd)

    def test_main_skips_deployment_when_requirement_forbids_service_control(self):
        module = load_module()
        payload = {
            "run_id": "discord-spreadagent-test",
            "status": "completed",
            "next_action": "none",
            "failed_stage": None,
            "run_dir": "/tmp/discord-spreadagent-test",
            "artifacts": {},
            "stages": [],
        }
        requirement = "P0-1 只写入 memory/docs 长期事实，不触碰服务控制，不重启服务，不部署。"
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", requirement])

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        self.assertIn("--code-review-command", runner_cmd)
        self.assertIn("--memory-write-command", runner_cmd)
        self.assertIn("--git-publish-command", runner_cmd)
        self.assertNotIn("--deployment-command", runner_cmd)
        self.assertNotIn("--allow-internal-api-restart", " ".join(runner_cmd))
        self.assertEqual("", err.getvalue())

    def test_main_keeps_deployment_for_mixed_docs_then_restart_requirement(self):
        module = load_module()
        payload = {
            "run_id": "discord-spreadagent-test",
            "status": "completed",
            "next_action": "none",
            "failed_stage": None,
            "run_dir": "/tmp/discord-spreadagent-test",
            "artifacts": {},
            "stages": [],
        }
        requirement = "先只写入 memory/docs 长期事实，再重启服务完成部署。"
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", requirement])

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        self.assertIn("--deployment-command", runner_cmd)
        self.assertIn("--allow-internal-api-restart", " ".join(runner_cmd))
        self.assertEqual("", err.getvalue())

    def test_main_can_skip_git_publish_command(self):
        module = load_module()
        payload = {
            "run_id": "discord-spreadagent-test",
            "status": "completed",
            "next_action": "none",
            "failed_stage": None,
            "run_dir": "/tmp/discord-spreadagent-test",
            "artifacts": {},
            "stages": [],
        }
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, json.dumps(payload, ensure_ascii=False)),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--skip-git-publish-command", "--requirement", "demo"])

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        self.assertNotIn("--git-publish-command", runner_cmd)
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
                module,
                "run_pipeline_command",
                side_effect=[
                    completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(completed, ensure_ascii=False), returncode=0),
                ],
            ) as run_mock, redirect_stdout(out), redirect_stderr(err):
                rc = module.main(["--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo"])

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
                module,
                "run_pipeline_command",
                side_effect=[
                    completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
                    completed_process(module, json.dumps(completed, ensure_ascii=False), returncode=0),
                ],
            ) as run_mock, mock.patch.object(module, "write_repair_context_file", return_value=None), redirect_stdout(io.StringIO()):
                rc = module.main(["--emit-json", "--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo"])

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
                module,
                "run_pipeline_command",
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
                rc = module.main(["--emit-json", "--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo"])

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

    def test_revise_solution_auto_repair_allows_negated_production_flag(self):
        module = load_module()
        for detail in (
            "requires_revision: revise the delivery plan; do not set PRODUCTION_TRADING_ENABLED=true; do not place orders or transfer funds.",
            "solution_review requires_revision: 不是安全硬停，未发现 credential/secret/cookie/auth-state、force push、真实交易/下单/划转/提现等硬风险；delivery_plan target_files 需要回流修订。",
        ):
            state = {
                "run_id": "discord-spreadagent-test",
                "status": "blocked",
                "next_action": "revise_solution",
                "failed_stage": "solution_review",
                "run_dir": "",
                "artifacts": {},
                "stages": [
                    {
                        "name": "solution_review",
                        "status": "blocked",
                        "detail": detail,
                        "next_action": "revise_solution",
                    },
                ],
            }

            risk, reasons = module.classify_repair_risk(state)
            should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

            self.assertEqual("medium", risk)
            self.assertIn("可回流动作: revise_solution", reasons)
            self.assertTrue(should_repair)
            self.assertEqual("medium", repair_risk)
            self.assertIn("可回流动作: revise_solution", repair_reasons)

    def test_revise_solution_auth_target_blocker_auto_repairs_plan_contract(self):
        module = load_module()
        detail = (
            "solution_review requires_revision: delivery_plan target_files needs "
            "credential/auth-state cleanup; remove auth.json from target_files before retry."
        )
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "revise_solution",
            "failed_stage": "solution_review",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "detail": detail,
                    "next_action": "revise_solution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流方案修订: revise_solution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流方案修订: revise_solution", repair_reasons)

    def test_revise_solution_plan_quality_blocker_with_regex_reason_auto_repairs(self):
        module = load_module()
        detail = (
            "solution_review did not allow implementation after iterative reviewer repair loop. "
            "reviewer-a: Final verdict: requires_revision. 当前 delivery_plan 仍把 inspect-only 文件放入 "
            "target_files，api_contracts 缺少 /api/stock-tokens/status、/api/stock-tokens/markets、"
            "/api/stock-tokens/opportunities，只读验收合同；verification_commands 仍含自然语言伪命令。 "
            r"处理: 需要执行保护契约；原因=\bforce\s+push\b, "
            r"(?:需要|要求|读取|查看|输出|打印|提交|上传|使用|修改|删除).{0,20}(?:密钥|凭证|token|cookie|私钥|会话), "
            r"(?:下单|划转|转账|提现|出金|资金操作)"
        )
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "revise_solution",
            "failed_stage": "solution_review",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "detail": detail,
                    "next_action": "revise_solution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 3)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: revise_solution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流动作: revise_solution", repair_reasons)

    def test_revise_solution_forbidden_safety_prose_auto_repairs(self):
        module = load_module()
        detail = (
            "solution_review requires_revision. Final verdict: requires_revision. "
            "delivery_plan.json 已包含顶层结构字段，并且没有发现 credential/auth、真实交易、下单、划转、提现、force push 等硬风险。 "
            "但当前方案仍有 plan-quality blocker，需要 revise_solution。 "
            "forbidden_targets: new Hyperliquid real stock-token adapter files; "
            "credential-bearing private account/auth files; "
            "no `reset` `stash` `checkout --` merge commit force push or destructive data cleanup. "
            "verification_commands: fail on credential leakage and unclear destructive targets; "
            "added-line safety scan 确认未启用 PRODUCTION_TRADING_ENABLED=true /资金路径； "
            "读取/导入 stock_token_public_adapter 断言 DEFAULT_ENABLED_PLATFORMS 不含 kraken/mexc。 "
            "处理: 需要人工确认；原因=\\b(?:withdraw(?:als?)?|transfer\\s+funds|place\\s+orders?|submit\\s+orders?)\\b, "
            "(?:需要|要求|读取|查看|输出|打印|提交|上传|使用|修改|删除).{0,20}(?:密钥|凭证|(?<!stock_)token|cookie|私钥|会话)"
        )
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "revise_solution",
            "failed_stage": "solution_review",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "detail": detail,
                    "next_action": "revise_solution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 3)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: revise_solution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流动作: revise_solution", repair_reasons)

    def test_revise_solution_real_secret_access_still_blocks_auto_repair(self):
        module = load_module()
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "revise_solution",
            "failed_stage": "solution_review",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "detail": "solution_review requires_revision: implementation plan asks agent to read API key credentials from auth state.",
                    "next_action": "revise_solution",
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

    def test_positive_credential_request_still_high_risk(self):
        module = load_module()
        fake_openai_key = "sk-" + "1234567890abcdefghijklmnop"
        for detail in (
            "需要读取凭证并启用真实交易授权",
            "needs credentials to continue",
            f"api_key={fake_openai_key} and continue",
            "password=hunter2 and continue",
            "credential=session-cookie and continue",
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

    def test_trading_fund_and_destructive_requests_are_guarded_repairable(self):
        module = load_module()
        for detail in (
            "set PRODUCTION_TRADING_ENABLED=true before retrying",
            "do not set PRODUCTION_TRADING_ENABLED=true; set PRODUCTION_TRADING_ENABLED=true",
            "do not set PRODUCTION_TRADING_ENABLED=true and set PRODUCTION_TRADING_ENABLED=true",
            "needs fund movement to continue",
            "requires funds operation before proceeding",
            "需要资金操作后继续",
            "do not use credentials, but needs fund movement to continue",
            "do not use credentials and needs fund movement to continue",
            "no credentials required and enable live trading",
            "不要读取凭证，但需要资金操作后继续",
            "不要读取凭证并且需要资金操作后继续",
            "transfer funds to continue",
            "withdraw to continue",
            "place order now",
            "下单后继续",
            "提现后继续",
            "划转资金后继续",
            "no credentials required and transfer funds",
            "no credentials required and place order now",
            "drop table audit_logs after backup",
            "rm -rf build-output after backup",
            "force push after reviewer approval",
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

                self.assertEqual("medium", risk)
                self.assertTrue(reasons)
                self.assertIn("高权限动作已降级为执行保护契约", reasons[0])
                self.assertTrue(should_repair)
                self.assertEqual("medium", repair_risk)
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

    def test_generated_solution_boundary_language_does_not_block_revise_solution(self):
        module = load_module()
        detail = (
            "Stop before any credential, secret value, private key, cookie, or auth state handling.\n"
            "Stop before production market/account actions or destructive repository/data changes."
        )
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "revise_solution",
            "failed_stage": "solution_review",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "solution_review",
                    "status": "blocked",
                    "detail": detail,
                    "next_action": "revise_solution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: revise_solution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)

    def test_negated_multilingual_safety_list_does_not_block_code_repair(self):
        module = load_module()
        detail = (
            "Do not print, move, or modify secrets, tokens, cookies, credentials, "
            "auth state files, or private API keys.\n"
            "不打印、不移动、不修改 token、cookie、OAuth、API key、交易所密钥或 credential-imports 原始凭证。\n"
            "未读取 raw token/key/cookie/OAuth/API key；未读取 credential-imports；未启动交易；未下单不划转。"
        )
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
                    "detail": detail,
                    "next_action": "return_to_code_execution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: return_to_code_execution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流动作: return_to_code_execution", repair_reasons)

    def test_redacted_markers_and_history_diff_do_not_block_repair(self):
        module = load_module()
        detail = (
            "# stderr\n"
            "session_id=[REDACTED]\n"
            "- 2026-04-25: 按用户要求从待办中删除 P0 凭证/安全轮换类事项，不再作为项目 TODO 跟踪。\n"
            "- 未在文档或输出中保留任何 token/key/PAT 明文。\n"
            "LIVE_BRIDGE_STATUS: fail"
        )
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
                    "detail": detail,
                    "next_action": "return_to_code_execution",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: return_to_code_execution", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)

    def test_redacted_secret_request_stays_high_risk(self):
        module = load_module()
        details = [
            "Need api_key=[REDACTED] before retrying.",
            "Need Authorization: [REDACTED] before retrying.",
            "Need session_id=[REDACTED] before retrying.",
        ]
        for detail in details:
            with self.subTest(detail=detail):
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
                            "detail": detail,
                            "next_action": "return_to_code_execution",
                        },
                    ],
                }

                risk, _ = module.classify_repair_risk(state)
                should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

                self.assertEqual("high", risk)
                self.assertFalse(should_repair)
                self.assertEqual("high", repair_risk)

    def test_negated_redacted_secret_need_does_not_block_repair(self):
        module = load_module()
        details = [
            "No need for api_key=[REDACTED] before retrying.",
            "Do not need Authorization: [REDACTED] before retrying.",
            "Authorization: [REDACTED] is not required for this docs-only repair.",
            "No need for session_id=[REDACTED] before retrying.",
        ]
        for detail in details:
            with self.subTest(detail=detail):
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
                            "detail": detail,
                            "next_action": "return_to_code_execution",
                        },
                    ],
                }

                risk, reasons = module.classify_repair_risk(state)
                should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

                self.assertEqual("medium", risk)
                self.assertIn("可回流动作: return_to_code_execution", reasons)
                self.assertTrue(should_repair)
                self.assertEqual("medium", repair_risk)

    def test_fix_git_publish_can_auto_repair_without_secret_evidence(self):
        module = load_module()
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "fix_git_publish",
            "failed_stage": "git_publish",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "git_publish",
                    "status": "blocked",
                    "detail": "remote rejected non-fast-forward; rerun after pulling latest main",
                    "next_action": "fix_git_publish",
                },
            ],
        }

        risk, reasons = module.classify_repair_risk(state)
        should_repair, repair_risk, repair_reasons = module.should_auto_repair(state, 0, 2)

        self.assertEqual("medium", risk)
        self.assertIn("可回流动作: fix_git_publish", reasons)
        self.assertTrue(should_repair)
        self.assertEqual("medium", repair_risk)
        self.assertIn("可回流动作: fix_git_publish", repair_reasons)

    def test_fix_git_publish_stays_high_risk_with_secret_evidence(self):
        module = load_module()
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "fix_git_publish",
            "failed_stage": "git_publish",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "git_publish",
                    "status": "blocked",
                    "detail": "Need api_key=[REDACTED] before retrying publish.",
                    "next_action": "fix_git_publish",
                },
            ],
        }

        risk, _ = module.classify_repair_risk(state)
        should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

        self.assertEqual("high", risk)
        self.assertFalse(should_repair)
        self.assertEqual("high", repair_risk)

    def test_fix_git_publish_stays_high_risk_with_secret_scan_findings(self):
        module = load_module()
        detail = (
            "## Secret Scan Findings\n"
            "- Blocking findings: 1\n"
            "- config.py:1 risk=high rule=known_secret_pattern blocking=true "
            "snippet=OPENAI_API_KEY=[REDACTED]\n"
            "LIVE_BRIDGE_STATUS: fail"
        )
        state = {
            "run_id": "discord-spreadagent-test",
            "status": "blocked",
            "next_action": "fix_git_publish",
            "failed_stage": "git_publish",
            "run_dir": "",
            "artifacts": {},
            "stages": [
                {
                    "name": "git_publish",
                    "status": "blocked",
                    "detail": detail,
                    "next_action": "fix_git_publish",
                },
            ],
        }

        risk, _ = module.classify_repair_risk(state)
        should_repair, repair_risk, _ = module.should_auto_repair(state, 0, 2)

        self.assertEqual("high", risk)
        self.assertFalse(should_repair)
        self.assertEqual("high", repair_risk)

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
                        "detail": "requires API key credentials before continuing",
                        "next_action": "return_to_code_execution",
                    },
                ],
            }
            out = io.StringIO()

            with mock.patch.object(
                module,
                "run_pipeline_command",
                return_value=completed_process(module, json.dumps(blocked, ensure_ascii=False), returncode=1),
            ) as run_mock, redirect_stdout(out):
                rc = module.main(["--profile", "spreadagent", "--source", "discord", "--route-choice", "coding_workflow", "--requirement", "demo"])

        self.assertEqual(1, rc)
        self.assertEqual(1, run_mock.call_count)
        self.assertIn("未继续自动修复: high", out.getvalue())

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
            module,
            "run_pipeline_command",
            return_value=completed_process(module, raw, stderr="runner warning\n"),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--emit-json", "--route-choice", "coding_workflow", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertEqual(raw, out.getvalue())
        self.assertEqual("runner warning\n", err.getvalue())
        self.assertEqual(0, run_mock.call_args.kwargs["progress_interval_seconds"])

    def test_main_no_chat_summary_prints_raw_runner_output(self):
        module = load_module()
        out = io.StringIO()
        err = io.StringIO()

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, "runner raw output\n", stderr="runner err\n"),
        ) as run_mock, redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--no-chat-summary", "--route-choice", "coding_workflow", "--requirement", "demo"])

        self.assertEqual(0, rc)
        self.assertEqual("runner raw output\n", out.getvalue())
        self.assertEqual("runner err\n", err.getvalue())
        self.assertEqual(0, run_mock.call_args.kwargs["progress_interval_seconds"])

    def test_main_infers_frontend_code_agent_from_requirement(self):
        module = load_module()
        raw = '{"status":"completed","stages":[]}\n'
        out = io.StringIO()

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, raw),
        ) as run_mock, redirect_stdout(out):
            rc = module.main(
                [
                    "--emit-json",
                    "--no-live-bridge",
                    "--route-choice",
                    "coding_workflow",
                    "--requirement",
                    "请优化前端页面布局和按钮交互",
                ]
            )

        self.assertEqual(0, rc)
        runner_cmd = run_mock.call_args.args[0]
        code_agent_index = runner_cmd.index("--code-agent") + 1
        self.assertEqual("frontend-dev", runner_cmd[code_agent_index])

    def test_live_bridge_injects_explicit_verification_command_timeout(self):
        module = load_module()
        raw = '{"status":"completed","stages":[]}\n'

        with mock.patch.object(
            module,
            "run_pipeline_command",
            return_value=completed_process(module, raw),
        ) as run_mock:
            rc = module.main(
                [
                    "--emit-json",
                    "--live",
                    "--profile",
                    "spreadagent",
                    "--route-choice",
                    "coding_workflow",
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

    def test_risk_scan_ignores_negated_safety_constraints_but_keeps_real_risks(self):
        module = load_module()
        safe_text = (
            "Do not start real trading, place orders, transfer funds, or change production trading controls.\n"
            "Do not read, print, move, or modify token/cookie/OAuth/API key/auth JSON/credential files.\n"
            "do not start real trading, place orders, transfer funds, or read/print/move/modify credentials.\n"
            "no PRODUCTION_TRADING_ENABLED=true was found in added diff.\n"
            "不要读取、打印、移动或修改 token/cookie/OAuth/API key/auth JSON/credential files。"
            "未发现 PRODUCTION_TRADING_ENABLED=true。"
        )
        safe_scan = module.risk_scan_text(safe_text)
        self.assertFalse(any(pattern.search(safe_scan) for pattern in module.HIGH_RISK_PATTERNS), safe_scan)

        regex_reason_text = (
            r"未继续自动修复: high; \\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?)\\b\\s*[:=], "
            r"PRODUCTION_TRADING_ENABLED\\s*=\\s*true, \\b(?:withdraw(?:als?)?|transfer\\s+funds|place\\s+orders?)\\b"
        )
        regex_scan = module.risk_scan_text(regex_reason_text)
        self.assertFalse(any(pattern.search(regex_scan) for pattern in module.HIGH_RISK_PATTERNS), regex_scan)

        chinese_regex_reason_text = (
            r"自动修复判断 - 判断: 未继续自动修复: high; "
            r"(?:需要|要求|读取|查看|输出|打印|提交|上传|使用|修改|删除).{0,20}"
            r"(?:密钥|凭证|(?<!stock_)(?<!stock-)(?<!stock )tokens?(?!ized)(?![A-Za-z0-9_])|cookie|私钥|会话)"
        )
        chinese_regex_scan = module.risk_scan_text(chinese_regex_reason_text)
        self.assertFalse(any(pattern.search(chinese_regex_scan) for pattern in module.HIGH_RISK_PATTERNS), chinese_regex_scan)

        stock_token_plan_text = "要求实现阶段检查页面是否硬编码 stock-token，并把币股现货不进 MVP 转成断言。"
        stock_token_scan = module.risk_scan_text(stock_token_plan_text)
        self.assertFalse(any(pattern.search(stock_token_scan) for pattern in module.HARD_REPAIR_RISK_PATTERNS), stock_token_scan)

        negated_requirement_list_text = "计划没有要求真实交易、下单、划转、提现、读取凭证或新增真实 Hyperliquid stock-token adapter。"
        negated_requirement_scan = module.risk_scan_text(negated_requirement_list_text)
        self.assertFalse(any(pattern.search(negated_requirement_scan) for pattern in module.HARD_REPAIR_RISK_PATTERNS), negated_requirement_scan)

        status_card_text = (
            "自动修复判断\n"
            "判断: 未继续自动修复\n"
            "原因: 被风险规则判为 high\n"
            "触发点: 文本中仍出现真实交易/下单/划转/提现/资金操作相关表达\n"
            "触发项: 文本中仍出现资金动作相关关键词\n"
            "实际本轮边界: 用户需求里是保持禁用、不执行\n"
            "没有启动真实交易，没有下单、划转、提现或处理凭证\n"
        )
        status_scan = module.risk_scan_text(status_card_text)
        self.assertFalse(any(pattern.search(status_scan) for pattern in module.HIGH_RISK_PATTERNS), status_scan)

        negative_secret_scan_text = (
            "code review found credential/password/secret leakage and must be fixed before publish\n"
            "reviewer-b: Secret scan：commit diff 中无结构化 credential/secret/token 赋值\n"
            "reviewer-b: Secret scan: no structural credential/secret/token assignment in commit diff\n"
        )
        negative_secret_scan = module.risk_scan_text(negative_secret_scan_text)
        self.assertFalse(any(pattern.search(negative_secret_scan) for pattern in module.HARD_REPAIR_RISK_PATTERNS), negative_secret_scan)

        risky_scan = module.risk_scan_text("Read and print API keys from credential-imports, then start real trading and place orders.")
        self.assertTrue(any(pattern.search(risky_scan) for pattern in module.HIGH_RISK_PATTERNS), risky_scan)

    def test_code_review_contract_drift_is_auto_repairable_not_high_risk(self):
        module = load_module()
        state = {
            "status": "blocked",
            "failed_stage": "code_review",
            "next_action": "return_to_code_execution",
            "stages": [
                {
                    "name": "code_review",
                    "status": "blocked",
                    "detail": (
                        "code review failed and must be fixed by implementation agent. "
                        "Final verdict: requires_revision. Blocking issue: Required memory target files are "
                        "missing from the reviewed workspace and are not part of the diff; ignored by git; "
                        "memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md: MISSING. "
                        "Residual scan found no `PRODUCTION_TRADING_ENABLED=true` and reviewer pattern "
                        r"PRODUCTION_TRADING_ENABLED\s*=\s*true was used only as a scan rule."
                    ),
                }
            ],
        }
        risk, reasons = module.classify_repair_risk(state)
        self.assertEqual("medium", risk, reasons)
        self.assertIn("return_to_code_execution", reasons[0])

        high_state = dict(state)
        high_state["stages"] = [
            {
                "name": "code_review",
                "status": "blocked",
                "detail": "requires_revision but patch contains authorization: Bearer real-token-like-value",
            }
        ]
        risk, reasons = module.classify_repair_risk(high_state)
        self.assertEqual("high", risk, reasons)


if __name__ == "__main__":
    unittest.main()

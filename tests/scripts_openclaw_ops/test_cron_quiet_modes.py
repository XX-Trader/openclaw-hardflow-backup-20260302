import json
import contextlib
import io
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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


class CronQuietModeTests(unittest.TestCase):
    def test_switch_model_tier_high_doubao_keeps_code_and_ops_layers(self):
        module = load_module(
            "switch_model_tier",
            "scripts/openclaw-ops/switch_model_tier.py",
        )
        profiles = module.load_profiles(ROOT / "scripts/openclaw-ops/model_tier_profiles.json")
        tier = module.resolve_tier("high_doubao", profiles)
        profile = module.ensure_profile(profiles["tiers"][tier], tier)

        self.assertEqual(tier, "high_doubao")
        self.assertEqual(profile["primary_model"], "kimicode/Doubao-Seed-2.0-Code")
        self.assertEqual(profile["agent_model_overrides"]["optimization-agent"], "openai-codex/gpt-5.3-codex")
        self.assertEqual(profile["agent_model_overrides"]["backend-dev"], "openai-codex/gpt-5.3-codex")
        self.assertEqual(profile["agent_model_overrides"]["ops-agent"], "glmcode/glm-4.7")
        self.assertEqual(profile["agent_model_overrides"]["web-agent"], "glmcode/glm-4.7")
        self.assertEqual(profile["model_thinking_overrides"]["kimicode/Doubao-Seed-2.0-Code"], "high")
        self.assertEqual(profile["model_thinking_overrides"]["openai-codex/gpt-5.3-codex"], "xhigh")

    def test_ops_cron_runner_creates_follow_up_task_for_failed_workflow(self):
        module = load_module(
            "ops_cron_runner",
            "scripts/openclaw-ops/ops_cron_runner.py",
        )
        cfg = module.default_config()
        state = {}
        workflow_health = {
            "failed_jobs": [
                {
                    "id": "9873ab34-c4af-4db0-8cd5-40df68f92efd",
                    "name": "ops_daily_work_report_dingtalk",
                    "last_status": "error",
                    "consecutive_errors": 1,
                    "last_run_at": "2026-03-08T07:02:45+08:00",
                    "stale_minutes": 61.5,
                    "last_error": "⚠️ Edit: in ~/.openclaw/ops/daily_work_report.py (53 chars) failed",
                }
            ]
        }
        invoked: list[list[str]] = []

        def fake_invoke(db_path: Path, args: list[str], timeout: int = 30):
            invoked.append(list(args))
            return True, {"ok": True}, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            run_file = Path(tmpdir) / "ops_run.json"
            with mock.patch.object(module, "invoke_policy_enforcer", side_effect=fake_invoke):
                summary = module.create_workflow_follow_up_tasks(
                    cfg=cfg,
                    state=state,
                    db_path=db_path,
                    actor="ops-agent/ops-cron-runner",
                    run_file=run_file,
                    run_task_id="cron:ops-incremental-monitor",
                    mode="incremental",
                    started_at="2026-03-08T12:37:28+08:00",
                    workflow_health=workflow_health,
                )
                repeated = module.create_workflow_follow_up_tasks(
                    cfg=cfg,
                    state=state,
                    db_path=db_path,
                    actor="ops-agent/ops-cron-runner",
                    run_file=run_file,
                    run_task_id="cron:ops-incremental-monitor",
                    mode="incremental",
                    started_at="2026-03-08T12:37:28+08:00",
                    workflow_health=workflow_health,
                )

        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["created_count"], 1)
        self.assertEqual(summary["existing_count"], 0)
        self.assertEqual(len(summary["tasks"]), 1)
        self.assertTrue(summary["tasks"][0]["task_id"].startswith("todo-ops-workflow-repair-"))
        self.assertEqual(summary["tasks"][0]["assignee"], "optimization-agent")
        self.assertEqual(len(invoked), 1)
        args = invoked[0]
        self.assertIn("create-task", args)
        self.assertIn("ops_workflow_repair", args)
        self.assertIn("jobs", args)
        self.assertIn("optimization-agent", args)
        self.assertIn("false", args)
        self.assertIn("true", args)
        self.assertEqual(repeated["created_count"], 0)
        self.assertEqual(repeated["existing_count"], 0)
        self.assertEqual(len(invoked), 1)

    def test_ops_cron_runner_marks_existing_follow_up_task_without_error(self):
        module = load_module(
            "ops_cron_runner",
            "scripts/openclaw-ops/ops_cron_runner.py",
        )
        cfg = module.default_config()
        state = {}
        workflow_health = {
            "failed_jobs": [
                {
                    "id": "job-1",
                    "name": "ops_daily_work_report_dingtalk",
                    "last_status": "error",
                    "consecutive_errors": 1,
                    "last_run_at": "2026-03-08T07:02:45+08:00",
                    "stale_minutes": 61.5,
                    "last_error": "⚠️ Edit failed",
                }
            ]
        }

        def fake_invoke(db_path: Path, args: list[str], timeout: int = 30):
            return False, {}, "task_id already exists"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            with mock.patch.object(module, "invoke_policy_enforcer", side_effect=fake_invoke):
                summary = module.create_workflow_follow_up_tasks(
                    cfg=cfg,
                    state=state,
                    db_path=db_path,
                    actor="ops-agent/ops-cron-runner",
                    run_file=Path(tmpdir) / "ops_run.json",
                    run_task_id="cron:ops-incremental-monitor",
                    mode="incremental",
                    started_at="2026-03-08T12:37:28+08:00",
                    workflow_health=workflow_health,
                )

        self.assertEqual(summary["created_count"], 0)
        self.assertEqual(summary["existing_count"], 1)
        self.assertEqual(summary["errors"], [])

    def test_ops_cron_runner_follow_up_output_includes_progress_summary(self):
        module = load_module(
            "ops_cron_runner",
            "scripts/openclaw-ops/ops_cron_runner.py",
        )
        base_output = "\n".join(
            [
                "# 运维巡检异常",
                "- 模式: incremental",
                "- 任务: cron:ops-incremental-monitor",
                "- 失败工作流:",
                "  1. job-1 / ops_daily_work_report_dingtalk",
            ]
        )
        summary = {
            "created_count": 1,
            "existing_count": 1,
            "tasks": [
                {
                    "task_id": "todo-ops-workflow-repair-job-1",
                    "assignee": "optimization-agent",
                    "status": "created",
                    "workflow_job_id": "job-1",
                    "workflow_job_name": "ops_daily_work_report_dingtalk",
                },
                {
                    "task_id": "todo-ops-workflow-repair-job-2",
                    "assignee": "optimization-agent",
                    "status": "existing",
                    "workflow_job_id": "job-2",
                    "workflow_job_name": "ops_local_openclaw_git_backup",
                },
            ],
            "errors": [],
        }

        output = module.append_workflow_follow_up_output(base_output, summary)

        self.assertIn("- 修复进展:", output)
        self.assertIn("新建修复任务 1 条", output)
        self.assertIn("已有待处理修复任务 1 条", output)
        self.assertIn("ops_daily_work_report_dingtalk", output)
        self.assertIn("ops_local_openclaw_git_backup", output)

    def test_task_executor_skips_ops_runtime_cron_binding_tasks(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                pool TEXT NOT NULL,
                priority TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO tasks (task_id, status, pool, priority, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("cron:ops-governance-evolution", "pending", "jobs", "low", "2026-03-07T08:00:00+00:00"),
                ("todo-1", "pending", "todo", "medium", "2026-03-07T08:01:00+00:00"),
            ],
        )

        tasks = {
            "cron:ops-governance-evolution": {
                "task_id": "cron:ops-governance-evolution",
                "status": "pending",
                "pool": "jobs",
                "priority": "low",
                "task_type": "ops_runtime_cron",
                "reason": "[CRON_RUNTIME] bind cron:ops-governance-evolution",
            },
            "todo-1": {
                "task_id": "todo-1",
                "status": "pending",
                "pool": "todo",
                "priority": "medium",
                "task_type": "workflow",
                "reason": "normal work item",
            },
        }

        class FakeDB:
            def __init__(self, conn_obj, task_map):
                self.conn = conn_obj
                self._task_map = task_map

            def get_task(self, task_id):
                return self._task_map[task_id]

        enforcer = SimpleNamespace(db=FakeDB(conn, tasks))

        selected = module.select_tasks(enforcer, "", 3)
        self.assertEqual([item["task_id"] for item in selected], ["todo-1"])

    def test_task_executor_builds_bounded_stable_session_id(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        task_id = "todo-ops-workflow-repair-5797cd5b-5539-4e95-8d58--1655223be5"
        session_id = module.build_task_session_id(task_id)

        self.assertLessEqual(len(session_id), 48)
        self.assertTrue(session_id.startswith("task-"))
        self.assertIn("5797cd5", session_id)
        self.assertRegex(session_id, r"-[0-9a-f]{10}$")
        self.assertEqual(session_id, module.build_task_session_id(task_id))

    def test_task_executor_quiet_when_no_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "run_id": "exec-1",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 1,
            "tasks_executed": 0,
            "tasks_skipped": 1,
            "tasks_failed": 0,
            "results": [
                {
                    "task_id": "cron:ops-github-web-evolution",
                    "status": "skipped",
                    "reason": "needs_clarification",
                }
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertEqual(output, "NO_REPLY")

    def test_task_executor_reports_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "run_id": "exec-2",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 0,
            "tasks_failed": 2,
            "results": [
                {"task_id": "todo-1", "status": "failed", "reason": "pre_stage_failed:model blocked"},
                {"task_id": "todo-2", "status": "failed", "reason": "report_failed:timeout"},
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertIn("任务执行异常", output)
        self.assertIn("todo-1", output)
        self.assertIn("report.json", output)

    def test_task_executor_retries_rate_limit_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        calls: list[int] = []

        def fake_call_agent(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return 1, "", "FailoverError: ⚠️ API rate limit reached. Please try again later."
            return 0, "{\"status\":\"passed\",\"solved\":true,\"resolution_summary\":\"ok\"}", ""

        with mock.patch.object(module, "call_agent", side_effect=fake_call_agent):
            with mock.patch.object(module.time, "sleep") as mocked_sleep:
                rc, out, err, attempts, details = module.call_agent_with_retries(
                    "openclaw",
                    "optimization-agent",
                    "prompt",
                    "task-1",
                    300,
                    True,
                    "xhigh",
                    max_retries=2,
                    retry_delay_sec=1,
                )

        self.assertEqual(rc, 0)
        self.assertEqual(attempts, 2)
        self.assertEqual(len(details), 2)
        self.assertTrue(details[0]["retryable"])
        mocked_sleep.assert_called_once_with(1)
        self.assertIn("\"passed\"", out)

    def test_task_executor_resolves_agent_model_and_thinking_from_policy(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_path = Path(tmpdir) / "policy.json"
            policy_path.write_text(
                """
{
  "primary_model": "openai-codex/gpt-5.4",
  "allowed_models": [
    "openai-codex/gpt-5.4",
    "openai-codex/gpt-5.3-codex",
    "glmcode/glm-4.7"
  ],
  "agent_model_overrides": {
    "optimization-agent": "openai-codex/gpt-5.3-codex",
    "ops-agent": "glmcode/glm-4.7"
  },
  "model_thinking_overrides": {
    "openai-codex/gpt-5.4": "xhigh",
    "openai-codex/gpt-5.3-codex": "xhigh",
    "glmcode/glm-4.7": "high"
  }
}
""".strip(),
                encoding="utf-8",
            )

            model_name, model_source, thinking = module.resolve_executor_selection(
                "auto",
                "optimization-agent",
                policy_path,
            )
            ops_model, ops_source, ops_thinking = module.resolve_executor_selection(
                "auto",
                "ops-agent",
                policy_path,
            )

        self.assertEqual(model_name, "openai-codex/gpt-5.3-codex")
        self.assertEqual(model_source, "policy-agent:optimization-agent")
        self.assertEqual(thinking, "xhigh")
        self.assertEqual(ops_model, "glmcode/glm-4.7")
        self.assertEqual(ops_source, "policy-agent:ops-agent")
        self.assertEqual(ops_thinking, "high")

    def test_task_executor_passes_thinking_flag_for_codex(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        with mock.patch.object(module.subprocess, "run") as mocked_run:
            mocked_run.return_value = SimpleNamespace(returncode=0, stdout='{"status":"passed"}', stderr="")
            rc, out, err = module.call_agent(
                "openclaw",
                "optimization-agent",
                "prompt",
                "task-1",
                300,
                True,
                "xhigh",
            )

        self.assertEqual(rc, 0)
        self.assertIn('"passed"', out)
        self.assertEqual(err, "")
        cmd = mocked_run.call_args.args[0]
        self.assertIn("--thinking", cmd)
        self.assertIn("xhigh", cmd)

    def test_task_executor_does_not_retry_non_retryable_failures(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )

        def fake_call_agent(*args, **kwargs):
            return 1, "", "permission denied"

        with mock.patch.object(module, "call_agent", side_effect=fake_call_agent):
            with mock.patch.object(module.time, "sleep") as mocked_sleep:
                rc, out, err, attempts, details = module.call_agent_with_retries(
                    "openclaw",
                    "optimization-agent",
                    "prompt",
                    "task-1",
                    300,
                    True,
                    "xhigh",
                    max_retries=2,
                    retry_delay_sec=1,
                )

        self.assertEqual(rc, 1)
        self.assertEqual(attempts, 1)
        self.assertEqual(len(details), 1)
        self.assertFalse(details[0]["retryable"])
        mocked_sleep.assert_not_called()
        self.assertEqual(out, "")
        self.assertEqual(err, "permission denied")

    def test_task_executor_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-2",
            "started_at": "2026-03-06T10:00:00+00:00",
            "executor_model": "kimicode/Doubao-Seed-2.0-Code",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 0,
            "tasks_failed": 2,
            "results": [
                {
                    "task_id": "todo-1",
                    "assignee": "backend-dev",
                    "status": "failed",
                    "reason": "pre_stage_failed:model blocked by policy: volcengine/kimi-k2.5",
                },
                {
                    "task_id": "todo-2",
                    "assignee": "backend-dev",
                    "status": "failed",
                    "reason": "report_failed:timeout",
                },
            ],
        }
        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")
        self.assertIn("任务执行异常", output)
        self.assertIn("模型被策略拦截", output)
        self.assertIn("volcengine/kimi-k2.5", output)
        self.assertIn("执行结果回写失败", output)
        self.assertNotIn("# task-executor", output)

    def test_task_executor_failure_output_includes_conclusion_reason_and_progress(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-3",
            "started_at": "2026-03-13T03:18:25+00:00",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 3,
            "tasks_executed": 3,
            "tasks_skipped": 0,
            "tasks_failed": 3,
            "results": [
                {
                    "task_id": "todo-1",
                    "assignee": "optimization-agent",
                    "status": "partial",
                    "reason": "partial",
                },
                {
                    "task_id": "todo-2",
                    "assignee": "optimization-agent",
                    "status": "partial",
                    "reason": "partial",
                },
                {
                    "task_id": "todo-3",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "reason": "failed",
                },
            ],
        }

        output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")

        self.assertIn("- 结论:", output)
        self.assertIn("3 个任务均未闭环", output)
        self.assertIn("- 原因解析:", output)
        self.assertIn("任务仅部分完成 2 个", output)
        self.assertIn("任务执行失败 1 个", output)
        self.assertIn("- 修复进展:", output)
        self.assertIn("已执行 3/3", output)
        self.assertIn("部分推进 2", output)
        self.assertIn("失败 1", output)

    def test_task_executor_duplicate_workflow_repair_alert_returns_no_reply(self):
        module = load_module(
            "task_executor_runner",
            "scripts/openclaw-ops/policy/task_executor_runner.py",
        )
        dedupe_module = load_module(
            "alert_dedupe",
            "scripts/openclaw-ops/policy/alert_dedupe.py",
        )
        summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-20260312_062434-432f88d7",
            "started_at": "2026-03-10T10:27:01+00:00",
            "executor_model": "auto(per-assignee)",
            "tasks_selected": 1,
            "tasks_executed": 1,
            "tasks_skipped": 0,
            "tasks_failed": 1,
            "results": [
                {
                    "task_id": "todo-ops-workflow-repair-f603d2ac-2dcf-4f7a-9efe--08a4d9787c",
                    "assignee": "optimization-agent",
                    "status": "failed",
                    "reason": "failed",
                    "task_type": "ops_workflow_repair",
                    "requirement": "workflow_job_id: f603d2ac-2dcf-4f7a-9efe-26f0e0f8d24e",
                    "context_payload": {
                        "operation_path": "ops_cron_runner::f603d2ac-2dcf-4f7a-9efe-26f0e0f8d24e"
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "alert-dedupe-state.json"
            state = dedupe_module.load_dedupe_state(state_path)
            signature = dedupe_module.build_workflow_failure_signature(
                ["f603d2ac-2dcf-4f7a-9efe"]
            )
            suppressed, _ = dedupe_module.check_and_record_signature(
                state,
                bucket="workflow_failure",
                signature=signature,
                now_text="2026-03-10T18:26:28+08:00",
                cooldown_minutes=60,
                meta={"source": "ops_cron_runner"},
            )
            self.assertFalse(suppressed)
            dedupe_module.save_dedupe_state(state_path, state)

            summary["alert_dedupe"] = module.apply_shared_alert_dedupe(
                summary,
                state_path,
                cooldown_minutes=60,
                now_text="2026-03-10T18:27:01+08:00",
            )
            output = module.build_chat_output(summary, Path("/tmp/report.json"), "error")

        self.assertTrue(summary["alert_dedupe"]["suppressed"])
        self.assertIn(
            "workflow_repeat_within_cooldown",
            summary["alert_dedupe"]["reason"],
        )
        self.assertEqual(output, "NO_REPLY")

    def test_web_collect_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", failed_count=0, changed_count=3))
        self.assertFalse(module.should_quiet("silent", "error", failed_count=1, changed_count=0))

    def test_web_collect_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        output = module.build_output(
            sender_identity="web-agent/web-intel-collect",
            task_id="cron:web-intel-collect",
            started_at="2026-03-06T10:00:00+00:00",
            total=5,
            scanned=3,
            changed=0,
            skipped=2,
            failed=1,
            report_file=Path("/tmp/web_collect.json"),
            changed_ids=[],
            failed_items=[
                {
                    "id": "openai-responses-doc",
                    "status": "failed",
                    "error": "http_error:429",
                    "status_code": 429,
                }
            ],
        )
        self.assertIn("网页情报采集异常", output)
        self.assertIn("openai-responses-doc", output)
        self.assertIn("429", output)
        self.assertEqual(output.splitlines()[0], "网页情报采集异常")
        self.assertIn("留痕编号", output)
        self.assertNotIn("/tmp/web_collect.json", output)
        self.assertNotIn("报告文件", output)

    def test_web_review_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", changed_count=2))
        self.assertFalse(module.should_quiet("chat", "error", changed_count=2))

    def test_web_review_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        output = module.build_failure_output(
            mode="optimization",
            sender_identity="optimization-agent/web-intel-review",
            task_id="cron:web-intel-review-optimization",
            started_at="2026-03-06T10:00:00+00:00",
            error_text="parsed_dir_missing:/home/ubuntu/.openclaw/web/parsed",
        )
        self.assertIn("网页情报复核异常", output)
        self.assertIn("optimization", output)
        self.assertIn("解析结果目录缺失", output)
        self.assertEqual(output.splitlines()[0], "网页情报复核异常")
        self.assertIn("留痕", output)
        self.assertNotIn("/home/ubuntu/.openclaw/web/parsed", output)
        self.assertNotIn("report_file", output)

    def test_web_review_output_hides_report_path(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        output = module.build_output(
            mode="project-doc",
            sender_identity="project-agent/web-doc-review",
            task_id="cron:web-intel-review-project-doc",
            started_at="2026-03-06T10:00:00+00:00",
            scanned=8,
            reviewed=4,
            changed=2,
            report_file=Path("/tmp/web_review_report.json"),
            sample_items=[
                {
                    "id": "openai-docs",
                    "title": "OpenAI API Docs",
                }
            ],
        )
        self.assertEqual(output.splitlines()[0], "网页情报复核提醒")
        self.assertIn("留痕编号", output)
        self.assertIn("openai-docs", output)
        self.assertNotIn("/tmp/web_review_report.json", output)
        self.assertNotIn("报告文件", output)

    def test_web_review_extracts_new_information_and_updated_interfaces(self):
        module = load_module(
            "web_intel_review_runner",
            "scripts/openclaw-ops/web_intel_review_runner.py",
        )
        previous_text = "\n".join(
            [
                "Orders API",
                "GET /v1/orders",
                "Parameter: symbol",
                "Response field: price",
            ]
        )
        current_text = "\n".join(
            [
                "Orders API",
                "GET /v1/orders",
                "Parameter: symbol",
                "Parameter: recvWindow",
                "Response field: price",
                "POST /v1/orders",
                "New endpoint for batch create",
            ]
        )

        details = module.analyze_content_change(previous_text, current_text, mode="project-doc")

        self.assertIn("Parameter: recvWindow", details["new_information"])
        self.assertTrue(
            any(
                item["interface"] == "POST /v1/orders" and item["change_type"] == "新增接口"
                for item in details["updated_interfaces"]
            )
        )
        self.assertTrue(
            any(
                item["interface"] == "GET /v1/orders" and item["change_type"] == "接口说明更新"
                for item in details["updated_interfaces"]
            )
        )

        item = {
            "id": "orders-api",
            "title": "Orders API",
            "url": "https://example.com/orders",
            "parsed_file": "/tmp/orders.json",
            "signals": [],
            "new_information": details["new_information"],
            "updated_interfaces": details["updated_interfaces"],
        }
        rendered = "\n".join(module.render_review_item_summary(item))
        self.assertIn("新增信息", rendered)
        self.assertIn("Parameter: recvWindow", rendered)
        self.assertIn("接口更新", rendered)
        self.assertIn("新增接口: POST /v1/orders", rendered)
        self.assertIn("解析留痕编号", rendered)
        self.assertNotIn("/tmp/orders.json", rendered)
        self.assertNotIn("parsed_file:", rendered)

    def test_local_git_backup_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "local_git_backup_runner",
            "scripts/openclaw-ops/local_git_backup_runner.py",
        )
        output = module.build_chat_output(
            {
                "time": "2026-03-06T10:00:00+00:00",
                "task_id": "cron:ops-local-openclaw-git-backup",
                "repo": "/home/ubuntu/.openclaw",
                "initialized": False,
                "gitignore_updated": False,
                "committed": False,
                "commit_sha": "",
                "eligible_files": [],
                "skipped_files": [],
                "errors": ["git_commit_failed:permission denied"],
            },
            "errors-only",
        )
        self.assertEqual(output.splitlines()[0], "本地 Git 备份异常")
        self.assertIn("Git 提交失败", output)
        self.assertIn("permission denied", output)
        self.assertNotIn("# local-git-backup", output)

    def test_todo_patrol_stays_quiet_when_only_dispatched_tasks_changed(self):
        module = load_module(
            "todo_patrol",
            "scripts/openclaw-ops/todo_patrol.py",
        )
        output = module.format_dispatch_message(
            task="cron:todo-patrol",
            todo_file=Path("/tmp/TODO.md"),
            dispatched=[
                {
                    "task": {
                        "task_id": "todo-1",
                        "assignee": "backend-dev",
                        "priority": "medium",
                        "risk_level": "low",
                        "context_completeness": 100,
                    }
                }
            ],
            skipped_count=0,
            ops_incident_skipped_count=0,
            skip_ops_incidents=True,
            db_path=Path("/tmp/task_center.db"),
            state_file=Path("/tmp/todo_patrol_state.json"),
            dispatch_errors=[],
            planner_summary=None,
            output_mode="summary",
        )
        self.assertEqual(output, "NO_REPLY")

    def test_todo_patrol_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "todo_patrol",
            "scripts/openclaw-ops/todo_patrol.py",
        )
        output = module.format_dispatch_message(
            task="cron:todo-patrol",
            todo_file=Path("/tmp/TODO.md"),
            dispatched=[],
            skipped_count=0,
            ops_incident_skipped_count=0,
            skip_ops_incidents=True,
            db_path=Path("/tmp/task_center.db"),
            state_file=Path("/tmp/todo_patrol_state.json"),
            dispatch_errors=["planner_summary_failed:database locked"],
            planner_summary=None,
            output_mode="summary",
        )
        self.assertEqual(output.splitlines()[0], "任务巡检异常")
        self.assertIn("规划器摘要读取失败", output)
        self.assertIn("database locked", output)
        self.assertIn("留痕", output)
        self.assertNotIn("/tmp/TODO.md", output)
        self.assertNotIn("/tmp/task_center.db", output)
        self.assertNotIn("/tmp/todo_patrol_state.json", output)
        self.assertNotIn("# todo-patrol", output)
        self.assertNotIn("- error:", output)

    def test_todo_patrol_verbose_output_uses_human_card_without_machine_fields(self):
        module = load_module(
            "todo_patrol",
            "scripts/openclaw-ops/todo_patrol.py",
        )
        output = module.format_dispatch_message(
            task="cron:todo-patrol",
            todo_file=Path("/tmp/TODO.md"),
            dispatched=[
                {
                    "task": {
                        "task_id": "todo-1",
                        "assignee": "backend-dev",
                        "priority": "medium",
                        "risk_level": "low",
                        "status": "pending",
                        "retry_count": 0,
                        "failure_count": 0,
                        "request_source": "human",
                        "needs_clarification": False,
                        "context_completeness": 100,
                        "context_fields_missing": [],
                        "context_fields_recommended_missing": [],
                        "requirement": "统一群聊输出",
                        "result_output": "输出中文卡片",
                        "acceptance": "群聊消息不再显示文件路径",
                        "observable_outputs": "chat_output",
                        "acceptance_thresholds": "包含留痕编号",
                    },
                    "route": {"due_hours": 4, "due_at": "2026-03-12T00:00:00+08:00"},
                    "payload": {
                        "context_payload": {
                            "human_summary": "统一剩余入口输出样式",
                            "risk_points": ["路径直出"],
                            "information_flow": {
                                "assignment_packet": {
                                    "dependencies": ["chat_output"],
                                    "history_changes": ["daily_work_report"],
                                    "deliverables": ["中文通知卡片"],
                                }
                            },
                        }
                    },
                }
            ],
            skipped_count=0,
            ops_incident_skipped_count=0,
            skip_ops_incidents=True,
            db_path=Path("/tmp/task_center.db"),
            state_file=Path("/tmp/todo_patrol_state.json"),
            dispatch_errors=[],
            planner_summary={"task_count": 1, "resolved_task_count": 0, "failed_task_count": 0},
            output_mode="verbose",
        )
        self.assertEqual(output.splitlines()[0], "任务巡检摘要")
        self.assertIn("任务编号：cron:todo-patrol", output)
        self.assertIn("留痕", output)
        self.assertIn("todo-1", output)
        self.assertNotIn("sender_identity:", output)
        self.assertNotIn("todo_file:", output)
        self.assertNotIn("task_center_db:", output)
        self.assertNotIn("state_file:", output)
        self.assertNotIn("/tmp/TODO.md", output)

    def test_reviewer_context_gate_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        module.discover_git_repos = lambda _workspace: [Path("/tmp/repo-a")]
        module.ensure_project_context_gate = lambda _args, _mode, _repos: {
            "ok": False,
            "blocked": 1,
            "created": 0,
            "pending": 1,
            "ready": 0,
            "error": "task center unavailable",
            "items": [{"repo": "repo-a", "status": "blocked", "task_id": "ctx-1"}],
        }
        args = SimpleNamespace(
            workspace="/tmp",
            task_id="cron:reviewer-daily",
        )
        result = module.run_quality_scan(
            args,
            state={},
            normal_log_mode="silent",
            mode="daily_incremental",
            incremental_from_head=False,
            full_scan_skip_unchanged=False,
            run_fix_command=False,
        )
        self.assertTrue(result.notify)
        self.assertEqual(result.output.splitlines()[0], "代码审查巡检异常")
        self.assertIn("项目上下文门禁阻塞", result.output)
        self.assertIn("原因解析", result.output)
        self.assertIn("project-agent", result.output)
        self.assertIn("任务中心暂不可用", result.output)
        self.assertNotIn("# reviewer-cron/", result.output)

    def test_reviewer_main_output_hides_machine_fields(self):
        module = load_module(
            "reviewer_cron_runner",
            "scripts/openclaw-ops/reviewer_cron_runner.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            history_dir = Path(tmpdir) / "runs"
            module.run_mode = lambda _args, _state, _normal_log_mode: SimpleNamespace(
                notify=False,
                output="NO_REPLY",
                record={
                    "run_id": "run-test-1",
                    "run_duration_ms": 22,
                    "risk_reasons": ["project_context_gate_blocked"],
                },
            )
            module.emit_policy_observability = lambda _args, _result, _run_file: ({"errors": []}, {})
            argv_backup = list(sys.argv)
            sys.argv = [
                "reviewer_cron_runner.py",
                "--mode",
                "daily_incremental",
                "--task-id",
                "cron:reviewer-daily-incremental",
                "--state-file",
                str(state_file),
                "--history-dir",
                str(history_dir),
            ]
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    rc = module.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(rc, 0)
            output = stdout.getvalue()
        self.assertIn("代码审查巡检异常", output)
        self.assertIn("项目上下文门禁阻塞", output)
        self.assertNotIn("# reviewer-cron/", output)
        self.assertNotIn("exception_count", output)
        self.assertNotIn("- exception:", output)
        self.assertNotIn("evidence:", output)

    def test_project_index_command_omits_git_pull_by_default(self):
        module = load_module(
            "install_project_index_job",
            "scripts/openclaw-ops/install_project_index_job.py",
        )
        command = module.build_runner_command(
            maintainer_py="/home/ubuntu/.openclaw/ops/policy/project_index_maintainer.py",
            registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            task_id="cron:project-index-maintainer-30m",
            actor="project-agent",
            git_pull=False,
            disable_memory_index_on_change=True,
        )
        self.assertNotIn("--git-pull", command)
        self.assertIn("--disable-memory-index-on-change", command)

    def test_project_index_job_prompt_requires_single_exec_call(self):
        module = load_module(
            "install_project_index_job",
            "scripts/openclaw-ops/install_project_index_job.py",
        )
        jobs, _ = module.upsert_job(
            jobs=[],
            job_id="job-project-index",
            every_ms=1800000,
            maintainer_py="/home/ubuntu/.openclaw/ops/policy/project_index_maintainer.py",
            registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            task_id="cron:project-index-maintainer-30m",
            actor="project-agent",
            git_pull=False,
            disable_memory_index_on_change=True,
            channel="telegram",
            target="-1003333097130",
        )
        message = jobs[0]["payload"]["message"]
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll", message)
        self.assertIn("Never output sentences like 'Let's run ...'", message)

    def test_project_index_job_defaults_to_silent_delivery(self):
        module = load_module(
            "install_project_index_job",
            "scripts/openclaw-ops/install_project_index_job.py",
        )
        jobs, _ = module.upsert_job(
            jobs=[],
            job_id="job-project-index",
            every_ms=1800000,
            maintainer_py="/home/ubuntu/.openclaw/ops/policy/project_index_maintainer.py",
            registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            task_id="cron:project-index-maintainer-30m",
            actor="project-agent",
            git_pull=False,
            disable_memory_index_on_change=True,
            channel="telegram",
            target="-1003333097130",
        )
        self.assertEqual(jobs[0]["delivery"]["mode"], "none")
        self.assertNotIn("failureAlert", jobs[0])

    def test_reviewer_install_message_blocks_follow_up_chatter(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )
        message = module.build_message("python3 /tmp/reviewer_cron_runner.py --mode daily_incremental")
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll", message)
        self.assertIn("Never output sentences like 'Let's run ...'", message)

    def test_reviewer_jobs_default_to_silent_delivery(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )
        fresh = module.build_jobs(
            runner_py="/tmp/reviewer.py",
            workspace="/tmp/workspace",
            state_file="/tmp/state.json",
            history_dir="/tmp/history",
            tz_name="Asia/Shanghai",
            hourly_every_ms=3600000,
            daily_expr="0 4 * * *",
            bi_daily_expr="20 4 */2 * *",
            weekly_expr="40 4 * * 1",
            enable_hourly=True,
            enable_daily=True,
            enable_bi_daily=True,
            enable_weekly=True,
            normal_log_mode="silent",
            daily_fix_command="",
            hourly_git_fetch=True,
            hourly_check_pr=True,
            hourly_allow_merge=False,
            hourly_push_after_merge=False,
            hourly_merge_approval_file="",
            project_context_gate=True,
            project_context_db="/tmp/task_center.db",
            project_context_assignee="project-agent",
        )
        merged, _ = module.upsert_jobs(jobs=[], fresh_jobs=fresh, channel="telegram", target="-1003333097130")
        self.assertTrue(all(item["delivery"]["mode"] == "none" for item in merged[:4]))
        self.assertTrue(all(item["failureAlert"]["to"] == "-1003333097130" for item in merged[:4]))

    def test_reviewer_jobs_pin_stable_model_and_light_context(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )
        fresh = module.build_jobs(
            runner_py="/tmp/reviewer.py",
            workspace="/tmp/workspace",
            state_file="/tmp/state.json",
            history_dir="/tmp/history",
            tz_name="Asia/Shanghai",
            hourly_every_ms=3600000,
            daily_expr="0 4 * * *",
            bi_daily_expr="20 4 */2 * *",
            weekly_expr="40 4 * * 1",
            enable_hourly=True,
            enable_daily=True,
            enable_bi_daily=True,
            enable_weekly=True,
            normal_log_mode="silent",
            daily_fix_command="",
            hourly_git_fetch=True,
            hourly_check_pr=True,
            hourly_allow_merge=False,
            hourly_push_after_merge=False,
            hourly_merge_approval_file="",
            project_context_gate=True,
            project_context_db="/tmp/task_center.db",
            project_context_assignee="project-agent",
        )
        self.assertTrue(all(item["payload"]["model"] == "glmcode/glm-5" for item in fresh))
        self.assertTrue(all(item["payload"]["lightContext"] is True for item in fresh))

    def test_task_executor_message_uses_notify_on_error(self):
        module = load_module(
            "install_task_executor_job",
            "scripts/openclaw-ops/install_task_executor_job.py",
        )
        message = module.build_message(
            executor_py="/home/ubuntu/.openclaw/ops/policy/task_executor_runner.py",
            db_path="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            max_tasks=3,
            model="",
            actor="coordinator",
            planner_id="coordinator",
            openclaw_bin="openclaw",
            report_dir="/home/ubuntu/.openclaw/ops/task-center/executor-runs",
            local_agent=True,
            notify_on="error",
        )
        self.assertIn("--notify-on error", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll", message)
        self.assertNotIn("--emit-json", message)

    def test_cron_setup_hardens_project_index_without_git_pull(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        jobs = [
            {
                "id": "job-project-index",
                "name": "project_index_maintainer_30m",
                "enabled": True,
                "payload": {"kind": "agentTurn", "message": "old"},
            }
        ]
        result = module.harden_known_jobs(jobs, Path("/home/ubuntu/.openclaw"))
        self.assertEqual(result["status"]["project_index_maintainer_30m"], "hardened")
        self.assertNotIn("--git-pull", jobs[0]["payload"]["message"])

    def test_cron_setup_prompt_requires_single_exec_call(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        message = module.build_message("python3 /tmp/demo.py")
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll", message)

    def test_cron_setup_monitor_config_uses_home_defaults_when_runner_config_is_dict(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "cron-monitor-config.json"
            with mock.patch.object(module, "runner_default_config", return_value={}):
                cfg = module.ensure_monitor_config(config_file, overwrite=True, switches={})

        home = Path.home()
        self.assertEqual(
            cfg["runtime_monitor"]["project_registry"],
            str(home / ".openclaw" / "ops" / "task-center" / "project-registry.json"),
        )
        self.assertEqual(
            cfg["workflow_monitor"]["jobs_file"],
            str(home / ".openclaw" / "cron" / "jobs.json"),
        )

    def test_ops_cron_runner_invoke_policy_enforcer_retries_database_locked(self):
        module = load_module(
            "ops_cron_runner",
            "scripts/openclaw-ops/ops_cron_runner.py",
        )

        runs = [
            SimpleNamespace(returncode=1, stdout="", stderr="sqlite3.OperationalError: database is locked"),
            SimpleNamespace(returncode=0, stdout='{"ok": true, "log": {"id": 1}}', stderr=""),
        ]

        with mock.patch.object(module.subprocess, "run", side_effect=runs) as run_mock:
            with mock.patch.object(module.time, "sleep") as sleep_mock:
                ok, payload, err = module.invoke_policy_enforcer(Path("/tmp/task_center.db"), ["log-module"], timeout=25)

        self.assertTrue(ok)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(err, "")
        self.assertEqual(run_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_install_workflow_profile_task_executor_cmd_pins_error_only_notify(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_task_executor_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            every_ms=600000,
            max_tasks=3,
            model="auto",
            local_agent=True,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--notify-on error", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_project_index_cmd_disables_git_pull(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_project_index_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            project_registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            every_ms=1800000,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--no-git-pull", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_web_intel_cmd_uses_error_only_notify(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_install_web_intel_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            ops_home="/home/ubuntu/.openclaw/ops",
            openclaw_home="/home/ubuntu/.openclaw",
            project_registry="/home/ubuntu/.openclaw/ops/task-center/project-registry.json",
            collect_every_ms=3600000,
            opt_review_every_ms=14400000,
            project_review_every_ms=21600000,
            collect_min_interval_minutes=60,
            review_min_interval_minutes=180,
            channel="telegram",
            target="-1003333097130",
        )
        rendered = " ".join(cmd)
        self.assertIn("--collect-notify-on error", rendered)
        self.assertIn("--review-notify-on error", rendered)

    def test_install_workflow_profile_reviewer_fix_command_uses_policy_subdir(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            stdout = io.StringIO()
            argv = [
                "install_workflow_profile.py",
                "--profile",
                "core",
                "--jobs-file",
                str(tmp / ".openclaw" / "cron" / "jobs.json"),
                "--openclaw-home",
                str(tmp / ".openclaw"),
                "--workflow-repo-path",
                str(tmp / "workflow-repo"),
                "--project-registry",
                str(tmp / ".openclaw" / "ops" / "task-center" / "project-registry.json"),
                "--task-db",
                str(tmp / ".openclaw" / "ops" / "task-center" / "task_center.db"),
                "--dry-run",
                "--no-sync-overlay-config",
                "--no-ensure-runtime-skills",
                "--no-normalize-openclaw-paths",
                "--no-recover-stale-cron-running-state",
            ]
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(stdout):
                    module.main()

        output = stdout.getvalue().replace("\\", "/")
        self.assertIn("/ops/policy/policy_enforcer.py next-todo --limit 5", output)
        self.assertNotIn("/ops/policy_enforcer.py next-todo --limit 5", output)

    def test_install_workflow_profile_ensure_runtime_skills_cmd_uses_manifest(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_ensure_runtime_skills_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            openclaw_home="/home/ubuntu/.openclaw",
            manifest_path="/repo/scripts/openclaw-ops/runtime-required-skills.json",
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("ensure_runtime_skills.py", rendered)
        self.assertIn("--manifest /repo/scripts/openclaw-ops/runtime-required-skills.json", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_sync_runtime_plugin_overrides_cmd_uses_openclaw_home(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_sync_runtime_plugin_overrides_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            openclaw_home="/home/ubuntu/.openclaw",
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("sync_runtime_plugin_overrides.py", rendered)
        self.assertIn("runtime-plugin-overrides", rendered)
        self.assertIn("--openclaw-home /home/ubuntu/.openclaw", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_normalize_runtime_binding_tasks_cmd_uses_task_db(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_normalize_runtime_binding_tasks_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            task_db="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("normalize_runtime_binding_tasks.py", rendered)
        self.assertIn("--db /home/ubuntu/.openclaw/ops/task-center/task_center.db", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_recover_stale_cron_running_state_cmd_uses_jobs_file(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_recover_stale_cron_running_state_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            stale_minutes=45,
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("recover_stale_cron_running_state.py", rendered)
        self.assertIn("--jobs-file /home/ubuntu/.openclaw/cron/jobs.json", rendered)
        self.assertIn("--stale-minutes 45", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_export_schedule_registry_cmd_uses_jobs_file_and_output(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_export_schedule_registry_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            jobs_file="/home/ubuntu/.openclaw/cron/jobs.json",
            mapping_file="/repo/cron/jobs_agent_mapping.md",
            output_file="/home/ubuntu/.openclaw/ops/workflow/schedule-registry.json",
            profile="all",
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("export_schedule_registry.py", rendered)
        self.assertIn("--jobs-file /home/ubuntu/.openclaw/cron/jobs.json", rendered)
        self.assertIn("--mapping-file /repo/cron/jobs_agent_mapping.md", rendered)
        self.assertIn("--output-file /home/ubuntu/.openclaw/ops/workflow/schedule-registry.json", rendered)
        self.assertIn("--profile all", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_reconcile_gateway_service_cmd_prefers_user(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        cmd = module.build_reconcile_gateway_service_cmd(
            python_bin="python3",
            here=Path("/repo/scripts/openclaw-ops"),
            prefer="user",
            dry_run=True,
        )
        rendered = " ".join(cmd)
        self.assertIn("gateway_service_manager.py", rendered)
        self.assertIn("--action restart", rendered)
        self.assertIn("--prefer user", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertIn("--emit-json", rendered)

    def test_install_workflow_profile_main_includes_recover_stale_cron_step(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        step_names: list[str] = []

        def fake_run_step(name: str, cmd: list[str], dry_run: bool):
            step_names.append(name)
            return {"step": name, "ok": True, "dry_run": dry_run, "returncode": 0}

        with mock.patch.object(
            sys,
            "argv",
            [
                "install_workflow_profile.py",
                "--profile",
                "core",
                "--dry-run",
                "--emit-json",
            ],
        ):
            with mock.patch.object(module, "sync_overlay_config", return_value={"step": module.OVERLAY_SYNC_STEP, "ok": True}):
                with mock.patch.object(module, "run_step", side_effect=fake_run_step):
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.main()

        self.assertIn("recover_stale_cron_running_state (stale runningAtMs cleanup)", step_names)

    def test_install_workflow_profile_main_includes_export_schedule_registry_step(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        step_names: list[str] = []

        def fake_run_step(name: str, cmd: list[str], dry_run: bool):
            step_names.append(name)
            return {"step": name, "ok": True, "dry_run": dry_run, "returncode": 0}

        with mock.patch.object(
            sys,
            "argv",
            [
                "install_workflow_profile.py",
                "--profile",
                "core",
                "--dry-run",
                "--emit-json",
            ],
        ):
            with mock.patch.object(module, "sync_overlay_config", return_value={"step": module.OVERLAY_SYNC_STEP, "ok": True}):
                with mock.patch.object(module, "run_step", side_effect=fake_run_step):
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.main()

        self.assertIn("export_schedule_registry (workflow registry snapshot)", step_names)

    def test_install_workflow_profile_main_includes_reconcile_gateway_service_step(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )
        step_names: list[str] = []

        def fake_run_step(name: str, cmd: list[str], dry_run: bool):
            step_names.append(name)
            return {"step": name, "ok": True, "dry_run": dry_run, "returncode": 0}

        with mock.patch.object(
            sys,
            "argv",
            [
                "install_workflow_profile.py",
                "--profile",
                "core",
                "--dry-run",
                "--emit-json",
            ],
        ):
            with mock.patch.object(module, "sync_overlay_config", return_value={"step": module.OVERLAY_SYNC_STEP, "ok": True}):
                with mock.patch.object(module, "run_step", side_effect=fake_run_step):
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.main()

        self.assertIn("reconcile_gateway_service (canonical gateway supervisor)", step_names)

    def test_sync_overlay_config_preserves_local_telegram_bot_token(self):
        module = load_module(
            "install_workflow_profile",
            "scripts/openclaw-ops/install_workflow_profile.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workflow_repo = root / "workflow-repo"
            (workflow_repo / "openclaw").mkdir(parents=True, exist_ok=True)
            (workflow_repo / "hooks").mkdir(parents=True, exist_ok=True)
            (workflow_repo / "skills").mkdir(parents=True, exist_ok=True)
            source = workflow_repo / "openclaw" / "openclaw.json"
            target = root / "openclaw-home" / "openclaw.json"
            target.parent.mkdir(parents=True, exist_ok=True)

            source.write_text(
                json.dumps(
                    {
                        "channels": {
                            "telegram": {
                                "enabled": True,
                                "botToken": "repo-unified-token",
                                "groupPolicy": "open",
                            }
                        },
                        "plugins": {"entries": {"telegram": {"enabled": True}}},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            target.write_text(
                json.dumps(
                    {
                        "channels": {
                            "telegram": {
                                "enabled": True,
                                "botToken": "local-server-token",
                                "allowFrom": ["1309629117"],
                            }
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = module.sync_overlay_config(
                source_path=str(source),
                target_path=str(target),
                vendor_runtime_root=str(root / "vendor"),
                boundary_doc_path=str(root / "boundary.md"),
                workflow_repo_path=str(workflow_repo),
                dry_run=False,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(
                result["merge_mode"],
                "repo-overlay-wins-with-local-telegram-credentials",
            )
            self.assertIn(
                "channels.telegram.botToken",
                result.get("preserved_local_config_keys", []),
            )

            merged = json.loads(target.read_text(encoding="utf-8"))
            telegram = merged["channels"]["telegram"]
            self.assertEqual(telegram["botToken"], "local-server-token")
            self.assertEqual(telegram["groupPolicy"], "open")
            self.assertEqual(telegram["allowFrom"], ["1309629117"])

    def test_todo_patrol_job_defaults_to_silent_delivery(self):
        module = load_module(
            "install_todo_patrol_job",
            "scripts/openclaw-ops/install_todo_patrol_job.py",
        )
        jobs, _ = module.upsert_job(
            jobs=[],
            job_id="job-todo",
            ops_script="/home/ubuntu/.openclaw/ops/todo_patrol.py",
            every_ms=900000,
            max_dispatch=5,
            default_request_source="human",
            ai_context_min_pct=100.0,
            skip_ops_incidents=True,
            output_mode="summary",
            channel="telegram",
            target="-1003333097130",
        )
        self.assertEqual(jobs[0]["delivery"]["mode"], "none")
        self.assertNotIn("failureAlert", jobs[0])

    def test_local_git_backup_job_defaults_to_silent_delivery(self):
        module = load_module(
            "install_local_openclaw_backup_job",
            "scripts/openclaw-ops/install_local_openclaw_backup_job.py",
        )
        jobs, _ = module.upsert_job(
            jobs=[],
            job_id="job-backup",
            every_ms=3600000,
            runner_py="/home/ubuntu/.openclaw/ops/local_git_backup_runner.py",
            openclaw_home="/home/ubuntu/.openclaw",
            task_id="cron:ops-local-openclaw-git-backup",
            notify_on="errors-only",
            list_changed_files=False,
            max_listed_files=20,
            channel="telegram",
            target="-1003333097130",
        )
        self.assertEqual(jobs[0]["delivery"]["mode"], "none")
        self.assertEqual(jobs[0]["failureAlert"]["after"], 1)
        self.assertEqual(jobs[0]["payload"]["model"], "glmcode/glm-4.7")
        self.assertTrue(jobs[0]["payload"]["lightContext"])

    def test_daily_work_report_job_announces_and_carries_todo_files(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        job = module.build_daily_work_job(
            script_py="/home/ubuntu/.openclaw/ops/daily_work_report.py",
            db_file="/home/ubuntu/.openclaw/ops/task-center/task_center.db",
            state_file="/home/ubuntu/.openclaw/ops/daily-work/state.json",
            report_dir="/home/ubuntu/.openclaw/ops/daily-work/reports",
            expr="15 0 * * *",
            tz_name="Asia/Shanghai",
            log_mode="silent",
            webhook_env="DINGTALK_WEBHOOK_URL",
            secret_env="DINGTALK_SECRET",
            env_file="/home/ubuntu/.openclaw/ops/runtime.env",
            todo_files=[
                "/home/ubuntu/openclaw-hardflow-backup-20260302/todo.md",
                "/home/ubuntu/openclaw-hardflow-backup-20260302/TODO.md",
            ],
        )
        self.assertEqual(job["delivery"]["mode"], "announce")
        message = job["payload"]["message"]
        self.assertIn("--todo-file /home/ubuntu/openclaw-hardflow-backup-20260302/todo.md", message)
        self.assertIn("--todo-file /home/ubuntu/openclaw-hardflow-backup-20260302/TODO.md", message)
        self.assertEqual(job["payload"]["model"], "glmcode/glm-4.7")
        self.assertTrue(job["payload"]["lightContext"])

    def test_web_intel_jobs_default_to_silent_delivery(self):
        module = load_module(
            "install_web_intel_jobs",
            "scripts/openclaw-ops/install_web_intel_jobs.py",
        )
        job = module.make_job(
            job_id="web-intel-job",
            agent_id="web-agent",
            name="web_intel_collect_hourly",
            description="desc",
            every_ms=3600000,
            message="run",
            timeout_seconds=300,
            old=None,
            channel="telegram",
            target="-1003333097130",
        )
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertNotIn("failureAlert", job)

    def test_cron_setup_maintenance_jobs_disable_failure_alert_by_default(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        conversation_job = module.build_conversation_evolution_job(
            script_py="/tmp/conversation.py",
            db_file="/tmp/task_center.db",
            openclaw_home="/tmp/openclaw",
            state_file="/tmp/state.json",
            report_dir="/tmp/reports",
            every_ms=21600000,
            log_mode="silent",
            lookback_hours=24,
            min_interval_minutes=180,
            max_files=120,
            max_evidence_per_candidate=4,
            min_evidence_lines=3,
            min_unique_files=2,
            min_quality_score=60,
            recent_dedupe_days=30,
            max_tasks_per_run=2,
            schedule_gap_minutes=120,
            assignee="optimization-agent",
        )
        governance_job = module.build_governance_evolution_job(
            script_py="/tmp/governance.py",
            db_file="/tmp/task_center.db",
            state_file="/tmp/state.json",
            report_dir="/tmp/reports",
            repo_path="/tmp/repo",
            openclaw_config="/tmp/openclaw.json",
            project_registry="/tmp/project-registry.json",
            repo_id="repo-id",
            repo_name="repo-name",
            auto_git_update=False,
            git_update_strategy="fetch",
            git_fetch_timeout=120,
            every_ms=21600000,
            log_mode="silent",
            max_files=120,
            min_interval_minutes=180,
            task_clarity="ambiguous",
            project_context_gate=True,
            project_context_assignee="project-agent",
            create_review_task=True,
            auto_pr=False,
            pr_base="main",
            reviewer_gh_user="",
            push_before_pr=False,
        )
        github_job = module.build_github_web_evolution_job(
            script_py="/tmp/github.py",
            db_file="/tmp/task_center.db",
            openclaw_home="/tmp/openclaw",
            web_root="/tmp/openclaw/web",
            state_file="/tmp/state.json",
            report_dir="/tmp/reports",
            every_ms=43200000,
            log_mode="silent",
            min_interval_minutes=360,
            max_queries=4,
            max_repos_per_query=8,
            max_total_repos=16,
            min_stars=50,
            min_quality_score=60,
            min_new_or_updated=1,
            recent_dedupe_days=30,
            max_tasks_per_run=2,
            schedule_gap_minutes=120,
            assignee="optimization-agent",
            github_token_env="GITHUB_TOKEN",
        )
        git_sync_job = module.build_git_sync_job(
            script_py="/tmp/git_sync.py",
            repo_path="/tmp/repo",
            every_ms=21600000,
            log_mode="silent",
            remote="origin",
            branch="main",
            max_files=120,
            commit_prefix="chore(sync): update",
            auto_pull=True,
            push=True,
            include_prefixes=[],
            exclude_prefixes=[],
            required_remote_urls=[],
            notify_on="error",
        )
        auto_update_job = module.build_auto_update_install_job(
            script_py="/tmp/auto_update.py",
            repo_path="/tmp/repo",
            every_ms=3600000,
            log_mode="silent",
            remote="origin",
            branch="main",
            install_cmd="python3 install.py",
            install_on_no_change=False,
            git_timeout=120,
            install_timeout=900,
            report_dir="/tmp/reports",
            required_remote_urls=[],
            notify_on="error",
        )

        for job in [conversation_job, governance_job, github_job, git_sync_job, auto_update_job]:
            self.assertEqual(job["delivery"]["mode"], "none")
            self.assertNotIn("failureAlert", job)

    def test_ops_cron_runner_ignores_low_value_maintenance_job_failures(self):
        module = load_module(
            "ops_cron_runner",
            "scripts/openclaw-ops/ops_cron_runner.py",
        )
        cfg = module.default_config()
        state = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_file = Path(tmpdir) / "jobs.json"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "job-ignored",
                                "name": "web_intel_collect_hourly",
                                "agentId": "web-agent",
                                "enabled": True,
                                "state": {
                                    "lastStatus": "error",
                                    "consecutiveErrors": 2,
                                    "lastRunAtMs": 1710111111000,
                                    "lastError": "cron: job execution timed out",
                                },
                            },
                            {
                                "id": "job-important",
                                "name": "reviewer_weekly_structure_review",
                                "agentId": "reviewer",
                                "enabled": True,
                                "state": {
                                    "lastStatus": "error",
                                    "consecutiveErrors": 1,
                                    "lastRunAtMs": 1710112222000,
                                    "lastError": "cron: job execution timed out",
                                },
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            cfg["workflow_monitor"]["jobs_file"] = str(jobs_file)
            summary = module.collect_workflow_health(cfg, state)

        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["ignored_failed_count"], 1)
        self.assertEqual(len(summary["failed_jobs"]), 1)
        self.assertEqual(summary["failed_jobs"][0]["name"], "reviewer_weekly_structure_review")

    def test_install_workflow_profile_dry_run_uses_hardened_runtime_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            openclaw_home = tmp / "openclaw-home"
            workflow_repo = tmp / "workflow-repo"
            openclaw_home.mkdir(parents=True)
            workflow_repo.mkdir(parents=True)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/openclaw-ops/install_workflow_profile.py"),
                    "--profile",
                    "all",
                    "--jobs-file",
                    str(tmp / "jobs.json"),
                    "--openclaw-home",
                    str(openclaw_home),
                    "--workflow-repo-path",
                    str(workflow_repo),
                    "--project-registry",
                    str(tmp / "project-registry.json"),
                    "--task-db",
                    str(tmp / "task_center.db"),
                    "--channel",
                    "telegram",
                    "--to",
                    "-1003333097130",
                    "--install-web-intel-jobs",
                    "--no-sync-overlay-config",
                    "--no-normalize-openclaw-paths",
                    "--dry-run",
                    "--emit-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=ROOT,
            )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("--notify-on error", proc.stdout)
        self.assertIn("--no-git-pull", proc.stdout)
        self.assertIn("--collect-notify-on error", proc.stdout)
        self.assertIn("--review-notify-on error", proc.stdout)
        self.assertIn("--daily-work-todo-file", proc.stdout)
        self.assertIn(str(workflow_repo / "todo.md"), proc.stdout)
        self.assertIn(str(workflow_repo / "TODO.md"), proc.stdout)


if __name__ == "__main__":
    unittest.main()

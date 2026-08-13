import json
import contextlib
import io
import importlib.util
import json
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
            "skills/library/openclaw-workflow-manager/scripts/switch_model_tier.py",
        )
        profiles = module.load_profiles(
            ROOT / "skills/library/openclaw-workflow-manager/scripts/model_tier_profiles.json"
        )
        tier = module.resolve_tier("high_doubao", profiles)
        profile = module.ensure_profile(profiles["tiers"][tier], tier)

        self.assertEqual(tier, "high_doubao")
        self.assertEqual(profile["primary_model"], "kimicode/doubao-seed-2.0-pro")
        self.assertEqual(profile["agent_model_overrides"]["optimization-agent"], "openai-codex/gpt-5.5")
        self.assertEqual(profile["agent_model_overrides"]["backend-dev"], "openai-codex/gpt-5.5")
        self.assertEqual(profile["agent_model_overrides"]["ops-agent"], "openai-codex/gpt-5.5")
        self.assertEqual(profile["agent_model_overrides"]["web-agent"], "openai-codex/gpt-5.5")
        self.assertEqual(profile["model_thinking_overrides"]["kimicode/doubao-seed-2.0-pro"], "high")
        self.assertEqual(profile["model_thinking_overrides"]["openai-codex/gpt-5.3-codex"], "xhigh")

    def test_ops_cron_runner_creates_follow_up_task_for_failed_workflow(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
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
        self.assertEqual(summary["tasks"][0]["assignee"], "ops-agent")
        self.assertEqual(len(invoked), 1)
        args = invoked[0]
        self.assertIn("create-task", args)
        self.assertIn("ops_workflow_repair", args)
        self.assertIn("jobs", args)
        self.assertIn("ops-agent", args)
        self.assertIn("--required-capabilities", args)
        self.assertEqual(
            args[args.index("--required-capabilities") + 1],
            "skill_backed,task_execution",
        )
        self.assertIn("--allowed-agents", args)
        self.assertEqual(args[args.index("--allowed-agents") + 1], "ops-agent")
        self.assertIn("false", args)
        self.assertIn("true", args)
        self.assertEqual(repeated["created_count"], 0)
        self.assertEqual(repeated["existing_count"], 0)
        self.assertEqual(len(invoked), 1)

    def test_ops_cron_runner_marks_existing_follow_up_task_without_error(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
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
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
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
        self.assertIn("OpenClaw 本地备份（1小时）", output)

    def test_task_executor_skips_ops_runtime_cron_binding_tasks(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
        self.assertIn("首次发现 1 个未闭环任务", output)
        self.assertIn("执行结论1：待补充上下文", output)

    def test_task_executor_reports_failures(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
        self.assertIn("任务执行器（10分钟）", output.splitlines()[0])
        self.assertIn("首次发现 2 个未闭环任务", output)
        self.assertIn("失败原因1：执行前检查失败", output)
        self.assertIn("失败原因2：执行结果回写失败", output)
        self.assertNotIn("todo-1", output)
        self.assertNotIn("report.json", output)

    def test_task_executor_retries_rate_limit_failures(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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
        self.assertIn("任务执行器（10分钟）", output.splitlines()[0])
        self.assertIn("执行前检查失败：模型 volcengine/kimi-k2.5 被策略禁止", output)
        self.assertIn("volcengine/kimi-k2.5", output)
        self.assertIn("执行结果回写失败", output)
        self.assertNotIn("# task-executor", output)

    def test_task_executor_failure_output_includes_conclusion_reason_and_progress(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
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

        self.assertIn("任务执行器（10分钟）", output.splitlines()[0])
        self.assertIn("首次发现 3 个未闭环任务。", output)
        self.assertIn("本轮变化：新增 3 个，变化 0 个，已闭环 0 个，仍未闭环 3 个。", output)
        self.assertIn("事项1：未命名任务", output)
        self.assertIn("执行结论1：执行失败", output)
        self.assertIn("失败原因1：任务执行失败", output)
        self.assertIn("需要协助2：partial", output)

    def test_task_executor_duplicate_workflow_repair_alert_returns_no_reply(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
        )
        dedupe_module = load_module(
            "alert_dedupe",
            "skills/library/control-plane-ops/scripts/policy/alert_dedupe.py",
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

    def test_task_executor_incremental_notify_suppresses_unchanged_open_items(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
        )

        summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-20260317_054211-697478b5",
            "started_at": "2026-03-17T05:42:11+00:00",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 2,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "project-agent",
                    "stage": "plan",
                    "status": "failed",
                    "reason": "preflight_strict_blocked",
                    "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                    "preflight_reassign": {
                        "recommended_agents": ["project-agent"],
                    },
                },
                {
                    "task_id": "todo-risk-2",
                    "assignee": "optimization-agent",
                    "stage": "implement",
                    "status": "failed",
                    "reason": "needs_clarification",
                    "task_requirement": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "alert-dedupe-state.json"
            first = module.apply_task_executor_incremental_notify(
                summary,
                state_path,
                now_text="2026-03-17T05:42:11+00:00",
            )
            second = module.apply_task_executor_incremental_notify(
                dict(summary),
                state_path,
                now_text="2026-03-17T05:53:09+00:00",
            )

        self.assertFalse(first["suppressed"])
        self.assertEqual(first["mode"], "initial")
        self.assertEqual(first["new_count"], 2)
        self.assertEqual(first["changed_count"], 0)
        self.assertTrue(second["suppressed"])
        self.assertEqual(second["mode"], "no_change")
        self.assertEqual(second["open_count"], 2)

    def test_task_executor_incremental_notify_reports_only_changed_items(self):
        module = load_module(
            "task_executor_runner",
            "skills/library/control-plane-ops/scripts/policy/task_executor_runner.py",
        )

        first_summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-20260317_054211-697478b5",
            "started_at": "2026-03-17T05:42:11+00:00",
            "tasks_selected": 2,
            "tasks_executed": 0,
            "tasks_skipped": 2,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "project-agent",
                    "stage": "plan",
                    "status": "failed",
                    "reason": "preflight_strict_blocked",
                    "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                    "preflight_reassign": {
                        "recommended_agents": ["project-agent"],
                    },
                },
                {
                    "task_id": "todo-risk-2",
                    "assignee": "optimization-agent",
                    "stage": "implement",
                    "status": "failed",
                    "reason": "needs_clarification",
                    "task_requirement": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                },
            ],
        }
        second_summary = {
            "trigger_task": "cron:task-executor",
            "run_id": "exec-20260317_060324-08861d20",
            "started_at": "2026-03-17T06:03:24+00:00",
            "tasks_selected": 2,
            "tasks_executed": 1,
            "tasks_skipped": 1,
            "results": [
                {
                    "task_id": "todo-risk-1",
                    "assignee": "project-agent",
                    "stage": "plan",
                    "status": "failed",
                    "reason": "waiting_human_confirm",
                    "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                },
                {
                    "task_id": "todo-risk-2",
                    "assignee": "optimization-agent",
                    "stage": "implement",
                    "status": "passed",
                    "report_status": "passed",
                    "reason": "solved",
                    "task_requirement": "梳理任务执行器的人类摘要模板，避免重复刷屏。",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "alert-dedupe-state.json"
            module.apply_task_executor_incremental_notify(
                first_summary,
                state_path,
                now_text="2026-03-17T05:42:11+00:00",
            )
            change = module.apply_task_executor_incremental_notify(
                second_summary,
                state_path,
                now_text="2026-03-17T06:03:24+00:00",
            )

        self.assertFalse(change["suppressed"])
        self.assertEqual(change["mode"], "delta")
        self.assertEqual(change["new_count"], 0)
        self.assertEqual(change["changed_count"], 1)
        self.assertEqual(change["resolved_count"], 1)
        self.assertEqual(change["focus_task_ids"], ["todo-risk-1"])

    def test_web_collect_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", failed_count=0, changed_count=3))
        self.assertFalse(module.should_quiet("silent", "error", failed_count=1, changed_count=0))

    def test_web_collect_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
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
        self.assertIn("网页情报采集异常", output.splitlines()[0])
        self.assertIn("留痕编号", output)
        self.assertNotIn("/tmp/web_collect.json", output)
        self.assertNotIn("报告文件", output)

    def test_web_review_error_only_mode_stays_quiet_on_changes(self):
        module = load_module(
            "web_intel_review_runner",
            "skills/library/web-intelligence/scripts/web_intel_review_runner.py",
        )
        self.assertTrue(module.should_quiet("silent", "error", changed_count=2))
        self.assertFalse(module.should_quiet("chat", "error", changed_count=2))

    def test_web_review_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "web_intel_review_runner",
            "skills/library/web-intelligence/scripts/web_intel_review_runner.py",
        )
        output = module.build_failure_output(
            mode="optimization",
            sender_identity="optimization-agent/web-intel-review",
            task_id="cron:web-intel-review-optimization",
            started_at="2026-03-06T10:00:00+00:00",
            error_text="parsed_dir_missing:/home/runtime-user/.openclaw/web/parsed",
        )
        self.assertIn("网页情报复核异常", output)
        self.assertIn("optimization", output)
        self.assertIn("解析结果目录缺失", output)
        self.assertIn("网页情报复核异常", output.splitlines()[0])
        self.assertIn("留痕", output)
        self.assertNotIn("/home/runtime-user/.openclaw/web/parsed", output)
        self.assertNotIn("report_file", output)

    def test_web_review_output_hides_report_path(self):
        module = load_module(
            "web_intel_review_runner",
            "skills/library/web-intelligence/scripts/web_intel_review_runner.py",
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
        self.assertIn("网页情报复核提醒", output.splitlines()[0])
        self.assertIn("留痕编号", output)
        self.assertIn("openai-docs", output)
        self.assertNotIn("/tmp/web_review_report.json", output)
        self.assertNotIn("报告文件", output)

    def test_web_review_extracts_new_information_and_updated_interfaces(self):
        module = load_module(
            "web_intel_review_runner",
            "skills/library/web-intelligence/scripts/web_intel_review_runner.py",
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
            "skills/library/git-sync/scripts/local_git_backup_runner.py",
        )
        output = module.build_chat_output(
            {
                "time": "2026-03-06T10:00:00+00:00",
                "task_id": "cron:ops-local-openclaw-git-backup",
                "repo": "/home/runtime-user/.openclaw",
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
            "skills/library/todo-patrol/scripts/todo_patrol.py",
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
            "skills/library/todo-patrol/scripts/todo_patrol.py",
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
        self.assertIn("任务巡检异常", output.splitlines()[0])
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
            "skills/library/todo-patrol/scripts/todo_patrol.py",
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
        self.assertIn("任务巡检摘要", output.splitlines()[0])
        self.assertIn("任务编号：cron:todo-patrol", output)
        self.assertIn("留痕", output)
        self.assertIn("任务1：统一剩余入口输出样式", output)
        self.assertIn("要求1：统一群聊输出", output)
        self.assertIn("状态1：已派发给 backend-dev", output)
        self.assertIn("值得做1：", output)
        self.assertNotIn("todo-1", output)
        self.assertNotIn("sender_identity:", output)
        self.assertNotIn("todo_file:", output)
        self.assertNotIn("task_center_db:", output)
        self.assertNotIn("state_file:", output)
        self.assertNotIn("/tmp/TODO.md", output)

    def test_reviewer_context_gate_failure_output_is_human_friendly_chinese(self):
        module = load_module(
            "reviewer_cron_runner",
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
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
        self.assertIn("代码审查巡检异常", result.output.splitlines()[0])
        self.assertIn("项目上下文门禁阻塞", result.output)
        self.assertIn("原因解析", result.output)
        self.assertIn("project-agent", result.output)
        self.assertIn("任务中心暂不可用", result.output)
        self.assertNotIn("# reviewer-cron/", result.output)

    def test_reviewer_main_output_hides_machine_fields(self):
        module = load_module(
            "reviewer_cron_runner",
            "skills/library/receiving-code-review/scripts/reviewer_cron_runner.py",
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












    def test_ops_cron_runner_invoke_policy_enforcer_retries_database_locked(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
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























    def test_ops_cron_runner_ignores_low_value_maintenance_job_failures(self):
        module = load_module(
            "ops_cron_runner",
            "skills/library/control-plane-ops/scripts/ops_cron_runner.py",
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






if __name__ == "__main__":
    unittest.main()

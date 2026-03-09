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
        self.assertNotIn("# todo-patrol", output)
        self.assertNotIn("- error:", output)

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
        self.assertIn("task center unavailable", result.output)
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
        )
        self.assertNotIn("--git-pull", command)

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
            channel="telegram",
            target="-1003333097130",
        )
        message = jobs[0]["payload"]["message"]
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll or process log", message)
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
            channel="telegram",
            target="-1003333097130",
        )
        self.assertEqual(jobs[0]["delivery"]["mode"], "none")
        self.assertEqual(jobs[0]["failureAlert"]["channel"], "telegram")

    def test_reviewer_install_message_blocks_follow_up_chatter(self):
        module = load_module(
            "install_reviewer_scan_jobs",
            "scripts/openclaw-ops/install_reviewer_scan_jobs.py",
        )
        message = module.build_message("python3 /tmp/reviewer_cron_runner.py --mode daily_incremental")
        self.assertIn("first assistant turn MUST contain exactly one exec tool call", message)
        self.assertIn("Command still running", message)
        self.assertIn("process poll or process log", message)
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
        self.assertIn("process poll or process log", message)
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
        self.assertIn("process poll or process log", message)

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
        self.assertEqual(jobs[0]["failureAlert"]["to"], "-1003333097130")

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
        self.assertEqual(job["failureAlert"]["channel"], "telegram")

    def test_cron_setup_internal_jobs_default_to_silent_delivery(self):
        module = load_module(
            "cron_setup",
            "scripts/openclaw-ops/cron_setup.py",
        )
        job = module.build_governance_evolution_job(
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
        self.assertEqual(job["delivery"]["mode"], "none")
        self.assertEqual(job["failureAlert"]["cooldownMs"], 1800000)

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


if __name__ == "__main__":
    unittest.main()

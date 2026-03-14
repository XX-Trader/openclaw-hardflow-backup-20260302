import io
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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


class DailyTodoDigestOutputTests(unittest.TestCase):
    def test_build_chat_output_returns_no_reply_when_no_updates_or_exceptions(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )

        output = module.build_chat_output(
            sender_identity="ops-agent/daily-todo-digest",
            task_id="cron:ops-daily-todo-digest",
            run_time="2026-03-11T08:00:00+08:00",
            run_id="digest-run-000",
            new_todo=[],
            new_done=[],
            planner_summary=None,
            exception_reasons=[],
            max_notify_items=5,
        )

        self.assertEqual(output, "NO_REPLY")

    def test_build_chat_output_uses_chinese_card_without_paths(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )

        output = module.build_chat_output(
            sender_identity="ops-agent/daily-todo-digest",
            task_id="cron:ops-daily-todo-digest",
            run_time="2026-03-11T08:00:00+08:00",
            run_id="digest-run-001",
            new_todo=[
                {
                    "task_id": "todo-1",
                    "reason": "收敛群聊输出样式",
                    "requirement": "统一群聊卡片中给人看的任务字段，只保留任务、要求、状态和值得做。",
                    "acceptance": "人工看到摘要后，可以直接判断先做什么，不需要再打开任务中心。",
                    "priority": "high",
                    "risk_level": "high",
                    "assignee": "ops-agent",
                    "status": "pending",
                }
            ],
            new_done=[
                {
                    "task_id": "done-1",
                    "reason": "清理旧英文标题",
                    "priority": "medium",
                    "risk_level": "low",
                    "assignee": "ops-agent",
                }
            ],
            planner_summary={
                "task_count": 3,
                "resolved_task_count": 2,
                "failed_task_count": 1,
            },
            exception_reasons=[],
            max_notify_items=5,
        )

        self.assertIn("每日任务摘要", output.splitlines()[0])
        self.assertIn("人工判断：", output)
        self.assertIn("任务1：收敛群聊输出样式", output)
        self.assertIn("要求1：统一群聊卡片中给人看的任务字段", output)
        self.assertIn("状态1：任务中心待处理", output)
        self.assertIn("值得做1：", output)
        self.assertIn("完成1：清理旧英文标题", output)
        self.assertIn("近24小时处理", output)
        self.assertIn("留痕编号：digest-run-001", output)
        self.assertNotIn("Daily TODO Digest", output)
        self.assertNotIn("evidence:", output)
        self.assertNotIn("/tmp/", output)
        self.assertNotIn(".json", output)

    def test_build_chat_output_shows_failure_reason_and_execution_metrics_for_failed_todo(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )

        output = module.build_chat_output(
            sender_identity="ops-agent/daily-todo-digest",
            task_id="cron:ops-daily-todo-digest",
            run_time="2026-03-11T08:00:00+08:00",
            run_id="digest-run-003",
            new_todo=[
                {
                    "task_id": "todo-2",
                    "reason": "恢复钉钉日报发送",
                    "requirement": "恢复钉钉日报发送，并确保失败任务展示完整执行信息。",
                    "priority": "high",
                    "risk_level": "high",
                    "assignee": "ops-agent",
                    "status": "failed",
                    "failure_count": 2,
                    "retry_count": 1,
                    "latest_report": {
                        "failed_items": ["dingtalk webhook request timeout"],
                        "failure_count": 2,
                        "duration_ms": 14500,
                        "model_id": "openai-codex/gpt-5",
                        "input_tokens": 1200,
                        "output_tokens": 2000,
                        "total_tokens": 3200,
                        "cost_estimate": 0.01234,
                    },
                }
            ],
            new_done=[],
            planner_summary=None,
            exception_reasons=["webhook_missing:DINGTALK_WEBHOOK_URL"],
            max_notify_items=5,
        )

        self.assertIn("失败信息1：原因=dingtalk webhook request timeout；失败次数=2次；最近耗时=14.5秒；已重试=1次", output)
        self.assertIn("执行概况1：模型=openai-codex · gpt-5；tokens=总=3200（输入=1200，输出=2000）；成本≈$0.012340", output)
        self.assertIn("异常1：钉钉 Webhook 未配置：DINGTALK_WEBHOOK_URL", output)

    def test_build_chat_output_emits_exception_card_when_only_exceptions(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )

        output = module.build_chat_output(
            sender_identity="ops-agent/daily-todo-digest",
            task_id="cron:ops-daily-todo-digest",
            run_time="2026-03-11T08:00:00+08:00",
            run_id="digest-run-002",
            new_todo=[],
            new_done=[],
            planner_summary=None,
            exception_reasons=["policy_enforcer_failed:/tmp/runtime-error.json"],
            max_notify_items=5,
        )

        self.assertIn("每日任务摘要异常", output.splitlines()[0])
        self.assertIn("发现 1 个运行异常", output)
        self.assertIn("运行详情已写入内部留痕", output)
        self.assertIn("留痕编号：digest-run-002", output)
        self.assertNotIn("/tmp/runtime-error.json", output)
        self.assertNotIn(".json", output)

    def test_main_emits_exception_card_when_only_runtime_errors_exist(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )
        invoked: list[list[str]] = []

        def fake_invoke(_db_path, args, timeout=30):
            invoked.append(list(args))
            if args and args[0] == "planner-summary":
                return False, {}, "task center unavailable"
            if args and args[0] in {"log-module", "log-communication", "report-agent-result"}:
                return True, {"ok": True}, ""
            return True, {"ok": True}, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            state_path = tmp / "state.json"
            report_dir = tmp / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            argv = [
                "daily_todo_digest.py",
                "--db",
                str(db_path),
                "--state-file",
                str(state_path),
                "--report-dir",
                str(report_dir),
                "--task-id",
                "cron:ops-daily-todo-digest",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(module, "load_tasks", return_value=[]):
                    with mock.patch.object(
                        module,
                        "ensure_task_binding",
                        return_value=("cron:ops-daily-todo-digest", ""),
                    ):
                        with mock.patch.object(module, "invoke_policy_enforcer", side_effect=fake_invoke):
                            with redirect_stdout(stdout):
                                rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertTrue(payload["notify"])
        self.assertIn("每日任务摘要异常", payload["output"].splitlines()[0])
        self.assertIn("留痕编号", payload["output"])
        self.assertNotIn("Daily TODO Digest", payload["output"])
        self.assertNotIn("evidence:", payload["output"])
        self.assertNotIn(".json", payload["output"])
        self.assertTrue(any(args and args[0] == "planner-summary" for args in invoked))


    def test_main_ignores_runtime_binding_tasks_in_pending_and_done_lists(self):
        module = load_module(
            "daily_todo_digest",
            "scripts/openclaw-ops/daily_todo_digest.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "task_center.db"
            db_path.write_text("", encoding="utf-8")
            state_path = tmp / "state.json"
            report_dir = tmp / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            argv = [
                "daily_todo_digest.py",
                "--db",
                str(db_path),
                "--state-file",
                str(state_path),
                "--report-dir",
                str(report_dir),
                "--task-id",
                "cron:ops-daily-todo-digest",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(
                    module,
                    "load_tasks",
                    return_value=[
                        {
                            "task_id": "cron:ops-conversation-evolution",
                            "task_type": "ops_runtime_cron",
                            "reason": "[CRON_RUNTIME] bind cron:ops-conversation-evolution",
                            "status": "pending",
                            "updated_at": "2026-03-12T23:00:00+08:00",
                        },
                        {
                            "task_id": "cron:ops-governance-evolution",
                            "task_type": "ops_runtime_cron",
                            "reason": "[CRON_RUNTIME] bind cron:ops-governance-evolution",
                            "status": "passed",
                            "updated_at": "2026-03-12T23:00:00+08:00",
                        },
                    ],
                ):
                    with mock.patch.object(
                        module,
                        "ensure_task_binding",
                        return_value=("cron:ops-daily-todo-digest", ""),
                    ):
                        with mock.patch.object(module, "invoke_policy_enforcer", return_value=(True, {"ok": True}, "")):
                            with redirect_stdout(stdout):
                                rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertFalse(payload["notify"])
        self.assertEqual(payload["output"], "NO_REPLY")


if __name__ == "__main__":
    unittest.main()

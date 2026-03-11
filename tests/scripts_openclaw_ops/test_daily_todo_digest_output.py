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
                    "priority": "high",
                    "risk_level": "high",
                    "assignee": "ops-agent",
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

        self.assertEqual(output.splitlines()[0], "每日任务摘要")
        self.assertIn("新增待办 1 项", output)
        self.assertIn("新增完成 1 项", output)
        self.assertIn("近24小时处理", output)
        self.assertIn("留痕编号：digest-run-001", output)
        self.assertNotIn("Daily TODO Digest", output)
        self.assertNotIn("evidence:", output)
        self.assertNotIn("/tmp/", output)
        self.assertNotIn(".json", output)

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

        self.assertEqual(output.splitlines()[0], "每日任务摘要异常")
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
        self.assertEqual(payload["output"].splitlines()[0], "每日任务摘要异常")
        self.assertIn("留痕编号", payload["output"])
        self.assertNotIn("Daily TODO Digest", payload["output"])
        self.assertNotIn("evidence:", payload["output"])
        self.assertNotIn(".json", payload["output"])
        self.assertTrue(any(args and args[0] == "planner-summary" for args in invoked))


if __name__ == "__main__":
    unittest.main()

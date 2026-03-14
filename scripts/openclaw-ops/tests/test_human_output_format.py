import sys
import unittest
from pathlib import Path


OPS_ROOT = Path(__file__).resolve().parents[1]
if str(OPS_ROOT) not in sys.path:
    sys.path.insert(0, str(OPS_ROOT))
POLICY_ROOT = OPS_ROOT / "policy"
if str(POLICY_ROOT) not in sys.path:
    sys.path.insert(0, str(POLICY_ROOT))

from chat_output import render_chat_notice
from cron_setup import build_message as build_cron_message
from workflow_views import build_ops_scan_event, build_task_executor_event, render_human_view


class HumanOutputFormatTests(unittest.TestCase):
    def test_render_chat_notice_uses_utc8_headline(self) -> None:
        output = render_chat_notice(
            "系统定时巡检提醒",
            status="需关注",
            sender_identity="ops-agent",
            run_time="2026-03-14T00:14:14+00:00",
            trace_id="trace-001",
            summary="检测到 2 个高风险项",
            extra_lines=["OpenClaw 定时任务：21 个"],
        )

        lines = output.splitlines()
        self.assertEqual(lines[0], "2026-03-14 08:14:14 UTC+8 系统定时巡检提醒：检测到 2 个高风险项")
        self.assertNotIn("北京时间", output)
        self.assertIn("- 状态：需关注", output)
        self.assertIn("- 留痕编号：trace-001", output)

    def test_task_executor_human_view_uses_readable_task_summaries(self) -> None:
        event = build_task_executor_event(
            {
                "trigger_task": "cron:task-executor",
                "run_id": "exec-20260314_085300-1517c872",
                "started_at": "2026-03-14T00:53:00+00:00",
                "finished_at": "2026-03-14T00:53:02+00:00",
                "executor_model": "openai-codex/gpt-5",
                "tasks_selected": 3,
                "tasks_executed": 0,
                "tasks_skipped": 3,
                "results": [
                    {
                        "task_id": "todo-a76d92b6fce91185",
                        "assignee": "project-agent",
                        "stage": "plan",
                        "status": "skipped",
                        "reason": "waiting_human_confirm",
                        "task_requirement": "补齐项目索引治理方案，并确认是否纳入本周计划。",
                    },
                    {
                        "task_id": "todo-919de13c19b14128",
                        "assignee": "project-agent",
                        "stage": "plan",
                        "status": "skipped",
                        "reason": "waiting_human_confirm",
                        "task_requirement": "梳理增量巡检输出格式，确认哪些字段给人看。",
                    },
                    {
                        "task_id": "todo-e97f97a2e088e68f",
                        "assignee": "project-agent",
                        "stage": "plan",
                        "status": "skipped",
                        "reason": "waiting_human_confirm",
                        "task_requirement": "整理任务执行器的人类摘要模板，避免只显示任务 ID。",
                    },
                ],
            },
            OPS_ROOT / "reports" / "exec-20260314_085300-1517c872.json",
            "always",
        )

        output = render_human_view(event["views"]["human"])
        self.assertIn("2026-03-14 08:53:02 UTC+8 任务执行器（10分钟）：3 个任务等待人工确认，本轮未执行。", output)
        self.assertIn("任务1：补齐项目索引治理方案，并确认是否纳入本周计划。", output)
        self.assertIn("任务2：梳理增量巡检输出格式，确认哪些字段给人看。", output)
        self.assertIn("任务3：整理任务执行器的人类摘要模板，避免只显示任务 ID。", output)
        self.assertIn("状态1：等待人工确认", output)
        self.assertIn("值得做1：", output)
        self.assertNotIn("todo-a76d92b6fce91185", output)
        self.assertNotIn("todo-919de13c19b14128", output)
        self.assertNotIn("todo-e97f97a2e088e68f", output)
        self.assertIn("- 触发任务：任务执行器（10分钟）", output)
        self.assertIn("- 运行编号：exec-20260314_085300-1517c872", output)
        self.assertIn("- 留痕编号：exec-20260314_085300-1517c872", output)

    def test_ops_scan_human_view_uses_compact_cn_summary(self) -> None:
        event = build_ops_scan_event(
            {
                "task_id": "cron:ops-incremental-monitor",
                "mode": "incremental",
                "time": "2026-03-14 07:28:58 (UTC+8)",
                "run_id": "ops-run-001",
                "risk_reasons": ["workflow_job_error=2"],
                "workflow_health": {
                    "failed_jobs": [
                        {
                            "id": "job-1",
                            "name": "ops_git_sync_push",
                            "consecutive_errors": 2,
                            "last_status": "error",
                            "last_error": "Unhandled stop reason: network_error",
                        }
                    ]
                },
                "workflow_follow_up_summary": {},
                "runtime_health": {},
                "scan_errors": [],
                "handoff_summary": {},
            }
        )

        output = render_human_view(event["views"]["human"])
        self.assertIn("2026-03-14 07:28:58 UTC+8 运维增量巡检（15分钟）：发现 2 个工作流失败，0 个持续失败。", output)
        self.assertIn("- 任务：运维增量巡检（15分钟）", output)
        self.assertIn("Git 同步推送（6小时）：网络错误", output)
        self.assertNotIn("ops_git_sync_push", output)
        self.assertNotIn("cron:ops-incremental-monitor", output)
        self.assertNotIn("- 时间:", output)

    def test_cron_message_requires_raw_cn_output_passthrough(self) -> None:
        message = build_cron_message("python3 /tmp/demo.py")
        self.assertIn("If the finished command prints NO_REPLY, you must respond exactly NO_REPLY and stop.", message)
        self.assertIn(
            "If the finished command outputs a human-facing message, preserve the original Chinese text and UTC+8 timestamps exactly.",
            message,
        )
        self.assertIn("Do not translate, paraphrase, summarize, explain, or add process commentary.", message)


if __name__ == "__main__":
    unittest.main()

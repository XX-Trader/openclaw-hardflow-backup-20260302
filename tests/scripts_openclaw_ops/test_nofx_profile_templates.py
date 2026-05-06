import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class NofxProfileTemplateTests(unittest.TestCase):
    def test_workflow_maintenance_mode_is_not_readonly(self):
        for profile in ("arbitrageagent", "spreadagent"):
            with self.subTest(profile=profile):
                text = (ROOT / "config" / "nofx-hermes-profiles" / profile / "SOUL.md").read_text(encoding="utf-8")

                self.assertIn("高权限工作流维护模式", text)
                self.assertIn("不要启动新的 `smart-arb-pipeline`", text)
                self.assertIn("/home/arbops/projects/openclaw-hardflow-backup-20260302", text)
                self.assertIn("runtime installer", text)
                self.assertIn("review=pending_external", text)
                self.assertIn("不要 force push", text)
                self.assertIn("不要删除生产数据", text)
                self.assertIn("不要读取或打印 token", text)
                self.assertIn("保持 `PRODUCTION_TRADING_ENABLED=false`", text)
                self.assertIn("先确认没有活跃 `smart-arb-pipeline`", text)
                self.assertIn("同步 live `/home/arbops/.hermes/profiles/<profile>/SOUL.md`", text)
                self.assertIn("`gateway_state=running`", text)
                self.assertIn("--human-risk-confirmed", text)
                self.assertIn("真实交易、下单、划转、提现和资金类策略任务不是永久阻断", text)
                self.assertNotIn("只允许做只读诊断和状态回传", text)

    def test_discord_execution_requests_require_manual_route_choice(self):
        for profile in ("arbitrageagent", "spreadagent"):
            with self.subTest(profile=profile):
                text = (ROOT / "config" / "nofx-hermes-profiles" / profile / "SOUL.md").read_text(encoding="utf-8")

                self.assertIn("所有来自 Discord 的新任务", text)
                self.assertIn("收到任何 Discord 新任务", text)
                self.assertIn("不要直接做只读查询或普通沟通", text)
                self.assertIn("执行链路选择", text)
                self.assertIn("回答状态: 等待人工选择", text)
                self.assertIn("推荐不是授权", text)
                self.assertIn("Discord profile 是本入口的最高权限 operator", text)
                self.assertIn("direct_run", text)
                self.assertIn("requirement_discussion", text)
                self.assertIn("specified_agent", text)
                self.assertIn("coding_workflow", text)
                self.assertIn("todo_auto_candidate", text)
                self.assertIn("用户选择 `direct_run` 后", text)
                self.assertIn("--route-choice coding_workflow", text)
                self.assertIn("--human-risk-confirmed", text)
                self.assertIn("缺失时入口会只返回选择卡并拒绝启动 pipeline", text)
                self.assertIn("git pull --ff-only", text)
                self.assertIn("HEAD == origin/main", text)
                self.assertIn("只有用户明确回复", text)
                self.assertNotIn("只读状态查询、简单解释、方案讨论或查询监控数据，可以直接读取", text)
                self.assertNotIn("收到普通项目执行类请求时，不要立刻创建", text)
                self.assertNotIn("收到普通项目执行类请求时，先创建 `smart-arb-pipeline` run", text)
                self.assertNotIn("默认就是真实执行", text)


if __name__ == "__main__":
    unittest.main()

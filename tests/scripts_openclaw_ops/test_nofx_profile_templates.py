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
                self.assertNotIn("只允许做只读诊断和状态回传", text)


if __name__ == "__main__":
    unittest.main()

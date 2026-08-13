import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROFILE_ROOT = ROOT / "config" / "runtime-profiles"


class RuntimeProfileTemplateTests(unittest.TestCase):
    def test_profiles_are_domain_neutral_and_environment_driven(self):
        for profile in ("deliveryagent", "projectagent", "workflow-repair"):
            with self.subTest(profile=profile):
                soul = (PROFILE_ROOT / profile / "SOUL.md").read_text(encoding="utf-8")
                config = (PROFILE_ROOT / profile / "config.yaml").read_text(encoding="utf-8")

                self.assertIn("通用", soul)
                self.assertIn("redact_secrets: true", config)
                self.assertNotIn("/home/", soul + config)
                self.assertNotIn("D:\\", soul + config)

    def test_delivery_profile_defines_end_to_end_evidence_contract(self):
        text = (PROFILE_ROOT / "deliveryagent" / "SOUL.md").read_text(encoding="utf-8")

        self.assertIn("需求、方案、实现、测试、审查、部署和写回闭环", text)
        self.assertIn("缺陷复现、根因分析、修复、防复发回归", text)
        self.assertIn("Git 发布只包含已确认范围，并回读远端 SHA", text)
        self.assertIn("不绑定业务领域", text)

    def test_project_and_repair_profiles_keep_roles_separate(self):
        project = (PROFILE_ROOT / "projectagent" / "SOUL.md").read_text(encoding="utf-8")
        repair = (PROFILE_ROOT / "workflow-repair" / "SOUL.md").read_text(encoding="utf-8")

        self.assertIn("必改文件、只读来源、参考模式、检查项与禁止目标", project)
        self.assertIn("未进入实现阶段时保持只读", project)
        self.assertIn("避免用故障中的同一流水线递归修复自己", repair)
        self.assertIn("防复发测试", repair)


if __name__ == "__main__":
    unittest.main()

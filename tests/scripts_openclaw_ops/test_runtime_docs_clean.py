import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_head(rel_path: str, line_count: int) -> str:
    path = ROOT / rel_path
    return "\n".join(path.read_text(encoding="utf-8-sig").splitlines()[:line_count])


class RuntimeDocsCleanTests(unittest.TestCase):
    def test_ops_readme_top_sections_are_clean_chinese(self):
        text = read_head("scripts/openclaw-ops/README.md", 24)
        self.assertIn("当前原则", text)
        self.assertIn("project-delivery-pipeline", text)
        self.assertIn("shared/", text)
        self.assertIn("不恢复 `cron_setup.py`", text)
        self.assertNotIn("闂冭埖顔", text)
        self.assertNotIn("閹貉冨煑闂", text)

    def test_runtime_plan_top_sections_are_clean_chinese(self):
        text = read_head("requirements.md", 30)
        self.assertIn("工作流基础设施与配置备份", text)
        self.assertIn("领域中立", text)
        self.assertIn("通用", text)
        self.assertIn("验收", text)
        self.assertNotIn("缁楊兛绗", text)
        self.assertNotIn("閹貉冨煑闂", text)

    def test_done_top_sections_are_clean_chinese(self):
        text = read_head("done.md", 32)
        self.assertIn("领域中立", text)
        self.assertIn("项目交付状态机", text)
        self.assertIn("跨 Runtime 安装器", text)
        self.assertIn("敏感信息扫描", text)
        self.assertNotIn("缁楊兛绗", text)
        self.assertNotIn("闂冭埖顔", text)


if __name__ == "__main__":
    unittest.main()

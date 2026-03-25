import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_head(rel_path: str, line_count: int) -> str:
    path = ROOT / rel_path
    return "\n".join(path.read_text(encoding="utf-8-sig").splitlines()[:line_count])


class RuntimeDocsCleanTests(unittest.TestCase):
    def test_ops_readme_top_sections_are_clean_chinese(self):
        text = read_head("scripts/openclaw-ops/README.md", 24)
        self.assertIn("基建输入输出与通信标准收口", text)
        self.assertIn("基建设施输入输出与通信标准", text)
        self.assertIn("基建设施模板文档", text)
        self.assertIn("字段字典", text)
        self.assertNotIn("闂冭埖顔", text)
        self.assertNotIn("閹貉冨煑闂", text)

    def test_runtime_plan_top_sections_are_clean_chinese(self):
        text = read_head("docs/plans/2026-03-22-workflow-selection-runtime-implementation-plan.md", 24)
        self.assertIn("第四十批基建输入输出与通信标准收口", text)
        self.assertIn("基建设施输入输出与通信标准", text)
        self.assertIn("基建设施模板文档", text)
        self.assertIn("ExecutionEnvelope", text)
        self.assertNotIn("缁楊兛绗", text)
        self.assertNotIn("閹貉冨煑闂", text)

    def test_done_top_sections_are_clean_chinese(self):
        text = read_head("done.md", 24)
        self.assertIn("第四十批基建输入输出与通信标准收口", text)
        self.assertIn("基建设施输入输出与通信标准", text)
        self.assertIn("基建设施模板文档", text)
        self.assertIn("字段字典", text)
        self.assertNotIn("缁楊兛绗", text)
        self.assertNotIn("闂冭埖顔", text)


if __name__ == "__main__":
    unittest.main()

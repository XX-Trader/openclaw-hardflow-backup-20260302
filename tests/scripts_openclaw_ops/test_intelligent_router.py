import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = ROOT / "skills/library/intelligent-router/router_engine.py"
CONFIG_DIR = ROOT / "skills/library/intelligent-router/config"
SKILLS_DIR = ROOT / "skills/library"


def load_module():
    spec = importlib.util.spec_from_file_location("intelligent_router_test", ROUTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IntelligentRouterTests(unittest.TestCase):
    def setUp(self):
        module = load_module()
        self.router = module.IntelligentRouter(str(SKILLS_DIR), str(CONFIG_DIR))

    def test_dot_prefixed_and_filename_extensions_are_routed(self):
        direct = self.router.route("分析代码", file_context=".py")
        filename = self.router.route("分析代码", file_context="src/service.py")
        typescript = self.router.route("收紧类型", file_context="src/model.ts")
        dockerfile = self.router.route("检查构建", file_context="Dockerfile")
        self.assertEqual(direct["method"], "file_type")
        self.assertEqual(direct["target"], "python-expert")
        self.assertEqual(filename["target"], "python-expert")
        self.assertEqual(typescript["target"], "typescript-expert")
        self.assertEqual(dockerfile["target"], "deployment-engineer")

    def test_explicit_targets_are_validated_and_invalid_target_falls_back(self):
        skill = self.router.route("[调用技能: pdf] 提取文档内容")
        subagent = self.router.route("[调用 Subagent: smart-flow:python-expert] 优化代码")
        combo = self.router.route("[调用组合: 数据分析组合] 分析数据")
        missing = self.router.route("[调用技能: missing-owner] 执行任务")

        self.assertEqual(skill["target"], "pdf")
        self.assertEqual(subagent["target"], "smart-flow:python-expert")
        self.assertEqual(combo["target"], "数据分析组合")
        self.assertEqual(missing["method"], "default")
        self.assertIsNone(missing["target"])

    def test_bug_fix_keyword_uses_controlled_debugger_route(self):
        result = self.router.route("请修复 bug 并补充测试")
        self.assertEqual(result["method"], "keyword")
        self.assertEqual(result["target"], "debugger")

    def test_general_delivery_keywords_do_not_select_legacy_project_skills(self):
        self.assertEqual(self.router.route("新增功能并补测试")["target"], "coordinator")
        self.assertEqual(
            self.router.route("部署项目并保留回滚证据")["target"],
            "deployment-engineer",
        )
        self.assertEqual(self.router.route("执行部署后测试")["target"], "test-automator")

    def test_keyword_routes_honor_priority_before_file_order(self):
        result = self.router.route("请检查代码和本地环境")
        self.assertEqual(result["target"], "code-reviewer")

    def test_all_configured_route_targets_are_registered_or_installed(self):
        keyword_config = json.loads((CONFIG_DIR / "keyword_routes.json").read_text(encoding="utf-8"))
        file_config = json.loads((CONFIG_DIR / "file_type_routes.json").read_text(encoding="utf-8"))
        routes = keyword_config.get("routes", keyword_config.get("keywords", []))
        routes += file_config.get("routes", file_config.get("file_types", []))
        unknown = []
        for route in routes:
            target = route.get("target") or route.get("agent") or route.get("agent_alternative")
            if not self.router._is_known_target(target):
                unknown.append(target)
        self.assertEqual(unknown, [])

    def test_source_checkout_demo_uses_repository_relative_config(self):
        process = subprocess.run(
            [sys.executable, str(ROUTER_PATH)],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("智能路由引擎", process.stdout)


if __name__ == "__main__":
    unittest.main()

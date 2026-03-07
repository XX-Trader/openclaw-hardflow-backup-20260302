import importlib.util
import sys
import unittest
from pathlib import Path


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


class ScraplingAndGithubFilterTests(unittest.TestCase):
    def test_api_test_audit_accepts_scrapling_engines(self):
        module = load_module(
            "api_test_audit",
            "scripts/openclaw-ops/api_test_audit.py",
        )
        self.assertEqual(module.normalize_engine("scrapling", "http"), "scrapling")
        self.assertEqual(module.normalize_engine("scrapling-stealth", "http"), "scrapling-stealth")

    def test_github_web_evolution_filters_infrastructure_repos(self):
        module = load_module(
            "github_web_evolution_runner",
            "scripts/openclaw-ops/github_web_evolution_runner.py",
        )
        self.assertTrue(module.is_infrastructure_repo({"full_name": "python/cpython"}))
        self.assertTrue(module.is_infrastructure_repo({"full_name": "nodejs/node"}))
        self.assertFalse(module.is_infrastructure_repo({"full_name": "microsoft/playwright"}))

    def test_github_web_evolution_matches_project_scope(self):
        module = load_module(
            "github_web_evolution_runner",
            "scripts/openclaw-ops/github_web_evolution_runner.py",
        )
        self.assertTrue(
            module.matches_project_scope(
                {
                    "full_name": "D4Vinci/Scrapling",
                    "description": "Web scraping anti bot browser automation toolkit",
                    "language": "Python",
                    "topics": ["scraping", "browser", "automation"],
                    "query_hits": [],
                }
            )
        )
        self.assertTrue(
            module.matches_project_scope(
                {
                    "full_name": "microsoft/playwright",
                    "description": "Browser testing and automation framework",
                    "language": "TypeScript",
                    "topics": ["browser", "testing"],
                    "query_hits": [],
                }
            )
        )
        self.assertFalse(
            module.matches_project_scope(
                {
                    "full_name": "psf/requests",
                    "description": "HTTP for Humans",
                    "language": "Python",
                    "topics": ["http", "requests"],
                    "query_hits": [],
                }
            )
        )

    def test_default_query_pack_avoids_language_python_bias(self):
        module = load_module(
            "github_web_evolution_runner",
            "scripts/openclaw-ops/github_web_evolution_runner.py",
        )
        queries = module.build_query_list([], 80, 5)
        self.assertEqual(len(queries), 5)
        self.assertTrue(any("web scraping anti bot browser automation" in query for query in queries))
        self.assertTrue(all("language:python" not in query for query in queries))

    def test_web_intel_prefers_scrapling_before_other_browsers(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        call_order: list[str] = []

        def fake_scrapling(url: str, timeout_seconds: int):
            call_order.append("scrapling")
            return {
                "ok": False,
                "method": "browser-scrapling-stealth",
                "status": 403,
                "content_type": "text/html",
                "text": "just a moment",
                "truncated": False,
                "error": "browser_antibot_challenge",
            }

        def fake_playwright(url: str, timeout_seconds: int):
            call_order.append("playwright")
            return {
                "ok": True,
                "method": "browser-playwright",
                "status": 200,
                "content_type": "text/html",
                "text": "<html><body>ok</body></html>",
                "truncated": False,
                "error": "",
            }

        def fake_selenium(url: str, timeout_seconds: int):
            call_order.append("selenium")
            return {
                "ok": True,
                "method": "browser-selenium",
                "status": 200,
                "content_type": "text/html",
                "text": "<html><body>unused</body></html>",
                "truncated": False,
                "error": "",
            }

        original_scrapling = module.fetch_with_scrapling
        original_playwright = module.fetch_with_playwright
        original_selenium = module.fetch_with_selenium
        original_antibot = module.looks_like_antibot
        try:
            module.fetch_with_scrapling = fake_scrapling
            module.fetch_with_playwright = fake_playwright
            module.fetch_with_selenium = fake_selenium
            module.looks_like_antibot = lambda result: "just a moment" in str(result.get("text", "")).lower()

            result = module.fetch_with_browser("https://example.com", 10)
        finally:
            module.fetch_with_scrapling = original_scrapling
            module.fetch_with_playwright = original_playwright
            module.fetch_with_selenium = original_selenium
            module.looks_like_antibot = original_antibot

        self.assertEqual(call_order, ["scrapling", "playwright"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "browser-playwright")

    def test_web_intel_humanizes_http_403_in_readable_chinese(self):
        module = load_module(
            "web_intel_collect_runner",
            "scripts/openclaw-ops/web_intel_collect_runner.py",
        )
        title, detail = module.humanize_collect_error("http_error:403", 403)
        self.assertEqual(title, "HTTP 请求失败")
        self.assertEqual(detail, "目标站点返回状态码 403")


if __name__ == "__main__":
    unittest.main()

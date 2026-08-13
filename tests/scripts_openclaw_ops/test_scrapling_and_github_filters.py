import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
            "skills/library/openclaw-security-audit/scripts/api_test_audit.py",
        )
        self.assertEqual(module.normalize_engine("scrapling", "http"), "scrapling")
        self.assertEqual(module.normalize_engine("scrapling-stealth", "http"), "scrapling-stealth")

    def test_api_test_audit_missing_config_uses_chinese_card_without_path(self):
        module = load_module(
            "api_test_audit",
            "skills/library/openclaw-security-audit/scripts/api_test_audit.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "api_test_config.json"
            state_path = tmp / "state.json"
            history_dir = tmp / "history"
            history_dir.mkdir(parents=True, exist_ok=True)

            argv = [
                "api_test_audit.py",
                "--config-file",
                str(config_path),
                "--state-file",
                str(state_path),
                "--history-dir",
                str(history_dir),
                "--task-id",
                "cron:ops-api-test-audit",
                "--emit-json",
            ]
            stdout = io.StringIO()
            with unittest.mock.patch.object(sys, "argv", argv):
                with redirect_stdout(stdout):
                    rc = module.main()

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue().strip())
        self.assertTrue(payload["notify"])
        self.assertIn("接口巡检异常", payload["output"].splitlines()[0])
        self.assertIn("巡检配置缺失", payload["output"])
        self.assertIn("留痕编号", payload["output"])
        self.assertNotIn(str(config_path), payload["output"])
        self.assertNotIn("evidence:", payload["output"])
        self.assertNotIn("# api-test-audit", payload["output"])

    def test_github_web_evolution_filters_infrastructure_repos(self):
        module = load_module(
            "github_web_evolution_runner",
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
        )
        self.assertTrue(module.is_infrastructure_repo({"full_name": "python/cpython"}))
        self.assertTrue(module.is_infrastructure_repo({"full_name": "nodejs/node"}))
        self.assertFalse(module.is_infrastructure_repo({"full_name": "microsoft/playwright"}))

    def test_github_web_evolution_matches_project_scope(self):
        module = load_module(
            "github_web_evolution_runner",
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
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
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
        )
        queries = module.build_query_list([], 80, 5)
        self.assertEqual(len(queries), 5)
        self.assertTrue(any("openclaw" in query for query in queries))
        self.assertTrue(any(any(token in query for token in ["skill", "hook", "plugin"]) for query in queries))
        self.assertTrue(all("language:python" not in query for query in queries))

    def test_web_intel_prefers_scrapling_before_other_browsers(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
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

    def test_web_intel_collect_follow_up_task_payload_hides_report_path(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
        )
        captured_args: list[list[str]] = []

        def fake_invoke(_db_path, args, timeout=35):
            captured_args.append(list(args))
            return True, {"ok": True}, ""

        original_invoke = module.invoke_policy_enforcer
        try:
            module.invoke_policy_enforcer = fake_invoke
            created, errors = module.create_collect_follow_up_tasks(
                db_path=Path("/tmp/task_center.db"),
                actor="web-agent/web-intel-collect",
                report_file=Path("/tmp/reports/web_collect_20260311.json"),
                run_task_id="cron:web-intel-collect",
                started_at="2026-03-11T08:00:00+00:00",
                failed_items=[
                    {
                        "id": "openai-docs",
                        "url": "https://example.com/docs",
                        "error": "http_error:429",
                        "status_code": 429,
                    }
                ],
            )
        finally:
            module.invoke_policy_enforcer = original_invoke

        self.assertEqual(len(created), 1)
        self.assertEqual(errors, [])
        self.assertEqual(len(captured_args), 1)
        args = captured_args[0]
        requirement = args[args.index("--requirement") + 1]
        context_payload = json.loads(args[args.index("--context-json") + 1])
        observable_outputs = args[args.index("--observable-outputs") + 1]
        required_capabilities = args[args.index("--required-capabilities") + 1]
        allowed_agents = args[args.index("--allowed-agents") + 1]
        self.assertIn("留痕编号", requirement)
        self.assertNotIn("/tmp/reports/web_collect_20260311.json", requirement)
        self.assertTrue(str(context_payload.get("evidence", "")).startswith("留痕编号："))
        self.assertNotIn("/tmp/reports/web_collect_20260311.json", str(context_payload))
        self.assertIn("留痕编号=", observable_outputs)
        self.assertNotIn("report_file=", observable_outputs)
        self.assertEqual(required_capabilities, "skill_backed,task_execution")
        self.assertEqual(allowed_agents, "ops-agent")

    def test_web_intel_collect_summary_file_hides_internal_paths(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
        )
        original_http = module.fetch_with_http
        original_browser = module.fetch_with_browser

        def fake_http(url: str, timeout_seconds: int, max_bytes: int):
            return {
                "ok": True,
                "method": "http",
                "status": 200,
                "text": "<html><title>OpenAI Docs</title><body>hello world</body></html>",
                "truncated": False,
                "error": "",
            }

        def fake_browser(url: str, timeout_seconds: int):
            raise AssertionError("browser fallback should not be used")

        try:
            module.fetch_with_http = fake_http
            module.fetch_with_browser = fake_browser
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                sources_file = tmp / "sources.json"
                state_file = tmp / "state.json"
                report_dir = tmp / "reports"
                raw_dir = tmp / "raw"
                parsed_dir = tmp / "parsed"
                summary_dir = tmp / "summary"
                sources_file.write_text(
                    json.dumps(
                        {
                            "sources": [
                                {
                                    "id": "openai-docs",
                                    "url": "https://example.com/docs",
                                    "enabled": True,
                                    "browser_fallback": False,
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                argv = [
                    "web_intel_collect_runner.py",
                    "--sources-file",
                    str(sources_file),
                    "--state-file",
                    str(state_file),
                    "--report-dir",
                    str(report_dir),
                    "--raw-dir",
                    str(raw_dir),
                    "--parsed-dir",
                    str(parsed_dir),
                    "--summary-dir",
                    str(summary_dir),
                    "--max-sources",
                    "1",
                    "--force",
                    "--emit-json",
                ]
                stdout = io.StringIO()
                with unittest.mock.patch.object(sys, "argv", argv):
                    with redirect_stdout(stdout):
                        module.main()

                summary_text = (summary_dir / "openai-docs.md").read_text(encoding="utf-8")
        finally:
            module.fetch_with_http = original_http
            module.fetch_with_browser = original_browser

        self.assertIn("解析留痕编号", summary_text)
        self.assertIn("原始留痕编号", summary_text)
        self.assertNotIn("parsed_file:", summary_text)
        self.assertNotIn("raw_file:", summary_text)
        self.assertNotIn(str(parsed_dir), summary_text)
        self.assertNotIn(str(raw_dir), summary_text)

    def test_web_intel_humanizes_http_403_in_readable_chinese(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
        )
        title, detail = module.humanize_collect_error("http_error:403", 403)
        self.assertEqual(title, "HTTP 请求失败")
        self.assertEqual(detail, "目标站点返回状态码 403")

    def test_web_intel_review_follow_up_task_payload_hides_internal_paths(self):
        module = load_module(
            "web_intel_review_runner",
            "skills/library/web-intelligence/scripts/web_intel_review_runner.py",
        )
        captured_args: list[list[str]] = []

        def fake_invoke(_db_path, args, timeout=35):
            captured_args.append(list(args))
            return True, {"ok": True}, ""

        original_invoke = module.invoke_policy_enforcer
        try:
            module.invoke_policy_enforcer = fake_invoke
            created, errors = module.create_review_follow_up_tasks(
                db_path=Path("/tmp/task_center.db"),
                mode="project-doc",
                assignee="project-agent",
                actor="project-agent/web-doc-review",
                report_file=Path("/tmp/reports/web_review_project_doc.json"),
                review_items=[
                    {
                        "id": "orders-api",
                        "fingerprint": "abcdef123456",
                        "title": "Orders API",
                        "url": "https://example.com/orders",
                        "parsed_file": "/tmp/parsed/orders-api.json",
                        "signals": [{"signal": "API 契约信号", "action": "更新契约测试"}],
                        "new_information": ["Parameter: recvWindow"],
                        "updated_interfaces": [],
                        "fetched_at": "2026-03-11T08:00:00+00:00",
                    }
                ],
            )
        finally:
            module.invoke_policy_enforcer = original_invoke

        self.assertEqual(len(created), 1)
        self.assertEqual(errors, [])
        self.assertEqual(len(captured_args), 1)
        args = captured_args[0]
        requirement = args[args.index("--requirement") + 1]
        context_payload = json.loads(args[args.index("--context-json") + 1])
        observable_outputs = args[args.index("--observable-outputs") + 1]
        required_capabilities = args[args.index("--required-capabilities") + 1]
        allowed_agents = args[args.index("--allowed-agents") + 1]
        self.assertIn("运行留痕编号", requirement)
        self.assertIn("解析留痕编号", requirement)
        self.assertNotIn("/tmp/reports/web_review_project_doc.json", requirement)
        self.assertNotIn("/tmp/parsed/orders-api.json", requirement)
        self.assertIn("留痕编号", str(context_payload.get("evidence", "")))
        self.assertNotIn("/tmp/reports/web_review_project_doc.json", str(context_payload))
        self.assertNotIn("/tmp/parsed/orders-api.json", str(context_payload))
        self.assertIn("运行留痕编号=", observable_outputs)
        self.assertIn("解析留痕编号=", observable_outputs)
        self.assertNotIn("report_file=", observable_outputs)
        self.assertNotIn("parsed_file=", observable_outputs)
        self.assertEqual(required_capabilities, "role_only")
        self.assertEqual(allowed_agents, "project-agent")


if __name__ == "__main__":
    unittest.main()

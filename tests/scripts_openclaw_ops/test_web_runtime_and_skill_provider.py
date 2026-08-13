import importlib.util
import json
import subprocess
import sys
import tempfile
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


class WebRuntimeAndSkillProviderTests(unittest.TestCase):
    def init_git_repo(self, path: Path, remote: str = "") -> None:
        subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "Test User"],
            check=True,
            capture_output=True,
            text=True,
        )
        if remote:
            subprocess.run(
                ["git", "-C", str(path), "remote", "add", "origin", remote],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_project_index_doc_knowledge_detects_external_api_urls_and_repo_sources(self):
        module = load_module(
            "project_index_maintainer",
            "skills/library/control-plane-ops/scripts/policy/project_index_maintainer.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            service_file = tmp / "src" / "github_client.py"
            service_file.parent.mkdir(parents=True, exist_ok=True)
            service_file.write_text(
                "\n".join(
                    [
                        'BASE_URL = "https://api.github.com/repos/example/project"',
                        'FUTURES_URL = "https://uploads.github.com/repos/example/project/releases"',
                    ]
                ),
                encoding="utf-8",
            )
            index_root = tmp / ".workflow" / "project-index-local"

            payload, _changed = module.build_doc_knowledge(
                root=tmp,
                index_root=index_root,
                api_files=["src/github_client.py"],
                source_files=["src/github_client.py"],
                enable_checks=False,
                timeout=5,
                fetch_content=False,
                fetch_max_chars=2048,
            )

        self.assertIn("https://api.github.com/repos/example/project", payload["external_api_urls"])
        self.assertIn("api.github.com", payload["external_api_hosts"])
        self.assertTrue(any(item.get("vendor") == "github" for item in payload["repo_sources"]))
        github_repo_source = next(item for item in payload["repo_sources"] if item.get("vendor") == "github")
        self.assertIn("github/rest-api-description", github_repo_source["official_repos"])
        self.assertTrue(any("github" in query.lower() for query in github_repo_source["repo_queries"]))
        self.assertTrue(any("docs.github.com" in item.get("url", "") for item in payload["doc_sources"]))

    def test_project_index_doc_knowledge_builds_host_repo_queries_for_unknown_api_hosts(self):
        module = load_module(
            "project_index_maintainer",
            "skills/library/control-plane-ops/scripts/policy/project_index_maintainer.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            service_file = tmp / "src" / "vendor_client.py"
            service_file.parent.mkdir(parents=True, exist_ok=True)
            service_file.write_text(
                "\n".join(
                    [
                        'BASE_URL = "https://api.polybaymax.com/v1/orders"',
                        'PUBLIC_URL = "https://dabaiquant.com/api/markets"',
                    ]
                ),
                encoding="utf-8",
            )
            index_root = tmp / ".workflow" / "project-index-local"

            payload, _changed = module.build_doc_knowledge(
                root=tmp,
                index_root=index_root,
                api_files=["src/vendor_client.py"],
                source_files=["src/vendor_client.py"],
                enable_checks=False,
                timeout=5,
                fetch_content=False,
                fetch_max_chars=2048,
            )

        repo_sources = payload["repo_sources"]
        vendors = {item.get("vendor") for item in repo_sources}
        all_queries = [query for item in repo_sources for query in item.get("repo_queries", [])]
        self.assertIn("api.polybaymax.com", payload["external_api_hosts"])
        self.assertIn("dabaiquant.com", payload["external_api_hosts"])
        self.assertIn("polybaymax", vendors)
        self.assertIn("dabaiquant", vendors)
        self.assertTrue(any("polybaymax api sdk" in query.lower() for query in all_queries))
        self.assertTrue(any("dabaiquant api sdk" in query.lower() for query in all_queries))

    def test_project_index_maintainer_skips_unchanged_git_projects_after_state_recorded(self):
        module = load_module(
            "project_index_maintainer",
            "skills/library/control-plane-ops/scripts/policy/project_index_maintainer.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.init_git_repo(tmp)
            src_file = tmp / "src" / "main.py"
            src_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_text("print('ok')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(tmp), "add", "."], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(tmp), "commit", "-m", "init"],
                check=True,
                capture_output=True,
                text=True,
            )

            item = {"id": "demo-project", "name": "demo-project", "path": str(tmp)}
            first = module.maintain_project(
                item=item,
                git_pull_flag=False,
                timeout=10,
                max_files=50,
                enable_doc_knowledge=False,
                doc_check_updates=False,
                doc_timeout=5,
                doc_fetch_content=False,
                doc_fetch_max_chars=2048,
                memory_index_on_change=False,
                skip_unchanged_git_projects=True,
            )
            self.assertTrue(first.ok)
            self.assertFalse(first.skipped)

            head = subprocess.run(
                ["git", "-C", str(tmp), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            state_path = tmp / ".workflow" / "project-index-local" / "project-index-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["git"]["head"], head)

            second = module.maintain_project(
                item=item,
                git_pull_flag=False,
                timeout=10,
                max_files=50,
                enable_doc_knowledge=False,
                doc_check_updates=False,
                doc_timeout=5,
                doc_fetch_content=False,
                doc_fetch_max_chars=2048,
                memory_index_on_change=False,
                skip_unchanged_git_projects=True,
            )
            self.assertTrue(second.ok)
            self.assertTrue(second.skipped)
            self.assertFalse(second.changed)
            self.assertEqual(second.skip_reason, f"git_head_unchanged:{head}")


    def test_web_intel_load_sources_merges_project_registry_and_vendor_docs(self):
        module = load_module(
            "web_intel_collect_runner",
            "skills/library/web-intelligence/scripts/web_intel_collect_runner.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            static_sources = tmp / "sources.json"
            extra_sources = tmp / "project_docs_sources.json"
            project_registry = tmp / "project-registry.json"

            static_sources.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "fastapi-release-notes",
                                "url": "https://fastapi.tiangolo.com/release-notes/",
                                "category": "official-doc",
                                "tags": ["api", "doc", "release"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            extra_sources.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "project-doc-base",
                                "url": "https://example.com/project-doc",
                                "category": "project-doc",
                                "tags": ["project", "doc"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            project_registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "service-bot",
                                "name": "service-bot",
                                "path": str(tmp),
                                "integrations": ["github"],
                                "doc_sources": [
                                    {
                                        "id": "service-bot-api-overview",
                                        "url": "https://example.com/service-bot/api",
                                        "category": "api-doc",
                                        "tags": ["project", "api"],
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            sources = module.load_sources(
                static_sources,
                extra_paths=[extra_sources],
                project_registry=project_registry,
            )

        ids = {item["id"] for item in sources}
        urls = {item["url"] for item in sources}
        self.assertIn("fastapi-release-notes", ids)
        self.assertIn("project-doc-base", ids)
        self.assertIn("service-bot-api-overview", ids)
        self.assertIn("https://example.com/service-bot/api", urls)
        self.assertIn(
            "https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api",
            urls,
        )
        self.assertTrue(any(item["id"].startswith("service-bot-github-") for item in sources))

    def test_web_runtime_sources_reads_project_index_doc_knowledge_automatically(self):
        module = load_module(
            "web_sources_runtime",
            "skills/library/web-intelligence/scripts/web_sources_runtime.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            project_root = tmp / "service-bot"
            index_root = project_root / ".workflow" / "project-index-local"
            index_root.mkdir(parents=True, exist_ok=True)
            static_sources = tmp / "sources.json"
            project_registry = tmp / "project-registry.json"

            static_sources.write_text(json.dumps({"sources": []}, ensure_ascii=False), encoding="utf-8")
            project_registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "service-bot",
                                "name": "service-bot",
                                "path": str(project_root),
                                "index_dir": ".workflow/project-index-local",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (index_root / "doc-knowledge.json").write_text(
                json.dumps(
                    {
                        "doc_sources": [
                            {
                                "tag": "github",
                                "name": "GitHub REST API",
                                "url": "https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api",
                                "category": "api-doc",
                                "tags": ["official", "api", "github"],
                            }
                        ],
                        "repo_sources": [
                            {
                                "vendor": "github",
                                "official_repos": ["github/rest-api-description"],
                                "repo_queries": ["org:github rest api archived:false"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            sources = module.load_runtime_sources(static_sources, project_registry=project_registry)
            repo_targets = module.load_project_repo_targets(project_registry)

        self.assertTrue(any("docs.github.com" in item.get("url", "") for item in sources))
        self.assertIn("github/rest-api-description", repo_targets["official_repos"])
        self.assertTrue(any("rest api" in query for query in repo_targets["queries"]))

    def test_project_repo_targets_fallback_to_external_api_hosts_when_repo_sources_missing(self):
        module = load_module(
            "web_sources_runtime",
            "skills/library/web-intelligence/scripts/web_sources_runtime.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            project_root = tmp / "service-bot"
            index_root = project_root / ".workflow" / "project-index-local"
            index_root.mkdir(parents=True, exist_ok=True)
            project_registry = tmp / "project-registry.json"

            project_registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "service-bot",
                                "name": "service-bot",
                                "path": str(project_root),
                                "index_dir": ".workflow/project-index-local",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (index_root / "doc-knowledge.json").write_text(
                json.dumps(
                    {
                        "external_api_hosts": [
                            "api.polybaymax.com",
                            "dabaiquant.com",
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            repo_targets = module.load_project_repo_targets(project_registry)

        self.assertTrue(any("polybaymax api sdk" in query.lower() for query in repo_targets["queries"]))
        self.assertTrue(any("dabaiquant api sdk" in query.lower() for query in repo_targets["queries"]))

    def test_project_registry_auto_discovers_git_projects(self):
        module = load_module(
            "web_sources_runtime",
            "skills/library/web-intelligence/scripts/web_sources_runtime.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            explicit = tmp / "explicit-project"
            explicit.mkdir(parents=True, exist_ok=True)
            discovered_root = tmp / "projects"
            discovered = discovered_root / "auto-found-project"
            discovered.mkdir(parents=True, exist_ok=True)
            hidden_skill = tmp / ".openclaw" / "skills" / "frontend-design-ultimate"
            hidden_skill.mkdir(parents=True, exist_ok=True)
            hidden_tool = tmp / ".nvm"
            hidden_tool.mkdir(parents=True, exist_ok=True)
            workflow_repo = tmp / "workflow-infra"
            workflow_repo.mkdir(parents=True, exist_ok=True)
            upstream_repo = tmp / "lobster"
            upstream_repo.mkdir(parents=True, exist_ok=True)

            (discovered / "package.json").write_text('{"name":"auto-found-project"}', encoding="utf-8")
            (hidden_skill / "package.json").write_text('{"name":"skill-repo"}', encoding="utf-8")
            (hidden_tool / "package.json").write_text('{"name":"nvm"}', encoding="utf-8")
            (workflow_repo / "package.json").write_text('{"name":"workflow-infra"}', encoding="utf-8")
            (workflow_repo / "setup.py").write_text("# workflow installer\n", encoding="utf-8")
            (workflow_repo / "skills" / "library" / "project-delivery-pipeline").mkdir(parents=True)
            (upstream_repo / "package.json").write_text('{"name":"lobster"}', encoding="utf-8")
            self.init_git_repo(discovered, remote="https://github.com/example/auto-found-project.git")
            self.init_git_repo(hidden_skill, remote="https://github.com/example/skill-repo.git")
            self.init_git_repo(hidden_tool, remote="https://github.com/nvm-sh/nvm.git")
            self.init_git_repo(workflow_repo, remote="https://github.com/ORG/workflow-infra.git")
            self.init_git_repo(upstream_repo, remote="https://github.com/openclaw/lobster.git")

            project_registry = tmp / "project-registry.json"
            project_registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "explicit-project",
                                "name": "explicit-project",
                                "path": str(explicit),
                                "index_dir": ".workflow/project-index-local",
                            }
                        ],
                        "discovery": {
                            "enabled": True,
                            "scan_roots": [str(tmp)],
                            "max_depth": 4,
                            "max_projects": 10,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            projects = module.load_project_registry(project_registry)

        paths = {item["path"] for item in projects}
        self.assertIn(str(explicit), paths)
        self.assertIn(str(discovered), paths)
        self.assertIn(str(workflow_repo), paths)
        self.assertIn(str(upstream_repo), paths)
        self.assertNotIn(str(hidden_skill), paths)
        self.assertNotIn(str(hidden_tool), paths)
        business = next(item for item in projects if item["path"] == str(discovered))
        workflow = next(item for item in projects if item["path"] == str(workflow_repo))
        upstream = next(item for item in projects if item["path"] == str(upstream_repo))
        self.assertEqual(business["project_role"], "business")
        self.assertTrue(business["vendor_monitoring"]["enabled"])
        self.assertEqual(workflow["project_role"], "workflow-ops")
        self.assertFalse(workflow["vendor_monitoring"]["enabled"])
        self.assertEqual(upstream["project_role"], "upstream-reference")
        self.assertFalse(upstream["vendor_monitoring"]["enabled"])

    def test_project_repo_targets_ignore_vendor_monitoring_disabled_projects(self):
        module = load_module(
            "web_sources_runtime",
            "skills/library/web-intelligence/scripts/web_sources_runtime.py",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            biz_root = tmp / "service-bot"
            ops_root = tmp / "workflow-infra"
            for root in (biz_root, ops_root):
                index_root = root / ".workflow" / "project-index-local"
                index_root.mkdir(parents=True, exist_ok=True)
            project_registry = tmp / "project-registry.json"
            project_registry.write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "service-bot",
                                "name": "service-bot",
                                "path": str(biz_root),
                                "vendor_monitoring": {"enabled": True},
                            },
                            {
                                "id": "workflow-repo",
                                "name": "workflow-infra",
                                "path": str(ops_root),
                                "vendor_monitoring": {"enabled": False},
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (biz_root / ".workflow" / "project-index-local" / "doc-knowledge.json").write_text(
                json.dumps(
                    {
                        "repo_sources": [
                            {
                                "vendor": "github",
                                "official_repos": ["github/docs"],
                                "repo_queries": ["org:github rest api archived:false"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (ops_root / ".workflow" / "project-index-local" / "doc-knowledge.json").write_text(
                json.dumps(
                    {
                        "repo_sources": [
                            {
                                "vendor": "openclaw",
                                "official_repos": ["openclaw/openclaw"],
                                "repo_queries": ["org:openclaw openclaw archived:false"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            repo_targets = module.load_project_repo_targets(project_registry)

        self.assertIn("github/docs", repo_targets["official_repos"])
        self.assertNotIn("openclaw/openclaw", repo_targets["official_repos"])

    def test_skill4agent_query_pack_defaults_to_openclaw_focus(self):
        module = load_module(
            "github_web_evolution_runner",
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
        )
        queries = module.build_skill_query_list([], 5)
        self.assertEqual(len(queries), 5)
        self.assertTrue(all(query for query in queries))
        self.assertTrue(any("openclaw" in query.lower() for query in queries))
        self.assertTrue(any(any(token in query.lower() for token in ["skill", "hook", "plugin"]) for query in queries))

    def test_github_query_inputs_merge_project_repo_targets(self):
        module = load_module(
            "github_web_evolution_runner",
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
        )
        payload = module.build_repo_scan_inputs(
            raw_queries=["openclaw hooks plugins skills archived:false"],
            min_stars=80,
            max_queries=5,
            project_repo_targets={
                "queries": ["org:github rest api archived:false"],
                "official_repos": ["github/rest-api-description"],
            },
        )

        self.assertIn("github/rest-api-description", payload["official_repos"])
        self.assertTrue(any("stars:>=80" in query for query in payload["queries"]))
        self.assertTrue(any("org:github" in query for query in payload["queries"]))

    def test_search_skill4agent_skills_parses_json_payload(self):
        module = load_module(
            "github_web_evolution_runner",
            "skills/library/web-intelligence/scripts/github_web_evolution_runner.py",
        )

        class FakeProc:
            returncode = 0
            stdout = json.dumps(
                {
                    "totalResults": 1,
                    "returnedCount": 1,
                    "query": "github",
                    "skills": [
                        {
                            "skillId": "github-auth--ticruz38-skills",
                            "source": "ticruz38/skills",
                            "skillName": "github-auth",
                            "description": "GitHub API authentication and permission management for automation skills.",
                            "tags": "github-api-auth, key-management",
                            "categoryName": "工具与效率",
                            "totalInstalls": 1,
                            "relevance": 1,
                            "translation": {"has_translation": True, "translated_language": "zh"},
                            "script": {"has_script": True, "script_check_result": "safe"},
                        }
                    ],
                },
                ensure_ascii=False,
            ) + "\n- Searching for \"github\"..."
            stderr = ""

        original_run = module.subprocess.run
        original_which = module.shutil.which
        try:
            module.shutil.which = lambda value: value
            module.subprocess.run = lambda *args, **kwargs: FakeProc()
            items, log = module.search_skill4agent_skills(
                query="github",
                skill4agent_bin="skill4agent",
                limit=5,
                timeout=20,
            )
        finally:
            module.subprocess.run = original_run
            module.shutil.which = original_which

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["skillName"], "github-auth")
        self.assertTrue(log["ok"])
        self.assertEqual(log["returned_count"], 1)

if __name__ == "__main__":
    unittest.main()

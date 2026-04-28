import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts/openclaw-ops/smart_arb_live_bridge.py"


def diff_assignment_line(key: str, value: str) -> str:
    return "+" + key + "=" + value


def diff_json_assignment_line(key: str, value: str) -> str:
    return '+"' + key + '": "' + value + '",'


class SmartArbLiveBridgeTests(unittest.TestCase):
    def _load_bridge_module(self):
        spec = util.spec_from_file_location("smart_arb_live_bridge", BRIDGE)
        module = util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def test_echo_code_review_outputs_required_verdict(self):
        proc = subprocess.run(
            [sys.executable, str(BRIDGE), "--stage", "code_review", "--agent-mode", "echo"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("Final verdict: pass", proc.stdout)
        self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)

    def test_echo_requirements_and_solution_review_output_required_verdicts(self):
        cases = {
            "requirements_review": "Final verdict: ready_for_solution",
            "solution_review": "Final verdict: ready_for_implement",
        }
        for stage, expected in cases.items():
            with self.subTest(stage=stage):
                proc = subprocess.run(
                    [sys.executable, str(BRIDGE), "--stage", stage, "--agent-mode", "echo"],
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(0, proc.returncode, proc.stderr)
                self.assertIn(expected, proc.stdout)
                self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)

    def test_project_dir_defaults_to_pipeline_agent_repo_dir(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(
            os.environ,
            {"PIPELINE_AGENT_REPO_DIR": tmpdir},
            clear=False,
        ):
            parser = bridge.build_parser()
            args = parser.parse_args(["--stage", "external_research", "--agent-mode", "echo"])

        self.assertEqual(Path(tmpdir), args.project_dir)

    def test_repair_context_can_be_supplied_inline_env(self):
        bridge = self._load_bridge_module()
        with mock.patch.dict(os.environ, {"PIPELINE_REPAIR_CONTEXT": "previous failure evidence"}, clear=False):
            self.assertEqual("previous failure evidence", bridge.repair_context_text())

    def test_extract_hermes_session_id_from_cli_output(self):
        bridge = self._load_bridge_module()

        self.assertEqual("abc_123", bridge.extract_hermes_session_id("session_id: abc_123\nok"))
        self.assertEqual("", bridge.extract_hermes_session_id("no session here"))

    def test_memory_writeback_uses_pipeline_memory_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()
            writeback = run_dir / "writeback_report.md"
            writeback.write_text("# Writeback\n\nBridge memory test.\n", encoding="utf-8")
            project_memory_dir = tmp / "memory" / "demo"

            env = dict(os.environ)
            env.update(
                {
                    "PIPELINE_PROJECT_KEY": "demo",
                    "PIPELINE_PROJECT_MEMORY_DIR": str(project_memory_dir),
                    "PIPELINE_WRITEBACK_REPORT_FILE": str(writeback),
                }
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "memory_writeback",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(ROOT),
                    "--python-bin",
                    sys.executable,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)
            changelog = project_memory_dir / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            record = json.loads(changelog.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("Bridge memory test", record["content"])

    def test_git_publish_commits_with_chinese_message_and_pushes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            remote = tmp / "remote.git"
            repo.mkdir()
            git_kwargs = {"cwd": repo, "check": True, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
            subprocess.run(["git", "init", "-b", "main"], **git_kwargs)
            subprocess.run(["git", "config", "user.name", "Test"], **git_kwargs)
            subprocess.run(["git", "config", "user.email", "test@example.com"], **git_kwargs)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], **git_kwargs)
            subprocess.run(["git", "commit", "-m", "初始化"], **git_kwargs)
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
            subprocess.run(["git", "remote", "add", "origin", str(remote)], **git_kwargs)
            subprocess.run(["git", "push", "origin", "main"], **git_kwargs)
            (repo / "feature.txt").write_text("published\n", encoding="utf-8")
            requirement_file = tmp / "requirement.txt"
            requirement_file.write_text("提交已经审核通过的代码变更", encoding="utf-8")

            env = dict(os.environ)
            env.update(
                {
                    "PIPELINE_REQUIREMENT_FILE": str(requirement_file),
                    "PIPELINE_RUN_DIR": str(tmp / "run"),
                }
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "git_publish",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(repo),
                    "--git-remote",
                    "origin",
                    "--git-branch",
                    "main",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            self.assertIn("LIVE_BRIDGE_STATUS: pass", proc.stdout)
            message = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
            self.assertIn("交付: 提交已审核的项目变更", message)
            self.assertIn("变更说明:", message)
            remote_log = subprocess.run(
                ["git", "--git-dir", str(remote), "log", "-1", "--pretty=%B", "main"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
            self.assertIn("交付: 提交已审核的项目变更", remote_log)

    def test_git_publish_redacts_requirement_secrets_from_commit_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            remote = tmp / "remote.git"
            repo.mkdir()
            git_kwargs = {"cwd": repo, "check": True, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
            subprocess.run(["git", "init", "-b", "main"], **git_kwargs)
            subprocess.run(["git", "config", "user.name", "Test"], **git_kwargs)
            subprocess.run(["git", "config", "user.email", "test@example.com"], **git_kwargs)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], **git_kwargs)
            subprocess.run(["git", "commit", "-m", "初始化"], **git_kwargs)
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
            subprocess.run(["git", "remote", "add", "origin", str(remote)], **git_kwargs)
            subprocess.run(["git", "push", "origin", "main"], **git_kwargs)
            (repo / "feature.txt").write_text("published\n", encoding="utf-8")
            fake_pat = "ghp_" + "123456789012345678901234567890123456"
            requirement_file = tmp / "requirement.txt"
            requirement_file.write_text(
                "请发布代码\n"
                f"api_key={fake_pat}\n"
                "password=should-not-leak\n",
                encoding="utf-8",
            )

            env = dict(os.environ)
            env.update(
                {
                    "PIPELINE_REQUIREMENT_FILE": str(requirement_file),
                    "PIPELINE_RUN_DIR": str(tmp / "run"),
                }
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "git_publish",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(repo),
                    "--git-remote",
                    "origin",
                    "--git-branch",
                    "main",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            message = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
            self.assertIn("需求摘要:", message)
            self.assertIn("[REDACTED]", message)
            self.assertNotIn(fake_pat, message)
            self.assertNotIn("should-not-leak", message)

    def test_staged_diff_secret_scan_allows_env_names_and_test_placeholders(self):
        bridge = self._load_bridge_module()
        diff = "\n".join(
            [
                "diff --git a/.env.example b/.env.example",
                "+++ b/.env.example",
                "+DASHBOARD_BASIC_PASS=rotatable-pass",
                "+BASIC_PASS=rotatable-pass",
                "+password: 替换为实际强密码",
                "+Authorization: Basic Auth",
                "+Authorization: Bearer <token>",
                "+api_key=${EXCHANGE_API_KEY}",
                diff_json_assignment_line("api_key", "${EXCHANGE_API_KEY}"),
                diff_json_assignment_line("password", "replace-me"),
                "+password = os.getenv('DASHBOARD_BASIC_PASS', '')",
                "+README says BASIC_PASS is the env var name",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)
        self.assertFalse(bridge.staged_diff_has_secret(diff))
        self.assertTrue(findings)
        self.assertTrue(all(not finding["blocking"] for finding in findings))

    def test_staged_diff_secret_scan_allows_markdown_inline_basic_auth_placeholder(self):
        bridge = self._load_bridge_module()
        diff = "\n".join(
            [
                "diff --git a/memory/PITFALLS.md b/memory/PITFALLS.md",
                "+++ b/memory/PITFALLS.md",
                "@@ -0,0 +1,2 @@",
                "+" + "事实：README 占位说明：" + "Authorization" + ": Basic Auth 测试说明不应误报。",
                "+" + "说明：`" + "Authorization" + ": Bearer <token>` 只是文档占位，不是真实 token。",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertFalse(bridge.staged_diff_has_secret(diff))
        self.assertTrue(findings)
        self.assertTrue(all(not finding["blocking"] for finding in findings))

    def test_staged_diff_secret_scan_blocks_markdown_inline_real_authorization_value(self):
        bridge = self._load_bridge_module()
        cases = [
            "+" + "说明：" + "Authorization" + ": Bearer live-real-short-token 不应进入文档。",
            "+" + "说明：" + "Authorization" + ": Bearer live-real-short-token test only 也必须阻断。",
            "+" + "说明：" + "Authorization" + ": Bearer live-real-short-token example only 也必须阻断。",
            "+" + "说明：" + "Authorization" + ": Basic Auth live-real-short-token test only 也必须阻断。",
            "+" + "说明：" + "Authorization" + ": Basic Auth live-real-short-token example only 也必须阻断。",
        ]
        for line in cases:
            with self.subTest(line=line):
                diff = "\n".join(
                    [
                        "diff --git a/README.md b/README.md",
                        "+++ b/README.md",
                        "@@ -0,0 +1 @@",
                        line,
                    ]
                )
                findings = bridge.staged_diff_secret_findings(diff)

                self.assertTrue(bridge.staged_diff_has_secret(diff))
                self.assertEqual(1, len(findings))
                self.assertEqual("sensitive_header_assignment", findings[0]["rule"])
                self.assertTrue(findings[0]["blocking"])

    def test_redact_text_handles_quoted_sensitive_assignments(self):
        bridge = self._load_bridge_module()
        field_one = "api" + "_key"
        field_two = "pass" + "word"
        field_three = "sec" + "ret"
        text = "\n".join(
            [
                f'{{"{field_one}": "json-live-secret", "safe": true}}',
                f'"{field_two}" = "toml-local-doc-example"',
                f"`{field_three}` = `shell-local-doc-example`",
            ]
        )

        redacted = bridge.redact_text(text)

        self.assertIn("[REDACTED]", redacted)
        self.assertNotIn("json-live-secret", redacted)
        self.assertNotIn("toml-local-doc-example", redacted)
        self.assertNotIn("shell-local-doc-example", redacted)

    def test_staged_diff_secret_scan_blocks_real_secret_shapes(self):
        bridge = self._load_bridge_module()
        openai_value = "sk-" + "1234567890abcdefghijklmnop"
        github_value = "ghp_" + "123456789012345678901234567890123456"
        aws_value = "AKIA" + "1234567890ABCDEF"
        slack_value = "xoxb-" + "1234567890-abcdef"
        cases = [
            diff_assignment_line("OPENAI_API_KEY", openai_value),
            diff_assignment_line("GITHUB_TOKEN", github_value),
            diff_assignment_line("AWS_ACCESS_KEY_ID", aws_value),
            diff_assignment_line("SLACK_TOKEN", slack_value),
            "+" + "Cookie" + ": " + "sessionid" + "=" + "short-real-value",
            diff_assignment_line("EXCHANGE_API_KEY", "live-but-short"),
            diff_assignment_line("OAUTH_SECRET", "abcdefghijklmno1234567890abcdefghijklmno123456"),
        ]
        for line in cases:
            with self.subTest(line=line):
                self.assertTrue(bridge.staged_diff_has_secret(f"diff --git a/x b/x\n+++ b/x\n{line}\n"))

    def test_staged_diff_secret_scan_blocks_short_real_values_in_example_contexts(self):
        bridge = self._load_bridge_module()
        cases = [
            (
                "docs/leak.md",
                diff_assignment_line("EXCHANGE_API_KEY", "live-but-short"),
            ),
            (
                ".env.example",
                diff_assignment_line("OAUTH_SECRET", "short-real-secret"),
            ),
            (
                "tests/test_env.py",
                diff_assignment_line("TEST_EXCHANGE_API_KEY", "live-but-short"),
            ),
            (
                "config.json",
                diff_json_assignment_line("api_key", "live-but-short"),
            ),
            (
                "settings.toml",
                '+"' + "password" + '" = "' + "local-doc-example" + '"',
            ),
        ]
        for path, line in cases:
            with self.subTest(path=path, line=line):
                diff = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{line}\n"
                findings = bridge.staged_diff_secret_findings(diff)
                self.assertTrue(bridge.staged_diff_has_secret(diff))
                self.assertEqual(1, len(findings))
                self.assertTrue(findings[0]["blocking"])
                self.assertEqual("sensitive_assignment", findings[0]["rule"])

    def test_staged_diff_secret_scan_blocks_hardcoded_getenv_fallback_secret(self):
        bridge = self._load_bridge_module()
        fake_value = "ghp_" + "123456789012345678901234567890123456"
        diff = "\n".join(
            [
                "diff --git a/config.py b/config.py",
                "--- a/config.py",
                "+++ b/config.py",
                "@@ -0,0 +1 @@",
                "+password = os.getenv('DASHBOARD_BASIC_PASS', '" + fake_value + "')",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertTrue(bridge.staged_diff_has_secret(diff))
        self.assertEqual("known_secret_pattern", findings[0]["rule"])
        self.assertTrue(findings[0]["blocking"])
        self.assertIn("[REDACTED]", findings[0]["snippet"])
        self.assertNotIn(fake_value, findings[0]["snippet"])

    def test_staged_diff_secret_scan_blocks_short_getenv_fallback_secret(self):
        bridge = self._load_bridge_module()
        diff_line = "+" + "api" + "_key" + " = " + "os.getenv" + "('EXCHANGE_API_KEY', 'live-but-short')"
        diff = "\n".join(
            [
                "diff --git a/config.py b/config.py",
                "--- a/config.py",
                "+++ b/config.py",
                "@@ -0,0 +1 @@",
                diff_line,
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertTrue(bridge.staged_diff_has_secret(diff))
        self.assertEqual(1, len(findings))
        self.assertEqual("sensitive_assignment", findings[0]["rule"])
        self.assertTrue(findings[0]["blocking"])

    def test_staged_diff_secret_scan_blocks_unquoted_high_entropy_assignment(self):
        bridge = self._load_bridge_module()
        long_value = "abcdefghijklmnopqrstuvwxyz" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "1234567890"
        diff = "\n".join(
            [
                "diff --git a/.env b/.env",
                "--- a/.env",
                "+++ b/.env",
                "@@ -0,0 +1 @@",
                "+" + "SAFE_VALUE" + "=" + long_value,
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertTrue(bridge.staged_diff_has_secret(diff))
        self.assertEqual(1, len(findings))
        self.assertEqual("high_entropy_secret_value", findings[0]["rule"])
        self.assertTrue(findings[0]["blocking"])

    def test_staged_diff_secret_scan_blocks_pem_private_key_lines(self):
        bridge = self._load_bridge_module()
        begin_marker = "-----BEGIN " + "PRIVATE KEY" + "-----"
        end_marker = "-----END " + "PRIVATE KEY" + "-----"
        private_material = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" + "A" * 24 + "=="
        diff = "\n".join(
            [
                "diff --git a/secrets/private.key b/secrets/private.key",
                "+++ b/secrets/private.key",
                "@@ -0,0 +1,3 @@",
                "+" + begin_marker,
                "+" + private_material,
                "+" + end_marker,
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertTrue(bridge.staged_diff_has_secret(diff))
        self.assertIn("private_key_marker", {finding["rule"] for finding in findings})
        self.assertIn("private_key_material", {finding["rule"] for finding in findings})
        self.assertTrue(all(finding["blocking"] for finding in findings))
        self.assertTrue(all(finding["snippet"] == "[REDACTED_PRIVATE_KEY]" for finding in findings))
        self.assertNotIn(private_material, "\n".join(finding["snippet"] for finding in findings))

    def test_staged_diff_secret_scan_reports_redacted_file_line_and_rule(self):
        bridge = self._load_bridge_module()
        fake_value = "sk-" + "1234567890abcdefghijklmnop"
        diff = "\n".join(
            [
                "diff --git a/config.py b/config.py",
                "--- a/config.py",
                "+++ b/config.py",
                "@@ -0,0 +1,2 @@",
                diff_assignment_line("OPENAI_API_KEY", fake_value),
                "+SAFE_VALUE=1",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertEqual(1, len(findings))
        self.assertEqual("config.py", findings[0]["file"])
        self.assertEqual(1, findings[0]["line"])
        self.assertEqual("known_secret_pattern", findings[0]["rule"])
        self.assertEqual("high", findings[0]["risk"])
        self.assertTrue(findings[0]["blocking"])
        self.assertIn("[REDACTED]", findings[0]["snippet"])
        self.assertNotIn(fake_value, findings[0]["snippet"])

    def test_staged_diff_secret_scan_ignores_removed_secret_lines(self):
        bridge = self._load_bridge_module()
        fake_value = "sk-" + "1234567890abcdefghijklmnop"
        diff = "\n".join(
            [
                "diff --git a/.env b/.env",
                "--- a/.env",
                "+++ b/.env",
                "-" + "OPENAI_API_KEY" + "=" + fake_value,
                "+OPENAI_API_KEY=${OPENAI_API_KEY}",
            ]
        )

        self.assertFalse(bridge.staged_diff_has_secret(diff))

    def test_git_publish_blocks_real_secret_with_redacted_findings(self):
        fake_value = "sk-" + "1234567890abcdefghijklmnop"
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            git_kwargs = {"cwd": repo, "check": True, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
            subprocess.run(["git", "init", "-b", "main"], **git_kwargs)
            subprocess.run(["git", "config", "user.name", "Test"], **git_kwargs)
            subprocess.run(["git", "config", "user.email", "test@example.com"], **git_kwargs)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], **git_kwargs)
            subprocess.run(["git", "commit", "-m", "初始化"], **git_kwargs)
            (repo / "config.py").write_text(f"OPENAI_API_KEY={fake_value}\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(BRIDGE),
                    "--stage",
                    "git_publish",
                    "--agent-mode",
                    "hermes",
                    "--project-dir",
                    str(repo),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(9, proc.returncode, proc.stderr + proc.stdout)
        self.assertIn("## Secret Scan Findings", proc.stdout)
        self.assertIn("config.py:1", proc.stdout)
        self.assertIn("known_secret_pattern", proc.stdout)
        self.assertIn("[REDACTED]", proc.stdout)
        self.assertNotIn(fake_value, proc.stdout)

    def test_staged_diff_secret_scan_allows_basic_auth_test_placeholders(self):
        bridge = self._load_bridge_module()
        diff = "\n".join(
            [
                "diff --git a/tests/test_basic_auth_proxy.py b/tests/test_basic_auth_proxy.py",
                "+++ b/tests/test_basic_auth_proxy.py",
                "@@ -0,0 +1,3 @@",
                "+DASHBOARD_BASIC_USER=test-user",
                "+DASHBOARD_BASIC_PASS=test-pass",
                "+Authorization: Basic Auth",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertFalse(bridge.staged_diff_has_secret(diff))
        self.assertTrue(findings)
        self.assertTrue(all(not finding["blocking"] for finding in findings))

    def test_staged_diff_secret_scan_blocks_non_placeholder_example_assignments(self):
        bridge = self._load_bridge_module()
        diff = "\n".join(
            [
                "diff --git a/docs/basic-auth.md b/docs/basic-auth.md",
                "+++ b/docs/basic-auth.md",
                "@@ -0,0 +1,2 @@",
                "+" + "password" + " = " + "local-doc-example",
                "+" + "api_key" + " = " + "sample-dashboard-key",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertTrue(bridge.staged_diff_has_secret(diff))
        self.assertEqual({"high"}, {finding["risk"] for finding in findings})
        self.assertEqual({"sensitive_assignment"}, {finding["rule"] for finding in findings})
        self.assertTrue(all(finding["blocking"] for finding in findings))

    def test_staged_diff_secret_scan_allows_scanner_code_diff(self):
        bridge = self._load_bridge_module()
        diff = "\n".join(
            [
                "diff --git a/scripts/openclaw-ops/smart_arb_live_bridge.py b/scripts/openclaw-ops/smart_arb_live_bridge.py",
                "+++ b/scripts/openclaw-ops/smart_arb_live_bridge.py",
                "@@ -0,0 +1,4 @@",
                "+SECRET_PLACEHOLDER_RE = re.compile(",
                "+secret_findings = staged_diff_secret_findings(staged_diff.stdout or \"\")",
                "+def test_staged_diff_secret_scan_blocks_non_placeholder_example_assignments(self):",
                "+safe_value = \"a\" * 64",
            ]
        )

        findings = bridge.staged_diff_secret_findings(diff)

        self.assertFalse(bridge.staged_diff_has_secret(diff))
        self.assertTrue(all(not finding["blocking"] for finding in findings))

    def test_external_research_prompt_forbids_file_edits_and_allows_local_only_pass(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")

        with mock.patch.dict(os.environ, {}, clear=True):
            prompt = bridge.stage_prompt("external_research", args, "只做本地环境检查")

        self.assertIn("NO_EXTERNAL_LOOKUP_NEEDED", prompt)
        self.assertIn("Do not modify files", prompt)
        self.assertIn("Return the stage evidence in your final answer/stdout only", prompt)
        self.assertNotIn("Stage output file hint", prompt)

    def test_external_research_recovers_local_only_output_from_session_file(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profile_dir = tmp / "profiles" / "spreadagent"
            sessions_dir = profile_dir / "sessions"
            sessions_dir.mkdir(parents=True)
            session_id = "20260426_154049_316711"
            (sessions_dir / f"session_{session_id}.json").write_text(
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "research"},
                            {
                                "role": "assistant",
                                "content": "NO_EXTERNAL_LOOKUP_NEEDED\nlocal evidence from prior run",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                runtime_home=tmp,
                profile="spreadagent",
                hermes_bin=Path("/tmp/hermes"),
                provider="openai-codex",
                model="gpt-5.5",
                max_turns=24,
                allow_yolo=False,
                project_dir=ROOT,
                home=tmp,
            )
            out = StringIO()

            with mock.patch.object(
                bridge,
                "run_command",
                return_value=subprocess.CompletedProcess(
                    ["hermes"],
                    0,
                    "",
                    f"session_id: {session_id}\n",
                ),
            ), redirect_stdout(out):
                rc = bridge.run_hermes_stage("external_research", args)

        text = out.getvalue()
        self.assertEqual(0, rc)
        self.assertIn("# recovered_session_output", text)
        self.assertIn("NO_EXTERNAL_LOOKUP_NEEDED", text)
        self.assertIn("LIVE_BRIDGE_STATUS: pass", text)

    def test_non_code_hermes_env_hides_pipeline_artifact_paths(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(
            home=Path("/tmp/home"),
            hermes_bin=Path("/tmp/hermes/bin/hermes"),
        )
        profile_dir = Path("/tmp/hermes/profile")

        with mock.patch.dict(
            os.environ,
            {
                "PIPELINE_RESEARCH_REPORT_FILE": "/tmp/run/research_report.md",
                "PIPELINE_DELIVERY_PLAN_FILE": "/tmp/run/delivery_plan.json",
                "PIPELINE_PATCH_SUMMARY_FILE": "/tmp/run/patch_summary.md",
                "PIPELINE_CODE_REVIEW_FILE": "/tmp/run/code_review.md",
            },
            clear=True,
        ):
            research_env = bridge.bridge_env(args, profile_dir, "external_research")
            req_review_env = bridge.bridge_env(args, profile_dir, "requirements_review")
            sol_review_env = bridge.bridge_env(args, profile_dir, "solution_review")
            review_env = bridge.bridge_env(args, profile_dir, "code_review")
            code_env = bridge.bridge_env(args, profile_dir, "code_execution")

        self.assertNotIn("PIPELINE_RESEARCH_REPORT_FILE", research_env)
        self.assertNotIn("PIPELINE_PATCH_SUMMARY_FILE", research_env)
        self.assertNotIn("PIPELINE_DELIVERY_PLAN_FILE", sol_review_env)
        self.assertNotIn("PIPELINE_RESEARCH_REPORT_FILE", req_review_env)
        self.assertNotIn("PIPELINE_PATCH_SUMMARY_FILE", sol_review_env)
        self.assertNotIn("PIPELINE_CODE_REVIEW_FILE", review_env)
        self.assertEqual("/tmp/run/delivery_plan.json", code_env["PIPELINE_DELIVERY_PLAN_FILE"])
        self.assertEqual("/tmp/run/research_report.md", code_env["PIPELINE_RESEARCH_REPORT_FILE"])
        self.assertEqual("/tmp/run/patch_summary.md", code_env["PIPELINE_PATCH_SUMMARY_FILE"])

    def test_code_execution_prompt_includes_prior_stage_context(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "research_report.md").write_text("P0 only; do not implement S1\n", encoding="utf-8")
            (run_dir / "delivery_plan.json").write_text('{"schema_version":"delivery-plan/v1","target_files":[]}\n', encoding="utf-8")
            (run_dir / "solution.md").write_text("Solution says memory first\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"PIPELINE_RUN_DIR": str(run_dir)}, clear=True):
                prompt = bridge.stage_prompt("code_execution", args, "按 P0 顺序执行")

        self.assertIn("Prior accepted stage context", prompt)
        self.assertIn("P0 only; do not implement S1", prompt)
        self.assertIn("delivery-plan/v1", prompt)
        self.assertIn("Solution says memory first", prompt)
        self.assertIn("delivery_plan.json", prompt)
        self.assertIn("Do not implement later-phase strategy work", prompt)

    def test_pipeline_context_redacts_sensitive_context_values(self):
        bridge = self._load_bridge_module()
        args = SimpleNamespace(project_dir=ROOT, profile="spreadagent")
        fake_github_token = "ghp_" + "123456789012345678901234567890123456"

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "research_report.md").write_text(
                "Authorization: Bearer should-not-leak\n"
                "api_key=should-not-leak-either\n"
                f"token only: {fake_github_token}\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"PIPELINE_RUN_DIR": str(run_dir)}, clear=True):
                prompt = bridge.stage_prompt("code_execution", args, "检查上下文脱敏")

        self.assertIn("Authorization: [REDACTED]", prompt)
        self.assertIn("api_key: [REDACTED]", prompt)
        self.assertNotIn("should-not-leak", prompt)
        self.assertNotIn("should-not-leak-either", prompt)
        self.assertNotIn(fake_github_token, prompt)

    def test_run_command_returns_evidence_on_timeout(self):
        bridge = self._load_bridge_module()
        proc = bridge.run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=ROOT,
            timeout=1,
        )

        self.assertEqual(124, proc.returncode)
        self.assertIn("timed out", proc.stderr)

    def test_default_verification_uses_compile_smoke_not_unittest_discover(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, {}, clear=True):
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "demo.py").write_text("value = 1\n", encoding="utf-8")
            tests_dir = tmp / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_demo.py").write_text("raise RuntimeError('should not be discovered')\n", encoding="utf-8")
            args = SimpleNamespace(project_dir=tmp, python_bin=Path(sys.executable), skip_tests=False)

            commands = bridge.verification_commands(args)

        self.assertIn("git diff --check", commands)
        self.assertTrue(any("-m compileall -q scripts" in command for command in commands))
        self.assertFalse(any("unittest discover" in command for command in commands))

    def test_run_verification_reports_timeout_from_cli_argument(self):
        bridge = self._load_bridge_module()
        slow_command = subprocess.list2cmdline([sys.executable, "-c", "import time; time.sleep(5)"])
        args = SimpleNamespace(
            project_dir=ROOT,
            python_bin=Path(sys.executable),
            skip_tests=False,
            verification_command_timeout_seconds=1,
        )
        out = StringIO()

        with mock.patch.dict(os.environ, {"SMART_ARB_LIVE_BRIDGE_TEST_COMMAND": slow_command}, clear=False), redirect_stdout(out):
            rc = bridge.run_verification(args)

        text = out.getvalue()
        self.assertEqual(1, rc)
        self.assertIn("Verification command timeout seconds: 1", text)
        self.assertIn("Command timed out after 1 seconds.", text)
        self.assertIn("LIVE_BRIDGE_STATUS: fail", text)

    def test_deployment_restarts_api_with_new_tmux_session_cwd(self):
        bridge = self._load_bridge_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            api_cwd = tmp / "智能多平台套利"
            uvicorn_bin = tmp / "bin" / "uvicorn"
            api_cwd.mkdir()
            uvicorn_bin.parent.mkdir()
            uvicorn_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            args = SimpleNamespace(
                allow_internal_api_restart=True,
                api_cwd=api_cwd,
                uvicorn_bin=uvicorn_bin,
                api_session="smart-arb-api",
                project_dir=tmp,
                deploy_wait_seconds=0,
            )
            calls: list[list[str] | str] = []

            def fake_run_command(command, cwd=None, shell=False):
                calls.append(command)
                if command == ["tmux", "has-session", "-t", "smart-arb-api"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, "{\"status\":\"ok\",\"strategy_running\":false}\n", "")

            with mock.patch.object(bridge, "run_command", side_effect=fake_run_command), mock.patch.object(bridge.time, "sleep"):
                rc = bridge.run_deployment(args)

            self.assertEqual(0, rc)
            self.assertIn(["tmux", "kill-session", "-t", "smart-arb-api"], calls)
            new_session = next(call for call in calls if isinstance(call, list) and call[:4] == ["tmux", "new-session", "-d", "-s"])
            self.assertIn("-c", new_session)
            self.assertEqual(str(api_cwd), new_session[new_session.index("-c") + 1])
            self.assertFalse(any(isinstance(call, list) and "send-keys" in call for call in calls))


if __name__ == "__main__":
    unittest.main()

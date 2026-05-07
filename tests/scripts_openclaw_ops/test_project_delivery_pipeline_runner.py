import argparse
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    ROOT
    / "skills"
    / "library"
    / "project-delivery-pipeline"
    / "scripts"
    / "pipeline_runner.py"
)
POLICY_WORKFLOW_PATH = (
    ROOT
    / "skills"
    / "library"
    / "control-plane-ops"
    / "scripts"
    / "policy"
    / "policy_workflow.py"
)
_spec = importlib.util.spec_from_file_location("project_delivery_pipeline_runner", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

PipelineConfig = _mod.PipelineConfig
run_pipeline = _mod.run_pipeline


def load_policy_workflow_module():
    sys.path.insert(0, str(POLICY_WORKFLOW_PATH.parent))
    try:
        spec = importlib.util.spec_from_file_location("project_delivery_policy_workflow", POLICY_WORKFLOW_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("project_delivery_policy_workflow", None)
        sys.path.pop(0)


class ProjectDeliveryPipelineRunnerTests(unittest.TestCase):
    def _write_stage_review_script(
        self,
        path: Path,
        code_review_check: str = "",
        reviewer_role: str = "reviewer-a",
        reviewer_model = None,
    ) -> None:
        check_body = "\n".join(f"    {line}" for line in code_review_check.strip().splitlines()) or "    pass"
        reviewer_model = reviewer_model or f"test-model-{reviewer_role}"
        path.write_text(
            (
                "import os, pathlib\n"
                "stage = os.environ.get('PIPELINE_STAGE_NAME', '')\n"
                "if stage == 'code_review':\n"
                f"{check_body}\n"
                "verdicts = {\n"
                "    'requirements_review': 'ready_for_solution',\n"
                "    'solution_review': 'ready_for_implement',\n"
                "    'code_review': 'pass',\n"
                "}\n"
                "print(f\"Final verdict: {verdicts.get(stage, 'pass')}\")\n"
                "print('Confidence: high')\n"
                f"print('Reviewer role: {reviewer_role}')\n"
                "print('Reviewer provider: test-provider')\n"
                f"print('Reviewer model: {reviewer_model}')\n"
            ),
            encoding="utf-8",
        )

    def _write_review_pair(self, scripts_dir: Path, code_review_check: str = "") -> tuple[Path, Path]:
        review_a = scripts_dir / "review_a.py"
        review_b = scripts_dir / "review_b.py"
        self._write_stage_review_script(review_a, code_review_check, "reviewer-a", "test-model-a")
        self._write_stage_review_script(review_b, code_review_check, "reviewer-b", "test-model-b")
        return review_a, review_b

    def test_dry_run_happy_path_creates_required_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the full coding delivery pipeline.",
                    workspace_root=Path(tmp),
                    run_id="happy",
                    dry_run=True,
                )
            )

            run_dir = Path(tmp) / "happy"
            self.assertEqual("completed", state["status"])
            self.assertEqual("none", state["next_action"])
            for name in (
                "run_meta",
                "context_snapshot",
                "project_memory_context",
                "git_repository_context",
                "graphify_context",
                "external_research",
                "requirements_package",
                "requirements_review",
                "delivery_plan",
                "solution_package",
                "graphify_scope_validation",
                "solution_review",
                "pre_execution_risk",
                "plan_publish",
                "code_execution",
                "verification",
                "code_review",
                "acceptance",
                "writeback",
                "failure_learning_check",
            ):
                self.assertIn(name, state["artifacts"])
                self.assertTrue(Path(state["artifacts"][name]).exists(), name)
            self.assertTrue((run_dir / "pipeline_state.json").exists())
            risk = json.loads(Path(state["artifacts"]["pre_execution_risk"]).read_text(encoding="utf-8"))
            self.assertEqual("auto_execute", risk["execution_decision"])
            plan_publish = Path(state["artifacts"]["plan_publish"]).read_text(encoding="utf-8")
            self.assertIn("群回传执行方案", plan_publish)
            self.assertIn("已收集上下文", plan_publish)
            memory_dir = Path(tmp) / "project-memory" / "demo"
            self.assertTrue((memory_dir / "RETRIEVAL_MANIFEST.json").exists())



    def test_graphify_context_and_scope_validation_use_external_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
            index_root = tmp_path / "indexes"
            graph_out = index_root / repo.name / "graphify-out"
            graph_out.mkdir(parents=True)
            (graph_out / "graph.json").write_text(
                json.dumps({"nodes": [{"id": "app", "label": "App", "community": 1}], "links": []}),
                encoding="utf-8",
            )
            (graph_out / "GRAPH_REPORT.md").write_text(
                "# Report\n\n## God Nodes\n- App\n\n## Suggested Questions\n- What owns App?\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"PIPELINE_GRAPHIFY_INDEX_ROOT": str(index_root)}):
                state = run_pipeline(
                    PipelineConfig(
                        project_key="demo",
                        requirement="Update app.py safely; no trading.",
                        workspace_root=tmp_path / "runs",
                        run_id="graphify",
                        dry_run=True,
                        command_cwd=repo,
                        runtime_host="hermes",
                        runtime_home=str(tmp_path / "runtime"),
                        source_urls=("discord:spreadagent",),
                    )
                )

            context = Path(state["artifacts"]["graphify_context"]).read_text(encoding="utf-8")
            self.assertIn("status: `available`", context)
            self.assertIn("nodes: `1`", context)
            validation = json.loads(Path(state["artifacts"]["graphify_scope_validation_payload"]).read_text(encoding="utf-8"))
            self.assertIn(validation["scope_status"], {"pass", "warning"})
            self.assertFalse(any(item["severity"] == "block" for item in validation["findings"]))
            risk = json.loads(Path(state["artifacts"]["pre_execution_risk"]).read_text(encoding="utf-8"))
            self.assertEqual("auto_execute", risk["execution_decision"])
            plan_publish = Path(state["artifacts"]["plan_publish"]).read_text(encoding="utf-8")
            self.assertIn("graphify_context.md", plan_publish)

    def test_graphify_scope_validation_blocks_cross_repo_and_credentials_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            config = PipelineConfig(project_key="demo", command_cwd=repo, runtime_home=str(Path(tmp) / "runtime"))
            runtime = {"runtime_home": str(Path(tmp) / "runtime")}
            safe_plan = {
                "target_files": [{"path": "missing_module.py"}],
                "verification_commands": [{"command": "git diff --check"}],
                "out_of_scope": ["Do not use secrets, credentials, private keys, cookies, or auth state files.", "Do not start real trading."],
            }
            safe_payload = _mod.validate_graphify_scope(config, runtime, safe_plan, {})
            self.assertEqual("warning", safe_payload["scope_status"])
            self.assertFalse(any(item["severity"] == "block" for item in safe_payload["findings"]))

            unsafe_plan = {
                "target_files": [{"path": str(Path(tmp) / "outside" / "credential.json")}],
                "verification_commands": [],
            }
            unsafe_payload = _mod.validate_graphify_scope(config, runtime, unsafe_plan, {})
            self.assertEqual("block", unsafe_payload["scope_status"])
            reasons = "\n".join(item["reason"] for item in unsafe_payload["findings"])
            self.assertIn("outside the command repository", reasons)

    def test_graphify_scope_validation_allows_stock_token_business_route_and_safety_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            target = repo / "智能多平台套利" / "api" / "routes"
            target.mkdir(parents=True)
            (target / "stock_tokens.py").write_text("def route():\n    return 'ok'\n", encoding="utf-8")
            config = PipelineConfig(project_key="demo", command_cwd=repo, runtime_home=str(Path(tmp) / "runtime"))
            runtime = {"runtime_home": str(Path(tmp) / "runtime")}
            safe_plan = {
                "target_files": [{"path": "智能多平台套利/api/routes/stock_tokens.py"}],
                "implementation_steps": [
                    {"description": "Keep PRODUCTION_TRADING_ENABLED=false and do not place orders."},
                ],
                "verification_commands": [
                    {"command": _mod.added_line_safety_scan_command()},
                ],
                "out_of_scope": ["Do not use secrets, credentials, private keys, cookies, or auth state files."],
            }
            payload = _mod.validate_graphify_scope(config, runtime, safe_plan, {})

            self.assertIn(payload["scope_status"], {"pass", "warning"})
            self.assertFalse(any(item["severity"] == "block" for item in payload["findings"]))

    def test_graphify_scope_validation_blocks_positive_trading_even_with_negated_safety_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
            config = PipelineConfig(project_key="demo", command_cwd=repo, runtime_home=str(Path(tmp) / "runtime"))
            runtime = {"runtime_home": str(Path(tmp) / "runtime")}
            risky_plan = {
                "target_files": [{"path": "app.py"}],
                "implementation_steps": [
                    {"description": "Set PRODUCTION_TRADING_ENABLED=true and place real orders"},
                ],
                "out_of_scope": [
                    "Do not use secrets, credentials, private keys, cookies, or auth state files.",
                    "Do not transfer funds unless separately approved.",
                ],
            }
            payload = _mod.validate_graphify_scope(config, runtime, risky_plan, {})
            self.assertEqual("block", payload["scope_status"])
            reasons = "\n".join(item["reason"] for item in payload["findings"])
            self.assertIn("production trading", reasons)

    def test_pre_execution_risk_keeps_positive_trading_when_same_line_has_negated_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_paths = [
                Path(tmp) / "requirements.md",
                Path(tmp) / "requirements-review.md",
                Path(tmp) / "solution-review.md",
                Path(tmp) / "graphify.md",
            ]
            for path in artifact_paths:
                path.write_text("", encoding="utf-8")
            artifacts = {
                "requirements_discussion": str(artifact_paths[0]),
                "requirements_review": str(artifact_paths[1]),
                "solution_review": str(artifact_paths[2]),
                "graphify_scope_validation": str(artifact_paths[3]),
            }
            risk = _mod.assess_pre_execution_risk(
                "已人工确认：允许本策略项目执行真实交易下单 smoke，不读取或打印凭证。",
                {},
                artifacts,
            )

        self.assertEqual("high", risk["risk_level"])
        self.assertIn("enable_live_trading", risk["high_risk_reasons"])
        self.assertIn("place_real_order", risk["high_risk_reasons"])

    def test_pre_execution_risk_ignores_pure_negated_trading_and_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_paths = [
                Path(tmp) / "requirements.md",
                Path(tmp) / "requirements-review.md",
                Path(tmp) / "solution-review.md",
                Path(tmp) / "graphify.md",
            ]
            for path in artifact_paths:
                path.write_text("", encoding="utf-8")
            artifacts = {
                "requirements_discussion": str(artifact_paths[0]),
                "requirements_review": str(artifact_paths[1]),
                "solution_review": str(artifact_paths[2]),
                "graphify_scope_validation": str(artifact_paths[3]),
            }
            risk = _mod.assess_pre_execution_risk(
                "保持 PRODUCTION_TRADING_ENABLED=false，不启动真实交易、不下单、不划转、不读取或打印凭证。Do not place orders, transfer funds, or enable live trading.",
                {},
                artifacts,
            )

        self.assertEqual("low", risk["risk_level"])
        self.assertFalse(risk["high_risk_reasons"])

    def test_graphify_context_does_not_trust_mismatched_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            other = tmp_path / "other-repo"
            repo.mkdir()
            other.mkdir()
            index_root = tmp_path / "indexes"
            graph_out = index_root / repo.name / "graphify-out"
            graph_out.mkdir(parents=True)
            (graph_out / "graph.json").write_text(json.dumps({"nodes": [{"id": "x", "label": "Wrong", "community": 1}], "links": []}), encoding="utf-8")
            (graph_out / "GRAPH_REPORT.md").write_text("## God Nodes\n- Wrong repo\n", encoding="utf-8")
            (graph_out / ".graphify_root").write_text(str(other), encoding="utf-8")
            config = PipelineConfig(project_key="demo", command_cwd=repo, runtime_home=str(tmp_path / "runtime"), source_urls=("discord:spreadagent",))
            runtime = {"runtime_home": str(tmp_path / "runtime")}
            with mock.patch.dict(os.environ, {"PIPELINE_GRAPHIFY_INDEX_ROOT": str(index_root)}):
                context = _mod.render_graphify_context(config, runtime, "inspect graph")
                payload = _mod.validate_graphify_scope(config, runtime, {"target_files": []}, {})
            self.assertIn("status: `root_mismatch`", context)
            self.assertIn("root_matches_repo: `False`", context)
            self.assertNotIn("Wrong repo", context)
            self.assertEqual("warning", payload["scope_status"])

    def test_delivery_plan_uses_holistic_scope_without_deferred_slices(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Fix API, dashboard, and docs together after reviewers agree.",
                    workspace_root=Path(tmp),
                    run_id="holistic",
                    dry_run=True,
                )
            )

            plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            self.assertFalse(plan["task_split_policy"]["enabled"])
            self.assertEqual(["holistic-scope"], [item["id"] for item in plan["scope_slices"]])
            self.assertEqual([], plan["task_split_policy"]["deferred_slice_ids"])
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            self.assertIn("Task-splitting granularity control is disabled", solution)

    def test_dual_review_prefers_but_does_not_require_distinct_reviewer_models(self):
        report_a = {
            "ok": True,
            "command": "review --reviewer-role reviewer-a --provider p --model same",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-a\nReviewer provider: p\nReviewer model: same\n",
            "stderr": "",
        }
        report_b_same = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider p --model same",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-b\nReviewer provider: p\nReviewer model: same\n",
            "stderr": "",
        }
        report_b_other = {**report_b_same, "command": "review --reviewer-role reviewer-b --provider q --model other", "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-b\nReviewer provider: q\nReviewer model: other\n"}

        self.assertTrue(_mod.dual_review_pass("requirements_review", [report_a, report_b_same]))
        self.assertTrue(_mod.dual_review_pass("requirements_review", [report_a, report_b_other]))

    def test_dual_review_passes_with_one_valid_output_when_peer_model_fails(self):
        report_a = {
            "ok": True,
            "command": "review --reviewer-role reviewer-a --provider openai-codex --model gpt-5.5",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-a\nReviewer provider: openai-codex\nReviewer model: gpt-5.5\n",
            "stderr": "",
        }
        report_b_failed = {
            "ok": False,
            "returncode": 1,
            "command": "review --reviewer-role reviewer-b --provider kimi-coding --model kimi-k2.6",
            "stdout": "",
            "stderr": "API call failed after 3 retries: HTTP 404",
        }

        self.assertTrue(_mod.dual_review_pass("requirements_review", [report_a, report_b_failed]))
        rendered = _mod.render_dual_ai_review("requirements_review", [report_a, report_b_failed], "ready_for_solution")
        self.assertIn("Review gate mode: degraded_single_valid", rendered)
        self.assertIn("Valid reviewer outputs: 1", rendered)
        self.assertIn("Non-blocking reviewer runtime/model failures", rendered)
        self.assertIn("HTTP 404", rendered)

    def test_dual_review_blocks_concrete_reviewer_revision_even_when_peer_passes(self):
        report_a = {
            "ok": True,
            "command": "review --reviewer-role reviewer-a --provider openai-codex --model gpt-5.5",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-a\nReviewer provider: openai-codex\nReviewer model: gpt-5.5\n",
            "stderr": "",
        }
        report_b_blocker = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider zai --model glm-5.1",
            "stdout": (
                "Final verdict: requires_revision\n"
                "Reviewer role: reviewer-b\n"
                "Reviewer provider: zai\n"
                "Reviewer model: glm-5.1\n"
                "Blocker: target_files missing create_if_missing rationale and content assertion commands.\n"
            ),
            "stderr": "",
        }

        self.assertFalse(_mod.dual_review_pass("requirements_review", [report_a, report_b_blocker]))
        rendered = _mod.render_dual_ai_review("requirements_review", [report_a, report_b_blocker], "requires_revision")
        self.assertIn("Review gate mode: blocked_concrete_reviewers", rendered)
        self.assertIn("Reviewer Discussion And Joint Revision Plan", rendered)
        self.assertIn("target_files missing create_if_missing rationale", rendered)
        self.assertIn("Complete Revision Plan", rendered)
        detail = _mod.review_failure_detail("requirements_review", [report_a, report_b_blocker], "requirements review did not pass")
        self.assertIn("Merged reviewer non-pass reasons", detail)

    def test_solution_review_plan_quality_blocker_is_soft_gate(self):
        report_b_blocker = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider zai --model glm-5.1",
            "stdout": (
                "Final verdict: requires_revision\n"
                "Reviewer role: reviewer-b\n"
                "Reviewer provider: zai\n"
                "Reviewer model: glm-5.1\n"
                "Blocker: verification_commands missing docs memory content assertion and create_if_missing rationale.\n"
            ),
            "stderr": "",
        }

        self.assertTrue(_mod.solution_review_can_soft_continue([report_b_blocker], "requires_revision"))
        rendered = _mod.render_solution_review_soft_gate([report_b_blocker], "requires_revision")
        self.assertIn("Decision: soft_continue", rendered)
        self.assertIn("verification_commands missing docs memory content assertion", rendered)

    def test_solution_review_secret_blocker_remains_hard_gate(self):
        report_b_blocker = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider zai --model glm-5.1",
            "stdout": (
                "Final verdict: requires_revision\n"
                "Reviewer role: reviewer-b\n"
                "Reviewer provider: zai\n"
                "Reviewer model: glm-5.1\n"
                "Blocker: implementation plan asks the agent to read API key credentials from auth state.\n"
            ),
            "stderr": "",
        }

        self.assertFalse(_mod.solution_review_can_soft_continue([report_b_blocker], "requires_revision"))
        hard_lines = _mod.solution_review_hard_blocker_lines([report_b_blocker])
        self.assertTrue(any("API key credentials" in line for line in hard_lines))

    def test_dual_review_rendering_merges_distinct_model_findings(self):
        report_a = {
            "ok": True,
            "command": "review --reviewer-role reviewer-a --provider p --model alpha",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-a\nReviewer provider: p\nReviewer model: alpha\n",
            "stderr": "",
        }
        report_b = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider q --model beta",
            "stdout": "Final verdict: ready_for_solution\nReviewer role: reviewer-b\nReviewer provider: q\nReviewer model: beta\n",
            "stderr": "",
        }

        rendered = _mod.render_dual_ai_review("requirements_review", [report_a, report_b], "ready_for_solution")

        self.assertIn("## Merged Reviewer Consensus", rendered)
        self.assertIn("independent multi-model review", rendered)
        self.assertIn("No artificial task-splitting granularity gate", rendered)
        self.assertIn("Remaining blockers", rendered)
        self.assertIn("none; no concrete reviewer blocker remains", rendered)

    def test_reviewer_model_from_output_uses_final_fallback_model(self):
        stdout = "\n".join(
            [
                "Reviewer provider: kimi-coding",
                "Reviewer model: kimi-k2.6",
                "# reviewer fallback attempt failed",
                "Reviewer provider: openai-codex",
                "Reviewer model: gpt-5.5",
                "Final verdict: ready_for_solution",
            ]
        )
        self.assertEqual("openai-codex", _mod.reviewer_provider_from_output(stdout, ""))
        self.assertEqual("gpt-5.5", _mod.reviewer_model_from_output(stdout, ""))

    def test_default_repair_loop_budget_is_four_for_until_clean_review_policy(self):
        self.assertEqual(4, PipelineConfig(project_key="demo").max_repair_loops)

    def test_git_repository_context_fetches_remote_branches_for_project_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote = tmp_path / "remote.git"
            repo = tmp_path / "repo"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.name", "Test Bot"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            (repo / "README.md").write_text("main\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "-b", "feature/context"], cwd=repo, check=True, capture_output=True, text=True)
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            subprocess.run(["git", "add", "feature.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "feature"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "push", "origin", "HEAD:feature/context"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True, text=True)

            snapshot = _mod.collect_git_repository_context(repo)
            rendered = _mod.render_git_repository_context(snapshot)

            self.assertTrue(snapshot["is_git_repository"])
            self.assertIn("origin/feature/context", "\n".join(snapshot["remote_branches"]))
            self.assertIn("fetch_all_prune", rendered)
            self.assertIn("Project-agent must consider", rendered)

    def test_high_risk_plan_blocks_before_code_execution_and_records_group_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            scripts_dir = tmp_path / "scripts"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass_stage.py"
            pass_script.write_text("print('LIVE_BRIDGE_STATUS: pass')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            command_repo = tmp_path / "command-repo"
            command_repo.mkdir()
            (command_repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "README.md"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test Bot", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
                cwd=command_repo,
                check=True,
                capture_output=True,
                text=True,
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="开启真实交易并设置 PRODUCTION_TRADING_ENABLED=true",
                    workspace_root=tmp_path,
                    run_id="high-risk-plan",
                    source_urls=("https://example.invalid/docs",),
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    command_cwd=command_repo,
                    agent_workspace_root=tmp_path / "agent-workspaces",
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("risk_gate", state["failed_stage"])
            self.assertEqual("await_human_confirmation", state["next_action"])
            self.assertNotIn("code_execution", [stage["name"] for stage in state["stages"]])
            risk = json.loads(Path(state["artifacts"]["pre_execution_risk"]).read_text(encoding="utf-8"))
            self.assertEqual("high", risk["risk_level"])
            self.assertTrue(risk["human_confirmation_required"])
            group_plan = Path(state["artifacts"]["plan_publish"]).read_text(encoding="utf-8")
            self.assertIn("等待用户确认", group_plan)
            failure_summary = Path(state["artifacts"]["failure_summary"]).read_text(encoding="utf-8")
            self.assertIn("失败步骤群回传摘要", failure_summary)
            self.assertIn("risk_gate", failure_summary)

    def test_high_risk_plan_runs_after_human_risk_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            scripts_dir = tmp_path / "scripts"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass_stage.py"
            pass_script.write_text("print('LIVE_BRIDGE_STATUS: pass')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            command_repo = tmp_path / "command-repo"
            command_repo.mkdir()
            (command_repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "README.md"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test Bot", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
                cwd=command_repo,
                check=True,
                capture_output=True,
                text=True,
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="已人工确认：允许本策略项目开启真实交易并设置 PRODUCTION_TRADING_ENABLED=true",
                    workspace_root=tmp_path,
                    run_id="high-risk-confirmed",
                    source_urls=("https://example.invalid/docs",),
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    memory_write_command=py_cmd(pass_script),
                    command_cwd=command_repo,
                    agent_workspace_root=tmp_path / "agent-workspaces",
                    human_risk_confirmed=True,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertEqual("none", state["next_action"])
            self.assertIn("code_execution", [stage["name"] for stage in state["stages"]])
            risk = json.loads(Path(state["artifacts"]["pre_execution_risk"]).read_text(encoding="utf-8"))
            self.assertEqual("high", risk["risk_level"])
            self.assertTrue(risk["human_confirmation_required"])
            self.assertTrue(risk["human_confirmation_confirmed"])
            self.assertEqual("confirmed_execute", risk["execution_decision"])
            group_plan = Path(state["artifacts"]["plan_publish"]).read_text(encoding="utf-8")
            self.assertIn("human_confirmation_confirmed", group_plan)

    def test_pipeline_state_collects_agent_session_and_run_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            report = run_dir / "command-runs" / "code_execution-1.json"
            report.parent.mkdir()
            report.write_text(
                json.dumps(
                    {
                        "stage": "code_execution",
                        "index": 1,
                        "agent_id": "backend-dev",
                        "dispatch_mode": "native-agent-session",
                        "agent_session_id": "sess-123",
                        "agent_run_id": "run-456",
                        "agent_session_key": "agent:backend-dev:run:task-1",
                        "returncode": 0,
                        "ok": True,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = _mod.pipeline_state(
                PipelineConfig(project_key="demo", requirement="x", workspace_root=Path(tmp), dry_run=True),
                "run",
                run_dir,
                {},
                [_mod.StageRecord(name="code_execution", status="completed")],
                {"command_code_execution_1": str(report)},
                "completed",
                "none",
            )

        self.assertEqual("sess-123", state["agent_invocations"][0]["session_id"])
        self.assertEqual("run-456", state["agent_invocations"][0]["run_id"])
        self.assertEqual("backend-dev", state["agent_invocations"][0]["agent_id"])

    def test_extract_agent_runtime_refs_from_bridge_output(self):
        refs = _mod.extract_agent_runtime_refs(
            "session_id: sess-123\nLIVE_BRIDGE_AGENT_RUN_ID: run-456\n",
            "LIVE_BRIDGE_AGENT_SESSION_KEY: agent:backend-dev:run:task-1",
        )

        self.assertEqual("sess-123", refs["session_id"])
        self.assertEqual("run-456", refs["run_id"])
        self.assertEqual("agent:backend-dev:run:task-1", refs["session_key"])

    def test_live_command_writes_running_pipeline_state_before_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            scripts_dir = tmp_path / "scripts"
            scripts_dir.mkdir()
            slow_research = scripts_dir / "slow_research.py"
            slow_research.write_text(
                "import time\n"
                "print('# Research')\n"
                "time.sleep(1.5)\n"
                "print('Final verdict: pass')\n",
                encoding="utf-8",
            )
            command_repo = tmp_path / "command-repo"
            command_repo.mkdir()
            (command_repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "README.md"], cwd=command_repo, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test Bot",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                cwd=command_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            result: dict[str, object] = {}

            def run() -> None:
                result["state"] = run_pipeline(
                    PipelineConfig(
                        project_key="demo",
                        requirement="Run long research command.",
                        workspace_root=tmp_path,
                        run_id="running-state",
                        research_commands=(f'"{sys.executable}" "{slow_research}"',),
                        command_timeout_seconds=5,
                        command_cwd=command_repo,
                        force=True,
                    )
                )

            thread = threading.Thread(target=run)
            thread.start()
            state_file = tmp_path / "running-state" / "pipeline_state.json"
            running_state = None
            try:
                for _ in range(30):
                    if state_file.exists():
                        state = json.loads(state_file.read_text(encoding="utf-8"))
                        if any(
                            item.get("name") == "external_research" and item.get("status") == "running"
                            for item in state.get("stages", [])
                        ):
                            running_state = state
                            break
                    time.sleep(0.1)
            finally:
                thread.join(timeout=10)

            self.assertFalse(thread.is_alive())
            self.assertIsNotNone(running_state)
            assert running_state is not None
            self.assertEqual("running", running_state["status"])
            self.assertEqual("continue", running_state["next_action"])
            self.assertIn("run_meta", running_state["artifacts"])
            self.assertIn("state", result)

    def test_requirement_and_solution_artifacts_preserve_specific_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            requirement = (
                "修复 nofx smart-arb-pipeline 的 Dual AI evidence contract，"
                "不要继续业务第五切片，也不要提交 _close_position 漂移。"
            )
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement=requirement,
                    workspace_root=Path(tmp),
                    run_id="specific-requirement",
                    dry_run=True,
                )
            )

            requirements = Path(state["artifacts"]["requirements_package"]).read_text(encoding="utf-8")
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            self.assertIn("修复 nofx smart-arb-pipeline", requirements)
            self.assertIn("不要继续业务第五切片", requirements)
            self.assertIn("Deliver the user request above exactly as written", requirements)
            self.assertNotIn("Build an end-to-end coding delivery pipeline that can", requirements)
            self.assertIn("## Delivery Plan Contract", solution)
            self.assertIn("delivery_plan.json", solution)
            self.assertIn("修复 nofx smart-arb-pipeline", delivery_plan["scope_slices"][0]["description"])
            self.assertEqual("delivery-plan/v1", delivery_plan["schema_version"])
            self.assertIn("smart-arb-pipeline", json.dumps(delivery_plan, ensure_ascii=False))
            self.assertNotIn("## Stage Order", solution)

    def test_delivery_plan_prefers_explicit_target_paths_over_memory_context_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Fix scripts/openclaw-ops/smart_arb_pipeline_entry.py without live trading.",
                    workspace_root=Path(tmp),
                    run_id="explicit-plan-path",
                    dry_run=True,
                )
            )

            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))

            self.assertEqual("bugfix", delivery_plan["task_type"])
            self.assertEqual("backend-dev", delivery_plan["owner"])
            self.assertEqual(
                ["scripts/openclaw-ops/smart_arb_pipeline_entry.py"],
                [item["path"] for item in delivery_plan["target_files"]],
            )
            self.assertNotIn("project-agent", json.dumps(delivery_plan, ensure_ascii=False))
            self.assertNotIn("API_REGISTRY.json", [item["path"] for item in delivery_plan["target_files"]])
            self.assertTrue(solution.startswith("# Solution Package\n\n## Delivery Plan Contract"))

    def test_delivery_plan_keeps_code_fix_type_when_docs_are_synced(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="修复 skills/library/project-delivery-pipeline/scripts/pipeline_runner.py 并同步 memory/RUNBOOK.md 文档",
                    workspace_root=Path(tmp),
                    run_id="code-fix-with-doc-sync",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))

            self.assertEqual("bugfix", delivery_plan["task_type"])
            self.assertEqual("backend-dev", delivery_plan["owner"])
            self.assertIn(
                "/home/arbops/.venvs/smart-arbitrage/bin/python -B -m compileall -q 智能多平台套利 scripts tests",
                [item["command"] for item in delivery_plan["verification_commands"]],
            )

    def test_delivery_plan_does_not_treat_readme_tooling_as_docs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Add README renderer support in scripts/openclaw-ops/smart_arb_pipeline_entry.py",
                    workspace_root=Path(tmp),
                    run_id="readme-tooling-support",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))

            self.assertEqual("feature", delivery_plan["task_type"])
            self.assertEqual("backend-dev", delivery_plan["owner"])
            self.assertIn(
                "/home/arbops/.venvs/smart-arbitrage/bin/python -B -m compileall -q 智能多平台套利 scripts tests",
                [item["command"] for item in delivery_plan["verification_commands"]],
            )

    def test_delivery_plan_does_not_promote_memory_context_to_simple_task_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="把 Discord 状态卡的回答状态文案改短一点。",
                    workspace_root=Path(tmp),
                    run_id="simple-task-no-memory-targets",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            target_paths = [item["path"] for item in delivery_plan["target_files"]]
            filtered_candidates = delivery_plan["plan_findings"]["filtered_target_candidates"]

            self.assertEqual([], target_paths)
            self.assertTrue(delivery_plan["plan_findings"]["discovery_required"])
            self.assertTrue(delivery_plan["plan_findings"]["abnormal_feedback_required"])
            self.assertNotIn("API_REGISTRY.json", target_paths)
            self.assertNotIn("SOURCE_REGISTRY.json", target_paths)
            self.assertFalse(any(".workflow" in path or ".hermes" in path for path in target_paths))
            self.assertTrue(any(item["path"] == "API_REGISTRY.json" for item in filtered_candidates))
            self.assertTrue(any(item["reason"] == "project_memory_control_file" for item in filtered_candidates))
            self.assertIn("## Filtered Target Candidates", solution)
            self.assertIn("API_REGISTRY.json: project_memory_control_file", solution)

    def test_delivery_plan_skips_negated_control_paths_in_original_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement=(
                        "Do not edit .workflow/pipeline-runs/demo/retry.py; "
                        "把 Discord 状态卡的回答状态文案改短一点。"
                    ),
                    workspace_root=Path(tmp),
                    run_id="negated-control-path",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            target_paths = [item["path"] for item in delivery_plan["target_files"]]
            filtered_candidates = delivery_plan["plan_findings"]["filtered_target_candidates"]

            self.assertEqual([], target_paths)
            self.assertTrue(delivery_plan["plan_findings"]["discovery_required"])
            self.assertIn(
                {
                    "path": ".workflow/pipeline-runs/demo/retry.py",
                    "source": "original_requirement_or_repair_context",
                    "reason": "negated_context",
                    "context": "Do not edit .workflow/pipeline-runs/demo/retry.py",
                },
                filtered_candidates,
            )
            self.assertIn(".workflow/pipeline-runs/demo/retry.py: negated_context", solution)

    def test_delivery_plan_filters_auth_state_targets_before_solution_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="target_files: auth.json；只做策略配置参数页面/API 的非敏感只读快照。",
                    workspace_root=Path(tmp),
                    run_id="auth-target-filter",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            target_paths = [item["path"] for item in delivery_plan["target_files"]]
            filtered_candidates = delivery_plan["plan_findings"]["filtered_target_candidates"]

            self.assertNotIn("auth.json", target_paths)
            self.assertTrue(delivery_plan["plan_findings"]["discovery_required"])
            self.assertTrue(
                any(
                    item["path"] == "auth.json"
                    and item["reason"] == "credential_or_auth_target_file"
                    and item["source"] == "original_requirement_or_repair_context"
                    for item in filtered_candidates
                )
            )
            self.assertIn("auth.json: credential_or_auth_target_file", solution)

    def test_delivery_plan_reads_explicit_target_from_multiline_original_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement=(
                        "Shorten the Discord answer-status copy.\n"
                        "Target file: scripts/openclaw-ops/smart_arb_pipeline_entry.py"
                    ),
                    workspace_root=Path(tmp),
                    run_id="multiline-explicit-target",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))

            self.assertEqual(
                ["scripts/openclaw-ops/smart_arb_pipeline_entry.py"],
                [item["path"] for item in delivery_plan["target_files"]],
            )
            self.assertEqual([], delivery_plan["plan_findings"]["filtered_target_candidates"])

    def test_delivery_plan_filters_windows_absolute_target_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Target file: E:/repo/src/app.py，把状态卡文案改短。",
                    workspace_root=Path(tmp),
                    run_id="windows-absolute-target-path",
                    dry_run=True,
                )
            )

            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            filtered_candidates = delivery_plan["plan_findings"]["filtered_target_candidates"]

            self.assertEqual([], [item["path"] for item in delivery_plan["target_files"]])
            self.assertTrue(delivery_plan["plan_findings"]["discovery_required"])
            self.assertTrue(delivery_plan["plan_findings"]["abnormal_feedback_required"])
            self.assertTrue(
                any(
                    item["path"] == "E:/repo/src/app.py"
                    and item["reason"] == "external_or_runtime_absolute_path"
                    and item["source"] == "original_requirement_or_repair_context"
                    for item in filtered_candidates
                )
            )
            self.assertIn("E:/repo/src/app.py: external_or_runtime_absolute_path", solution)

    def test_delivery_plan_filters_control_paths_from_review_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            requirements_review = run_dir / "requirements_review.md"
            project_memory_context = run_dir / "project_memory_context.md"
            requirements_review.write_text(
                "\n".join(
                    [
                        "Final verdict: ready_for_solution",
                        "Likely implementation file: scripts/openclaw-ops/smart_arb_pipeline_entry.py",
                        "Do not edit .workflow/pipeline-runs/demo/retry.py",
                        "Do not edit .workflow/project-memory/demo/API_REGISTRY.json",
                        "Do not edit /home/arbops/.hermes/profiles/spreadagent/sessions/session_1.json",
                    ]
                ),
                encoding="utf-8",
            )
            project_memory_context.write_text(
                "Runtime host: hermes\nRequired Files: API_REGISTRY.json, SOURCE_REGISTRY.json\n",
                encoding="utf-8",
            )

            delivery_plan = _mod.compile_delivery_plan(
                PipelineConfig(project_key="demo", requirement="把状态卡文案改短"),
                {"host": "hermes", "runtime_home": "/home/arbops/.hermes"},
                "把状态卡文案改短",
                {
                    "requirements_review": str(requirements_review),
                    "project_memory_context": str(project_memory_context),
                },
            )

            self.assertEqual([], [item["path"] for item in delivery_plan["target_files"]])
            filtered_candidates = delivery_plan["plan_findings"]["filtered_target_candidates"]
            solution = _mod.render_solution(delivery_plan)
            self.assertTrue(
                any(
                    item["path"] == "scripts/openclaw-ops/smart_arb_pipeline_entry.py"
                    and item["reason"] == "workflow_or_runtime_control_path"
                    and item["source"] == "requirements_review"
                    for item in filtered_candidates
                )
            )
            self.assertTrue(
                any(
                    item["path"] == ".workflow/pipeline-runs/demo/retry.py"
                    and item["reason"] == "negated_context"
                    and item["source"] == "requirements_review"
                    for item in filtered_candidates
                )
            )
            self.assertTrue(
                any(
                    item["path"] == "/home/arbops/.hermes/profiles/spreadagent/sessions/session_1.json"
                    and item["reason"] == "external_or_runtime_absolute_path"
                    and item["source"] == "requirements_review"
                    for item in filtered_candidates
                )
            )
            self.assertIn(
                "/home/arbops/.hermes/profiles/spreadagent/sessions/session_1.json: external_or_runtime_absolute_path",
                solution,
            )
            self.assertTrue(
                any(
                    item["path"] == ".workflow/project-memory/demo/API_REGISTRY.json"
                    and item["reason"] == "negated_context"
                    for item in filtered_candidates
                )
            )

    def test_delivery_plan_filters_negated_workflow_basenames_and_combined_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            requirements_review = run_dir / "requirements_review.md"
            requirements_review.write_text(
                "\n".join(
                    [
                        "Final verdict: ready_for_solution",
                        "target_files must only contain SmartMultiPlatformArbitrage business files; "
                        "禁止 smart_arb_live_bridge.py、smart_arb_pipeline_entry.py 进入 target_files。",
                        "Candidate business files: todo.md/done.md, 智能多平台套利/api/routes/stock_tokens.py",
                    ]
                ),
                encoding="utf-8",
            )

            delivery_plan = _mod.compile_delivery_plan(
                PipelineConfig(project_key="demo", requirement="继续推进价差监控测试，不修改 workflow 宿主"),
                {"host": "hermes", "runtime_home": "/home/arbops/.hermes"},
                "继续推进价差监控测试，不修改 workflow 宿主",
                {"requirements_review": str(requirements_review)},
            )

            paths = [item["path"] for item in delivery_plan["target_files"]]
            self.assertEqual(["智能多平台套利/api/routes/stock_tokens.py"], paths)
            self.assertNotIn("todo.md/done.md", paths)
            self.assertFalse(any("smart_arb_" in path for path in paths))
            findings = delivery_plan["plan_findings"]["filtered_target_candidates"]
            self.assertTrue(any(item["path"] == "todo.md/done.md" and item["reason"] == "combined_file_paths" for item in findings))
            self.assertTrue(any(item["reason"] in {"negated_context", "workflow_host_basename"} for item in findings))

    def test_delivery_plan_marks_reviewer_paths_as_candidates_and_generates_file_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / "requirements_review.md"
            review.write_text(
                "Final verdict: ready_for_solution\nCandidate: 智能多平台套利/api/routes/stock_tokens.py\n",
                encoding="utf-8",
            )
            plan = _mod.compile_delivery_plan(
                PipelineConfig(project_key="demo", requirement="继续推进价差监控测试"),
                {"host": "hermes"},
                "继续推进价差监控测试",
                {"requirements_review": str(review)},
            )

            self.assertEqual("review_candidate", plan["target_files"][0]["confidence"])
            step_text = json.dumps(plan["implementation_steps"], ensure_ascii=False)
            self.assertIn("智能多平台套利/api/routes/stock_tokens.py", step_text)
            self.assertIn("blocked_manual_acceptance_required", "\n".join(plan["human_blockers"]))

    def test_delivery_plan_uses_discussion_targets_and_command_level_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            for path in (
                "智能多平台套利/api/routes",
                "智能多平台套利/api",
                "智能多平台套利/monitoring",
                "scripts",
                "tests",
                "docs",
                "memory",
            ):
                (repo / path).mkdir(parents=True, exist_ok=True)
            for path in (
                "智能多平台套利/api/routes/stock_tokens.py",
                "智能多平台套利/api/stock_token_public_adapter.py",
                "智能多平台套利/monitoring/funding_discovery_service.py",
                "智能多平台套利/monitoring/opportunity_monitor.py",
                "智能多平台套利/api/routes/funding.py",
                "智能多平台套利/api/routes/dashboard.py",
                "智能多平台套利/api/main.py",
                "scripts/query_spread_funding_profit.py",
                "tests/test_query_spread_funding_profit.py",
                "tests/test_dashboard_api.py",
                "tests/test_opportunity_monitor_service.py",
                "tests/test_stock_token_public_adapter.py",
                "tests/test_basic_auth_proxy.py",
                "todo.md",
                "done.md",
                "MEMORY.md",
                "docs/INDEX.md",
            ):
                (repo / path).write_text("# ok\n", encoding="utf-8")

            discussion = root / "requirements_discussion.md"
            discussion.write_text(
                """
最可能改动/验证位置：
- `智能多平台套利/monitoring/funding_discovery_service.py`
- `智能多平台套利/monitoring/funding_rate_scanner.py`，如不存在则需要 create_if_missing rationale
- `智能多平台套利/api/routes/funding.py`
- `智能多平台套利/api/routes/dashboard.py`
- `智能多平台套利/api/routes/stock_tokens.py`
- `智能多平台套利/api/stock_token_public_adapter.py`
- `智能多平台套利/api/main.py`
- `scripts/query_spread_funding_profit.py`
- `tests/test_funding_rate_scanner.py`，如不存在则需要 create_if_missing rationale
- `tests/test_query_spread_funding_profit.py`
- `tests/test_dashboard_api.py`
- `tests/test_opportunity_monitor_service.py`
- `tests/test_stock_token_public_adapter.py`
- `tests/test_basic_auth_proxy.py`
- `docs/INDEX.md`
- `docs/观测与运维/币股平台只读监控方案.md`
- `memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md`
- `memory/smart-multi-platform-arbitrage/DECISIONS.md`
- `memory/smart-multi-platform-arbitrage/DELIVERY_RULES.md`
- `MEMORY.md`
- `todo.md`
- `done.md`
- `2026-04-27.md`

不得进入 target_files：
- `smart_arb_live_bridge.py`
- `smart_arb_pipeline_entry.py`
- `/home/arbops/.hermes/**`

Verification commands:
- `/home/arbops/.venvs/smart-arbitrage/bin/python -m pytest -q tests/test_funding_rate_scanner.py tests/test_query_spread_funding_profit.py tests/test_dashboard_api.py tests/test_opportunity_monitor_service.py`
- `/home/arbops/.venvs/smart-arbitrage/bin/python -m pytest -q tests/test_stock_token_public_adapter.py tests/test_basic_auth_proxy.py`
- `/home/arbops/.venvs/smart-arbitrage/bin/python -B -m compileall -q 智能多平台套利 scripts tests`
- `git diff --check`
- `curl -fsS http://127.0.0.1:18080/health`
- `curl -fsS http://127.0.0.1:18080/api/strategy/status`
- `curl -fsS http://127.0.0.1:18080/api/realtime/funding`
需要 docs/memory/todo/done content assertion、git publish / origin/main remote containment、Discord blocked_manual_acceptance_required。
""",
                encoding="utf-8",
            )
            review = root / "requirements_review.md"
            review.write_text("Final verdict: ready_for_solution\nAlso inspect stock_tokens.py\n", encoding="utf-8")
            git_context = root / "git_repository_context.md"
            git_context.write_text("Status: ## main...origin/main [behind 2]\nM MEMORY.md\ndirty worktree\n", encoding="utf-8")

            plan = _mod.compile_delivery_plan(
                PipelineConfig(project_key="demo", requirement="价差监控测试", command_cwd=repo),
                {"host": "hermes"},
                "价差监控测试",
                {
                    "requirements_discussion": str(discussion),
                    "requirements_review": str(review),
                    "git_repository_context": str(git_context),
                },
            )

            paths = [item["path"] for item in plan["target_files"]]
            self.assertIn("智能多平台套利/api/routes/stock_tokens.py", paths)
            self.assertIn("智能多平台套利/api/stock_token_public_adapter.py", paths)
            self.assertIn("智能多平台套利/monitoring/funding_discovery_service.py", paths)
            self.assertIn("智能多平台套利/monitoring/funding_rate_scanner.py", paths)
            self.assertIn("tests/test_funding_rate_scanner.py", paths)
            self.assertNotIn("docs/观测与运维/币股平台只读监控方案.md", paths)
            self.assertNotIn("memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md", paths)
            self.assertNotIn("memory/smart-multi-platform-arbitrage/DECISIONS.md", paths)
            self.assertNotIn("memory/smart-multi-platform-arbitrage/DELIVERY_RULES.md", paths)
            read_only_paths = [item["path"] for item in plan["read_only_sources"]]
            self.assertIn("docs/观测与运维/币股平台只读监控方案.md", read_only_paths)
            self.assertIn("memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md", read_only_paths)
            self.assertIn("memory/smart-multi-platform-arbitrage/DECISIONS.md", read_only_paths)
            self.assertIn("memory/smart-multi-platform-arbitrage/DELIVERY_RULES.md", read_only_paths)
            self.assertNotIn("2026-04-27.md", paths)
            self.assertNotIn("stock_tokens.py", paths)
            self.assertNotIn("origin/main", paths)
            scanner = next(item for item in plan["target_files"] if item["path"] == "智能多平台套利/monitoring/funding_rate_scanner.py")
            self.assertTrue(scanner["create_if_missing"])
            self.assertIn("expected_net_daily", scanner["create_if_missing_rationale"])
            self.assertFalse(any("Inspect `" in item["description"] for item in plan["implementation_steps"]))
            self.assertFalse(any(item["path"] in {"todo.md", "done.md", "MEMORY.md"} for item in plan["entry_points"]))
            self.assertFalse(any(item["path"].startswith("tests/") for item in plan["entry_points"]))

            commands = [item["command"] for item in plan["verification_commands"]]
            self.assertIn(
                "/home/arbops/.venvs/smart-arbitrage/bin/python -m pytest -q tests/test_funding_rate_scanner.py tests/test_query_spread_funding_profit.py tests/test_dashboard_api.py tests/test_opportunity_monitor_service.py",
                commands,
            )
            self.assertIn("/home/arbops/.venvs/smart-arbitrage/bin/python -B -m compileall -q 智能多平台套利 scripts tests", commands)
            self.assertIn("curl -fsS http://127.0.0.1:18080/api/realtime/funding", commands)
            self.assertIn("git fetch origin main --prune", commands)
            self.assertNotIn("git merge-base --is-ancestor HEAD origin/main", commands)
            self.assertIn("git rev-list --left-right --count HEAD...origin/main", commands)
            self.assertNotIn("test -f todo.md", commands)
            self.assertNotIn(
                "rg -n '价差监控|stock-token|read-only|signal-only|blocked_manual_acceptance_required|NO_EXTERNAL_LOOKUP_NEEDED' docs memory todo.md done.md MEMORY.md",
                commands,
            )

            validation = _mod.validate_graphify_scope(
                PipelineConfig(project_key="demo", command_cwd=repo),
                {},
                plan,
                {},
            )
            self.assertFalse(
                any(
                    item.get("path") == "智能多平台套利/monitoring/funding_rate_scanner.py"
                    and "create_if_missing" in item.get("reason", "")
                    for item in validation["findings"]
                )
            )
            self.assertFalse(any(item.get("path") == "2026-04-27.md" for item in validation["findings"]))

    def test_delivery_plan_keeps_heavy_multi_item_requirement_holistic(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="继续推进：策略主干、资金费率套利、spread_grid 远端集成验收、Discord 真实查询验收、文档治理。安全要求：不读取凭证。",
                    workspace_root=Path(tmp),
                    run_id="split-heavy-task",
                    dry_run=True,
                )
            )

            solution = Path(state["artifacts"]["solution_package"]).read_text(encoding="utf-8")
            delivery_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))

            self.assertEqual("holistic-scope", delivery_plan["task_split_policy"]["current_slice_id"])
            self.assertEqual([], delivery_plan["task_split_policy"]["deferred_slice_ids"])
            self.assertEqual("current", delivery_plan["scope_slices"][0]["status"])
            self.assertEqual(1, len(delivery_plan["scope_slices"]))
            self.assertFalse(delivery_plan["task_split_policy"]["enabled"])
            self.assertTrue(
                any("complete accepted requirement" in item for item in delivery_plan["out_of_scope"])
            )
            self.assertIn("## Task Split Policy", solution)

    def test_code_agent_can_select_frontend_stage_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Update a frontend dashboard interaction.",
                    workspace_root=Path(tmp),
                    run_id="frontend-owner",
                    dry_run=True,
                    code_agent="frontend-dev",
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertEqual(["frontend-dev"], state["stage_agents"]["code_execution"])
            run_meta = json.loads(Path(state["artifacts"]["run_meta"]).read_text(encoding="utf-8"))
            self.assertEqual("frontend-dev", run_meta["code_agent"])

    def test_requirements_failure_routes_back_to_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build something ambiguous.",
                    workspace_root=Path(tmp),
                    run_id="requirements-failure",
                    dry_run=True,
                    simulate_failure_stage="requirements",
                )
            )

            run_dir = Path(tmp) / "requirements-failure"
            self.assertEqual("blocked", state["status"])
            self.assertEqual("requirements_review", state["failed_stage"])
            self.assertEqual("revise_requirements", state["next_action"])
            self.assertTrue((run_dir / "requirements_review.md").exists())
            self.assertFalse((run_dir / "solution.md").exists())

    def test_acceptance_requirement_failure_routes_to_requirement_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline but acceptance criteria are wrong.",
                    workspace_root=Path(tmp),
                    run_id="acceptance-requirement-failure",
                    dry_run=True,
                    simulate_failure_stage="acceptance_requirement",
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("acceptance", state["failed_stage"])
            self.assertEqual("revise_requirements", state["next_action"])
            self.assertIn("delivery_evidence", state["artifacts"])

    def test_hermes_runtime_home_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline in Hermes.",
                    workspace_root=Path(tmp),
                    run_id="hermes-runtime",
                    runtime_host="hermes",
                    runtime_home="/home/ubuntu/.hermes",
                    dry_run=True,
                )
            )

            runtime = state["runtime_context"]
            self.assertEqual("hermes", runtime["host"])
            self.assertEqual("/home/ubuntu/.hermes", runtime["runtime_home"])
            self.assertEqual("/home/ubuntu/.hermes/.workflow/pipeline-runs", runtime["state_dir"])

    def test_custom_runtime_host_with_explicit_home_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Build the pipeline in a custom runtime.",
                    workspace_root=Path(tmp),
                    run_id="custom-runtime",
                    runtime_host="my-runtime",
                    runtime_home="/srv/my-runtime",
                    dry_run=True,
                )
            )

            runtime = state["runtime_context"]
            self.assertEqual("my-runtime", runtime["host"])
            self.assertEqual("/srv/my-runtime", runtime["runtime_home"])
            self.assertEqual("/srv/my-runtime/.workflow/pipeline-runs", runtime["state_dir"])

    def test_project_memory_module_is_bootstrapped_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_root = Path(tmp) / "project-memory"
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Add a project memory retrieval gate.",
                    workspace_root=Path(tmp) / "runs",
                    project_memory_root=memory_root,
                    run_id="memory",
                    dry_run=True,
                )
            )

            memory_dir = memory_root / "demo"
            self.assertEqual("completed", state["status"])
            for name in (
                "PROJECT_PROFILE.md",
                "DECISIONS.md",
                "DELIVERY_RULES.md",
                "API_REGISTRY.json",
                "SOURCE_REGISTRY.json",
                "IMPACT_MAP.json",
                "RETRIEVAL_MANIFEST.json",
            ):
                self.assertTrue((memory_dir / name).exists(), name)
            context = Path(state["artifacts"]["project_memory_context"]).read_text(encoding="utf-8")
            self.assertIn("Anti Local-Optimum Rule", context)

    def test_task_center_mirror_records_pipeline_task_and_stage_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "task_center.db"
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Record pipeline runs in task center.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="task-center",
                    dry_run=True,
                    record_task_center=True,
                    task_center_db=db_path,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertEqual("project-delivery:task-center", state["task_center"]["task_id"])
            conn = sqlite3.connect(db_path)
            try:
                task_count = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                stage_count = conn.execute(
                    "SELECT COUNT(*) FROM stage_runs WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                comm_count = conn.execute(
                    "SELECT COUNT(*) FROM module_communications WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
                output_count = conn.execute(
                    "SELECT COUNT(*) FROM task_outputs WHERE task_id = ?",
                    ("project-delivery:task-center",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(1, task_count)
            self.assertGreaterEqual(stage_count, 13)
            self.assertGreaterEqual(comm_count, 13)
            self.assertEqual(1, output_count)

    def test_task_center_mirror_allows_repeat_run_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "task_center.db"
            config = PipelineConfig(
                project_key="demo",
                requirement="Record repeat pipeline runs in task center.",
                workspace_root=root / "runs",
                project_memory_root=root / "memory",
                run_id="task-center-repeat",
                dry_run=True,
                force=True,
                record_task_center=True,
                task_center_db=db_path,
            )

            first = run_pipeline(config)
            second = run_pipeline(config)

            self.assertEqual("completed", first["status"])
            self.assertEqual("completed", second["status"])
            self.assertEqual("project-delivery:task-center-repeat", second["task_center"]["task_id"])
            self.assertEqual("passed", second["task_center"]["status"])
            conn = sqlite3.connect(db_path)
            try:
                task_count = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE task_id = ?",
                    ("project-delivery:task-center-repeat",),
                ).fetchone()[0]
                stage_count = conn.execute(
                    "SELECT COUNT(*) FROM stage_runs WHERE task_id = ?",
                    ("project-delivery:task-center-repeat",),
                ).fetchone()[0]
                comm_count = conn.execute(
                    "SELECT COUNT(*) FROM module_communications WHERE task_id = ?",
                    ("project-delivery:task-center-repeat",),
                ).fetchone()[0]
                output_count = conn.execute(
                    "SELECT COUNT(*) FROM task_outputs WHERE task_id = ?",
                    ("project-delivery:task-center-repeat",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(1, task_count)
            self.assertGreaterEqual(stage_count, 26)
            self.assertGreaterEqual(comm_count, 26)
            self.assertEqual(2, output_count)

    def test_legacy_hardflow_score_policy_ref_resolves_after_skillization(self):
        module = load_policy_workflow_module()
        resolved = module.WorkflowMixin._resolve_repo_ref_path("scripts/hardflow/score-policy.json")

        self.assertTrue(resolved.exists())
        self.assertEqual("score-policy.json", resolved.name)
        self.assertIn("openclaw-hardflow-automation", resolved.parts)

    def test_workflow_repo_root_prefers_runtime_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            score_policy = repo / "skills" / "openclaw-hardflow-automation" / "scripts" / "score-policy.json"
            score_policy.parent.mkdir(parents=True)
            (repo / ".git").mkdir()
            score_policy.write_text('{"gates":{"default":{}}}\n', encoding="utf-8")

            with mock.patch.dict(os.environ, {"HARDFLOW_WORKFLOW_REPO": str(repo)}):
                module = load_policy_workflow_module()

            resolved = module.WorkflowMixin._resolve_repo_ref_path("scripts/hardflow/score-policy.json")
            self.assertEqual(repo.resolve(), module.REPO_ROOT)
            self.assertEqual(score_policy.resolve(), resolved)

    def test_workflow_repo_root_falls_back_to_current_workdir(self):
        module = load_policy_workflow_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            runtime = Path(tmp) / "runtime" / "ops"
            repo.mkdir()
            runtime.mkdir(parents=True)
            (repo / ".git").mkdir()
            old_cwd = Path.cwd()
            try:
                os.chdir(repo)
                resolved = module._discover_repo_root(runtime)
            finally:
                os.chdir(old_cwd)

        self.assertEqual(repo.resolve(), resolved)

    def test_workflow_repo_root_ignores_inaccessible_git_probe(self):
        module = load_policy_workflow_module()
        original_exists = module.Path.exists

        def fake_exists(path):
            if path.name == ".git":
                raise PermissionError("blocked")
            return original_exists(path)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {"HARDFLOW_WORKFLOW_REPO": "", "OPENCLAW_WORKFLOW_REPO": ""},
        ), mock.patch.object(module.Path, "exists", fake_exists):
            resolved = module._discover_repo_root(Path(tmp) / "runtime" / "ops")

        self.assertIsInstance(resolved, Path)

    def test_view_without_state_or_task_center_fails_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-runs"
            with self.assertRaises(_mod.PipelineError) as ctx:
                _mod.build_view_payload(
                    argparse.Namespace(
                        workspace_root=missing,
                        run_id=None,
                        task_center_db=None,
                        task_id=None,
                        event_limit=100,
                    )
                )

        self.assertIn("workspace root not found", str(ctx.exception))

    def test_live_command_adapters_complete_and_write_project_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            research_script = scripts_dir / "research.py"
            code_script = scripts_dir / "code.py"
            verify_script = scripts_dir / "verify.py"
            verify_second_script = scripts_dir / "verify_second.py"
            deploy_script = scripts_dir / "deploy.py"
            git_publish_script = scripts_dir / "git_publish.py"
            research_script.write_text("print('# Research\\n- Source: official docs checked')\n", encoding="utf-8")
            code_script.write_text("print('# Patch Summary\\n- Implemented by live command adapter')\n", encoding="utf-8")
            verify_script.write_text("print('verification passed')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            deploy_script.write_text("print('deployment passed')\n", encoding="utf-8")
            git_publish_script.write_text("print('git publish passed 中文备注')\n", encoding="utf-8")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live command adapters.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="live-adapter",
                    dry_run=False,
                    research_commands=(py_cmd(research_script),),
                    requirements_discussion_commands=(py_cmd(research_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(verify_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    deployment_command=py_cmd(deploy_script),
                    git_publish_command=py_cmd(git_publish_script),
                    write_project_memory=True,
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertIn("command_external_research_1", state["artifacts"])
            self.assertIn("command_code_execution_1", state["artifacts"])
            self.assertIn("command_verification_1", state["artifacts"])
            self.assertIn("command_code_review_1", state["artifacts"])
            self.assertIn("command_code_review_2", state["artifacts"])
            self.assertIn("command_requirements_review_1", state["artifacts"])
            self.assertIn("command_requirements_review_2", state["artifacts"])
            self.assertIn("command_solution_review_1", state["artifacts"])
            self.assertIn("command_solution_review_2", state["artifacts"])
            self.assertIn("command_deployment_1", state["artifacts"])
            self.assertIn("command_git_publish_1", state["artifacts"])
            self.assertIn("deployment", state["artifacts"])
            self.assertIn("memory_writeback", state["artifacts"])
            self.assertIn("git_publish", state["artifacts"])
            review = Path(state["artifacts"]["code_review"]).read_text(encoding="utf-8")
            self.assertIn("Final verdict: pass", review)
            self.assertIn("Reviewer roles: reviewer-a, reviewer-b", review)
            self.assertIn("Distinct commands: true", review)
            git_publish = Path(state["artifacts"]["git_publish"]).read_text(encoding="utf-8")
            self.assertIn("Git publish runs only after verification", git_publish)
            command_report = json.loads(Path(state["artifacts"]["command_verification_1"]).read_text(encoding="utf-8"))
            self.assertTrue(command_report["ok"])
            review_report_1 = json.loads(Path(state["artifacts"]["command_code_review_1"]).read_text(encoding="utf-8"))
            review_report_2 = json.loads(Path(state["artifacts"]["command_code_review_2"]).read_text(encoding="utf-8"))
            self.assertEqual("reviewer-a", review_report_1["reviewer_role"])
            self.assertEqual("reviewer-b", review_report_2["reviewer_role"])
            changelog = root / "memory" / "demo" / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            self.assertIn("project-delivery:live-adapter", changelog.read_text(encoding="utf-8"))

    def test_live_solution_review_plan_blocker_soft_continues_to_code_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            review_a, review_b = self._write_review_pair(scripts_dir)
            solution_blocker = scripts_dir / "solution_blocker.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                (
                    "import os, pathlib\n"
                    "soft_gate = pathlib.Path(os.environ['PIPELINE_SOLUTION_REVIEW_SOFT_GATE_FILE'])\n"
                    "assert soft_gate.exists(), soft_gate\n"
                    "print('code execution absorbed solution review soft gate')\n"
                ),
                encoding="utf-8",
            )
            solution_blocker.write_text(
                (
                    "import pathlib\n"
                    "state = pathlib.Path(__file__).with_suffix('.count')\n"
                    "count = int(state.read_text() or '0') if state.exists() else 0\n"
                    "state.write_text(str(count + 1))\n"
                    "print('Reviewer role: reviewer-b')\n"
                    "print('Reviewer provider: zai')\n"
                    "print('Reviewer model: glm-5.1')\n"
                    "if count == 0:\n"
                    "    print('Final verdict: requires_revision')\n"
                    "    print('Blocker: verification_commands missing docs memory content assertion and create_if_missing rationale.')\n"
                    "else:\n"
                    "    print('Final verdict: ready_for_implement')\n"
                ),
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live mode where solution review plan-quality blockers should be absorbed.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="solution-soft-gate",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(solution_blocker)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    write_project_memory=True,
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertIn("solution_review_soft_gate", state["artifacts"])
            self.assertIn("command_code_execution_1", state["artifacts"])
            soft_gate = Path(state["artifacts"]["solution_review_soft_gate"]).read_text(encoding="utf-8")
            self.assertIn("Decision: soft_continue", soft_gate)
            self.assertIn("verification_commands missing docs memory content assertion", soft_gate)
            solution_review = Path(state["artifacts"]["solution_review"]).read_text(encoding="utf-8")
            self.assertIn("Final verdict: ready_for_implement", solution_review)
            self.assertIn("solution_review_revision_ledger", state["artifacts"])
            ledger = json.loads(Path(state["artifacts"]["solution_review_revision_ledger"]).read_text(encoding="utf-8"))
            self.assertTrue(ledger["entries"][0]["absorbed"])
            self.assertIn("solution review plan-quality blockers are converted into implementation constraints", soft_gate)
            revised_plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
            self.assertTrue(revised_plan.get("solution_review_absorbed_revision", {}).get("applied"))
            self.assertTrue(revised_plan.get("plan_findings", {}).get("repair_context_present"))

    def test_solution_review_negated_credential_contract_is_not_hard_gate(self):
        report = {
            "ok": True,
            "command": "review --reviewer-role reviewer-b --provider zai --model glm-5.1",
            "stdout": (
                "Final verdict: requires_revision\n"
                "Reviewer role: reviewer-b\n"
                "Reviewer provider: zai\n"
                "Reviewer model: glm-5.1\n"
                "Blocker: plan-quality issue only; do not read credentials, tokens, cookies, auth JSON, or private keys.\n"
                "没有发现凭证、secret、cookie/auth-state、真实交易、破坏性生产操作、force push 等硬风险；但 delivery_plan 缺少 must_change_targets。\n"
                "Blocker: remove pipeline_runner.py from target_files and move no_trading/simulation_only into runtime_contracts.\n"
            ),
            "stderr": "",
        }

        self.assertTrue(_mod.solution_review_can_soft_continue([report], "requires_revision"))
        self.assertEqual([], _mod.solution_review_hard_blocker_lines([report]))
        self.assertEqual("runtime_contract_not_file_path", _mod.plan_path_rejection_reason("simulation_only/no_trading"))

    def test_live_requirements_review_requires_two_independent_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            review_script = scripts_dir / "review.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            self._write_stage_review_script(review_script)

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live mode with only one requirements reviewer.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="single-reviewer-blocked",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_script),),
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("solution_review", state["failed_stage"])
            self.assertEqual("revise_solution", state["next_action"])
            self.assertIn("command_requirements_review_1", state["artifacts"])
            self.assertNotIn("command_requirements_review_2", state["artifacts"])
            review = Path(state["artifacts"]["requirements_review"]).read_text(encoding="utf-8")
            self.assertIn("Final verdict: ready_for_solution", review)
            self.assertIn("Review gate mode: degraded_single_valid", review)

    def test_live_requirements_review_rejects_duplicate_reviewer_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            review_1 = scripts_dir / "review_1.py"
            review_2 = scripts_dir / "review_2.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            self._write_stage_review_script(review_1, reviewer_role="reviewer-a")
            self._write_stage_review_script(review_2, reviewer_role="reviewer-a")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live mode with duplicated reviewer roles.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="duplicate-reviewer-role-blocked",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_1), py_cmd(review_2)),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("solution_review", state["failed_stage"])
            review = Path(state["artifacts"]["requirements_review"]).read_text(encoding="utf-8")
            self.assertIn("Reviewer roles: reviewer-a, reviewer-a", review)
            self.assertIn("Final verdict: ready_for_solution", review)

    def test_live_requirements_review_rejects_duplicate_review_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            review_script = scripts_dir / "review.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            self._write_stage_review_script(review_script, reviewer_role="reviewer-a")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            duplicated_command = py_cmd(review_script)
            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run live mode with duplicated reviewer command.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="duplicate-review-command-blocked",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(duplicated_command, duplicated_command),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("solution_review", state["failed_stage"])
            review = Path(state["artifacts"]["requirements_review"]).read_text(encoding="utf-8")
            self.assertIn("Distinct commands: false", review)
            self.assertIn("Final verdict: ready_for_solution", review)

    def test_code_review_failure_rolls_back_applied_workspace_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            review_a = scripts_dir / "review_a.py"
            review_b = scripts_dir / "review_b.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'bad_feature.txt').write_text('not accepted yet', encoding='utf-8')\n",
                encoding="utf-8",
            )
            self._write_stage_review_script(review_a, reviewer_role="reviewer-a")
            review_b.write_text(
                "import os\n"
                "stage = os.environ.get('PIPELINE_STAGE_NAME', '')\n"
                "verdicts = {\n"
                "    'requirements_review': 'ready_for_solution',\n"
                "    'solution_review': 'ready_for_implement',\n"
                "    'code_review': 'requires_revision',\n"
                "}\n"
                "print(f\"Final verdict: {verdicts.get(stage, 'requires_revision')}\")\n"
                "print('Reviewer role: reviewer-b')\n"
                "print('Reviewer provider: test-provider')\n"
                "print('Reviewer model: test-model-b')\n",
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Create a feature that code review must reject.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="rollback-code-review",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("code_review", state["failed_stage"])
            self.assertFalse((repo / "bad_feature.txt").exists())
            status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
            self.assertEqual("", status.stdout.strip())
            rollback_keys = [key for key in state["artifacts"] if key.startswith("rollback_code_review_failed")]
            self.assertEqual(1, len(rollback_keys))
            rollback_report = json.loads(Path(state["artifacts"][rollback_keys[0]]).read_text(encoding="utf-8"))
            self.assertTrue(rollback_report["ok"])
            self.assertTrue(rollback_report["reverted"])

    def test_verification_failure_rolls_back_applied_workspace_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            fail_verify = scripts_dir / "fail_verify.py"
            review_a, review_b = self._write_review_pair(scripts_dir)
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'feature.txt').write_text('pending verification', encoding='utf-8')\n",
                encoding="utf-8",
            )
            fail_verify.write_text("import sys\nprint('verification failed')\nsys.exit(7)\n", encoding="utf-8")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Create a feature that verification must reject.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="rollback-verification",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(fail_verify),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("verification", state["failed_stage"])
            self.assertFalse((repo / "feature.txt").exists())
            status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
            self.assertEqual("", status.stdout.strip())
            rollback_keys = [key for key in state["artifacts"] if key.startswith("rollback_verification_failed")]
            self.assertEqual(1, len(rollback_keys))

    def test_code_workspace_patch_refuses_dirty_command_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            (repo / "feature.txt").write_text("user change", encoding="utf-8")
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            review_a, review_b = self._write_review_pair(scripts_dir)
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'feature.txt').write_text('pending review', encoding='utf-8')\n",
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Do not apply code patch into a dirty command cwd.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="dirty-command-cwd",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("code_execution", state["failed_stage"])
            self.assertEqual("user change", (repo / "feature.txt").read_text(encoding="utf-8"))
            report = json.loads(Path(state["artifacts"]["command_code_execution_1"]).read_text(encoding="utf-8"))
            self.assertTrue(report["workspace_patch"]["command_cwd_preflight"]["dirty"])
            self.assertEqual(["feature.txt"], report["workspace_patch"]["command_cwd_preflight"]["overlapping_dirty_paths"])
            self.assertFalse(report["workspace_patch"]["applied_to_command_cwd"]["applied"])

    def test_rollback_failure_blocks_for_manual_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            mutate_and_fail = scripts_dir / "mutate_and_fail.py"
            review_a, review_b = self._write_review_pair(scripts_dir)
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'feature.txt').write_text('pending verification', encoding='utf-8')\n",
                encoding="utf-8",
            )
            mutate_and_fail.write_text(
                "import pathlib, sys\n"
                f"repo = pathlib.Path({str(repo)!r})\n"
                "(repo / 'feature.txt').write_text('changed after apply', encoding='utf-8')\n"
                "sys.exit(7)\n",
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Expose rollback failure as manual cleanup.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="rollback-failure",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(mutate_and_fail),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    command_cwd=repo,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("rollback_cleanup", state["failed_stage"])
            self.assertEqual("manual_cleanup_required", state["next_action"])
            self.assertEqual("changed after apply", (repo / "feature.txt").read_text(encoding="utf-8"))
            rollback_keys = [key for key in state["artifacts"] if key.startswith("rollback_verification_failed")]
            self.assertEqual(1, len(rollback_keys))
            rollback_report = json.loads(Path(state["artifacts"][rollback_keys[0]]).read_text(encoding="utf-8"))
            self.assertFalse(rollback_report["ok"])

    def test_live_agent_worktree_isolates_code_and_applies_diff_for_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            verify_script = scripts_dir / "verify.py"
            verify_second_script = scripts_dir / "verify_second.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'feature.txt').write_text('from isolated backend-dev workspace\\n', encoding='utf-8')\n"
                "print('code workspace', repo)\n",
                encoding="utf-8",
            )
            verify_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "assert (repo / 'feature.txt').read_text(encoding='utf-8').startswith('from isolated')\n"
                "print('verified workspace', repo)\n",
                encoding="utf-8",
            )
            verify_second_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "assert (repo / 'feature.txt').read_text(encoding='utf-8').startswith('from isolated')\n"
                "print('verified second workspace', repo)\n",
                encoding="utf-8",
            )
            review_a, review_b = self._write_review_pair(
                scripts_dir,
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "assert (repo / 'feature.txt').exists()",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Run coding in an isolated backend-dev workspace.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="agent-worktree",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(verify_script), py_cmd(verify_second_script)),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    memory_write_command=py_cmd(pass_script),
                    command_cwd=repo,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertTrue((repo / "feature.txt").exists())
            code_report = json.loads(Path(state["artifacts"]["command_code_execution_1"]).read_text(encoding="utf-8"))
            verify_report = json.loads(Path(state["artifacts"]["command_verification_1"]).read_text(encoding="utf-8"))
            verify_second_report = json.loads(
                Path(state["artifacts"]["command_verification_2"]).read_text(encoding="utf-8")
            )
            review_report = json.loads(Path(state["artifacts"]["command_code_review_1"]).read_text(encoding="utf-8"))
            review_second_report = json.loads(Path(state["artifacts"]["command_code_review_2"]).read_text(encoding="utf-8"))
            self.assertEqual("backend-dev", code_report["agent_id"])
            self.assertEqual("tester", verify_report["agent_id"])
            self.assertEqual("tester", verify_second_report["agent_id"])
            self.assertEqual("reviewer", review_report["agent_id"])
            self.assertEqual("reviewer", review_second_report["agent_id"])
            self.assertNotEqual(str(repo), code_report["cwd"])
            self.assertNotEqual(str(repo), verify_report["cwd"])
            self.assertEqual(verify_report["cwd"], verify_second_report["cwd"])
            self.assertNotEqual(str(repo), review_report["cwd"])
            self.assertTrue(Path(code_report["workspace_patch_file"]).exists())
            self.assertIn("agent_workspace_manifest", state["artifacts"])
            manifest = json.loads(Path(state["artifacts"]["agent_workspace_manifest"]).read_text(encoding="utf-8"))
            self.assertIn("backend-dev", json.dumps(manifest, ensure_ascii=False))

    def test_nested_agent_workspace_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            workspace_dir = repo / ".workflow" / "agent-workspaces" / "code_execution" / "backend-dev"
            with self.assertRaises(_mod.PipelineError) as ctx:
                _mod.ensure_agent_repo(repo, workspace_dir)
            self.assertIn("must be outside command cwd", str(ctx.exception))

    def test_deployment_command_failure_blocks_before_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            deploy_script = scripts_dir / "deploy.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            deploy_script.write_text("import sys\nprint('deployment failed')\nsys.exit(7)\n", encoding="utf-8")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Deploy after passing review.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="deploy-failure",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    deployment_command=py_cmd(deploy_script),
                    write_project_memory=True,
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("deployment", state["failed_stage"])
            self.assertEqual("return_to_deployment", state["next_action"])
            self.assertIn("deployment", state["artifacts"])
            self.assertNotIn("acceptance", state["artifacts"])

    def test_git_publish_command_failure_blocks_after_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            git_publish_script.write_text("import sys\nprint('git push failed')\nsys.exit(9)\n", encoding="utf-8")

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Publish after passing review and writeback.",
                    workspace_root=root / "runs",
                    project_memory_root=root / "memory",
                    run_id="git-publish-failure",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    memory_write_command=py_cmd(pass_script),
                    git_publish_command=py_cmd(git_publish_script),
                    command_cwd=ROOT,
                )
            )

            self.assertEqual("blocked", state["status"])
            self.assertEqual("git_publish", state["failed_stage"])
            self.assertEqual("fix_git_publish", state["next_action"])
            self.assertIn("writeback", state["artifacts"])
            self.assertIn("git_publish", state["artifacts"])

    def test_git_publish_receives_memory_writeback_workspace_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            code_script = scripts_dir / "code.py"
            memory_write_script = scripts_dir / "memory_write.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            code_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "(repo / 'feature.txt').write_text('implemented\\n', encoding='utf-8')\n"
                "print('implemented')\n",
                encoding="utf-8",
            )
            memory_write_script.write_text(
                "import os, pathlib, sys\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "feature = repo / 'feature.txt'\n"
                "if not feature.exists():\n"
                "    print('missing code patch before writeback')\n"
                "    sys.exit(2)\n"
                "path = repo / 'memory' / 'demo' / 'WRITEBACK.md'\n"
                "path.parent.mkdir(parents=True, exist_ok=True)\n"
                "path.write_text('写回证据\\n', encoding='utf-8')\n"
                "print('memory writeback passed')\n",
                encoding="utf-8",
            )
            git_publish_script.write_text(
                "import os, pathlib, sys\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "checks = [repo / 'feature.txt', repo / 'memory' / 'demo' / 'WRITEBACK.md']\n"
                "missing = [str(path.relative_to(repo)) for path in checks if not path.exists()]\n"
                "if missing:\n"
                "    print('missing publish inputs: ' + ', '.join(missing))\n"
                "    sys.exit(3)\n"
                "print('git publish sees writeback 中文备注')\n",
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Publish code and writeback as one accepted change set.",
                    workspace_root=root / "runs",
                    project_memory_root=repo / ".workflow" / "project-memory",
                    run_id="git-publish-writeback",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    memory_write_command=py_cmd(memory_write_script),
                    git_publish_command=py_cmd(git_publish_script),
                    command_cwd=repo,
                )
            )

            self.assertEqual("completed", state["status"])
            self.assertIn("git_publish_input_patch_report", state["artifacts"])
            input_report = json.loads(Path(state["artifacts"]["git_publish_input_patch_report"]).read_text(encoding="utf-8"))
            self.assertEqual("memory_writeback_workspace_patch", input_report["source"])
            git_publish_report = json.loads(Path(state["artifacts"]["command_git_publish_1"]).read_text(encoding="utf-8"))
            self.assertEqual("memory_writeback_workspace_patch", git_publish_report["input_patch"]["source"])
            self.assertIn("git publish sees writeback", git_publish_report["stdout"])

    def test_git_publish_does_not_publish_unaccepted_dirty_command_cwd_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            (repo / "dirty.txt").write_text("not accepted by pipeline\n", encoding="utf-8")

            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            pass_script = scripts_dir / "pass.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_a, review_b = self._write_review_pair(scripts_dir)
            git_publish_script.write_text(
                "import os, pathlib, sys\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "if (repo / 'dirty.txt').exists():\n"
                "    print('dirty command cwd file leaked into publish workspace')\n"
                "    sys.exit(4)\n"
                "print('git publish input is clean')\n",
                encoding="utf-8",
            )

            def py_cmd(path: Path) -> str:
                return f'"{sys.executable}" "{path}"'

            state = run_pipeline(
                PipelineConfig(
                    project_key="demo",
                    requirement="Publish only accepted pipeline changes.",
                    workspace_root=root / "runs",
                    project_memory_root=repo / ".workflow" / "project-memory",
                    run_id="git-publish-no-dirty",
                    dry_run=False,
                    research_commands=(py_cmd(pass_script),),
                    requirements_discussion_commands=(py_cmd(pass_script),),
                    requirements_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    solution_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_commands=(py_cmd(review_a), py_cmd(review_b)),
                    memory_write_command=py_cmd(pass_script),
                    git_publish_command=py_cmd(git_publish_script),
                    command_cwd=repo,
                )
            )

            self.assertEqual("completed", state["status"])
            input_report = json.loads(Path(state["artifacts"]["git_publish_input_patch_report"]).read_text(encoding="utf-8"))
            self.assertEqual("no_accepted_patch", input_report["source"])
            git_publish_report = json.loads(Path(state["artifacts"]["command_git_publish_1"]).read_text(encoding="utf-8"))
            self.assertIn("git publish input is clean", git_publish_report["stdout"])

    def test_delivery_plan_uses_original_requirement_not_template_scope_fragments(self):
        requirement = (
            "【原始需求】按用户确认的顺序依次推进 SmartMultiPlatformArbitrage：第一轮先执行 P0 口径修正。"
            "删除 Kraken/MEXC 币股 public adapter 代码和测试/文档口径；币股现货不进入 MVP；"
            "借币套利放到最后，并拆成交易所借币与链上借币两个后期阶段。保持 PRODUCTION_TRADING_ENABLED=false，不启动真实交易、不下单、不划转、不读取或打印凭证。\n\n"
            "【强制目标文件约束】target_files 必须使用真实 repo-relative 路径，至少检查/按需修改："
            "智能多平台套利/api/stock_token_public_adapter.py、智能多平台套利/api/routes/stock_tokens.py、"
            "智能多平台套利/api/static/dashboard/index.html、tests/test_stock_token_public_adapter.py、todo.md。"
            "运行证据目录包含 run_meta.json 和 pipeline_state.json，但这些只是 pipeline artifact，不是 target_files。"
            "上一轮 reviewer 文本提到 PROJECT_PROFILE.md、DECISIONS.md、code_review.md、deployment_report.md、"
            "stock_token_public_adapter.py、routes/stock_tokens.py、PROJECT_PROFILE.md/DECISIONS.md；这些都是 basename/artifact drift，"
            "不能进入 target_files，只有 memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md 和 "
            "memory/smart-multi-platform-arbitrage/DECISIONS.md 才是合法 repo-relative memory 目标。"
            "禁止使用 /api/... 这种仓库根外路径。\n\n"
            "【强制验证】必须运行并记录：pytest targeted tests tests/test_stock_token_public_adapter.py tests/test_dashboard_api.py、"
            "python -m compileall -q 智能多平台套利 tests、git diff --check、残留口径扫描 Kraken/MEXC/spot MVP/cross_venue_spot_public_snapshot、"
            "安全扫描确认无凭证/POST私有端点/下单/划转/签名调用/PRODUCTION_TRADING_ENABLED=true、"
            "只读内控 API smoke：GET /health、GET /api/strategy/status。"
        )
        resolved = (
            "# Resolved Requirement\n\n## Original Requirement\n"
            f"{requirement}\n\n"
            "## Accepted Requirement Source\n"
            "The accepted implementation scope is the original requirement plus the\n"
            "completed requirements discussion and requirements review below. Downstream\n"
            "stages must use this artifact as the handoff contract and must not fall\n"
            "back to a generic pipeline template.\n"
        )
        plan = _mod.compile_delivery_plan(
            PipelineConfig(
                project_key="demo",
                verification_commands=("/usr/bin/python3 /home/arbops/.hermes/ops/smart_arb_live_bridge.py --stage verification",),
            ),
            {"host": "hermes"},
            resolved,
            {},
        )

        scope_text = "\n".join(item["description"] for item in plan["scope_slices"])
        self.assertIn("P0 口径修正", scope_text)
        self.assertNotIn("accepted implementation scope", scope_text)
        self.assertNotIn("generic pipeline template", scope_text)
        paths = [item["path"] for item in plan["target_files"]]
        self.assertIn("智能多平台套利/api/stock_token_public_adapter.py", paths)
        self.assertIn("智能多平台套利/api/routes/stock_tokens.py", paths)
        self.assertNotIn("智能多平台套利/api/static/dashboard/index.html", paths)
        inspect_only_paths = [item["path"] for item in plan["inspect_only_sources"]]
        self.assertIn("智能多平台套利/api/static/dashboard/index.html", inspect_only_paths)
        self.assertNotIn("run_meta.json", paths)
        self.assertNotIn("pipeline_state.json", paths)
        self.assertNotIn("PROJECT_PROFILE.md", paths)
        self.assertNotIn("DECISIONS.md", paths)
        self.assertNotIn("code_review.md", paths)
        self.assertNotIn("deployment_report.md", paths)
        self.assertNotIn("stock_token_public_adapter.py", paths)
        self.assertNotIn("routes/stock_tokens.py", paths)
        self.assertNotIn("PROJECT_PROFILE.md/DECISIONS.md", paths)
        self.assertNotIn("memory/smart-multi-platform-arbitrage/", paths)
        self.assertFalse(any(path.startswith("curl ") for path in paths))
        read_only_paths = [item["path"] for item in plan["read_only_sources"]]
        self.assertIn("memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md", read_only_paths)
        self.assertIn("memory/smart-multi-platform-arbitrage/DECISIONS.md", read_only_paths)
        self.assertIn("tests/test_stock_token_public_adapter.py", paths)
        self.assertNotIn("/api/stock_token_public_adapter.py", paths)
        negated = [item for item in plan.get("plan_findings", {}).get("filtered_target_candidates", []) if item.get("reason") == "negated_context"]
        self.assertFalse(any(item.get("path") == "智能多平台套利/api/static/dashboard/index.html" for item in negated))
        commands = [item["command"] for item in plan["verification_commands"]]
        self.assertIn("/home/arbops/.venvs/smart-arbitrage/bin/python -m pytest -q tests/test_stock_token_public_adapter.py tests/test_dashboard_api.py", commands)
        self.assertIn("/home/arbops/.venvs/smart-arbitrage/bin/python -B -m compileall -q 智能多平台套利 tests", commands)
        self.assertIn("git diff --check", commands)
        self.assertIn("test -f memory/smart-multi-platform-arbitrage/PROJECT_PROFILE.md", commands)
        self.assertIn("test -f memory/smart-multi-platform-arbitrage/DECISIONS.md", commands)
        self.assertTrue(any("git diff --name-only" in command for command in commands))
        self.assertFalse(any("Kraken|MEXC|spot MVP|cross_venue_spot_public_snapshot" in command for command in commands))
        self.assertTrue(any("PRODUCTION_TRADING_ENABLED" in command for command in commands))
        self.assertIn("curl -fsS http://127.0.0.1:18080/health", commands)
        self.assertIn("curl -fsS http://127.0.0.1:18080/api/strategy/status", commands)
        self.assertFalse(any("smart_arb_live_bridge.py" in command for command in commands))
        self.assertNotIn("pytest", commands)
        self.assertFalse(any(command.endswith("`") for command in commands))
        self.assertFalse(any("通过" in command or "必须" in command or "pytest:" == command for command in commands))


    def test_requirements_discussion_includes_solution_review_readiness_contract(self):
        discussion = _mod.render_requirements_discussion("Update dashboard safely")
        self.assertIn("Solution Review Readiness Discussion", discussion)
        self.assertIn("must_change_targets", discussion)
        self.assertIn("read_only_sources", discussion)
        self.assertIn("reference_patterns", discussion)
        self.assertIn("target_files", discussion)

    def test_compile_delivery_plan_separates_read_only_sources_and_reference_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "智能多平台套利" / "api" / "routes").mkdir(parents=True)
            (repo / "智能多平台套利" / "api" / "routes" / "strategy.py").write_text("# route\n", encoding="utf-8")
            (repo / "智能多平台套利" / "api" / "routes" / "stock_tokens.py").write_text("# reference\n", encoding="utf-8")
            (repo / "智能多平台套利" / "config_security.py").write_text("# safety\n", encoding="utf-8")
            (repo / "scripts").mkdir(parents=True)
            (repo / "scripts" / "nofx_hermes_services.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (repo / "MEMORY.md").write_text("facts\n", encoding="utf-8")
            (repo / "智能多平台套利" / "arbitrage_config.json5").write_text("{}\n", encoding="utf-8")
            (repo / "智能多平台套利" / "setup.py").write_text("# setup\n", encoding="utf-8")
            (repo / "智能多平台套利" / "apollo").mkdir(parents=True)
            (repo / "智能多平台套利" / "apollo" / "trade.py").write_text("# apollo\n", encoding="utf-8")
            (repo / "智能多平台套利" / "arbitrage" / "market_adapters").mkdir(parents=True)
            (repo / "智能多平台套利" / "arbitrage" / "market_adapters" / "hyperliquid_ws.py").write_text("# hl\n", encoding="utf-8")
            (repo / "智能多平台套利" / "arbitrage" / "market_adapters" / "__init__.py").write_text("# registry\n", encoding="utf-8")
            (repo / "智能多平台套利" / "api" / "static" / "dashboard").mkdir(parents=True)
            (repo / "智能多平台套利" / "api" / "static" / "dashboard" / "dashboard.js").write_text("// dashboard\n", encoding="utf-8")
            (repo / "智能多平台套利" / "api" / "static" / "dashboard" / "index.html").write_text("<html></html>\n", encoding="utf-8")
            artifacts = {}
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            discussion = run_dir / "requirements_discussion.md"
            discussion.write_text(
                "# Discussion\n"
                "## Solution Review Readiness Contract\n"
                "must_change_targets: 智能多平台套利/api/routes/strategy.py\n"
                "read_only_sources: 智能多平台套利/arbitrage_config.json5 是只读源，不建议修改。\n"
                "reference_patterns: 智能多平台套利/api/routes/stock_tokens.py 只是参考模式，不应默认修改。\n"
                "inspect_only: 智能多平台套利/config_security.py 应作为 safety contract reference，除非测试发现缺口。\n"
                "优先遵守/读取 MEMORY.md，不等于必须写回。\n"
                "scripts/nofx_hermes_services.sh 只是运维 smoke 参考，不是本轮业务修改目标。\n"
                "solution_review_revision_ledger.json 是 pipeline artifact，不是 repo target。\n"
                "graph.json 是 graphify artifact，不是 repo target。\n"
                "智能多平台套利/setup.py 是 packaging 文件，不是本轮业务修改目标。\n"
                "Apollo 历史 MEXC 代码 智能多平台套利/apollo/trade.py 不因名称命中被删除。\n"
                "Hyperliquid 不在本轮新增真实 adapter，智能多平台套利/arbitrage/market_adapters/hyperliquid_ws.py 仅 inspect。\n"
                "智能多平台套利/api/static/dashboard/index.html、智能多平台套利/api/static/dashboard/dashboard.js、智能多平台套利/arbitrage/market_adapters/__init__.py 当前未发现硬编码，仅 inspect。\n"
                "Feishu Base Izh8bWlF5aFKmYsvUBMcYKbonQf / 交易所模块 tbl1jj9DTcfAd6tZ / 平台范围 是只读事实源。\n"
                "api_contracts: GET /api/stock-tokens/status returns redacted non-sensitive config.\n",
                encoding="utf-8",
            )
            review = run_dir / "requirements_review.md"
            review.write_text("Final verdict: ready_for_solution\n", encoding="utf-8")
            artifacts["requirements_discussion"] = str(discussion)
            artifacts["requirements_review"] = str(review)
            plan = _mod.compile_delivery_plan(
                PipelineConfig(project_key="demo", command_cwd=repo),
                {"host": "hermes"},
                "必须修改 智能多平台套利/api/routes/strategy.py，交付只读配置快照。Feishu Base Izh8bWlF5aFKmYsvUBMcYKbonQf 平台范围只读核对。",
                artifacts,
            )

            target_paths = [item["path"] for item in plan["target_files"]]
            self.assertIn("智能多平台套利/api/routes/strategy.py", target_paths)
            self.assertNotIn("智能多平台套利/arbitrage_config.json5", target_paths)
            self.assertNotIn("智能多平台套利/api/routes/stock_tokens.py", target_paths)
            self.assertNotIn("智能多平台套利/config_security.py", target_paths)
            self.assertNotIn("MEMORY.md", target_paths)
            self.assertNotIn("scripts/nofx_hermes_services.sh", target_paths)
            self.assertNotIn("solution_review_revision_ledger.json", target_paths)
            self.assertNotIn("智能多平台套利/apollo/trade.py", target_paths)
            self.assertNotIn("智能多平台套利/arbitrage/market_adapters/hyperliquid_ws.py", target_paths)
            self.assertNotIn("graph.json", target_paths)
            self.assertNotIn("智能多平台套利/setup.py", target_paths)
            self.assertNotIn("智能多平台套利/api/static/dashboard/index.html", target_paths)
            self.assertNotIn("智能多平台套利/api/static/dashboard/dashboard.js", target_paths)
            self.assertNotIn("智能多平台套利/arbitrage/market_adapters/__init__.py", target_paths)
            self.assertIn("智能多平台套利/arbitrage_config.json5", [item["path"] for item in plan["read_only_sources"]])
            self.assertIn("MEMORY.md", [item["path"] for item in plan["read_only_sources"]])
            self.assertTrue(any("Feishu Base Izh8bWlF5aFKmYsvUBMcYKbonQf" in item["path"] for item in plan["read_only_sources"]));
            self.assertIn("智能多平台套利/api/routes/stock_tokens.py", [item["path"] for item in plan["reference_patterns"]])
            self.assertIn("智能多平台套利/config_security.py", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("scripts/nofx_hermes_services.sh", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("solution_review_revision_ledger.json", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/apollo/trade.py", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/arbitrage/market_adapters/hyperliquid_ws.py", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("graph.json", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/setup.py", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/api/static/dashboard/index.html", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/api/static/dashboard/dashboard.js", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("智能多平台套利/arbitrage/market_adapters/__init__.py", [item["path"] for item in plan["inspect_only_sources"]])
            self.assertIn("solution_review_readiness", plan)
            self.assertIn("must_change_targets", plan)
            self.assertEqual(["智能多平台套利/api/routes/strategy.py"], [item["path"] for item in plan["must_change_targets"]])
            self.assertIn("api_contracts", plan)
            self.assertTrue(any(item.get("endpoint") == "/api/stock-tokens/status" and "exclude kraken/mexc" in item.get("contract", "") for item in plan["api_contracts"]))
            self.assertIn("setup.py / packaging / dependency files", plan["forbidden_targets"])
            rendered = _mod.render_solution(plan)
            self.assertIn("## Must-change Targets", rendered)
            self.assertIn("## API Contracts", rendered)
            findings = plan.get("plan_findings", {}).get("filtered_target_candidates", [])
            self.assertTrue(
                any(item.get("reason") in {"read_only_source", "reference_pattern", "inspect_only_context", "read_only_or_reference_context"} for item in findings)
            )



if __name__ == "__main__":
    unittest.main()

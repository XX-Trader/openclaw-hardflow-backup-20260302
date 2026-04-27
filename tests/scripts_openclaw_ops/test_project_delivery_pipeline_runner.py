import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
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
                "external_research",
                "requirements_package",
                "requirements_review",
                "solution_package",
                "solution_review",
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
            memory_dir = Path(tmp) / "project-memory" / "demo"
            self.assertTrue((memory_dir / "RETRIEVAL_MANIFEST.json").exists())

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
            scripts_dir = root / "cmds"
            scripts_dir.mkdir()
            research_script = scripts_dir / "research.py"
            code_script = scripts_dir / "code.py"
            verify_script = scripts_dir / "verify.py"
            verify_second_script = scripts_dir / "verify_second.py"
            review_script = scripts_dir / "review.py"
            deploy_script = scripts_dir / "deploy.py"
            git_publish_script = scripts_dir / "git_publish.py"
            research_script.write_text("print('# Research\\n- Source: official docs checked')\n", encoding="utf-8")
            code_script.write_text("print('# Patch Summary\\n- Implemented by live command adapter')\n", encoding="utf-8")
            verify_script.write_text("print('verification passed')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass\\nConfidence: high')\n", encoding="utf-8")
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
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(verify_script),),
                    code_review_command=py_cmd(review_script),
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
            self.assertIn("command_deployment_1", state["artifacts"])
            self.assertIn("command_git_publish_1", state["artifacts"])
            self.assertIn("deployment", state["artifacts"])
            self.assertIn("memory_writeback", state["artifacts"])
            self.assertIn("git_publish", state["artifacts"])
            review = Path(state["artifacts"]["code_review"]).read_text(encoding="utf-8")
            self.assertIn("Final verdict: pass", review)
            git_publish = Path(state["artifacts"]["git_publish"]).read_text(encoding="utf-8")
            self.assertIn("Git publish runs only after verification", git_publish)
            command_report = json.loads(Path(state["artifacts"]["command_verification_1"]).read_text(encoding="utf-8"))
            self.assertTrue(command_report["ok"])
            changelog = root / "memory" / "demo" / "CHANGELOG.ndjson"
            self.assertTrue(changelog.exists())
            self.assertIn("project-delivery:live-adapter", changelog.read_text(encoding="utf-8"))

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
            review_script = scripts_dir / "review.py"
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
            review_script.write_text(
                "import os, pathlib\n"
                "repo = pathlib.Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
                "assert (repo / 'feature.txt').exists()\n"
                "print('Final verdict: pass')\n",
                encoding="utf-8",
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
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(verify_script), py_cmd(verify_second_script)),
                    code_review_command=py_cmd(review_script),
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
            self.assertEqual("backend-dev", code_report["agent_id"])
            self.assertEqual("tester", verify_report["agent_id"])
            self.assertEqual("tester", verify_second_report["agent_id"])
            self.assertEqual("reviewer", review_report["agent_id"])
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
            review_script = scripts_dir / "review.py"
            deploy_script = scripts_dir / "deploy.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass')\n", encoding="utf-8")
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
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_command=py_cmd(review_script),
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
            review_script = scripts_dir / "review.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass')\n", encoding="utf-8")
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
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_command=py_cmd(review_script),
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
            review_script = scripts_dir / "review.py"
            code_script = scripts_dir / "code.py"
            memory_write_script = scripts_dir / "memory_write.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass')\n", encoding="utf-8")
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
                    code_command=py_cmd(code_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_command=py_cmd(review_script),
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
            review_script = scripts_dir / "review.py"
            git_publish_script = scripts_dir / "git_publish.py"
            pass_script.write_text("print('ok')\n", encoding="utf-8")
            review_script.write_text("print('Final verdict: pass')\n", encoding="utf-8")
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
                    code_command=py_cmd(pass_script),
                    verification_commands=(py_cmd(pass_script),),
                    code_review_command=py_cmd(review_script),
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


if __name__ == "__main__":
    unittest.main()

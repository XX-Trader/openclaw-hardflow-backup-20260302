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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_fixture_repo(root: Path) -> None:
    write_text(
        root / "openclaw/openclaw.json",
        json.dumps(
            {
                "agents": {
                    "list": [
                        {
                            "id": "main",
                            "name": "Main",
                            "default": True,
                            "model": "openai-codex/gpt-5.4",
                            "workspace": "/workspace/main",
                            "subagents": {"allowAgents": ["frontend-dev"]},
                        },
                        {
                            "id": "frontend-dev",
                            "name": "Frontend",
                            "default": False,
                            "model": "openai-codex/gpt-5.3-codex",
                            "workspace": "/workspace/frontend",
                        },
                        {
                            "id": "web-agent",
                            "name": "Web",
                            "default": False,
                            "model": "glmcode/glm-4.7",
                            "workspace": "/workspace/web",
                        },
                    ]
                },
                "hooks": {
                    "internal": {
                        "enabled": True,
                        "entries": {
                            "command-logger": {"enabled": True},
                            "hardflow-policy-enforcer": {"enabled": True},
                        },
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        root / "skills/by_agent/main.md",
        "\n".join(
            [
                "# main",
                "",
                "- skills_count: 2",
                "- source.matrix_count: 2",
                "- source.soul_count: 2",
                "",
                "## Skills",
                "",
                "- agent-manager (present)",
                "- using-superpowers (missing)",
            ]
        )
        + "\n",
    )
    write_text(
        root / "skills/by_agent/frontend-dev.md",
        "\n".join(
            [
                "# frontend-dev",
                "",
                "- skills_count: 1",
                "- source.matrix_count: 1",
                "- source.soul_count: 1",
                "",
                "## Skills",
                "",
                "- frontend-design (present)",
            ]
        )
        + "\n",
    )
    write_text(
        root / "agents/main/SOUL.md",
        "\n".join(
            [
                "# main",
                "",
                "## 技能主线",
                "`agent-manager, using-superpowers`",
            ]
        )
        + "\n",
    )
    write_text(
        root / "agents/frontend-dev/SOUL.md",
        "\n".join(
            [
                "# frontend-dev",
                "",
                "## 技能主线",
                "`frontend-design`",
            ]
        )
        + "\n",
    )
    write_text(root / "agents/web-agent/SOUL.md", "# web-agent\n")
    write_text(
        root / "hooks/hardflow-policy-enforcer/HOOK.md",
        "\n".join(
            [
                "---",
                "name: hardflow-policy-enforcer",
                'metadata: { "openclaw": { "events": ["command:new", "command:stop"] } }',
                "---",
                "",
                "# hook",
            ]
        )
        + "\n",
    )
    write_text(
        root / "cron/jobs_agent_mapping.md",
        "\n".join(
            [
                "# OpenClaw Cron -> Agent Mapping",
                "- job-1 | task_executor_10m | agent=main | exists=True | schedule=600000",
                "- job-2 | unknown_job | agent=ghost-agent | exists=False | schedule=0 4 * * *",
            ]
        )
        + "\n",
    )
    write_text(
        root / "agents/agent_index.json",
        json.dumps(
            [
                {
                    "id": "main",
                    "default": False,
                    "allowAgents": ["frontend-dev"],
                },
                {
                    "id": "frontend-dev",
                    "default": True,
                    "allowAgents": [],
                },
                {
                    "id": "web-agent",
                    "default": False,
                    "allowAgents": [],
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        root / "agents/agent_index.md",
        "\n".join(
            [
                "# Agent Index",
                "",
                "## main",
                "- default: False",
                "",
                "## frontend-dev",
                "- default: True",
                "",
                "## web-agent",
                "- default: False",
            ]
        )
        + "\n",
    )
    write_text(
        root / "scripts/openclaw-ops/runtime-required-skills.json",
        json.dumps(
            {
                "skills": [
                    {
                        "name": "frontend-design-ultimate",
                        "conflicts": ["frontend-design"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


class InspectRuntimeBindingsTests(unittest.TestCase):
    def test_build_report_detects_missing_skills_and_index_drift(self):
        module = load_module(
            "inspect_runtime_bindings",
            "scripts/openclaw-ops/inspect_runtime_bindings.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            build_fixture_repo(repo_root)

            report = module.build_runtime_bindings_report(repo_root)

        self.assertEqual(report["missing_skills"], ["using-superpowers"])
        self.assertEqual(report["declared_skills"], ["agent-manager", "frontend-design", "using-superpowers"])

        agents = {item["agent_id"]: item for item in report["agents"]}
        self.assertEqual(agents["main"]["missing_skills"], ["using-superpowers"])
        self.assertEqual(agents["web-agent"]["declared_skills"], [])
        self.assertEqual(agents["main"]["matrix_only_skills"], [])
        self.assertEqual(agents["main"]["soul_only_skills"], [])

        hook_events = report["hook_events"]
        self.assertEqual(hook_events["command:new"], ["hardflow-policy-enforcer"])
        self.assertEqual(hook_events["command:stop"], ["hardflow-policy-enforcer"])

        runtime_conflicts = report["runtime_skill_conflicts"]
        self.assertEqual(len(runtime_conflicts), 1)
        self.assertEqual(runtime_conflicts[0]["affected_agents"], ["frontend-dev"])

        cron_jobs = {item["job_id"]: item for item in report["cron_agent_bindings"]}
        self.assertTrue(cron_jobs["job-1"]["agent_exists"])
        self.assertFalse(cron_jobs["job-2"]["agent_exists"])

        index_drift = report["index_drift"]
        self.assertFalse(index_drift["default_agent"]["matches"])
        self.assertEqual(index_drift["default_agent"]["openclaw"], ["main"])
        self.assertEqual(index_drift["default_agent"]["agent_index_json"], ["frontend-dev"])
        self.assertEqual(index_drift["default_agent"]["agent_index_md"], ["frontend-dev"])
        self.assertEqual(index_drift["missing_by_agent_docs"], ["web-agent"])

    def test_main_emit_json_outputs_machine_readable_report(self):
        module = load_module(
            "inspect_runtime_bindings",
            "scripts/openclaw-ops/inspect_runtime_bindings.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            build_fixture_repo(repo_root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = module.main(["--repo-root", str(repo_root), "--emit-json"])

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["summary"]["agent_count"], 3)
        self.assertEqual(report["summary"]["hook_count"], 2)
        self.assertEqual(report["summary"]["cron_binding_count"], 2)


if __name__ == "__main__":
    unittest.main()

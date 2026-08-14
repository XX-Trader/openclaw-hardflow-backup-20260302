#!/usr/bin/env python3
"""Run the live delivery pipeline against disposable Python and frontend repositories."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = ROOT / "skills" / "library" / "project-delivery-pipeline" / "scripts" / "pipeline_runner.py"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location("generic_fixture_pipeline_runner", PIPELINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"pipeline module could not be loaded: {PIPELINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def command_text(args: list[str]) -> str:
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def run_checked(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        rendered = command_text(args)
        raise RuntimeError(f"command failed ({proc.returncode}): {rendered}\n{proc.stdout}\n{proc.stderr}")
    return proc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def initialize_repository(root: Path, kind: str) -> tuple[Path, Path, str]:
    repo = root / "repo"
    remote = root / "remote.git"
    repo.mkdir(parents=True)
    run_checked(["git", "init", "--bare", str(remote)])
    run_checked(["git", "init", "-b", "main"], repo)
    run_checked(["git", "config", "user.name", "HardFlow Fixture"], repo)
    run_checked(["git", "config", "user.email", "fixture@example.invalid"], repo)

    if kind == "python":
        write_text(repo / "README.md", "# Generic Python fixture\n")
        write_text(repo / "items.py", "def normalize_items(values):\n    return list(values)\n")
        write_text(
            repo / "test_items.py",
            "import unittest\n\nfrom items import normalize_items\n\n\n"
            "class ItemTests(unittest.TestCase):\n"
            "    def test_preserves_initial_values(self):\n"
            "        self.assertEqual(['A'], normalize_items(['A']))\n\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
        )
    elif kind == "frontend":
        write_text(repo / "README.md", "# Generic frontend fixture\n")
        write_text(
            repo / "package.json",
            json.dumps(
                {
                    "name": "generic-frontend-fixture",
                    "version": "1.0.0",
                    "private": True,
                    "type": "module",
                    "scripts": {"build": "node scripts/build.mjs", "test": "node --test"},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        write_text(repo / "src" / "format.mjs", "export function summarize(items) { return items.join(', '); }\n")
        write_text(
            repo / "test" / "format.test.mjs",
            "import test from 'node:test';\n"
            "import assert from 'node:assert/strict';\n"
            "import { summarize } from '../src/format.mjs';\n\n"
            "test('joins initial values', () => {\n"
            "  assert.equal(summarize(['A', 'B']), 'A, B');\n"
            "});\n",
        )
        write_text(
            repo / "scripts" / "build.mjs",
            "import { mkdir, readFile, writeFile } from 'node:fs/promises';\n"
            "const source = await readFile(new URL('../src/format.mjs', import.meta.url), 'utf8');\n"
            "await mkdir(new URL('../dist/', import.meta.url), { recursive: true });\n"
            "await writeFile(new URL('../dist/bundle.txt', import.meta.url), source, 'utf8');\n"
            "console.log('build completed');\n",
        )
        write_text(repo / ".gitignore", "node_modules/\ndist/\n")
    else:
        raise ValueError(f"unknown fixture kind: {kind}")

    run_checked(["git", "add", "."], repo)
    run_checked(["git", "commit", "-m", "initial fixture"], repo)
    run_checked(["git", "remote", "add", "origin", str(remote)], repo)
    run_checked(["git", "push", "-u", "origin", "main"], repo)
    initial_sha = run_checked(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    return repo, remote, initial_sha


def write_review_pair(scripts: Path, kind: str) -> tuple[Path, Path]:
    if kind == "python":
        assertion = "assert 'sorted(set(normalized))' in (repo / 'items.py').read_text(encoding='utf-8')"
    else:
        assertion = "assert '.filter(Boolean)' in (repo / 'src' / 'format.mjs').read_text(encoding='utf-8')"

    paths: list[Path] = []
    for suffix, role, model in (("a", "reviewer-a", "fixture-model-a"), ("b", "reviewer-b", "fixture-model-b")):
        path = scripts / f"review_{suffix}.py"
        write_text(
            path,
            "import os\n"
            "from pathlib import Path\n"
            "stage = os.environ.get('PIPELINE_STAGE_NAME', '')\n"
            "if stage == 'code_review':\n"
            "    repo = Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
            f"    {assertion}\n"
            "verdicts = {'requirements_review': 'ready_for_solution', "
            "'solution_review': 'ready_for_implement', 'code_review': 'pass'}\n"
            "print(f\"Final verdict: {verdicts.get(stage, 'pass')}\")\n"
            "print('Confidence: high')\n"
            f"print('Reviewer role: {role}')\n"
            "print('Reviewer provider: fixture-provider')\n"
            f"print('Reviewer model: {model}')\n",
        )
        paths.append(path)
    return paths[0], paths[1]


def write_fixture_commands(root: Path, kind: str) -> dict[str, Path]:
    scripts = root / "commands"
    scripts.mkdir(parents=True)
    pass_script = scripts / "context.py"
    write_text(pass_script, "print('fixture context collected and checked')\n")

    code_script = scripts / "implement.py"
    if kind == "python":
        write_text(
            code_script,
            "import os\nfrom pathlib import Path\n"
            "repo = Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
            "(repo / 'items.py').write_text(\"def normalize_items(values):\\n"
            "    normalized = [str(value).strip().lower() for value in values if str(value).strip()]\\n"
            "    return sorted(set(normalized))\\n\", encoding='utf-8')\n"
            "(repo / 'test_items.py').write_text(\"import unittest\\n\\nfrom items import normalize_items\\n\\n\\n"
            "class ItemTests(unittest.TestCase):\\n"
            "    def test_normalizes_deduplicates_and_sorts(self):\\n"
            "        self.assertEqual(['a', 'b'], normalize_items([' B ', 'a', 'A', '']))\\n\\n\\n"
            "if __name__ == '__main__':\\n    unittest.main()\\n\", encoding='utf-8')\n"
            "print('python fixture implemented')\n",
        )
    else:
        write_text(
            code_script,
            "import os\nfrom pathlib import Path\n"
            "repo = Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
            "(repo / 'src' / 'format.mjs').write_text("
            "\"export function summarize(items) {\\n"
            "  return [...new Set(items.map((item) => String(item).trim()).filter(Boolean))].sort().join(', ');\\n"
            "}\\n\", encoding='utf-8')\n"
            "(repo / 'test' / 'format.test.mjs').write_text("
            "\"import test from 'node:test';\\n"
            "import assert from 'node:assert/strict';\\n"
            "import { summarize } from '../src/format.mjs';\\n\\n"
            "test('normalizes unique sorted labels', () => {\\n"
            "  assert.equal(summarize([' B ', 'A', 'A', '']), 'A, B');\\n"
            "});\\n\", encoding='utf-8')\n"
            "print('frontend fixture implemented')\n",
        )

    memory_script = scripts / "writeback.py"
    write_text(
        memory_script,
        "import os\nfrom pathlib import Path\n"
        "repo = Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
        "path = repo / 'delivery-notes' / 'WRITEBACK.md'\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        f"path.write_text('# Delivery writeback\\n\\n- fixture: {kind}\\n- verification: passed\\n', encoding='utf-8')\n"
        "print('project writeback completed')\n",
    )

    publish_script = scripts / "publish.py"
    write_text(
        publish_script,
        "import os\nimport subprocess\nfrom pathlib import Path\n"
        "repo = Path(os.environ['PIPELINE_AGENT_REPO_DIR'])\n"
        "def run(args):\n"
        "    proc = subprocess.run(args, cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace')\n"
        "    if proc.returncode:\n"
        "        raise SystemExit(proc.stdout + proc.stderr)\n"
        "    return proc.stdout.strip()\n"
        "run(['git', 'config', 'user.name', 'HardFlow Fixture'])\n"
        "run(['git', 'config', 'user.email', 'fixture@example.invalid'])\n"
        "run(['git', 'add', '-A'])\n"
        "if not run(['git', 'status', '--porcelain']):\n"
        "    raise SystemExit('publish workspace has no accepted changes')\n"
        "run(['git', 'commit', '-m', 'deliver generic fixture'])\n"
        "run(['git', 'push', 'origin', 'HEAD:main'])\n"
        "print('published_sha=' + run(['git', 'rev-parse', 'HEAD']))\n",
    )

    review_a, review_b = write_review_pair(scripts, kind)
    return {
        "context": pass_script,
        "code": code_script,
        "memory": memory_script,
        "publish": publish_script,
        "review_a": review_a,
        "review_b": review_b,
    }


def remote_file(remote: Path, path: str) -> str:
    return run_checked(["git", f"--git-dir={remote}", "show", f"refs/heads/main:{path}"]).stdout


def run_fixture(kind: str, root: Path) -> dict[str, Any]:
    module = load_pipeline_module()
    repo, remote, initial_sha = initialize_repository(root, kind)
    commands = write_fixture_commands(root, kind)
    python_command = lambda path: command_text([sys.executable, str(path)])

    if kind == "python":
        requirement = "Implement deterministic item normalization in this Python project, test it, review it, write back evidence, and publish it."
        verification_command = command_text([sys.executable, "-m", "unittest", "discover", "-v"])
        expected_agent = "backend-dev"
        expected_file = "items.py"
        expected_text = "sorted(set(normalized))"
    else:
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            raise RuntimeError("frontend fixture requires node and npm")
        requirement = "Implement a frontend label component helper, run project install, build and tests, review it, write back evidence, and publish it."
        verification_command = " && ".join(
            (
                command_text([npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"]),
                command_text([npm, "run", "build"]),
                command_text([npm, "test"]),
            )
        )
        expected_agent = "frontend-dev"
        expected_file = "src/format.mjs"
        expected_text = ".filter(Boolean)"

    state = module.run_pipeline(
        module.PipelineConfig(
            project_key=f"generic-{kind}-fixture",
            requirement=requirement,
            runtime_host="fixture-local",
            runtime_home=str(root / "runtime"),
            workspace_root=root / "pipeline-runs",
            project_memory_root=root / "project-memory",
            agent_workspace_root=root / "agent-workspaces",
            run_id=f"{kind}-live-e2e",
            dry_run=False,
            research_commands=(python_command(commands["context"]),),
            requirements_discussion_commands=(python_command(commands["context"]),),
            requirements_review_commands=(python_command(commands["review_a"]), python_command(commands["review_b"])),
            solution_review_commands=(python_command(commands["review_a"]), python_command(commands["review_b"])),
            code_agent=expected_agent,
            code_command=python_command(commands["code"]),
            verification_commands=(verification_command,),
            code_review_commands=(python_command(commands["review_a"]), python_command(commands["review_b"])),
            memory_write_command=python_command(commands["memory"]),
            git_publish_command=python_command(commands["publish"]),
            command_cwd=repo,
        )
    )

    code_report = json.loads(Path(state["artifacts"]["command_code_execution_1"]).read_text(encoding="utf-8"))
    verify_report = json.loads(Path(state["artifacts"]["command_verification_1"]).read_text(encoding="utf-8"))
    publish_report = json.loads(Path(state["artifacts"]["command_git_publish_1"]).read_text(encoding="utf-8"))
    plan = json.loads(Path(state["artifacts"]["delivery_plan"]).read_text(encoding="utf-8"))
    remote_sha = run_checked(["git", f"--git-dir={remote}", "rev-parse", "refs/heads/main"]).stdout.strip()
    commit_count = int(run_checked(["git", f"--git-dir={remote}", "rev-list", "--count", "refs/heads/main"]).stdout.strip())
    delivered = remote_file(remote, expected_file)
    writeback = remote_file(remote, "delivery-notes/WRITEBACK.md")

    checks = {
        "pipeline_completed": state.get("status") == "completed",
        "isolated_code_workspace": code_report.get("agent_workspace", {}).get("isolated") is True,
        "expected_code_agent": code_report.get("agent_id") == expected_agent,
        "expected_plan_owner": plan.get("owner") == expected_agent,
        "verification_passed": verify_report.get("ok") is True,
        "publish_passed": publish_report.get("ok") is True,
        "remote_advanced": remote_sha != initial_sha and commit_count == 2,
        "remote_contains_code": expected_text in delivered,
        "remote_contains_writeback": f"fixture: {kind}" in writeback,
    }
    if not all(checks.values()):
        raise RuntimeError(f"{kind} fixture acceptance failed: {json.dumps(checks, ensure_ascii=False)}")
    return {
        "kind": kind,
        "ok": True,
        "checks": checks,
        "initial_sha": initial_sha,
        "remote_sha": remote_sha,
        "state_file": str(root / "pipeline-runs" / f"{kind}-live-e2e" / "pipeline_state.json"),
        "verification_command": verification_command,
        "verification_stdout": verify_report.get("stdout", ""),
        "publish_stdout": publish_report.get("stdout", ""),
    }


def run_all(work_root: Path, kinds: tuple[str, ...] = ("python", "frontend")) -> dict[str, Any]:
    work_root.mkdir(parents=True, exist_ok=False)
    results = [run_fixture(kind, work_root / kind) for kind in kinds]
    report = {"ok": all(item["ok"] for item in results), "work_root": str(work_root), "results": results}
    write_text(work_root / "summary.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run disposable live pipeline fixtures")
    parser.add_argument("--kind", choices=["python", "frontend", "all"], default="all")
    parser.add_argument("--work-root", default="", help="new directory that will retain evidence")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kinds = ("python", "frontend") if args.kind == "all" else (args.kind,)
    if args.work_root:
        report = run_all(Path(args.work_root).expanduser().resolve(), kinds)
    else:
        with tempfile.TemporaryDirectory(prefix="hardflow-fixture-") as tmp:
            report = run_all(Path(tmp) / "evidence", kinds)
    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for result in report["results"]:
            print(f"{result['kind']}: ok={result['ok']} remote_sha={result['remote_sha']}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

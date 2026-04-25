#!/usr/bin/env python3
"""Live evidence bridge for the SmartMultiPlatformArbitrage delivery pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


PROJECT_DIR = Path("/home/arbops/projects/SmartMultiPlatformArbitrage")
RUNTIME_HOME = Path("/home/arbops/.hermes")
HERMES_BIN = Path("/home/arbops/.local/bin/hermes")
VENV_BIN = Path("/home/arbops/.venvs/smart-arbitrage/bin")
API_SUBDIR = "\u667a\u80fd\u591a\u5e73\u53f0\u5957\u5229"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STATUS_RE = re.compile(r"(?im)^\s*LIVE_BRIDGE_STATUS\s*:\s*(pass|fail)\s*$")
FINAL_VERDICT_RE = re.compile(r"(?im)^\s*Final verdict\s*:\s*pass\s*$")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return default


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def profile_home(runtime_home: Path, profile: str) -> Path:
    profile = (profile or "").strip()
    if not profile:
        return runtime_home
    candidate = runtime_home / "profiles" / profile
    return candidate if candidate.exists() else runtime_home


def stage_output_file(stage: str) -> Path | None:
    key_by_stage = {
        "external_research": "PIPELINE_RESEARCH_REPORT_FILE",
        "requirements_discussion": "PIPELINE_REQUIREMENTS_DISCUSSION_FILE",
        "code_execution": "PIPELINE_PATCH_SUMMARY_FILE",
        "verification": "PIPELINE_VERIFICATION_REPORT_FILE",
        "code_review": "PIPELINE_CODE_REVIEW_FILE",
        "deployment": "PIPELINE_DEPLOYMENT_REPORT_FILE",
        "memory_writeback": "PIPELINE_WRITEBACK_REPORT_FILE",
    }
    value = os.environ.get(key_by_stage.get(stage, ""), "").strip()
    return Path(value).expanduser() if value else None


def requirement_text() -> str:
    path = env_path("PIPELINE_REQUIREMENT_FILE", Path(""))
    if path and str(path) != "." and path.exists():
        return read_text(path)
    return os.environ.get("PIPELINE_REQUIREMENT", "").strip()


def run_command(
    command: str | list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        shell=shell,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def command_block(title: str, command: str | list[str], proc: subprocess.CompletedProcess[str]) -> str:
    command_text = command if isinstance(command, str) else " ".join(shlex.quote(str(part)) for part in command)
    return "\n".join(
        [
            f"## {title}",
            f"- command: `{command_text}`",
            f"- returncode: {proc.returncode}",
            "",
            "### stdout",
            "```text",
            (proc.stdout or "").strip(),
            "```",
            "",
            "### stderr",
            "```text",
            (proc.stderr or "").strip(),
            "```",
        ]
    )


def bridge_env(args: argparse.Namespace, profile_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(args.home)
    env["HERMES_HOME"] = str(profile_dir)
    env["HERMES_ACCEPT_HOOKS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    path_parts = [str(args.hermes_bin.parent), str(VENV_BIN), "/usr/local/bin", "/usr/bin", "/bin"]
    existing_path = env.get("PATH", "")
    env["PATH"] = ":".join([part for part in path_parts if part] + ([existing_path] if existing_path else []))
    return env


def stage_prompt(stage: str, args: argparse.Namespace, requirement: str) -> str:
    run_dir = os.environ.get("PIPELINE_RUN_DIR", "")
    memory_dir = os.environ.get("PIPELINE_PROJECT_MEMORY_DIR", "")
    agent_id = os.environ.get("PIPELINE_AGENT_ID", "").strip()
    agent_workspace = os.environ.get("PIPELINE_AGENT_WORKSPACE", "").strip()
    agent_repo_dir = os.environ.get("PIPELINE_AGENT_REPO_DIR", "").strip()
    output_file = stage_output_file(stage)
    common = f"""
You are running one non-interactive stage of the SmartMultiPlatformArbitrage delivery pipeline.

Project directory: {args.project_dir}
Pipeline run dir: {run_dir}
Project memory dir: {memory_dir}
Source profile: {args.profile}
Stage: {stage}
Agent id: {agent_id or "unspecified"}
Agent workspace: {agent_workspace or "unspecified"}
Agent repo dir: {agent_repo_dir or str(args.project_dir)}
Stage output file hint: {output_file or ""}

Requirement:
{requirement}

Safety contract:
- Do not print, move, or modify secrets, tokens, cookies, credentials, auth state files, or private API keys.
- Do not place exchange orders, transfer funds, start trading strategies, or enable live trading.
- Keep changes scoped to the requirement and the existing repository patterns.
- Record evidence with concrete files, commands, and outcomes.
- End the final answer with these exact lines:
LIVE_BRIDGE_STAGE: {stage}
LIVE_BRIDGE_STATUS: pass
"""
    if stage == "external_research":
        specific = """
Act as web-agent. Check whether current external docs or online references are needed before implementation.
Use available browser/search tools when the requirement depends on external facts. If no external lookup is needed, explain why.
Return concise research evidence and implementation constraints.
"""
    elif stage == "requirements_discussion":
        specific = """
Act as two agents: project-agent and reviewer.
Run at least two short rounds of discussion:
1. project-agent clarifies the user goal, affected modules, constraints, and acceptance criteria.
2. reviewer challenges ambiguity, hidden risks, missing tests, deployment impact, and safety boundaries.
3. project-agent produces the final refined requirement document.
"""
    elif stage == "code_execution":
        specific = """
Act as backend-dev/frontend-dev executor. Read project memory/docs/todo/done and the relevant code before editing.
Implement the smallest safe change that satisfies the refined requirement.
Run the most relevant local checks you can run in this environment.
Return a patch summary with changed files, commands run, and remaining risk.
"""
    elif stage == "code_review":
        specific = """
Act as reviewer. Review the current diff and the pipeline artifacts for bugs, regressions, missing tests, unsafe behavior, and doc drift.
If the change is acceptable, include exactly this line:
Final verdict: pass
If it is not acceptable, include:
Final verdict: requires_revision
"""
    else:
        specific = "Return concise stage evidence."
    return common.strip() + "\n\n" + specific.strip()


def run_echo_stage(stage: str) -> int:
    if stage == "code_review":
        print("# Smart Arb Live Bridge Echo Review")
        print("Final verdict: pass")
    elif stage == "deployment":
        print("# Smart Arb Live Bridge Echo Deployment")
        print("- Internal API restart skipped in echo mode.")
    else:
        print(f"# Smart Arb Live Bridge Echo {stage}")
        print("- Deterministic echo evidence generated for smoke testing.")
    print(f"LIVE_BRIDGE_STAGE: {stage}")
    print("LIVE_BRIDGE_STATUS: pass")
    return 0


def run_hermes_stage(stage: str, args: argparse.Namespace) -> int:
    requirement = requirement_text()
    prompt = stage_prompt(stage, args, requirement)
    profile_dir = profile_home(args.runtime_home, args.profile)
    command = [
        str(args.hermes_bin),
        "chat",
        "--ignore-user-config",
        "--provider",
        args.provider,
        "-m",
        args.model,
        "-q",
        prompt,
        "-Q",
        "--max-turns",
        str(args.max_turns),
        "--source",
        f"smart-arb-live-bridge:{stage}",
        "--accept-hooks",
        "--checkpoints",
    ]
    if args.allow_yolo:
        command.append("--yolo")

    proc = run_command(command, cwd=args.project_dir, env=bridge_env(args, profile_dir))
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print("\n# stderr")
        print(proc.stderr.rstrip())

    plain = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    status = STATUS_RE.search(plain)
    if proc.returncode != 0:
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return proc.returncode or 1
    if not status or status.group(1).lower() != "pass":
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return 2
    if stage == "code_review" and not FINAL_VERDICT_RE.search(plain):
        print("Final verdict: requires_revision")
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return 3
    return 0


def verification_commands(args: argparse.Namespace) -> list[str]:
    commands = ["git diff --check"]
    test_command = os.environ.get("SMART_ARB_LIVE_BRIDGE_TEST_COMMAND", "").strip()
    if test_command:
        commands.append(test_command)
    elif not args.skip_tests and (args.project_dir / "tests").is_dir():
        python_bin = args.python_bin if args.python_bin.exists() else Path(sys.executable)
        commands.append(f"{shlex.quote(str(python_bin))} -m unittest discover -s tests -p 'test_*.py'")
    return commands


def run_verification(args: argparse.Namespace) -> int:
    sections: list[str] = ["# Smart Arb Live Verification"]
    ok = True
    for index, command in enumerate(verification_commands(args), start=1):
        proc = run_command(command, cwd=args.project_dir, shell=True)
        sections.append(command_block(f"Verification command {index}", command, proc))
        if proc.returncode != 0:
            ok = False
    sections.append("LIVE_BRIDGE_STAGE: verification")
    sections.append(f"LIVE_BRIDGE_STATUS: {'pass' if ok else 'fail'}")
    print("\n\n".join(sections))
    return 0 if ok else 1


def run_tmux(args: argparse.Namespace, command: list[str]) -> subprocess.CompletedProcess[str]:
    return run_command(command, cwd=args.project_dir)


def run_deployment(args: argparse.Namespace) -> int:
    if not args.allow_internal_api_restart:
        print("# Smart Arb Live Deployment")
        print("- Internal API restart was not allowed by bridge args.")
        print("LIVE_BRIDGE_STAGE: deployment")
        print("LIVE_BRIDGE_STATUS: fail")
        return 2

    api_cwd = args.api_cwd
    uvicorn_bin = args.uvicorn_bin
    if not api_cwd.exists():
        print(f"API cwd not found: {api_cwd}")
        print("LIVE_BRIDGE_STAGE: deployment")
        print("LIVE_BRIDGE_STATUS: fail")
        return 3
    if not uvicorn_bin.exists():
        print(f"uvicorn not found: {uvicorn_bin}")
        print("LIVE_BRIDGE_STAGE: deployment")
        print("LIVE_BRIDGE_STATUS: fail")
        return 3

    sections = ["# Smart Arb Live Deployment"]
    has_session = ["tmux", "has-session", "-t", args.api_session]
    proc = run_tmux(args, has_session)
    sections.append(command_block("Deployment command 1", has_session, proc))
    if proc.returncode == 0:
        kill_session = ["tmux", "kill-session", "-t", args.api_session]
        proc = run_tmux(args, kill_session)
        sections.append(command_block("Deployment command 2", kill_session, proc))
        if proc.returncode != 0:
            print("\n\n".join(sections))
            print("LIVE_BRIDGE_STAGE: deployment")
            print("LIVE_BRIDGE_STATUS: fail")
            return 4

    start_command = f"{shlex.quote(str(uvicorn_bin))} api.main:app --host 127.0.0.1 --port 18080"
    new_session = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        args.api_session,
        "-c",
        str(api_cwd),
        start_command,
    ]
    proc = run_tmux(args, new_session)
    sections.append(command_block("Deployment command 3", new_session, proc))
    if proc.returncode != 0:
        print("\n\n".join(sections))
        print("LIVE_BRIDGE_STAGE: deployment")
        print("LIVE_BRIDGE_STATUS: fail")
        return 4

    smoke_commands = [
        "curl -fsS http://127.0.0.1:18080/health",
        "curl -fsS http://127.0.0.1:18080/api/strategy/status",
    ]
    deadline = time.monotonic() + max(args.deploy_wait_seconds, 0)
    smoke_results: list[tuple[int, str, subprocess.CompletedProcess[str]]] = []
    while True:
        smoke_results = []
        ok = True
        for index, command in enumerate(smoke_commands, start=1):
            proc = run_command(command, cwd=args.project_dir, shell=True)
            smoke_results.append((index, command, proc))
            if proc.returncode != 0:
                ok = False
        if ok or time.monotonic() >= deadline:
            break
        time.sleep(1)

    for index, command, proc in smoke_results:
        sections.append(command_block(f"Deployment smoke {index}", command, proc))
    sections.append("LIVE_BRIDGE_STAGE: deployment")
    sections.append(f"LIVE_BRIDGE_STATUS: {'pass' if ok else 'fail'}")
    print("\n\n".join(sections))
    return 0 if ok else 5


def run_memory_writeback(args: argparse.Namespace) -> int:
    writer = Path(__file__).with_name("project_memory_writer.py")
    if not writer.exists():
        print(f"project_memory_writer.py not found next to bridge: {writer}")
        print("LIVE_BRIDGE_STAGE: memory_writeback")
        print("LIVE_BRIDGE_STATUS: fail")
        return 2

    project_key = os.environ.get("PIPELINE_PROJECT_KEY", "").strip() or "smart-multi-platform-arbitrage"
    memory_dir = env_path("PIPELINE_PROJECT_MEMORY_DIR", args.project_dir / "memory" / project_key)
    data_dir = memory_dir.parent
    content_file = env_path("PIPELINE_WRITEBACK_REPORT_FILE", Path(""))
    if not content_file.exists():
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write("# Pipeline Writeback\n\nNo writeback report file was present.\n")
            content_file = Path(handle.name)

    command = [
        str(args.python_bin if args.python_bin.exists() else Path(sys.executable)),
        str(writer),
        "--data-dir",
        str(data_dir),
        "--project-key",
        project_key,
        "--artifact-type",
        "changelog",
        "--content-file",
        str(content_file),
        "--source",
        "smart-arb-live-bridge",
    ]
    proc = run_command(command, cwd=args.project_dir)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print("\n# stderr")
        print(proc.stderr.rstrip())
    print("LIVE_BRIDGE_STAGE: memory_writeback")
    print(f"LIVE_BRIDGE_STATUS: {'pass' if proc.returncode == 0 else 'fail'}")
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart arbitrage live pipeline evidence bridge")
    parser.add_argument("--stage", required=True, choices=[
        "external_research",
        "requirements_discussion",
        "code_execution",
        "verification",
        "code_review",
        "deployment",
        "memory_writeback",
    ])
    parser.add_argument("--agent-mode", choices=["hermes", "echo"], default=os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MODE", "hermes"))
    parser.add_argument("--profile", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROFILE", "arbitrageagent"))
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=env_path("PIPELINE_AGENT_REPO_DIR", env_path("SMART_ARB_PROJECT_DIR", PROJECT_DIR)),
    )
    parser.add_argument("--runtime-home", type=Path, default=env_path("SMART_ARB_HERMES_RUNTIME_HOME", RUNTIME_HOME))
    parser.add_argument("--home", type=Path, default=env_path("SMART_ARB_HOME", Path("/home/arbops")))
    parser.add_argument("--hermes-bin", type=Path, default=env_path("SMART_ARB_HERMES_BIN", HERMES_BIN))
    parser.add_argument("--provider", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROVIDER", "openai-codex"))
    parser.add_argument("--model", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_MODEL", "gpt-5.5"))
    parser.add_argument("--max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_MAX_TURNS", "24")))
    parser.add_argument("--allow-yolo", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--python-bin", type=Path, default=env_path("SMART_ARB_PYTHON_BIN", VENV_BIN / "python"))
    parser.add_argument("--allow-internal-api-restart", action="store_true")
    parser.add_argument("--api-session", default=os.environ.get("SMART_ARB_API_TMUX_SESSION", "smart-arb-api"))
    parser.add_argument("--api-cwd", type=Path, default=env_path("SMART_ARB_API_CWD", PROJECT_DIR / API_SUBDIR))
    parser.add_argument("--uvicorn-bin", type=Path, default=env_path("SMART_ARB_UVICORN_BIN", VENV_BIN / "uvicorn"))
    parser.add_argument("--deploy-wait-seconds", type=int, default=int(os.environ.get("SMART_ARB_DEPLOY_WAIT_SECONDS", "30")))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.project_dir = args.project_dir.expanduser().resolve()
    args.runtime_home = args.runtime_home.expanduser().resolve()
    args.home = args.home.expanduser().resolve()
    args.hermes_bin = args.hermes_bin.expanduser()
    args.python_bin = args.python_bin.expanduser()
    args.api_cwd = args.api_cwd.expanduser()
    args.uvicorn_bin = args.uvicorn_bin.expanduser()

    if args.stage == "verification":
        if args.agent_mode == "echo":
            return run_echo_stage(args.stage)
        return run_verification(args)
    if args.stage == "deployment":
        if args.agent_mode == "echo":
            return run_echo_stage(args.stage)
        return run_deployment(args)
    if args.stage == "memory_writeback":
        return run_memory_writeback(args)
    if args.agent_mode == "echo":
        return run_echo_stage(args.stage)
    return run_hermes_stage(args.stage, args)


if __name__ == "__main__":
    raise SystemExit(main())

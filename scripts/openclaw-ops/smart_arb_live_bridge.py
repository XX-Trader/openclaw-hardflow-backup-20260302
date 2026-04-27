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
FINAL_VERDICT_RE = re.compile(r"(?im)^\s*Final verdict\s*:\s*([a-z_]+)\s*$")
SESSION_ID_RE = re.compile(r"(?im)^\s*session_id\s*:\s*([A-Za-z0-9_-]+)\s*$")
SENSITIVE_VALUE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9_-]{47,}(?![A-Za-z0-9])")
KNOWN_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9_])("
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9][A-Za-z0-9_-]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"hf_[A-Za-z0-9]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"ya29\.[0-9A-Za-z_-]{20,}|"
    r"AKIA[0-9A-Z]{16}"
    r")(?![A-Za-z0-9_])"
)
SENSITIVE_LINE_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)\b\s*[:=]\s*([^\r\n]+)"
)
ARTIFACT_PATH_ENV_NAMES = {
    "PIPELINE_RESEARCH_REPORT_FILE",
    "PIPELINE_REQUIREMENTS_FILE",
    "PIPELINE_REQUIREMENTS_DISCUSSION_FILE",
    "PIPELINE_REQUIREMENTS_REVIEW_FILE",
    "PIPELINE_SOLUTION_FILE",
    "PIPELINE_SOLUTION_REVIEW_FILE",
    "PIPELINE_PATCH_SUMMARY_FILE",
    "PIPELINE_VERIFICATION_REPORT_FILE",
    "PIPELINE_CODE_REVIEW_FILE",
    "PIPELINE_DEPLOYMENT_REPORT_FILE",
    "PIPELINE_WRITEBACK_REPORT_FILE",
    "PIPELINE_GIT_PUBLISH_REPORT_FILE",
}
NON_CODE_HERMES_STAGES = {
    "external_research",
    "requirements_discussion",
    "requirements_review",
    "solution_review",
    "code_review",
}
EXPECTED_REVIEW_VERDICTS = {
    "requirements_review": "ready_for_solution",
    "solution_review": "ready_for_implement",
    "code_review": "pass",
}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def redact_text(text: str) -> str:
    text = SENSITIVE_LINE_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", text or "")
    text = KNOWN_SECRET_RE.sub("[REDACTED]", text)
    return SENSITIVE_VALUE_RE.sub("[REDACTED]", text)


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return default


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def profile_home(runtime_home: Path, profile: str) -> Path:
    profile = (profile or "").strip()
    if not profile:
        return runtime_home
    candidate = runtime_home / "profiles" / profile
    return candidate if candidate.exists() else runtime_home


def recover_hermes_session_output(profile_dir: Path, command_text: str) -> str:
    match = SESSION_ID_RE.search(command_text or "")
    if not match:
        return ""
    session_id = match.group(1).strip()
    if not session_id:
        return ""
    session_file = profile_dir / "sessions" / f"session_{session_id}.json"
    payload = read_json(session_file)
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return redact_text(content)
    return ""


def recovered_stage_pass(stage: str, text: str) -> bool:
    if not text.strip():
        return False
    if STATUS_RE.search(text):
        return True
    if stage == "external_research" and "NO_EXTERNAL_LOOKUP_NEEDED" in text:
        return True
    return False


def requirement_text() -> str:
    path = env_path("PIPELINE_REQUIREMENT_FILE", Path(""))
    if path and str(path) != "." and path.exists():
        return read_text(path)
    return os.environ.get("PIPELINE_REQUIREMENT", "").strip()


def repair_context_text() -> str:
    for name in ("PIPELINE_REPAIR_CONTEXT_FILE", "SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE"):
        path = env_path(name, Path(""))
        if path and str(path) != "." and path.exists():
            return read_text(path)
    for name in ("PIPELINE_REPAIR_CONTEXT", "SMART_ARB_ENTRY_REPAIR_CONTEXT"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def stage_context_files(stage: str) -> tuple[str, ...]:
    if stage == "requirements_discussion":
        return ("research_report.md", "project_memory_context.md")
    if stage == "requirements_review":
        return ("research_report.md", "project_memory_context.md", "requirements.md", "requirements_discussion.md")
    if stage == "solution_review":
        return ("requirements.md", "requirements_review.md", "solution.md")
    if stage == "code_execution":
        return (
            "research_report.md",
            "requirements.md",
            "requirements_discussion.md",
            "requirements_review.md",
            "solution.md",
            "solution_review.md",
        )
    if stage in {"verification", "code_review", "deployment", "memory_writeback", "git_publish"}:
        return (
            "research_report.md",
            "requirements_discussion.md",
            "solution.md",
            "patch_summary.md",
            "verification_report.md",
            "code_review.md",
            "writeback_report.md",
        )
    return ()


def pipeline_context_text(stage: str, limit_per_file: int = 2200) -> str:
    run_dir_raw = os.environ.get("PIPELINE_RUN_DIR", "").strip()
    if not run_dir_raw:
        return "not_applicable"
    run_dir = Path(run_dir_raw).expanduser()
    sections: list[str] = []
    for name in stage_context_files(stage):
        path = run_dir / name
        if not path.exists() or not path.is_file():
            continue
        text = redact_text(read_text(path))
        if len(text) > limit_per_file:
            text = text[:limit_per_file].rstrip() + "\n...[truncated]"
        sections.append(f"## {name}\n{text.strip()}")
    return "\n\n".join(sections) if sections else "not_applicable"


def final_verdict(text: str) -> str | None:
    match = FINAL_VERDICT_RE.search(text or "")
    return match.group(1).strip().lower() if match else None


def run_command(
    command: str | list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    shell: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
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
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        timeout_note = f"Command timed out after {timeout} seconds."
        stderr = (stderr.rstrip() + "\n" + timeout_note).strip() if stderr else timeout_note
        return subprocess.CompletedProcess(command, 124, stdout, stderr)


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


def bridge_env(args: argparse.Namespace, profile_dir: Path, stage: str = "") -> dict[str, str]:
    env = dict(os.environ)
    if stage in NON_CODE_HERMES_STAGES:
        for name in ARTIFACT_PATH_ENV_NAMES:
            env.pop(name, None)
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
    repair_context = repair_context_text()
    prior_stage_context = pipeline_context_text(stage)
    agent_id = os.environ.get("PIPELINE_AGENT_ID", "").strip()
    agent_workspace = os.environ.get("PIPELINE_AGENT_WORKSPACE", "").strip()
    agent_repo_dir = os.environ.get("PIPELINE_AGENT_REPO_DIR", "").strip()
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

Requirement:
{requirement}

Repair context from previous blocked attempt:
{repair_context or "not_applicable"}

Prior accepted stage context:
{prior_stage_context}

Safety contract:
- Do not print, move, or modify secrets, tokens, cookies, credentials, auth state files, or private API keys.
- Do not place exchange orders, transfer funds, start trading strategies, or enable live trading.
- Keep changes scoped to the requirement and the existing repository patterns.
- Record evidence with concrete files, commands, and outcomes.
- Do not edit pipeline artifact files such as research_report.md, requirements_discussion.md, patch_summary.md, verification_report.md, code_review.md, or deployment_report.md.
- For non-code stages, do not edit any files. Return the stage evidence in your final answer/stdout only; the runner will persist it.
- End the final answer with these exact lines:
LIVE_BRIDGE_STAGE: {stage}
LIVE_BRIDGE_STATUS: pass
"""
    if stage == "external_research":
        specific = """
Act as web-agent. Check whether current external docs or online references are needed before implementation.
Use available browser/search tools when the requirement depends on external facts. If no external lookup is needed, explicitly say NO_EXTERNAL_LOOKUP_NEEDED, explain why, and give local evidence instead.
Return concise research evidence and implementation constraints.
Do not modify files. Do not write the stage output artifact yourself.
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
        role = "frontend-dev" if agent_id == "frontend-dev" else "backend-dev"
        focus = (
            "front-end UI, page, interaction, state, and integration changes"
            if role == "frontend-dev"
            else "backend, script, service, API, and strategy-runtime changes"
        )
        specific = """
Act as {role} executor for {focus}. Read project memory/docs/todo/done and the relevant code before editing.
Treat Prior accepted stage context and Repair context as hard constraints. Do not implement later-phase strategy work if the current requirement or research context says to stay on P0 memory/environment work.
Implement the smallest safe change that satisfies the refined requirement.
Run the most relevant local checks you can run in this environment.
Return a patch summary with changed files, commands run, and remaining risk.
""".format(role=role, focus=focus)
    elif stage in {"requirements_review", "solution_review", "code_review"}:
        role = str(args.reviewer_role or "").strip() or "reviewer-a"
        if stage == "requirements_review":
            expected = "ready_for_solution"
            focus = "requirements clarity, scope, acceptance criteria, risk routing, and human confirmation boundaries"
        elif stage == "solution_review":
            expected = "ready_for_implement"
            focus = "implementation plan, reuse of existing runtime skills, dependency risk, and deployment boundaries"
        else:
            expected = "pass"
            focus = "bugs, regressions, missing tests, unsafe behavior, and doc or memory drift"
        specific = """
Act as {role}. Review the pipeline artifacts for {focus}.
You are one side of a dual-AI review gate. Produce your own independent verdict and evidence.
Include exactly this reviewer role line:
Reviewer role: {role}
If the material is acceptable, include exactly this line:
Final verdict: {expected}
If it is not acceptable, include:
Final verdict: requires_revision
""".format(role=role, focus=focus, expected=expected)
    else:
        specific = "Return concise stage evidence."
    return common.strip() + "\n\n" + specific.strip()


def run_echo_stage(stage: str, reviewer_role: str = "") -> int:
    if stage == "requirements_review":
        print("# Smart Arb Live Bridge Echo Requirements Review")
        print("Final verdict: ready_for_solution")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
    elif stage == "solution_review":
        print("# Smart Arb Live Bridge Echo Solution Review")
        print("Final verdict: ready_for_implement")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
    elif stage == "code_review":
        print("# Smart Arb Live Bridge Echo Review")
        print("Final verdict: pass")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
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

    proc = run_command(command, cwd=args.project_dir, env=bridge_env(args, profile_dir, stage))
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print("\n# stderr")
        print(proc.stderr.rstrip())

    plain = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    recovered = recover_hermes_session_output(profile_dir, plain)
    if recovered and recovered not in plain:
        print("\n# recovered_session_output")
        print(recovered.rstrip())
        plain = f"{plain}\n{recovered}"
    if recovered_stage_pass(stage, recovered) and not STATUS_RE.search(plain):
        plain = f"{plain}\nLIVE_BRIDGE_STAGE: {stage}\nLIVE_BRIDGE_STATUS: pass"
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: pass")
    status = STATUS_RE.search(plain)
    if proc.returncode != 0:
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return proc.returncode or 1
    if not status or status.group(1).lower() != "pass":
        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return 2
    expected_verdict = EXPECTED_REVIEW_VERDICTS.get(stage)
    if expected_verdict and final_verdict(plain) != expected_verdict:
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
    elif not args.skip_tests:
        python_bin = args.python_bin if args.python_bin.exists() else Path(sys.executable)
        targets = [args.project_dir / name for name in ("scripts", "strategy_runtime") if (args.project_dir / name).exists()]
        if targets:
            quoted_targets = " ".join(shlex.quote(str(target.relative_to(args.project_dir))) for target in targets)
            commands.append(f"{shlex.quote(str(python_bin))} -m compileall -q {quoted_targets}")
    return commands


def int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def run_verification(args: argparse.Namespace) -> int:
    sections: list[str] = ["# Smart Arb Live Verification"]
    ok = True
    timeout = int(args.verification_command_timeout_seconds)
    sections.append(f"- Verification command timeout seconds: {timeout}")
    for index, command in enumerate(verification_commands(args), start=1):
        proc = run_command(command, cwd=args.project_dir, shell=True, timeout=timeout)
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


def build_chinese_commit_message() -> str:
    requirement = " ".join(redact_text(requirement_text()).split())
    if len(requirement) > 160:
        requirement = requirement[:157].rstrip() + "..."
    if not requirement:
        requirement = "未提供需求摘要"
    run_dir = redact_text(os.environ.get("PIPELINE_RUN_DIR", "").strip()) or "未记录"
    return "\n".join(
        [
            "交付: 提交已审核的项目变更",
            "",
            "变更说明:",
            "- 本次提交来自项目交付流水线，已通过验证和代码审查后进入发布阶段。",
            f"- 需求摘要: {requirement}",
            "",
            "验证:",
            "- 已通过验证阶段记录的验证命令。",
            "- 已通过代码审查阶段的独立审核。",
            "",
            "审查:",
            "- 代码审查员: 通过",
            "",
            "备注:",
            "- 提交说明与发布备注使用中文。",
            "- 禁止 force push；如远端冲突或凭证问题，停止并回流人工处理。",
            f"- 证据目录: {run_dir}",
            "",
        ]
    )


def staged_diff_has_secret(diff: str) -> bool:
    if KNOWN_SECRET_RE.search(diff or ""):
        return True
    if SENSITIVE_LINE_RE.search(diff or ""):
        return True
    return False


def run_git_publish(args: argparse.Namespace) -> int:
    sections = ["# Smart Arb Git Publish"]
    remote = str(args.git_remote or "origin").strip() or "origin"
    branch = str(args.git_branch or "main").strip() or "main"
    sections.append(f"- Remote: {remote}")
    sections.append(f"- Branch: {branch}")
    sections.append("- Commit language: Chinese")
    sections.append("- Force push: disabled")

    inside = run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=args.project_dir)
    sections.append(command_block("Git check 1", ["git", "rev-parse", "--is-inside-work-tree"], inside))
    if inside.returncode != 0 or "true" not in (inside.stdout or "").lower():
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 2

    diff_check = run_command(["git", "diff", "--check"], cwd=args.project_dir)
    sections.append(command_block("Git check 2", ["git", "diff", "--check"], diff_check))
    if diff_check.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 3

    status_before = run_command(["git", "status", "--porcelain"], cwd=args.project_dir)
    sections.append(command_block("Git status before add", ["git", "status", "--porcelain"], status_before))
    if status_before.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 4
    if not (status_before.stdout or "").strip():
        sections.append("- No repository changes to publish.")
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: pass")
        print("\n\n".join(sections))
        return 0

    add_proc = run_command(["git", "add", "-A"], cwd=args.project_dir)
    sections.append(command_block("Git add", ["git", "add", "-A"], add_proc))
    if add_proc.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 5

    staged_check = run_command(["git", "diff", "--cached", "--check"], cwd=args.project_dir)
    sections.append(command_block("Git staged check", ["git", "diff", "--cached", "--check"], staged_check))
    if staged_check.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 6

    staged_stat = run_command(["git", "diff", "--cached", "--stat"], cwd=args.project_dir)
    sections.append(command_block("Git staged diff summary", ["git", "diff", "--cached", "--stat"], staged_stat))
    if staged_stat.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 7
    staged_diff = run_command(["git", "diff", "--cached", "--no-ext-diff"], cwd=args.project_dir)
    if staged_diff.returncode != 0:
        redacted = subprocess.CompletedProcess(
            staged_diff.args,
            staged_diff.returncode,
            "",
            staged_diff.stderr,
        )
        sections.append(command_block("Git staged diff scan", ["git", "diff", "--cached", "--no-ext-diff"], redacted))
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 8
    if not (staged_diff.stdout or "").strip():
        sections.append("- No staged changes after git add.")
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: pass")
        print("\n\n".join(sections))
        return 0
    if staged_diff_has_secret(staged_diff.stdout or ""):
        sections.append("- Secret-like content detected in staged diff; publish is blocked.")
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 9

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".commit-message", delete=False) as handle:
        handle.write(build_chinese_commit_message())
        message_file = Path(handle.name)
    try:
        commit_proc = run_command(["git", "commit", "-F", str(message_file)], cwd=args.project_dir)
    finally:
        try:
            message_file.unlink()
        except OSError:
            pass
    sections.append(command_block("Git commit", ["git", "commit", "-F", "<chinese-message-file>"], commit_proc))
    if commit_proc.returncode != 0:
        sections.append("LIVE_BRIDGE_STAGE: git_publish")
        sections.append("LIVE_BRIDGE_STATUS: fail")
        print("\n\n".join(sections))
        return 10

    push_command = ["git", "push", remote, f"HEAD:{branch}"]
    push_proc = run_command(push_command, cwd=args.project_dir, timeout=max(1, int(args.git_push_timeout_seconds)))
    sections.append(command_block("Git push", push_command, push_proc))
    sections.append("LIVE_BRIDGE_STAGE: git_publish")
    sections.append(f"LIVE_BRIDGE_STATUS: {'pass' if push_proc.returncode == 0 else 'fail'}")
    print("\n\n".join(sections))
    return 0 if push_proc.returncode == 0 else 11


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart arbitrage live pipeline evidence bridge")
    parser.add_argument("--stage", required=True, choices=[
        "external_research",
        "requirements_discussion",
        "requirements_review",
        "solution_review",
        "code_execution",
        "verification",
        "code_review",
        "deployment",
        "memory_writeback",
        "git_publish",
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
    parser.add_argument("--reviewer-role", choices=["reviewer-a", "reviewer-b"], default=os.environ.get("PIPELINE_REVIEWER_ROLE", "reviewer-a"))
    parser.add_argument("--max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_MAX_TURNS", "24")))
    parser.add_argument("--allow-yolo", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--python-bin", type=Path, default=env_path("SMART_ARB_PYTHON_BIN", VENV_BIN / "python"))
    parser.add_argument(
        "--verification-command-timeout-seconds",
        type=int,
        default=int_env("SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS", 300),
    )
    parser.add_argument("--allow-internal-api-restart", action="store_true")
    parser.add_argument("--api-session", default=os.environ.get("SMART_ARB_API_TMUX_SESSION", "smart-arb-api"))
    parser.add_argument("--api-cwd", type=Path, default=env_path("SMART_ARB_API_CWD", PROJECT_DIR / API_SUBDIR))
    parser.add_argument("--uvicorn-bin", type=Path, default=env_path("SMART_ARB_UVICORN_BIN", VENV_BIN / "uvicorn"))
    parser.add_argument("--deploy-wait-seconds", type=int, default=int(os.environ.get("SMART_ARB_DEPLOY_WAIT_SECONDS", "30")))
    parser.add_argument("--git-remote", default=os.environ.get("SMART_ARB_GIT_REMOTE", "origin"))
    parser.add_argument("--git-branch", default=os.environ.get("SMART_ARB_GIT_BRANCH", "main"))
    parser.add_argument("--git-push-timeout-seconds", type=int, default=int_env("SMART_ARB_GIT_PUSH_TIMEOUT_SECONDS", 120))
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
            return run_echo_stage(args.stage, args.reviewer_role)
        return run_verification(args)
    if args.stage == "deployment":
        if args.agent_mode == "echo":
            return run_echo_stage(args.stage, args.reviewer_role)
        return run_deployment(args)
    if args.stage == "memory_writeback":
        return run_memory_writeback(args)
    if args.stage == "git_publish":
        if args.agent_mode == "echo":
            return run_echo_stage(args.stage, args.reviewer_role)
        return run_git_publish(args)
    if args.agent_mode == "echo":
        return run_echo_stage(args.stage, args.reviewer_role)
    return run_hermes_stage(args.stage, args)


if __name__ == "__main__":
    raise SystemExit(main())

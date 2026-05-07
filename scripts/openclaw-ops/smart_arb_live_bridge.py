#!/usr/bin/env python3
"""Live evidence bridge for the SmartMultiPlatformArbitrage delivery pipeline."""

from __future__ import annotations

import argparse
import copy
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
DEFAULT_REVIEWER_FALLBACK_MODELS = "zai/glm-5.1,zhipu/glm-5.1,openai-codex/gpt-5.5"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STATUS_RE = re.compile(r"(?im)^\s*LIVE_BRIDGE_STATUS\s*:\s*(pass|fail)\s*$")
FINAL_VERDICT_RE = re.compile(r"(?im)^\s*Final verdict\s*:\s*([a-z_]+)\s*$")
SESSION_ID_RE = re.compile(r"(?im)^\s*session_id\s*:\s*([A-Za-z0-9_-]+)\s*$")
SENSITIVE_VALUE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9_-]{47,}(?![A-Za-z0-9])")
QUOTED_VALUE_RE = re.compile(r"['\"]([A-Za-z0-9][A-Za-z0-9_-]{47,})['\"]")
STRING_LITERAL_RE = re.compile(r"(?P<quote>['\"`])(?P<value>.*?)(?P=quote)")
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
PRIVATE_KEY_MARKER_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|-----END [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
PRIVATE_KEY_PATH_RE = re.compile(r"(?i)(^|[\\/])(?:id_(?:rsa|dsa|ecdsa|ed25519)|[^\\/]*(?:private[_-]?key|\.pem|\.key))$")
PRIVATE_KEY_MATERIAL_RE = re.compile(r"^[A-Za-z0-9+/=]{32,}$")
SENSITIVE_LINE_RE = re.compile(
    r"(?im)(?<![A-Za-z0-9_])['\"`]?(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"[A-Z0-9_]*(?:API[_-]?KEY|SECRET|PASSWORD|PASS|TOKEN|COOKIE|OAUTH|PRIVATE[_-]?KEY|SESSION(?:ID|_ID)?|CREDENTIAL)[A-Z0-9_]*|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)['\"`]?\s*[:=]\s*([^\r\n]+)"
)
DIFF_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])['\"`]?("
    r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|x-csrf-token|"
    r"[A-Z0-9_]*(?:API[_-]?KEY|SECRET|PASSWORD|PASS|TOKEN|COOKIE|OAUTH|PRIVATE[_-]?KEY|SESSION(?:ID|_ID)?|CREDENTIAL)[A-Z0-9_]*|"
    r"api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token"
    r")['\"`]?\s*[:=]\s*([^\r\n]+)"
)
SECRET_PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:"
    r"[\s'\"`]*|"
    r"(?:none|null|false|0)|"
    r"(?:redacted|masked|placeholder|example|sample|dummy|fake|test|todo|tbd|changeme|change-me|replace-me|"
    r"replace-with-[a-z0-9_-]+|your-[a-z0-9_-]+)|"
    r"(?:required|optional|string|boolean)|"
    r"(?:basic\s+auth|bearer\s+token|basic\s+<[^>]+>|bearer\s+<[^>]+>)|"
    r"(?:rotatable-pass|test-pass|test-password|dummy-password|fake-password|should-not-leak)|"
    r"(?:\[[^\]]*(?:redacted|masked|placeholder|token|secret|password|key|pass)[^\]]*\])|"
    r"(?:<[^>]*(?:token|secret|password|key|pass|cookie|credential)[^>]*>)|"
    r"(?:\$\{?[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|PASSWORD|COOKIE|CREDENTIAL)[A-Z0-9_]*\}?|%[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|PASSWORD|COOKIE|CREDENTIAL)[A-Z0-9_]*%)"
    r")$"
)
SECRET_CONTEXT_PLACEHOLDER_RE = re.compile(
    r"(?i)("
    r"os\.getenv|os\.environ\.get|getenv|process\.env|from\s+env|env(?:ironment)?\s+var(?:iable)?|"
    r"replace\s+with|use\s+your|example\s+only|test\s+only|"
    r"替换为|占位|示例|测试|假密码|环境变量|变量名"
    r")"
)
ENV_LOOKUP_RE = re.compile(r"(?i)\b(?:os\.getenv|os\.environ\.get|getenv|process\.env)\b")
ENV_FUNCTION_LOOKUP_RE = re.compile(r"(?i)\b(?:os\.getenv|os\.environ\.get|getenv)\s*\(")
CODE_EXPRESSION_RE = re.compile(r"(?i)^[A-Za-z_][A-Za-z0-9_.]*\s*\(")
CODE_FILE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
GENERIC_DIFF_ASSIGNMENT_RE = re.compile(r"(?<![A-Za-z0-9_])['\"`]?[A-Za-z_][A-Za-z0-9_.-]*['\"`]?\s*[:=]\s*(.+)$")
INLINE_HEADER_PLACEHOLDER_RE = re.compile(
    r"(?i)(?:\bbasic\s+auth\b|\bbearer\s+(?:<[^>]+>|\[[^\]]+\]|\btoken\b))"
)
AUTH_PAYLOAD_RE = re.compile(r"(?i)\b(?:basic\s+auth|bearer)\s+([A-Za-z0-9][A-Za-z0-9._~+/=-]{6,})")
HEADER_VALUE_BOUNDARY_RE = re.compile(r"[`。；;，,]|(?:\s+-\s+)|(?:\s+[A-Z][A-Za-z]+:)")
ARTIFACT_PATH_ENV_NAMES = {
    "PIPELINE_RESEARCH_REPORT_FILE",
    "PIPELINE_REQUIREMENTS_FILE",
    "PIPELINE_REQUIREMENTS_DISCUSSION_FILE",
    "PIPELINE_REQUIREMENTS_REVIEW_FILE",
    "PIPELINE_DELIVERY_PLAN_FILE",
    "PIPELINE_SOLUTION_FILE",
    "PIPELINE_SOLUTION_REVIEW_FILE",
    "PIPELINE_PATCH_SUMMARY_FILE",
    "PIPELINE_VERIFICATION_REPORT_FILE",
    "PIPELINE_CODE_REVIEW_FILE",
    "PIPELINE_DEPLOYMENT_REPORT_FILE",
    "PIPELINE_WRITEBACK_REPORT_FILE",
    "PIPELINE_GIT_PUBLISH_REPORT_FILE",
    "PIPELINE_GRAPHIFY_CONTEXT_FILE",
    "PIPELINE_GRAPHIFY_SCOPE_VALIDATION_FILE",
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
    text = PRIVATE_KEY_MARKER_RE.sub("[REDACTED_PRIVATE_KEY]", text)
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


def extract_hermes_session_id(command_text: str) -> str:
    match = SESSION_ID_RE.search(command_text or "")
    return match.group(1).strip() if match else ""


def recovered_stage_pass(stage: str, text: str) -> bool:
    if not text.strip():
        return False
    if STATUS_RE.search(text):
        return True
    if stage == "external_research" and "NO_EXTERNAL_LOOKUP_NEEDED" in text:
        return True
    return False


EXTERNAL_LOOKUP_REQUIRED_RE = re.compile(
    r"(?i)官方文档|外部资料|联网|网上|browser|web\s+search|sdk|第三方|平台政策|合规|release|changelog|"
    r"version-sensitive|版本敏感|依赖升级|upgrade dependency|exchange rule|交易所规则"
)


def run_dir_path() -> Path:
    raw = os.environ.get("PIPELINE_RUN_DIR", "").strip()
    return Path(raw).expanduser() if raw else Path("")


def current_source_urls() -> list[str]:
    run_dir = run_dir_path()
    if not run_dir or str(run_dir) == ".":
        return []
    meta = read_json(run_dir / "run_meta.json")
    urls = meta.get("source_urls")
    if isinstance(urls, list):
        return [str(item).strip() for item in urls if str(item).strip()]
    return []


def local_context_evidence_files(run_dir: Path) -> list[str]:
    evidence: list[str] = []
    for name in ("context_snapshot.md", "project_memory_context.md", "git_repository_context.md", "graphify_context.md"):
        path = run_dir / name
        try:
            if path.exists() and path.stat().st_size > 0:
                evidence.append(name)
        except OSError:
            continue
    return evidence


def can_synthesize_local_only_research(requirement: str) -> tuple[bool, str]:
    run_dir = run_dir_path()
    if not run_dir or str(run_dir) == "." or not run_dir.exists():
        return False, "missing_pipeline_run_dir"
    source_urls = current_source_urls()
    if any(re.match(r"(?i)^https?://", item) for item in source_urls):
        return False, "http_source_url_requires_real_research"
    if EXTERNAL_LOOKUP_REQUIRED_RE.search(requirement or ""):
        return False, "requirement_mentions_external_lookup"
    evidence = local_context_evidence_files(run_dir)
    if len(evidence) < 3:
        return False, "insufficient_local_context_evidence"
    return True, "local_project_context_is_sufficient"


def synthesized_local_only_research(stage: str, args: argparse.Namespace, requirement: str, proc: subprocess.CompletedProcess[str], command_text: str) -> str:
    run_dir = run_dir_path()
    source_urls = current_source_urls()
    evidence = local_context_evidence_files(run_dir)
    return "\n".join(
        [
            "# External Research Local-Only Evidence",
            "",
            "NO_EXTERNAL_LOOKUP_NEEDED",
            "",
            "原因：本轮 external_research 阶段没有 http/https source URL，需求未要求官方/联网/第三方资料核对；可用项目记忆、Git 上下文、Graphify 上下文和上一阶段 artifact 已足够支撑进入需求评审。",
            "",
            "本地证据：",
            *(f"- `{name}`" for name in evidence),
            "",
            "Source URLs:",
            *(f"- `{item}`" for item in source_urls or ["not_supplied"]),
            "",
            "Hermes 调用诊断：",
            f"- returncode: `{proc.returncode}`",
            f"- command: `{command_text}`",
            "- fallback: `synthesized_local_only_research`",
            "",
            "安全边界：未读取或打印凭证；未下单、划转、提现或启用真实交易；本阶段不修改文件，只返回 research evidence，由 runner 写入 `research_report.md`。",
            f"LIVE_BRIDGE_STAGE: {stage}",
            "LIVE_BRIDGE_STATUS: pass",
        ]
    )


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
        return ("research_report.md", "project_memory_context.md", "git_repository_context.md", "graphify_context.md")
    if stage == "requirements_review":
        return ("research_report.md", "project_memory_context.md", "git_repository_context.md", "graphify_context.md", "requirements.md", "requirements_discussion.md")
    if stage == "solution_review":
        return ("graphify_context.md", "requirements.md", "requirements_review.md", "delivery_plan.json", "solution.md", "graphify_scope_validation.md")
    if stage == "code_execution":
        return (
            "research_report.md",
            "requirements.md",
            "graphify_context.md",
            "requirements_discussion.md",
            "requirements_review.md",
            "delivery_plan.json",
            "solution.md",
            "solution_review.md",
            "graphify_scope_validation.md",
            "pre_execution_risk.json",
            "group_plan_publish.md",
        )
    if stage in {"verification", "code_review", "deployment", "memory_writeback", "git_publish"}:
        return (
            "research_report.md",
            "requirements_discussion.md",
            "graphify_context.md",
            "delivery_plan.json",
            "solution.md",
            "solution_review.md",
            "graphify_scope_validation.md",
            "pre_execution_risk.json",
            "group_plan_publish.md",
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


def lark_cli_profile() -> str:
    """Return the lark-cli profile used by nofx pipeline agents.

    This is a profile name only, not a secret. Agents should still use the
    configured lark-cli auth store and must never read or print credential files.
    """

    return os.environ.get("SMART_ARB_LARK_CLI_PROFILE", "cli_a953bab500b89cd1").strip()


def bridge_env(args: argparse.Namespace, profile_dir: Path, stage: str = "") -> dict[str, str]:
    env = dict(os.environ)
    if stage in NON_CODE_HERMES_STAGES:
        for name in ARTIFACT_PATH_ENV_NAMES:
            env.pop(name, None)
    env["HOME"] = str(args.home)
    env["HERMES_HOME"] = str(profile_dir)
    env["HERMES_ACCEPT_HOOKS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    profile = lark_cli_profile()
    if profile:
        env["SMART_ARB_LARK_CLI_PROFILE"] = profile
        # lark-cli currently requires the explicit --profile flag for reliable
        # cross-agent use, but exporting this marker makes the chosen profile
        # visible to spawned Hermes agents without exposing credentials.
        env["LARKSUITE_CLI_PROFILE"] = profile
    path_parts = [str(args.hermes_bin.parent), str(VENV_BIN), "/usr/local/bin", "/usr/bin", "/bin"]
    existing_path = env.get("PATH", "")
    env["PATH"] = ":".join([part for part in path_parts if part] + ([existing_path] if existing_path else []))
    return env


def feishu_access_guidance() -> str:
    profile = lark_cli_profile()
    profile_clause = f"--profile {shlex.quote(profile)} " if profile else ""
    return f"""
Feishu/Lark access contract for all pipeline agents:
- If the requirement references Feishu, Lark, Base, bitable, table, or view data, prefer lark-cli before declaring the source unreadable.
- Use the configured lark-cli profile explicitly: `lark-cli {profile_clause}base +table-list --base-token <base_token>` and then `lark-cli {profile_clause}base +record-list --base-token <base_token> --table-id <current_table_id> [--view-id <view_id>]`.
- A web URL that redirects to a login page does not prove the Base is unreadable; list tables with lark-cli first.
- If a user-provided table/view id is stale or returns not_found, list the Base tables/views and use the current table id by name instead of failing immediately.
- Do not run `lark-cli config show`, do not read `.lark-cli/config.json`, and do not print, move, or modify tokens, cookies, app secrets, OAuth state, API keys, or credential files.
""".strip()


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

{feishu_access_guidance()}

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
Act as web-agent. First decide whether current external docs or online references are needed before implementation.
Use available browser/search tools when the requirement depends on external facts, third-party APIs, exchange behavior, library versions, deployment patterns, or unknown best practices.
If no external lookup is needed, explicitly say NO_EXTERNAL_LOOKUP_NEEDED, explain why, and give local project evidence instead.
Return concise research evidence, source URLs when used, constraints, and how the findings affect implementation.
Do not modify files. Do not write the stage output artifact yourself.
"""
    elif stage == "requirements_discussion":
        specific = """
Act as project-agent plus reviewer, using the project memory, `git_repository_context.md`, and `graphify_context.md` as primary context sources.
Before proposing changes, read or use the supplied project memory/docs/todo/done and graphify context; identify the most likely modules/files to modify.
Project-agent must consider refreshed git state: current branch, HEAD, dirty worktree, local branches, remote branches, and fetched remote refs. It may use git fetch evidence supplied by the runner, but must not merge, reset, checkout, stash, or discard changes.
Run at least four short rounds of discussion:
1. project-agent summarizes the user goal, git/branch context, available project context, existing memory decisions, likely change locations, and missing context.
2. reviewer challenges ambiguity, hidden risks, missing tests, deployment impact, safety boundaries, and whether web research is still missing.
3. project-agent revises a whole-task requirement: acceptance criteria, target files, verification commands, non-goals, and current logic. Do not split the task into deferred slices merely for granularity.
4. reviewer gives final risk routing: low/medium can auto-execute; high risk must be sent to the group for human confirmation before code execution.
Return the final refined requirement and a group-ready summary with context used, graphify observations, assumptions, risks, branch/git observations, and open questions.
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
Treat Prior accepted stage context, `delivery_plan.json`, and Repair context as hard constraints. Do not implement later-phase strategy work if the current requirement or research context says to stay on P0 memory/environment work.
Implement the complete accepted requirement as constrained by the reviewed plan; do not create artificial deferred task slices.
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
        reviewer_provider = effective_reviewer_provider(args, role)
        reviewer_model = effective_reviewer_model(args, role)
        specific = """
Act as {role}. Review the pipeline artifacts for {focus}.
You are one side of a multi-model review gate. Produce your own independent verdict and evidence, then explain how your findings should be merged with other reviewers until no blocker remains.
For solution review, validate the structured `delivery_plan.json` contract first; `solution.md` is only the human-readable rendering. Use `graphify_context.md` and `graphify_scope_validation.md` to challenge missing related modules/tests and respect its policy: warning by default, block only for cross-repo paths, credential/auth material, or production trading/order/fund-transfer risk.
Do not require artificial task-splitting granularity; review the whole accepted requirement and block only for concrete risk, missing context, invalid target files, missing tests, unsafe execution, or a graphify scope block.
If you return requires_revision, write every non-pass reason as explicit Blocker lines and then give a complete revised plan that another reviewer/coordinator can merge directly into delivery_plan.json. Include file-level actions, create_if_missing rationale, verification commands, publish containment, docs/memory/todo/done content assertions, and final acceptance boundaries when relevant.
For every review stage, include a Reviewer discussion note: what you agree with from the available prior artifacts, what you challenge, and how the joint final plan should change. Do not stop at "inspect first"; the review output must be sufficient for revise_solution to produce an implementable plan.
Include exactly these reviewer identity lines:
Reviewer role: {role}
Reviewer provider: {reviewer_provider}
Reviewer model: {reviewer_model}
If the material is acceptable, include exactly this line:
Final verdict: {expected}
If it is not acceptable, include:
Final verdict: requires_revision
""".format(role=role, focus=focus, expected=expected, reviewer_provider=reviewer_provider, reviewer_model=reviewer_model)
    else:
        specific = "Return concise stage evidence."
    return common.strip() + "\n\n" + specific.strip()


def effective_reviewer_provider(args: argparse.Namespace, role: str) -> str:
    override = str(getattr(args, "_reviewer_provider_override", "") or "").strip()
    if override:
        return override
    suffix = "A" if role == "reviewer-a" else "B" if role == "reviewer-b" else ""
    if suffix:
        value = os.environ.get(f"SMART_ARB_REVIEWER_{suffix}_PROVIDER", "").strip()
        if value:
            return value
    return str(args.provider)


def effective_reviewer_model(args: argparse.Namespace, role: str) -> str:
    override = str(getattr(args, "_reviewer_model_override", "") or "").strip()
    if override:
        return override
    suffix = "A" if role == "reviewer-a" else "B" if role == "reviewer-b" else ""
    if suffix:
        value = os.environ.get(f"SMART_ARB_REVIEWER_{suffix}_MODEL", "").strip()
        if value:
            return value
    return str(args.model)


def parse_provider_model(value: str) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text:
        return None
    for separator in ("/", ":"):
        if separator in text:
            provider, model = text.split(separator, 1)
            provider = provider.strip()
            model = model.strip()
            return (provider, model) if provider and model else None
    return None


def reviewer_model_attempts(args: argparse.Namespace, role: str) -> list[tuple[str, str]]:
    primary = (effective_reviewer_provider(args, role), effective_reviewer_model(args, role))
    raw_fallbacks = str(getattr(args, "reviewer_fallback_models", "") or "").strip()
    attempts: list[tuple[str, str]] = [primary]
    for item in re.split(r"[,;\s]+", raw_fallbacks):
        parsed = parse_provider_model(item)
        if parsed:
            attempts.append(parsed)

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for provider, model in attempts:
        key = (provider.strip().lower(), model.strip().lower())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append((provider.strip(), model.strip()))
    return deduped


def run_hermes_command_for_model(
    stage: str,
    args: argparse.Namespace,
    requirement: str,
    profile_dir: Path,
    provider: str,
    model: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    attempt_args = copy.copy(args)
    if stage in {"requirements_review", "solution_review", "code_review"}:
        attempt_args._reviewer_provider_override = provider
        attempt_args._reviewer_model_override = model
    prompt = stage_prompt(stage, attempt_args, requirement)
    command = [
        str(args.hermes_bin),
        "chat",
        "--ignore-user-config",
        "--provider",
        provider,
        "-m",
        model,
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
    diagnostic_command = [
        str(args.hermes_bin),
        "chat",
        "--ignore-user-config",
        "--provider",
        provider,
        "-m",
        model,
        "-q",
        "[stage prompt redacted]",
        "-Q",
        "--max-turns",
        str(args.max_turns),
        "--source",
        f"smart-arb-live-bridge:{stage}",
    ]
    if args.allow_yolo:
        diagnostic_command.append("--yolo")
    return run_command(command, cwd=args.project_dir, env=bridge_env(args, profile_dir, stage)), " ".join(shlex.quote(str(part)) for part in diagnostic_command)


def run_echo_stage(stage: str, reviewer_role: str = "") -> int:
    if stage == "requirements_review":
        print("# Smart Arb Live Bridge Echo Requirements Review")
        print("Final verdict: ready_for_solution")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
        print("Reviewer provider: echo")
        print(f"Reviewer model: echo-{reviewer_role or 'reviewer-a'}")
    elif stage == "solution_review":
        print("# Smart Arb Live Bridge Echo Solution Review")
        print("Final verdict: ready_for_implement")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
        print("Reviewer provider: echo")
        print(f"Reviewer model: echo-{reviewer_role or 'reviewer-a'}")
    elif stage == "code_review":
        print("# Smart Arb Live Bridge Echo Review")
        print("Final verdict: pass")
        print(f"Reviewer role: {reviewer_role or 'reviewer-a'}")
        print("Reviewer provider: echo")
        print(f"Reviewer model: echo-{reviewer_role or 'reviewer-a'}")
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
    profile_dir = profile_home(args.runtime_home, args.profile)
    expected_verdict = EXPECTED_REVIEW_VERDICTS.get(stage)
    role = str(getattr(args, "reviewer_role", "") or "").strip() or "reviewer-a"
    attempts = reviewer_model_attempts(args, role) if expected_verdict else [(str(args.provider), str(args.model))]
    last_failure_code = 1

    for attempt_index, (provider, model) in enumerate(attempts, start=1):
        if expected_verdict:
            print(f"# reviewer model attempt {attempt_index}/{len(attempts)}")
            print(f"Reviewer role: {role}")
            print(f"Reviewer provider: {provider}")
            print(f"Reviewer model: {model}")
        proc, command_text = run_hermes_command_for_model(stage, args, requirement, profile_dir, provider, model)
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print("\n# stderr")
            print(proc.stderr.rstrip())

        plain = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
        session_id = extract_hermes_session_id(plain)
        if session_id:
            print(f"LIVE_BRIDGE_AGENT_SESSION_ID: {session_id}")
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
        verdict = final_verdict(plain)

        if expected_verdict and verdict and verdict != expected_verdict:
            print(f"# reviewer returned concrete blocker on {provider}/{model}; no fallback is attempted")
            print("Final verdict: requires_revision")
            print(f"LIVE_BRIDGE_STAGE: {stage}")
            print("LIVE_BRIDGE_STATUS: fail")
            return 3

        if proc.returncode == 0 and status and status.group(1).lower() == "pass":
            if not expected_verdict or verdict == expected_verdict:
                return 0

        if stage == "external_research":
            can_synthesize, synthesize_reason = can_synthesize_local_only_research(requirement)
            if can_synthesize:
                print("\n# synthesized_local_only_research")
                print(synthesized_local_only_research(stage, args, requirement, proc, command_text))
                return 0
            print("\n# bridge failure diagnostic")
            print(f"- returncode: {proc.returncode}")
            print(f"- command: `{command_text}`")
            print(f"- reason: {synthesize_reason}")
            if not (proc.stdout or "").strip():
                print("- stdout: empty")
            if not (proc.stderr or "").strip():
                print("- stderr: empty")

        last_failure_code = proc.returncode or 2
        if expected_verdict and attempt_index < len(attempts):
            print("\n# reviewer fallback attempt failed")
            print(f"- attempted_provider: {provider}")
            print(f"- attempted_model: {model}")
            print(f"- command: `{command_text}`")
            print(f"- returncode: {proc.returncode}")
            print(f"- verdict: {verdict or 'missing_verdict'}")
            print("- action: try_next_reviewer_model")
            continue

        print(f"LIVE_BRIDGE_STAGE: {stage}")
        print("LIVE_BRIDGE_STATUS: fail")
        return last_failure_code or 1


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


def diff_added_lines(diff: str) -> list[str]:
    lines: list[str] = []
    for raw_line in (diff or "").splitlines():
        if not raw_line.startswith("+") or raw_line.startswith("+++"):
            continue
        lines.append(raw_line[1:])
    return lines


def diff_added_line_records(diff: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current_file = "unknown"
    next_new_line: int | None = None
    for raw_line in (diff or "").splitlines():
        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            if path == "/dev/null":
                current_file = "deleted"
            elif path.startswith("b/"):
                current_file = path[2:]
            else:
                current_file = path.strip('"')
            continue
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,\d+)?", raw_line)
            next_new_line = int(match.group(1)) if match else None
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            records.append({"file": current_file, "line": next_new_line, "text": raw_line[1:]})
            if next_new_line is not None:
                next_new_line += 1
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        if next_new_line is not None:
            next_new_line += 1
    return records


def normalize_secret_value(value: str) -> str:
    text = (value or "").strip()
    if "#" in text:
        text = text.split("#", 1)[0].strip()
    return text.strip().strip(",;").strip()


def is_secret_placeholder_literal(value: str) -> bool:
    stripped = normalize_secret_value(value).strip("'\"`").strip()
    if SECRET_PLACEHOLDER_RE.fullmatch(stripped):
        return True
    if SECRET_CONTEXT_PLACEHOLDER_RE.search(stripped) and not ENV_LOOKUP_RE.search(stripped):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|PASSWORD|COOKIE|CREDENTIAL)[A-Z0-9_]*", stripped):
        return True
    return False


def is_safe_env_lookup_value(value: str) -> bool:
    text = normalize_secret_value(value).strip("'\"`").strip()
    if not ENV_LOOKUP_RE.search(text):
        return False
    literal_values = [match.group("value") for match in STRING_LITERAL_RE.finditer(text)]
    if not literal_values:
        return True
    fallback_values = literal_values[1:] if ENV_FUNCTION_LOOKUP_RE.search(text) else literal_values
    if not fallback_values:
        return True
    return all(is_secret_placeholder_literal(fallback) for fallback in fallback_values)


def is_secret_placeholder_value(value: str) -> bool:
    text = normalize_secret_value(value)
    stripped = text.strip("'\"`").strip()
    if ENV_LOOKUP_RE.search(stripped):
        return is_safe_env_lookup_value(stripped)
    if SECRET_PLACEHOLDER_RE.fullmatch(stripped):
        return True
    if CODE_EXPRESSION_RE.match(stripped):
        return False
    if SECRET_CONTEXT_PLACEHOLDER_RE.search(stripped):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|PASSWORD|COOKIE|CREDENTIAL)[A-Z0-9_]*", stripped):
        return True
    return False


def is_code_expression_value(value: str, file_path: str) -> bool:
    suffix = Path(file_path or "").suffix.lower()
    if suffix not in CODE_FILE_SUFFIXES:
        return False
    stripped = normalize_secret_value(value).strip("'\"`").strip()
    if CODE_EXPRESSION_RE.match(stripped):
        return True
    return stripped.startswith(("{", "[", "(", "lambda "))


def is_inline_header_placeholder_value(value: str, file_path: str) -> bool:
    suffix = Path(file_path or "").suffix.lower()
    if suffix not in {".md", ".markdown", ".txt", ".rst"}:
        return False
    text = normalize_secret_value(value).strip("'\"`").strip()
    match = INLINE_HEADER_PLACEHOLDER_RE.match(text)
    if not match:
        return False
    first_segment = HEADER_VALUE_BOUNDARY_RE.split(text, maxsplit=1)[0].strip()
    if INLINE_HEADER_PLACEHOLDER_RE.fullmatch(first_segment):
        return True
    trailing_text = text[match.end() :].strip()
    if not trailing_text:
        return True
    if AUTH_PAYLOAD_RE.match(text):
        return False
    if KNOWN_SECRET_RE.search(trailing_text) or SENSITIVE_VALUE_RE.search(trailing_text):
        return False
    return bool(SECRET_CONTEXT_PLACEHOLDER_RE.search(trailing_text))


def is_sensitive_header_key(key: str) -> bool:
    key_lower = (key or "").lower()
    return any(name in key_lower for name in ("authorization", "cookie", "x-api-key", "x-auth-token", "x-csrf-token"))


def is_safe_sensitive_header_value(value: str, file_path: str) -> bool:
    stripped = normalize_secret_value(value).strip("'\"`").strip()
    if not stripped:
        return True
    if SECRET_PLACEHOLDER_RE.fullmatch(stripped):
        return True
    if is_inline_header_placeholder_value(stripped, file_path):
        return True
    if ENV_LOOKUP_RE.search(stripped):
        return is_safe_env_lookup_value(stripped)
    return False


def sensitive_assignment_has_secret(key: str, value: str) -> bool:
    return secret_assignment_finding(key, value, "", "", None)["blocking"]


def redact_diff_snippet(line: str, limit: int = 180) -> str:
    def redact_assignment(match: re.Match[str]) -> str:
        return f"{match.group(1)}=[REDACTED]"

    text = DIFF_SENSITIVE_ASSIGNMENT_RE.sub(redact_assignment, line or "")
    text = redact_text(text)
    if "[REDACTED_PRIVATE_KEY]" in text:
        return "[REDACTED_PRIVATE_KEY]"
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "...[truncated]"
    return text


def secret_assignment_finding(
    key: str,
    value: str,
    line: str,
    file_path: str,
    line_number: int | None,
) -> dict[str, Any]:
    text = normalize_secret_value(value)
    base = {
        "file": file_path or "unknown",
        "line": line_number,
        "key": key or "secret",
        "snippet": redact_diff_snippet(line),
    }
    if PRIVATE_KEY_MARKER_RE.search(line or ""):
        return {**base, "risk": "high", "rule": "private_key_marker", "blocking": True}
    if KNOWN_SECRET_RE.search(line or "") or KNOWN_SECRET_RE.search(text):
        return {**base, "risk": "high", "rule": "known_secret_pattern", "blocking": True}
    if SENSITIVE_VALUE_RE.search(text):
        return {**base, "risk": "high", "rule": "high_entropy_secret_value", "blocking": True}
    if is_sensitive_header_key(key):
        if is_safe_sensitive_header_value(text, file_path):
            return {**base, "risk": "low", "rule": "secret_placeholder", "blocking": False}
        return {**base, "risk": "high", "rule": "sensitive_header_assignment", "blocking": True}
    if ENV_LOOKUP_RE.search(text):
        if is_safe_env_lookup_value(text):
            return {**base, "risk": "low", "rule": "secret_placeholder", "blocking": False}
        return {**base, "risk": "high", "rule": "sensitive_assignment", "blocking": True}
    if not text or is_secret_placeholder_value(text):
        return {**base, "risk": "low", "rule": "secret_placeholder", "blocking": False}
    if is_code_expression_value(text, file_path):
        return {**base, "risk": "low", "rule": "code_expression", "blocking": False}
    return {**base, "risk": "high", "rule": "sensitive_assignment", "blocking": True}


def secret_token_finding(rule: str, line: str, file_path: str, line_number: int | None) -> dict[str, Any]:
    snippet = "[REDACTED_PRIVATE_KEY]" if rule.startswith("private_key") else redact_diff_snippet(line)
    return {
        "file": file_path or "unknown",
        "line": line_number,
        "key": "secret",
        "risk": "high",
        "rule": rule,
        "blocking": True,
        "snippet": snippet,
    }


def high_entropy_literal_findings(line: str, file_path: str, line_number: int | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for match in QUOTED_VALUE_RE.finditer(line or ""):
        value = match.group(1)
        if SENSITIVE_VALUE_RE.fullmatch(value):
            findings.append(secret_token_finding("high_entropy_secret_value", value, file_path, line_number))
    assignment_match = GENERIC_DIFF_ASSIGNMENT_RE.search(line or "")
    if assignment_match:
        value = normalize_secret_value(assignment_match.group(1)).strip("'\"`").strip()
        if SENSITIVE_VALUE_RE.fullmatch(value):
            findings.append(secret_token_finding("high_entropy_secret_value", value, file_path, line_number))
    stripped = (line or "").strip().strip(",;")
    if SENSITIVE_VALUE_RE.fullmatch(stripped):
        findings.append(secret_token_finding("high_entropy_secret_value", stripped, file_path, line_number))
    return findings


def staged_diff_secret_findings(diff: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in diff_added_line_records(diff):
        line = str(record.get("text") or "")
        file_path = str(record.get("file") or "unknown")
        line_number = record.get("line") if isinstance(record.get("line"), int) else None
        stripped = line.strip()
        if PRIVATE_KEY_MARKER_RE.search(line):
            findings.append(secret_token_finding("private_key_marker", line, file_path, line_number))
            continue
        if PRIVATE_KEY_PATH_RE.search(file_path) and PRIVATE_KEY_MATERIAL_RE.fullmatch(stripped):
            findings.append(secret_token_finding("private_key_material", line, file_path, line_number))
            continue
        matches = list(DIFF_SENSITIVE_ASSIGNMENT_RE.finditer(line))
        if matches:
            for match in matches:
                findings.append(secret_assignment_finding(match.group(1), match.group(2), line, file_path, line_number))
            continue
        if KNOWN_SECRET_RE.search(line):
            findings.append(secret_token_finding("known_secret_pattern", line, file_path, line_number))
            continue
        entropy_findings = high_entropy_literal_findings(line, file_path, line_number)
        if entropy_findings:
            findings.extend(entropy_findings)
    return findings


def format_secret_scan_findings(findings: list[dict[str, Any]], limit: int = 20) -> str:
    blocking = sum(1 for item in findings if item.get("blocking"))
    non_blocking = max(0, len(findings) - blocking)
    lines = [
        "## Secret Scan Findings",
        f"- Blocking findings: {blocking}",
        f"- Non-blocking findings: {non_blocking}",
    ]
    for finding in findings[: max(1, int(limit or 20))]:
        line_number = finding.get("line")
        location = str(finding.get("file") or "unknown")
        if isinstance(line_number, int):
            location = f"{location}:{line_number}"
        lines.append(
            "- "
            + f"{location} risk={finding.get('risk')} rule={finding.get('rule')} "
            + f"blocking={str(bool(finding.get('blocking'))).lower()} "
            + f"snippet={finding.get('snippet') or '[REDACTED]'}"
        )
    if len(findings) > limit:
        lines.append(f"- ... {len(findings) - limit} more findings omitted")
    return "\n".join(lines)


def staged_diff_has_secret(diff: str) -> bool:
    return any(finding.get("blocking") for finding in staged_diff_secret_findings(diff))


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
    secret_findings = staged_diff_secret_findings(staged_diff.stdout or "")
    if secret_findings:
        sections.append(format_secret_scan_findings(secret_findings))
    if any(finding.get("blocking") for finding in secret_findings):
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
    parser.add_argument(
        "--reviewer-fallback-models",
        default=os.environ.get("SMART_ARB_REVIEWER_FALLBACK_MODELS", DEFAULT_REVIEWER_FALLBACK_MODELS),
        help="comma-separated provider/model reviewer fallback chain used when a reviewer provider is unavailable",
    )
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

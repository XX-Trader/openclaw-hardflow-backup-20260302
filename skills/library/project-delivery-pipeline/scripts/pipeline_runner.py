#!/usr/bin/env python3
"""Project delivery pipeline state machine.

This runner owns deterministic orchestration artifacts and gates. It does not
pretend to be the coding agent runtime. In dry-run mode it simulates every
stage so the workflow can be tested without mutating product code. In live mode
it requires external agent artifacts for implementation, verification, and
review stages.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable


SCHEMA_VERSION = "1.0"
DEFAULT_RUNTIME_HOME = {
    "generic": "~/.hardflow-runtime",
    "hermes": "~/.hermes",
    "openclaw": "~/.openclaw",
}
EXPECTED_VERDICTS = {
    "requirements_review": "ready_for_solution",
    "solution_review": "ready_for_implement",
    "code_review": "pass",
}
PROJECT_MEMORY_FILES = {
    "PROJECT_PROFILE.md": "project profile and module boundary",
    "DECISIONS.md": "durable project decisions",
    "DELIVERY_RULES.md": "coding and acceptance rules",
    "API_REGISTRY.json": "third-party API ownership and docs",
    "SOURCE_REGISTRY.json": "official docs, changelog, and repo sources",
    "IMPACT_MAP.json": "module/file impact map for change localization",
    "RETRIEVAL_MANIFEST.json": "hybrid retrieval policy and optional RAG backend",
}
STAGE_AGENT_MAP = {
    "intake": "coordinator",
    "context_snapshot": "project-agent",
    "project_memory_context": "project-agent",
    "git_repository_context": "project-agent",
    "graphify_context": "project-agent",
    "external_research": "web-agent",
    "requirements_package": "project-agent",
    "requirements_discussion": "project-agent,reviewer",
    "requirements_review": "reviewer",
    "solution_package": "project-agent",
    "graphify_scope_validation": "project-agent",
    "solution_review": "reviewer",
    "plan_publish": "coordinator",
    "code_execution": "backend-dev",
    "verification": "tester",
    "code_review": "reviewer",
    "deployment": "deployer",
    "acceptance": "tester",
    "writeback": "doc-writer",
    "git_publish": "coordinator",
    "failure_summary": "coordinator",
}
SIMULATED_FAILURES = {
    "requirements",
    "solution",
    "verification",
    "code_review",
    "acceptance_requirement",
    "acceptance_implementation",
    "git_publish",
}
VERDICT_RE = re.compile(
    r"(?im)^\s*(?:Final verdict|final_verdict|verdict)\s*:\s*([a-z_]+)"
)
DUAL_REVIEW_STAGES = {"requirements_review", "solution_review", "code_review"}
REVIEWER_ROLE_ARG_RE = re.compile(
    r"(?:^|\s)--reviewer-role(?:=|\s+)(?:\"([A-Za-z0-9_.-]+)\"|'([A-Za-z0-9_.-]+)'|([A-Za-z0-9_.-]+))"
)
REVIEWER_ROLE_OUTPUT_RE = re.compile(
    r"(?im)^\s*(?:Reviewer role|reviewer_role|reviewer-role)\s*:\s*([A-Za-z0-9_.-]+)\s*$"
)
REVIEWER_MODEL_ARG_RE = re.compile(
    r"(?:^|\s)(?:--model|-m)(?:=|\s+)(?:\"([^\"\s]+)\"|'([^'\s]+)'|([^\s]+))"
)
REVIEWER_PROVIDER_ARG_RE = re.compile(
    r"(?:^|\s)--provider(?:=|\s+)(?:\"([^\"\s]+)\"|'([^'\s]+)'|([^\s]+))"
)
REVIEWER_MODEL_OUTPUT_RE = re.compile(
    r"(?im)^\s*(?:Reviewer model|reviewer_model|model)\s*:\s*([A-Za-z0-9_./:-]+)\s*$"
)
REVIEWER_PROVIDER_OUTPUT_RE = re.compile(
    r"(?im)^\s*(?:Reviewer provider|reviewer_provider|provider)\s*:\s*([A-Za-z0-9_.-]+)\s*$"
)
AGENT_SESSION_ID_RE = re.compile(
    r"(?im)^\s*(?:LIVE_BRIDGE_AGENT_SESSION_ID|agent_session_id|session_id|sessionId)\s*[:=]\s*([A-Za-z0-9_.:-]+)\s*$"
)
AGENT_RUN_ID_RE = re.compile(
    r"(?im)^\s*(?:LIVE_BRIDGE_AGENT_RUN_ID|agent_run_id|agentRunId|runId)\s*[:=]\s*([A-Za-z0-9_.:-]+)\s*$"
)
AGENT_SESSION_KEY_RE = re.compile(
    r"(?im)^\s*(?:LIVE_BRIDGE_AGENT_SESSION_KEY|agent_session_key|sessionKey)\s*[:=]\s*([A-Za-z0-9_.:/-]+)\s*$"
)
PATH_TOKEN_RE = re.compile(
    r"(?:`([^`\r\n]+)`)|"
    r"(?:(?<![A-Za-z0-9_./\\])((?:[A-Za-z]:[\\/]|/(?!/))[A-Za-z0-9_.\-/\\]*"
    r"(?:\.(?:py|md|json|json5|yaml|yml|toml|js|jsx|ts|tsx|html|css|sh|ps1|sql)))(?![A-Za-z0-9_/\\-]))|"
    r"(?:(?<![A-Za-z0-9_./\\])([.]?[A-Za-z0-9_][A-Za-z0-9_.\-/\\]*"
    r"(?:\.(?:py|md|json|json5|yaml|yml|toml|js|jsx|ts|tsx|html|css|sh|ps1|sql)))(?![A-Za-z0-9_/\\-]))",
    re.IGNORECASE,
)
UNICODE_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./\\-])([\w\u4e00-\u9fff][\w\u4e00-\u9fff_.\-/\\]*"
    r"(?:\.(?:py|md|json|json5|yaml|yml|toml|js|jsx|ts|tsx|html|css|sh|ps1|sql)))(?![\w/\\-])",
    re.IGNORECASE,
)
PLAN_PATH_RE = re.compile(r"(?:/|\\|\.(?:py|md|json|json5|yaml|yml|toml|js|jsx|ts|tsx|html|css|sh|ps1|sql)$)", re.IGNORECASE)
PSEUDO_TARGET_PATH_RE = re.compile(
    r"^(?:simulation_only|read_only|signal_only|mock|replay)(?:/(?:simulation_only|read_only|signal_only|mock|replay))*$",
    re.IGNORECASE,
)
PATH_CONTEXT_SPLIT_RE = re.compile(
    r"[\r\n;；。]+|\b(?:but|however|yet|and|only)\b|(?:但|但是|不过|然而|并且|然后|同时|只有)",
    re.IGNORECASE,
)
NEGATED_PATH_CONTEXT_RE = re.compile(
    r"\b(?:do\s+not|don't|never|avoid|exclude|excluded|out\s+of\s+scope|must\s+not|should\s+not)\b|"
    r"(?:不要|不得|禁止|不允许|不应|不能|不修改|不编辑|不触碰|别改|别碰|排除|非目标)",
    re.IGNORECASE,
)
STRONG_NEGATED_PATH_CONTEXT_RE = re.compile(
    r"\b(?:do\s+not|don't|never|must\s+not|should\s+not)\s+"
    r"(?:edit|modify|touch|include|add|target|put|use)\b|"
    r"\b(?:exclude|excluded|out\s+of\s+scope)\b|"
    r"(?:不要|不得|禁止|不允许|不应|不能|不让|不修改|不编辑|不触碰|别改|别碰|排除|非目标|不能进入\s*target_files|不得包含|禁止包含|不让(?:它们|其)?进入\s*(?:target_files|must_change_targets))",
    re.IGNORECASE,
)
INSPECT_ONLY_PATH_CONTEXT_RE = re.compile(
    r"\b(?:read[-_ ]?only\s+(?:source|input|file)|inspect[-_ ]?only|source(?:s)?|reference(?:s)?|pattern(?:s)?|example(?:s)?|do\s+not\s+(?:edit|modify|touch)|should\s+not\s+(?:edit|modify|touch))\b|"
    r"(?:只读源|配置源|读取源|参考|参考模式|参考文件|按需检查|检查用|不建议修改|不应强制|不应默认|不要修改|不得修改|不修改|不编辑|非必改|不是(?:必改|目标文件))",
    re.IGNORECASE,
)
MUST_CHANGE_PATH_CONTEXT_RE = re.compile(
    r"\b(?:must[-_ ]?change|required\s+target|target_files?|modify|edit|update|create|implement|writeback)\b|"
    r"(?:必须修改|必改|目标文件|强制目标|新增|创建|实现|修改|更新|写回)",
    re.IGNORECASE,
)
REFERENCE_PATTERN_CONTEXT_RE = re.compile(
    r"\b(?:reference\s+pattern|pattern\s+only|example\s+only)\b|(?:参考模式|参考样例|参考只读|参考文件)",
    re.IGNORECASE,
)
READ_ONLY_SOURCE_CONTEXT_RE = re.compile(
    r"\b(?:read[-_ ]?only\s+source|inspect[-_ ]?only|source\s+file)\b|(?:只读源|配置源|读取源|按需检查|检查用|不建议修改|不应强制|不应默认|非必改)",
    re.IGNORECASE,
)
CONTROL_PLANE_TARGET_REQUEST_RE = re.compile(
    r"\b(?:fix|repair|restore|update|edit|modify|migrate|clean)\b.{0,80}"
    r"\b(?:workflow|pipeline|runtime|control[- ]?plane|state|artifact|\.workflow|\.hermes|\.openclaw)\b|"
    r"\bscripts/openclaw-ops/\b|"
    r"(?:修复|恢复|修改|更新|迁移|清理).{0,40}(?:工作流|pipeline|runtime|运行态|控制面|状态|产物|\.workflow|\.hermes|\.openclaw)",
    re.IGNORECASE,
)
PIPELINE_ARTIFACT_FILES = {
    "code_review.md",
    "context_snapshot.md",
    "delivery_evidence.md",
    "delivery_plan.json",
    "deployment_report.md",
    "failure_summary.md",
    "git_publish_report.md",
    "patch_summary.md",
    "pipeline_state.json",
    "run_meta.json",
    "project_memory_context.md",
    "git_repository_context.md",
    "graphify_context.md",
    "graphify_scope_validation.md",
    "requirements.md",
    "requirements_discussion.md",
    "requirements_review.md",
    "research_report.md",
    "resolved_requirement.md",
    "solution.md",
    "solution_review.md",
    "verification_report.md",
    "writeback_report.md",
}
CONTROL_PLANE_PATH_PREFIXES = (
    ".workflow/",
    "workflow/",
    "scripts/openclaw-ops/",
    "agent-workspaces/",
    "command-runs/",
    "task-center/",
)
WORKFLOW_HOST_BASENAMES = {
    "pipeline_runner.py",
    "live_runtime_bridge.py",
    "project_pipeline_entry.py",
    "backlog_runner.py",
    "runtime_installer.py",
    "hermes_profile_smoke.py",
}
SENSITIVE_TARGET_BASENAME_RE = re.compile(
    r"(?i)^(?:"
    r"auth(?:[-_ ]?state)?|"
    r"credential(?:s)?|"
    r"secret(?:s)?|"
    r"cookie(?:s)?|"
    r"oauth(?:[-_ ]?state)?|"
    r"(?:api[-_ ]?)?key(?:s)?|"
    r"token(?:s)?"
    r")\.(?:json|ya?ml|toml|env)$"
)
CONTROL_PLANE_PATH_PARTS = (
    "/.workflow/",
    "/agent-workspaces/",
    "/command-runs/",
    "/task-center/",
    "/.hermes/",
    "/.openclaw/",
    "/.codex/",
    "/auth-profiles/",
    "/credential-imports/",
    "/sessions/",
)
MAX_FILTERED_TARGET_FINDINGS = 24


class PipelineError(RuntimeError):
    """Raised for invalid runner input."""


@dataclass(frozen=True)
class PipelineConfig:
    project_key: str
    requirement: str | None = None
    requirement_file: Path | None = None
    runtime_host: str = "generic"
    runtime_home: str | None = None
    workspace_root: Path = Path(".workflow/pipeline-runs")
    run_id: str | None = None
    source_urls: tuple[str, ...] = ()
    dry_run: bool = False
    simulate_failure_stage: str | None = None
    max_repair_loops: int = 4
    research_report_file: Path | None = None
    research_commands: tuple[str, ...] = ()
    requirements_discussion_commands: tuple[str, ...] = ()
    requirements_review_commands: tuple[str, ...] = ()
    solution_review_commands: tuple[str, ...] = ()
    code_agent: str = "backend-dev"
    code_command: str | None = None
    patch_summary_file: Path | None = None
    verification_commands: tuple[str, ...] = ()
    verification_report_file: Path | None = None
    code_review_command: str | None = None
    code_review_commands: tuple[str, ...] = ()
    code_review_file: Path | None = None
    deployment_command: str | None = None
    memory_write_command: str | None = None
    git_publish_command: str | None = None
    write_project_memory: bool = False
    command_cwd: Path = Path(".")
    agent_workspace_root: Path | None = None
    command_timeout_seconds: int = 600
    project_memory_root: Path = Path(".workflow/project-memory")
    record_task_center: bool = False
    task_center_db: Path | None = None
    task_center_task_id: str | None = None
    force: bool = False
    human_risk_confirmed: bool = False


@dataclass
class StageRecord:
    name: str
    status: str
    artifact: str | None = None
    verdict: str | None = None
    score: int | None = None
    next_action: str = "continue"
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "artifact": self.artifact,
            "verdict": self.verdict,
            "score": self.score,
            "next_action": self.next_action,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AgentWorkspace:
    stage: str
    agent_id: str
    workspace_dir: Path
    repo_dir: Path
    mode: str
    isolated: bool
    primary: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "agent_id": self.agent_id,
            "workspace_dir": str(self.workspace_dir),
            "repo_dir": str(self.repo_dir),
            "mode": self.mode,
            "isolated": self.isolated,
            "primary": self.primary,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug[:64] or "pipeline-run"


def default_run_id(project_key: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{slugify(project_key)}"


def load_requirement(config: PipelineConfig) -> str:
    parts: list[str] = []
    if config.requirement:
        parts.append(config.requirement.strip())
    if config.requirement_file:
        if not config.requirement_file.exists():
            raise PipelineError(f"requirement file not found: {config.requirement_file}")
        parts.append(config.requirement_file.read_text(encoding="utf-8").strip())
    requirement = "\n\n".join(part for part in parts if part)
    if not requirement:
        raise PipelineError("provide --requirement or --requirement-file")
    return requirement


def resolve_runtime_context(config: PipelineConfig) -> dict[str, Any]:
    runtime_home = config.runtime_home or DEFAULT_RUNTIME_HOME.get(config.runtime_host) or f"~/.{slugify(config.runtime_host)}"
    return {
        "host": config.runtime_host,
        "runtime_home": runtime_home,
        "state_dir": f"{runtime_home}/.workflow/pipeline-runs",
        "skill_entry": "skills/library/project-delivery-pipeline/SKILL.md",
        "adapter_contract": "references/runtime-adapter.md",
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    write_text(path, content)


def write_json_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        return
    write_json(path, payload)


def read_optional_file(path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    if not path.exists():
        raise PipelineError(f"artifact file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def parse_verdict(content: str) -> str | None:
    match = VERDICT_RE.search(content)
    return match.group(1).strip() if match else None


def gate_result(stage_name: str, artifact_path: Path) -> tuple[bool, str | None]:
    expected = EXPECTED_VERDICTS[stage_name]
    verdict = parse_verdict(artifact_path.read_text(encoding="utf-8"))
    return verdict == expected, verdict


def command_report_verdict(report: dict[str, Any]) -> str | None:
    text = "\n".join([str(report.get("stdout") or ""), str(report.get("stderr") or "")])
    return parse_verdict(text)


def normalize_reviewer_role(value: str | None) -> str:
    role = str(value or "").strip().lower()
    return role if re.fullmatch(r"[a-z0-9_.-]+", role) else ""


def reviewer_role_from_command(command_text: str) -> str:
    match = REVIEWER_ROLE_ARG_RE.search(str(command_text or ""))
    if not match:
        return ""
    return normalize_reviewer_role(next((part for part in match.groups() if part), ""))


def reviewer_role_from_output(stdout: str, stderr: str) -> str:
    text = "\n".join([str(stdout or ""), str(stderr or "")])
    match = REVIEWER_ROLE_OUTPUT_RE.search(text)
    return normalize_reviewer_role(match.group(1) if match else "")


def first_regex_group(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return str(match.group(1) or "").strip() if match else ""


def first_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    decoder = json.JSONDecoder()
    for idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def extract_agent_runtime_refs(stdout: str, stderr: str) -> dict[str, str]:
    text = "\n".join([str(stdout or ""), str(stderr or "")])
    refs = {
        "session_id": first_regex_group(AGENT_SESSION_ID_RE, text),
        "run_id": first_regex_group(AGENT_RUN_ID_RE, text),
        "session_key": first_regex_group(AGENT_SESSION_KEY_RE, text),
    }

    payload = first_json_object(text)
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    agent_meta = meta.get("agentMeta", {}) if isinstance(meta, dict) else {}
    if isinstance(agent_meta, dict):
        refs["run_id"] = refs["run_id"] or str(agent_meta.get("runId", "")).strip()
        refs["session_id"] = refs["session_id"] or str(agent_meta.get("sessionId", "")).strip()
        refs["session_key"] = refs["session_key"] or str(agent_meta.get("sessionKey", "")).strip()

    return {key: value for key, value in refs.items() if value}


def reviewer_role_for_report(report: dict[str, Any]) -> str:
    explicit = normalize_reviewer_role(str(report.get("reviewer_role") or ""))
    if explicit:
        return explicit
    command_role = reviewer_role_from_command(str(report.get("command") or ""))
    if command_role:
        return command_role
    return reviewer_role_from_output(str(report.get("stdout") or ""), str(report.get("stderr") or ""))


def first_nonempty_regex_group(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(str(text or ""))
    if not match:
        return ""
    for group in match.groups():
        if group:
            return str(group).strip()
    return ""


def reviewer_model_from_command(command: str) -> str:
    return first_nonempty_regex_group(REVIEWER_MODEL_ARG_RE, command)


def reviewer_provider_from_command(command: str) -> str:
    return first_nonempty_regex_group(REVIEWER_PROVIDER_ARG_RE, command)


def reviewer_model_from_output(stdout: str, stderr: str) -> str:
    matches = REVIEWER_MODEL_OUTPUT_RE.findall("\n".join([str(stdout or ""), str(stderr or "")]))
    return str(matches[-1]).strip() if matches else ""


def reviewer_provider_from_output(stdout: str, stderr: str) -> str:
    matches = REVIEWER_PROVIDER_OUTPUT_RE.findall("\n".join([str(stdout or ""), str(stderr or "")]))
    return str(matches[-1]).strip() if matches else ""


def reviewer_model_key_for_report(report: dict[str, Any]) -> str:
    command = str(report.get("command") or "")
    stdout = str(report.get("stdout") or "")
    stderr = str(report.get("stderr") or "")
    provider = str(report.get("reviewer_provider") or "").strip() or reviewer_provider_from_output(stdout, stderr) or reviewer_provider_from_command(command) or "unknown-provider"
    model = str(report.get("reviewer_model") or "").strip() or reviewer_model_from_output(stdout, stderr) or reviewer_model_from_command(command)
    return f"{provider}/{model}" if model else ""


def valid_review_reports(stage_name: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = EXPECTED_VERDICTS[stage_name]
    return [item for item in reports if bool(item.get("ok")) and command_report_verdict(item) == expected]


def blocking_review_reports(stage_name: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = EXPECTED_VERDICTS[stage_name]
    return [item for item in reports if command_report_verdict(item) not in {None, expected}]


def dual_review_pass(stage_name: str, reports: list[dict[str, Any]]) -> bool:
    if blocking_review_reports(stage_name, reports):
        return False
    return bool(valid_review_reports(stage_name, reports))


REVIEW_BLOCKER_HINT_RE = re.compile(
    r"(?:Blocker|阻塞|修订要求|requires_revision|create_if_missing|target_files|verification_commands|compileall|content assertion|内容断言|manual acceptance|blocked_manual_acceptance_required|origin/main|git publish|2026-\d{2}-\d{2}\.md|not acceptable|未满足|缺少|不足|不合格|必须|应)",
    re.IGNORECASE,
)
SOLUTION_REVIEW_HARD_BLOCKER_RE = re.compile(r"(?!x)x")


def report_text(report: dict[str, Any]) -> str:
    return "\n".join(
        str(report.get(key) or "")
        for key in ("stdout", "stderr", "error")
        if str(report.get(key) or "").strip()
    )


def extract_review_blocker_lines(reports: list[dict[str, Any]], limit: int = 18) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for report in reports:
        role = reviewer_role_for_report(report) or "reviewer"
        for raw_line in report_text(report).splitlines():
            text = " ".join(raw_line.strip().strip("-* ").split())
            if not text or len(text) < 8 or not REVIEW_BLOCKER_HINT_RE.search(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            lines.append(f"- {role}: {clip_text(text, 260)}")
            if len(lines) >= limit:
                return lines
    return lines


def render_reviewer_discussion(stage_name: str, reports: list[dict[str, Any]], verdict: str) -> str:
    expected = EXPECTED_VERDICTS[stage_name]
    blocker_lines = extract_review_blocker_lines(blocking_review_reports(stage_name, reports) or reports)
    if not blocker_lines:
        blocker_lines = ["- none; reviewers did not report concrete blockers"]
    if verdict == expected:
        revision_plan = [
            "- No revision required; keep the accepted plan and proceed to the next gate.",
            "- Preserve all verification, safety, deployment, and publish gates in downstream stages.",
        ]
    elif stage_name == "solution_review":
        revision_plan = [
            "- Write the non-pass reasons into the review artifact, soft-gate artifact, and downstream implementation context.",
            "- Merge reviewer-a and reviewer-b blockers into one revised delivery_plan.json where possible; remaining plan-quality blockers become code_execution constraints.",
            "- Remove invalid target_files and add explicit create_if_missing rationale for every missing file that remains.",
            "- Replace template steps with file-level business actions, mapped tests, verification commands, release gates, and acceptance boundaries.",
            "- Continue to code_execution when no credential/secret, unclear-target, or failed-backup hard boundary remains; code_review verifies the implementation followed these absorbed constraints.",
        ]
    else:
        revision_plan = [
            "- Write the non-pass reasons into the review artifact and failure summary before stopping.",
            "- Merge reviewer-a and reviewer-b blockers into one revised delivery_plan.json instead of asking code_execution to discover the plan.",
            "- Remove invalid target_files and add explicit create_if_missing rationale for every missing file that remains.",
            "- Replace template steps with file-level business actions, mapped tests, verification commands, release gates, and acceptance boundaries.",
            "- Re-run solution_package and solution_review; do not enter code_execution until the merged blocker list is empty.",
        ]
    return "\n".join(
        [
            "## Reviewer Discussion And Joint Revision Plan",
            "- Round 1: reviewer-a checks scope, file targets, business behavior, tests, release gates, and safety boundaries.",
            "- Round 2: reviewer-b challenges reviewer-a with missing rationale, invalid paths, command-level gaps, docs/memory assertions, and acceptance closure.",
            "- Round 3: coordinator merges both outputs into one blocker list and one revised plan contract; unresolved concrete blockers keep the final verdict at `requires_revision`.",
            "",
            "### Joint Non-Pass Reasons",
            *blocker_lines,
            "",
            "### Complete Revision Plan",
            *revision_plan,
        ]
    )


def review_failure_detail(stage_name: str, reports: list[dict[str, Any]], default: str) -> str:
    blockers = extract_review_blocker_lines(blocking_review_reports(stage_name, reports) or reports, limit=10)
    if not blockers:
        return default
    return "\n".join([default, "", "Merged reviewer non-pass reasons:", *blockers])


def solution_review_hard_blocker_lines(reports: list[dict[str, Any]], limit: int = 10) -> list[str]:
    return []


CODE_REVIEW_SECRET_LEAK_RE = re.compile(
    r"(?:"
    r"(?:hard[- ]?coded|leak(?:s|ed|age)?|expos(?:e|es|ed|ure)?|"
    r"print(?:s|ed|ing)?|log(?:s|ged|ging)?|commit(?:s|ted|ting)?|"
    r"upload(?:s|ed|ing)?|dump(?:s|ed|ing)?|read(?:s|ing)?|show(?:s|ed|ing)?)"
    r".{0,100}"
    r"(?:api[-_ ]?key|secret|credential|password|private[-_ ]?key|cookie|oauth|auth[-_ ]?(?:token|json|state)|"
    r"凭证|密钥|密码|私钥|会话|token|cookie)"
    r"|"
    r"(?:api[-_ ]?key|secret|password|private[-_ ]?key|auth[-_ ]?token|cookie|credential|"
    r"密钥|密码|凭证|私钥)\s*[:=：]\s*(?!\[REDACTED\]|<redacted>|REDACTED|xxx|\*{3,}|None\b|null\b)[^\s`'\"<>]{8,}"
    r")",
    re.IGNORECASE,
)

CODE_REVIEW_SECRET_CONTEXT_ONLY_RE = re.compile(
    r"(?:secret\s+scan|credential\s+scan|安全扫描|扫描|断言|assertion|"
    r"forbidden|forbidden_targets?|排除|禁止目标|安全边界|safety\s+contract|"
    r"do\s+not|must\s+not|without|\bno\b|\bnot\b|不得|不要|不能|禁止|不允许|不读取|不打印|不泄露|未读取|未打印|未泄露|未提交|未上传)",
    re.IGNORECASE,
)

CODE_REVIEW_SECRET_NEGATIVE_SCAN_RE = re.compile(
    r"(?:"
    r"(?:secret\s+scan|credential\s+scan|安全扫描|扫描|commit\s+diff|diff|新增行|added[- ]?lines?)"
    r".{0,180}"
    r"(?:no|none|without|not\s+(?:found|detected|present)|clean|passed|pass|"
    r"无|未发现|没有|未检测到|不存在|不含|不包含)"
    r".{0,140}"
    r"(?:structural|结构化|credential|credentials|secret|secrets|token|tokens|api[-_ ]?key|password|"
    r"private[-_ ]?key|cookie|auth|assignment|leak|泄露|赋值|证据|凭证|密钥|密码|私钥)"
    r"|"
    r"(?:no|none|without|not\s+(?:found|detected|present)|无|未发现|没有|未检测到|不存在|不含|不包含)"
    r".{0,120}"
    r"(?:structural|结构化)"
    r".{0,120}"
    r"(?:credential|credentials|secret|secrets|token|tokens|api[-_ ]?key|password|assignment|赋值|凭证|密钥)"
    r")",
    re.IGNORECASE,
)


def code_review_secret_leak_blocker_lines(reports: list[dict[str, Any]], limit: int = 10) -> list[str]:
    """Return only concrete credential/password leakage blockers from code review.

    Code-review artifacts contain a lot of safety-contract prose ("secret scan",
    "do not read credentials", forbidden target examples).  Under the simplified
    user-approved gate policy, that prose must not trigger rollback.  We only
    keep positive evidence that the implementation actually leaks, prints,
    commits, uploads, or hardcodes credential material, or contains an obvious
    credential assignment value.
    """
    lines: list[str] = []
    seen: set[str] = set()
    for report in blocking_review_reports("code_review", reports) or reports:
        role = reviewer_role_for_report(report) or "reviewer"
        for raw_line in scrub_negated_risk_lines(report_text(report)).splitlines():
            text = " ".join(raw_line.strip().strip("-* ").split())
            if not text or len(text) < 8:
                continue
            if CODE_REVIEW_SECRET_NEGATIVE_SCAN_RE.search(text):
                continue
            if CODE_REVIEW_SECRET_CONTEXT_ONLY_RE.search(text) and not CODE_REVIEW_SECRET_LEAK_RE.search(text):
                continue
            if not CODE_REVIEW_SECRET_LEAK_RE.search(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            lines.append(f"- {role}: {clip_text(text, 260)}")
            if len(lines) >= limit:
                return lines
    return lines


def solution_review_can_soft_continue(reports: list[dict[str, Any]], parsed_verdict: str | None) -> bool:
    if parsed_verdict == EXPECTED_VERDICTS["solution_review"]:
        return False
    if not reports:
        return False
    return not solution_review_hard_blocker_lines(reports)


def render_solution_review_soft_gate(reports: list[dict[str, Any]], parsed_verdict: str | None) -> str:
    blockers = extract_review_blocker_lines(blocking_review_reports("solution_review", reports) or reports, limit=14)
    if not blockers:
        blockers = ["- no concrete reviewer blocker lines were emitted; preserve the non-pass artifact as implementation context."]
    hard_blockers = solution_review_hard_blocker_lines(reports)
    return "\n".join(
        [
            "# Solution Review Soft Gate",
            "",
            f"- Parsed verdict: {parsed_verdict or 'missing'}",
            "- Decision: soft_continue",
            "- Reason: solution review plan-quality blockers are converted into implementation notes; user-approved simplified workflow proceeds when the requirement is clear.",
            "- Hard boundary: no solution-review content is a permanent workflow stop; reviewer findings must loop back into a revised plan until review passes. Git publish still blocks staged diffs with real password/token/cookie/private-key material.",
            "",
            "## Absorbed Reviewer Blockers",
            *blockers,
            "",
            "## Hard Blockers Detected",
            *(hard_blockers or ["- none"]),
        ]
    )


def build_solution_review_repair_context(soft_gate_text: str, solution_review_text: str) -> str:
    """Context used to regenerate delivery_plan after solution_review discussion.

    The reviewer discussion is not just a message to humans: non-hard solution
    blockers must be absorbed into a revised plan before code_execution.
    """
    return "\n".join(
        part
        for part in (
            "# Solution Review Absorbed Revision Context",
            soft_gate_text,
            "## Original Solution Review",
            read_optional_file(Path(solution_review_text), str(solution_review_text)) if isinstance(solution_review_text, (str, Path)) else str(solution_review_text or ""),
        )
        if str(part or "").strip()
    )


def render_dual_ai_review(stage_name: str, reports: list[dict[str, Any]], verdict: str) -> str:
    expected = EXPECTED_VERDICTS[stage_name]
    roles = [reviewer_role_for_report(item) or "missing" for item in reports]
    model_keys = [reviewer_model_key_for_report(item) or "missing" for item in reports]
    commands = [str(item.get("command") or "").strip() for item in reports]
    distinct_commands = len({command for command in commands if command}) == len(commands) if commands else False
    valid_reports = valid_review_reports(stage_name, reports)
    concrete_blockers = blocking_review_reports(stage_name, reports)
    valid_model_keys = [reviewer_model_key_for_report(item) or "missing" for item in valid_reports]
    valid_distinct_models = len(valid_model_keys) >= 2 and len(set(valid_model_keys)) >= 2 and "missing" not in set(valid_model_keys)
    runtime_failures = [
        item
        for item in reports
        if item not in valid_reports
        and item not in concrete_blockers
        and (not item.get("ok") or command_report_verdict(item) is None)
    ]
    blocker_reports = [
        f"- {reviewer_role_for_report(item) or 'missing'} / {reviewer_model_key_for_report(item) or 'missing'}: {command_report_verdict(item) or 'missing_verdict'}"
        for item in concrete_blockers
    ]
    runtime_failure_text = "\n".join(
        f"- {reviewer_role_for_report(item) or 'missing'} / {reviewer_model_key_for_report(item) or 'missing'}: runtime_or_model_failure; returncode={item.get('returncode')}; error={clip_text(str(item.get('error') or item.get('stderr') or ''), 180)}"
        for item in runtime_failures
    ) or "- none"
    blocker_text = "\n".join(blocker_reports) if blocker_reports else "- none; no concrete reviewer blocker remains"
    if concrete_blockers:
        review_mode = "blocked_concrete_reviewers"
    elif valid_distinct_models:
        review_mode = "independent_multi_model"
    elif valid_reports:
        review_mode = "degraded_single_valid"
    else:
        review_mode = "blocked_missing_valid_reviewer"
    pass_policy = (
        "Prefer two independent reviewer outputs with distinct provider/model identity. If one reviewer command fails "
        "because its provider/model is unavailable or does not emit a verdict, continue when at least one reviewer "
        "returns the expected verdict and no valid reviewer reports a concrete blocker."
    )
    return dedent(
        f"""
        # {stage_name.replace('_', ' ').title()}

        Final verdict: {verdict}
        Confidence: {"high" if verdict == expected else "medium"}

        ## Dual AI Contract
        - Expected verdict: {expected}
        - Reviewer-A evidence: {"present" if "reviewer-a" in roles else "missing"}
        - Reviewer-B evidence: {"present" if "reviewer-b" in roles else "missing"}
        - Reviewer roles: {", ".join(roles) if roles else "missing"}
        - Reviewer models: {", ".join(model_keys) if model_keys else "missing"}
        - Distinct reviewer models: {str(valid_distinct_models).lower()}
        - Distinct commands: {str(distinct_commands).lower()}
        - Independent command reports: {len(reports)}
        - Valid reviewer outputs: {len(valid_reports)}
        - Review gate mode: {review_mode}
        - Pass policy: {pass_policy}

        ## Merged Reviewer Consensus
        - Review mode: prefer independent multi-model review followed by blocker merge; degrade only for provider/model runtime failures.
        - No artificial task-splitting granularity gate is allowed; reviewers judge the whole accepted requirement.
        - If any valid reviewer raises a concrete blocker, requirements_review and code_review remain hard gates. solution_review treats plan-quality and guarded high-permission blockers as soft constraints when no credential/secret, unclear-target, or failed-backup hard boundary is present, and passes them to code_execution and later code_review.
        - Remaining blockers:
        {blocker_text}
        - Non-blocking reviewer runtime/model failures:
        {runtime_failure_text}

        {render_reviewer_discussion(stage_name, reports, verdict)}

        {command_markdown("Dual AI Review Commands", reports)}
        """
    )


def consensus_review(review_type: str, verdict: str, requirement: str) -> str:
    return dedent(
        f"""
        # {review_type.replace('_', ' ').title()}

        ## Reviewer-A independent opinion
        - Conclusion: {verdict}
        - Key finding: The package is testable and has explicit acceptance gates.

        ## Reviewer-B challenge
        - Conclusion: {verdict}
        - Challenge: Prefer existing runtime skills and deterministic gates before adding new services.

        ## Consensus discussion
        - Round 1: Reviewer-A checks scope and artifact completeness.
        - Round 2: Reviewer-B checks reuse, failure routing, and missing external research.
        - Round 3+: Reviewers merge all blocking and non-blocking findings, revise the plan, and continue until no reviewer has a remaining blocker.

        ## Joint conclusion
        Final verdict: {verdict}
        Confidence: high
        Dissent: false
        Rewrite targets:
        - requirement package

        ## Requirement excerpt
        {requirement[:800]}
        """
    )


def render_run_meta(config: PipelineConfig, run_id: str, requirement: str, runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "created_at": utc_now(),
        "dry_run": config.dry_run,
        "runtime_context": runtime,
        "source_urls": list(config.source_urls),
        "max_repair_loops": config.max_repair_loops,
        "agent_workspace_strategy": "git-worktree",
        "agent_workspace_root": str(config.agent_workspace_root) if config.agent_workspace_root else "",
        "code_workspace_diff_policy": "always-apply",
        "code_agent": normalize_code_agent(config.code_agent),
        "requirement_preview": requirement[:240],
    }


def render_context_snapshot(requirement: str, runtime: dict[str, Any]) -> str:
    return dedent(
        f"""
        # Context Snapshot

        ## User Requirement
        {requirement}

        ## Runtime
        - Host: {runtime["host"]}
        - Runtime home: {runtime["runtime_home"]}
        - State dir: {runtime["state_dir"]}

        ## Repository Boundary
        - The runner records orchestration artifacts only.
        - Product code changes must be performed by coding agents or by the coordinator.
        - Host-specific details stay inside the runtime adapter.
        """
    )


def run_git_probe(repo: Path, args: list[str], *, timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive for missing git/timeouts
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": redact_remote_urls(proc.stdout.strip()),
        "stderr": redact_remote_urls(proc.stderr.strip()),
    }


def redact_remote_urls(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(https?://)([^/@\s]+)@", r"\1[REDACTED]@", value)
    value = re.sub(r"(://)([^:/@\s]+):([^/@\s]+)@", r"\1[REDACTED]@", value)
    return value


def git_lines(result: dict[str, Any], limit: int = 40) -> list[str]:
    lines = []
    for line in str(result.get("stdout") or "").splitlines():
        text = line.strip()
        if text:
            lines.append(text)
    return lines[:limit]


def collect_git_repository_context(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    inside = run_git_probe(repo, ["rev-parse", "--is-inside-work-tree"])
    if not inside.get("ok") or str(inside.get("stdout") or "").strip() != "true":
        return {"is_git_repository": False, "repo": str(repo), "error": inside.get("stderr") or inside.get("stdout") or "not a git worktree"}

    remotes = run_git_probe(repo, ["remote", "-v"])
    fetch = {"skipped": True, "reason": "no git remotes configured"}
    if git_lines(remotes):
        fetch = run_git_probe(repo, ["fetch", "--all", "--prune"], timeout=60)
    return {
        "is_git_repository": True,
        "repo": str(repo),
        "fetch_all_prune": fetch,
        "current_branch": git_lines(run_git_probe(repo, ["branch", "--show-current"]), 1),
        "head": git_lines(run_git_probe(repo, ["rev-parse", "--short", "HEAD"]), 1),
        "status_short_branch": git_lines(run_git_probe(repo, ["status", "--short", "--branch"]), 80),
        "remotes": git_lines(remotes, 40),
        "local_branches": git_lines(run_git_probe(repo, ["branch", "--list", "--format=%(refname:short) %(objectname:short) %(committerdate:short) %(subject)"]), 80),
        "remote_branches": git_lines(run_git_probe(repo, ["branch", "-r", "--format=%(refname:short) %(objectname:short) %(committerdate:short) %(subject)"]), 120),
    }


def render_git_repository_context(snapshot: dict[str, Any]) -> str:
    if not snapshot.get("is_git_repository"):
        return f"# Git Repository Context\n\n- is_git_repository: false\n- repo: `{snapshot.get('repo', '')}`\n- error: {snapshot.get('error', '')}\n"
    fetch = snapshot.get("fetch_all_prune") if isinstance(snapshot.get("fetch_all_prune"), dict) else {}
    def items(name: str) -> str:
        values = snapshot.get(name) if isinstance(snapshot.get(name), list) else []
        return "\n".join(f"- `{item}`" for item in values) or "- none"
    return dedent(
        f"""
        # Git Repository Context

        ## Project-agent Git Update
        - repo: `{snapshot.get('repo', '')}`
        - fetch_all_prune: `{fetch.get('ok', False)}`
        - fetch_returncode: `{fetch.get('returncode', 'skipped')}`
        - fetch_note: `{fetch.get('stderr') or fetch.get('reason') or 'ok'}`

        ## Current Worktree
        - current_branch: `{', '.join(snapshot.get('current_branch') or []) or 'unknown'}`
        - head: `{', '.join(snapshot.get('head') or []) or 'unknown'}`

        ## Status
        {items('status_short_branch')}

        ## Remotes
        {items('remotes')}

        ## Local Branches
        {items('local_branches')}

        ## Remote Branches
        {items('remote_branches')}

        ## Project-agent Rule
        Project-agent must consider the refreshed remote refs, local branches, remote branches, current HEAD, and dirty worktree state before locating current logic or recommending modifications. It may fetch refs, but must not merge, reset, checkout, stash, or discard changes without explicit human approval.
        """
    )


def project_memory_dir(config: PipelineConfig) -> Path:
    memory_root = config.project_memory_root
    if (
        memory_root == Path(".workflow/project-memory")
        and config.workspace_root != Path(".workflow/pipeline-runs")
    ):
        memory_root = (
            config.workspace_root.parent / "project-memory"
            if config.workspace_root.name in {"pipeline-runs", "runs"}
            else config.workspace_root / "project-memory"
        )
    return memory_root / slugify(config.project_key)


def bootstrap_project_memory_module(config: PipelineConfig, requirement: str, runtime: dict[str, Any]) -> Path:
    memory_dir = project_memory_dir(config)
    memory_dir.mkdir(parents=True, exist_ok=True)

    write_text_if_missing(
        memory_dir / "PROJECT_PROFILE.md",
        dedent(
            f"""
            # Project Profile

            ## Project Key
            {config.project_key}

            ## Purpose
            TODO: describe the product goal, core modules, runtime entrypoints, and deployment boundary.

            ## Runtime Hosts
            - preferred: {runtime["host"]}
            - runtime_home: {runtime["runtime_home"]}

            ## Current Requirement Seed
            {requirement[:800]}
            """
        ),
    )
    write_text_if_missing(
        memory_dir / "DECISIONS.md",
        dedent(
            """
            # Decisions

            Add durable project decisions here. Each entry should include date,
            decision, rejected alternatives, and verification evidence.
            """
        ),
    )
    write_text_if_missing(
        memory_dir / "DELIVERY_RULES.md",
        dedent(
            """
            # Delivery Rules

            - Read project memory before solution design or code execution.
            - Prefer existing module boundaries before introducing new paths.
            - Record the intended change location before editing.
            - If the best location is unclear, stop at requirements or solution revision.
            """
        ),
    )
    write_json_if_missing(
        memory_dir / "API_REGISTRY.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "providers": [],
        },
    )
    write_json_if_missing(
        memory_dir / "SOURCE_REGISTRY.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "sources": [],
        },
    )
    write_json_if_missing(
        memory_dir / "IMPACT_MAP.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "modules": [],
            "last_indexed_at": "",
            "note": "Populate module, owner, entrypoint, tests, docs, and related files before live coding.",
        },
    )
    write_json_if_missing(
        memory_dir / "RETRIEVAL_MANIFEST.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_key": config.project_key,
            "default_strategy": "hybrid_local_first",
            "required_indexes": [
                "PROJECT_PROFILE.md",
                "DECISIONS.md",
                "DELIVERY_RULES.md",
                "API_REGISTRY.json",
                "SOURCE_REGISTRY.json",
                "IMPACT_MAP.json",
            ],
            "retrieval_order": [
                "structured project memory",
                "keyword and symbol search",
                "semantic/vector search when configured",
                "GraphRAG only for cross-module or multi-hop architecture questions",
            ],
            "optional_backends": {
                "vector_store": "OpenAI vector stores / file_search or compatible local vector DB",
                "graph_rag": "Microsoft GraphRAG or graph-backed retrieval for global architecture questions",
                "mcp": "MCP resources/tools for external systems and runtime state",
            },
        },
    )
    return memory_dir


def render_project_memory_context(config: PipelineConfig, requirement: str, runtime: dict[str, Any]) -> str:
    memory_dir = bootstrap_project_memory_module(config, requirement, runtime)
    file_lines = "\n".join(
        f"- `{name}`: {purpose}" for name, purpose in sorted(PROJECT_MEMORY_FILES.items())
    )
    return dedent(
        f"""
        # Project Memory Context

        ## Memory Module
        - Project key: {config.project_key}
        - Memory dir: {memory_dir}
        - Runtime host: {runtime["host"]}

        ## Required Files
        {file_lines}

        ## Retrieval Gate
        Before solution design and before coding, project-agent must identify:
        - existing module or file most likely to own the change
        - related tests and docs that must move with the change
        - prior decisions that constrain the implementation
        - refreshed git context: current branch, HEAD, dirty state, remotes, local branches, and remote branches from `git_repository_context.md`
        - source/API registry entries that require current external checks

        ## Retrieval Strategy
        - Default: hybrid local-first retrieval using structured memory, keyword search, and symbol/file mapping.
        - Optional vector RAG: use when project docs exceed the prompt budget or semantic recall is needed.
        - Optional GraphRAG: use only for cross-module, multi-hop, or architecture-level questions where file-level search is not enough.
        - MCP resources/tools may expose external systems, but must respect project/workspace boundaries.

        ## Anti Local-Optimum Rule
        Coding is blocked until `IMPACT_MAP.json` or this run's context snapshot names the likely change location.
        If no reliable location exists, route back to `requirements_package` or `solution_package` instead of guessing.
        """
    )


def render_research_report(
    config: PipelineConfig,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if config.research_report_file:
        return read_optional_file(config.research_report_file, "")

    source_lines = "\n".join(f"- {url}" for url in config.source_urls) or "- No live source URLs supplied to runner."
    mode = "dry-run simulated research" if config.dry_run else "live research evidence required"
    command_section = command_markdown("Research Commands", command_reports) if command_reports else ""
    return dedent(
        f"""
        # External Research Report

        ## Status
        - Mode: {mode}
        - Gate rule: implementation cannot rely only on memory when external SDKs, APIs, or existing solutions may exist.

        ## Sources Checked Or Required
        {source_lines}

        ## Reuse Decision
        - Prefer official SDKs, existing runtime skills, and mature open-source implementations before writing new code.
        - If a source changes the requirement or solution, route back to the requirements or solution package before coding.

        ## Existing Code Candidates
        - dual-ai-review templates and review gate artifacts
        - failure tracker CLI contract
        - project memory writer/injector contract

        {command_section}
        """
    )


def render_requirements(requirement: str) -> str:
    return dedent(
        f"""
        # Requirement Package

        ## Original Requirement
        {requirement}

        ## Normalized Requirement
        Deliver the user request above exactly as written, preserving its target
        files, non-goals, safety boundaries, deployment expectations, and publish
        requirements. If later discussion narrows or corrects the scope, the
        refined requirement must stay tied to this original request instead of
        falling back to a generic pipeline template.

        ## Scope Guard
        - Keep implementation scoped to the original request and the accepted
          requirements discussion.
        - Do not continue unrelated feature slices when the request is about
          workflow repair, deployment, cleanup, documentation, or diagnosis.
        - If the request names files, services, run ids, artifacts, dirty
          worktree entries, or safety constraints, treat them as acceptance inputs.

        ## Acceptance Criteria
        - Requirements review must return ready_for_solution.
        - The requirement package and discussion must preserve the user-specific
          objective, explicit non-goals, and safety constraints.
        - Project memory context must name likely change locations or force revision.
        - Solution review must return ready_for_implement.
        - Verification must pass before acceptance.
        - Code review must return pass.
        - Acceptance failures must be routed to the correct upstream stage.
        """
    )


def render_requirements_discussion(requirement: str) -> str:
    return dedent(
        f"""
        # Dual-Agent Requirement Discussion

        ## Goal
        Two AI roles must actively discuss the requirement before the final requirement review:
        - `project-agent`: product/project analyst, owns user intent, scope, acceptance criteria, and delivery constraints.
        - `reviewer`: independent challenger, owns ambiguity, hidden risks, missing evidence, and testability.

        ## Original Requirement
        {requirement}

        ## Discussion Transcript Template

        ### Round 1 - project-agent: intent and first draft
        - Restate the user goal in concrete, testable language.
        - Identify target users, entry points, outputs, constraints, and non-goals.
        - Draft acceptance criteria and required evidence.

        ### Round 2 - reviewer: challenge and gap finding
        - Challenge unclear terms, missing data contracts, unsafe assumptions, and unsupported external facts.
        - Ask whether internet or official documentation research is required before implementation.
        - Identify risks that would make the requirement incomplete or unsafe.

        ### Round 3 - project-agent: revised requirement
        - Answer reviewer challenges.
        - Add missing scope boundaries, explicit non-goals, validation steps, and rollback/verification expectations.
        - Convert the discussion into a coherent requirement document outline.

        ### Round 4 - reviewer: final tightening
        - Confirm the requirement is specific, testable, bounded, and implementable.
        - List any remaining open questions that must block coding.
        - If no blocking questions remain, mark the requirement ready for formal review.

        ## Solution Review Readiness Discussion
        Because `solution_review` feeds implementation constraints before code execution, the discussion must
        pre-negotiate its contract instead of discovering basic gaps later:
        - Name `must_change_targets` separately from `read_only_sources`, `reference_patterns`, `runtime_contracts`, `api_contracts`, and `forbidden_targets`.
        - `target_files` in the later delivery plan may contain only concrete repo-relative files that the implementer is expected to create or modify.
        - Files mentioned as read-only sources, inspect-only inputs, reference examples, or API/runtime/data contracts must not be promoted to `target_files`.
        - Credential material, unclear destructive targets, backup/audit requirements, high-permission runtime operations, and dirty/behind containment must be discussed before solution generation.
        - Verification expectations must be command-level, deterministic, and include tests, compileall, diff check, safety scan, smoke checks, docs/memory writeback, and publish containment when applicable.

        ## Final Requirement Document Contract
        The final `requirements.md` / requirement package must include:
        - Problem statement
        - Users and entry points
        - In-scope behavior
        - Out-of-scope behavior
        - Data/API/config contracts
        - External research evidence needed or supplied
        - Acceptance criteria
        - Test and verification plan
        - Security/credential/production boundaries
        - Open questions, with coding blocked if any are material
        """
    )


def render_resolved_requirement(requirement: str, artifacts: dict[str, str]) -> str:
    discussion = read_optional_file(Path(artifacts.get("requirements_discussion", "")), "")
    review = read_optional_file(Path(artifacts.get("requirements_review", "")), "")
    return dedent(
        f"""
        # Resolved Requirement

        ## Original Requirement
        {requirement}

        ## Accepted Requirement Source
        The accepted implementation scope is the original requirement plus the
        completed requirements discussion and requirements review below. Downstream
        stages must use this artifact as the handoff contract and must not fall
        back to a generic pipeline template.

        ## Requirements Discussion
        {discussion}

        ## Requirements Review
        {review}
        """
    )


# Business-operation risk gates were removed by user direction.  The pipeline no
# longer scans plans for business-operation keywords before implementation.  Quality
# enforcement now happens through the developer -> verification -> code_review
# loop, and upload containment is handled by git_publish secret/password scans.
HARD_STOP_PLAN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = ()
GUARDED_OPERATION_PLAN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = ()
HIGH_RISK_PLAN_PATTERNS = HARD_STOP_PLAN_PATTERNS
MEDIUM_RISK_PLAN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = ()


def scrub_negated_risk_lines(text: str) -> str:
    return str(text or "")


def pre_execution_plan_scan_text(delivery_plan: dict[str, Any]) -> str:
    """Return only plan fields that describe intended work, not generated gates/policies."""
    implementation_steps = delivery_plan.get("implementation_steps")
    if not isinstance(implementation_steps, list):
        implementation_steps = []
    target_files = delivery_plan.get("target_files")
    if not isinstance(target_files, list):
        target_files = []
    scan_payload = {
        "target_files": target_files,
        "implementation_steps": implementation_steps,
    }
    return json.dumps(scan_payload, ensure_ascii=False, indent=2)


def clean_pre_execution_artifact_text(text: str) -> str:
    return str(text or "")


def unique_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            result.append(label)
    return result


def delivery_plan_targets(delivery_plan: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for key in ("target_files", "must_change_targets", "entry_points"):
        items = delivery_plan.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            path = item.get("path") if isinstance(item, dict) else item
            if str(path or "").strip():
                targets.append(str(path).strip())
    return unique_labels(targets)


def assess_pre_execution_risk(requirement: str, delivery_plan: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "pre-execution-risk/v2",
        "risk_level": "low",
        "human_confirmation_required": False,
        "hard_stop_required": False,
        "execution_decision": "auto_execute",
        "high_risk_reasons": [],
        "guarded_action_reasons": [],
        "hard_stop_reasons": [],
        "medium_risk_reasons": [],
        "low_risk_reason": "Business-operation gates are disabled; continue to development, verification, review, and git publish.",
        "group_publish_required": True,
    }


def apply_human_risk_confirmation(risk: dict[str, Any], config: PipelineConfig) -> dict[str, Any]:
    """Carry legacy caller approval for audit only; it no longer changes routing."""
    payload = dict(risk)
    confirmed = bool(config.human_risk_confirmed)
    payload["human_confirmation_confirmed"] = confirmed
    if confirmed:
        payload["confirmation_source"] = "human_risk_confirmed_flag"
        payload["confirmed_at"] = utc_now()
    return payload


def render_group_plan_publish(requirement: str, artifacts: dict[str, str], delivery_plan: dict[str, Any], risk: dict[str, Any]) -> str:
    research = read_optional_file(Path(artifacts.get("external_research", "")), "")
    memory = read_optional_file(Path(artifacts.get("project_memory_context", "")), "")
    discussion = read_optional_file(Path(artifacts.get("requirements_discussion", "")), "")
    requirements_review = read_optional_file(Path(artifacts.get("requirements_review", "")), "")
    solution_review = read_optional_file(Path(artifacts.get("solution_review", "")), "")
    graphify_context = read_optional_file(Path(artifacts.get("graphify_context", "")), "")
    graphify_scope = read_optional_file(Path(artifacts.get("graphify_scope_validation", "")), "")
    target_files = "\n".join(f"- `{item.get('path')}`" for item in delivery_plan.get("target_files", [])[:40]) or "- 待 code agent 基于项目记忆继续定位"
    verification_commands = "\n".join(f"- `{item.get('command')}`" for item in delivery_plan.get("verification_commands", [])[:40]) or "- 待 tester/code agent 补齐"
    return dedent(
        f"""
        # 群回传执行方案

        ## 原始需求
        {requirement}

        ## 已收集上下文
        - 项目记忆/文档：已读取并写入 `project_memory_context.md`，project-agent 必须据此定位最可能修改位置。
        - 外部调研：已写入 `research_report.md`；如无需联网，web-agent 必须说明 `NO_EXTERNAL_LOOKUP_NEEDED` 与原因。
        - 需求讨论：已写入 `requirements_discussion.md`，至少包含 project-agent 与 reviewer 的多轮讨论。
        - 双 reviewer 审查：已写入 `requirements_review.md` 与 `solution_review.md`，reviewer-a/reviewer-b 必须独立给出结论。
        - graphify 项目图谱：已写入 `graphify_context.md`，作为软上下文；solution 后校验写入 `graphify_scope_validation.md`。

        ## 目标文件
        {target_files}

        ## 验收命令
        {verification_commands}

        ## 风险判断
        - risk_level: `{risk.get('risk_level')}`
        - execution_decision: `{risk.get('execution_decision')}`
        - hard_stop_required: `{risk.get('hard_stop_required')}`
        - human_confirmation_confirmed: `{risk.get('human_confirmation_confirmed', False)}`
        - high_risk_reasons: `none`
        - guarded_action_reasons: `none`
        - medium_risk_reasons: `{', '.join(risk.get('medium_risk_reasons') or []) or 'none'}`

        ## 门禁策略
        - 业务操作关键词不再由 workflow 风险门禁拦截，也不再生成单独的执行保护 artifact。
        - 开发、验证、代码审核和 Git 发布必须形成回流闭环；失败原因会写入对应 artifact 并回到开发修复。
        - Git 发布阶段保留 staged diff 的密钥、密码、Token、Cookie、私钥扫描；命中真实敏感信息时阻塞到 `fix_git_publish`。

        ## 执行规则
        - 本方案作为群回传摘要与证据 artifact，随后自动进入 code_execution。
        - 测试、审核、部署或 git publish 任一失败时，必须生成失败摘要，记录失败阶段、命令、证据目录和下一步修复动作，再回流修复。

        ## 摘要引用
        - project_memory_context 摘要长度: {len(memory)} 字符
        - research_report 摘要长度: {len(research)} 字符
        - requirements_discussion 摘要长度: {len(discussion)} 字符
        - requirements_review 摘要长度: {len(requirements_review)} 字符
        - solution_review 摘要长度: {len(solution_review)} 字符
        - graphify_context 摘要长度: {len(graphify_context)} 字符
        - graphify_scope_validation 摘要长度: {len(graphify_scope)} 字符
        """
    )


def render_failure_summary(stage_name: str, next_action: str, detail: str, artifact: str | None, verdict: str | None, run_dir: Path) -> str:
    artifact_path = run_dir / artifact if artifact else None
    artifact_text = read_optional_file(artifact_path, "") if artifact_path and artifact_path.exists() else ""
    excerpt = artifact_text[:3000] if artifact_text else "无"
    return dedent(
        f"""
        # 失败步骤群回传摘要

        ## 失败阶段
        - stage: `{stage_name}`
        - verdict: `{verdict or 'unknown'}`
        - next_action: `{next_action}`

        ## 失败原因
        {detail}

        ## 证据目录
        `{run_dir}`

        ## 关联 artifact
        `{artifact or 'not_applicable'}`

        ## 失败内容摘录
        ```text
        {excerpt}
        ```

        ## 处理规则
        - 低/中风险修复：总结后自动回流给对应 agent。
        - 高风险或需要人工决策：把本摘要发到群里等待确认。
        - 修复后必须重新测试、审核；部署/git publish 失败也要记录并回流。
        """
    )


def normalize_plan_path_token(value: str) -> str:
    path = str(value or "").strip().strip(",;:()[]{}<>\"'").rstrip(".")
    if not path:
        return ""
    path = path.replace("\\", "/")
    return path


def plan_path_rejection_reason(path: str) -> str:
    if not path:
        return "empty_path"
    if path.lstrip().startswith("#") or re.search(r"\s+\[(?:behind|ahead|gone|diverged)\b", path, re.IGNORECASE):
        return "git_status_not_file_path"
    if re.match(r"^(?:origin|upstream|refs/remotes)/[A-Za-z0-9_.-]+$", path):
        return "git_ref_not_file_path"
    name = Path(path).name
    if PSEUDO_TARGET_PATH_RE.fullmatch(path.replace("\\", "/")):
        return "runtime_contract_not_file_path"
    if name in PIPELINE_ARTIFACT_FILES:
        return "pipeline_artifact_file"
    if re.search(r"\s", path):
        return "natural_language_not_file_path"
    if re.search(r"\.(?:py|md|json|json5|ya?ml|toml|js|ts|html|css|sh):\d+(?:-\d+)?\b", path, re.IGNORECASE):
        return "file_line_reference_not_target"
    if SENSITIVE_TARGET_BASENAME_RE.fullmatch(name):
        return "credential_or_auth_target_file"
    if re.search(r"(?:credential|credentials|auth|secret|cookie|oauth|api[-_ ]?key|private[-_ ]?key|凭证|密钥|私钥)", path, re.IGNORECASE):
        return "credential_or_auth_natural_language_not_target"
    if not PLAN_PATH_RE.search(path):
        return "not_repository_plan_path"
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if any(PLAN_PATH_RE.search(part) for part in parts[:-1]):
        return "combined_file_paths"
    # Delivery plans are repository-relative contracts.  Absolute-looking paths
    # such as /api/foo.py are often copied from API routes or reviewer examples;
    # keeping them as target_files sends implementers outside the repo layout.
    if path.endswith("/"):
        return "directory_path_not_file"
    if re.search(r"\b(?:https?|ws|wss)://", path, re.IGNORECASE):
        return "url_or_command_not_file_path"
    if re.match(r"^(?:curl|pytest|python|python3|git|grep|rg|find|npm|pnpm|yarn)\b", path.strip(), re.IGNORECASE):
        return "command_not_file_path"
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:/", path):
        return "external_or_runtime_absolute_path"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", Path(path).name) and "/" not in path.replace("\\", "/"):
        return "root_date_file_not_allowed"
    return ""


def clean_plan_path(value: str) -> str:
    path = normalize_plan_path_token(value)
    if plan_path_rejection_reason(path):
        return ""
    return path


def iter_plan_path_tokens(text: str) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen_raw: set[str] = set()
    for match in PATH_TOKEN_RE.finditer(str(text or "")):
        raw = next((group for group in match.groups() if group), "")
        path = normalize_plan_path_token(raw)
        candidates.append((raw, path, plan_path_rejection_reason(path)))
        if raw:
            seen_raw.add(raw)
    for match in UNICODE_PATH_TOKEN_RE.finditer(str(text or "")):
        raw = match.group(1)
        if raw in seen_raw:
            continue
        path = normalize_plan_path_token(raw)
        candidates.append((raw, path, plan_path_rejection_reason(path)))
    return candidates


def extract_plan_paths(*texts: str, limit: int = 24) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for _raw, candidate, rejection_reason in iter_plan_path_tokens(text):
            if rejection_reason:
                continue
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            paths.append(candidate)
            if len(paths) >= limit:
                return paths
    return paths


def path_context_segments(text: str) -> list[str]:
    return [segment.strip() for segment in PATH_CONTEXT_SPLIT_RE.split(str(text or "")) if segment.strip()]


def is_explicit_target_path_context(text: str) -> bool:
    value = str(text or "")
    return bool(
        re.search(
            r"(?:target_files?|目标文件|目标路径|至少检查|按需修改|检查/按需修改|repo-relative|仓库真实|真实路径|writeback|写回)",
            value,
            re.IGNORECASE,
        )
    )


def is_negated_path_context(text: str) -> bool:
    value = str(text or "")
    if is_explicit_target_path_context(value) and not STRONG_NEGATED_PATH_CONTEXT_RE.search(value):
        return False
    return bool(NEGATED_PATH_CONTEXT_RE.search(value))


def is_inspect_only_path_context(text: str) -> bool:
    """Return true when a path is mentioned as source/reference, not an edit target."""
    value = str(text or "")
    if not INSPECT_ONLY_PATH_CONTEXT_RE.search(value):
        return False
    return not MUST_CHANGE_PATH_CONTEXT_RE.search(value)


def classify_non_target_path_context(text: str) -> str:
    value = str(text or "")
    # Explicit readiness labels such as read_only_sources/reference_patterns are
    # stronger than nearby negated words like "do not modify".  A segment that
    # says "must_change_targets" does not match these patterns, so true targets
    # remain actionable.
    lowered = value.lower()
    if re.search(r"\b(?:inspect[-_ ]?only|conditional\s+(?:edit|source)|safety\s+contract\s+reference)\b|(?:按需检查|检查用|条件修改|除非测试发现缺口)", value, re.IGNORECASE):
        return "inspect_only_context"
    if REFERENCE_PATTERN_CONTEXT_RE.search(value):
        return "reference_pattern"
    if READ_ONLY_SOURCE_CONTEXT_RE.search(value):
        return "read_only_source"
    if is_inspect_only_path_context(value):
        return "inspect_only_context"
    return ""


def collect_classified_plan_paths(
    text: str,
    *,
    repo_root: Path | None = None,
    resolution_context: str = "",
) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"read_only_sources": [], "reference_patterns": [], "inspect_only_sources": []}
    seen: dict[str, set[str]] = {key: set() for key in buckets}
    full_context = str(text or "") + "\n" + str(resolution_context or "")
    for segment in path_context_segments(text):
        classification = classify_non_target_path_context(segment)
        if not classification:
            continue
        bucket = "reference_patterns" if classification == "reference_pattern" else "read_only_sources" if classification == "read_only_source" else "inspect_only_sources"
        for _raw, path, rejection_reason in iter_plan_path_tokens(segment):
            if rejection_reason:
                continue
            resolved = resolve_repo_basename_path(path, repo_root, full_context)
            if resolved and resolved not in seen[bucket]:
                seen[bucket].add(resolved)
                buckets[bucket].append(resolved)
    return buckets


def merge_classified_plan_paths(*groups: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {"read_only_sources": [], "reference_patterns": [], "inspect_only_sources": []}
    seen: dict[str, set[str]] = {key: set() for key in merged}
    for group in groups:
        for key in merged:
            for path in group.get(key, []):
                if path and path not in seen[key]:
                    seen[key].add(path)
                    merged[key].append(path)
    return merged


REVIEWER_REQUIRED_TARGET_CONTEXT_RE = re.compile(
    r"(?:Blocker|requires_revision|reviewer|方案评审|阻塞|修订).{0,220}"
    r"(?:遗漏|缺少|未覆盖|必须|必改|must[-_ ]?change|required|不应被降级|不得降级|不能降级|not\s+downgraded)|"
    r"(?:遗漏|缺少|未覆盖|必须|必改|must[-_ ]?change|required|不应被降级|不得降级|不能降级|not\s+downgraded).{0,220}"
    r"(?:Blocker|requires_revision|reviewer|方案评审|阻塞|修订|target_files|must_change_targets)",
    re.IGNORECASE,
)


def reviewer_required_target_paths(
    text: str,
    *,
    repo_root: Path | None = None,
    resolution_context: str = "",
    filtered_findings: list[dict[str, str]] | None = None,
    limit: int = 24,
) -> list[str]:
    """Extract reviewer-mandated implementation targets from repair context.

    Ordinary plan extraction is intentionally conservative because reviewers also
    mention read-only sources, forbidden files, and inspect-only examples.  Once
    solution_review has already returned a non-hard requires_revision, explicit
    Blocker lines such as "遗漏 X" or "X 是必改文件，不应降级为 inspect_only"
    are the handoff contract for revise_solution and must override older
    reference/inspect-only classification unless the path is later rejected by
    credential/runtime/forbidden target filters.
    """
    paths: list[str] = []
    seen: set[str] = set()
    full_context = str(text or "") + "\n" + str(resolution_context or "")
    for segment in path_context_segments(text):
        if not REVIEWER_REQUIRED_TARGET_CONTEXT_RE.search(segment):
            continue
        # A reviewer Blocker can either promote missing concrete files or demote
        # files that were incorrectly placed in target_files/must_change_targets.
        # Do not treat demotion/removal blockers as required implementation
        # targets; record them as filtered findings so revise_solution preserves
        # the negative contract instead of re-promoting them.
        if (
            re.search(r"(?:证据不足|必须从.{0,80}移除|应从.{0,80}移除|从.{0,80}移除|降级(?:到|为)|reference_patterns?|route\s+wiring\s+reference|作为\s*reference|inspect_only|read_only)", segment, re.IGNORECASE)
            and not re.search(r"(?:不应被降级|不得降级|不能降级|不应降级|not\s+downgraded)", segment, re.IGNORECASE)
        ):
            for _raw, path, rejection_reason in iter_plan_path_tokens(segment):
                add_filtered_target_finding(
                    filtered_findings,
                    path,
                    "solution_review_blocker_demoted_target",
                    rejection_reason or "reviewer_requested_reference_or_inspect_only",
                    segment,
                )
            continue
        for _raw, path, rejection_reason in iter_plan_path_tokens(segment):
            if rejection_reason:
                add_filtered_target_finding(
                    filtered_findings,
                    path,
                    "solution_review_blocker_required_target",
                    rejection_reason,
                    segment,
                )
                continue
            resolved_path = resolve_repo_basename_path(path, repo_root, full_context)
            if not resolved_path or resolved_path in seen:
                continue
            seen.add(resolved_path)
            paths.append(resolved_path)
            if len(paths) >= limit:
                return paths
    return paths


def control_plane_plan_path_reason(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    if not normalized:
        return "empty_path"
    trimmed = normalized
    while trimmed.startswith("./"):
        trimmed = trimmed[2:]
    trimmed = trimmed.lstrip("/")
    name = Path(trimmed).name
    if name in PIPELINE_ARTIFACT_FILES:
        return "pipeline_artifact_file"
    if SENSITIVE_TARGET_BASENAME_RE.fullmatch(name):
        return "credential_or_auth_target_file"
    if "/" not in trimmed and name in WORKFLOW_HOST_BASENAMES:
        return "workflow_host_basename"
    if name in PROJECT_MEMORY_FILES and not trimmed.startswith("memory/"):
        return "project_memory_control_file"
    if any(trimmed.startswith(prefix) for prefix in CONTROL_PLANE_PATH_PREFIXES):
        return "workflow_or_runtime_control_path"
    wrapped = f"/{trimmed.strip('/')}/"
    if any(part in wrapped for part in CONTROL_PLANE_PATH_PARTS):
        return "workflow_or_runtime_control_path"
    return ""


def is_control_plane_plan_path(path: str) -> bool:
    return bool(control_plane_plan_path_reason(path))


def allows_control_plane_targets(text: str) -> bool:
    value = str(text or "")
    # A business rerun may mention that workflow/runtime was already fixed as
    # history or as a forbidden target.  Do not let that prose reopen workflow
    # host files as application delivery targets.
    if re.search(
        r"(?:已修复|已验证|stale\s+runner\s+(?:已)?(?:fixed|修复)|重新(?:执行|跑).{0,40}业务|本轮.{0,40}业务|不应作为.{0,40}(?:业务|target_files|target)|不得.{0,40}(?:workflow|runtime).{0,20}(?:target|目标))",
        value,
        re.IGNORECASE,
    ):
        return False
    return bool(CONTROL_PLANE_TARGET_REQUEST_RE.search(value))


def add_filtered_target_finding(
    findings: list[dict[str, str]] | None,
    path: str,
    source: str,
    reason: str,
    segment: str,
) -> None:
    if findings is None or not path or reason in {"", "empty_path", "not_repository_plan_path", "pipeline_artifact_file"}:
        return
    if len(findings) >= MAX_FILTERED_TARGET_FINDINGS:
        return
    normalized_path = normalize_plan_path_token(path)
    for item in findings:
        if (
            item.get("path") == normalized_path
            and item.get("source") == source
            and item.get("reason") == reason
        ):
            return
    findings.append(
        {
            "path": clip_text(normalized_path, 240),
            "source": source,
            "reason": reason,
            "context": clip_text(" ".join(str(segment or "").split()), 220),
        }
    )


def drop_accepted_target_findings(findings: list[dict[str, str]], accepted_paths: list[str]) -> None:
    accepted = {normalize_plan_path_token(path) for path in accepted_paths if path}
    if not accepted:
        return
    findings[:] = [
        item
        for item in findings
        if normalize_plan_path_token(str(item.get("path") or "")) not in accepted
    ]


REPO_PATH_RESOLVE_SKIP_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".agents",
    ".codex-tmp",
    ".codex_tmp_openclaw_upgrade",
    ".pytest_cache",
    ".tmp",
    ".workflow",
    ".hermes",
    ".openclaw",
    ".codex",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "vendor",
    "agent-workspaces",
    "af39077",
    "chrome_user_data",
    "command-runs",
    "foo",
    "pipeline-runs",
    "graphify-out",
    "tmp",
}


def resolve_repo_basename_path(path: str, repo_root: Path | None, context_text: str = "") -> str:
    normalized = normalize_plan_path_token(path)
    if not normalized or not repo_root:
        return normalized
    if normalized in PROJECT_MEMORY_FILES or normalized in WORKFLOW_HOST_BASENAMES:
        return normalized
    try:
        repo = repo_root.expanduser().resolve()
    except OSError:
        return normalized
    if not repo.exists():
        return normalized
    if (repo / normalized).exists():
        return normalized
    suffix = Path(normalized).suffix.lower()
    if suffix not in {".py", ".md", ".json", ".json5", ".yaml", ".yml", ".toml", ".js", ".ts", ".html", ".css", ".sh"}:
        return normalized
    # Reviewers sometimes quote a valid repo suffix without the project package
    # prefix (for example `api/routes/dashboard.py` instead of
    # `src/product/api/routes/dashboard.py`). Resolve unique suffix drift
    # before solution_review so implementers never receive non-existent pseudo
    # targets.  Absolute/runtime-looking paths are still rejected earlier by
    # plan_path_rejection_reason and are not normalized here.
    matches: list[str] = []
    normalized_suffix = normalized.casefold()
    target_name = Path(normalized).name.casefold()
    skip_parts = {part.casefold() for part in REPO_PATH_RESOLVE_SKIP_PARTS}

    def ignore_walk_error(_error: OSError) -> None:
        # A generated/cache directory may be unreadable on a mixed local
        # workspace.  It is outside the source-resolution contract, so keep
        # resolving other candidates instead of aborting the whole plan.
        return None

    try:
        for current_root, dirnames, filenames in os.walk(repo, topdown=True, onerror=ignore_walk_error):
            # Prune before descending.  Filtering only after Path.glob() has
            # already traversed vendor/node_modules defeats the purpose and
            # can turn a small plan compilation into a multi-minute scan.
            dirnames[:] = [name for name in dirnames if name.casefold() not in skip_parts]
            for filename in filenames:
                if filename.casefold() != target_name:
                    continue
                candidate = Path(current_root) / filename
                rel_path = candidate.relative_to(repo)
                rel_value = rel_path.as_posix()
                folded = rel_value.casefold()
                if "/" in normalized and folded != normalized_suffix and not folded.endswith(f"/{normalized_suffix}"):
                    continue
                matches.append(rel_value)
    except OSError:
        return normalized
    if not matches:
        return normalized
    context = str(context_text or "")
    exact = [item for item in matches if item in context]
    if exact:
        return sorted(exact, key=lambda item: (len(item), item))[0]

    def rank(item: str) -> tuple[int, int, str]:
        value = item.replace("\\", "/")
        priority = 50
        if "/api/routes/" in value:
            priority = 0
        elif "/api/" in value:
            priority = 1
        elif "/monitoring/" in value:
            priority = 2
        elif value.startswith("scripts/"):
            priority = 3
        elif value.startswith("tests/"):
            priority = 8
        return (priority, len(value), value)

    return sorted(matches, key=rank)[0]


def contextual_plan_paths(
    *texts: str,
    limit: int = 24,
    filter_control_plane: bool = False,
    allow_control_plane: bool = False,
    filtered_findings: list[dict[str, str]] | None = None,
    source_label: str = "unknown",
    repo_root: Path | None = None,
    resolution_context: str = "",
) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    full_context = "\n".join(str(text or "") for text in texts) + "\n" + str(resolution_context or "")
    for text in texts:
        for segment in path_context_segments(text):
            segment_paths: list[str] = []
            for _raw, path, rejection_reason in iter_plan_path_tokens(segment):
                if rejection_reason:
                    add_filtered_target_finding(
                        filtered_findings,
                        path,
                        source_label,
                        rejection_reason,
                        segment,
                    )
                    continue
                segment_paths.append(path)
            non_target_reason = classify_non_target_path_context(segment)
            if non_target_reason:
                for path in segment_paths:
                    add_filtered_target_finding(
                        filtered_findings,
                        path,
                        source_label,
                        non_target_reason,
                        segment,
                    )
                continue
            if is_negated_path_context(segment):
                for path in segment_paths:
                    add_filtered_target_finding(
                        filtered_findings,
                        path,
                        source_label,
                        "negated_context",
                        segment,
                    )
                continue
            for path in segment_paths:
                if path in seen:
                    continue
                control_reason = control_plane_plan_path_reason(path)
                if filter_control_plane and control_reason and not allow_control_plane:
                    add_filtered_target_finding(
                        filtered_findings,
                        path,
                        source_label,
                        control_reason,
                        segment,
                    )
                    continue
                resolved_path = resolve_repo_basename_path(path, repo_root, full_context)
                if resolved_path in seen:
                    continue
                seen.add(resolved_path)
                paths.append(resolved_path)
                if len(paths) >= limit:
                    return paths
    return paths


def low_trust_plan_paths(
    *texts: str,
    limit: int = 24,
    filtered_findings: list[dict[str, str]] | None = None,
    source_label: str = "low_trust_context",
    repo_root: Path | None = None,
    resolution_context: str = "",
) -> list[str]:
    return contextual_plan_paths(
        *texts,
        limit=limit,
        filter_control_plane=True,
        filtered_findings=filtered_findings,
        source_label=source_label,
        repo_root=repo_root,
        resolution_context=resolution_context,
    )


def merge_plan_paths(*path_groups: list[str], limit: int = 24) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in path_groups:
        for path in group:
            if not path or path in seen:
                continue
            seen.add(path)
            merged.append(path)
            if len(merged) >= limit:
                return merged
    return merged


def delivery_target_priority(path: str) -> tuple[int, int, str]:
    value = str(path or "").replace("\\", "/")
    priority = 50
    if value.startswith(("src/", "app/", "lib/", "services/")):
        priority = 0
    elif value.startswith("scripts/"):
        priority = 1
    elif value.startswith("tests/"):
        priority = 5
    elif value.startswith("docs/"):
        priority = 8
    elif value.startswith("memory/") or value in {"MEMORY.md", "todo.md", "done.md"}:
        priority = 9
    return (priority, len(value), value)


def sort_delivery_target_paths(paths: list[str]) -> list[str]:
    return sorted(paths, key=delivery_target_priority)


def post_filter_target_paths(paths: list[str], findings: list[dict[str, str]] | None = None) -> list[str]:
    """Drop low-trust basename/artifact drift after merging target candidates.

    Repair context and reviewer prose frequently mention artifact names and
    basenames while explaining what went wrong.  If a concrete repo-relative
    path already exists in the contract, the basename form is ambiguous and
    should not be handed to implementers as a second target.
    """
    normalized = [normalize_plan_path_token(path) for path in paths if normalize_plan_path_token(path)]
    concrete_basenames = {Path(path).name for path in normalized if "/" in path}
    concrete_paths = {path for path in normalized if "/" in path}
    filtered: list[str] = []
    seen: set[str] = set()
    for path in normalized:
        parts = [part for part in path.split("/") if part]
        name = Path(path).name
        reason = ""
        if name in PIPELINE_ARTIFACT_FILES:
            reason = "pipeline_artifact_file"
        elif parts and parts[0] in PIPELINE_ARTIFACT_FILES:
            reason = "pipeline_artifact_path"
        elif parts and parts[0] in PROJECT_MEMORY_FILES and not path.startswith("memory/"):
            reason = "ambiguous_project_memory_basename_path"
        elif "/" not in path and name in PROJECT_MEMORY_FILES:
            reason = "ambiguous_project_memory_basename"
        elif "/" not in path and name in concrete_basenames:
            reason = "ambiguous_basename_duplicate"
        elif "/" in path and any(other != path and other.endswith("/" + path) for other in concrete_paths):
            reason = "ambiguous_suffix_duplicate"
        if reason:
            add_filtered_target_finding(findings, path, "post_filter", reason, path)
            continue
        if path in seen:
            continue
        seen.add(path)
        filtered.append(path)
    return filtered


def infer_task_type(text: str) -> str:
    value = str(text or "")
    lowered = value.lower()
    if any(token in lowered for token in ("docs-only", "doc-only", "memory/docs-only", "memory-only")):
        return "docs"
    if any(token in lowered for token in ("bug", "fix", "failed", "requires_revision", "修复", "失败", "阻塞")):
        return "bugfix"
    if any(token in lowered for token in ("deploy", "restart", "install", "runtime", "部署", "重启", "安装")):
        return "deploy"
    if any(token in lowered for token in ("research", "官方", "调研", "资料")):
        return "research"
    if (
        re.search(r"\b(?:only|just)\s+(?:update|edit|write|sync)\b.{0,60}\b(?:docs?|documentation|memory|readme)\b", lowered)
        or re.search(r"(?:只|仅|只需|仅需|只要).{0,30}(?:更新|修改|补充|同步|整理|撰写|写).{0,60}(?:文档|记忆|README)", value, re.IGNORECASE)
    ):
        return "docs"
    return "feature"


def infer_code_agent(text: str, config: PipelineConfig) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("frontend", "front-end", "dashboard", "page", "component", "页面", "前端", "交互", "样式")) or re.search(r"\bui\b", lowered):
        return "frontend-dev"
    if infer_task_type(text) == "docs":
        return "doc-writer"
    return normalize_code_agent(config.code_agent)


def original_requirement_block(requirement: str) -> str:
    match = re.search(r"(?ims)^## Original Requirement\s*(.+?)(?=^## |\Z)", str(requirement or ""))
    return (match.group(1) if match else requirement).strip()


def original_requirement_excerpt(requirement: str) -> str:
    source = original_requirement_block(requirement)
    lines = [line.strip(" -\t") for line in str(source or "").splitlines() if line.strip(" -\t")]
    return next((line for line in lines if not line.startswith("#")), "")


def task_slice_title(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    match = re.search(r"(P\d+\s*[^。；;，,：:\n]{1,24})", value, re.IGNORECASE)
    if match:
        return clip_text(match.group(1).strip(), 48)
    for marker in ("口径修正", "修复", "实现", "部署", "验收", "清理"):
        idx = value.find(marker)
        if 0 <= idx <= 40:
            return clip_text(value[idx : idx + 48].strip(" ：:"), 48)
    return "当前需求"


def is_template_scope_text(text: str) -> bool:
    value = str(text or "")
    return bool(
        re.search(
            r"(accepted implementation scope|handoff contract|generic pipeline template|Two AI roles|project-agent|reviewer|Delivery Plan Contract|solution_package|delivery_plan|scope_slices|target_files|verification plan|上一轮|重跑原因|本次重跑原因|强制方案|强制目标文件|强制验证|安全措辞)",
            value,
            re.IGNORECASE,
        )
    )


def plan_scope_slice(requirement: str, review: str, repair_context: str) -> dict[str, Any]:
    original_block = original_requirement_block(requirement)
    original = original_requirement_excerpt(original_block)
    source = original or original_requirement_excerpt(requirement) or review or requirement
    title = task_slice_title(source)
    description = source
    if title != "当前需求" and not source.strip().startswith(title):
        description = f"{title}：{source}"
    return {
        "id": re.sub(r"[^A-Za-z0-9_-]+", "-", title.lower()).strip("-") or "primary",
        "description": clip_text(description, 420),
        "status": "current",
        "source": "original_requirement",
    }


def split_scope_candidates(text: str) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    lines = []
    for raw in value.splitlines():
        line = raw.strip(" \t-")
        line = re.sub(r"^\s*(?:\d+[.)、]|[A-Za-z][.)])\s*", "", line).strip()
        if line and not line.startswith("#"):
            lines.append(line)
    bullet_like = [line for line in lines if len(line) >= 8]
    if len(bullet_like) >= 2:
        return bullet_like

    source = original_requirement_excerpt(value) or value
    if "：" in source:
        source = source.split("：", 1)[1]
    elif ":" in source:
        source = source.split(":", 1)[1]
    parts = re.split(r"[、；;]\s*|\s*,\s*", source)
    cleaned = [part.strip(" -\t。.") for part in parts if len(part.strip(" -\t。.")) >= 4]
    return cleaned if len(cleaned) >= 2 else []


def is_scope_control_text(text: str) -> bool:
    return bool(
        re.search(
            r"(安全|要求|不得|禁止|保持|不读取|不打印|不处理|token|cookie|credential|private key)",
            str(text or ""),
            re.IGNORECASE,
        )
    )


def plan_scope_slices(requirement: str, review: str, repair_context: str) -> list[dict[str, Any]]:
    # The OpenClaw backup workflow no longer enforces artificial task-splitting
    # granularity.  Keep this compatibility field as a single holistic scope so
    # downstream agents and multiple reviewers can consider all accepted findings
    # together until the complete plan passes.
    original_block = original_requirement_block(requirement) or requirement
    whole = plan_scope_slice(original_block, review, repair_context)
    whole["id"] = "holistic-scope"
    whole["status"] = "current"
    whole["source"] = "holistic_requirement"
    whole["review_policy"] = "multiple reviewers synthesize all findings; no deferred slices are created by the runner"
    return [whole]


def normalize_verification_command(command: str) -> str:
    value = str(command or "").strip().strip("` ")
    value = re.sub(r"\s+", " ", value)
    value = value.rstrip("。；;:")
    return value


def verification_command_rejection_reason(command: str) -> str:
    value = normalize_verification_command(command)
    lowered = value.lower()
    if not value:
        return "empty_command"
    if "live_runtime_bridge.py" in lowered or "--stage verification" in lowered:
        return "pipeline_runner_orchestration_command"
    if re.search(r"(?:通过|必须|进入 diff|验收|运行并记录|建议|例如|应|需要|不能|不要|缺少|包含上述)", value):
        return "natural_language_not_command"
    if lowered in {"pytest", "pytest:", "python", "python3", "py", "git"}:
        return "too_broad_or_incomplete_command"
    if value.endswith("`"):
        return "malformed_backtick_command"
    if re.match(r"^pytest\b", value):
        if not re.search(r"(?:^|\s)(?:tests?/|[^\s]+test[^\s]*\.py)", value) or re.search(r"[\u4e00-\u9fff]", value):
            return "malformed_pytest_command"
        return ""
    python_prefix = r'(?:(?:"[^"]*python(?:3(?:\.\d+)?)?(?:\.exe)?"|[^\s]*python(?:3(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?(?:\s+-3)?))'
    if re.match(rf"^{python_prefix}\s+", value, re.IGNORECASE):
        if re.search(r"\s-m\s+(?:pytest|compileall)\b", value) or re.search(r"\s-B\s+-m\s+compileall\b", value):
            return ""
        return "unsupported_python_verification_command"
    if value in {
        "git diff --check",
        "git status --short --branch",
        "git fetch origin main --prune",
        "git rev-parse --verify HEAD",
        "git rev-list --left-right --count HEAD...origin/main",
        "git branch -r --contains HEAD",
    }:
        return ""
    if re.match(r"^test\s+-f\s+[^\s]+$", value):
        return ""
    if re.match(r"^git\s+diff\s+--name-only\b", value):
        return ""
    if re.match(r'^/bin/sh\s+-c\s+"git\s+diff\s+--unified=0\b', value):
        return ""
    if re.match(r"^curl\s+-fsS\s+https?://(?:127\.0\.0\.1|localhost):\d+/", value):
        return ""
    if re.match(r"^(?:grep|rg)\b", value):
        return ""
    if lowered.startswith("run ") or lowered.startswith("read-only api smoke"):
        return "natural_language_not_command"
    return "unsupported_verification_command"


def add_verification_command(commands: list[dict[str, Any]], command: str, source: str = "accepted_requirement") -> None:
    normalized = normalize_verification_command(command)
    if verification_command_rejection_reason(normalized):
        return
    if normalized and normalized not in [item["command"] for item in commands]:
        commands.append({"command": normalized, "required": True, "source": source})


def added_line_safety_scan_command() -> str:
    return (
        "/bin/sh -c \"git diff --unified=0 -- . ':!pipeline-runs/**' ':!command-runs/**' ':!agent-workspaces/**' "
        r"| rg -n '^\+.*(credential\s*[:=]|credentials\s*[:=]|api[_ -]?key\s*[:=]|secret\s*[:=]|password\s*[:=]|private[_ -]?key\s*[:=]|Authorization\s*[:=]|Cookie\s*[:=])' "
        "&& exit 1 || test $? -eq 1\""
    )


def explicit_verification_commands(text: str) -> list[dict[str, Any]]:
    value = str(text or "")
    commands: list[dict[str, Any]] = []
    python_prefix = r'(?:(?:"[^"]*python(?:3(?:\.\d+)?)?(?:\.exe)?"|[^\s]*python(?:3(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?(?:\s+-3)?))'
    for match in re.finditer(rf"{python_prefix}\s+(?:-B\s+)?-m\s+(?:pytest|compileall)[^\r\n；;。、`]*", value, re.IGNORECASE):
        add_verification_command(commands, match.group(0).strip())
    for match in re.finditer(r"(?m)^\s*pytest\s+-q\s+[^\r\n；;。、`]+", value, re.IGNORECASE):
        add_verification_command(commands, match.group(0).strip())
    for match in re.finditer(r"curl\s+-fsS\s+https?://(?:127\.0\.0\.1|localhost):\d+/[^\s`]*", value, re.IGNORECASE):
        add_verification_command(commands, match.group(0).strip())
    if "git diff --check" in value:
        add_verification_command(commands, "git diff --check")
    if re.search(r"credential|credentials|secret|password|private key|密钥|凭证", value, re.IGNORECASE):
        add_verification_command(commands, added_line_safety_scan_command())
    if re.search(r"git publish|origin/main|remote containment|远端包含", value, re.IGNORECASE):
        add_verification_command(commands, "git status --short --branch")
        add_verification_command(commands, "git fetch origin main --prune")
        add_verification_command(commands, "git rev-parse --verify HEAD")
        add_verification_command(commands, "git diff --name-only --cached -- . ':!command-runs/**' ':!agent-workspaces/**' ':!pipeline_state.json' ':!run_meta.json'")
        add_verification_command(commands, "git rev-list --left-right --count HEAD...origin/main")
    return commands


def configured_verification_commands(config: PipelineConfig, task_type: str, evidence_text: str = "") -> list[dict[str, Any]]:
    explicit = explicit_verification_commands(evidence_text)
    commands = [
        {"command": normalize_verification_command(command), "required": True, "source": "runner_config"}
        for command in config.verification_commands
        if not verification_command_rejection_reason(str(command or ""))
    ]
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*explicit, *commands]:
        command = normalize_verification_command(str(item.get("command") or ""))
        if command and command not in seen and not verification_command_rejection_reason(command):
            seen.add(command)
            merged.append({**item, "command": command})
    if "git diff --check" not in seen:
        seen.add("git diff --check")
        merged.append({"command": "git diff --check", "required": True, "source": "default_baseline"})
    default_compileall = "python -m compileall -q ."
    if task_type != "docs" and not any(" -m compileall " in command or command.endswith(" -m compileall") for command in seen):
        merged.append({"command": default_compileall, "required": True, "source": "default_baseline"})
    return merged


def render_markdown_items(items: list[str]) -> str:
    cleaned = [clip_text(str(item).strip(), 240) for item in items if str(item).strip()]
    if not cleaned:
        return "- not_applicable"
    return "\n".join(f"- {item}" for item in cleaned)


def artifact_text(artifacts: dict[str, str], key: str) -> str:
    path = artifacts.get(key)
    if not path:
        return ""
    return read_optional_file(Path(path), "")


GRAPHIFY_INDEX_ROOT_ENV = "PIPELINE_GRAPHIFY_INDEX_ROOT"
GRAPHIFY_BLOCK_PATTERNS = {
    "credential_path": re.compile(r"(?i)(credential|credentials|secret|cookie|oauth|api[-_ ]?key|private[-_ ]?key|auth[-_ ]?state|credential-imports|private/|(?:^|[/_.-])token(?:s)?(?:[/_.-]|$))"),
}


def profile_from_source_urls(source_urls: tuple[str, ...]) -> str:
    for item in source_urls:
        text = str(item or "").strip()
        if text.startswith("discord:") and ":" in text:
            value = text.split(":", 1)[1].strip()
            if value:
                return value
    return os.environ.get("PROJECT_PIPELINE_LIVE_BRIDGE_PROFILE", "projectagent").strip() or "projectagent"


def graphify_index_root(config: PipelineConfig, runtime: dict[str, Any]) -> Path:
    explicit = os.environ.get(GRAPHIFY_INDEX_ROOT_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runtime_home = Path(str(runtime.get("runtime_home") or config.runtime_home or "~/.hermes")).expanduser()
    profile = profile_from_source_urls(config.source_urls)
    return runtime_home / "profiles" / profile / "graphify-indexes"


def graphify_repo_index_dir(config: PipelineConfig, runtime: dict[str, Any]) -> Path:
    repo = config.command_cwd.expanduser().resolve()
    return graphify_index_root(config, runtime) / repo.name / "graphify-out"


def graphify_graph_stats(graph_path: Path) -> dict[str, Any]:
    try:
        if graph_path.stat().st_size > 20_000_000:
            return {"nodes": 0, "links": 0, "communities": 0, "skipped": "graph_json_too_large"}
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    links = payload.get("links") if isinstance(payload.get("links"), list) else []
    communities: set[str] = set()
    for node in nodes:
        if isinstance(node, dict) and node.get("community") is not None:
            communities.add(str(node.get("community")))
    return {"nodes": len(nodes), "links": len(links), "communities": len(communities)}


def extract_report_section(report: str, heading_hint: str, max_chars: int = 1800) -> str:
    if not report.strip():
        return "not_available"
    lines = report.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.lstrip("# ").strip().lower().startswith(heading_hint.lower()):
            start = index
            break
    if start is None:
        return clip_text(report, max_chars)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("#") and lines[index].strip("# "):
            end = index
            break
    return clip_text("\n".join(lines[start:end]).strip(), max_chars)


def render_graphify_context(config: PipelineConfig, runtime: dict[str, Any], requirement: str) -> str:
    repo = config.command_cwd.expanduser().resolve()
    index_dir = graphify_repo_index_dir(config, runtime)
    graph_path = index_dir / "graph.json"
    report_path = index_dir / "GRAPH_REPORT.md"
    root_marker = index_dir / ".graphify_root"
    root_text = read_optional_file(root_marker, "").strip() if root_marker.exists() else ""
    root_matches = True
    if root_text:
        try:
            root_matches = Path(root_text).expanduser().resolve() == repo
        except OSError:
            root_matches = False
    status = "available" if graph_path.exists() and root_matches else "root_mismatch" if graph_path.exists() else "missing"
    report = read_optional_file(report_path, "") if report_path.exists() and root_matches else ""
    stats = graphify_graph_stats(graph_path) if graph_path.exists() and root_matches else {"nodes": 0, "links": 0, "communities": 0}
    return dedent(
        f"""
        # Graphify Project Context

        ## Status
        - status: `{status}`
        - repo: `{repo}`
        - index_dir: `{index_dir}`
        - graph_json: `{graph_path if graph_path.exists() else 'missing'}`
        - graph_report: `{report_path if report_path.exists() else 'missing'}`
        - indexed_root: `{root_text or 'unknown'}`
        - root_matches_repo: `{root_matches}`
        - nodes: `{stats.get('nodes', 0)}`
        - links: `{stats.get('links', 0)}`
        - communities: `{stats.get('communities', 0)}`

        ## Usage Contract
        - This artifact is a soft project-knowledge-graph context layer.
        - `requirements_discussion` must use it before proposing target files.
        - `solution_review` and `code_review` must use it to challenge missing related modules/tests.
        - Missing graphify output is a warning only; fall back to project memory/docs and repository search.
        - Do not mix business repository graph context with hardflow/workflow graph context unless the requirement explicitly asks for pipeline/runtime interaction debugging.

        ## Original Requirement Excerpt
        {clip_text(requirement, 1200)}

        ## Graph Report Excerpt
        {extract_report_section(report, 'God Nodes') if report else 'not_available'}

        ## Suggested Questions Excerpt
        {extract_report_section(report, 'Suggested Questions') if report else 'not_available'}
        """
    ).strip() + "\n"


def normalize_plan_path(path_value: str) -> str:
    value = str(path_value or "").strip().strip("`'\"")
    return value.replace("\\", "/")


def graphify_scope_validation_status(findings: list[dict[str, str]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warning"
    return "pass"


def scope_scan_text_from_plan(delivery_plan: dict[str, Any]) -> str:
    # Scan actionable execution fields only. The runner intentionally writes
    # generated contracts must not become graphify hard blocks. Pretty JSON
    # keeps each item on its own line so unrelated fields stay separable.
    actionable = {
        key: delivery_plan.get(key)
        for key in ("implementation_steps",)
        if delivery_plan.get(key)
    }
    return scrub_negated_risk_lines(json.dumps(actionable, ensure_ascii=False, indent=2))


def is_noncredential_token_path(path: str) -> bool:
    """Return true only for source-code tokenizer modules, not credential stores."""

    value = str(path or "").replace("\\", "/").lower()
    return bool(re.search(r"(?:^|/)(?:tokenizer|tokenizers|lexer|parser)(?:[._/-]|$)", value))


def validate_graphify_scope(config: PipelineConfig, runtime: dict[str, Any], delivery_plan: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
    repo = config.command_cwd.expanduser().resolve()
    index_dir = graphify_repo_index_dir(config, runtime)
    graph_path = index_dir / "graph.json"
    root_marker = index_dir / ".graphify_root"
    findings: list[dict[str, str]] = []
    if not graph_path.exists():
        findings.append({"severity": "warning", "path": str(graph_path), "reason": "graphify graph is missing; falling back to memory/docs/repository search"})
    elif root_marker.exists():
        root_text = read_optional_file(root_marker, "").strip()
        try:
            root_matches = Path(root_text).expanduser().resolve() == repo
        except OSError:
            root_matches = False
        if not root_matches:
            findings.append({"severity": "warning", "path": str(graph_path), "reason": "graphify index root does not match command repository; graph context should not be trusted"})
    target_files = delivery_plan.get("target_files") if isinstance(delivery_plan.get("target_files"), list) else []
    for item in target_files:
        if not isinstance(item, dict):
            continue
        raw_path = normalize_plan_path(str(item.get("path") or ""))
        if not raw_path:
            continue
        severity = "warning"
        reason = "target file could not be confirmed against graph context"
        path_obj = Path(raw_path).expanduser()
        if path_obj.is_absolute():
            try:
                path_obj.resolve().relative_to(repo)
            except ValueError:
                severity = "block"
                reason = "target path is outside the command repository boundary"
        elif raw_path.startswith("../") or "/../" in raw_path:
            severity = "block"
            reason = "target path escapes the command repository boundary"
        elif GRAPHIFY_BLOCK_PATTERNS["credential_path"].search(raw_path) and not is_noncredential_token_path(raw_path):
            severity = "block"
            reason = "target path appears to reference credential/auth/secret material"
        else:
            candidate = repo / raw_path
            if not candidate.exists():
                if item.get("create_if_missing_rationale") or item.get("create_if_missing"):
                    reason = ""
                else:
                    reason = "target file is not currently present; create_if_missing rationale is required"
        if severity == "block" or reason.startswith("target file"):
            findings.append({"severity": severity, "path": raw_path, "reason": reason})
    scan_plan_text = scope_scan_text_from_plan(delivery_plan)
    if GRAPHIFY_BLOCK_PATTERNS["credential_path"].search(scan_plan_text):
        findings.append({"severity": "block", "path": "delivery_plan.json", "reason": "plan text references credential/auth/secret material"})
    status = graphify_scope_validation_status(findings)
    return {
        "schema_version": "graphify-scope-validation/v1",
        "scope_status": status,
        "graph_available": graph_path.exists(),
        "graph_json": str(graph_path) if graph_path.exists() else "missing",
        "repo": str(repo),
        "policy": "warning by default; block only for cross-repo paths or credentials/auth material",
        "findings": findings,
        "recommended_verification": [item.get("command") for item in delivery_plan.get("verification_commands", []) if isinstance(item, dict) and item.get("command")][:12],
        "source_artifacts": {key: artifacts[key] for key in ("graphify_context", "delivery_plan", "solution_package") if key in artifacts},
    }


def render_graphify_scope_validation(payload: dict[str, Any]) -> str:
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    finding_lines = [f"- `{item.get('severity')}` `{item.get('path')}` — {item.get('reason')}" for item in findings[:40] if isinstance(item, dict)]
    if not finding_lines:
        finding_lines = ["- no scope findings"]
    commands = payload.get("recommended_verification") if isinstance(payload.get("recommended_verification"), list) else []
    command_lines = [f"- `{cmd}`" for cmd in commands[:20] if str(cmd or "").strip()] or ["- not_available"]
    return dedent(
        f"""
        # Graphify Scope Validation

        ## Verdict
        - scope_status: `{payload.get('scope_status')}`
        - graph_available: `{payload.get('graph_available')}`
        - graph_json: `{payload.get('graph_json')}`
        - repo: `{payload.get('repo')}`

        ## Policy
        {payload.get('policy')}

        ## Findings
        {chr(10).join(finding_lines)}

        ## Recommended Verification
        {chr(10).join(command_lines)}
        """
    ).strip() + "\n"


def create_if_missing_rationale(path: str, evidence_text: str = "") -> str:
    value = str(path or "").replace("\\", "/")
    text = str(evidence_text or "")
    if value.startswith("tests/"):
        return "Create only when no existing targeted test covers this accepted requirement; keep it deterministic and repository-local."
    if value.startswith("docs/"):
        return (
            "Create only when no existing documentation page records this accepted requirement; "
            "state the verified behavior, evidence commands, ownership, rollback boundary, and index linkage."
        )
    if value.startswith("memory/"):
        name = Path(value).name
        if name == "PROJECT_PROFILE.md":
            return "Create only if the project memory module is missing; record module boundaries, owners, supported entry points, and explicit exclusions."
        if name == "DECISIONS.md":
            return "Create only if the project memory module is missing; record durable decisions and their verification evidence."
        if name == "DELIVERY_RULES.md":
            return "Create only if the project memory module is missing; record test, review, publish, rollback, and evidence gates."
        return "Create only if the project memory module is missing; seed it with verified facts from this run and deterministic content assertions."
    if "create_if_missing" in text and Path(value).suffix:
        return "Create only after confirming no existing module implements the accepted requirement, and document the import or wiring path in implementation steps."
    return ""


def target_file_reason(path: str, confidence: str, exists: bool, evidence_text: str) -> str:
    value = str(path or "").replace("\\", "/")
    if not exists:
        rationale = create_if_missing_rationale(value, evidence_text)
        if rationale:
            return f"Create if missing: {rationale}"
    if confidence == "solution_review_blocker_required_target":
        return "Promoted from a concrete solution-review blocker; preserve it unless an explicit forbidden-target rule applies."
    if value.startswith("tests/"):
        return "Targeted regression test referenced by the accepted requirement or review evidence."
    if value.startswith("docs/") or value.startswith("memory/") or value in {"MEMORY.md", "todo.md", "done.md"}:
        return "Documentation, memory, or task-board writeback target required for closure evidence."
    return {
        "explicit": "Referenced by the original user requirement.",
        "repair_context": "Referenced by repair context and retained as a candidate target.",
        "requirements_discussion": "Referenced by project-agent/reviewer requirements discussion as a candidate target.",
        "review_candidate": "Referenced by reviewer or requirements review as a candidate target.",
        "project_evidence": "Referenced by project evidence as a candidate target.",
    }.get(confidence, "Referenced by project evidence as a candidate target.")


def implementation_step_description(path: str, item: dict[str, Any]) -> str:
    value = str(path or "").replace("\\", "/")
    if item.get("create_if_missing_rationale"):
        return (
            f"Confirm whether `{value}` already has an equivalent implementation; if not, create it for: "
            f"{item['create_if_missing_rationale']} Wire it into the smallest existing entry point and cover it with targeted tests."
        )
    if value.startswith("tests/"):
        return "Add or update this targeted test to prove the exact behavior, boundary conditions, and regression acceptance for the related implementation."
    if value.endswith(("api/main.py", "app.py", "server.py")):
        return "Confirm the application entry point wires the accepted route or service; change registration only when repository evidence proves it is missing."
    if value.startswith("scripts/"):
        return "Update this operational script only when it is part of the accepted workflow; prove deterministic output, idempotence where applicable, and credential hygiene."
    if value.startswith("docs/") or value.startswith("memory/") or value in {"MEMORY.md", "todo.md", "done.md"}:
        return "Update this writeback target with verified behavior, commands run, ownership, rollback, and any remaining acceptance boundary."
    return f"Map `{value}` to the accepted requirement, state the intended behavior before editing, then apply the smallest code, test, or documentation change with a matching verification command."


def is_delivery_entry_point(path: str) -> bool:
    value = str(path or "").replace("\\", "/")
    if value.startswith(("docs/", "memory/")) or value in {"MEMORY.md", "todo.md", "done.md"}:
        return False
    if value.startswith("tests/"):
        return False
    return Path(value).suffix in {".py", ".js", ".ts", ".html"}




FACT_SOURCE_PATHS = {
    "MEMORY.md",
    "memory/INDEX.md",
    "memory/DEPLOYMENT.md",
    "memory/RUNBOOK.md",
    "docs/INDEX.md",
    "todo.md",
    "done.md",
}

PIPELINE_ARTIFACT_TARGET_NAMES = {
    "run_meta.json",
    "pipeline_state.json",
    "delivery_plan.json",
    "solution.md",
    "solution_review.md",
    "solution_review_soft_gate.md",
    "solution_review_revision_ledger.json",
    "requirements_review.md",
    "requirements_discussion.md",
    "graphify_scope_validation.md",
    "failure_summary.md",
}


def nearby_negative_scope(context: str, value: str, terms: str) -> bool:
    normalized = str(context or "").replace("`", "")
    basename = Path(value).name
    candidates = [re.escape(value), re.escape(basename)]
    path_pattern = "|".join(candidate for candidate in candidates if candidate)
    if not path_pattern:
        return False
    return bool(re.search(
        rf"(?:不|不要|不得|禁止|非目标|不在本轮|不新增|不删除|不因名称命中).{{0,120}}(?:{path_pattern}|{terms})|(?:{path_pattern}|{terms}).{{0,120}}(?:不|不要|不得|禁止|非目标|不在本轮|不新增|不删除|不因名称命中)",
        normalized,
        re.IGNORECASE,
    ))


def has_explicit_writeback_intent(context: str, value: str) -> bool:
    return bool(re.search(
        rf"(?:修改|更新|写回|创建|新增|落库|记录|create|update|writeback).{{0,80}}{re.escape(value)}|{re.escape(value)}.{{0,80}}(?:修改|更新|写回|创建|新增|落库|记录|create|update|writeback)",
        str(context or ""),
        re.IGNORECASE,
    ))


def delivery_non_target_bucket(path: str, exists: bool, planning_context: str, confidence: str) -> tuple[str, str] | None:
    value = str(path or "").replace("\\", "/").strip()
    lower = value.lower()
    context = str(planning_context or "")
    if not value:
        return None
    if re.search(r"(?:auth|credential|credentials|secret|cookie|oauth|api[-_ ]?key|private[-_ ]?key|凭证|密钥|私钥)", lower) and ("*" in value or "/" in value or lower.endswith((".json", ".yaml", ".yml", ".toml", ".env"))):
        return ("inspect_only_sources", "credential_auth_material_forbidden_not_target")
    if re.match(r"(?i)^(?:GET|POST|PUT|PATCH|DELETE)\s+/", value) or lower.startswith("/api/") or lower == "/health":
        return ("reference_patterns", "api_contract_endpoint_not_repo_target")
    if Path(value).is_absolute():
        return ("inspect_only_sources", "absolute_or_external_path_not_repo_target")
    if lower.startswith(("skills/library/", "scripts/openclaw-ops/", "config/runtime-profiles/", "cron/")) and confidence != "explicit":
        return ("inspect_only_sources", "workflow_or_runtime_path_not_application_target")
    if value in PIPELINE_ARTIFACT_TARGET_NAMES or lower in {"graph.json", "graphify.json", "external_research.md", "research_report.md", "graphify_scope_validation.md"} or lower.startswith(("pipeline-runs/", ".hermes/", "command-runs/", "agent-workspaces/")):
        return ("inspect_only_sources", "pipeline_artifact_not_repo_target")
    if value in FACT_SOURCE_PATHS:
        return ("read_only_sources", "project_fact_source_read_only")
    if value == "GRAPH_REPORT.md" or lower.endswith("/graph_report.md"):
        return ("inspect_only_sources", "external_graph_context_not_application_target")
    if lower.startswith("scripts/") and confidence != "explicit" and any(token in lower for token in ("service", "restart", "deploy", "runtime")):
        return ("inspect_only_sources", "operations_script_reference_not_application_target")
    if lower.startswith("cron/") or lower in {"cron/jobs.json", "jobs.json"}:
        return ("inspect_only_sources", "schedule_runtime_not_application_target")
    if re.search(r"\s/\s", value):
        return ("reference_patterns", "natural_language_scope_not_repo_target")
    if lower in {"setup.py", "pyproject.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        packaging_requested = confidence == "explicit" and re.search(r"(?:packag|dependency|dependencies|安装包|依赖|entrypoint|console_scripts)", context, re.IGNORECASE)
        if not packaging_requested:
            return ("inspect_only_sources", "packaging_file_outside_current_scope")
    if lower.startswith("docs/research/"):
        return ("read_only_sources", "research_document_read_only")
    if lower.startswith("docs/") or lower.startswith("memory/") or value in {"MEMORY.md", "todo.md", "done.md"} or (value.endswith(".md") and "/" not in value and value != "README.md"):
        if confidence == "explicit" and has_explicit_writeback_intent(context, value) and re.search(r"(?:文档|memory|docs|writeback|写回|记录)", context, re.IGNORECASE):
            return None
        return ("read_only_sources", "documentation_or_memory_read_only_unless_explicit_writeback")
    return None


def append_classified_context_path(classified: dict[str, list[str]], bucket: str, path: str) -> None:
    values = classified.setdefault(bucket, [])
    if path not in values:
        values.append(path)


def remove_classified_context_path(classified: dict[str, list[str]], path: str) -> None:
    for values in classified.values():
        while path in values:
            values.remove(path)


API_ENDPOINT_RE = re.compile(r"(?i)\b(?:GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_./{}?=&:-]+)|`(/[A-Za-z0-9_./{}?=&:-]+)`")


def extract_api_contracts(*texts: str, limit: int = 12) -> list[dict[str, str]]:
    contracts: list[dict[str, str]] = []
    seen: set[str] = set()
    joined = "\n".join(str(text or "") for text in texts)
    for match in API_ENDPOINT_RE.finditer(joined):
        endpoint = next((group for group in match.groups() if group), "")
        endpoint = endpoint.strip().rstrip(".,;:)")
        if not endpoint or endpoint in seen:
            continue
        if endpoint.startswith(("/home/", "/tmp/", "/var/", "/root/", "/Users/")) or "/pipeline-runs/" in endpoint or "/agent-workspaces/" in endpoint:
            continue
        seen.add(endpoint)
        if endpoint.lower() == "/health":
            contract = "Health smoke must satisfy the accepted service contract."
        else:
            contract = "Request, response, authentication, error, and data-exposure behavior must satisfy the accepted requirement."
        contracts.append({"endpoint": endpoint, "contract": contract})
        if len(contracts) >= limit:
            break
    if not contracts and re.search(r"(?:页面|API|接口|dashboard|配置|显示|验收)", joined, re.IGNORECASE):
        contracts.append({"endpoint": "accepted requirement API/UI surface", "contract": "The accepted UI or API surface must expose only intended data and pass deterministic assertions."})
    return contracts


def build_must_change_targets(target_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    must_change: list[dict[str, Any]] = []
    for item in target_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        must_item = {
            "path": path,
            "reason": item.get("reason", "Required implementation target from delivery_plan.target_files."),
            "required": True,
        }
        if item.get("create_if_missing"):
            must_item["create_if_missing"] = True
            must_item["create_if_missing_rationale"] = item.get("create_if_missing_rationale", "")
        must_change.append(must_item)
    return must_change


def compile_delivery_plan(
    config: PipelineConfig,
    runtime: dict[str, Any],
    requirement: str,
    artifacts: dict[str, str],
) -> dict[str, Any]:
    research = artifact_text(artifacts, "external_research")
    memory = artifact_text(artifacts, "project_memory_context")
    requirements_discussion = artifact_text(artifacts, "requirements_discussion")
    requirements_review = artifact_text(artifacts, "requirements_review")
    git_context = artifact_text(artifacts, "git_repository_context")
    repair_context = os.environ.get("PIPELINE_REPAIR_CONTEXT", "").strip()
    original_requirement_full = original_requirement_block(requirement) or requirement
    original_requirement = original_requirement_excerpt(requirement) or original_requirement_full or requirement
    decision_text = "\n".join([requirement, requirements_review, repair_context])
    planning_context = "\n".join([original_requirement_full, requirements_discussion, requirements_review, repair_context, research, memory])
    classification_text = "\n".join(
        part for part in (original_requirement_full, repair_context) if str(part or "").strip()
    ) or requirements_review
    task_type = infer_task_type(classification_text)
    allow_control_targets = allows_control_plane_targets("\n".join([original_requirement_full, repair_context]))
    filtered_target_candidates: list[dict[str, str]] = []
    explicit_target_paths = contextual_plan_paths(
        original_requirement_full,
        limit=48,
        filter_control_plane=True,
        allow_control_plane=allow_control_targets,
        filtered_findings=filtered_target_candidates,
        source_label="original_requirement_or_repair_context",
        repo_root=config.command_cwd,
        resolution_context=planning_context,
    )
    repair_target_paths = low_trust_plan_paths(
        repair_context,
        limit=48,
        filtered_findings=filtered_target_candidates,
        source_label="repair_context",
        repo_root=config.command_cwd,
        resolution_context=planning_context,
    )
    reviewer_required_paths = reviewer_required_target_paths(
        repair_context,
        limit=48,
        filtered_findings=filtered_target_candidates,
        repo_root=config.command_cwd,
        resolution_context=planning_context,
    )
    discussion_target_paths = low_trust_plan_paths(
        requirements_discussion,
        limit=48,
        filtered_findings=filtered_target_candidates,
        source_label="requirements_discussion",
        repo_root=config.command_cwd,
        resolution_context=planning_context,
    )
    review_target_paths = low_trust_plan_paths(
        requirements_review,
        limit=48,
        filtered_findings=filtered_target_candidates,
        source_label="requirements_review",
        repo_root=config.command_cwd,
        resolution_context=planning_context,
    )
    classified_context_paths = merge_classified_plan_paths(
        collect_classified_plan_paths(requirements_discussion, repo_root=config.command_cwd, resolution_context=planning_context),
        collect_classified_plan_paths(requirements_review, repo_root=config.command_cwd, resolution_context=planning_context),
        collect_classified_plan_paths(repair_context, repo_root=config.command_cwd, resolution_context=planning_context),
    )
    non_target_path_set = {
        path
        for key in ("read_only_sources", "reference_patterns", "inspect_only_sources")
        for path in classified_context_paths.get(key, [])
    }
    source_by_path: dict[str, str] = {}
    for path in explicit_target_paths:
        source_by_path.setdefault(path, "explicit")
    for path in repair_target_paths:
        source_by_path.setdefault(path, "repair_context")
    for path in reviewer_required_paths:
        source_by_path[path] = "solution_review_blocker_required_target"
        remove_classified_context_path(classified_context_paths, path)
    for path in discussion_target_paths:
        source_by_path.setdefault(path, "requirements_discussion")
    for path in review_target_paths:
        source_by_path.setdefault(path, "review_candidate")
    target_paths = post_filter_target_paths(
        merge_plan_paths(explicit_target_paths, reviewer_required_paths, repair_target_paths, discussion_target_paths, review_target_paths, limit=64),
        filtered_target_candidates,
    )
    if non_target_path_set:
        kept_target_paths = []
        for path in target_paths:
            if path in non_target_path_set and path not in set(reviewer_required_paths):
                add_filtered_target_finding(
                    filtered_target_candidates,
                    path,
                    "solution_review_readiness",
                    "read_only_or_reference_context",
                    path,
                )
                continue
            kept_target_paths.append(path)
        target_paths = kept_target_paths
    try:
        repo = config.command_cwd.expanduser().resolve()
    except OSError:
        repo = Path(".")
    filtered_actionable_paths: list[str] = []
    for path in sort_delivery_target_paths(target_paths):
        confidence = source_by_path.get(path, "project_evidence")
        exists = (repo / path).exists()
        bucket = delivery_non_target_bucket(path, exists, planning_context, confidence)
        if bucket:
            bucket_name, reason = bucket
            append_classified_context_path(classified_context_paths, bucket_name, path)
            add_filtered_target_finding(filtered_target_candidates, path, "delivery_plan_target_convergence", reason, path)
            continue
        filtered_actionable_paths.append(path)
    target_paths = filtered_actionable_paths
    if not target_paths:
        target_paths = low_trust_plan_paths(
            research,
            memory,
            limit=48,
            filtered_findings=filtered_target_candidates,
            source_label="research_or_project_memory",
            repo_root=config.command_cwd,
            resolution_context=planning_context,
        )
        target_paths = sort_delivery_target_paths(target_paths)
    drop_accepted_target_findings(filtered_target_candidates, target_paths)
    target_files = []
    for path in target_paths:
        confidence = source_by_path.get(path, "project_evidence")
        exists = (repo / path).exists()
        bucket = delivery_non_target_bucket(path, exists, planning_context, confidence)
        if bucket:
            bucket_name, reason = bucket
            append_classified_context_path(classified_context_paths, bucket_name, path)
            add_filtered_target_finding(filtered_target_candidates, path, "delivery_plan_target_convergence_final", reason, path)
            continue
        item = {"path": path, "reason": target_file_reason(path, confidence, exists, planning_context), "confidence": confidence}
        rationale = create_if_missing_rationale(path, planning_context) if not exists else ""
        if rationale:
            item["create_if_missing"] = True
            item["create_if_missing_rationale"] = rationale
        target_files.append(item)
    discovery_required = not target_files
    implementation_steps: list[dict[str, Any]] = [
        {
            "id": "confirm-scope",
            "description": (
                "Use repository search, project memory, git context, and graphify context to locate exact business files before editing."
                if discovery_required
                else "Confirm every listed repo-relative business target exists or has an explicit create-if-missing rationale before editing."
            ),
            "required": True,
        }
    ]
    for index, item in enumerate(target_files[:12], start=1):
        path = item["path"]
        implementation_steps.append(
            {
                "id": f"file-{index}",
                "path": path,
                "description": implementation_step_description(path, item),
                "required": True,
            }
        )
    implementation_steps.extend(
        [
            {
                "id": "verify-targeted",
                "description": "Run targeted pytest/compileall/API smoke/git checks listed in verification_commands and record concrete command outcomes.",
                "required": True,
            },
            {
                "id": "publish-containment",
                "description": "Before git publish, prove the accepted diff contains only approved repo changes, excludes runtime artifacts and unrelated dirty worktree paths, and verify origin/main contains the pushed commit when publish is enabled.",
                "required": True,
            },
            {
                "id": "manual-channel-acceptance-boundary",
                "description": "If real communication-channel send/read proof is required but absent, stop final acceptance with blocked_manual_acceptance_required instead of claiming channel acceptance passed.",
                "required": True,
            },
        ]
    )
    scope_slices = plan_scope_slices(requirement, requirements_review, repair_context)
    deferred_slices: list[dict[str, Any]] = []
    must_change_targets = build_must_change_targets(target_files)
    api_contracts = extract_api_contracts(original_requirement_full, requirements_discussion, requirements_review, repair_context, research)
    forbidden_targets = [
        ".env",
        "auth.json",
        "credential-imports",
        "OAuth/cookie/token/API key/private key files",
        "runtime homes outside the command repository",
        "pipeline-runs/**",
        "command-runs/**",
        "agent-workspaces/**",
        "graphify-out/**",
        "setup.py / packaging / dependency files",
        "docs/research/** as target_files/must_change_targets",
        "MEMORY.md / memory/** / docs/INDEX.md / todo.md / done.md as target_files/must_change_targets",
        "unrelated legacy modules and generated caches",
        "credential-bearing private account/auth files",
    ]
    runtime_contracts = [
        "Business-operation keywords are not workflow risk gates.",
        "Do not treat runtime/API/data-contract prose as target_files; encode them here or in api_contracts instead.",
        "Verification, code review, and git_publish failures must return to development with the concrete failure reason.",
    ]
    risk_boundaries = [
        {"name": "git_publish_secret_scan", "allowed": False, "description": "Git publish must block staged diffs containing real passwords, tokens, cookies, private keys, or credential material."},
    ]
    return {
        "schema_version": "delivery-plan/v1",
        "task_type": task_type,
        "owner": infer_code_agent(classification_text, config),
        "source_artifacts": {
            key: artifacts[key]
            for key in (
                "resolved_requirement",
                "requirements_review",
                "requirements_discussion",
                "external_research",
                "project_memory_context",
                "git_repository_context",
                "graphify_context",
            )
            if key in artifacts
        },
        "runtime": {
            "host": runtime.get("host", ""),
            "runtime_home": runtime.get("runtime_home", ""),
        },
        "scope_slices": scope_slices,
        "task_split_policy": {
            "enabled": False,
            "current_slice_id": scope_slices[0].get("id", "holistic-scope") if scope_slices else "holistic-scope",
            "deferred_slice_ids": [str(item.get("id")) for item in deferred_slices],
            "rule": "Task-splitting granularity control is disabled for the OpenClaw backup multi-agent workflow; reviewers and implementers consider the whole accepted requirement together until all reviewer blockers are resolved.",
        },
        "target_files": target_files,
        "must_change_targets": must_change_targets,
        "read_only_sources": [
            {"path": path, "reason": "Mentioned as read-only/inspect-only source during requirements or review readiness discussion."}
            for path in classified_context_paths.get("read_only_sources", [])
        ],
        "reference_patterns": [
            {"path": path, "reason": "Mentioned as a reference pattern/example, not a required implementation target."}
            for path in classified_context_paths.get("reference_patterns", [])
        ],
        "inspect_only_sources": [
            {"path": path, "reason": "Mentioned as inspect-only/conditional context and excluded from required target_files."}
            for path in classified_context_paths.get("inspect_only_sources", [])
        ],
        "runtime_contracts": runtime_contracts,
        "api_contracts": api_contracts,
        "forbidden_targets": forbidden_targets,
        "solution_review_readiness": {
            "target_files_contract": "Only concrete repo-relative files expected to be created or modified may appear in target_files.",
            "non_target_contract": "read_only_sources, reference_patterns, inspect_only_sources, runtime_contracts, and api_contracts are not implementation targets; must_change_targets mirrors the required edit/create subset.",
            "pre_review_self_check": [
                "No credential/auth/secret files in target_files or executable steps.",
                "No runtime/API/data-contract pseudo paths in target_files.",
                "Must-change, inspect-only, and reference-pattern files are separated before solution_review.",
                "Verification commands are deterministic and command-level.",
            ],
        },
        "entry_points": [
            {"path": path["path"], "reason": path["reason"]}
            for path in target_files
            if is_delivery_entry_point(path["path"])
        ],
        "out_of_scope": [
            "Do not broaden the task beyond the accepted requirement.",
            "Do not invent artificial deferred slices; handle the complete accepted requirement.",
            "Do not leak, print, commit, or log secrets, credentials, private keys, cookies, or auth state files.",
        ],
        "implementation_steps": implementation_steps,
        "verification_commands": configured_verification_commands(config, task_type, "\n".join([original_requirement_full, requirements_discussion, requirements_review, git_context, repair_context])),
        "release_gates": [
            "All required verification commands pass.",
            "Dual review gates pass with the expected final verdicts.",
            "Deployment or git publish only runs when explicitly configured by the runner.",
            "If git publish is enabled, prove the pushed commit is contained by origin/main and no runtime/pipeline artifacts or unrelated dirty worktree paths were committed.",
            "If real Discord channel acceptance cannot be safely proven by the runner, final acceptance must stop with blocked_manual_acceptance_required instead of claiming success.",
        ],
        "rollback_plan": [
            "If verification or code review fails after a workspace patch is applied, revert the applied patch and preserve rollback evidence.",
            "If rollback fails, stop with manual_cleanup_required.",
        ],
        "human_blockers": [
            "Stop before any credential, secret value, private key, cookie, or auth state leakage, printing, logging, or commit.",
            "Stop when a destructive repository/data target is unclear.",
            "Stop when required backup, backup verification, audit logging, or restore instruction creation fails.",
            "Target files cannot be located from repository evidence and implementation would require guessing.",
            "blocked_manual_acceptance_required: real Discord channel acceptance cannot be safely proven inside the pipeline.",
        ],
        "risk_boundaries": risk_boundaries,
        "plan_findings": {
            "discovery_required": discovery_required,
            "repair_context_present": bool(repair_context),
            "target_source_policy": (
                "Target files come from the original requirement or repair context first, "
                "then requirements review, then low-trust research/project memory only as fallback. "
                "Pipeline artifacts are ignored. Negated paths, project memory control files, runtime state, "
                "and workflow host paths are filtered and reported."
            ),
            "filtered_target_candidates": filtered_target_candidates,
            "abnormal_feedback_required": bool(filtered_target_candidates),
        },
    }


def render_solution(delivery_plan: dict[str, Any]) -> str:
    target_files = delivery_plan.get("target_files") if isinstance(delivery_plan.get("target_files"), list) else []
    verification_commands = delivery_plan.get("verification_commands") if isinstance(delivery_plan.get("verification_commands"), list) else []
    implementation_steps = delivery_plan.get("implementation_steps") if isinstance(delivery_plan.get("implementation_steps"), list) else []
    human_blockers = delivery_plan.get("human_blockers") if isinstance(delivery_plan.get("human_blockers"), list) else []
    out_of_scope = delivery_plan.get("out_of_scope") if isinstance(delivery_plan.get("out_of_scope"), list) else []
    split_policy = delivery_plan.get("task_split_policy") if isinstance(delivery_plan.get("task_split_policy"), dict) else {}
    plan_findings = delivery_plan.get("plan_findings") if isinstance(delivery_plan.get("plan_findings"), dict) else {}
    filtered_target_candidates = (
        plan_findings.get("filtered_target_candidates")
        if isinstance(plan_findings.get("filtered_target_candidates"), list)
        else []
    )
    return "\n".join(
        [
            "# Solution Package",
            "",
            "## Delivery Plan Contract",
            "- Source of truth: `delivery_plan.json`",
            f"- Schema: {delivery_plan.get('schema_version', 'delivery-plan/v1')}",
            f"- Task type: {delivery_plan.get('task_type', 'feature')}",
            f"- Owner: {delivery_plan.get('owner', 'backend-dev')}",
            "",
            "## Scope Slices",
            render_markdown_items(
                [
                    f"{item.get('id', 'slice')}: {item.get('description', '')}"
                    + (f" ({item.get('status')})" if item.get("status") else "")
                    for item in delivery_plan.get("scope_slices", [])
                    if isinstance(item, dict)
                ]
            ),
            "",
            "## Task Split Policy",
            render_markdown_items(
                [
                    str(split_policy.get("rule", "")),
                    f"current_slice_id: {split_policy.get('current_slice_id', '')}",
                    f"deferred_slice_ids: {', '.join(split_policy.get('deferred_slice_ids', []))}"
                    if isinstance(split_policy.get("deferred_slice_ids"), list) and split_policy.get("deferred_slice_ids")
                    else "",
                ]
            ),
            "",
            "## Target Files",
            render_markdown_items([item.get("path", "") for item in target_files if isinstance(item, dict)] or ["Discovery required before editing; do not guess."]),
            "",
            "## Must-change Targets",
            render_markdown_items([item.get("path", "") for item in delivery_plan.get("must_change_targets", []) if isinstance(item, dict)] or ["No must-change targets declared; revise before implementation."]),
            "",
            "## Read-only Sources",
            render_markdown_items([item.get("path", "") for item in delivery_plan.get("read_only_sources", []) if isinstance(item, dict)] or ["No read-only sources declared."]),
            "",
            "## Reference Patterns",
            render_markdown_items([item.get("path", "") for item in delivery_plan.get("reference_patterns", []) if isinstance(item, dict)] or ["No reference patterns declared."]),
            "",
            "## Inspect-only Sources",
            render_markdown_items([item.get("path", "") for item in delivery_plan.get("inspect_only_sources", []) if isinstance(item, dict)] or ["No inspect-only sources declared."]),
            "",
            "## API Contracts",
            render_markdown_items([f"{item.get('endpoint', '')}: {item.get('contract', '')}" for item in delivery_plan.get("api_contracts", []) if isinstance(item, dict)] or ["No API contracts declared."]),
            "",
            "## Solution Review Readiness",
            render_markdown_items([
                str(delivery_plan.get("solution_review_readiness", {}).get("target_files_contract", "")) if isinstance(delivery_plan.get("solution_review_readiness"), dict) else "",
                str(delivery_plan.get("solution_review_readiness", {}).get("non_target_contract", "")) if isinstance(delivery_plan.get("solution_review_readiness"), dict) else "",
            ]),
            "",
            "## Filtered Target Candidates",
            render_markdown_items(
                [
                    f"{item.get('path', '')}: {item.get('reason', '')} (source: {item.get('source', '')})"
                    for item in filtered_target_candidates
                    if isinstance(item, dict)
                ]
                or ["No filtered target candidates."]
            ),
            "",
            "## Implementation Steps",
            render_markdown_items([item.get("description", "") for item in implementation_steps if isinstance(item, dict)]),
            "",
            "## Verification Commands",
            render_markdown_items([item.get("command", "") for item in verification_commands if isinstance(item, dict)]),
            "",
            "## Out Of Scope",
            render_markdown_items([str(item) for item in out_of_scope]),
            "",
            "## Human Blockers",
            render_markdown_items([str(item) for item in human_blockers]),
            "",
            "## Review Contract",
            "Reviewers must validate `delivery_plan.json`, not prose shape alone. The plan is not ready for implementation if it lacks scope, target discovery, verification commands, release gates, rollback behavior, or human blockers.",
        ]
    )


def clip_text(value: str, limit: int = 12000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... truncated {len(text) - limit} chars ..."


def normalize_code_agent(value: str | None) -> str:
    agent = str(value or "").strip()
    return agent if agent in {"backend-dev", "frontend-dev"} else "backend-dev"


def stage_agent_ids(stage_name: str, config: PipelineConfig | None = None) -> list[str]:
    raw = normalize_code_agent(config.code_agent) if stage_name == "code_execution" and config else STAGE_AGENT_MAP.get(stage_name, "coordinator")
    agents = [part.strip() for part in str(raw).split(",") if part.strip()]
    return agents or ["coordinator"]


def agent_workspace_base(config: PipelineConfig, run_dir: Path) -> Path:
    if config.agent_workspace_root is not None:
        root = config.agent_workspace_root.expanduser()
        return root / run_dir.name if root.name != run_dir.name else root
    return run_dir / "agent-workspaces"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def ensure_agent_repo(base_cwd: Path, workspace_dir: Path) -> tuple[Path, str, bool]:
    repo_dir = workspace_dir / "repo"
    if repo_dir.exists():
        return repo_dir, "worktree", True

    workspace_dir.mkdir(parents=True, exist_ok=True)
    try:
        nested_under_base = repo_dir.resolve().is_relative_to(base_cwd.resolve())
    except OSError:
        nested_under_base = False
    if nested_under_base:
        raise PipelineError(
            f"agent workspace root must be outside command cwd for git worktree mode: "
            f"repo={repo_dir} command_cwd={base_cwd}"
        )
    inside = run_git(["rev-parse", "--is-inside-work-tree"], base_cwd)
    head = run_git(["rev-parse", "HEAD"], base_cwd)
    if inside.returncode != 0 or head.returncode != 0:
        raise PipelineError(f"agent workspaces require a git repository with HEAD: {base_cwd}")
    proc = run_git(["worktree", "add", "--detach", str(repo_dir), "HEAD"], base_cwd)
    if proc.returncode != 0:
        raise PipelineError(f"failed to create git worktree at {repo_dir}: {proc.stderr.strip()}")
    return repo_dir, "worktree", True


def apply_patch_file(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    if not patch_file.exists() or patch_file.stat().st_size == 0:
        return {"ok": True, "applied": False, "returncode": 0, "stderr": ""}
    proc = run_git(["apply", "--whitespace=nowarn", str(patch_file)], repo_dir)
    return {
        "ok": proc.returncode == 0,
        "applied": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": clip_text(proc.stdout),
        "stderr": clip_text(proc.stderr),
    }


def git_status_porcelain(repo_dir: Path) -> dict[str, Any]:
    proc = run_git(["status", "--porcelain"], repo_dir)
    status = proc.stdout or ""
    return {
        "ok": proc.returncode == 0 and not status.strip(),
        "returncode": proc.returncode,
        "dirty": bool(status.strip()),
        "stdout": clip_text(status),
        "stderr": clip_text(proc.stderr),
    }


def status_paths(porcelain: str) -> set[str]:
    paths: set[str] = set()
    for line in str(porcelain or "").splitlines():
        if not line.strip() or len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.rsplit(" -> ", 1)[-1].strip()
        paths.add(raw.strip('"'))
    return paths


def patch_paths(patch_file: Path) -> set[str]:
    paths: set[str] = set()
    try:
        content = patch_file.read_text(encoding="utf-8")
    except OSError:
        return paths
    for line in content.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) >= 4:
            path = parts[3]
            if path.startswith("b/"):
                path = path[2:]
            paths.add(path.strip('"'))
    return paths


def command_cwd_patch_preflight(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    status = git_status_porcelain(repo_dir)
    dirty_paths = status_paths(str(status.get("stdout") or ""))
    changed_paths = patch_paths(patch_file)
    overlapping = sorted(dirty_paths & changed_paths)
    return {
        "ok": status.get("returncode") == 0 and not overlapping,
        "returncode": status.get("returncode", 0),
        "dirty": bool(dirty_paths),
        "dirty_paths": sorted(dirty_paths),
        "patch_paths": sorted(changed_paths),
        "overlapping_dirty_paths": overlapping,
        "stdout": status.get("stdout", ""),
        "stderr": status.get("stderr", ""),
    }


def reverse_patch_file(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    if not patch_file.exists() or patch_file.stat().st_size == 0:
        return {"ok": True, "reverted": False, "returncode": 0, "stderr": ""}
    proc = run_git(["apply", "-R", "--whitespace=nowarn", str(patch_file)], repo_dir)
    return {
        "ok": proc.returncode == 0,
        "reverted": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": clip_text(proc.stdout),
        "stderr": clip_text(proc.stderr),
    }


def rollback_applied_code_patch(
    config: PipelineConfig,
    run_dir: Path,
    artifacts: dict[str, str],
    patch_file: Path | None,
    reason: str,
) -> dict[str, Any]:
    if patch_file is None:
        return {"ok": True, "reverted": False, "reason": reason, "patch_file": ""}
    report = reverse_patch_file(config.command_cwd.expanduser().resolve(), patch_file)
    report["reason"] = reason
    report["patch_file"] = str(patch_file)
    report_file = run_dir / "command-runs" / f"rollback-{slugify(reason)}.json"
    report["report_file"] = str(report_file)
    write_json(report_file, report)
    artifacts[f"rollback_{slugify(reason)}"] = str(report_file)
    return report


def rollback_failed(report: dict[str, Any]) -> bool:
    return bool(report.get("patch_file")) and not bool(report.get("ok"))


def rollback_failure_detail(report: dict[str, Any]) -> str:
    stderr = str(report.get("stderr") or "").strip()
    return (
        "failed to rollback an unaccepted code workspace patch from command cwd; "
        "manual cleanup is required before continuing"
        + (f": {clip_text(stderr, 600)}" if stderr else "")
    )


def export_workspace_patch(repo_dir: Path, patch_file: Path) -> dict[str, Any]:
    inside = run_git(["rev-parse", "--is-inside-work-tree"], repo_dir)
    if inside.returncode != 0:
        return {
            "ok": False,
            "patch_file": str(patch_file),
            "stderr": "workspace repo is not a git repository; cannot export workspace diff",
        }
    run_git(["add", "-N", "."], repo_dir)
    proc = run_git(["diff", "--binary"], repo_dir)
    if proc.returncode != 0:
        return {
            "ok": False,
            "patch_file": str(patch_file),
            "stdout": clip_text(proc.stdout),
            "stderr": clip_text(proc.stderr),
        }
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(proc.stdout or "", encoding="utf-8")
    return {
        "ok": True,
        "patch_file": str(patch_file),
        "has_changes": bool((proc.stdout or "").strip()),
        "stdout": "",
        "stderr": "",
    }


def update_agent_workspace_manifest(run_dir: Path, stage_name: str, index: int, workspaces: list[AgentWorkspace]) -> Path:
    manifest_file = run_dir / "agent-workspaces" / "manifest.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    manifest.setdefault("stages", {})
    manifest["updated_at"] = utc_now()
    manifest["stages"].setdefault(stage_name, {})
    manifest["stages"][stage_name][str(index)] = [workspace.as_dict() for workspace in workspaces]
    write_json(manifest_file, manifest)
    return manifest_file


def prepare_agent_workspaces(
    config: PipelineConfig,
    run_dir: Path,
    stage_name: str,
    index: int,
    base_cwd: Path,
    input_patch_file: Path | None = None,
) -> list[AgentWorkspace]:
    workspaces: list[AgentWorkspace] = []
    root = agent_workspace_base(config, run_dir)
    for agent_index, agent_id in enumerate(stage_agent_ids(stage_name, config)):
        workspace_dir = root / slugify(stage_name) / slugify(agent_id)
        repo_preexisted = (workspace_dir / "repo").exists()
        repo_dir, effective_mode, isolated = ensure_agent_repo(base_cwd, workspace_dir)
        workspace = AgentWorkspace(
            stage=stage_name,
            agent_id=agent_id,
            workspace_dir=workspace_dir,
            repo_dir=repo_dir,
            mode=effective_mode,
            isolated=isolated,
            primary=agent_index == 0,
        )
        if agent_index == 0 and input_patch_file and isolated and not repo_preexisted:
            result = apply_patch_file(repo_dir, input_patch_file)
            if not result.get("ok"):
                raise PipelineError(
                    f"failed to apply prior code workspace diff to {agent_id} workspace: "
                    f"{result.get('stderr', '')}"
                )
        workspaces.append(workspace)
    update_agent_workspace_manifest(run_dir, stage_name, index, workspaces)
    return workspaces


def command_env(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    requirement: str,
    stage_name: str = "",
    primary_workspace: AgentWorkspace | None = None,
    workspaces: list[AgentWorkspace] | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    requirement_file = run_dir / "requirement.txt"
    if not requirement_file.exists():
        write_text(requirement_file, requirement)
    memory_dir = project_memory_dir(config)
    env.update(
        {
            "PIPELINE_RUN_DIR": str(run_dir),
            "PIPELINE_REQUIREMENT_FILE": str(requirement_file),
            "PIPELINE_PROJECT_KEY": config.project_key,
            "PIPELINE_RUNTIME_HOST": str(runtime.get("host", "")),
            "PIPELINE_RUNTIME_HOME": str(runtime.get("runtime_home", "")),
            "PIPELINE_PROJECT_MEMORY_DIR": str(memory_dir),
            "PIPELINE_RESEARCH_REPORT_FILE": str(run_dir / "research_report.md"),
            "PIPELINE_REQUIREMENTS_FILE": str(run_dir / "requirements.md"),
            "PIPELINE_REQUIREMENTS_DISCUSSION_FILE": str(run_dir / "requirements_discussion.md"),
            "PIPELINE_REQUIREMENTS_REVIEW_FILE": str(run_dir / "requirements_review.md"),
            "PIPELINE_DELIVERY_PLAN_FILE": str(run_dir / "delivery_plan.json"),
            "PIPELINE_SOLUTION_FILE": str(run_dir / "solution.md"),
            "PIPELINE_SOLUTION_REVIEW_FILE": str(run_dir / "solution_review.md"),
            "PIPELINE_SOLUTION_REVIEW_SOFT_GATE_FILE": str(run_dir / "solution_review_soft_gate.md"),
            "PIPELINE_PATCH_SUMMARY_FILE": str(run_dir / "patch_summary.md"),
            "PIPELINE_VERIFICATION_REPORT_FILE": str(run_dir / "verification_report.md"),
            "PIPELINE_CODE_REVIEW_FILE": str(run_dir / "code_review.md"),
            "PIPELINE_DEPLOYMENT_REPORT_FILE": str(run_dir / "deployment_report.md"),
            "PIPELINE_WRITEBACK_REPORT_FILE": str(run_dir / "writeback_report.md"),
            "PIPELINE_GIT_PUBLISH_REPORT_FILE": str(run_dir / "git_publish_report.md"),
            "PIPELINE_GRAPHIFY_CONTEXT_FILE": str(run_dir / "graphify_context.md"),
            "PIPELINE_GRAPHIFY_SCOPE_VALIDATION_FILE": str(run_dir / "graphify_scope_validation.md"),
        }
    )
    if stage_name:
        env["PIPELINE_STAGE_NAME"] = stage_name
    if primary_workspace is not None:
        env.update(
            {
                "PIPELINE_AGENT_ID": primary_workspace.agent_id,
                "PIPELINE_AGENT_WORKSPACE": str(primary_workspace.workspace_dir),
                "PIPELINE_AGENT_REPO_DIR": str(primary_workspace.repo_dir),
                "PIPELINE_AGENT_WORKSPACE_MODE": primary_workspace.mode,
                "PIPELINE_AGENT_WORKSPACE_ISOLATED": "1" if primary_workspace.isolated else "0",
            }
        )
    if workspaces is not None:
        env["PIPELINE_AGENT_WORKSPACES_JSON"] = json.dumps(
            [workspace.as_dict() for workspace in workspaces],
            ensure_ascii=False,
        )
    return env


def run_stage_command(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    artifacts: dict[str, str],
    requirement: str,
    stage_name: str,
    command: str,
    index: int = 1,
    input_patch_file: Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    command_text = str(command or "").strip()
    if not command_text:
        raise PipelineError(f"{stage_name} command must not be empty")
    base_cwd = config.command_cwd.expanduser().resolve()
    if not base_cwd.exists() or not base_cwd.is_dir():
        raise PipelineError(f"command cwd not found: {base_cwd}")
    workspaces = prepare_agent_workspaces(config, run_dir, stage_name, index, base_cwd, input_patch_file)
    primary_workspace = workspaces[0]
    cwd = primary_workspace.repo_dir
    if progress_callback is not None:
        progress_callback(stage_name, f"running command {index} in {primary_workspace.agent_id}")

    started_at = utc_now()
    stdout = ""
    stderr = ""
    returncode = 124
    timed_out = False
    error = ""
    workspace_patch: dict[str, Any] = {}
    try:
        proc = subprocess.run(
            command_text,
            shell=True,
            cwd=str(cwd),
            env=command_env(config, run_dir, runtime, requirement, stage_name, primary_workspace, workspaces),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(config.command_timeout_seconds or 600)),
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        error = f"timeout after {config.command_timeout_seconds}s"
    runtime_refs = extract_agent_runtime_refs(stdout, stderr)

    if (
        stage_name in {"code_execution", "memory_writeback"}
        and returncode == 0
        and not timed_out
        and primary_workspace.isolated
    ):
        patch_file = run_dir / "command-runs" / f"{stage_name}-{index}.patch"
        workspace_patch = export_workspace_patch(primary_workspace.repo_dir, patch_file)
        if (
            stage_name == "code_execution"
            and workspace_patch.get("ok")
            and workspace_patch.get("has_changes")
        ):
            preflight = command_cwd_patch_preflight(base_cwd, patch_file)
            workspace_patch["command_cwd_preflight"] = preflight
            if not preflight.get("ok"):
                returncode = 1
                error = (
                    "command cwd has uncommitted changes overlapping the code workspace diff; "
                    "refusing to apply patch before verification and code review"
                )
                workspace_patch["applied_to_command_cwd"] = {
                    "ok": False,
                    "applied": False,
                    "returncode": int(preflight.get("returncode") or 1),
                    "stderr": preflight.get("stderr", ""),
                }
            else:
                apply_result = apply_patch_file(base_cwd, patch_file)
                workspace_patch["applied_to_command_cwd"] = apply_result
                if not apply_result.get("ok"):
                    returncode = int(apply_result.get("returncode") or 1)
                    error = f"failed to apply code workspace diff to command cwd: {apply_result.get('stderr', '')}"
        elif not workspace_patch.get("ok"):
            returncode = 1
            error = f"failed to export code workspace diff: {workspace_patch.get('stderr', '')}"

    report = {
        "stage": stage_name,
        "index": index,
        "command": command_text,
        "cwd": str(cwd),
        "command_cwd": str(base_cwd),
        "agent_id": primary_workspace.agent_id,
        "agent_workspace": primary_workspace.as_dict(),
        "agent_workspaces": [workspace.as_dict() for workspace in workspaces],
        "dispatch_mode": "native-agent-session" if runtime_refs else "isolated-agent-workspace",
        "runtime_agent_refs": runtime_refs,
        "agent_session_id": runtime_refs.get("session_id", ""),
        "agent_run_id": runtime_refs.get("run_id", ""),
        "agent_session_key": runtime_refs.get("session_key", ""),
        "started_at": started_at,
        "ended_at": utc_now(),
        "returncode": returncode,
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "stdout": clip_text(stdout),
        "stderr": clip_text(stderr),
    }
    if workspace_patch:
        report["workspace_patch"] = workspace_patch
        if workspace_patch.get("patch_file"):
            report["workspace_patch_file"] = workspace_patch["patch_file"]
    if stage_name in DUAL_REVIEW_STAGES:
        report["reviewer_role"] = reviewer_role_from_command(command_text) or reviewer_role_from_output(stdout, stderr)
        report["reviewer_provider"] = reviewer_provider_from_output(stdout, stderr) or reviewer_provider_from_command(command_text)
        report["reviewer_model"] = reviewer_model_from_output(stdout, stderr) or reviewer_model_from_command(command_text)
    report_dir = run_dir / "command-runs"
    report_file = report_dir / f"{stage_name}-{index}.json"
    write_json(report_file, report)
    artifacts[f"command_{stage_name}_{index}"] = str(report_file)
    artifacts["agent_workspace_manifest"] = str(run_dir / "agent-workspaces" / "manifest.json")
    return report


def run_stage_commands(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    artifacts: dict[str, str],
    requirement: str,
    stage_name: str,
    commands: tuple[str, ...],
    input_patch_file: Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    return [
        run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            stage_name,
            command,
            index,
            input_patch_file,
            progress_callback,
        )
        for index, command in enumerate(commands, start=1)
    ]


def commands_ok(reports: list[dict[str, Any]]) -> bool:
    return bool(reports) and all(bool(item.get("ok")) for item in reports)


def command_markdown(title: str, reports: list[dict[str, Any]]) -> str:
    lines = [f"## {title}"]
    for item in reports:
        lines.extend(
            [
                f"### Command {item.get('index')}",
                f"- cwd: `{item.get('cwd', '')}`",
                f"- agent: `{item.get('agent_id', '')}`",
                f"- dispatch: `{item.get('dispatch_mode', '')}`",
                f"- returncode: {item.get('returncode')}",
                f"- ok: {str(item.get('ok')).lower()}",
                "",
                "```text",
                str(item.get("command", "")),
                "```",
            ]
        )
        stdout = str(item.get("stdout", "")).strip()
        stderr = str(item.get("stderr", "")).strip()
        if stdout:
            lines.extend(["", "#### stdout", "```text", stdout, "```"])
        if stderr:
            lines.extend(["", "#### stderr", "```text", stderr, "```"])
    return "\n".join(lines)


def render_patch_summary(config: PipelineConfig, command_report: dict[str, Any] | None = None) -> str:
    if command_report is not None:
        return dedent(
            f"""
            # Patch Summary

            ## Mode
            Live command adapter.

            ## Result
            - Status: {"pass" if command_report.get("ok") else "fail"}
            - Return code: {command_report.get("returncode")}
            - Command evidence: `command-runs/code_execution-1.json`
            - Agent: `{command_report.get("agent_id", "")}`
            - Agent repo: `{command_report.get("cwd", "")}`
            - Workspace diff: `{command_report.get("workspace_patch_file", "") or "not_applicable"}`

            {command_markdown("Coding Command", [command_report])}

            ## Handoff
            Runtime agent output above is treated as the implementation handoff. When the
            command ran in an isolated workspace, the exported workspace diff is applied
            back to the configured command cwd before verification.
            """
        )

    fallback = dedent(
        """
        # Patch Summary

        ## Mode
        Dry-run simulation.

        ## Code Changes
        - No product code was modified by this runner.
        - In a live Hermes run, this artifact is produced by the coding agent after implementation.

        ## Handoff
        - Coding agent must list changed files, behavior changes, tests, and known risks.
        """
    )
    return read_optional_file(config.patch_summary_file, fallback)


def render_verification_report(
    config: PipelineConfig,
    failed: bool,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if command_reports:
        passed = commands_ok(command_reports)
        return dedent(
            f"""
            # Verification Report

            ## Result
            - Status: {"pass" if passed else "fail"}
            - Score: {100 if passed else 55}

            ## Evidence
            - Verification commands executed: {len(command_reports)}
            - Command evidence dir: `command-runs/`

            {command_markdown("Verification Commands", command_reports)}

            ## Failure Class
            - {"none" if passed else "implementation"}
            """
        )

    fallback = dedent(
        f"""
        # Verification Report

        ## Result
        - Status: {"fail" if failed else "pass"}
        - Score: {55 if failed else 100}

        ## Evidence
        - Runner dry-run generated all required orchestration artifacts.
        - Live implementation tests must be attached by the coding agent or verifier.

        ## Failure Class
        - {"implementation" if failed else "none"}
        """
    )
    if config.verification_report_file and not failed:
        return read_optional_file(config.verification_report_file, fallback)
    return fallback


def render_code_review(
    config: PipelineConfig,
    failed: bool,
    command_reports: list[dict[str, Any]] | None = None,
) -> str:
    if command_reports is not None and command_reports:
        return render_dual_ai_review("code_review", command_reports, "requires_revision" if failed else "pass")
    if config.code_review_file and not failed:
        return read_optional_file(config.code_review_file, "")
    verdict = "requires_revision" if failed else "pass"
    return consensus_review("code_review", verdict, "Implementation evidence is attached in patch_summary.md.")


def render_deployment_report(command_report: dict[str, Any] | None) -> str:
    if command_report is not None:
        passed = bool(command_report.get("ok"))
        return dedent(
            f"""
            # Deployment Report

            ## Result
            - Status: {"pass" if passed else "fail"}
            - Return code: {command_report.get("returncode")}
            - Command evidence: `command-runs/deployment-1.json`

            {command_markdown("Deployment Command", [command_report])}
            """
        )
    return dedent(
        """
        # Deployment Report

        ## Result
        - Status: skipped

        ## Evidence
        - No deployment command was supplied for this run.
        """
    )


def render_git_publish_report(command_report: dict[str, Any]) -> str:
    passed = bool(command_report.get("ok"))
    input_patch = command_report.get("input_patch") or {}
    input_patch_file = input_patch.get("patch_file") or "none"
    input_patch_source = input_patch.get("source") or "unknown"
    return dedent(
        f"""
        # Git Publish Report

        ## Result
        - Status: {"pass" if passed else "fail"}
        - Return code: {command_report.get("returncode")}
        - Command evidence: `command-runs/git_publish-1.json`
        - Input patch: `{input_patch_file}` ({input_patch_source})

        ## Contract
        - Git publish runs only after verification, code review, deployment if supplied, acceptance, and memory writeback.
        - Commit message and publish notes must be written in Chinese.
        - Force push and secret-bearing diffs are not allowed.

        {command_markdown("Git Publish Command", [command_report])}
        """
    )


def render_delivery_evidence(score: int, status: str, next_action: str) -> str:
    return dedent(
        f"""
        # Delivery Evidence

        ## Acceptance
        - Status: {status}
        - Score: {score}
        - Next action: {next_action}

        ## Required Evidence
        - Requirement package
        - Solution package
        - Patch summary
        - Verification report
        - Code review
        - Deployment report when a deployment command is supplied
        - Git publish report when a git publish command is supplied
        - Pipeline state
        """
    )


def render_writeback_report(project_key: str, status: str, next_action: str) -> str:
    return dedent(
        f"""
        # Writeback Report

        ## Project
        - Project key: {project_key}
        - Pipeline status: {status}
        - Next action: {next_action}

        ## Memory Contract
        The runner can execute project memory writeback when `--write-project-memory`
        or `--memory-write-command` is supplied. Otherwise this report is a
        recommendation and live completion remains blocked.

        ## Suggested Command
        python scripts/openclaw-ops/project_memory_writer.py --project-key {project_key} --artifact-type changelog --content-file <writeback_report.md> --source project-delivery-pipeline
        """
    )


def repo_root_from_runner() -> Path:
    return Path(__file__).resolve().parents[4]


def find_project_memory_writer(runtime: dict[str, Any]) -> Path | None:
    runtime_home = str(runtime.get("runtime_home", "") or "").strip()
    candidates = [
        repo_root_from_runner() / "scripts" / "openclaw-ops" / "project_memory_writer.py",
    ]
    if runtime_home:
        candidates.append(Path(runtime_home).expanduser() / "ops" / "project_memory_writer.py")
    candidates.append(Path("scripts/openclaw-ops/project_memory_writer.py").resolve())
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def run_builtin_project_memory_writeback(
    config: PipelineConfig,
    run_dir: Path,
    runtime: dict[str, Any],
    writeback_file: Path,
) -> dict[str, Any]:
    writer = find_project_memory_writer(runtime)
    if writer is None:
        return {
            "ok": False,
            "returncode": 2,
            "stage": "memory_writeback",
            "command": "project_memory_writer.py",
            "stdout": "",
            "stderr": "project_memory_writer.py not found in repo or runtime ops",
        }
    cmd = [
        sys.executable,
        str(writer),
        "--data-dir",
        str(config.project_memory_root),
        "--project-key",
        config.project_key,
        "--artifact-type",
        "changelog",
        "--content-file",
        str(writeback_file),
        "--source",
        f"project-delivery:{run_dir.name}",
    ]
    started_at = utc_now()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(config.command_cwd.expanduser().resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(config.command_timeout_seconds or 600)),
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = int(proc.returncode)
        timed_out = False
        error = ""
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        returncode = 124
        timed_out = True
        error = f"timeout after {config.command_timeout_seconds}s"
    return {
        "stage": "memory_writeback",
        "index": 1,
        "command": " ".join(cmd),
        "cwd": str(config.command_cwd.expanduser().resolve()),
        "started_at": started_at,
        "ended_at": utc_now(),
        "returncode": returncode,
        "ok": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "stdout": clip_text(stdout),
        "stderr": clip_text(stderr),
    }


def write_memory_command_report(
    run_dir: Path,
    artifacts: dict[str, str],
    report: dict[str, Any],
) -> Path:
    report_file = run_dir / "command-runs" / "memory_writeback-1.json"
    write_json(report_file, report)
    artifacts["command_memory_writeback_1"] = str(report_file)
    return report_file


def render_memory_writeback_report(reports: list[dict[str, Any]]) -> str:
    return dedent(
        f"""
        # Memory Writeback Evidence

        ## Result
        - Status: {"pass" if commands_ok(reports) else "fail"}
        - Commands: {len(reports)}

        {command_markdown("Memory Writeback Commands", reports)}
        """
    )


def failure_learning_payload(
    config: PipelineConfig,
    run_id: str,
    status: str,
    failed_stage: str | None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "triggered": status != "completed",
        "failed_stage": failed_stage,
        "next_action": next_action,
        "failure_tracker_contract": {
            "command": (
                "python scripts/openclaw-ops/failure_tracker.py record "
                f"--task-id {run_id} --task-type project_delivery_pipeline "
                "--model coordinator "
                f"--project-key {config.project_key} "
                "--failure-reason <reason>"
            )
        },
        "timestamp": utc_now(),
    }


def pipeline_state(
    config: PipelineConfig,
    run_id: str,
    run_dir: Path,
    runtime: dict[str, Any],
    stages: list[StageRecord],
    artifacts: dict[str, str],
    status: str,
    next_action: str,
    failed_stage: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_key": config.project_key,
        "status": status,
        "next_action": next_action,
        "failed_stage": failed_stage,
        "dry_run": config.dry_run,
        "runtime_context": runtime,
        "run_dir": str(run_dir),
        "artifacts": artifacts,
        "stage_agents": {
            stage.name: stage_agent_ids(stage.name, config)
            for stage in stages
        },
        "agent_invocations": pipeline_agent_invocations(artifacts, run_dir),
        "stages": [stage.as_dict() for stage in stages],
        "updated_at": utc_now(),
    }


def policy_dir_candidates() -> list[Path]:
    current = Path(__file__).resolve()
    return [
        current.parent / "policy",
        current.parents[2] / "control-plane-ops" / "scripts" / "policy",
    ]


def policy_dir() -> Path:
    candidates = policy_dir_candidates()
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def load_task_center_classes() -> tuple[Any, Any]:
    path = policy_dir()
    if not path.exists():
        candidates = ", ".join(str(candidate) for candidate in policy_dir_candidates())
        raise PipelineError(f"task-center policy dir not found: {path}; checked: {candidates}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        from task_center import TaskCenter, TaskCenterError  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive import boundary
        raise PipelineError(f"failed to load task-center integration: {exc}") from exc
    return TaskCenter, TaskCenterError


def task_center_db_path(config: PipelineConfig) -> Path:
    if config.task_center_db is not None:
        return config.task_center_db.expanduser()
    return config.workspace_root.parent / "task-center" / "task_center.db"


def task_center_task_id(config: PipelineConfig, run_id: str) -> str:
    return config.task_center_task_id or f"project-delivery:{run_id}"


TASK_CENTER_UPDATE_FIELDS = {
    "task_type",
    "reason",
    "source",
    "request_source",
    "trace_id",
    "attempt_id",
    "priority",
    "risk_level",
    "assignee",
    "status",
    "retry_count",
    "failure_count",
    "need_human_confirm",
    "human_confirmed",
    "needs_clarification",
    "clarification_reason",
    "context_completeness",
    "context_fields_missing",
    "context_fields_recommended_missing",
    "context_payload",
    "review_status",
    "review_mode",
    "review_head",
    "reviewed_at",
    "owner",
    "change_id",
    "requirement",
    "result_output",
    "acceptance",
    "observable_outputs",
    "acceptance_thresholds",
    "stage_id",
    "stage_score_gate",
    "stage_min_evidence_count",
    "stage_output_contract",
    "stage_verification_contract",
    "required_capabilities",
    "required_skills",
    "allowed_agents",
    "workflow_profile_id",
    "workflow_channel",
    "selection_reason",
    "selection_inputs",
    "score_raw",
    "score_normalized",
    "score_payload",
    "token_usage_summary",
    "cost_estimate_total",
    "action",
    "scheduled_at",
    "started_at",
    "completed_at",
}


def stage_output_ref(run_dir: Path, stage: dict[str, Any]) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    path = Path(artifact)
    if path.is_absolute():
        return str(path)
    return str(run_dir / artifact)


def command_reports_from_artifacts(
    artifacts: dict[str, Any],
    run_dir: Path,
    stage_name: str = "",
) -> list[tuple[str, str, dict[str, Any]]]:
    prefix = f"command_{stage_name}_" if stage_name else "command_"
    reports: list[tuple[str, str, dict[str, Any]]] = []
    for key, value in sorted(artifacts.items()):
        if not str(key).startswith(prefix):
            continue
        path = Path(str(value))
        if not path.is_absolute():
            path = run_dir / path
        if not path.exists():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(report, dict):
            reports.append((str(key), str(path), report))
    return reports


def agent_invocation_from_report(
    report: dict[str, Any],
    *,
    artifact_key: str = "",
    artifact_ref: str = "",
) -> dict[str, Any]:
    stage_name = str(report.get("stage") or "").strip()
    returncode = int(report.get("returncode") or 0)
    ok = bool(report.get("ok"))
    return {
        "stage": stage_name,
        "index": int(report.get("index") or 0),
        "agent_id": str(report.get("agent_id") or STAGE_AGENT_MAP.get(stage_name, "coordinator")).strip(),
        "dispatch_mode": str(report.get("dispatch_mode") or "").strip(),
        "session_id": str(report.get("agent_session_id") or "").strip(),
        "run_id": str(report.get("agent_run_id") or "").strip(),
        "session_key": str(report.get("agent_session_key") or "").strip(),
        "status": "completed" if ok else "failed",
        "returncode": returncode,
        "completed": ok,
        "failure_reason": str(report.get("error") or report.get("stderr") or "").strip()[:600],
        "command_ref": artifact_ref,
        "artifact_key": artifact_key,
    }


def agent_invocations_from_reports(
    reports: list[tuple[str, str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        agent_invocation_from_report(report, artifact_key=artifact_key, artifact_ref=artifact_ref)
        for artifact_key, artifact_ref, report in reports
    ]


def pipeline_agent_invocations(
    artifacts: dict[str, Any],
    run_dir: Path,
) -> list[dict[str, Any]]:
    return agent_invocations_from_reports(command_reports_from_artifacts(artifacts, run_dir))


def stage_command_execution_details(state: dict[str, Any], stage_name: str) -> dict[str, Any]:
    artifacts = state.get("artifacts", {})
    run_dir = Path(str(state.get("run_dir") or "."))
    report_items = command_reports_from_artifacts(artifacts, run_dir, stage_name)
    command_refs = {artifact_key: artifact_ref for artifact_key, artifact_ref, _report in report_items}
    reports = [report for _artifact_key, _artifact_ref, report in report_items]
    agent_workspaces: list[dict[str, Any]] = []
    for report in reports:
        for workspace in report.get("agent_workspaces", []) or []:
            if isinstance(workspace, dict):
                agent_workspaces.append(workspace)
    return {
        "command_run_refs": command_refs,
        "dispatch_mode": reports[0].get("dispatch_mode") if reports else "state-machine",
        "agent_id": reports[0].get("agent_id") if reports else STAGE_AGENT_MAP.get(stage_name, "coordinator"),
        "agent_workspaces": agent_workspaces,
        "workspace_patch_files": [
            report.get("workspace_patch_file")
            for report in reports
            if report.get("workspace_patch_file")
        ],
        "agent_invocations": agent_invocations_from_reports(report_items),
    }


def mirror_state_to_task_center(config: PipelineConfig, state: dict[str, Any], requirement: str) -> dict[str, Any] | None:
    if not config.record_task_center:
        return None

    TaskCenter, TaskCenterError = load_task_center_classes()
    db_path = task_center_db_path(config)
    task_id = task_center_task_id(config, str(state["run_id"]))
    status = "passed" if state["status"] == "completed" else "failed"
    action = "complete" if status == "passed" else str(state.get("next_action", ""))
    run_dir = Path(str(state["run_dir"]))
    memory_dir = project_memory_dir(config)
    stage_names = [str(item.get("name", "")) for item in state.get("stages", []) if item.get("name")]
    context_payload = {
        "pipeline_state": state,
        "run_dir": str(run_dir),
        "project_memory_dir": str(memory_dir),
        "stage_names": stage_names,
        "agent_invocations": state.get("agent_invocations", []),
    }

    task_payload = {
        "task_id": task_id,
        "pool": "jobs",
        "task_type": "project_delivery_pipeline",
        "reason": f"{config.project_key}: {requirement[:180]}",
        "source": str(state.get("runtime_context", {}).get("host", "project-delivery-pipeline")),
        "request_source": "human",
        "priority": "medium",
        "risk_level": "low",
        "assignee": "coordinator",
        "status": status,
        "requirement": requirement,
        "result_output": f"Pipeline {state['status']} at {state['run_dir']}",
        "acceptance": "delivery_evidence.md and pipeline_state.json must show pass",
        "observable_outputs": ",".join(sorted(str(key) for key in state.get("artifacts", {}).keys())),
        "requirements_discussion_agents": "project-agent,reviewer",
        "acceptance_thresholds": (
            "requirements_review=ready_for_solution,"
            "solution_review=ready_for_implement,verification=pass,code_review=pass,"
            "acceptance=pass,git_publish=pass_when_supplied"
        ),
        "required_capabilities": "project_memory_retrieval,external_research,coding,verification,code_review,git_publish",
        "required_skills": "project-delivery-pipeline",
        "allowed_agents": "coordinator,project-agent,web-agent,reviewer,backend-dev,frontend-dev,tester,deployer,doc-writer",
        "workflow_profile_id": "project-delivery-pipeline@stable",
        "workflow_channel": "stable",
        "selection_reason": "single controlled coding delivery pipeline",
        "selection_inputs": {
            "run_id": state["run_id"],
            "runtime_context": state.get("runtime_context", {}),
            "project_memory_dir": str(memory_dir),
        },
        "context_payload": context_payload,
        "score_raw": 100 if status == "passed" else 0,
        "score_normalized": 100 if status == "passed" else 0,
        "score_payload": {
            "status": state["status"],
            "next_action": state.get("next_action", ""),
            "failed_stage": state.get("failed_stage"),
        },
        "action": action,
        "started_at": state.get("updated_at", utc_now()),
        "completed_at": utc_now(),
    }

    task_center = TaskCenter(db_path)
    try:
        task_center.init_schema()
        try:
            task_center.get_task(task_id, display_safe=False)
        except TaskCenterError:
            task_center.create_task(task_payload, actor="project-delivery-pipeline")
        else:
            update_fields = {key: value for key, value in task_payload.items() if key in TASK_CENTER_UPDATE_FIELDS}
            task_center.update_task(task_id, actor="project-delivery-pipeline", fields=update_fields)

        for stage in state.get("stages", []):
            stage_name = str(stage.get("name", "")).strip()
            if not stage_name:
                continue
            agent_id = STAGE_AGENT_MAP.get(stage_name, "coordinator")
            output_ref = stage_output_ref(run_dir, stage)
            execution_details = stage_command_execution_details(state, stage_name)
            model_id = (
                "runtime-agent-workspace"
                if execution_details.get("command_run_refs")
                else "state-machine"
            )
            task_center.start_stage_run(
                task_id=task_id,
                stage=stage_name,
                agent_id=agent_id,
                model_id=model_id,
                input_ref=str(run_dir / "run_meta.json"),
                details={"pipeline_stage": stage, "agent_execution": execution_details},
            )
            stage_status = "passed" if str(stage.get("status")) == "completed" else "failed"
            task_center.finish_stage_run(
                task_id=task_id,
                stage=stage_name,
                status=stage_status,
                exit_code=0 if stage_status == "passed" else 1,
                error_reason=str(stage.get("detail", "")),
                output_ref=output_ref,
                details={
                    "verdict": stage.get("verdict"),
                    "score": stage.get("score"),
                    "next_action": stage.get("next_action"),
                    "agent_execution": execution_details,
                },
            )
            handoff_agents = [part.strip() for part in str(agent_id).split(",") if part.strip()] or ["coordinator"]
            for handoff_agent in handoff_agents:
                task_center.record_module_communication(
                    task_id=task_id,
                    from_module="coordinator",
                    to_module=handoff_agent,
                    protocol="project-delivery-pipeline",
                    message_type="stage_handoff",
                    status="acked" if stage_status == "passed" else "failed",
                    payload_ref=output_ref,
                    details={
                        "stage": stage_name,
                        "run_id": state["run_id"],
                        "agent_execution": execution_details,
                    },
                    actor="project-delivery-pipeline",
                )

        task_center.record_task_output(
            task_id=task_id,
            output_type="pipeline_state",
            audience="human",
            channel="task-center",
            status="prepared",
            summary=f"Project delivery pipeline {state['status']}; next_action={state.get('next_action', '')}",
            payload={
                "run_id": state["run_id"],
                "run_dir": state["run_dir"],
                "status": state["status"],
                "next_action": state.get("next_action", ""),
                "failed_stage": state.get("failed_stage"),
                "project_memory_dir": str(memory_dir),
                "artifacts": state.get("artifacts", {}),
                "agent_invocations": state.get("agent_invocations", []),
            },
            actor="project-delivery-pipeline",
        )
        if state["status"] != "completed":
            task_center.record_task_incident(
                task_id=task_id,
                incident_type="pipeline_blocked",
                severity="warning",
                status="open",
                reason=str(state.get("failed_stage", "")),
                summary=f"Pipeline blocked; next_action={state.get('next_action', '')}",
                owner="coordinator",
                details={
                    "run_id": state["run_id"],
                    "failed_stage": state.get("failed_stage"),
                    "next_action": state.get("next_action"),
                },
                actor="project-delivery-pipeline",
            )
    except TaskCenterError as exc:
        raise PipelineError(f"failed to mirror pipeline run to task center: {exc}") from exc
    finally:
        task_center.close()

    return {
        "db": str(db_path),
        "task_id": task_id,
        "status": status,
    }


def finalize_pipeline_state(config: PipelineConfig, state: dict[str, Any], requirement: str) -> dict[str, Any]:
    task_center_ref = mirror_state_to_task_center(config, state, requirement)
    if task_center_ref:
        state["task_center"] = task_center_ref
        write_json(Path(str(state["run_dir"])) / "pipeline_state.json", state)
    return state


def block_pipeline(
    config: PipelineConfig,
    run_id: str,
    run_dir: Path,
    runtime: dict[str, Any],
    stages: list[StageRecord],
    artifacts: dict[str, str],
    stage_name: str,
    next_action: str,
    detail: str,
    artifact: str | None = None,
    verdict: str | None = None,
    score: int | None = None,
) -> dict[str, Any]:
    stages.append(
        StageRecord(
            name=stage_name,
            status="blocked",
            artifact=artifact,
            verdict=verdict,
            score=score,
            next_action=next_action,
            detail=detail,
        )
    )
    failure_path = run_dir / "failure_learning_check.json"
    write_json(failure_path, failure_learning_payload(config, run_id, "blocked", stage_name, next_action))
    artifacts["failure_learning_check"] = str(failure_path)
    failure_summary_path = run_dir / "failure_summary.md"
    write_text(failure_summary_path, render_failure_summary(stage_name, next_action, detail, artifact, verdict, run_dir))
    artifacts["failure_summary"] = str(failure_summary_path)
    state = pipeline_state(config, run_id, run_dir, runtime, stages, artifacts, "blocked", next_action, stage_name)
    write_json(run_dir / "pipeline_state.json", state)
    return state


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    if config.simulate_failure_stage and config.simulate_failure_stage not in SIMULATED_FAILURES:
        raise PipelineError(f"unsupported simulated failure: {config.simulate_failure_stage}")

    requirement = load_requirement(config)
    run_id = config.run_id or default_run_id(config.project_key)
    run_dir = config.workspace_root / run_id
    if run_dir.exists() and any(run_dir.iterdir()) and not config.force:
        raise PipelineError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    runtime = resolve_runtime_context(config)
    stages: list[StageRecord] = []
    artifacts: dict[str, str] = {}

    def write_progress_state(stage_name: str | None = None, detail: str = "") -> None:
        snapshot_stages = list(stages)
        if stage_name:
            snapshot_stages.append(
                StageRecord(
                    name=stage_name,
                    status="running",
                    next_action="continue",
                    detail=detail,
                )
            )
        state = pipeline_state(config, run_id, run_dir, runtime, snapshot_stages, artifacts, "running", "continue")
        write_json(run_dir / "pipeline_state.json", state)

    def record(name: str, file_name: str, content: str, **extra: Any) -> Path:
        path = run_dir / file_name
        write_text(path, content)
        artifacts[name] = str(path)
        stages.append(StageRecord(name=name, status="completed", artifact=file_name, **extra))
        write_progress_state()
        return path

    def record_payload(name: str, file_name: str, payload: dict[str, Any]) -> Path:
        path = run_dir / file_name
        write_json(path, payload)
        artifacts[name] = str(path)
        write_progress_state()
        return path

    meta_path = run_dir / "run_meta.json"
    write_json(meta_path, render_run_meta(config, run_id, requirement, runtime))
    artifacts["run_meta"] = str(meta_path)
    stages.append(StageRecord(name="intake", status="completed", artifact="run_meta.json"))
    write_progress_state()

    record("context_snapshot", "context_snapshot.md", render_context_snapshot(requirement, runtime))
    record("project_memory_context", "project_memory_context.md", render_project_memory_context(config, requirement, runtime))
    git_snapshot = collect_git_repository_context(config.command_cwd)
    record("git_repository_context", "git_repository_context.md", render_git_repository_context(git_snapshot), verdict="pass" if git_snapshot.get("is_git_repository") else "missing")
    record("graphify_context", "graphify_context.md", render_graphify_context(config, runtime, requirement), verdict="pass")
    research_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "external_research",
        config.research_commands,
        progress_callback=write_progress_state,
    ) if config.research_commands else []
    research_evidence_supplied = bool(
        config.dry_run
        or config.source_urls
        or config.research_report_file
        or research_command_reports
    )
    record(
        "external_research",
        "research_report.md",
        render_research_report(config, research_command_reports),
        verdict="pass" if research_evidence_supplied and (not research_command_reports or commands_ok(research_command_reports)) else "missing",
    )
    if not config.dry_run and (not research_evidence_supplied or (research_command_reports and not commands_ok(research_command_reports))):
        record_payload(
            "external_research_warning",
            "external_research_warning.json",
            {
                "policy": "user_cancelled_all_non_secret_gates",
                "reason": "External research evidence is missing or failed; recorded only, not blocking workflow progression.",
                "commands_supplied": bool(research_command_reports),
            },
        )
    record("requirements_package", "requirements.md", render_requirements(requirement))
    discussion_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "requirements_discussion",
        config.requirements_discussion_commands,
        progress_callback=write_progress_state,
    ) if config.requirements_discussion_commands else []
    discussion_evidence_supplied = bool(config.dry_run or discussion_command_reports)
    discussion_body = render_requirements_discussion(requirement)
    if discussion_command_reports:
        discussion_body = discussion_body.rstrip() + "\n\n" + command_markdown("Requirements Discussion Commands", discussion_command_reports)
    record(
        "requirements_discussion",
        "requirements_discussion.md",
        discussion_body,
        verdict="pass" if discussion_evidence_supplied and (not discussion_command_reports or commands_ok(discussion_command_reports)) else "missing",
    )
    if not config.dry_run and (not discussion_evidence_supplied or (discussion_command_reports and not commands_ok(discussion_command_reports))):
        record_payload(
            "requirements_discussion_warning",
            "requirements_discussion_warning.json",
            {
                "policy": "user_cancelled_all_non_secret_gates",
                "reason": "Requirements discussion evidence is missing or failed; recorded only, not blocking workflow progression.",
                "commands_supplied": bool(discussion_command_reports),
            },
        )

    req_review_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "requirements_review",
        config.requirements_review_commands,
        progress_callback=write_progress_state,
    ) if config.requirements_review_commands else []
    req_verdict = "requires_revision" if config.simulate_failure_stage == "requirements" else "ready_for_solution"
    if req_review_reports:
        req_verdict = "ready_for_solution" if dual_review_pass("requirements_review", req_review_reports) else "requires_revision"
    elif not config.dry_run:
        req_verdict = "requires_revision"
    req_review = record(
        "requirements_review",
        "requirements_review.md",
        render_dual_ai_review("requirements_review", req_review_reports, req_verdict)
        if req_review_reports or not config.dry_run
        else consensus_review("requirements_review", req_verdict, requirement),
        verdict=req_verdict,
    )
    gate_ok, parsed_verdict = gate_result("requirements_review", req_review)
    if not gate_ok:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "requirements_review",
                "revise_requirements",
                "requirements review requires revision; refine the requirement discussion using reviewer feedback and rerun review",
                "requirements_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    resolved_requirement = record(
        "resolved_requirement",
        "resolved_requirement.md",
        render_resolved_requirement(requirement, artifacts),
        verdict="pass",
    )

    delivery_plan = compile_delivery_plan(
        config,
        runtime,
        resolved_requirement.read_text(encoding="utf-8"),
        artifacts,
    )
    record_payload("delivery_plan", "delivery_plan.json", delivery_plan)
    record("solution_package", "solution.md", render_solution(delivery_plan))
    graphify_scope_validation = validate_graphify_scope(config, runtime, delivery_plan, artifacts)
    record_payload("graphify_scope_validation_payload", "graphify_scope_validation.json", graphify_scope_validation)
    record(
        "graphify_scope_validation",
        "graphify_scope_validation.md",
        render_graphify_scope_validation(graphify_scope_validation),
        verdict=str(graphify_scope_validation.get("scope_status") or "warning"),
    )
    solution_review_ledger_entries: list[dict[str, Any]] = []
    solution_review_passed = False
    parsed_verdict = None
    solution_review_budget = max(1, int(config.max_repair_loops or 1))
    for solution_review_attempt in range(1, solution_review_budget + 1):
        sol_review_reports = run_stage_commands(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "solution_review",
            config.solution_review_commands,
            progress_callback=write_progress_state,
        ) if config.solution_review_commands else []
        sol_verdict = "requires_revision" if config.simulate_failure_stage == "solution" else "ready_for_implement"
        if sol_review_reports:
            sol_verdict = "ready_for_implement" if dual_review_pass("solution_review", sol_review_reports) else "requires_revision"
        elif not config.dry_run:
            sol_verdict = "requires_revision"
        sol_review = record(
            "solution_review",
            "solution_review.md",
            render_dual_ai_review("solution_review", sol_review_reports, sol_verdict)
            if sol_review_reports or not config.dry_run
            else consensus_review("solution_review", sol_verdict, requirement),
            verdict=sol_verdict,
        )
        gate_ok, parsed_verdict = gate_result("solution_review", sol_review)
        solution_review_ledger_entries.append(
            {
                "attempt": solution_review_attempt,
                "verdict": parsed_verdict or sol_verdict,
                "hard_blockers": solution_review_hard_blocker_lines(sol_review_reports),
                "absorbed": False,
            }
        )
        if gate_ok:
            solution_review_passed = True
            break
        if not solution_review_can_soft_continue(sol_review_reports, parsed_verdict):
            break
        soft_gate_text = render_solution_review_soft_gate(sol_review_reports, parsed_verdict)
        record(
            "solution_review_soft_gate",
            "solution_review_soft_gate.md",
            soft_gate_text,
            verdict="soft_continue",
        )
        previous_repair_context = os.environ.get("PIPELINE_REPAIR_CONTEXT")
        absorbed_repair_context = build_solution_review_repair_context(soft_gate_text, sol_review)
        solution_review_ledger_entries[-1]["absorbed"] = True
        solution_review_ledger_entries[-1]["repair_artifact"] = "solution_review_soft_gate.md"
        record_payload(
            "solution_review_revision_ledger",
            "solution_review_revision_ledger.json",
            {
                "policy": "Each non-hard solution_review requires_revision is appended to the ledger, merged into PIPELINE_REPAIR_CONTEXT, and followed by a regenerated delivery_plan/solution before the next review attempt.",
                "budget": solution_review_budget,
                "entries": solution_review_ledger_entries,
            },
        )
        os.environ["PIPELINE_REPAIR_CONTEXT"] = "\n".join(
            part for part in (previous_repair_context, absorbed_repair_context) if str(part or "").strip()
        )
        try:
            delivery_plan = compile_delivery_plan(
                config,
                runtime,
                resolved_requirement.read_text(encoding="utf-8"),
                artifacts,
            )
            delivery_plan["solution_review_absorbed_revision"] = {
                "applied": True,
                "attempt": solution_review_attempt,
                "source_artifact": "solution_review_soft_gate.md",
                "ledger_artifact": "solution_review_revision_ledger.json",
                "policy": "non-hard solution_review blockers are merged back into delivery_plan before the next solution_review/code_execution",
            }
            record_payload("delivery_plan", "delivery_plan.json", delivery_plan)
            record("solution_package", "solution.md", render_solution(delivery_plan), verdict="revised_after_solution_review")
            graphify_scope_validation = validate_graphify_scope(config, runtime, delivery_plan, artifacts)
            record_payload("graphify_scope_validation_payload", "graphify_scope_validation.json", graphify_scope_validation)
            record(
                "graphify_scope_validation",
                "graphify_scope_validation.md",
                render_graphify_scope_validation(graphify_scope_validation),
                verdict=str(graphify_scope_validation.get("scope_status") or "warning"),
            )
        finally:
            if previous_repair_context is None:
                os.environ.pop("PIPELINE_REPAIR_CONTEXT", None)
            else:
                os.environ["PIPELINE_REPAIR_CONTEXT"] = previous_repair_context
    if not solution_review_passed and parsed_verdict != EXPECTED_VERDICTS["solution_review"]:
        solution_review_ledger_entries.append(
            {
                "attempt": solution_review_budget,
                "verdict": parsed_verdict or sol_verdict,
                "hard_blockers": solution_review_hard_blocker_lines(sol_review_reports),
                "absorbed": False,
                "policy": "review_loop_blocks_until_pass",
            }
        )
        record_payload(
            "solution_review_revision_ledger",
            "solution_review_revision_ledger.json",
            {
                "policy": "Solution review blocks until reviewer findings are fixed and review passes.",
                "budget": solution_review_budget,
                "entries": solution_review_ledger_entries,
            },
        )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "solution_review",
                "revise_solution",
                "solution review requires revision after the configured repair attempts; revise delivery_plan/solution using reviewer failure reasons and rerun review",
                "solution_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    pre_execution_risk = apply_human_risk_confirmation(
        assess_pre_execution_risk(requirement, delivery_plan, artifacts),
        config,
    )
    record_payload("pre_execution_risk", "pre_execution_risk.json", pre_execution_risk)
    record(
        "plan_publish",
        "group_plan_publish.md",
        render_group_plan_publish(requirement, artifacts, delivery_plan, pre_execution_risk),
        verdict=pre_execution_risk.get("execution_decision"),
    )
    code_command_report = None
    code_workspace_patch_file: Path | None = None
    code_workspace_patch_applied_to_command_cwd = False
    if config.code_command:
        code_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "code_execution",
            config.code_command,
            progress_callback=write_progress_state,
        )
        if code_command_report.get("workspace_patch_file"):
            candidate = Path(str(code_command_report["workspace_patch_file"]))
            if candidate.exists() and candidate.stat().st_size > 0:
                code_workspace_patch_file = candidate
        applied_result = (code_command_report.get("workspace_patch") or {}).get("applied_to_command_cwd") or {}
        code_workspace_patch_applied_to_command_cwd = bool(applied_result.get("ok") and applied_result.get("applied"))
    missing_live_code_execution = not config.dry_run and config.patch_summary_file is None and code_command_report is None
    record("code_execution", "patch_summary.md", render_patch_summary(config, code_command_report))
    if code_command_report and not code_command_report.get("ok"):
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_execution",
                "return_to_code_execution",
                f"coding command failed with returncode={code_command_report.get('returncode')}; developer must fix the failure and rerun implementation",
                "patch_summary.md",
                "fail",
            ),
            requirement,
        )
    if missing_live_code_execution:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_execution",
                "return_to_code_execution",
                "live mode did not receive a coding command or patch summary; developer must produce an implementation artifact before review",
                "patch_summary.md",
                "fail",
            ),
            requirement,
        )

    verification_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "verification",
        config.verification_commands,
        code_workspace_patch_file,
        progress_callback=write_progress_state,
    ) if config.verification_commands else []
    missing_live_verification = (
        not config.dry_run
        and not config.verification_report_file
        and not verification_command_reports
    )
    verification_failed = (
        config.simulate_failure_stage == "verification"
        or missing_live_verification
        or (bool(verification_command_reports) and not commands_ok(verification_command_reports))
    )
    verification_content = render_verification_report(config, verification_failed, verification_command_reports)
    verification_score = 55 if verification_failed else 100
    record(
        "verification",
        "verification_report.md",
        verification_content,
        score=verification_score,
        verdict="fail" if verification_failed else "pass",
    )
    if verification_failed:
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "verification",
                "return_to_code_execution",
                "verification failed; developer must use verification_report.md and command reports to fix the implementation before review",
                "verification_report.md",
                "fail",
                verification_score,
            ),
            requirement,
        )

    code_review_commands = config.code_review_commands or (
        (config.code_review_command,) if config.code_review_command else ()
    )
    code_review_command_reports = run_stage_commands(
        config,
        run_dir,
        runtime,
        artifacts,
        requirement,
        "code_review",
        code_review_commands,
        input_patch_file=code_workspace_patch_file,
        progress_callback=write_progress_state,
    ) if code_review_commands else []
    missing_live_code_review = (
        not config.dry_run
        and not config.code_review_file
        and not code_review_command_reports
    )
    code_review_failed = (
        config.simulate_failure_stage == "code_review"
        or missing_live_code_review
        or (bool(code_review_command_reports) and not dual_review_pass("code_review", code_review_command_reports))
    )
    code_review = record(
        "code_review",
        "code_review.md",
        render_code_review(config, code_review_failed, code_review_command_reports),
        verdict="requires_revision" if code_review_failed else "pass",
    )
    gate_ok, parsed_verdict = gate_result("code_review", code_review)
    if not gate_ok:
        hard_review_blockers = code_review_secret_leak_blocker_lines(code_review_command_reports)
        if hard_review_blockers:
            rollback_report = rollback_applied_code_patch(
                config,
                run_dir,
                artifacts,
                code_workspace_patch_file if code_workspace_patch_applied_to_command_cwd else None,
                "code_review_secret_failed",
            )
            if rollback_failed(rollback_report):
                return finalize_pipeline_state(
                    config,
                    block_pipeline(
                        config,
                        run_id,
                        run_dir,
                        runtime,
                        stages,
                        artifacts,
                        "rollback_cleanup",
                        "manual_cleanup_required",
                        rollback_failure_detail(rollback_report),
                        Path(str(rollback_report.get("report_file") or "")).name or None,
                        "fail",
                        20,
                    ),
                    requirement,
                )
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "code_review",
                    "return_to_code_execution",
                    "code review found credential/password/secret leakage and must be fixed before publish\n" + "\n".join(hard_review_blockers),
                    "code_review.md",
                    parsed_verdict,
                ),
                requirement,
            )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "code_review",
                "return_to_code_execution",
                "code review requires revision; developer must fix the reviewer findings and rerun code review until it passes",
                "code_review.md",
                parsed_verdict,
            ),
            requirement,
        )

    deployment_command_report = None
    if config.deployment_command:
        deployment_command_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "deployment",
            config.deployment_command,
            input_patch_file=code_workspace_patch_file,
            progress_callback=write_progress_state,
        )
        deployment_failed = not deployment_command_report.get("ok")
        record(
            "deployment",
            "deployment_report.md",
            render_deployment_report(deployment_command_report),
            verdict="fail" if deployment_failed else "pass",
        )
        if deployment_failed:
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "deployment",
                    "return_to_deployment",
                    f"deployment command failed with returncode={deployment_command_report.get('returncode') if deployment_command_report else None}; developer/deployer must fix the failure and rerun deployment",
                    "deployment_report.md",
                    "fail",
                ),
                requirement,
            )

    if config.simulate_failure_stage == "acceptance_requirement":
        acceptance_path = record(
            "acceptance",
            "delivery_evidence.md",
            render_delivery_evidence(60, "fail", "revise_requirements"),
            score=60,
            verdict="fail",
        )
        artifacts["delivery_evidence"] = str(acceptance_path)
        record_payload(
            "acceptance_warning",
            "acceptance_warning.json",
            {
                "policy": "user_cancelled_all_non_secret_gates",
                "reason": "Acceptance requirement failure is recorded only, not blocking completion.",
                "source": "simulate_failure_stage=acceptance_requirement",
            },
        )

    if config.simulate_failure_stage == "acceptance_implementation":
        acceptance_path = record(
            "acceptance",
            "delivery_evidence.md",
            render_delivery_evidence(65, "fail", "return_to_code_execution"),
            score=65,
            verdict="fail",
        )
        artifacts["delivery_evidence"] = str(acceptance_path)
        record_payload(
            "acceptance_warning",
            "acceptance_warning.json",
            {
                "policy": "user_cancelled_all_non_secret_gates",
                "reason": "Acceptance implementation failure is recorded only, not blocking completion.",
                "source": "simulate_failure_stage=acceptance_implementation",
            },
        )

    if "delivery_evidence" not in artifacts:
        acceptance_path = record(
            "acceptance",
            "delivery_evidence.md",
            render_delivery_evidence(100, "pass", "writeback"),
            score=100,
            verdict="pass",
        )
        artifacts["delivery_evidence"] = str(acceptance_path)
    writeback_path = record("writeback", "writeback_report.md", render_writeback_report(config.project_key, "completed", "none"))
    memory_reports: list[dict[str, Any]] = []
    if config.memory_write_command:
        memory_reports.append(
            run_stage_command(
                config,
                run_dir,
                runtime,
                artifacts,
                requirement,
                "memory_writeback",
                config.memory_write_command,
                input_patch_file=code_workspace_patch_file,
                progress_callback=write_progress_state,
            )
        )
    elif config.write_project_memory:
        builtin_report = run_builtin_project_memory_writeback(config, run_dir, runtime, writeback_path)
        write_memory_command_report(run_dir, artifacts, builtin_report)
        memory_reports.append(builtin_report)

    missing_live_memory_writeback = (
        not config.dry_run
        and not config.write_project_memory
        and not config.memory_write_command
    )
    if memory_reports:
        memory_report_path = run_dir / "memory_writeback_report.md"
        write_text(memory_report_path, render_memory_writeback_report(memory_reports))
        artifacts["memory_writeback"] = str(memory_report_path)
    if missing_live_memory_writeback or (memory_reports and not commands_ok(memory_reports)):
        record_payload(
            "writeback_warning",
            "writeback_warning.json",
            {
                "policy": "user_simplified_gate_soft_continue",
                "reason": "Memory writeback failures or missing writeback evidence are recorded as warnings and do not block completion under the simplified gate policy.",
                "missing_live_memory_writeback": missing_live_memory_writeback,
            },
        )

    if config.git_publish_command:
        git_publish_input_patch_file: Path | None = None
        git_publish_input_patch_report: dict[str, Any] = {
            "ok": True,
            "source": "none",
            "patch_file": "",
            "has_changes": False,
        }
        for memory_report in reversed(memory_reports):
            candidate_text = str(memory_report.get("workspace_patch_file") or "")
            candidate = Path(candidate_text) if candidate_text else None
            if candidate is not None and candidate.exists() and candidate.stat().st_size > 0:
                git_publish_input_patch_file = candidate
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "memory_writeback_workspace_patch",
                    "patch_file": str(candidate),
                    "has_changes": True,
                }
                break
        if git_publish_input_patch_file is None:
            if code_workspace_patch_file is not None and code_workspace_patch_file.exists():
                git_publish_input_patch_file = code_workspace_patch_file
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "code_execution_workspace_patch",
                    "patch_file": str(code_workspace_patch_file),
                    "has_changes": code_workspace_patch_file.stat().st_size > 0,
                }
            else:
                git_publish_input_patch_report = {
                    "ok": True,
                    "source": "no_accepted_patch",
                    "patch_file": "",
                    "has_changes": False,
                }
        git_publish_input_patch_report_path = run_dir / "command-runs" / "git_publish-input-patch.json"
        write_json(git_publish_input_patch_report_path, git_publish_input_patch_report)
        artifacts["git_publish_input_patch_report"] = str(git_publish_input_patch_report_path)
        if git_publish_input_patch_file:
            artifacts["git_publish_input_patch"] = str(git_publish_input_patch_file)
        git_publish_report = run_stage_command(
            config,
            run_dir,
            runtime,
            artifacts,
            requirement,
            "git_publish",
            config.git_publish_command,
            input_patch_file=git_publish_input_patch_file,
            progress_callback=write_progress_state,
        )
        git_publish_report["input_patch"] = git_publish_input_patch_report
        git_publish_command_report_path = artifacts.get("command_git_publish_1")
        if git_publish_command_report_path:
            write_json(Path(git_publish_command_report_path), git_publish_report)
        git_publish_failed = not git_publish_report.get("ok")
        record(
            "git_publish",
            "git_publish_report.md",
            render_git_publish_report(git_publish_report),
            verdict="fail" if git_publish_failed else "pass",
        )
        if git_publish_failed:
            return finalize_pipeline_state(
                config,
                block_pipeline(
                    config,
                    run_id,
                    run_dir,
                    runtime,
                    stages,
                    artifacts,
                    "git_publish",
                    "fix_git_publish",
                    f"git publish failed with returncode={git_publish_report.get('returncode')}; developer must fix the publish failure, including any staged diff password/secret findings, and retry upload",
                    "git_publish_report.md",
                    "fail",
                ),
                requirement,
            )
    elif config.simulate_failure_stage == "git_publish":
        record(
            "git_publish",
            "git_publish_report.md",
            "# Git Publish Report\n\nFinal verdict: fail\n\nNo git publish command was supplied.",
            verdict="fail",
        )
        return finalize_pipeline_state(
            config,
            block_pipeline(
                config,
                run_id,
                run_dir,
                runtime,
                stages,
                artifacts,
                "git_publish",
                "fix_git_publish",
                "simulated git publish failure; developer must fix publish failure and retry upload",
                "git_publish_report.md",
                "fail",
            ),
            requirement,
        )

    failure_path = run_dir / "failure_learning_check.json"
    write_json(failure_path, failure_learning_payload(config, run_id, "completed", None, "none"))
    artifacts["failure_learning_check"] = str(failure_path)

    state = pipeline_state(config, run_id, run_dir, runtime, stages, artifacts, "completed", "none")
    write_json(run_dir / "pipeline_state.json", state)
    return finalize_pipeline_state(config, state, requirement)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the project delivery pipeline state machine")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--requirement")
    parser.add_argument("--requirement-file", type=Path)
    parser.add_argument("--runtime-host", default="generic")
    parser.add_argument("--runtime-home")
    parser.add_argument("--workspace-root", type=Path, default=Path(".workflow/pipeline-runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--simulate-failure-stage", choices=sorted(SIMULATED_FAILURES))
    parser.add_argument("--max-repair-loops", type=int, default=4)
    parser.add_argument("--research-report-file", type=Path)
    parser.add_argument("--research-command", action="append", default=[], help="trusted command that produces research evidence")
    parser.add_argument("--requirements-discussion-command", action="append", default=[], help="trusted command that makes project-agent and reviewer discuss/refine requirements")
    parser.add_argument("--requirements-review-command", action="append", default=[], help="trusted independent reviewer command for requirements gate; supply at least two")
    parser.add_argument("--solution-review-command", action="append", default=[], help="trusted independent reviewer command for solution gate; supply at least two")
    parser.add_argument("--code-agent", choices=["backend-dev", "frontend-dev"], default="backend-dev", help="workflow owner for code_execution")
    parser.add_argument("--code-command", help="trusted runtime/agent command that performs or dispatches implementation")
    parser.add_argument("--patch-summary-file", type=Path)
    parser.add_argument("--verification-command", action="append", default=[], help="trusted command used as verification evidence")
    parser.add_argument("--verification-report-file", type=Path)
    parser.add_argument("--code-review-command", action="append", default=[], help="trusted independent reviewer command that produces code review output; supply at least two")
    parser.add_argument("--code-review-file", type=Path)
    parser.add_argument("--deployment-command", help="trusted command that deploys an accepted implementation")
    parser.add_argument("--memory-write-command", help="trusted command that writes project memory after acceptance")
    parser.add_argument("--git-publish-command", help="trusted command that commits and pushes accepted changes after writeback")
    parser.add_argument("--write-project-memory", action="store_true", help="call project_memory_writer.py for accepted runs")
    parser.add_argument("--command-cwd", type=Path, default=Path("."))
    parser.add_argument("--agent-workspace-root", type=Path, help="root for per-run agent workspaces")
    parser.add_argument("--command-timeout-seconds", type=int, default=600)
    parser.add_argument("--project-memory-root", type=Path, default=Path(".workflow/project-memory"))
    parser.add_argument("--record-task-center", action="store_true")
    parser.add_argument("--task-center-db", type=Path)
    parser.add_argument("--task-center-task-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--human-risk-confirmed",
        action="store_true",
        help="allow a high-risk pre-execution plan to continue after audited human confirmation",
    )
    parser.add_argument("--emit-json", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        project_key=args.project_key,
        requirement=args.requirement,
        requirement_file=args.requirement_file,
        runtime_host=args.runtime_host,
        runtime_home=args.runtime_home,
        workspace_root=args.workspace_root,
        run_id=args.run_id,
        source_urls=tuple(args.source_url or ()),
        dry_run=args.dry_run,
        simulate_failure_stage=args.simulate_failure_stage,
        max_repair_loops=args.max_repair_loops,
        research_report_file=args.research_report_file,
        research_commands=tuple(args.research_command or ()),
        requirements_discussion_commands=tuple(args.requirements_discussion_command or ()),
        requirements_review_commands=tuple(args.requirements_review_command or ()),
        solution_review_commands=tuple(args.solution_review_command or ()),
        code_agent=normalize_code_agent(args.code_agent),
        code_command=args.code_command,
        patch_summary_file=args.patch_summary_file,
        verification_commands=tuple(args.verification_command or ()),
        verification_report_file=args.verification_report_file,
        code_review_commands=tuple(args.code_review_command or ()),
        code_review_file=args.code_review_file,
        deployment_command=args.deployment_command,
        memory_write_command=args.memory_write_command,
        git_publish_command=args.git_publish_command,
        write_project_memory=bool(args.write_project_memory),
        command_cwd=args.command_cwd,
        agent_workspace_root=args.agent_workspace_root,
        command_timeout_seconds=args.command_timeout_seconds,
        project_memory_root=args.project_memory_root,
        record_task_center=args.record_task_center,
        task_center_db=args.task_center_db,
        task_center_task_id=args.task_center_task_id,
        force=args.force,
        human_risk_confirmed=bool(args.human_risk_confirmed),
    )


def build_view_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View a project delivery pipeline run")
    parser.add_argument("--workspace-root", type=Path, default=Path(".workflow/pipeline-runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--task-center-db", type=Path)
    parser.add_argument("--task-id")
    parser.add_argument("--event-limit", type=int, default=100)
    parser.add_argument("--emit-json", action="store_true")
    return parser


def load_pipeline_state(workspace_root: Path, run_id: str | None) -> dict[str, Any]:
    if run_id:
        state_file = workspace_root / run_id / "pipeline_state.json"
    else:
        candidates = sorted(workspace_root.glob("*/pipeline_state.json"), key=lambda item: item.stat().st_mtime)
        if not candidates:
            raise PipelineError(f"no pipeline_state.json found under {workspace_root}")
        state_file = candidates[-1]
    if not state_file.exists():
        raise PipelineError(f"pipeline state not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8"))


def load_task_center_report(db_path: Path | None, task_id: str | None, event_limit: int) -> dict[str, Any] | None:
    if db_path is None or not task_id:
        return None
    TaskCenter, TaskCenterError = load_task_center_classes()
    task_center = TaskCenter(db_path.expanduser())
    try:
        task_center.init_schema()
        return task_center.task_report(task_id, event_limit=max(20, int(event_limit or 100)), display_safe=False)
    except TaskCenterError as exc:
        raise PipelineError(f"failed to load task-center report: {exc}") from exc
    finally:
        task_center.close()


def build_view_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_id or args.workspace_root.exists():
        state = load_pipeline_state(args.workspace_root, args.run_id)
    elif args.task_center_db and args.task_id:
        state = {}
    else:
        raise PipelineError(f"workspace root not found: {args.workspace_root}")
    task_id = str(args.task_id or state.get("task_center", {}).get("task_id", "")).strip()
    db_raw = args.task_center_db or state.get("task_center", {}).get("db")
    db_path = Path(db_raw).expanduser() if db_raw else None
    task_report = load_task_center_report(db_path, task_id, args.event_limit) if task_id and db_path else None
    return {
        "state": state,
        "task_center_report": task_report,
        "summary": {
            "run_id": state.get("run_id", ""),
            "project_key": state.get("project_key", ""),
            "status": state.get("status", ""),
            "next_action": state.get("next_action", ""),
            "failed_stage": state.get("failed_stage", ""),
            "run_dir": state.get("run_dir", ""),
            "task_center_db": str(db_path) if db_path else "",
            "task_id": task_id,
            "stage_count": len(state.get("stages", [])),
            "artifact_count": len(state.get("artifacts", {})),
            "open_incident_count": (
                task_report.get("control_plane", {}).get("open_incident_count", 0) if task_report else 0
            ),
        },
    }


def render_view_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    state = payload.get("state", {})
    lines = [
        f"Pipeline {summary.get('status', '-')}: {summary.get('run_id', '-')}",
        f"- project: {summary.get('project_key', '-')}",
        f"- next_action: {summary.get('next_action', '-')}",
        f"- failed_stage: {summary.get('failed_stage') or 'none'}",
        f"- run_dir: {summary.get('run_dir', '-')}",
        f"- task_center: {summary.get('task_id') or 'not recorded'}",
        f"- open_incidents: {summary.get('open_incident_count', 0)}",
    ]
    artifacts = state.get("artifacts", {})
    if artifacts:
        lines.append("- key artifacts:")
        for key in (
            "project_memory_context",
            "requirements_package",
            "requirements_discussion",
            "delivery_plan",
            "solution_package",
            "verification",
            "code_review",
            "acceptance",
            "git_publish",
        ):
            if key in artifacts:
                lines.append(f"  {key}: {artifacts[key]}")
    return "\n".join(lines)


def run_view(argv: list[str]) -> int:
    parser = build_view_arg_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_view_payload(args)
    except PipelineError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_view_text(payload))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["view"]:
        return run_view(argv[1:])
    if argv[:1] == ["run"]:
        argv = argv[1:]
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        state = run_pipeline(config_from_args(args))
    except PipelineError as exc:
        payload = {"status": "error", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(f"pipeline {state['status']}: {state['run_dir']}")
    return 0 if state["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

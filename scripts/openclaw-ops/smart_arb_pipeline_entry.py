#!/usr/bin/env python3
"""Project-specific entrypoint for SmartMultiPlatformArbitrage pipeline runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_KEY = "smart-multi-platform-arbitrage"
RUNTIME_HOME = Path("/home/arbops/.hermes")
PROJECT_DIR = Path("/home/arbops/projects/SmartMultiPlatformArbitrage")
OPS_DIR = RUNTIME_HOME / "ops"
RUNNER = OPS_DIR / "pipeline_runner.py"
BRIDGE = OPS_DIR / "smart_arb_live_bridge.py"
WORKSPACE_ROOT = RUNTIME_HOME / "pipeline-runs"
PROJECT_MEMORY_ROOT = PROJECT_DIR / "memory"
TASK_CENTER_DB = OPS_DIR / "task-center" / "task_center.db"
STAGE_AGENT_MAP = {
    "intake": "coordinator",
    "context_snapshot": "project-agent",
    "project_memory_context": "project-agent",
    "external_research": "web-agent",
    "requirements_package": "project-agent",
    "requirements_discussion": "project-agent,reviewer",
    "requirements_review": "reviewer",
    "solution_package": "project-agent",
    "solution_review": "reviewer",
    "code_execution": "backend-dev",
    "verification": "tester",
    "code_review": "reviewer",
    "deployment": "deployer",
    "acceptance": "tester",
    "writeback": "doc-writer",
    "git_publish": "coordinator",
}
FRONTEND_KEYWORDS = (
    "frontend",
    "front-end",
    "ui",
    "ux",
    "react",
    "vue",
    "页面",
    "前端",
    "样式",
    "交互",
    "按钮",
    "表单",
    "组件",
)
BACKEND_KEYWORDS = (
    "backend",
    "api",
    "database",
    "db",
    "service",
    "strategy",
    "后端",
    "接口",
    "数据库",
    "服务",
    "策略",
)
STAGE_LABELS = {
    "intake": "任务接入",
    "context_snapshot": "上下文快照",
    "project_memory_context": "项目记忆读取",
    "external_research": "外部资料核对",
    "requirements_package": "需求整理",
    "requirements_discussion": "双 AI 需求讨论",
    "requirements_review": "需求评审",
    "solution_package": "方案整理",
    "solution_review": "方案评审",
    "code_execution": "代码执行",
    "verification": "验证",
    "code_review": "代码审查",
    "deployment": "内部部署",
    "acceptance": "验收",
    "writeback": "记忆写回",
    "git_publish": "Git 发布",
}
STATUS_LABELS = {
    "completed": "完成",
    "blocked": "阻塞",
    "failed": "失败",
    "passed": "通过",
}
REPAIRABLE_NEXT_ACTIONS = {
    "run_external_research",
    "return_to_code_execution",
    "return_to_deployment",
    "fix_memory_writeback",
}
HIGH_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?|cookies?|jwt|(?:access|refresh|bearer|auth|api|csrf)[_ -]?tokens?)\b\s*[:=]",
        r"\b(?:need|needs|requires?|read|print|show|dump|export|upload|commit|use|modify|delete)\b.{0,60}\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|(?:access|refresh|bearer|auth|api|csrf)[_ -]?tokens?)\b",
        r"\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|x-csrf-token)\b\s*[:=]",
        r"PRODUCTION_TRADING_ENABLED\s*=\s*true",
        r"\b(?:withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?|enable\s+(?:real|live)\s+trading|start\s+(?:real|live)\s+trading)\b",
        r"\b(?:need|needs|requires?|start|enable|execute|place|submit|perform|allow)\b.{0,60}\b(?:withdrawals?|transfer\s+funds|funds?\s+(?:movement|operation|transfer)|place\s+orders?|real\s+trading|live\s+trading)\b",
        r"\brm\s+-rf\b",
        r"\bdrop\s+table\b",
        r"\btruncate\s+table\b",
        r"\bforce\s+push\b",
        r"(?:需要|要求|读取|查看|输出|打印|提交|上传|使用|修改|删除).{0,20}(?:密钥|凭证|token|cookie|私钥|会话)",
        r"(?:下单|划转|转账|提现|出金|资金操作)",
        r"(?:需要|要求|启动|启用|执行|进行|允许).{0,20}(?:真实交易|实盘交易|下单|划转|转账|提现|出金|资金操作)",
        r"(?:真实交易|实盘交易).{0,20}(?:授权|开启|执行)",
    )
]
SAFE_NEGATED_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:do\s+not|don't|never|without|no)\b.{0,80}\b(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdraw|transfer)\b",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不读取|不泄露).{0,60}(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)",
        r"(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金).{0,30}(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|关闭|false)",
    )
]
RISK_CLAUSE_SPLIT_RE = re.compile(
    r"[\r\n.;；。!?！？,，]+|\b(?:but|however|yet|and)\b|(?:但|但是|不过|然而|并且|并|且|同时)",
    re.IGNORECASE,
)
NEGATED_CLAUSE_RE = re.compile(
    r"^\s*(?:(?:do\s+not|don't|never|without|no)\b|不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不读取|不泄露)",
    re.IGNORECASE,
)
SAFE_NEGATED_COORDINATE_RE = re.compile(
    r"\b(?:or|nor)\s+(?:use|read|print|show|dump|export|upload|commit|modify|delete|place|start|enable|execute|transfer|withdraw)?\s*"
    r"(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?)\b",
    re.IGNORECASE,
)
SAFE_NEGATED_CN_COORDINATE_RE = re.compile(r"(?:或|或者|以及|和)(?:读取|泄露|使用|输出|打印|查看|启动|启用|执行|进行|允许|下单|划转|转账|提现|出金)?(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)")
SAFE_NEGATED_FRAGMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:do\s+not|don't|never|without|no)\b\s+(?:withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?|enable\s+(?:real|live)\s+trading|start\s+(?:real|live)\s+trading)\b",
        r"\b(?:do\s+not|don't|never|without|no)\b\s+(?:use|read|print|show|dump|export|upload|commit|modify|delete|place|start|enable|execute|transfer|withdraw)?\s*(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdrawals?|transfer\s+funds)\s*(?:required|needed|used|enabled|disabled)?",
        r"\bkeep\s+(?:live\s+trading|real\s+trading|orders?|funds?|withdrawals?|transfers?)\s+disabled\b",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不转账|不提现|不出金|不读取|不泄露)(?:读取|泄露|使用|输出|打印|查看|启动|启用|执行|进行|允许|下单|划转|转账|提现|出金)?(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)?(?:关闭|false)?",
        r"(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|关闭|false)",
    )
]
SAFE_NEGATED_LIST_FRAGMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:no\s+need(?:ed)?\s+for|do\s+not\s+need|don't\s+need|not\s+(?:required|needed))\b.{0,120}\b(?:api[_ /-]?keys?|secrets?|passwords?|credentials?|credential-imports|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|jwt|tokens?|oauth|authorization|auth\s+state\s+files?)\b\s*(?::|=)?\s*(?:\[[^\]]*REDACTED[^\]]*\])?",
        r"\b(?:do\s+not|don't|never|without)\b(?:(?!\b(?:but|however|yet|needs?|requires?|start|enable|execute|place|submit|perform|allow)\b).){0,160}\b(?:api[_ /-]?keys?|secrets?|passwords?|credentials?|credential-imports|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|jwt|tokens?|oauth|auth\s+state\s+files?|live\s+trading|real\s+trading|orders?|funds?|withdraw(?:als?)?|transfer\s+funds)\b",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未在|未启动|未下单|未划转|未转账|未提现|未出金|未读取|未泄露|未打印|未移动|未修改|未保留|不保留|不启动|不下单|不划转|不转账|不提现|不出金|不读取|不泄露|不打印|不移动|不修改)(?:(?!(?:但|但是|不过|然而|需要|要求|启动|启用|执行|进行|允许|下单后|划转后|转账后|提现后|出金后|资金操作)).){0,160}(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|交易|下单|划转|转账|提现|出金|资金|credential(?:-imports)?|credentials?|secrets?|tokens?|cookies?|oauth|api[_ /-]?keys?)",
    )
]
SAFE_DOCUMENTATION_HISTORY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:按用户要求|已|已经).{0,30}从待办中删除.{0,80}(?:凭证|密钥|token|cookie|安全轮换).{0,80}(?:事项|TODO|任务|跟踪)",
        r"未在.{0,40}(?:文档|输出|日志).{0,40}(?:保留|记录|包含).{0,80}(?:token|key|pat|密钥|凭证|cookie).{0,40}(?:明文)?",
    )
]
SERVICE_CONTROL_DENY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"不触碰服务控制",
        r"不触碰服务",
        r"不修改服务",
        r"不需要.{0,10}(?:重启|部署)",
        r"不重启",
        r"不部署",
        r"不要.{0,20}(?:重启|部署|改动服务|触碰服务)",
        r"\bdo\s+not\s+(?:restart|deploy|touch\s+service|modify\s+service)",
        r"\bwithout\s+(?:service\s+control|deployment|restart)",
        r"\bno\s+(?:service\s+control|deployment|restart)",
    )
]
MEMORY_DOC_ONLY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:只|仅)写入.{0,60}(?:memory|记忆|docs|文档|长期事实)",
        r"写回.{0,60}(?:memory|记忆|docs|文档|长期事实).{0,40}(?:不触碰|不要|不修改|不重启|不部署)",
        r"\b(?:memory|docs?|documentation)[-/ ]?only\b",
    )
]
POSITIVE_DEPLOYMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:重启|部署|上线|发布|启动).{0,30}(?:服务|API|FastAPI|内控|完成部署)?",
        r"\b(?:restart|deploy|deployment|rollout|smoke)\b",
    )
]
PRE_REDACTED_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)\b\s*[:=]\s*\[[^\]]*REDACTED[^\]]*\]"
)
PRE_REDACTED_HEADER_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|session(?:id|_id)?|csrf(?:token)?|jwt)\b\s*[:=]\s*\[[^\]]*REDACTED[^\]]*\]"
)
PRE_REDACTED_MARKER_RE = re.compile(
    r"__SMART_ARB_PRE_REDACTED__(?P<key>[A-Za-z0-9_-]+)(?P<sep>[:=])\[REDACTED\]__"
)
NEGATED_PRE_REDACTED_CONTEXT_RE = re.compile(
    r"(?i)\b(?:no\s+need(?:ed)?\s+for|do\s+not\s+need|don't\s+need|not\s+(?:required|needed))\b|"
    r"(?:不需要|无需|无须)"
)
SENSITIVE_ACTION_CONTEXT_RE = re.compile(
    r"(?i)\b(?:need|needs|required?|requires?|missing|read|print|show|dump|export|upload|"
    r"commit|use|modify|delete|provide|set|configure|add)\b|"
    r"(?:需要|要求|缺少|未配置|读取|打印|展示|输出|导出|上传|提交|使用|修改|删除|配置|提供|填入|设置)"
)
SENSITIVE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9_-]{47,}(?![A-Za-z0-9])")
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
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)\b\s*[:=]\s*([^\s,;]+)"
)
SENSITIVE_HEADER_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|session(?:id|_id)?|csrf(?:token)?|jwt)\b\s*[:=]\s*([^\r\n]+)"
)
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)


def utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in prefix).strip("-")
    return f"{safe_prefix or 'discord'}-{stamp}"


def option_present(args: list[str], option: str) -> bool:
    return any(item == option or item.startswith(option + "=") for item in args)


def compact_text(value: object, limit: int = 120) -> str:
    text = " ".join(redact_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def redact_text(value: object) -> str:
    text = str(value or "")
    text = PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    text = SENSITIVE_HEADER_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", text)
    text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = KNOWN_SECRET_RE.sub("[REDACTED]", text)
    return SENSITIVE_TOKEN_RE.sub("[REDACTED]", text)


def strip_safe_negated_fragments(text: str) -> str:
    cleaned = text
    for pattern in SAFE_NEGATED_LIST_FRAGMENT_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def strip_safe_documentation_history(text: str) -> str:
    cleaned = text
    for pattern in SAFE_DOCUMENTATION_HISTORY_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def mark_pre_redacted_sensitive_markers(text: str) -> str:
    def replacement(match: re.Match, separator: str) -> str:
        key = re.sub(r"[^A-Za-z0-9_-]+", "_", match.group(1).strip()).strip("_").lower()
        return f"__SMART_ARB_PRE_REDACTED__{key}{separator}[REDACTED]__"

    text = PRE_REDACTED_HEADER_RE.sub(lambda match: replacement(match, ":"), text)
    return PRE_REDACTED_ASSIGNMENT_RE.sub(lambda match: replacement(match, "="), text)


def restore_or_strip_pre_redacted_sensitive_markers(text: str) -> str:
    if PRE_REDACTED_MARKER_RE.search(text) and NEGATED_PRE_REDACTED_CONTEXT_RE.search(text):
        return PRE_REDACTED_MARKER_RE.sub(" ", text)
    if SENSITIVE_ACTION_CONTEXT_RE.search(text):
        return PRE_REDACTED_MARKER_RE.sub(
            lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]",
            text,
        )
    return PRE_REDACTED_MARKER_RE.sub(" ", text)


def risk_scan_text(value: object) -> str:
    text = redact_text(mark_pre_redacted_sensitive_markers(str(value or "")))
    text = strip_safe_negated_fragments(strip_safe_documentation_history(text))
    clauses = [clause.strip() for clause in RISK_CLAUSE_SPLIT_RE.split(text) if clause.strip()]
    risky_clauses = []
    for clause in clauses:
        cleaned_clause = strip_safe_negated_fragments(strip_safe_documentation_history(clause))
        cleaned_clause = restore_or_strip_pre_redacted_sensitive_markers(cleaned_clause)
        for pattern in SAFE_NEGATED_FRAGMENT_PATTERNS:
            cleaned_clause = pattern.sub(" ", cleaned_clause)
        if NEGATED_CLAUSE_RE.search(clause):
            cleaned_clause = SAFE_NEGATED_COORDINATE_RE.sub(" ", cleaned_clause)
            cleaned_clause = SAFE_NEGATED_CN_COORDINATE_RE.sub(" ", cleaned_clause)
        if not cleaned_clause.strip() and any(pattern.search(clause) for pattern in SAFE_NEGATED_RISK_PATTERNS):
            continue
        risky_clauses.append(cleaned_clause)
    return "\n".join(risky_clauses)


def parse_runner_state(stdout: str) -> dict | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) and "stages" in payload else None


def stage_artifact_name(stage: dict) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    return Path(artifact).name


def read_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text_excerpt(path: Path, limit: int = 420) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return compact_text(text, limit)


def artifact_path(value: object, run_dir: str = "") -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or not run_dir:
        return path
    return Path(run_dir) / path


def command_reports(state: dict | None, stage_name: str | None = None) -> list[dict]:
    if not isinstance(state, dict):
        return []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    reports: list[dict] = []
    prefix = f"command_{stage_name}_" if stage_name else "command_"
    for key, value in sorted(artifacts.items()):
        if not str(key).startswith(prefix):
            continue
        path = artifact_path(value, str(state.get("run_dir") or ""))
        if path is None:
            continue
        report = read_json_file(path)
        if report:
            report["_artifact_key"] = str(key)
            report["_artifact_path"] = str(path)
            reports.append(report)
    return reports


def stage_record(state: dict | None, stage_name: str) -> dict:
    if not isinstance(state, dict):
        return {}
    for item in state.get("stages", []) or []:
        if isinstance(item, dict) and item.get("name") == stage_name:
            return item
    return {}


def failed_stage_record(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    failed_stage = str(state.get("failed_stage") or "").strip()
    return stage_record(state, failed_stage) if failed_stage else {}


def report_excerpt(report: dict, limit: int = 260) -> str:
    for key in ("error", "stderr", "stdout"):
        text = compact_text(report.get(key), limit)
        if text:
            return text
    return "没有可用输出"


def report_line(report: dict) -> str:
    stage = str(report.get("stage") or "").strip()
    label = STAGE_LABELS.get(stage, stage or "命令")
    agent = str(report.get("agent_id") or STAGE_AGENT_MAP.get(stage, "agent")).strip()
    returncode = report.get("returncode")
    ok = "通过" if report.get("ok") else "失败"
    output = report_excerpt(report)
    return f"- {label}: {agent} -> {ok}；returncode={returncode}；输出={output}"


def failure_evidence(state: dict | None, *, redact: bool = True) -> str:
    if not isinstance(state, dict):
        return ""
    failed_stage = str(state.get("failed_stage") or "").strip()
    stage = failed_stage_record(state)
    parts = [
        str(stage.get("detail") or "").strip(),
        str(state.get("next_action") or "").strip(),
    ]
    for report in command_reports(state, failed_stage):
        parts.extend(
            [
                str(report.get("error") or "").strip(),
                str(report.get("stderr") or "").strip(),
                str(report.get("stdout") or "").strip(),
            ]
        )
    artifact = artifact_path(stage.get("artifact"), str(state.get("run_dir") or ""))
    if artifact:
        parts.append(read_text_excerpt(artifact, 640))
    text = "\n".join(part for part in parts if part)
    return redact_text(text) if redact else text


def classify_repair_risk(state: dict | None) -> tuple[str, list[str]]:
    if not isinstance(state, dict):
        return "unknown", ["没有可解析的 pipeline 状态"]
    if str(state.get("status") or "") != "blocked":
        return "none", ["当前不是阻塞态"]
    evidence = risk_scan_text(failure_evidence(state, redact=False))
    reasons = [pattern.pattern for pattern in HIGH_RISK_PATTERNS if pattern.search(evidence)]
    if reasons:
        return "high", reasons[:4]
    next_action = str(state.get("next_action") or "").strip()
    if next_action in REPAIRABLE_NEXT_ACTIONS:
        return "medium", [f"可回流动作: {next_action}"]
    return "high", [f"不在自动修复白名单: {next_action or 'none'}"]


def should_auto_repair(state: dict | None, attempt_count: int, max_attempts: int) -> tuple[bool, str, list[str]]:
    if max_attempts <= 0:
        return False, "disabled", ["自动修复已关闭"]
    if attempt_count >= max_attempts:
        return False, "exhausted", [f"已达到最大自动修复次数 {max_attempts}"]
    risk, reasons = classify_repair_risk(state)
    if risk == "high":
        return False, risk, reasons
    if risk == "medium":
        return True, risk, reasons
    return False, risk, reasons


def repair_context_markdown(state: dict, attempt: int, risk: str, reasons: list[str]) -> str:
    failed_stage = str(state.get("failed_stage") or "unknown")
    next_action = str(state.get("next_action") or "unknown")
    evidence = compact_text(failure_evidence(state), 1400)
    return "\n".join(
        [
            "# Smart Arb Auto Repair Context",
            "",
            f"- Attempt: {attempt}",
            f"- Previous run: {state.get('run_id', '-')}",
            f"- Failed stage: {failed_stage}",
            f"- Next action: {next_action}",
            f"- Risk class: {risk}",
            f"- Decision reason: {', '.join(reasons) if reasons else 'repairable pipeline block'}",
            "",
            "## Previous Failure Evidence",
            evidence or "No detailed failure evidence was available.",
            "",
            "## Repair Contract",
            "- Repair through the normal pipeline stages; do not bypass verification, code review, deployment, memory writeback, or git publish.",
            "- Fix the root cause if it is within the repository/runtime permissions.",
            "- Stop and report if the next step requires secrets, real trading authorization, fund movement, or destructive data operations.",
        ]
    )


def write_repair_context_file(
    state: dict,
    attempt: int,
    risk: str,
    reasons: list[str],
    content: str | None = None,
) -> Path | None:
    raw_run_dir = str(state.get("run_dir") or "").strip()
    if not raw_run_dir:
        return None
    run_dir = Path(raw_run_dir).expanduser()
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"auto_repair_context_{attempt}.md"
        path.write_text(content or repair_context_markdown(state, attempt, risk, reasons), encoding="utf-8")
        return path
    except OSError:
        return None


def render_stage_line(stage: dict, stage_agents: dict | None = None) -> str:
    name = str(stage.get("name") or "").strip()
    label = STAGE_LABELS.get(name, name or "未知阶段")
    raw_agents = stage_agents.get(name) if isinstance(stage_agents, dict) else None
    if isinstance(raw_agents, list):
        agent = ",".join(str(item).strip() for item in raw_agents if str(item).strip()) or STAGE_AGENT_MAP.get(name, "coordinator")
    else:
        agent = STAGE_AGENT_MAP.get(name, "coordinator")
    status = str(stage.get("status") or "").strip()
    status_label = STATUS_LABELS.get(status, status or "未知")
    parts = [f"{label}: {agent} -> {status_label}"]
    verdict = str(stage.get("verdict") or "").strip()
    if verdict:
        parts.append(f"结论={verdict}")
    score = stage.get("score")
    if score is not None:
        parts.append(f"分数={score}")
    artifact_name = stage_artifact_name(stage)
    if artifact_name:
        parts.append(f"证据={artifact_name}")
    next_action = str(stage.get("next_action") or "").strip()
    if status != "completed" and next_action:
        parts.append(f"下一步={next_action}")
    return "- " + "；".join(parts)


def render_chat_summary(
    state: dict | None,
    *,
    source: str,
    profile: str,
    returncode: int,
    raw_stdout: str = "",
    raw_stderr: str = "",
    stage_limit: int = 20,
    command_limit: int = 24,
) -> str:
    if not state:
        tail = compact_text((raw_stderr or raw_stdout or "pipeline runner 没有返回可解析状态"), 360)
        return "\n".join(
            [
                "# nofx 任务执行状态",
                f"- 来源: {source}/{profile}",
                f"- 状态: 无法解析 pipeline JSON，returncode={returncode}",
                f"- 输出: {tail}",
            ]
        )

    status = str(state.get("status") or "").strip()
    status_label = "已完成" if status == "completed" else "已阻塞" if status == "blocked" else status or "未知"
    stages = [item for item in state.get("stages", []) if isinstance(item, dict)]
    completed = sum(1 for item in stages if item.get("status") == "completed")
    blocked = len(stages) - completed
    task_center = state.get("task_center") if isinstance(state.get("task_center"), dict) else {}
    task_id = str(task_center.get("task_id") or "未记录").strip()
    failed_stage = str(state.get("failed_stage") or "none").strip()
    next_action = str(state.get("next_action") or "none").strip()
    run_dir = str(state.get("run_dir") or "").strip()

    lines = [
        "# nofx 任务执行状态",
        f"- 来源: {source}/{profile}",
        f"- Run ID: {state.get('run_id', '-')}",
        f"- 总状态: {status_label}",
        f"- Task Center: {task_id}",
        f"- 阶段进度: {completed}/{len(stages)} 完成，阻塞 {blocked}",
        f"- 下一步: {next_action}；失败阶段: {failed_stage}",
    ]
    if run_dir:
        lines.append(f"- 证据目录: {run_dir}")

    lines.append("")
    lines.append("## agent 分工与完成情况")
    stage_agents = state.get("stage_agents") if isinstance(state.get("stage_agents"), dict) else {}
    for stage in stages[: max(1, int(stage_limit or 20))]:
        lines.append(render_stage_line(stage, stage_agents))
    if len(stages) > stage_limit:
        lines.append(f"- 还有 {len(stages) - stage_limit} 个阶段未展开，详见 pipeline_state.json")

    reports = command_reports(state)
    if reports:
        lines.append("")
        lines.append("## agent 输出摘要")
        visible_command_limit = max(1, int(command_limit or 24))
        for report in reports[:visible_command_limit]:
            lines.append(report_line(report))
        if len(reports) > visible_command_limit:
            lines.append(f"- 还有 {len(reports) - visible_command_limit} 条命令输出未展开，详见 command-runs/")

    auto_repair = state.get("auto_repair") if isinstance(state.get("auto_repair"), dict) else {}
    if auto_repair:
        lines.append("")
        lines.append("## 自动修复判断")
        attempts = auto_repair.get("attempts", 0)
        if attempts:
            lines.append(f"- 已自动回流 {attempts} 次，修复过程仍走 coordinator pipeline。")
        decision = compact_text(auto_repair.get("decision") or "", 240)
        if decision:
            lines.append(f"- 判断: {decision}")
        history = auto_repair.get("history") if isinstance(auto_repair.get("history"), list) else []
        for item in history[:4]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                + compact_text(
                    f"第 {item.get('attempt')} 次: {item.get('failed_stage')} -> {item.get('next_action')}；"
                    f"风险={item.get('risk')}；结果={item.get('result_status') or '已重新执行'}",
                    260,
                )
            )

    if status == "blocked":
        risk, reasons = classify_repair_risk(state)
        failed_stage_label = STAGE_LABELS.get(failed_stage, failed_stage or "未知阶段")
        evidence = compact_text(failure_evidence(state), 520)
        lines.append("")
        lines.append("## 阻塞原因")
        lines.append(f"- 卡点: {failed_stage_label}")
        if evidence:
            lines.append(f"- 证据: {evidence}")
        if risk == "high":
            lines.append(f"- 处理: 需要人工确认；原因={compact_text(', '.join(reasons), 240)}")
        elif next_action in REPAIRABLE_NEXT_ACTIONS:
            lines.append(f"- 处理: 可自动修复，下一轮会回流到 {next_action}。")
        else:
            lines.append(f"- 处理: 暂无自动修复路径，下一步={next_action or 'none'}。")

    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    key_artifacts = [
        key
        for key in (
            "requirements_discussion",
            "verification",
            "code_review",
            "deployment",
            "acceptance",
            "delivery_evidence",
            "writeback",
            "git_publish",
        )
        if key in artifacts
    ]
    if key_artifacts:
        lines.append("")
        lines.append(f"关键证据: {', '.join(key_artifacts)}")
    return "\n".join(lines)


def run_pipeline_command(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )


def command_with_option_value(cmd: list[str], option: str, value: str) -> list[str]:
    updated = list(cmd)
    try:
        index = updated.index(option)
    except ValueError:
        updated.extend([option, value])
    else:
        if index + 1 >= len(updated):
            updated.append(value)
        else:
            updated[index + 1] = value
    return updated


def passthrough_option_value(passthrough: list[str], option: str) -> str:
    try:
        index = passthrough.index(option)
    except ValueError:
        return ""
    if index + 1 >= len(passthrough):
        return ""
    return str(passthrough[index + 1] or "")


def requirement_from_passthrough(passthrough: list[str]) -> str:
    parts: list[str] = []
    requirement = passthrough_option_value(passthrough, "--requirement")
    if requirement:
        parts.append(requirement)
    requirement_file = passthrough_option_value(passthrough, "--requirement-file")
    if requirement_file:
        path = Path(requirement_file).expanduser()
        if path.exists():
            parts.append(read_text_excerpt(path, 4000))
    return "\n\n".join(part for part in parts if part)


def normalize_code_agent(value: str | None) -> str:
    agent = str(value or "").strip()
    return agent if agent in {"backend-dev", "frontend-dev"} else ""


def infer_code_agent(requirement: str) -> str:
    text = str(requirement or "").lower()
    frontend_hit = any(keyword in text for keyword in FRONTEND_KEYWORDS)
    backend_hit = any(keyword in text for keyword in BACKEND_KEYWORDS)
    if frontend_hit and not backend_hit:
        return "frontend-dev"
    return "backend-dev"


def strip_service_control_denials(text: str) -> str:
    cleaned = text or ""
    for pattern in SERVICE_CONTROL_DENY_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def requirement_requests_deployment(requirement: str) -> bool:
    text = strip_service_control_denials(requirement)
    return any(pattern.search(text) for pattern in POSITIVE_DEPLOYMENT_PATTERNS)


def requirement_disables_deployment(requirement: str) -> bool:
    text = requirement or ""
    if requirement_requests_deployment(text):
        return False
    if any(pattern.search(text) for pattern in SERVICE_CONTROL_DENY_PATTERNS):
        return True
    return any(pattern.search(text) for pattern in MEMORY_DOC_ONLY_PATTERNS)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def bridge_command(stage: str, args: argparse.Namespace, reviewer_role: str | None = None) -> str:
    command = [
        sys.executable,
        str(BRIDGE),
        "--stage",
        stage,
        "--profile",
        args.profile,
        "--agent-mode",
        args.live_bridge_agent_mode,
        "--provider",
        args.live_bridge_provider,
        "--model",
        args.live_bridge_model,
    ]
    if reviewer_role:
        command.extend(["--reviewer-role", reviewer_role])
    if stage == "code_execution" and not args.live_bridge_no_yolo:
        command.append("--allow-yolo")
        command.extend(["--max-turns", str(args.live_bridge_code_max_turns)])
    elif stage in {"external_research", "requirements_discussion", "requirements_review", "solution_review", "code_review"}:
        command.extend(["--max-turns", str(args.live_bridge_agent_max_turns)])
    elif stage == "verification":
        command.extend(
            [
                "--verification-command-timeout-seconds",
                str(args.live_bridge_verification_command_timeout_seconds),
            ]
        )
    if stage == "deployment" and not args.no_internal_api_restart:
        command.append("--allow-internal-api-restart")
    return " ".join(shlex.quote(str(part)) for part in command)


def default_live_bridge_args(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    if not args.live or args.no_live_bridge:
        return []

    injected: list[str] = []
    inject_deployment = not args.skip_deployment_command and not requirement_disables_deployment(
        requirement_from_passthrough(passthrough)
    )
    command_options = [
        ("--research-command", "external_research"),
        ("--requirements-discussion-command", "requirements_discussion"),
        ("--code-command", "code_execution"),
        ("--verification-command", "verification"),
        ("--memory-write-command", "memory_writeback"),
    ]
    review_command_options = [
        ("--requirements-review-command", "requirements_review", "reviewer-a"),
        ("--requirements-review-command", "requirements_review", "reviewer-b"),
        ("--solution-review-command", "solution_review", "reviewer-a"),
        ("--solution-review-command", "solution_review", "reviewer-b"),
        ("--code-review-command", "code_review", "reviewer-a"),
        ("--code-review-command", "code_review", "reviewer-b"),
    ]
    if inject_deployment:
        command_options.insert(5, ("--deployment-command", "deployment"))
    if not args.skip_git_publish_command:
        command_options.append(("--git-publish-command", "git_publish"))
    for option, stage in command_options:
        if not option_present(passthrough, option):
            injected.extend([option, bridge_command(stage, args)])
    for option, stage, reviewer_role in review_command_options:
        if not option_present(passthrough, option):
            injected.extend([option, bridge_command(stage, args, reviewer_role=reviewer_role)])
    if not option_present(passthrough, "--command-timeout-seconds"):
        injected.extend(["--command-timeout-seconds", str(args.live_bridge_timeout_seconds)])
    return injected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart arbitrage project delivery pipeline entry")
    parser.add_argument("--source", default="discord")
    parser.add_argument("--profile", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROFILE", "arbitrageagent"))
    parser.add_argument("--live", action="store_true", help="kept for compatibility; this entrypoint always runs live")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-live-bridge", action="store_true", help="do not inject default live evidence commands")
    parser.add_argument("--live-bridge-agent-mode", choices=["hermes", "echo"], default=os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MODE", "hermes"))
    parser.add_argument("--live-bridge-provider", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROVIDER", "openai-codex"))
    parser.add_argument("--live-bridge-model", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_MODEL", "gpt-5.5"))
    parser.add_argument("--live-bridge-timeout-seconds", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_TIMEOUT_SECONDS", "1800")))
    parser.add_argument(
        "--live-bridge-verification-command-timeout-seconds",
        type=int,
        default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS", "300")),
        help="per-command timeout used inside the live verification bridge",
    )
    parser.add_argument("--live-bridge-agent-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MAX_TURNS", "24")))
    parser.add_argument("--live-bridge-code-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_CODE_MAX_TURNS", "60")))
    parser.add_argument("--code-agent", choices=["backend-dev", "frontend-dev"], default=normalize_code_agent(os.environ.get("SMART_ARB_CODE_AGENT", "")), help="workflow owner for code execution; defaults to inferred backend/frontend owner")
    parser.add_argument("--live-bridge-no-yolo", action="store_true", help="do not let Hermes bypass command approvals for code execution")
    parser.add_argument("--no-internal-api-restart", action="store_true", help="do not restart the internal FastAPI tmux service in deployment stage")
    parser.add_argument("--skip-deployment-command", action="store_true", help="do not inject the deployment stage live bridge command")
    parser.add_argument(
        "--skip-git-publish-command",
        action="store_true",
        default=env_flag("SMART_ARB_SKIP_GIT_PUBLISH_COMMAND", False),
        help="do not inject the gated git publish stage",
    )
    parser.add_argument("--emit-json", action="store_true", help="print raw pipeline JSON instead of the chat summary")
    parser.add_argument("--no-chat-summary", action="store_true", help="print raw runner output without the chat summary")
    parser.add_argument("--chat-stage-limit", type=int, default=int(os.environ.get("SMART_ARB_CHAT_STAGE_LIMIT", "20")))
    parser.add_argument("--chat-command-limit", type=int, default=int(os.environ.get("SMART_ARB_CHAT_COMMAND_LIMIT", "24")))
    parser.add_argument(
        "--auto-repair-attempts",
        type=int,
        default=int(os.environ.get("SMART_ARB_AUTO_REPAIR_ATTEMPTS", "2")),
        help="retry repairable blocked live runs through the same pipeline",
    )
    parser.add_argument("--no-auto-repair", action="store_true", help="disable automatic pipeline repair loops")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, passthrough = parser.parse_known_args(argv)
    if args.dry_run or option_present(passthrough, "--dry-run"):
        parser.error("dry-run is disabled for smart-arb-pipeline; execution requests always run live")
    args.live = True

    profile = args.profile or "arbitrageagent"
    run_id = utc_run_id(f"{args.source}-{profile}")
    cmd = [
        sys.executable,
        str(RUNNER),
        "--project-key",
        PROJECT_KEY,
        "--runtime-host",
        "hermes",
        "--runtime-home",
        str(RUNTIME_HOME),
        "--workspace-root",
        str(WORKSPACE_ROOT),
        "--project-memory-root",
        str(PROJECT_MEMORY_ROOT),
        "--command-cwd",
        str(PROJECT_DIR),
        "--record-task-center",
        "--task-center-db",
        str(TASK_CENTER_DB),
        "--write-project-memory",
        "--run-id",
        run_id,
        "--source-url",
        f"{args.source}:{profile}",
        "--force",
        "--emit-json",
    ]
    requirement_text = requirement_from_passthrough(passthrough)
    code_agent = normalize_code_agent(args.code_agent) or infer_code_agent(requirement_text)
    cmd += ["--code-agent", code_agent]
    cmd += default_live_bridge_args(args, passthrough)
    cmd += passthrough
    proc = run_pipeline_command(cmd)
    state = parse_runner_state(proc.stdout)
    repair_history: list[dict[str, object]] = []
    repair_attempts = 0
    max_repair_attempts = 0 if args.no_auto_repair else max(0, int(args.auto_repair_attempts or 0))
    repair_env = dict(os.environ)

    while state:
        do_repair, risk, reasons = should_auto_repair(state, repair_attempts, max_repair_attempts)
        if not do_repair:
            if str(state.get("status") or "") == "blocked":
                state["auto_repair"] = {
                    "attempts": repair_attempts,
                    "decision": compact_text(f"未继续自动修复: {risk}; {', '.join(reasons)}", 360),
                    "history": repair_history,
                }
            break
        repair_attempts += 1
        repair_env.pop("SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE", None)
        repair_env.pop("PIPELINE_REPAIR_CONTEXT_FILE", None)
        context_text = repair_context_markdown(state, repair_attempts, risk, reasons)
        context_file = write_repair_context_file(state, repair_attempts, risk, reasons, context_text)
        repair_run_id = f"{run_id}-repair{repair_attempts}"
        repair_cmd = command_with_option_value(cmd, "--run-id", repair_run_id)
        repair_env["PIPELINE_REPAIR_CONTEXT"] = context_text
        repair_env["SMART_ARB_ENTRY_REPAIR_CONTEXT"] = context_text
        repair_env["PIPELINE_REPAIR_ATTEMPT"] = str(repair_attempts)
        if context_file is not None:
            repair_env["SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE"] = str(context_file)
            repair_env["PIPELINE_REPAIR_CONTEXT_FILE"] = str(context_file)
        repair_item: dict[str, object] = {
            "attempt": repair_attempts,
            "run_id": repair_run_id,
            "failed_stage": state.get("failed_stage"),
            "next_action": state.get("next_action"),
            "risk": risk,
            "reason": ", ".join(reasons),
            "context_file": str(context_file or ""),
            "context_delivery": "file+env" if context_file is not None else "env",
        }
        proc = run_pipeline_command(repair_cmd, env=repair_env)
        next_state = parse_runner_state(proc.stdout)
        repair_item["returncode"] = int(proc.returncode)
        repair_item["result_status"] = next_state.get("status") if isinstance(next_state, dict) else "unparsed"
        repair_history.append(repair_item)
        if not next_state:
            break
        state = next_state

    if state and repair_history:
        state["auto_repair"] = {
            "attempts": repair_attempts,
            "decision": (
                "自动修复后通过"
                if state.get("status") == "completed"
                else compact_text(f"自动修复后仍未通过: {state.get('status')} / {state.get('failed_stage')}", 360)
            ),
            "history": repair_history,
        }

    if args.emit_json or args.no_chat_summary:
        if args.emit_json and state and repair_history:
            print(json.dumps(state, ensure_ascii=False))
        elif proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
    else:
        print(
            render_chat_summary(
                state,
                source=args.source,
                profile=profile,
                returncode=int(proc.returncode),
                raw_stdout=proc.stdout,
                raw_stderr=proc.stderr,
                stage_limit=args.chat_stage_limit,
                command_limit=args.chat_command_limit,
            )
        )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Execute pending task-center items by invoking OpenClaw agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow_views import build_task_executor_event, render_human_view
from policy_enforcer import PolicyEnforcer, RuntimePaths, cmd_init, runtime_defaults  # type: ignore
from alert_dedupe import (
    WORKFLOW_FAILURE_BUCKET,
    build_workflow_failure_signature,
    check_and_record_signature,
    extract_workflow_failure_tokens_from_task,
    load_dedupe_state,
    resolve_shared_alert_state_path,
    save_dedupe_state,
    workflow_tokens_from_job_ids,
)

UTC = timezone.utc
GOVERNANCE_BRIDGE_EPILOG = (
    "Bridge contract: this Python executor is usually triggered from official "
    "OpenClaw cron/hooks/webhook surfaces, uses structured JSON for machine output, "
    "and does not mutate vendor private runtime files directly."
)
AUTO_MODEL_SENTINELS = {"", "auto", "default"}
LEGACY_DEFAULT_MODEL = "volcengine/kimi-k2.5"
DEFAULT_THINKING_LEVEL = "high"
NOTIFY_ON_MODES = {"error", "activity", "always"}
ERROR_TASK_STATUSES = {"failed", "partial", "escalated"}
RETRYABLE_AGENT_ERROR_PATTERNS = (
    "api rate limit reached",
    "too many requests",
    "http_error:429",
    "status code: 429",
    "status=429",
    "failovererror: ⚠️ api rate limit reached",
)


BENIGN_STDERR_PATTERNS = (
    "loaded without install/load-path provenance",
    "treat as untracked local code and pin trust via plugins.allow or install records",
)
GATEWAY_ACK_TIMEOUT_MS = 30_000
GATEWAY_HISTORY_LIMIT = 200


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    direct = parse_json_output(raw)
    if isinstance(direct, dict):
        return direct
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    for block in fenced:
        parsed = parse_json_output(block)
        if isinstance(parsed, dict):
            return parsed
    m = re.search(r"(\{[\s\S]*\})", raw)
    if m:
        parsed = parse_json_output(m.group(1))
        if isinstance(parsed, dict):
            return parsed
    return None


def split_list(value: Any) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
    else:
        text = str(value or "").strip()
        if not text:
            return []
        out = [x.strip() for x in re.split(r"[,\n;|，；、]+", text) if x.strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def load_policy(policy_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(policy_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_codex_model(model_name: str) -> bool:
    return str(model_name or "").strip().startswith("openai-codex/")


def normalize_thinking(value: Any, default: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"off", "minimal", "low", "medium", "high", "xhigh", "adaptive"}:
        return normalized
    return str(default or "").strip().lower()


def resolve_executor_selection(requested_model: str, assignee: str, policy_file: Path) -> tuple[str, str, str]:
    normalized = str(requested_model or "").strip()
    if normalized and normalized.lower() not in AUTO_MODEL_SENTINELS:
        policy = load_policy(policy_file)
        thinking_map = policy.get("model_thinking_overrides", {})
        thinking = ""
        if isinstance(thinking_map, dict):
            thinking = normalize_thinking(thinking_map.get(normalized), DEFAULT_THINKING_LEVEL)
        if not thinking:
            thinking = DEFAULT_THINKING_LEVEL
        return normalized, "cli", thinking

    policy = load_policy(policy_file)
    if not policy:
        return LEGACY_DEFAULT_MODEL, "legacy-default", DEFAULT_THINKING_LEVEL

    agent_overrides = policy.get("agent_model_overrides", {})
    if isinstance(agent_overrides, dict):
        assignee_key = str(assignee or "").strip()
        target = str(agent_overrides.get(assignee_key, "")).strip()
        if target:
            thinking_map = policy.get("model_thinking_overrides", {})
            thinking = ""
            if isinstance(thinking_map, dict):
                thinking = normalize_thinking(thinking_map.get(target), DEFAULT_THINKING_LEVEL)
            if not thinking:
                thinking = DEFAULT_THINKING_LEVEL
            return target, f"policy-agent:{assignee_key}", thinking

    thinking_map = policy.get("model_thinking_overrides", {})
    primary = str(policy.get("primary_model", "")).strip()
    allowed_raw = policy.get("allowed_models", [])
    allowed = [str(item).strip() for item in allowed_raw if str(item).strip()] if isinstance(allowed_raw, list) else []
    if primary and primary in allowed:
        thinking = normalize_thinking(thinking_map.get(primary), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return primary, "policy-primary", (thinking or DEFAULT_THINKING_LEVEL)
    if allowed:
        thinking = normalize_thinking(thinking_map.get(allowed[0]), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return allowed[0], "policy-allowed[0]", (thinking or DEFAULT_THINKING_LEVEL)
    if primary:
        thinking = normalize_thinking(thinking_map.get(primary), DEFAULT_THINKING_LEVEL) if isinstance(thinking_map, dict) else DEFAULT_THINKING_LEVEL
        return primary, "policy-primary", (thinking or DEFAULT_THINKING_LEVEL)
    return LEGACY_DEFAULT_MODEL, "legacy-default", DEFAULT_THINKING_LEVEL


def normalize_contract(reply_text: str) -> dict[str, Any]:
    parsed = extract_json_object(reply_text) or {}
    status = str(parsed.get("status", "")).strip().lower()
    solved = bool(parsed.get("solved", False))
    if status not in {"passed", "failed", "partial", "escalated"}:
        status = "passed" if solved else "partial"
    if status == "passed":
        solved = True

    try:
        quality_score = float(parsed.get("quality_score", 70.0))
    except Exception:
        quality_score = 70.0
    quality_score = max(0.0, min(100.0, quality_score))

    quality_grade = str(parsed.get("quality_grade", "")).strip().lower()
    if quality_grade not in {"a", "b", "c", "d"}:
        quality_grade = "a" if quality_score >= 90 else ("b" if quality_score >= 80 else ("c" if quality_score >= 70 else "d"))

    failed_items = split_list(parsed.get("failed_items"))
    failure_count = int(parsed.get("failure_count", len(failed_items) or (1 if status in {"failed", "partial"} else 0)) or 0)
    failure_count = max(0, failure_count)

    summary = str(parsed.get("resolution_summary", "")).strip() or str(reply_text or "").strip()[:400]
    steps = split_list(parsed.get("resolution_steps"))
    resolved = split_list(parsed.get("resolved_issues"))
    missing = split_list(parsed.get("context_fields_missing"))

    try:
        cost_estimate = float(parsed.get("cost_estimate", 0.0))
    except Exception:
        cost_estimate = 0.0
    cost_estimate = max(0.0, cost_estimate)

    return {
        "status": status,
        "solved": solved,
        "resolution_summary": summary,
        "resolution_steps": steps,
        "resolved_issues": resolved,
        "failed_items": failed_items,
        "failure_count": failure_count,
        "quality_score": quality_score,
        "quality_grade": quality_grade,
        "need_clarification": bool(parsed.get("need_clarification", False)),
        "clarification_reason": str(parsed.get("clarification_reason", "")).strip(),
        "context_fields_missing": missing,
        "cost_estimate": cost_estimate,
        "raw_text": str(reply_text or "").strip(),
    }


def sanitize_agent_stderr(stderr_text: str) -> str:
    lines = [line.strip() for line in str(stderr_text or "").splitlines() if line.strip()]
    kept: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(pattern in lowered for pattern in BENIGN_STDERR_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def contract_from_agent_result(exit_code: int, stdout_text: str, stderr_text: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    agent_json = parse_json_output(stdout_text) or {}
    payloads = agent_json.get("payloads", [])
    reply_text = ""
    if isinstance(payloads, list):
        reply_text = "\n".join(str(x.get("text", "")).strip() for x in payloads if isinstance(x, dict) and str(x.get("text", "")).strip())
    if not reply_text:
        reply_text = str(stdout_text or "").strip()

    sanitized_stderr = sanitize_agent_stderr(stderr_text)
    if int(exit_code or 0) != 0 and (not reply_text):
        reply_text = sanitized_stderr or str(stderr_text or "").strip()

    contract = normalize_contract(reply_text)
    if int(exit_code or 0) != 0:
        contract["status"] = "failed"
        contract["solved"] = False
        contract["failure_count"] = max(1, int(contract.get("failure_count", 0)))
    elif not reply_text:
        contract["status"] = "failed"
        contract["solved"] = False
        contract["failure_count"] = max(1, int(contract.get("failure_count", 0)))
        contract["resolution_summary"] = "agent_returned_no_structured_output"
        contract["raw_text"] = sanitized_stderr

    return contract, agent_json, reply_text, sanitized_stderr


def default_stage(assignee: str) -> str:
    agent = str(assignee or "").strip().lower()
    if agent in {"coordinator", "project-agent", "agent-factory"}:
        return "plan"
    if agent == "tester":
        return "test-loop"
    if agent == "reviewer":
        return "review"
    if agent == "doc-writer":
        return "document"
    if agent == "deployer":
        return "deploy"
    return "implement"


def normalize_notify_on(value: str) -> str:
    mode = str(value or "error").strip().lower()
    return mode if mode in NOTIFY_ON_MODES else "error"


def compact_text(value: Any, max_len: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_task_session_id(task_id: str, max_len: int = 48) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(task_id or "").strip()).strip("-._")
    if not normalized:
        normalized = "task"
    candidate = f"task-{normalized}"
    if len(candidate) <= max_len:
        return candidate
    digest = hashlib.sha1(str(task_id or "").encode("utf-8")).hexdigest()[:10]
    head_budget = max(8, max_len - len("task--") - len(digest))
    head = normalized[:head_budget].rstrip("-._") or "task"
    session_id = f"task-{head}-{digest}"
    return session_id[:max_len]


def normalize_agent_session_token(value: str, fallback: str = "main") -> str:
    token = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-_")
    return token[:64] or fallback


def build_gateway_agent_session_key(assignee: str, session_id: str) -> str:
    agent_id = normalize_agent_session_token(assignee, fallback="main")
    run_token = normalize_agent_session_token(session_id, fallback="task")
    return f"agent:{agent_id}:cron:task-executor:run:{run_token}"


def extract_latest_assistant_text(history_payload: dict[str, Any]) -> str:
    messages = history_payload.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for candidate in reversed(messages):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("role", "")).strip().lower() != "assistant":
            continue
        content = candidate.get("content", [])
        if not isinstance(content, list):
            continue
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).strip().lower() != "text":
                continue
            text = str(item.get("text", "")).strip()
            if text:
                texts.append(text)
        if texts:
            return "\n".join(texts).strip()
    return ""


def humanize_executor_detail(detail: str) -> str:
    text = compact_text(detail, 220)
    lower = text.lower()
    if lower in {"timeout", "timed out"}:
        return "超时"
    if lower == "waiting_human_confirm":
        return "等待人工确认"
    if lower == "needs_clarification":
        return "任务信息不足，需要补充上下文"
    return text or "未提供详细信息"


def humanize_executor_reason(reason: str, status: str) -> tuple[str, str]:
    raw = str(reason or "").strip()
    normalized_status = str(status or "").strip().lower()
    lower = raw.lower()
    if lower.startswith("pre_stage_failed:model blocked by policy:"):
        model = raw.split(":", 2)[-1].strip() or "-"
        return "模型被策略拦截", f"执行前检查失败：模型 {model} 被策略禁止"
    if lower.startswith("pre_stage_failed:"):
        detail = raw.split(":", 1)[1].strip()
        return "执行前检查失败", humanize_executor_detail(detail)
    if lower.startswith("report_failed:"):
        detail = raw.split(":", 1)[1].strip()
        return "执行结果回写失败", humanize_executor_detail(detail)
    if lower.startswith("call_agent_exception:"):
        detail = raw.split(":", 1)[1].strip()
        return "调用执行代理失败", humanize_executor_detail(detail)
    if lower == "waiting_human_confirm":
        return "等待人工确认", "任务要求人工确认，当前尚未确认"
    if lower == "needs_clarification":
        return "上下文不足", "任务上下文不足，需要补充说明后再执行"
    if normalized_status == "partial":
        return "任务仅部分完成", humanize_executor_detail(raw or "仅部分完成")
    if normalized_status == "escalated":
        return "任务已升级处理", humanize_executor_detail(raw or "已升级给更高优先级处理")
    if normalized_status == "failed":
        return "任务执行失败", humanize_executor_detail(raw)
    return "任务状态异常", humanize_executor_detail(raw or normalized_status or "unknown")


def result_is_error(item: dict[str, Any]) -> bool:
    status = str(item.get("status", "")).strip().lower()
    report_status = str(item.get("report_status", "")).strip().lower()
    task_status_after = str(item.get("task_status_after", "")).strip().lower()
    if status == "failed":
        return True
    if report_status in ERROR_TASK_STATUSES:
        return True
    if task_status_after in ERROR_TASK_STATUSES:
        return True
    return False


def build_chat_output(summary: dict[str, Any], report_path: Path, notify_on: str) -> str:
    event = build_task_executor_event(summary, report_path, normalize_notify_on(notify_on))
    return render_human_view(event["views"]["human"])


def apply_shared_alert_dedupe(
    summary: dict[str, Any],
    state_path: Path,
    *,
    cooldown_minutes: int,
    now_text: str = "",
) -> dict[str, Any]:
    dedupe = {
        "suppressed": False,
        "reason": "",
        "bucket": WORKFLOW_FAILURE_BUCKET,
        "signature": "",
        "tokens": [],
    }
    results = summary.get("results", [])
    if not isinstance(results, list):
        return dedupe
    error_items = [item for item in results if isinstance(item, dict) and result_is_error(item)]
    if not error_items:
        return dedupe

    tokens: list[str] = []
    for item in error_items:
        item_tokens = item.get("workflow_alert_tokens", [])
        if not isinstance(item_tokens, list) or not item_tokens:
            item_tokens = extract_workflow_failure_tokens_from_task(
                item.get("task_id", ""),
                task_type=item.get("task_type", ""),
                requirement=item.get("requirement", ""),
                context_payload=item.get("context_payload"),
            )
        if not item_tokens:
            return dedupe
        tokens.extend(item_tokens)

    normalized_tokens = workflow_tokens_from_job_ids(tokens)
    signature = build_workflow_failure_signature(normalized_tokens)
    if not signature:
        return dedupe

    state = load_dedupe_state(state_path)
    suppressed, reason = check_and_record_signature(
        state,
        bucket=WORKFLOW_FAILURE_BUCKET,
        signature=signature,
        now_text=now_text or str(summary.get("started_at", "")),
        cooldown_minutes=max(1, int(cooldown_minutes or 60)),
        meta={
            "source": "task_executor_runner",
            "trigger_task": str(summary.get("trigger_task", "")).strip(),
            "run_id": str(summary.get("run_id", "")).strip(),
            "tokens": list(normalized_tokens),
        },
    )
    save_dedupe_state(state_path, state)
    dedupe["suppressed"] = suppressed
    dedupe["reason"] = reason
    dedupe["signature"] = signature
    dedupe["tokens"] = normalized_tokens
    return dedupe


def cli_flag_enabled(flag: str) -> bool:
    return str(flag or "").strip() in {str(part).strip() for part in sys.argv[1:]}


def cli_flag_value(flag: str, default: str = "") -> str:
    parts = sys.argv[1:]
    for idx, part in enumerate(parts):
        if part == flag and idx + 1 < len(parts):
            return str(parts[idx + 1]).strip()
        if part.startswith(flag + "="):
            return str(part.split("=", 1)[1]).strip()
    return default


def build_fatal_output(exc: Exception) -> str:
    task_name = cli_flag_value("--task", "cron:task-executor") or "cron:task-executor"
    issue, detail = humanize_executor_reason(str(exc), "failed")
    lines = [
        "任务执行异常",
        f"- 触发任务: {task_name}",
        f"- 时间: {now_iso()}",
        "- 问题: 执行器入口异常",
        f"- 异常类型: {exc.__class__.__name__}",
        f"- 详情: {issue}；{detail}",
    ]
    return "\n".join(lines)


def is_runtime_binding_task(task: dict[str, Any] | None) -> bool:
    if not isinstance(task, dict):
        return False
    if str(task.get("task_type", "")).strip().lower() == "ops_runtime_cron":
        return True
    return str(task.get("reason", "")).strip().startswith("[CRON_RUNTIME] bind ")


def select_tasks(enforcer: PolicyEnforcer, only_task_id: str, max_tasks: int) -> list[dict[str, Any]]:
    if str(only_task_id or "").strip():
        task = enforcer.db.get_task(str(only_task_id).strip())
        return [] if is_runtime_binding_task(task) else [task]
    rows = enforcer.db.conn.execute(
        """
        SELECT task_id FROM tasks
        WHERE status = 'pending'
        ORDER BY
          CASE pool WHEN 'jobs' THEN 0 ELSE 1 END ASC,
          CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC,
          created_at ASC
        LIMIT ?
        """,
        (max(1, int(max_tasks)) * 4,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        task = enforcer.db.get_task(str(row["task_id"]))
        if is_runtime_binding_task(task):
            continue
        out.append(task)
        if len(out) >= max_tasks:
            break
    return out


def local_context(repo_root: Path, task: dict[str, Any]) -> list[str]:
    query = str(task.get("reason", "")).strip() or str(task.get("requirement", "")).strip()
    if not query:
        return []
    token = split_list(re.sub(r"[^\w\u4e00-\u9fff]+", " ", query))
    if not token:
        return []
    key = token[0]
    try:
        proc = subprocess.run(
            ["rg", "-n", "--max-count", "8", key, "scripts", "docs", "agents", "openclaw"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()][:8]


def web_context(sources_file: Path, keyword: str, max_chars: int) -> list[dict[str, str]]:
    if not sources_file.exists() or not keyword:
        return []
    try:
        data = json.loads(sources_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    sources = data.get("sources", []) if isinstance(data, dict) else []
    if not isinstance(sources, list):
        return []
    out: list[dict[str, str]] = []
    for item in sources:
        if len(out) >= 2:
            break
        if not isinstance(item, dict) or not bool(item.get("enabled", True)):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "openclaw-task-executor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read(max(2048, int(max_chars))).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError):
            continue
        hit = body.lower().find(keyword.lower())
        if hit < 0:
            continue
        start = max(0, hit - 160)
        end = min(len(body), hit + 240)
        out.append({"id": str(item.get("id", "")).strip(), "url": url, "snippet": body[start:end].replace("\n", " ").strip()})
    return out


def prompt_for_task(task: dict[str, Any], local_hits: list[str], web_hits: list[dict[str, str]]) -> str:
    local_text = "\n".join(f"- {x}" for x in local_hits) or "- (none)"
    web_text = "\n".join(f"- [{x['id']}] {x['url']} | {x['snippet']}" for x in web_hits) or "- (none)"
    return f"""你是执行代理，请完成任务并只输出 JSON 对象（不要解释）。\n\n任务:\n- task_id: {task.get('task_id')}\n- reason: {task.get('reason')}\n- requirement: {task.get('requirement')}\n- result_output: {task.get('result_output')}\n- acceptance: {task.get('acceptance')}\n- observable_outputs: {task.get('observable_outputs')}\n- acceptance_thresholds: {task.get('acceptance_thresholds')}\n\n本地检索:\n{local_text}\n\n网络检索:\n{web_text}\n\n输出模板:\n{{\"status\":\"passed|failed|partial|escalated\",\"solved\":true,\"resolution_summary\":\"\",\"resolution_steps\":[],\"resolved_issues\":[],\"failed_items\":[],\"failure_count\":0,\"quality_score\":0,\"quality_grade\":\"a|b|c|d\",\"need_clarification\":false,\"clarification_reason\":\"\",\"context_fields_missing\":[],\"cost_estimate\":0}}"""


def call_agent(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    local_mode: bool,
    thinking: str = "",
) -> tuple[int, str, str]:
    openclaw_cmd = str(openclaw_bin or "openclaw").strip() or "openclaw"
    timeout_value = max(30, int(timeout_sec))
    cmd = [
        openclaw_cmd,
        "agent",
        "--agent",
        str(assignee or "").strip(),
        "--message",
        str(message or ""),
        "--session-id",
        str(session_id or "").strip(),
        "--json",
        "--timeout",
        str(timeout_value),
    ]
    normalized_thinking = normalize_thinking(thinking)
    if normalized_thinking:
        cmd.extend(["--thinking", normalized_thinking])
    if local_mode:
        cmd.append("--local")
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max(60, int(timeout_sec) + 30),
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def call_gateway_method(
    openclaw_bin: str,
    method: str,
    params: dict[str, Any],
    timeout_ms: int,
) -> tuple[int, str, str]:
    openclaw_cmd = str(openclaw_bin or "openclaw").strip() or "openclaw"
    cmd = [
        openclaw_cmd,
        "gateway",
        "call",
        str(method or "").strip(),
        "--json",
        "--timeout",
        str(max(1, int(timeout_ms))),
        "--params",
        json.dumps(params, ensure_ascii=False),
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max(30, int(timeout_ms / 1000) + 30),
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def call_agent_via_gateway_step(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    thinking: str = "",
) -> tuple[int, str, str]:
    timeout_value = max(30, int(timeout_sec))
    normalized_thinking = normalize_thinking(thinking)
    session_key = build_gateway_agent_session_key(assignee, session_id)
    idempotency_key = (
        f"task-exec-{normalize_agent_session_token(session_id, fallback='task')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    agent_params: dict[str, Any] = {
        "message": str(message or ""),
        "agentId": str(assignee or "").strip(),
        "sessionKey": session_key,
        "idempotencyKey": idempotency_key,
        "timeout": timeout_value,
    }
    if normalized_thinking:
        agent_params["thinking"] = normalized_thinking

    rc, out, err = call_gateway_method(
        openclaw_bin,
        "agent",
        agent_params,
        GATEWAY_ACK_TIMEOUT_MS,
    )
    if rc != 0:
        return rc, out, err

    accepted = parse_json_output(out) or {}
    run_id = str(accepted.get("runId", "")).strip() or idempotency_key
    wait_timeout_ms = max(GATEWAY_ACK_TIMEOUT_MS, timeout_value * 1000)
    rc_wait, out_wait, err_wait = call_gateway_method(
        openclaw_bin,
        "agent.wait",
        {"runId": run_id, "timeoutMs": wait_timeout_ms},
        wait_timeout_ms + 2_000,
    )
    if rc_wait != 0:
        return rc_wait, out_wait, err_wait

    wait_payload = parse_json_output(out_wait) or {}
    wait_status = str(wait_payload.get("status", "")).strip().lower()
    if wait_status != "ok":
        wait_error = str(wait_payload.get("error", "")).strip()
        return 1, "", wait_error or f"agent.wait status={wait_status or 'unknown'}"

    rc_history, out_history, err_history = call_gateway_method(
        openclaw_bin,
        "chat.history",
        {"sessionKey": session_key, "limit": GATEWAY_HISTORY_LIMIT},
        GATEWAY_ACK_TIMEOUT_MS,
    )
    if rc_history != 0:
        return rc_history, out_history, err_history

    history_payload = parse_json_output(out_history) or {}
    reply_text = extract_latest_assistant_text(history_payload)
    if not reply_text:
        return 1, "", "chat.history returned no assistant text"

    wrapped = {
        "payloads": [{"text": reply_text}],
        "meta": {
            "agentMeta": {
                "runId": run_id,
                "waitStatus": wait_status,
                "sessionKey": session_key,
                "sessionId": str(history_payload.get("sessionId", "")).strip(),
            }
        },
    }
    return 0, json.dumps(wrapped, ensure_ascii=False), ""


def is_retryable_agent_failure(exit_code: int, out: str, err: str) -> bool:
    if int(exit_code or 0) == 0:
        return False
    combined = "\n".join([str(out or ""), str(err or "")]).lower()
    return any(pattern in combined for pattern in RETRYABLE_AGENT_ERROR_PATTERNS)


def call_agent_with_retries(
    openclaw_bin: str,
    assignee: str,
    message: str,
    session_id: str,
    timeout_sec: int,
    local_mode: bool,
    thinking: str,
    *,
    max_retries: int,
    retry_delay_sec: int,
    prefer_gateway: bool = False,
) -> tuple[int, str, str, int, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    total_attempts = max(1, int(max_retries or 0) + 1)
    delay_base = max(1, int(retry_delay_sec or 1))
    for attempt_idx in range(total_attempts):
        if prefer_gateway:
            rc, out, err = call_agent_via_gateway_step(
                openclaw_bin,
                assignee,
                message,
                session_id,
                timeout_sec,
                thinking,
            )
        else:
            rc, out, err = call_agent(
                openclaw_bin,
                assignee,
                message,
                session_id,
                timeout_sec,
                local_mode,
                thinking,
            )
        retryable = is_retryable_agent_failure(rc, out, err)
        attempts.append(
            {
                "attempt": attempt_idx + 1,
                "exit_code": int(rc or 0),
                "retryable": retryable,
                "stderr_excerpt": str(err or "")[:300],
            }
        )
        if rc == 0 or (not retryable) or attempt_idx >= total_attempts - 1:
            return rc, out, err, attempt_idx + 1, attempts
        time.sleep(delay_base * (attempt_idx + 1))
    return rc, out, err, total_attempts, attempts


def extract_usage(agent_json: dict[str, Any]) -> tuple[int, int, int]:
    meta = agent_json.get("meta", {})
    duration_ms = int(meta.get("durationMs", 0) or 0) if isinstance(meta, dict) else 0
    usage = ((meta.get("agentMeta", {}) if isinstance(meta, dict) else {}).get("usage", {}))
    if not isinstance(usage, dict):
        return 0, 0, max(0, duration_ms)
    return max(0, int(usage.get("input", 0) or 0)), max(0, int(usage.get("output", 0) or 0)), max(0, duration_ms)


def ns(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def main() -> int:
    defaults = runtime_defaults()
    repo_root = Path(__file__).resolve().parents[3]

    parser = argparse.ArgumentParser(
        description="Execute pending tasks by calling assigned agents",
        epilog=GOVERNANCE_BRIDGE_EPILOG,
    )
    parser.add_argument("--db", default=defaults["db"])
    parser.add_argument("--policy-file", default=defaults["policy_file"])
    parser.add_argument("--routing-file", default=defaults["routing_file"])
    parser.add_argument("--pricing-file", default=defaults["pricing_file"])
    parser.add_argument("--task", default="")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--planner-id", default="coordinator")
    parser.add_argument("--max-tasks", type=int, default=3)
    parser.add_argument("--only-task-id", default="")
    parser.add_argument("--timeout-sec", type=int, default=1200)
    parser.add_argument("--local-agent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--web-sources-file", default=str(repo_root / "scripts/openclaw-ops/web/project_docs_sources.json"))
    parser.add_argument("--web-max-chars", type=int, default=12000)
    parser.add_argument("--report-dir", default=str(repo_root / ".workflow/executor-runs"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notify-on", default="error", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--shared-alert-state-file", default=str(resolve_shared_alert_state_path()))
    parser.add_argument("--shared-alert-cooldown-minutes", type=int, default=60)
    parser.add_argument("--agent-max-retries", type=int, default=2)
    parser.add_argument("--agent-retry-delay-sec", type=int, default=20)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    paths = RuntimePaths(
        db=Path(args.db).expanduser(),
        policy_file=Path(args.policy_file).expanduser(),
        routing_file=Path(args.routing_file).expanduser(),
        pricing_file=Path(args.pricing_file).expanduser(),
    )
    requested_model = str(args.model or "").strip()
    has_fixed_model = bool(requested_model and requested_model.lower() not in AUTO_MODEL_SENTINELS)
    cmd_init(paths, force=False)
    enforcer = PolicyEnforcer(paths)

    run_id = f"exec-{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:8]}"
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "started_at": now_iso(),
        "tasks_selected": 0,
        "tasks_executed": 0,
        "tasks_skipped": 0,
        "tasks_failed": 0,
        "bridge": {
            "trigger_surfaces": ["cron", "hooks", "webhook"],
            "machine_output": "json",
            "vendor_state_policy": "no-direct-vendor-private-state-writes",
        },
        "trigger_task": str(args.task).strip(),
        "executor_model": (requested_model if has_fixed_model else "auto(per-assignee)"),
        "executor_model_source": ("cli" if has_fixed_model else "policy-agent-overrides"),
        "executor_thinking": "auto(by-model)",
        "results": [],
    }

    try:
        tasks = select_tasks(enforcer, str(args.only_task_id), max(1, int(args.max_tasks)))
        summary["tasks_selected"] = len(tasks)

        for task in tasks:
            task_id = str(task.get("task_id", "")).strip()
            assignee = str(task.get("assignee", "")).strip() or "backend-dev"
            stage = default_stage(assignee)
            task_type = str(task.get("task_type", "")).strip()
            workflow_alert_tokens = extract_workflow_failure_tokens_from_task(
                task_id,
                task_type=task_type,
                requirement=task.get("requirement", ""),
                context_payload=task.get("context_payload"),
            )
            task_model_name, task_model_source, task_thinking = resolve_executor_selection(
                requested_model,
                assignee,
                paths.policy_file,
            )
            task_cli_thinking = task_thinking if is_codex_model(task_model_name) else ""
            result: dict[str, Any] = {
                "task_id": task_id,
                "assignee": assignee,
                "stage": stage,
                "status": "skipped",
                "reason": "",
                "model": task_model_name,
                "model_source": task_model_source,
                "thinking": task_thinking,
                "task_type": task_type,
                "workflow_alert_tokens": workflow_alert_tokens,
            }

            if bool(task.get("needs_clarification")):
                result["reason"] = "needs_clarification"
                summary["tasks_skipped"] += 1
                summary["results"].append(result)
                continue
            if bool(task.get("need_human_confirm")) and (not bool(task.get("human_confirmed"))):
                result["reason"] = "waiting_human_confirm"
                summary["tasks_skipped"] += 1
                summary["results"].append(result)
                continue

            local_hits = local_context(repo_root, task)
            keyword = split_list(str(task.get("reason", "")))
            web_hits = web_context(Path(args.web_sources_file).expanduser(), keyword[0] if keyword else "", int(args.web_max_chars))
            prompt = prompt_for_task(task, local_hits, web_hits)
            session_id = build_task_session_id(task_id)

            try:
                enforcer.db.add_event(task_id=task_id, actor=str(args.actor), event_type="task_decomposed", stage="dispatch", details={"steps": [
                    {"id": "s1", "owner": "project-agent", "title": "澄清范围"},
                    {"id": "s2", "owner": assignee, "title": "实现改动"},
                    {"id": "s3", "owner": "tester", "title": "执行验证"},
                    {"id": "s4", "owner": "doc-writer", "title": "输出验收文档"},
                ]})
            except Exception:
                pass

            try:
                enforcer.pre_stage(
                    ns(
                        task_id=task_id,
                        stage=stage,
                        agent_id=assignee,
                        model=task_model_name,
                        input_ref=str(report_dir),
                        actor=str(args.actor),
                    )
                )
            except Exception as exc:
                result["status"] = "failed"
                result["reason"] = f"pre_stage_failed:{exc}"
                summary["tasks_failed"] += 1
                summary["results"].append(result)
                continue

            if args.dry_run:
                result["status"] = "dry_run"
                result["reason"] = "execution_skipped"
                summary["tasks_executed"] += 1
                summary["results"].append(result)
                continue

            started = datetime.now(tz=UTC)
            try:
                rc, out, err, agent_attempts, agent_attempt_details = call_agent_with_retries(
                    str(args.openclaw_bin),
                    assignee,
                    prompt,
                    session_id,
                    int(args.timeout_sec),
                    bool(args.local_agent),
                    task_cli_thinking,
                    max_retries=int(args.agent_max_retries),
                    retry_delay_sec=int(args.agent_retry_delay_sec),
                    prefer_gateway=bool(args.local_agent),
                )
            except Exception as exc:
                rc, out, err, agent_attempts, agent_attempt_details = 1, "", f"call_agent_exception:{exc}", 1, []
            agent_log_path = report_dir / f"{run_id}-{task_id}.agent.log"
            try:
                agent_log_path.write_text(
                    "\n".join(
                        [
                            f"task_id={task_id}",
                            f"assignee={assignee}",
                            f"model={task_model_name}",
                            f"model_source={task_model_source}",
                            f"thinking={task_thinking}",
                            f"session_id={session_id}",
                            f"exit_code={rc}",
                            f"attempts={agent_attempts}",
                            "=== STDOUT ===",
                            str(out or ""),
                            "=== STDERR ===",
                            str(err or ""),
                            "=== ATTEMPTS ===",
                            json.dumps(agent_attempt_details, ensure_ascii=False),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            post_reason = "ok" if rc == 0 else f"agent_exit_{rc}"
            try:
                enforcer.post_stage(ns(task_id=task_id, stage=stage, exit_code=str(rc), reason=post_reason, output_ref=str(agent_log_path), actor=str(args.actor)))
            except Exception:
                pass

            contract, agent_json, reply_text, sanitized_stderr = contract_from_agent_result(rc, out, err)
            in_tokens, out_tokens, duration_ms = extract_usage(agent_json)
            if duration_ms <= 0:
                duration_ms = max(0, int((datetime.now(tz=UTC) - started).total_seconds() * 1000))

            if bool(contract.get("need_clarification")):
                try:
                    enforcer.db.update_clarification(
                        task_id=task_id,
                        actor=assignee,
                        needs_clarification=True,
                        clarification_reason=str(contract.get("clarification_reason", "")).strip() or "agent_need_clarification",
                        context_payload=task.get("context_payload", {}),
                        context_completeness=float(task.get("context_completeness", 0.0) or 0.0),
                        context_fields_missing=list(contract.get("context_fields_missing", [])),
                        context_fields_recommended_missing=list(task.get("context_fields_recommended_missing", [])),
                    )
                except Exception:
                    pass

            try:
                if (in_tokens + out_tokens) > 0:
                    enforcer.record_token(
                        ns(
                            task_id=task_id,
                            agent_id=assignee,
                            model=task_model_name,
                            input_tokens=str(in_tokens),
                            output_tokens=str(out_tokens),
                        )
                    )
            except Exception:
                pass

            details = {
                "run_id": run_id,
                "session_id": session_id,
                "model": task_model_name,
                "model_source": task_model_source,
                "thinking": task_thinking,
                "command_exit_code": rc,
                "agent_attempts": agent_attempts,
                "agent_attempt_details": agent_attempt_details,
                "stderr_excerpt": str(err or "")[:1200],
                "stderr_sanitized_excerpt": str(sanitized_stderr or "")[:1200],
                "local_context_hits": len(local_hits),
                "web_context_hits": len(web_hits),
                "raw_reply_excerpt": str(contract.get("raw_text", ""))[:1200],
            }
            try:
                report = enforcer.report_agent_result(
                    ns(
                        task_id=task_id,
                        agent_id=assignee,
                        planner_id=str(args.planner_id),
                        status=str(contract.get("status", "partial")),
                        solved="true" if bool(contract.get("solved", False)) else "false",
                        resolved_issues=",".join(contract.get("resolved_issues", [])),
                        resolution_summary=str(contract.get("resolution_summary", "")),
                        resolution_steps=",".join(contract.get("resolution_steps", [])),
                        failed_items=",".join(contract.get("failed_items", [])),
                        failure_count=str(max(0, int(contract.get("failure_count", 0) or 0))),
                        duration_ms=str(max(0, int(duration_ms))),
                        model=task_model_name,
                        input_tokens=str(max(0, int(in_tokens))),
                        output_tokens=str(max(0, int(out_tokens))),
                        cost_estimate=str(max(0.0, float(contract.get("cost_estimate", 0.0) or 0.0))),
                        quality_score=str(max(0.0, min(float(contract.get("quality_score", 0.0) or 0.0), 100.0))),
                        quality_grade=str(contract.get("quality_grade", "c")),
                        notify_chat="false",
                        details_json=json.dumps(details, ensure_ascii=False),
                        actor=assignee,
                    )
                )
            except Exception as exc:
                result["status"] = "failed"
                result["reason"] = f"report_failed:{exc}"
                summary["tasks_failed"] += 1
                summary["results"].append(result)
                continue

            end_status = str(report.get("task_status_sync", {}).get("task_status_after", "")).strip() or str(contract.get("status", "partial"))
            result.update(
                {
                    "status": "executed",
                    "task_status_after": end_status,
                    "report_status": str(contract.get("status", "partial")),
                    "solved": bool(contract.get("solved", False)),
                    "quality_score": float(contract.get("quality_score", 0.0) or 0.0),
                    "duration_ms": duration_ms,
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                }
            )
            summary["tasks_executed"] += 1
            summary["results"].append(result)
    finally:
        enforcer.close()

    summary["finished_at"] = now_iso()
    summary["alert_dedupe"] = apply_shared_alert_dedupe(
        summary,
        Path(args.shared_alert_state_file).expanduser(),
        cooldown_minutes=max(1, int(args.shared_alert_cooldown_minutes)),
        now_text=str(summary.get("started_at", "")),
    )
    report_path = report_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["report_file"] = str(report_path)

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(build_chat_output(summary, report_path, str(args.notify_on)))
    return 0


def run_cli() -> int:
    try:
        return main()
    except Exception as exc:
        output = build_fatal_output(exc)
        payload = {
            "ok": False,
            "notify": True,
            "output": output,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if cli_flag_enabled("--emit-json"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(output)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

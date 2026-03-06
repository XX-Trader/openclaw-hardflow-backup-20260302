#!/usr/bin/env python3
"""Execute pending task-center items by invoking OpenClaw agents."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from policy_enforcer import PolicyEnforcer, RuntimePaths, cmd_init, runtime_defaults  # type: ignore

UTC = timezone.utc
GOVERNANCE_BRIDGE_EPILOG = (
    "Bridge contract: this Python executor is usually triggered from official "
    "OpenClaw cron/hooks/webhook surfaces, uses structured JSON for machine output, "
    "and does not mutate vendor private runtime files directly."
)
AUTO_MODEL_SENTINELS = {"", "auto", "default"}
LEGACY_DEFAULT_MODEL = "volcengine/kimi-k2.5"
NOTIFY_ON_MODES = {"error", "activity", "always"}
ERROR_TASK_STATUSES = {"failed", "partial", "escalated"}


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


def resolve_executor_model(requested_model: str, policy_file: Path) -> tuple[str, str]:
    normalized = str(requested_model or "").strip()
    if normalized and normalized.lower() not in AUTO_MODEL_SENTINELS:
        return normalized, "cli"

    try:
        policy = json.loads(policy_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return LEGACY_DEFAULT_MODEL, "legacy-default"

    if not isinstance(policy, dict):
        return LEGACY_DEFAULT_MODEL, "legacy-default"

    primary = str(policy.get("primary_model", "")).strip()
    allowed_raw = policy.get("allowed_models", [])
    allowed = [str(item).strip() for item in allowed_raw if str(item).strip()] if isinstance(allowed_raw, list) else []
    if primary and primary in allowed:
        return primary, "policy-primary"
    if allowed:
        return allowed[0], "policy-allowed[0]"
    if primary:
        return primary, "policy-primary"
    return LEGACY_DEFAULT_MODEL, "legacy-default"


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
    mode = normalize_notify_on(notify_on)
    results = summary.get("results", [])
    if not isinstance(results, list):
        results = []
    error_items = [item for item in results if isinstance(item, dict) and result_is_error(item)]
    executed = max(0, int(summary.get("tasks_executed", 0) or 0))

    if mode == "error" and not error_items:
        return "NO_REPLY"
    if mode == "activity" and (not error_items) and executed <= 0:
        return "NO_REPLY"

    lines = [
        "# task-executor",
        f"- task: {str(summary.get('trigger_task', '')).strip() or '-'}",
        f"- time: {str(summary.get('started_at', '')).strip() or '-'}",
        f"- run_id: {str(summary.get('run_id', '')).strip() or '-'}",
        f"- executor_model: {str(summary.get('executor_model', '')).strip() or '-'}",
        f"- tasks_selected: {max(0, int(summary.get('tasks_selected', 0) or 0))}",
        f"- tasks_executed: {executed}",
        f"- tasks_skipped: {max(0, int(summary.get('tasks_skipped', 0) or 0))}",
        f"- tasks_failed: {len(error_items)}",
        f"- report_file: {report_path}",
    ]
    if error_items:
        lines.append("- failures:")
        for item in error_items[:8]:
            task_id = str(item.get("task_id", "")).strip() or "-"
            assignee = str(item.get("assignee", "")).strip() or "-"
            reason = (
                str(item.get("reason", "")).strip()
                or str(item.get("report_status", "")).strip()
                or str(item.get("task_status_after", "")).strip()
                or str(item.get("status", "")).strip()
                or "-"
            )
            lines.append(f"  - {task_id} ({assignee}): {reason}")
    return "\n".join(lines)


def select_tasks(enforcer: PolicyEnforcer, only_task_id: str, max_tasks: int) -> list[dict[str, Any]]:
    if str(only_task_id or "").strip():
        return [enforcer.db.get_task(str(only_task_id).strip())]
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
        out.append(enforcer.db.get_task(str(row["task_id"])))
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


def call_agent(openclaw_bin: str, assignee: str, message: str, session_id: str, timeout_sec: int, local_mode: bool) -> tuple[int, str, str]:
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
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    paths = RuntimePaths(
        db=Path(args.db).expanduser(),
        policy_file=Path(args.policy_file).expanduser(),
        routing_file=Path(args.routing_file).expanduser(),
        pricing_file=Path(args.pricing_file).expanduser(),
    )
    model_name, model_source = resolve_executor_model(str(args.model), paths.policy_file)
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
        "executor_model": model_name,
        "executor_model_source": model_source,
        "results": [],
    }

    try:
        tasks = select_tasks(enforcer, str(args.only_task_id), max(1, int(args.max_tasks)))
        summary["tasks_selected"] = len(tasks)

        for task in tasks:
            task_id = str(task.get("task_id", "")).strip()
            assignee = str(task.get("assignee", "")).strip() or "backend-dev"
            stage = default_stage(assignee)
            result: dict[str, Any] = {"task_id": task_id, "assignee": assignee, "stage": stage, "status": "skipped", "reason": ""}

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
            session_id = f"task-{task_id}"

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
                enforcer.pre_stage(ns(task_id=task_id, stage=stage, agent_id=assignee, model=model_name, input_ref=str(report_dir), actor=str(args.actor)))
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
                rc, out, err = call_agent(
                    str(args.openclaw_bin),
                    assignee,
                    prompt,
                    session_id,
                    int(args.timeout_sec),
                    bool(args.local_agent),
                )
            except Exception as exc:
                rc, out, err = 1, "", f"call_agent_exception:{exc}"
            agent_log_path = report_dir / f"{run_id}-{task_id}.agent.log"
            try:
                agent_log_path.write_text(
                    "\n".join(
                        [
                            f"task_id={task_id}",
                            f"assignee={assignee}",
                            f"session_id={session_id}",
                            f"exit_code={rc}",
                            "=== STDOUT ===",
                            str(out or ""),
                            "=== STDERR ===",
                            str(err or ""),
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

            agent_json = parse_json_output(out) or {}
            payloads = agent_json.get("payloads", [])
            reply_text = ""
            if isinstance(payloads, list):
                reply_text = "\n".join(str(x.get("text", "")).strip() for x in payloads if isinstance(x, dict) and str(x.get("text", "")).strip())
            if not reply_text:
                reply_text = str(out or "").strip() or str(err or "").strip()

            contract = normalize_contract(reply_text)
            in_tokens, out_tokens, duration_ms = extract_usage(agent_json)
            if duration_ms <= 0:
                duration_ms = max(0, int((datetime.now(tz=UTC) - started).total_seconds() * 1000))
            if rc != 0:
                contract["status"] = "failed"
                contract["solved"] = False
                contract["failure_count"] = max(1, int(contract.get("failure_count", 0)))

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
                    enforcer.record_token(ns(task_id=task_id, agent_id=assignee, model=model_name, input_tokens=str(in_tokens), output_tokens=str(out_tokens)))
            except Exception:
                pass

            details = {
                "run_id": run_id,
                "session_id": session_id,
                "command_exit_code": rc,
                "stderr_excerpt": str(err or "")[:1200],
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
                        model=model_name,
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
    report_path = report_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["report_file"] = str(report_path)

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(build_chat_output(summary, report_path, str(args.notify_on)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

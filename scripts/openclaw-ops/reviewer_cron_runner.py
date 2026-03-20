#!/usr/bin/env python3
"""Reviewer scheduled scan runner.

Modes:
- hourly_git: git incremental record + branch sync + PR scan (+ optional approved merges).
- daily_incremental: incremental code-quality scan and optional fix command.
- bi_daily_recurring: recurring issue scan with full-scan dedupe.
- weekly_structure: structure audit (coupling, duplication hints, config dispersion, I/O contract).

Output contract:
- Print `NO_REPLY` when no notification is required.
- Otherwise print concise human-readable markdown only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from dataclass_compat import compat_dataclass as dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
DEFAULT_SENDER_PREFIX = "reviewer/reviewer-cron-runner"
ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))
from utf8_runtime import configure_process_utf8_stdio
from task_capability_binding import build_task_constraint_fields  # type: ignore
try:
    from task_center import TaskCenter  # type: ignore
    from io_write_gateway import FileWriteError, write_json_atomic  # type: ignore
except Exception:  # pragma: no cover
    TaskCenter = None
    FileWriteError = RuntimeError  # type: ignore
    write_json_atomic = None  # type: ignore
from chat_output import render_chat_notice, short_location_label

configure_process_utf8_stdio()

CONTEXT_GATE_BLOCK_MODES = {"daily_incremental", "bi_daily_recurring", "weekly_structure"}
SKIP_DIR_NAMES = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "dist", "build", ".next", ".idea", ".vscode"
}
SCANNED_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
REVIEW_SKIP_PREFIXES = (
    ".workflow/experience/",
    ".workflow/sessions/",
    "openclaw-memory/",
)
REVIEW_SKIP_NAME_SET = {"memory.md", "experience_recall.md"}
CONTROLLED_PR_BRANCH_PREFIXES = (
    "auto/evolution-",
    "auto/governance-",
    "auto/optimization-",
    "auto/reviewer-",
)
TECHDEBT_TASK_TYPE = "reviewer_technical_debt"
TECHDEBT_OPEN_STATUSES = {"pending", "running", "failed", "escalated"}
SEVERITY_RANK = {"medium": 1, "high": 2}
FRONTEND_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".vue", ".css", ".scss", ".less", ".sass"}
DATA_FUNC_HINTS = ("process", "transform", "compute", "calculate", "parse", "normalize", "aggregate", "clean")
JS_DATA_FUNC_HINTS = DATA_FUNC_HINTS
COMMON_DUP_NAMES = {"main", "run", "handler", "init", "setup", "test", "render", "create", "update", "delete"}
SECRET_ASSIGN_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|access[_-]?key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
)
PY_SECURITY_LINE_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    ("security.exec_eval", re.compile(r"\b(?:eval|exec)\s*\("), "high", "avoid eval/exec with untrusted input"),
    (
        "security.subprocess_shell_true",
        re.compile(r"subprocess\.(?:run|Popen|call|check_output|check_call)\s*\([^#\n]*\bshell\s*=\s*True"),
        "high",
        "shell=True may lead to command injection",
    ),
    ("security.os_system_call", re.compile(r"\bos\.system\s*\("), "high", "os.system may execute unsafe shell commands"),
    ("security.tls_verify_disabled", re.compile(r"\bverify\s*=\s*False\b"), "medium", "TLS certificate verification disabled"),
    ("security.pickle_deserialize", re.compile(r"\bpickle\.(?:load|loads)\s*\("), "medium", "pickle deserialization may execute code"),
]
JS_SECURITY_LINE_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    ("security.eval", re.compile(r"\beval\s*\("), "high", "avoid eval with untrusted input"),
    ("security.new_function", re.compile(r"\bnew\s+Function\s*\("), "high", "Function constructor may enable code injection"),
    ("security.child_process_exec", re.compile(r"\bchild_process\.(?:exec|execSync)\s*\("), "high", "child_process exec may execute unsafe commands"),
    ("security.dom_innerhtml", re.compile(r"\.innerHTML\s*="), "medium", "innerHTML writes may introduce XSS"),
    (
        "security.tls_verify_disabled",
        re.compile(r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]0['\"]"),
        "high",
        "TLS verification disabled in Node runtime",
    ),
]


@dataclass(slots=True)
class RunResult:
    notify: bool
    output: str
    record: dict[str, Any]


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"silent", "chat"} else default


def humanize_reviewer_reason(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "未提供异常原因"
    prefix_mapping = {
        "policy_enforcer_missing:": "策略执行器缺失",
        "policy_enforcer_exec_failed:": "策略执行器启动失败",
        "policy_enforcer_failed:": "策略执行器执行失败",
        "policy_enforcer_invalid_json_output": "策略执行器返回了无效 JSON",
        "policy_enforcer_return_not_ok": "策略执行器返回非成功状态",
        "git_fetch_failed:": "Git 拉取远端信息失败",
        "git_rev_parse_failed:": "Git HEAD 解析失败",
        "gh_pr_json_parse_failed": "GitHub PR 返回解析失败",
        "close_failed:": "关闭旧任务失败",
        "create_or_reopen_failed:": "创建或重新打开任务失败",
    }
    for prefix, label in prefix_mapping.items():
        if text == prefix.rstrip(":"):
            return label
        if text.startswith(prefix):
            detail = text[len(prefix):].strip()
            return f"{label}（{detail}）" if detail else label
    head, sep, tail = text.partition("=")
    detail = tail.strip() if sep else ""
    mapping = {
        "branches_behind": "分支落后远端",
        "merge_failed": "自动合并失败",
        "high_issue_delta": "新增高风险问题",
        "project_context_gate_blocked": "项目上下文门禁阻塞",
        "fix_command_failed": "自动修复命令执行失败",
        "techdebt_sync_error": "技术债任务同步失败",
        "repos_head_changed": "仓库远端发生变更",
        "dirty_repos": "存在未提交仓库",
        "open_prs": "存在待处理 PR",
        "new_issue": "发现新问题",
        "reopened_issue": "历史问题重新出现",
        "resolved_issue": "已有问题已解决",
        "io_contract_missing": "存在 I/O 契约缺失",
        "recurring_open": "存在重复未闭环问题",
        "techdebt_created": "新增技术债任务",
        "techdebt_reopened": "重新打开技术债任务",
        "techdebt_closed": "关闭技术债任务",
    }
    label = mapping.get(head, text)
    if detail:
        return f"{label}（{detail}）"
    return label


def humanize_reviewer_runtime_error(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    mapping = {
        "task center unavailable": "任务中心暂不可用",
        "database locked": "数据库暂时被占用",
    }
    return mapping.get(raw.lower(), raw)


def build_reviewer_exception_output(
    *,
    mode: str,
    task_id: str,
    run_id: str,
    run_duration_ms: int,
    priority: str,
    risk_level: str,
    normal_log_mode: str,
    risk_reasons: list[str],
    change_reasons: list[str],
    detail_lines: list[str] | None = None,
    manual_action: str = "",
) -> str:
    detail_items = [
        f"审查模式：{mode}",
        f"运行耗时：{max(0, int(run_duration_ms))} 毫秒",
        f"优先级：{priority}",
        f"风险级别：{risk_level}",
        f"日志模式：{normal_log_mode}",
    ]
    if risk_reasons:
        detail_items.append("问题：" + "；".join(humanize_reviewer_reason(item) for item in risk_reasons))
    if change_reasons:
        detail_items.append("变化：" + "；".join(humanize_reviewer_reason(item) for item in change_reasons))
    for line in detail_lines or []:
        text = str(line or "").strip()
        if text:
            detail_items.append(text)
    return render_chat_notice(
        "代码审查巡检异常",
        status="需处理",
        task_id=task_id,
        sender_identity=DEFAULT_SENDER_PREFIX,
        run_time=datetime.now(TZ).isoformat(timespec="seconds"),
        trace_id=run_id,
        summary="检测到需要人工关注的审查异常。",
        details=detail_items,
        next_step=manual_action or "请先查看内部留痕，再决定修复或升级处理。",
    )


def build_reviewer_exception_fallback_output(
    *,
    mode: str,
    task_id: str,
    run_id: str,
    run_duration_ms: int,
    normal_log_mode: str,
    exception_reasons: list[str],
) -> str:
    detail_lines: list[str] = []
    if exception_reasons:
        detail_lines.append("- 详情: " + "；".join(humanize_reviewer_reason(item) for item in exception_reasons[:6]))
    return build_reviewer_exception_output(
        mode=mode,
        task_id=task_id,
        run_id=run_id,
        run_duration_ms=run_duration_ms,
        priority="high",
        risk_level="high",
        normal_log_mode=normal_log_mode,
        risk_reasons=exception_reasons[:6],
        change_reasons=[],
        detail_lines=detail_lines,
        manual_action="请先查看本机 reviewer 运行记录与 policy 日志，再按问题类型处理。",
    )


def explain_context_gate(context_gate: dict[str, Any]) -> str:
    blocked = int(context_gate.get("blocked", 0) or 0)
    created = int(context_gate.get("created", 0) or 0)
    pending = int(context_gate.get("pending", 0) or 0)
    ready = int(context_gate.get("ready", 0) or 0)
    if pending > 0:
        return (
            "已有上下文任务处于 pending/running，说明 project-agent 还没有产出 reviewer 所需的上下文包，"
            "现在继续审查会缺少项目上下文。"
        )
    if created > 0 and ready == 0:
        return "本轮刚创建上下文任务，但上下文包还没生成完成，需要先等待 project-agent 产出结果。"
    if blocked > 0 and ready > 0:
        return "上下文包显示已有 ready 项但门禁仍未放行，通常是任务状态、绑定关系或门禁判定还存在异常。"
    if blocked > 0:
        return "存在被门禁阻塞的仓库，通常表示上下文任务缺失、未完成，或上下文状态异常。"
    return "项目上下文尚未满足 reviewer 执行条件。"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    if write_json_atomic is None:
        raise RuntimeError("save_json_failed:io_write_gateway_not_available")
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:  # type: ignore[misc]
        raise RuntimeError(f"save_json_failed:{getattr(exc, 'code', 'error')}:{path}:{exc}") from exc


def sha1_text(text: str, limit: int = 20) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:limit]


def run_cmd(command: list[str] | str, *, cwd: Path | None = None, timeout: int = 30, shell: bool = False) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=shell,
            check=False,
        )
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def policy_enforcer_path() -> Path:
    custom = str(os.environ.get("POLICY_ENFORCER_PY", "")).strip()
    if custom:
        return Path(custom).expanduser()
    return POLICY_DIR / "policy_enforcer.py"


def task_exists_in_db(db_path: Path, task_id: str) -> bool:
    normalized_id = str(task_id or "").strip()
    if not normalized_id or (not db_path.exists()):
        return False
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 AS ok FROM tasks WHERE task_id = ?", (normalized_id,)).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def ensure_task_binding(db_path: Path, task_id: str, actor: str, source_module: str) -> tuple[str, str]:
    normalized = str(task_id or "").strip()
    if not normalized:
        return "", ""
    if not db_path.exists():
        return "", f"task_db_missing:{db_path}"
    if task_exists_in_db(db_path, normalized):
        return normalized, ""

    actor_name = str(actor or "reviewer-agent").strip() or "reviewer-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "reviewer-agent"
    source_name = str(source_module or "reviewer/reviewer-cron-runner").strip() or "reviewer/reviewer-cron-runner"
    create_args = [
        "create-task",
        "--task-id",
        normalized,
        "--task-type",
        "ops_runtime_cron",
        "--reason",
        f"[CRON_RUNTIME] bind {normalized}",
        "--source",
        source_name,
        "--request-source",
        "ai",
        "--priority",
        "low",
        "--risk-level",
        "low",
        "--pool",
        "jobs",
        "--assignee",
        assignee,
        "--need-human-confirm",
        "false",
        "--human-confirmed",
        "true",
        "--requirement",
        f"Auto register runtime task for {normalized} to bind observability records.",
        "--result-output",
        "Runtime task exists and accepts module/communication/report records.",
        "--acceptance",
        "Task can be used for cron observability binding without manual action.",
        "--observable-outputs",
        "module_logs,module_communications,agent_task_reports,planner_summary",
        "--acceptance-thresholds",
        "At least one runtime observability record is bound to this task.",
        "--scheduled-at",
        now_iso(),
        "--actor",
        actor_name,
    ]
    ok, _payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
    if ok and task_exists_in_db(db_path, normalized):
        return normalized, ""
    return "", (err or f"auto_register_task_failed:{normalized}")


def invoke_policy_enforcer(db_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, dict[str, Any], str]:
    script = policy_enforcer_path()
    if not script.exists():
        return False, {}, f"policy_enforcer_missing:{script}"
    cmd = [sys.executable, str(script), "--db", str(db_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return False, {}, f"policy_enforcer_exec_failed:{exc}"

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    if not isinstance(payload, dict):
        return False, {}, "policy_enforcer_invalid_json_output"
    if not bool(payload.get("ok", False)):
        return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
    return True, payload, ""


def quality_grade_from_score(score: float) -> str:
    value = max(0.0, min(float(score), 100.0))
    if value >= 95:
        return "a+"
    if value >= 90:
        return "a"
    if value >= 80:
        return "b"
    if value >= 70:
        return "c"
    return "d"


def run_git(repo: Path, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    return run_cmd(["git", *args], cwd=repo, timeout=timeout, shell=False)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def repo_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def rel_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve()).replace("\\", "/")


def should_skip_review_path(repo: Path, path: Path) -> bool:
    rel = rel_to(repo, path).strip().replace("\\", "/")
    if not rel:
        return False
    low = rel.lower()
    name_low = Path(low).name
    if name_low in REVIEW_SKIP_NAME_SET:
        return True
    for prefix in REVIEW_SKIP_PREFIXES:
        if low.startswith(prefix):
            return True
    return False


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def discover_git_repos(workspace: Path, max_depth: int = 4, max_repos: int = 80) -> list[Path]:
    if not workspace.exists():
        return []
    repos: list[Path] = []
    seen: set[str] = set()
    ws = workspace.resolve()
    if is_git_repo(ws):
        repos.append(ws)
        seen.add(repo_key(ws))

    root_depth = len(ws.parts)
    for current, dirs, _files in os.walk(ws):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        if ".git" in dirs:
            key = repo_key(current_path)
            if key not in seen:
                repos.append(current_path.resolve())
                seen.add(key)
            dirs[:] = [d for d in dirs if d != ".git"]
        if len(repos) >= max_repos:
            break
    repos.sort(key=lambda p: str(p))
    return repos


def list_changed_files_since(repo: Path, old_head: str, new_head: str) -> list[str]:
    old = str(old_head or "").strip()
    new = str(new_head or "").strip()
    if not old or not new or old == new:
        return []
    rc, _out, _err = run_git(repo, ["merge-base", "--is-ancestor", old, new], timeout=20)
    if rc != 0:
        return []
    rc, out, _err = run_git(repo, ["diff", "--name-only", f"{old}..{new}"], timeout=40)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_branch_sync(repo: Path, max_branches: int = 40) -> list[dict[str, Any]]:
    rc, out, _err = run_git(repo, ["for-each-ref", "--format=%(refname:short)|%(upstream:short)", "refs/heads"], timeout=30)
    if rc != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        branch, upstream = line.split("|", 1)
        branch = branch.strip()
        upstream = upstream.strip()
        if not branch or not upstream:
            continue
        rc2, out2, _err2 = run_git(repo, ["rev-list", "--left-right", "--count", f"{branch}...{upstream}"], timeout=20)
        if rc2 != 0:
            continue
        parts = out2.split()
        ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
        behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        rows.append({"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind})
        if len(rows) >= max_branches:
            break
    return rows


def collect_git_snapshot(repo: Path, *, git_fetch: bool, previous_head: str) -> dict[str, Any]:
    data: dict[str, Any] = {"repo": repo_key(repo), "name": repo.name, "errors": [], "fetch_ok": False}
    if git_fetch:
        rc, _out, err = run_git(repo, ["fetch", "--all", "--prune"], timeout=120)
        data["fetch_ok"] = rc == 0
        if rc != 0:
            data["errors"].append(f"git_fetch_failed:{err or rc}")

    rc, head, err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    if rc != 0 or not head:
        data["errors"].append(f"git_rev_parse_failed:{err or rc}")
        return data
    data["head"] = head
    data["head_changed"] = bool(previous_head and previous_head != head)
    data["changed_files_since_prev"] = list_changed_files_since(repo, previous_head, head)[:200]

    rc, branch, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    data["branch"] = branch if rc == 0 else "UNKNOWN"
    rc, upstream, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=20)
    data["upstream"] = upstream if rc == 0 else ""

    ahead = behind = 0
    if data["upstream"]:
        rc, out, _err = run_git(repo, ["rev-list", "--left-right", "--count", "HEAD...@{u}"], timeout=20)
        if rc == 0:
            parts = out.split()
            ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
            behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    data["ahead"] = ahead
    data["behind"] = behind

    rc, out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    data["dirty_count"] = len([x for x in out.splitlines() if x.strip()]) if rc == 0 else 0
    data["branch_sync"] = collect_branch_sync(repo)
    return data


def current_head(repo: Path) -> str:
    rc, head, _err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    return head.strip() if rc == 0 else ""


def load_project_index_summary(repo: Path) -> dict[str, Any]:
    candidate_files = [
        repo / ".workflow" / "project-index-local" / "project-index.json",
        repo / ".workflow" / "project-index" / "project-index.json",
    ]
    index_file = next((path for path in candidate_files if path.exists()), candidate_files[0])
    if not index_file.exists():
        return {"exists": False, "index_file": str(index_file)}
    payload = load_json(index_file, {})
    if not isinstance(payload, dict):
        return {"exists": True, "valid": False, "index_file": str(index_file)}
    modules = payload.get("modules", [])
    apis = payload.get("apis", [])
    scripts = payload.get("scripts", [])
    return {
        "exists": True,
        "valid": True,
        "index_file": str(index_file),
        "generated_at": str(payload.get("generated_at", "")).strip(),
        "modules_count": len(modules) if isinstance(modules, list) else 0,
        "apis_count": len(apis) if isinstance(apis, list) else 0,
        "scripts_count": len(scripts) if isinstance(scripts, list) else 0,
    }


def query_context_task(tc: Any, change_id: str) -> dict[str, Any]:
    row = tc.conn.execute(
        """
        SELECT task_id, status, updated_at
        FROM tasks
        WHERE source = 'reviewer-cron-runner'
          AND task_type = 'reviewer_project_context_preflight'
          AND change_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (change_id,),
    ).fetchone()
    if row is None:
        return {"exists": False, "task_id": "", "status": ""}
    return {
        "exists": True,
        "task_id": str(row["task_id"] or "").strip(),
        "status": str(row["status"] or "").strip().lower(),
        "updated_at": str(row["updated_at"] or "").strip(),
    }


def ensure_project_context_gate(args: argparse.Namespace, mode: str, repos: list[Path]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": bool(args.project_context_gate),
        "mode": mode,
        "ok": True,
        "blocked": 0,
        "created": 0,
        "pending": 0,
        "ready": 0,
        "items": [],
        "error": "",
    }
    if mode not in CONTEXT_GATE_BLOCK_MODES or (not bool(args.project_context_gate)):
        return result
    if TaskCenter is None:
        result["ok"] = False
        result["blocked"] = len(repos)
        result["error"] = "task_center_unavailable"
        return result

    db = TaskCenter(Path(args.project_context_db).expanduser())
    db.init_schema()
    try:
        for repo in repos:
            key = repo_key(repo)
            head = current_head(repo)
            index_summary = load_project_index_summary(repo)
            change_id = sha1_text(f"reviewer_context|{mode}|{key}|{head}", limit=16)
            state = query_context_task(db, change_id)
            item = {
                "repo": key,
                "head": head,
                "change_id": change_id,
                "index_summary": index_summary,
                "status": str(state.get("status", "")),
                "task_id": str(state.get("task_id", "")),
                "created": False,
            }
            status = str(state.get("status", "")).lower()
            if status == "passed":
                result["ready"] += 1
                result["items"].append(item)
                continue
            if status in {"pending", "running", "failed", "escalated"}:
                result["ok"] = False
                result["blocked"] += 1
                result["pending"] += 1
                result["items"].append(item)
                continue

            requirement = "\n".join(
                [
                    f"审查模式: {mode}",
                    f"目标仓库: {key}",
                    f"当前HEAD: {head or '-'}",
                    "请 project-agent 先输出审查上下文包：",
                    "- 项目简介（目标、关键模块、禁改边界）",
                    "- 本轮审查应重点覆盖的文件/目录",
                    "- 已知风险点与建议验证命令",
                    "- 与项目索引不一致处（如有）",
                ]
            )
            task = db.create_task(
                {
                    "task_id": f"todo-reviewer-context-{datetime.now(TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
                    "pool": "todo",
                    "task_type": "reviewer_project_context_preflight",
                    "reason": "[REVIEWER_CONTEXT_GATE] project context preflight required",
                    "source": "reviewer-cron-runner",
                    "request_source": "ai",
                    "priority": "medium",
                    "risk_level": "high",
                    "assignee": str(args.project_context_assignee or "project-agent").strip() or "project-agent",
                    "status": "pending",
                    "need_human_confirm": False,
                    "human_confirmed": False,
                    "change_id": change_id,
                    "requirement": requirement,
                    "result_output": "输出项目上下文包（简介/索引/重点范围/验证命令）。",
                    "acceptance": "上下文包可直接支撑 reviewer 全量审查。",
                    "observable_outputs": "project overview, target paths, validation commands",
                    "acceptance_thresholds": "包含重点文件范围和至少1条验证命令",
                    "scheduled_at": (datetime.now(TZ) + timedelta(minutes=1)).isoformat(timespec="seconds"),
                    "context_payload": {
                        "mode": mode,
                        "repo": key,
                        "head": head,
                        "index_summary": index_summary,
                        "gate": "reviewer_project_context_preflight",
                    },
                },
                actor="reviewer-cron-runner",
            )
            task_id = str(task.get("task_id", "")).strip()
            item["created"] = True
            item["status"] = "pending"
            item["task_id"] = task_id
            result["ok"] = False
            result["blocked"] += 1
            result["created"] += 1
            result["items"].append(item)
    finally:
        db.close()
    return result


def collect_prs(repo: Path, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "available": False, "prs": []}
    if not has_command("gh"):
        return {"enabled": True, "available": False, "error": "gh_not_found", "prs": []}
    rc, out, err = run_cmd(
        ["gh", "pr", "list", "--limit", "50", "--json", "number,title,isDraft,mergeable,headRefName,baseRefName,updatedAt,url"],
        cwd=repo,
        timeout=40,
        shell=False,
    )
    if rc != 0:
        return {"enabled": True, "available": False, "error": err or f"gh_pr_list_exit_{rc}", "prs": []}
    try:
        rows = json.loads(out)
    except Exception:
        return {"enabled": True, "available": False, "error": "gh_pr_json_parse_failed", "prs": []}
    if not isinstance(rows, list):
        rows = []

    prs = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        prs.append(
            {
                "number": int(item.get("number", 0) or 0),
                "title": str(item.get("title", "")).strip(),
                "draft": bool(item.get("isDraft", False)),
                "mergeable": str(item.get("mergeable", "")).strip().upper(),
                "head": str(item.get("headRefName", "")).strip(),
                "base": str(item.get("baseRefName", "")).strip(),
                "updated_at": str(item.get("updatedAt", "")).strip(),
                "url": str(item.get("url", "")).strip(),
            }
        )
    return {"enabled": True, "available": True, "prs": prs}


def load_merge_approvals(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "approved_prs": [], "approved_branches": []}
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {"exists": True, "approved_prs": [], "approved_branches": []}

    approved_prs: list[dict[str, Any]] = []
    approved_branches: list[dict[str, Any]] = []
    for key in ("approved_prs", "prs", "pr_numbers"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, int):
                approved_prs.append({"repo": "", "number": int(item)})
            elif isinstance(item, str) and item.strip().isdigit():
                approved_prs.append({"repo": "", "number": int(item.strip())})
            elif isinstance(item, dict):
                repo_selector = str(item.get("repo", item.get("repository", ""))).strip()
                number = item.get("number", item.get("pr", 0))
                if str(number).strip().isdigit() and int(str(number).strip()) > 0:
                    approved_prs.append({"repo": repo_selector, "number": int(str(number).strip())})
                    continue
                head_prefix = str(item.get("head_prefix", item.get("headPrefix", ""))).strip()
                if head_prefix:
                    approved_prs.append(
                        {
                            "repo": repo_selector,
                            "head_prefix": head_prefix,
                            "base": str(item.get("base", item.get("base_branch", ""))).strip(),
                        }
                    )

    for key in ("approved_branches", "branches"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                text = item.strip()
                if not text or "->" not in text:
                    continue
                repo_sel = ""
                pair = text
                if ":" in text:
                    left, right = text.split(":", 1)
                    if "->" in right:
                        repo_sel = left.strip()
                        pair = right.strip()
                source, target = [x.strip() for x in pair.split("->", 1)]
                if source and target:
                    approved_branches.append({"repo": repo_sel, "source": source, "target": target})
            elif isinstance(item, dict):
                source = str(item.get("source", item.get("from", ""))).strip()
                target = str(item.get("target", item.get("to", ""))).strip()
                if source and target:
                    approved_branches.append({"repo": str(item.get("repo", item.get("repository", ""))).strip(), "source": source, "target": target})
    return {"exists": True, "approved_prs": approved_prs, "approved_branches": approved_branches}


def repo_matches_selector(repo: Path, selector: str) -> bool:
    needle = str(selector or "").strip().lower().replace("\\", "/")
    if needle in {"", "*", "all"}:
        return True
    path_text = repo_key(repo).lower()
    return path_text.endswith(needle) or repo.name.lower() == needle or f"/{needle}/" in path_text


def is_controlled_pr(pr: dict[str, Any]) -> bool:
    head = str(pr.get("head", "")).strip().lower()
    if not head:
        return False
    return any(head.startswith(prefix) for prefix in CONTROLLED_PR_BRANCH_PREFIXES)


def pr_matches_merge_approval(repo: Path, pr: dict[str, Any], approval: dict[str, Any]) -> bool:
    if not repo_matches_selector(repo, str(approval.get("repo", ""))):
        return False
    number = int(approval.get("number", 0) or 0)
    if number > 0:
        return int(pr.get("number", 0) or 0) == number
    head_prefix = str(approval.get("head_prefix", "")).strip().lower()
    if not head_prefix:
        return False
    head = str(pr.get("head", "")).strip().lower()
    if not head.startswith(head_prefix):
        return False
    base = str(approval.get("base", "")).strip().lower()
    if base and str(pr.get("base", "")).strip().lower() != base:
        return False
    return True


def merge_one_approved_pr(repo: Path, pr: dict[str, Any]) -> dict[str, Any]:
    number = int(pr.get("number", 0) or 0)
    if not is_controlled_pr(pr):
        return {"kind": "pr", "number": number, "ok": False, "reason": "not_controlled_pr"}
    if pr.get("draft"):
        return {"kind": "pr", "number": number, "ok": False, "reason": "draft"}
    if str(pr.get("mergeable", "")).upper() == "CONFLICTING":
        return {"kind": "pr", "number": number, "ok": False, "reason": "merge_conflict"}
    rc, out, err = run_cmd(["gh", "pr", "merge", str(number), "--merge", "--delete-branch"], cwd=repo, timeout=180)
    return {
        "kind": "pr",
        "number": number,
        "ok": rc == 0,
        "reason": "" if rc == 0 else (err or f"exit_{rc}"),
        "stdout": out[:300],
    }


def merge_approved_prs(repo: Path, prs: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not approvals:
        return actions
    if not has_command("gh"):
        actions.append({"kind": "pr", "ok": False, "reason": "gh_not_found"})
        return actions

    by_number = {int(item.get("number", 0)): item for item in prs if int(item.get("number", 0)) > 0}
    merged_numbers: set[int] = set()
    for approval in approvals:
        number = int(approval.get("number", 0) or 0)
        if number > 0:
            if not repo_matches_selector(repo, str(approval.get("repo", ""))):
                continue
            pr = by_number.get(number)
            if not pr:
                actions.append({"kind": "pr", "number": number, "ok": False, "reason": "pr_not_listed"})
                continue
            if number in merged_numbers:
                continue
            actions.append(merge_one_approved_pr(repo, pr))
            merged_numbers.add(number)
            continue

        for pr in prs:
            pr_number = int(pr.get("number", 0) or 0)
            if pr_number <= 0 or pr_number in merged_numbers:
                continue
            if not pr_matches_merge_approval(repo, pr, approval):
                continue
            actions.append(merge_one_approved_pr(repo, pr))
            merged_numbers.add(pr_number)
    return actions


def merge_branch_ff_only(repo: Path, source: str, target: str, *, push_after_merge: bool) -> dict[str, Any]:
    source = source.strip()
    target = target.strip()
    if not source or not target or source == target:
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": "invalid_source_target"}

    rc, out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    if rc == 0 and out.strip():
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": "dirty_worktree"}

    rc, original_branch, err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    if rc != 0 or not original_branch:
        return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "current_branch_unknown"}

    switched = False
    try:
        if original_branch != target:
            rc, _out, err = run_git(repo, ["checkout", target], timeout=40)
            if rc != 0:
                return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "checkout_target_failed"}
            switched = True
        rc, _out, err = run_git(repo, ["merge", "--ff-only", source], timeout=80)
        if rc != 0:
            return {"kind": "branch", "source": source, "target": target, "ok": False, "reason": err or "ff_merge_failed"}

        push_reason = ""
        if push_after_merge:
            rc, _out, err = run_git(repo, ["push"], timeout=120)
            if rc != 0:
                push_reason = err or "push_failed"
        return {"kind": "branch", "source": source, "target": target, "ok": push_reason == "", "reason": push_reason}
    finally:
        if switched:
            run_git(repo, ["checkout", original_branch], timeout=30)


def merge_approved_branches(repo: Path, approvals: list[dict[str, Any]], *, push_after_merge: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in approvals:
        if not repo_matches_selector(repo, str(item.get("repo", ""))):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if source and target:
            actions.append(merge_branch_ff_only(repo, source, target, push_after_merge=push_after_merge))
    return actions


def issue_key(category: str, path: str, symbol: str, detail: str) -> str:
    return sha1_text(f"{category}|{path}|{symbol}|{detail}")


def parse_python_params(text: str) -> list[str]:
    return [x.strip() for x in text.split(",")]


def py_param_has_annotation(token: str) -> bool:
    raw = token.strip()
    if raw in {"", "self", "cls", "*", "/"}:
        return True
    if raw.startswith("**"):
        return True
    if raw.startswith("*"):
        raw = raw[1:].strip()
        if raw in {"", "args"}:
            return True
    return ":" in raw


def has_jsdoc_contract(lines: list[str], line_index: int) -> bool:
    start = max(0, line_index - 6)
    chunk = "\n".join(lines[start:line_index])
    return ("@param" in chunk) and ("@returns" in chunk or "@return" in chunk)


def scan_python_file(path: Path, repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    symbols: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    rel = rel_to(repo_root, path)

    if len(lines) > 900:
        findings.append({"key": issue_key("maintainability.file_too_long", rel, "", f"lines={len(lines)}"), "category": "maintainability.file_too_long", "severity": "medium", "path": rel, "title": f"File too long ({len(lines)} lines): {rel}", "detail": "split into smaller modules"})

    for idx, line in enumerate(lines, start=1):
        if re.search(r"^\s*from\s+\.\.\.\.", line):
            findings.append({"key": issue_key("coupling.deep_relative_import", rel, str(idx), line.strip()), "category": "coupling.deep_relative_import", "severity": "high", "path": rel, "title": f"Deep relative import at {rel}:{idx}", "detail": line.strip()[:180]})
        if "sys.path.append(" in line:
            findings.append({"key": issue_key("coupling.dynamic_path_import", rel, str(idx), line.strip()), "category": "coupling.dynamic_path_import", "severity": "high", "path": rel, "title": f"Dynamic import path at {rel}:{idx}", "detail": line.strip()[:180]})
        if SECRET_ASSIGN_PATTERN.search(line):
            findings.append(
                {
                    "key": issue_key("security.hardcoded_secret", rel, str(idx), line.strip()),
                    "category": "security.hardcoded_secret",
                    "severity": "high",
                    "path": rel,
                    "title": f"Potential hardcoded secret at {rel}:{idx}",
                    "detail": "sensitive key/token/password literal found",
                }
            )
        for category, pattern, severity, detail in PY_SECURITY_LINE_RULES:
            if pattern.search(line):
                findings.append(
                    {
                        "key": issue_key(category, rel, str(idx), line.strip()),
                        "category": category,
                        "severity": severity,
                        "path": rel,
                        "title": f"Security risky pattern at {rel}:{idx} ({category})",
                        "detail": detail,
                    }
                )

    pattern = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\(([^)]*)\)\s*(?:->\s*([^:]+))?:")
    for idx, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if not match:
            continue
        name, params_raw, return_ann = match.groups()
        symbols.append(name)
        if any(h in name.lower() for h in DATA_FUNC_HINTS):
            params = parse_python_params(params_raw)
            all_annotated = all(py_param_has_annotation(p) for p in params)
            has_return = bool(str(return_ann or "").strip())
            if not (all_annotated and has_return):
                findings.append({"key": issue_key("io_contract.missing_signature", rel, name, line.strip()), "category": "io_contract.missing_signature", "severity": "high", "path": rel, "title": f"Missing explicit input/output contract: {name} ({rel}:{idx})", "detail": "add parameter annotations and return annotation"})
    return findings, symbols


def scan_js_ts_file(path: Path, repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    symbols: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    rel = rel_to(repo_root, path)

    import_pattern = re.compile(r"(from\s+['\"](\.\./){3,}[^'\"]+['\"])|(require\(['\"](\.\./){3,}[^'\"]+['\"]\))")
    for idx, line in enumerate(lines, start=1):
        if import_pattern.search(line):
            findings.append({"key": issue_key("coupling.deep_relative_import", rel, str(idx), line.strip()), "category": "coupling.deep_relative_import", "severity": "high", "path": rel, "title": f"Deep relative import at {rel}:{idx}", "detail": line.strip()[:180]})
        if SECRET_ASSIGN_PATTERN.search(line):
            findings.append(
                {
                    "key": issue_key("security.hardcoded_secret", rel, str(idx), line.strip()),
                    "category": "security.hardcoded_secret",
                    "severity": "high",
                    "path": rel,
                    "title": f"Potential hardcoded secret at {rel}:{idx}",
                    "detail": "sensitive key/token/password literal found",
                }
            )
        for category, pattern, severity, detail in JS_SECURITY_LINE_RULES:
            if pattern.search(line):
                findings.append(
                    {
                        "key": issue_key(category, rel, str(idx), line.strip()),
                        "category": category,
                        "severity": severity,
                        "path": rel,
                        "title": f"Security risky pattern at {rel}:{idx} ({category})",
                        "detail": detail,
                    }
                )

    fn_patterns = [
        re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\("),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
    ]
    for idx, line in enumerate(lines):
        matched_name = ""
        for pat in fn_patterns:
            m = pat.match(line)
            if m:
                matched_name = m.group(1)
                break
        if not matched_name:
            continue
        symbols.append(matched_name)
        if any(h in matched_name.lower() for h in JS_DATA_FUNC_HINTS) and not has_jsdoc_contract(lines, idx):
            findings.append({"key": issue_key("io_contract.missing_signature", rel, matched_name, line.strip()), "category": "io_contract.missing_signature", "severity": "high", "path": rel, "title": f"Missing explicit input/output contract: {matched_name} ({rel}:{idx + 1})", "detail": "add JSDoc @param and @returns"})
    return findings, symbols


def iter_code_files(repo: Path, max_files: int = 3000) -> list[Path]:
    files: list[Path] = []
    root_depth = len(repo.parts)
    for current, dirs, names in os.walk(repo):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        if len(current_path.parts) - root_depth > 8:
            dirs[:] = []
            continue
        for name in names:
            path = current_path / name
            if should_skip_review_path(repo, path):
                continue
            if path.suffix.lower() in SCANNED_SUFFIXES:
                files.append(path)
                if len(files) >= max_files:
                    return files
    return files


def file_fp(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def scan_paths(*, mode: str, repo: Path, paths: list[Path], state: dict[str, Any], skip_unchanged: bool) -> tuple[list[dict[str, Any]], dict[str, set[str]], dict[str, int], int]:
    scan_fp = state.setdefault("scan_fingerprints", {})
    mode_fp = scan_fp.setdefault(mode, {})
    if not isinstance(mode_fp, dict):
        mode_fp = {}
        scan_fp[mode] = mode_fp

    findings: list[dict[str, Any]] = []
    function_index: dict[str, set[str]] = {}
    metrics = {"files_scanned": 0, "files_skipped": 0, "config_files": 0}
    io_contract_count = 0

    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        rel = rel_to(repo, path)
        fp = file_fp(path)
        if skip_unchanged and mode_fp.get(rel) == fp:
            metrics["files_skipped"] += 1
            continue
        mode_fp[rel] = fp
        metrics["files_scanned"] += 1

        if "config" in path.name.lower() or path.name.lower().startswith(("settings", "env.")):
            metrics["config_files"] += 1

        suffix = path.suffix.lower()
        if suffix == ".py":
            file_findings, symbols = scan_python_file(path, repo)
        elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
            file_findings, symbols = scan_js_ts_file(path, repo)
        else:
            file_findings, symbols = [], []

        for item in file_findings:
            if item.get("category") == "io_contract.missing_signature":
                io_contract_count += 1
            findings.append(item)

        for name in symbols:
            function_index.setdefault(name.lower(), set()).add(rel)

    duplicate_hits = 0
    for func_name, locations in function_index.items():
        if len(locations) < 2 or func_name in COMMON_DUP_NAMES or len(func_name) <= 3:
            continue
        duplicate_hits += 1
        locs = sorted(locations)
        findings.append({"key": issue_key("duplication.same_function_name", repo.name, func_name, "|".join(locs[:4])), "category": "duplication.same_function_name", "severity": "medium", "path": repo.name, "title": f"Function name repeated across files: {func_name}", "detail": ", ".join(locs[:4])})
        if duplicate_hits >= 20:
            break

    if metrics["config_files"] >= 8:
        findings.append({"key": issue_key("config.dispersion", repo.name, "", f"count={metrics['config_files']}"), "category": "config.dispersion", "severity": "medium", "path": repo.name, "title": f"Config files appear dispersed in repo: count={metrics['config_files']}", "detail": "consider centralized config layout"})

    return findings, function_index, metrics, io_contract_count


def update_issues(state: dict[str, Any], *, findings: list[dict[str, Any]], mode: str, resolve_after_missed_runs: int = 2, keep_resolved_days: int = 30) -> dict[str, int]:
    issues = state.setdefault("issues", {})
    if not isinstance(issues, dict):
        issues = {}
        state["issues"] = issues
    ts = now_iso()
    seen: set[str] = set()
    created = reopened = resolved = created_high = reopened_high = 0

    for item in findings:
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        seen.add(key)
        rec = issues.get(key)
        severity = str(item.get("severity", "medium")).lower()
        if not isinstance(rec, dict):
            issues[key] = {"key": key, "mode": mode, "title": str(item.get("title", "")).strip(), "path": str(item.get("path", "")).strip(), "category": str(item.get("category", "")).strip(), "severity": severity, "status": "open", "first_seen": ts, "last_seen": ts, "resolved_at": "", "occurrences": 1, "missed_runs": 0, "reopened_count": 0}
            created += 1
            if severity == "high":
                created_high += 1
            continue

        if rec.get("status") == "resolved":
            rec["status"] = "open"
            rec["resolved_at"] = ""
            rec["reopened_count"] = int(rec.get("reopened_count", 0)) + 1
            reopened += 1
            if severity == "high":
                reopened_high += 1

        rec["mode"] = mode
        rec["title"] = str(item.get("title", rec.get("title", ""))).strip()
        rec["path"] = str(item.get("path", rec.get("path", ""))).strip()
        rec["category"] = str(item.get("category", rec.get("category", ""))).strip()
        rec["severity"] = "high" if rec.get("severity") == "high" or severity == "high" else "medium"
        rec["last_seen"] = ts
        rec["occurrences"] = int(rec.get("occurrences", 0)) + 1
        rec["missed_runs"] = 0

    for key, rec in list(issues.items()):
        if not isinstance(rec, dict) or str(rec.get("mode", "")).strip() != mode or rec.get("status") != "open" or key in seen:
            continue
        rec["missed_runs"] = int(rec.get("missed_runs", 0)) + 1
        if rec["missed_runs"] >= max(1, int(resolve_after_missed_runs)):
            rec["status"] = "resolved"
            rec["resolved_at"] = ts
            resolved += 1

    if keep_resolved_days > 0:
        cutoff = now() - timedelta(days=max(1, int(keep_resolved_days)))
        for key, rec in list(issues.items()):
            if not isinstance(rec, dict) or rec.get("status") != "resolved":
                continue
            stamp = str(rec.get("resolved_at", "")).strip()
            if not stamp:
                continue
            try:
                resolved_at = datetime.fromisoformat(stamp)
            except Exception:
                continue
            if resolved_at < cutoff:
                issues.pop(key, None)

    open_total = open_high_total = recurring_total = 0
    for rec in issues.values():
        if not isinstance(rec, dict) or rec.get("status") != "open":
            continue
        open_total += 1
        if str(rec.get("severity", "")).lower() == "high":
            open_high_total += 1
        if int(rec.get("occurrences", 0)) >= 3 or int(rec.get("reopened_count", 0)) >= 1:
            recurring_total += 1

    return {
        "new": created,
        "new_high": created_high,
        "reopened": reopened,
        "reopened_high": reopened_high,
        "resolved": resolved,
        "open_total": open_total,
        "open_high_total": open_high_total,
        "recurring_open_total": recurring_total,
    }


def severity_meets_threshold(severity: str, min_severity: str) -> bool:
    sev = str(severity or "medium").strip().lower()
    minimum = str(min_severity or "medium").strip().lower()
    return SEVERITY_RANK.get(sev, 0) >= SEVERITY_RANK.get(minimum, 1)


def infer_techdebt_assignee(path: str, fallback_assignee: str) -> str:
    candidate = str(fallback_assignee or "").strip()
    if candidate:
        return candidate
    normalized = str(path or "").strip().lower().replace("\\", "/")
    suffix = Path(normalized).suffix.lower()
    if suffix in FRONTEND_SUFFIXES or "/frontend/" in normalized or normalized.startswith("src/"):
        return "frontend-dev"
    return "backend-dev"


def list_open_debt_tasks_for_issue(tc: Any, issue_id: str) -> list[dict[str, Any]]:
    rows = tc.conn.execute(
        """
        SELECT task_id, status, assignee, updated_at
        FROM tasks
        WHERE task_type = ?
          AND change_id = ?
          AND status IN ('pending', 'running', 'failed', 'escalated')
        ORDER BY updated_at DESC
        """,
        (TECHDEBT_TASK_TYPE, issue_id),
    ).fetchall()
    return [dict(row) for row in rows]


def query_latest_debt_task(tc: Any, issue_id: str) -> dict[str, Any] | None:
    row = tc.conn.execute(
        """
        SELECT task_id, status, assignee, updated_at, review_status
        FROM tasks
        WHERE task_type = ?
          AND change_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (TECHDEBT_TASK_TYPE, issue_id),
    ).fetchone()
    return dict(row) if row is not None else None


def sync_resolved_techdebt_tasks(*, tc: Any, state: dict[str, Any], mode: str, actor: str) -> dict[str, Any]:
    result = {"closed": 0, "errors": [], "task_ids": []}
    issues = state.get("issues", {})
    if not isinstance(issues, dict):
        return result

    for issue_id, issue in issues.items():
        if not isinstance(issue, dict):
            continue
        if str(issue.get("mode", "")).strip() != mode:
            continue
        if str(issue.get("status", "")).strip().lower() != "resolved":
            continue
        for row in list_open_debt_tasks_for_issue(tc, str(issue_id).strip()):
            task_id = str(row.get("task_id", "")).strip()
            if not task_id:
                continue
            try:
                tc.update_task(
                    task_id,
                    actor=actor,
                    fields={
                        "status": "passed",
                        "review_status": "fix_verified",
                        "review_mode": mode,
                        "reviewed_at": now_iso(),
                    },
                )
                result["closed"] += 1
                result["task_ids"].append(task_id)
            except Exception as exc:
                result["errors"].append(f"close_failed:{task_id}:{exc}")
    return result


def create_or_reopen_techdebt_tasks(
    *,
    args: argparse.Namespace,
    state: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": bool(args.create_techdebt_task),
        "mode": mode,
        "created": 0,
        "reopened": 0,
        "deduped_open": 0,
        "closed": 0,
        "skipped_low_severity": 0,
        "skipped_no_key": 0,
        "errors": [],
        "task_ids": [],
    }
    if not bool(args.create_techdebt_task):
        return result
    if TaskCenter is None:
        result["errors"].append("task_center_unavailable")
        return result

    db_path = Path(str(args.project_context_db or "")).expanduser()
    if not db_path.exists():
        result["errors"].append(f"task_db_missing:{db_path}")
        return result

    max_tasks = max(1, int(args.techdebt_max_tasks_per_run or 1))
    min_severity = str(args.techdebt_min_severity or "medium").strip().lower()
    actor = "reviewer-cron-runner"
    unique_findings: dict[str, dict[str, Any]] = {}
    for item in findings:
        if not isinstance(item, dict):
            continue
        issue_id = str(item.get("key", "")).strip()
        if not issue_id:
            result["skipped_no_key"] += 1
            continue
        # Keep the highest-severity version when the same key appears repeatedly.
        prev = unique_findings.get(issue_id)
        if prev is None:
            unique_findings[issue_id] = item
            continue
        cur_rank = SEVERITY_RANK.get(str(item.get("severity", "medium")).lower(), 1)
        prev_rank = SEVERITY_RANK.get(str(prev.get("severity", "medium")).lower(), 1)
        if cur_rank > prev_rank:
            unique_findings[issue_id] = item

    tc = TaskCenter(db_path)
    tc.init_schema()
    try:
        resolve_sync = sync_resolved_techdebt_tasks(tc=tc, state=state, mode=mode, actor=actor)
        result["closed"] = int(resolve_sync.get("closed", 0) or 0)
        if isinstance(resolve_sync.get("task_ids"), list):
            result["task_ids"].extend(str(x) for x in resolve_sync.get("task_ids", []) if str(x).strip())
        if isinstance(resolve_sync.get("errors"), list):
            result["errors"].extend(str(x) for x in resolve_sync.get("errors", []) if str(x).strip())

        created_or_reopened = 0
        for issue_id, item in unique_findings.items():
            severity = str(item.get("severity", "medium")).strip().lower()
            if not severity_meets_threshold(severity, min_severity):
                result["skipped_low_severity"] += 1
                continue
            if created_or_reopened >= max_tasks:
                break

            open_rows = list_open_debt_tasks_for_issue(tc, issue_id)
            if open_rows:
                result["deduped_open"] += 1
                continue

            latest = query_latest_debt_task(tc, issue_id)
            path = str(item.get("path", "")).strip()
            category = str(item.get("category", "")).strip()
            title = str(item.get("title", "")).strip()
            detail = str(item.get("detail", "")).strip()
            repo = str(item.get("repo", "")).strip()
            repo_head = str(item.get("repo_head", "")).strip()
            assignee = infer_techdebt_assignee(path, str(args.techdebt_assignee or "").strip())
            priority = "high" if severity == "high" else "medium"
            risk_level = "high" if severity == "high" else "low"
            constraint_fields = build_task_constraint_fields(assignee)

            try:
                if latest and str(latest.get("status", "")).strip().lower() in {"passed", "cancelled"}:
                    task_id = str(latest.get("task_id", "")).strip()
                    if task_id:
                        tc.update_task(
                            task_id,
                            actor=actor,
                            fields={
                                "status": "pending",
                                "priority": priority,
                                "risk_level": risk_level,
                                "assignee": assignee,
                                "review_status": "fix_required",
                                "review_mode": mode,
                                "review_head": repo_head,
                                "reviewed_at": now_iso(),
                                "reason": f"[TECHDEBT_REOPEN] {title or category or issue_id}",
                            },
                        )
                        result["reopened"] += 1
                        created_or_reopened += 1
                        result["task_ids"].append(task_id)
                        continue

                requirement_lines = [
                    f"[issue_key:{issue_id}]",
                    f"审查模式: {mode}",
                    f"仓库: {repo or '-'}",
                    f"路径: {path or '-'}",
                    f"类别: {category or '-'}",
                    f"严重度: {severity}",
                    f"问题: {title or '-'}",
                    "",
                    "修复要求:",
                    "- 明确根因并给出最小修复改动",
                    "- 提供可复现的验证命令或测试步骤",
                    "- 避免引入跨模块耦合与边界破坏",
                    f"- 参考线索: {detail or '-'}",
                ]
                created = tc.create_task(
                    {
                        "task_id": f"todo-techdebt-{datetime.now(TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
                        "pool": "todo",
                        "task_type": TECHDEBT_TASK_TYPE,
                        "reason": f"[TECHDEBT] {title or category or issue_id}",
                        "source": "reviewer-cron-runner",
                        "request_source": "ai",
                        "priority": priority,
                        "risk_level": risk_level,
                        "assignee": assignee,
                        **constraint_fields,
                        "status": "pending",
                        "need_human_confirm": False,
                        "human_confirmed": False,
                        "review_status": "fix_required",
                        "review_mode": mode,
                        "review_head": repo_head,
                        "reviewed_at": now_iso(),
                        "owner": "reviewer",
                        "change_id": issue_id,
                        "requirement": "\n".join(requirement_lines),
                        "result_output": "提交修复说明、关键变更点和验证结果。",
                        "acceptance": "问题不再复现，且 reviewer 后续扫描不再命中同 issue_key。",
                        "observable_outputs": "commit diff, verification commands, reviewer evidence",
                        "acceptance_thresholds": "至少1条验证命令通过；issue_key在后续扫描中关闭",
                        "scheduled_at": (datetime.now(TZ) + timedelta(minutes=2)).isoformat(timespec="seconds"),
                        "context_payload": {
                            "issue_key": issue_id,
                            "mode": mode,
                            "run_id": run_id,
                            "repo": repo,
                            "repo_head": repo_head,
                            "path": path,
                            "category": category,
                            "severity": severity,
                            "title": title,
                            "detail": detail,
                            "assignee_recommendation": assignee,
                        },
                    },
                    actor=actor,
                )
                task_id = str(created.get("task_id", "")).strip()
                if task_id:
                    result["task_ids"].append(task_id)
                result["created"] += 1
                created_or_reopened += 1
            except Exception as exc:
                result["errors"].append(f"create_or_reopen_failed:{issue_id}:{exc}")
    finally:
        tc.close()
    return result


def run_hourly_git(args: argparse.Namespace, state: dict[str, Any], normal_log_mode: str) -> RunResult:
    run_started_at = datetime.now(TZ)
    repos = discover_git_repos(Path(args.workspace).expanduser())
    repo_state = state.setdefault("repos", {})
    findings: list[dict[str, Any]] = []
    repo_summaries: list[dict[str, Any]] = []
    total_changed_repos = total_behind_branches = total_dirty = pr_open_total = 0
    merge_actions: list[dict[str, Any]] = []

    approvals = load_merge_approvals(Path(args.merge_approval_file).expanduser()) if args.allow_merge else {"exists": False, "approved_prs": [], "approved_branches": []}

    for repo in repos:
        key = repo_key(repo)
        rec = repo_state.get(key, {}) if isinstance(repo_state.get(key), dict) else {}
        prev_head = str(rec.get("last_hourly_head", "")).strip()
        if bool(args.pr_gate_only):
            rc_head, head_out, _err_head = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
            snap = {
                "repo": key,
                "head": head_out.strip() if rc_head == 0 else "",
                "head_changed": False,
                "dirty_count": 0,
                "branch_sync": [],
                "pr_gate_only": True,
            }
        else:
            snap = collect_git_snapshot(repo, git_fetch=bool(args.git_fetch), previous_head=prev_head)
        repo_summaries.append(snap)
        if snap.get("head_changed"):
            total_changed_repos += 1
        total_dirty += int(snap.get("dirty_count", 0) or 0)

        branch_sync = snap.get("branch_sync", [])
        if (not bool(args.pr_gate_only)) and isinstance(branch_sync, list):
            for item in branch_sync:
                behind = int(item.get("behind", 0) or 0)
                if behind > 0:
                    total_behind_branches += 1
                    findings.append({"key": issue_key("git.branch_behind", key, str(item.get("branch", "")), str(behind)), "category": "git.branch_behind", "severity": "high" if behind >= 10 else "medium", "path": key, "title": f"Branch behind upstream: {item.get('branch')} behind={behind}", "detail": f"upstream={item.get('upstream')}"})

        pr_data = collect_prs(repo, enabled=bool(args.check_pr))
        snap["pr"] = pr_data
        prs = pr_data.get("prs", []) if isinstance(pr_data, dict) else []
        pr_open_total += len(prs) if isinstance(prs, list) else 0

        if args.allow_merge:
            pr_actions = merge_approved_prs(repo, prs if isinstance(prs, list) else [], approvals.get("approved_prs", []))
            branch_actions = merge_approved_branches(repo, approvals.get("approved_branches", []), push_after_merge=bool(args.push_after_merge))
            actions = pr_actions + branch_actions
            if actions:
                merge_actions.extend([{**x, "repo": key} for x in actions])
                for action in actions:
                    if not action.get("ok", False):
                        findings.append({"key": issue_key("merge.failure", key, str(action.get("kind", "")), str(action)), "category": "merge.failure", "severity": "high", "path": key, "title": f"Approved merge failed ({action.get('kind')}): {key}", "detail": str(action.get("reason", ""))[:180]})

        rec["last_hourly_head"] = str(snap.get("head", "")).strip()
        rec["last_hourly_at"] = now_iso()
        repo_state[key] = rec

    issue_stats = update_issues(state, findings=findings, mode="hourly_git")

    risk_reasons: list[str] = []
    change_reasons: list[str] = []
    if (not bool(args.pr_gate_only)) and total_behind_branches > 0:
        risk_reasons.append(f"branches_behind={total_behind_branches}")
    merge_failed = sum(1 for x in merge_actions if not x.get("ok", False))
    if merge_failed > 0:
        risk_reasons.append(f"merge_failed={merge_failed}")
    if issue_stats["new_high"] > 0 or issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"high_issue_delta={issue_stats['new_high'] + issue_stats['reopened_high']}")

    if (not bool(args.pr_gate_only)) and total_changed_repos > 0:
        change_reasons.append(f"repos_head_changed={total_changed_repos}")
    if (not bool(args.pr_gate_only)) and total_dirty > 0:
        change_reasons.append(f"dirty_repos={total_dirty}")
    if pr_open_total > 0 and args.check_pr:
        change_reasons.append(f"open_prs={pr_open_total}")
    if merge_actions:
        ok_merges = sum(1 for x in merge_actions if x.get("ok", False))
        change_reasons.append(f"merge_actions={len(merge_actions)},ok={ok_merges}")

    # Exception-only notifications: only high-risk reasons trigger chat.
    notify = bool(risk_reasons)

    run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
    run_id = uuid.uuid4().hex[:12]
    job_name = str(args.task_id or "").split(":", 1)[-1] if ":" in str(args.task_id or "") else "reviewer_hourly_git"
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    lines = ["NO_REPLY"]
    if notify:
        manual_required = bool(risk_reasons)
        lines = build_reviewer_exception_output(
            mode="hourly_git",
            task_id=str(args.task_id or ""),
            run_id=run_id,
            run_duration_ms=run_duration_ms,
            priority=priority,
            risk_level=risk_level,
            normal_log_mode=normal_log_mode,
            risk_reasons=risk_reasons,
            change_reasons=change_reasons,
            detail_lines=[
                (
                    f"- 仓库统计: 总数={len(repos)}，远端变更={total_changed_repos}，未提交={total_dirty}"
                    if not bool(args.pr_gate_only)
                    else f"- PR Gate 仓库统计: 总数={len(repos)}"
                ),
                (
                    f"- 分支落后数: {total_behind_branches}"
                    if not bool(args.pr_gate_only)
                    else "- 分支落后数: PR gate 模式下不扫描"
                ),
                f"- 打开中的 PR: {pr_open_total}",
                (
                    "- 问题汇总: "
                    f"新增={issue_stats['new']}，重开={issue_stats['reopened']}，"
                    f"已解决={issue_stats['resolved']}，未关闭={issue_stats['open_total']}，"
                    f"高风险未关闭={issue_stats['open_high_total']}"
                ),
                f"- 合并审批: allow_merge={bool(args.allow_merge)}，approval_file={args.merge_approval_file}",
            ],
            manual_action=(
                "coordinator 需确认分支同步和合并风险后，再继续自动执行。"
                if manual_required
                else ""
            ),
        ).splitlines()
    record = {
        "run_id": run_id,
        "sender_identity": f"{DEFAULT_SENDER_PREFIX}:hourly_git",
        "task_id": args.task_id,
        "job_name": job_name,
        "priority": priority,
        "risk_level": risk_level,
        "run_duration_ms": run_duration_ms,
        "mode": "hourly_git",
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": normal_log_mode,
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "issue_stats": issue_stats,
        "repos": repo_summaries,
        "merge_actions": merge_actions,
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_estimate": 0.0,
    }
    return RunResult(notify=notify, output="\n".join(lines), record=record)


def run_quality_scan(
    args: argparse.Namespace,
    state: dict[str, Any],
    normal_log_mode: str,
    *,
    mode: str,
    incremental_from_head: bool,
    full_scan_skip_unchanged: bool,
    run_fix_command: bool,
) -> RunResult:
    run_started_at = datetime.now(TZ)
    run_id = uuid.uuid4().hex[:12]
    repos = discover_git_repos(Path(args.workspace).expanduser())
    context_gate = ensure_project_context_gate(args, mode, repos)
    if not bool(context_gate.get("ok", True)):
        run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
        run_id = uuid.uuid4().hex[:12]
        job_name = (
            str(args.task_id or "").split(":", 1)[-1]
            if ":" in str(args.task_id or "")
            else f"reviewer_{mode}"
        )
        lines = build_reviewer_exception_output(
            mode=mode,
            task_id=str(args.task_id or ""),
            run_id=run_id,
            run_duration_ms=run_duration_ms,
            priority="high",
            risk_level="high",
            normal_log_mode=normal_log_mode,
            risk_reasons=["project_context_gate_blocked"],
            change_reasons=[],
            detail_lines=[
                (
                    "- 上下文门禁: "
                    f"blocked={context_gate.get('blocked', 0)}，created={context_gate.get('created', 0)}，"
                    f"pending={context_gate.get('pending', 0)}，ready={context_gate.get('ready', 0)}"
                ),
                f"- 原因解析: {explain_context_gate(context_gate)}",
            ],
            manual_action="project-agent 需先产出上下文包，reviewer 再执行全量审查。",
        ).splitlines()
        err = str(context_gate.get("error", "")).strip()
        if err:
            lines.append(f"- 详情：{humanize_reviewer_runtime_error(err)}")
        for item in context_gate.get("items", [])[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- 仓库：{short_location_label(str(item.get('repo', '')))} | 状态={item.get('status', '-')}"
                f" | 任务={item.get('task_id', '-')}"
            )
        record = {
            "run_id": run_id,
            "sender_identity": f"{DEFAULT_SENDER_PREFIX}:{mode}",
            "task_id": args.task_id,
            "job_name": job_name,
            "priority": "high",
            "risk_level": "high",
            "run_duration_ms": run_duration_ms,
            "mode": mode,
            "time": now_iso(),
            "notify": True,
            "normal_log_mode": normal_log_mode,
            "risk_reasons": ["project_context_gate_blocked"],
            "change_reasons": [],
            "issue_stats": {
                "new": 0,
                "new_high": 0,
                "reopened": 0,
                "reopened_high": 0,
                "resolved": 0,
                "open_total": 0,
                "open_high_total": 0,
                "recurring_open_total": 0,
            },
            "summary": [],
            "context_gate": context_gate,
            "token_usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_estimate": 0.0,
        }
        return RunResult(notify=True, output="\n".join(lines), record=record)

    repo_state = state.setdefault("repos", {})
    findings: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    total_io_missing = total_files_scanned = total_files_skipped = 0
    fix_result: dict[str, Any] = {}

    for repo in repos:
        key = repo_key(repo)
        rec = repo_state.get(key, {}) if isinstance(repo_state.get(key), dict) else {}
        rc, head, _err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
        if rc != 0 or not head:
            continue

        paths: list[Path] = []
        if incremental_from_head:
            previous = str(rec.get("last_daily_head", "")).strip()
            changed = list_changed_files_since(repo, previous, head)
            if not changed:
                rc2, out2, _err2 = run_git(repo, ["diff", "--name-only", "HEAD~1..HEAD"], timeout=20)
                if rc2 == 0:
                    changed = [line.strip() for line in out2.splitlines() if line.strip()]
            for rel in changed[:400]:
                path = repo / rel
                if path.exists() and path.is_file() and path.suffix.lower() in SCANNED_SUFFIXES:
                    if should_skip_review_path(repo, path):
                        continue
                    paths.append(path)
            rec["last_daily_head"] = head
            rec["last_daily_at"] = now_iso()
            repo_state[key] = rec
        else:
            paths = iter_code_files(repo, max_files=3000)
            rec[f"last_{mode}_at"] = now_iso()
            repo_state[key] = rec

        repo_findings, _function_index, metrics, io_missing = scan_paths(mode=mode, repo=repo, paths=paths, state=state, skip_unchanged=full_scan_skip_unchanged)
        for item in repo_findings:
            if not isinstance(item, dict):
                continue
            item.setdefault("repo", key)
            item.setdefault("repo_head", head)
            findings.append(item)
        total_io_missing += io_missing
        total_files_scanned += int(metrics.get("files_scanned", 0))
        total_files_skipped += int(metrics.get("files_skipped", 0))
        summary.append({"repo": key, "files": len(paths), "scanned": int(metrics.get("files_scanned", 0)), "skipped": int(metrics.get("files_skipped", 0)), "findings": len(repo_findings), "io_missing": io_missing})

    if run_fix_command and args.fix and str(args.fix_command or "").strip():
        rc, out, err = run_cmd(str(args.fix_command), cwd=Path(args.workspace).expanduser(), timeout=1800, shell=True)
        fix_result = {"ran": True, "ok": rc == 0, "exit_code": rc, "stdout": out[-1000:], "stderr": err[-1000:]}
        if rc != 0:
            findings.append({"key": issue_key("fix_command.failed", mode, "", str(rc)), "category": "fix_command.failed", "severity": "high", "path": str(Path(args.workspace).expanduser()), "title": f"Fix command failed in mode={mode}", "detail": (err or out or f"exit_code={rc}")[:180]})

    issue_stats = update_issues(state, findings=findings, mode=mode)
    techdebt_result = create_or_reopen_techdebt_tasks(
        args=args,
        state=state,
        mode=mode,
        findings=findings,
        run_id=run_id,
    )

    risk_reasons: list[str] = []
    change_reasons: list[str] = []
    if issue_stats["new_high"] > 0 or issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"high_issue_delta={issue_stats['new_high'] + issue_stats['reopened_high']}")
    if fix_result.get("ran") and not fix_result.get("ok", True):
        risk_reasons.append("fix_command_failed")
    if issue_stats["new"] > 0:
        change_reasons.append(f"new_issue={issue_stats['new']}")
    if issue_stats["reopened"] > 0:
        change_reasons.append(f"reopened_issue={issue_stats['reopened']}")
    if issue_stats["resolved"] > 0:
        change_reasons.append(f"resolved_issue={issue_stats['resolved']}")
    if total_io_missing > 0:
        change_reasons.append(f"io_contract_missing={total_io_missing}")
    if mode == "bi_daily_recurring" and issue_stats["recurring_open_total"] > 0:
        change_reasons.append(f"recurring_open={issue_stats['recurring_open_total']}")
    if int(techdebt_result.get("created", 0) or 0) > 0:
        change_reasons.append(f"techdebt_created={techdebt_result['created']}")
    if int(techdebt_result.get("reopened", 0) or 0) > 0:
        change_reasons.append(f"techdebt_reopened={techdebt_result['reopened']}")
    if int(techdebt_result.get("closed", 0) or 0) > 0:
        change_reasons.append(f"techdebt_closed={techdebt_result['closed']}")
    techdebt_errors = techdebt_result.get("errors", [])
    if isinstance(techdebt_errors, list) and techdebt_errors:
        risk_reasons.append(f"techdebt_sync_error={len(techdebt_errors)}")

    # Exception-only notifications: only high-risk reasons trigger chat.
    notify = bool(risk_reasons)

    run_duration_ms = max(0, int((datetime.now(TZ) - run_started_at).total_seconds() * 1000))
    job_name = str(args.task_id or "").split(":", 1)[-1] if ":" in str(args.task_id or "") else f"reviewer_{mode}"
    risk_level = "high" if risk_reasons else "low"
    priority = "high" if risk_reasons else ("medium" if change_reasons else "low")
    lines = ["NO_REPLY"]
    if notify:
        manual_required = bool(risk_reasons)
        detail_lines = [
            f"- 仓库数: {len(repos)}",
            f"- 文件统计: 扫描={total_files_scanned}，跳过={total_files_skipped}",
            (
                "- 问题汇总: "
                f"新增={issue_stats['new']}，重开={issue_stats['reopened']}，"
                f"已解决={issue_stats['resolved']}，未关闭={issue_stats['open_total']}，"
                f"高风险未关闭={issue_stats['open_high_total']}，重复未关闭={issue_stats['recurring_open_total']}"
            ),
            f"- I/O 契约缺失: {total_io_missing}",
            (
                "- 技术债同步: "
                f"created={techdebt_result.get('created', 0)}，reopened={techdebt_result.get('reopened', 0)}，"
                f"closed={techdebt_result.get('closed', 0)}，deduped_open={techdebt_result.get('deduped_open', 0)}"
            ),
        ]
        if fix_result.get("ran"):
            detail_lines.append(
                f"- 修复命令: ok={fix_result.get('ok')}，exit_code={fix_result.get('exit_code')}"
            )
        lines = build_reviewer_exception_output(
            mode=mode,
            task_id=str(args.task_id or ""),
            run_id=run_id,
            run_duration_ms=run_duration_ms,
            priority=priority,
            risk_level=risk_level,
            normal_log_mode=normal_log_mode,
            risk_reasons=risk_reasons,
            change_reasons=change_reasons,
            detail_lines=detail_lines,
            manual_action=(
                "coordinator 需确认高风险代码质量问题后，再下发修复。"
                if manual_required
                else ""
            ),
        ).splitlines()

    record = {
        "run_id": run_id,
        "sender_identity": f"{DEFAULT_SENDER_PREFIX}:{mode}",
        "task_id": args.task_id,
        "job_name": job_name,
        "priority": priority,
        "risk_level": risk_level,
        "run_duration_ms": run_duration_ms,
        "mode": mode,
        "time": now_iso(),
        "notify": notify,
        "normal_log_mode": normal_log_mode,
        "risk_reasons": risk_reasons,
        "change_reasons": change_reasons,
        "issue_stats": issue_stats,
        "summary": summary[:80],
        "context_gate": context_gate,
        "fix_result": fix_result,
        "techdebt": techdebt_result,
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_estimate": 0.0,
    }
    return RunResult(notify=notify, output="\n".join(lines), record=record)


def emit_policy_observability(args: argparse.Namespace, result: RunResult, run_file: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    db_path = Path(str(args.project_context_db or "")).expanduser()
    if not db_path.exists():
        return policy_observability, planner_summary_snapshot

    policy_observability["enabled"] = True
    policy_observability["db"] = str(db_path)
    bound_task_id = ""
    raw_task_id = str(args.task_id or "").strip()
    if raw_task_id:
        bound_task_id, bind_err = ensure_task_binding(
            db_path,
            raw_task_id,
            "reviewer-agent",
            "reviewer/reviewer-cron-runner",
        )
        if bound_task_id:
            policy_observability["task_bound"] = True
        elif bind_err:
            policy_observability["errors"].append(bind_err)

    mode = str(result.record.get("mode", str(args.mode))).strip() or str(args.mode)
    risk_reasons = result.record.get("risk_reasons", [])
    if not isinstance(risk_reasons, list):
        risk_reasons = [str(risk_reasons)]
    run_duration_ms = int(result.record.get("run_duration_ms", 0) or 0)

    module_args = [
        "log-module",
        "--module-name",
        "reviewer/reviewer-cron-runner",
        "--phase",
        mode,
        "--level",
        ("error" if risk_reasons else "info"),
        "--status",
        ("failed" if risk_reasons else "passed"),
        "--message",
        (
            "reviewer cron run finished: "
            + f"mode={mode} notify={bool(result.notify)} risk_count={len(risk_reasons)}"
        ),
        "--duration-ms",
        str(run_duration_ms),
        "--details-json",
        json.dumps(
            {
                "mode": mode,
                "notify": bool(result.notify),
                "risk_reasons": risk_reasons[:20],
                "change_reasons": result.record.get("change_reasons", []),
            },
            ensure_ascii=False,
        ),
        "--actor",
        "reviewer",
    ]
    if bound_task_id:
        module_args.extend(["--task-id", bound_task_id])
    ok_module, _payload_module, err_module = invoke_policy_enforcer(db_path, module_args, timeout=30)
    policy_observability["log_module_ok"] = ok_module
    if not ok_module and err_module:
        policy_observability["errors"].append(err_module)

    comm_args = [
        "log-communication",
        "--from-module",
        "reviewer/reviewer-cron-runner",
        "--to-module",
        "coordinator",
        "--protocol",
        "policy-enforcer",
        "--message-type",
        "review_scan_result",
        "--status",
        ("failed" if risk_reasons else "acked"),
        "--latency-ms",
        str(run_duration_ms),
        "--correlation-id",
        str(result.record.get("run_id", "")),
        "--payload-ref",
        str(run_file),
        "--details-json",
        json.dumps(
            {
                "mode": mode,
                "risk_reasons": risk_reasons[:20],
                "issue_stats": result.record.get("issue_stats", {}),
            },
            ensure_ascii=False,
        ),
        "--actor",
        "reviewer",
    ]
    if bound_task_id:
        comm_args.extend(["--task-id", bound_task_id])
    ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_path, comm_args, timeout=30)
    policy_observability["log_communication_ok"] = ok_comm
    if not ok_comm and err_comm:
        policy_observability["errors"].append(err_comm)

    # Reviewer observability must never mutate project-agent context gate tasks.
    # Those tasks stay pending until project-agent actually executes them.
    report_task_ids: list[str] = [bound_task_id] if bound_task_id else []

    report_count = 0
    for task_id in report_task_ids:
        success = len(risk_reasons) == 0
        quality_score = 92.0 if success else 58.0
        report_args = [
            "report-agent-result",
            "--task-id",
            task_id,
            "--agent-id",
            "reviewer",
            "--planner-id",
            "coordinator",
            "--status",
            ("passed" if success else "partial"),
            "--solved",
            ("true" if success else "false"),
            "--resolved-issues",
            f"reviewer_{mode}_scan_completed",
            "--resolution-summary",
            (
                f"reviewer {mode} scan completed without blocking risks"
                if success
                else f"reviewer {mode} scan found blocking risks"
            ),
            "--resolution-steps",
            "discover_repos,scan,issue_delta,emit_record",
            "--failed-items",
            ",".join(str(x) for x in risk_reasons[:20]),
            "--failure-count",
            str(len(risk_reasons)),
            "--duration-ms",
            str(run_duration_ms),
            "--input-tokens",
            "0",
            "--output-tokens",
            "0",
            "--cost-estimate",
            "0",
            "--quality-score",
            str(quality_score),
            "--quality-grade",
            quality_grade_from_score(quality_score),
            "--notify-chat",
            ("true" if risk_reasons else "false"),
            "--details-json",
            json.dumps(
                {
                    "run_id": result.record.get("run_id"),
                    "mode": mode,
                    "risk_reasons": risk_reasons[:20],
                },
                ensure_ascii=False,
            ),
            "--actor",
            "reviewer",
        ]
        ok_report, _payload_report, err_report = invoke_policy_enforcer(db_path, report_args, timeout=35)
        if ok_report:
            report_count += 1
        elif err_report:
            policy_observability["errors"].append(err_report)
    policy_observability["report_agent_result_count"] = report_count

    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
    ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
        db_path,
        ["planner-summary", "--planner-id", "coordinator", "--since", since_24h, "--limit", "60"],
        timeout=30,
    )
    policy_observability["planner_summary_ok"] = ok_summary
    if ok_summary and isinstance(payload_summary, dict):
        summary = payload_summary.get("summary")
        if isinstance(summary, dict):
            planner_summary_snapshot = {
                "planner_id": summary.get("planner_id"),
                "report_count": summary.get("report_count", 0),
                "task_count": summary.get("task_count", 0),
                "resolved_task_count": summary.get("resolved_task_count", 0),
                "failed_task_count": summary.get("failed_task_count", 0),
                "solved_ratio_pct": summary.get("solved_ratio_pct", 0.0),
                "total_tokens": summary.get("total_tokens", 0),
                "total_cost_estimate": summary.get("total_cost_estimate", 0.0),
            }
    if (not ok_summary) and err_summary:
        policy_observability["errors"].append(err_summary)
    return policy_observability, planner_summary_snapshot


def default_state() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-03",
        "updated_at": "",
        "runs": {"hourly_git": 0, "daily_incremental": 0, "bi_daily_recurring": 0, "weekly_structure": 0},
        "repos": {},
        "issues": {},
        "scan_fingerprints": {},
        "last_run_record": "",
    }


def run_mode(args: argparse.Namespace, state: dict[str, Any], normal_log_mode: str) -> RunResult:
    state.setdefault("runs", {})
    state["runs"][args.mode] = int(state["runs"].get(args.mode, 0) or 0) + 1
    if args.mode == "hourly_git":
        return run_hourly_git(args, state, normal_log_mode)
    if args.mode == "daily_incremental":
        return run_quality_scan(args, state, normal_log_mode, mode="daily_incremental", incremental_from_head=True, full_scan_skip_unchanged=False, run_fix_command=True)
    if args.mode == "bi_daily_recurring":
        return run_quality_scan(args, state, normal_log_mode, mode="bi_daily_recurring", incremental_from_head=False, full_scan_skip_unchanged=True, run_fix_command=False)
    return run_quality_scan(args, state, normal_log_mode, mode="weekly_structure", incremental_from_head=False, full_scan_skip_unchanged=False, run_fix_command=False)


def build_parser() -> argparse.ArgumentParser:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Reviewer scheduled scan runner")
    parser.add_argument("--mode", choices=["hourly_git", "daily_incremental", "bi_daily_recurring", "weekly_structure"], default="hourly_git")
    parser.add_argument("--workspace", default=str(home / ".openclaw/workspace"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/reviewer-scan-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/reviewer-scan-runs"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--emit-json", action="store_true")

    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--fix-command", default="")

    parser.add_argument("--git-fetch", action="store_true")
    parser.add_argument("--check-pr", action="store_true")
    parser.add_argument("--allow-merge", action="store_true")
    parser.add_argument("--push-after-merge", action="store_true")
    parser.add_argument("--pr-gate-only", action="store_true")
    parser.add_argument("--merge-approval-file", default=str(home / ".openclaw/ops/reviewer-merge-approval.json"), help="json file with approved_prs/approved_branches")
    parser.add_argument("--project-context-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project-context-db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--project-context-assignee", default="project-agent")
    parser.add_argument("--create-techdebt-task", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--techdebt-min-severity", choices=["high", "medium"], default="medium")
    parser.add_argument("--techdebt-max-tasks-per-run", type=int, default=8)
    parser.add_argument("--techdebt-assignee", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    history_dir = Path(args.history_dir).expanduser()
    history_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state_file).expanduser()
    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    result = run_mode(args, state, normal_log_mode)

    stamp = now().strftime("%Y%m%d_%H%M%S")
    run_id = result.record.get("run_id", uuid.uuid4().hex[:8])
    run_file = history_dir / f"{stamp}_{args.mode}_{run_id}.json"
    policy_observability, planner_summary_snapshot = emit_policy_observability(args, result, run_file)
    result.record["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        result.record["planner_summary"] = planner_summary_snapshot

    exception_reasons: list[str] = []
    risk_reasons = result.record.get("risk_reasons", [])
    if isinstance(risk_reasons, list):
        exception_reasons.extend(str(x) for x in risk_reasons if str(x).strip())
    elif str(risk_reasons).strip():
        exception_reasons.append(str(risk_reasons).strip())
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    result.record["exception_reasons"] = exception_reasons
    result.notify = bool(exception_reasons)
    result.record["notify"] = bool(result.notify)

    if result.notify:
        if str(result.output or "").strip() in {"", "NO_REPLY"}:
            result.output = build_reviewer_exception_fallback_output(
                mode=args.mode,
                task_id=args.task_id or "-",
                run_id=run_id,
                run_duration_ms=int(result.record.get("run_duration_ms", 0) or 0),
                normal_log_mode=normal_log_mode,
                exception_reasons=exception_reasons,
            )

    save_json(run_file, result.record)
    state["updated_at"] = now_iso()
    state["last_run_record"] = str(run_file)
    save_json(state_path, state)

    if args.emit_json:
        print(json.dumps({"notify": result.notify, "output": result.output, "record": str(run_file)}, ensure_ascii=False))
        return 0

    if result.notify:
        print(result.output)
    else:
        print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Governance evolution runner.

Loop:
1) Read incremental changes from the workflow repository.
2) Package optimization/review tasks into task-center.
3) Optionally auto-push and open/update PR when branch has commits ahead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from task_center import TaskCenter  # type: ignore
from task_capability_binding import build_task_constraint_fields  # type: ignore
from io_write_gateway import FileWriteError, write_json_atomic  # type: ignore
from chat_output import build_trace_id, render_chat_notice, short_location_label

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
TASK_CLARITY_MODES = {"auto", "clear", "ambiguous"}
GIT_UPDATE_STRATEGIES = {"fetch", "pull-ff-only"}
DEFAULT_SENDER_IDENTITY = "optimization-agent/governance-evolution"
DEFAULT_WATCH_PREFIXES = [
    "scripts/openclaw-ops/",
    "hooks/",
    "openclaw/",
    "setup.py",
]
DEFAULT_EXCLUDE_PREFIXES = [
    "openclaw-memory/",
    ".workflow/experience/",
    ".workflow/sessions/",
    "memory/",
]
DEFAULT_EXCLUDE_FILENAMES = {"memory.md", "experience_recall.md"}


def normalize_git_update_strategy(value: str, default: str = "fetch") -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in GIT_UPDATE_STRATEGIES else default


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def compact_text(value: Any, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_startup_failure_output(
    *,
    sender_identity: str,
    task_id: str,
    error: str,
    detail: str = "",
) -> str:
    return render_chat_notice(
        "治理巡检启动异常",
        status="需处理",
        task_id=task_id,
        sender_identity=sender_identity,
        run_time=now_iso(),
        summary="治理巡检在启动阶段失败，详细原因已写入内部留痕。",
        details=[f"启动摘要：{compact_text(error, 120)}"] if str(error or "").strip() else None,
        next_step="请按留痕记录检查启动参数、环境变量和运行时依赖。",
    )


def print_startup_failure(
    *,
    emit_json: bool,
    sender_identity: str,
    task_id: str,
    error: str,
    detail: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    output = build_startup_failure_output(
        sender_identity=sender_identity,
        task_id=task_id,
        error=error,
        detail=detail,
    )
    if emit_json:
        payload: dict[str, Any] = {"ok": False, "notify": True, "output": output, "error": str(error)}
        if str(detail or "").strip():
            payload["detail"] = str(detail)
        if isinstance(extra, dict):
            payload.update(extra)
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(output)


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


def run_cmd(
    command: list[str] | str,
    *,
    cwd: Path | None = None,
    timeout: int = 40,
    shell: bool = False,
) -> tuple[int, str, str]:
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
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)


def run_git(repo: Path, args: list[str], timeout: int = 40) -> tuple[int, str, str]:
    return run_cmd(["git", *args], cwd=repo, timeout=timeout, shell=False)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


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

    actor_name = str(actor or "governance-evolution-agent").strip() or "governance-evolution-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "optimization-agent"
    source_name = str(source_module or "optimization-agent/governance-evolution").strip() or "optimization-agent/governance-evolution"
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


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-03",
        "runs": 0,
        "updated_at": "",
        "last_scan_at": "",
        "last_scan_head": "",
        "last_report_file": "",
        "fingerprints": {},
        "last_pr_url": "",
        "last_pr_number": 0,
    }


def normalize_rel(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("/")


def infer_openclaw_home_from_config(config_path: Path) -> Path:
    cfg = config_path.expanduser().resolve()
    if cfg.name.lower() != "openclaw.json":
        return cfg.parent
    if cfg.parent.name.lower() == "openclaw":
        return cfg.parent.parent
    return cfg.parent


def load_project_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("projects", [])
    else:
        return []
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def resolve_repo_from_inputs(
    *,
    repo_path_arg: str,
    openclaw_config: Path,
    registry_path_arg: str,
    repo_id: str,
    repo_name: str,
) -> tuple[Path | None, dict[str, Any]]:
    detail: dict[str, Any] = {
        "source": "",
        "openclaw_config": str(openclaw_config),
        "project_registry": "",
        "repo_id": str(repo_id or "").strip(),
        "repo_name": str(repo_name or "").strip(),
        "matches": [],
        "error": "",
    }
    repo_path = Path(str(repo_path_arg or "").strip()).expanduser() if str(repo_path_arg or "").strip() else None
    if repo_path is not None:
        detail["source"] = "cli_repo_path"
        detail["resolved_repo_path"] = str(repo_path)
        return repo_path, detail

    registry_path = Path(str(registry_path_arg or "").strip()).expanduser() if str(registry_path_arg or "").strip() else None
    if registry_path is None:
        openclaw_home = infer_openclaw_home_from_config(openclaw_config)
        registry_path = openclaw_home / "ops" / "task-center" / "project-registry.json"
    detail["project_registry"] = str(registry_path)

    projects = load_project_registry(registry_path)
    if not projects:
        detail["error"] = f"project registry empty or missing: {registry_path}"
        return None, detail

    candidates: list[dict[str, Any]] = []
    wanted_id = str(repo_id or "").strip().lower()
    wanted_name = str(repo_name or "").strip().lower()
    for item in projects:
        path_raw = str(item.get("path", "")).strip()
        if not path_raw:
            continue
        item_id = str(item.get("id", "")).strip().lower()
        item_name = str(item.get("name", "")).strip().lower()
        if wanted_id and wanted_id != item_id:
            continue
        if wanted_name and wanted_name not in {item_name, item_id} and wanted_name not in item_name:
            continue
        candidates.append(item)

    if not wanted_id and not wanted_name:
        candidates = projects

    for x in candidates:
        detail["matches"].append(
            {
                "id": str(x.get("id", "")).strip(),
                "name": str(x.get("name", "")).strip(),
                "path": str(x.get("path", "")).strip(),
            }
        )

    if len(candidates) == 1:
        selected = Path(str(candidates[0].get("path", "")).strip()).expanduser()
        detail["source"] = "project_registry"
        detail["resolved_repo_path"] = str(selected)
        return selected, detail

    if len(candidates) <= 0:
        detail["error"] = "no project matched in project registry"
        return None, detail

    detail["error"] = "multiple projects matched in project registry; pass --repo-path or --repo-id"
    return None, detail


def git_ahead_behind(repo: Path) -> tuple[int, int, str]:
    rc, upstream, _err = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=20)
    upstream_name = upstream.strip() if rc == 0 else ""
    if not upstream_name:
        return 0, 0, ""
    rc2, out2, _err2 = run_git(repo, ["rev-list", "--left-right", "--count", "HEAD...@{u}"], timeout=20)
    if rc2 != 0:
        return 0, 0, upstream_name
    parts = out2.split()
    ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
    behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    return ahead, behind, upstream_name


def update_local_git(
    repo: Path,
    *,
    enabled: bool,
    strategy: str,
    fetch_timeout: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": bool(enabled),
        "strategy": strategy,
        "ok": True,
        "fetch_ok": False,
        "pull_attempted": False,
        "pull_ok": False,
        "skipped_reason": "",
        "before_head": "",
        "after_head": "",
        "head_changed": False,
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "upstream": "",
    }
    rc, before_head, err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    if rc != 0 or not before_head:
        result["ok"] = False
        result["skipped_reason"] = f"rev_parse_failed:{err or rc}"
        return result
    result["before_head"] = before_head.strip()

    rc, dirty_out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    result["dirty"] = bool(dirty_out.strip()) if rc == 0 else True

    if not enabled:
        result["skipped_reason"] = "disabled"
    else:
        rc, _out, err = run_git(repo, ["fetch", "--all", "--prune"], timeout=max(30, int(fetch_timeout)))
        result["fetch_ok"] = rc == 0
        if rc != 0:
            result["ok"] = False
            result["skipped_reason"] = f"fetch_failed:{err or rc}"
        elif strategy == "pull-ff-only":
            ahead, behind, upstream = git_ahead_behind(repo)
            result["ahead"] = ahead
            result["behind"] = behind
            result["upstream"] = upstream
            if not upstream:
                result["skipped_reason"] = "no_upstream"
            elif result["dirty"]:
                result["skipped_reason"] = "worktree_dirty"
            elif behind <= 0:
                result["skipped_reason"] = "already_up_to_date"
            else:
                result["pull_attempted"] = True
                rc2, _out2, err2 = run_git(repo, ["pull", "--ff-only"], timeout=max(40, int(fetch_timeout)))
                result["pull_ok"] = rc2 == 0
                if rc2 != 0:
                    result["ok"] = False
                    result["skipped_reason"] = f"pull_ff_only_failed:{err2 or rc2}"
        else:
            result["skipped_reason"] = "fetch_only"

    rc, after_head, err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    if rc == 0 and after_head:
        result["after_head"] = after_head.strip()
        result["head_changed"] = result["after_head"] != result["before_head"]
    else:
        result["ok"] = False
        result["skipped_reason"] = result.get("skipped_reason") or f"rev_parse_after_failed:{err or rc}"

    ahead, behind, upstream = git_ahead_behind(repo)
    result["ahead"] = ahead
    result["behind"] = behind
    result["upstream"] = upstream
    return result


def summarize_change_stats(changes: list[dict[str, str]]) -> dict[str, int]:
    stats = {"added": 0, "modified": 0, "deleted": 0, "renamed": 0, "other": 0}
    for item in changes:
        status = str(item.get("status", "")).strip().upper()[:1]
        if status == "A":
            stats["added"] += 1
        elif status == "D":
            stats["deleted"] += 1
        elif status == "R":
            stats["renamed"] += 1
        elif status in {"M", "C", "T", "U"}:
            stats["modified"] += 1
        else:
            stats["other"] += 1
    return stats


def should_include_file(
    rel: str,
    watch_prefixes: list[str],
    exclude_prefixes: list[str],
    exclude_filenames: set[str],
) -> bool:
    rel_norm = normalize_rel(rel)
    if not rel_norm:
        return False
    low = rel_norm.lower()
    if Path(low).name in exclude_filenames:
        return False
    for prefix in exclude_prefixes:
        if low.startswith(prefix.lower()):
            return False
    for prefix in watch_prefixes:
        if low.startswith(prefix.lower()):
            return True
    return False


def parse_name_status_line(line: str) -> dict[str, str] | None:
    text = str(line or "").strip()
    if not text:
        return None
    parts = text.split("\t")
    if len(parts) < 2:
        return None
    status_raw = parts[0].strip()
    status = status_raw[:1].upper() if status_raw else "M"
    path = parts[-1].strip()
    if not path:
        return None
    return {"status": status, "path": normalize_rel(path)}


def collect_incremental_changes(
    repo: Path,
    *,
    mode: str,
    last_head: str,
    max_files: int,
    force: bool,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    details: dict[str, Any] = {"mode": mode, "diff_base": "", "head": "", "fallback": ""}
    rc, head, err = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
    if rc != 0 or not head:
        raise RuntimeError(f"git rev-parse HEAD failed: {err or rc}")
    details["head"] = head

    changes: list[dict[str, str]] = []
    if mode == "full":
        rc, out, err = run_git(repo, ["ls-files"], timeout=40)
        if rc != 0:
            raise RuntimeError(f"git ls-files failed: {err or rc}")
        for line in out.splitlines():
            path = normalize_rel(line)
            if path:
                changes.append({"status": "M", "path": path})
                if len(changes) >= max(1, int(max_files)):
                    break
        details["diff_base"] = "full"
        return changes, details

    use_last = bool(last_head) and (not force)
    if use_last:
        rc, _out, _err = run_git(repo, ["merge-base", "--is-ancestor", str(last_head), head], timeout=20)
        use_last = rc == 0

    if use_last:
        base = str(last_head).strip()
        details["diff_base"] = base
        rc, out, err = run_git(repo, ["diff", "--name-status", f"{base}..{head}"], timeout=60)
        if rc == 0:
            for line in out.splitlines():
                item = parse_name_status_line(line)
                if item is None:
                    continue
                changes.append(item)
                if len(changes) >= max(1, int(max_files)):
                    break
            if changes:
                return changes, details
        details["fallback"] = "head_minus_1"

    rc, out, err = run_git(repo, ["diff", "--name-status", "HEAD~1..HEAD"], timeout=60)
    if rc == 0:
        for line in out.splitlines():
            item = parse_name_status_line(line)
            if item is None:
                continue
            changes.append(item)
            if len(changes) >= max(1, int(max_files)):
                break
        if changes:
            if not details.get("diff_base"):
                details["diff_base"] = "HEAD~1"
            return changes, details

    details["fallback"] = "show_head"
    rc, out, err = run_git(repo, ["show", "--name-status", "--pretty=format:", "HEAD"], timeout=60)
    if rc == 0:
        for line in out.splitlines():
            item = parse_name_status_line(line)
            if item is None:
                continue
            changes.append(item)
            if len(changes) >= max(1, int(max_files)):
                break
    if not details.get("diff_base"):
        details["diff_base"] = "HEAD"
    return changes, details


def to_fingerprint(items: list[dict[str, str]], head: str) -> str:
    raw = {"head": str(head or ""), "items": items}
    digest = hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def collect_open_fingerprints(tc: TaskCenter) -> set[str]:
    rows = tc.conn.execute(
        """
        SELECT requirement
        FROM tasks
        WHERE source = 'governance-evolution-agent'
          AND pool = 'todo'
          AND task_type IN ('governance_evolution_optimize', 'governance_evolution_review')
          AND status IN ('pending', 'running', 'failed')
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        text = str(row["requirement"] or "")
        marker = "[fingerprint:"
        start = text.find(marker)
        if start < 0:
            continue
        left = start + len(marker)
        right = text.find("]", left)
        if right <= left:
            continue
        fp = text[left:right].strip().lower()
        if fp:
            out.add(fp)
    return out


def summarize_change_lines(changes: list[dict[str, str]], limit: int = 80) -> list[str]:
    lines: list[str] = []
    for item in changes[: max(1, int(limit))]:
        lines.append(f"{item.get('status', 'M')} {item.get('path', '')}")
    return lines


def infer_need_project_context(task_clarity: str, changes_count: int, clarity_max_files: int) -> bool:
    mode = str(task_clarity or "").strip().lower()
    if mode == "clear":
        return False
    if mode == "ambiguous":
        return True
    return int(changes_count) > max(1, int(clarity_max_files))


def query_context_gate(tc: TaskCenter, fingerprint: str) -> dict[str, Any]:
    change_id = f"ctx:{str(fingerprint or '').strip().lower()}"
    row = tc.conn.execute(
        """
        SELECT task_id, status, updated_at
        FROM tasks
        WHERE source = 'governance-evolution-agent'
          AND task_type = 'governance_evolution_context_preflight'
          AND change_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (change_id,),
    ).fetchone()
    if row is None:
        return {"exists": False, "ready": False, "blocked": False, "task_id": "", "status": ""}
    status = str(row["status"] or "").strip().lower()
    task_id = str(row["task_id"] or "").strip()
    if status == "passed":
        return {"exists": True, "ready": True, "blocked": False, "task_id": task_id, "status": status}
    if status in {"pending", "running", "failed", "escalated"}:
        return {"exists": True, "ready": False, "blocked": True, "task_id": task_id, "status": status}
    return {"exists": True, "ready": False, "blocked": False, "task_id": task_id, "status": status}


def create_context_preflight_task(
    *,
    tc: TaskCenter,
    repo_path: Path,
    fingerprint: str,
    scan_head: str,
    diff_base: str,
    change_lines: list[str],
    assignee: str,
    base_time: datetime,
) -> dict[str, Any]:
    normalized_assignee = str(assignee or "project-agent").strip() or "project-agent"
    constraint_fields = build_task_constraint_fields(normalized_assignee)
    requirement = "\n".join(
        [
            f"[fingerprint:{fingerprint}]",
            f"目标仓库: {repo_path}",
            f"增量窗口: {diff_base or '-'} -> {scan_head or '-'}",
            "请先完成项目上下文复核（project-agent）并产出上下文包：",
            "- 项目简介（工作流目标、关键模块、禁改边界）",
            "- 本次变更影响图（文件级）",
            "- 建议修改位置（精确到文件路径）",
            "- 验证命令与回滚方案",
            "",
            "本次增量文件：",
            *[f"- {line}" for line in change_lines[:120]],
        ]
    )
    task = tc.create_task(
        {
            "task_id": f"todo-governance-context-{base_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            "pool": "todo",
            "task_type": "governance_evolution_context_preflight",
            "reason": "[GOVERNANCE_EVOLUTION] project context preflight required",
            "source": "governance-evolution-agent",
            "request_source": "ai",
            "priority": "medium",
            "risk_level": "high",
            "assignee": normalized_assignee,
            **constraint_fields,
            "status": "pending",
            "need_human_confirm": False,
            "human_confirmed": False,
            "change_id": f"ctx:{fingerprint}",
            "requirement": requirement,
            "result_output": "输出上下文包：项目简介、影响文件、建议改动路径、验证与回滚。",
            "acceptance": "上下文包完整且可指导 optimization-agent 精确修改。",
            "observable_outputs": "context package, target file list, verification commands",
            "acceptance_thresholds": "包含精确文件路径和至少1条验证命令",
            "scheduled_at": (base_time + timedelta(minutes=1)).replace(microsecond=0).isoformat(),
            "context_payload": {
                "repo_path": str(repo_path),
                "fingerprint": fingerprint,
                "scan_head": scan_head,
                "diff_base": diff_base,
                "changes": change_lines[:120],
                "gate": "project_context_preflight",
            },
        },
        actor="governance-evolution-agent",
    )
    return task


def create_task_packages(
    *,
    db_file: Path,
    repo_path: Path,
    fingerprint: str,
    scan_head: str,
    diff_base: str,
    changes: list[dict[str, str]],
    create_review_task: bool,
    require_project_context: bool,
    project_context_assignee: str,
) -> dict[str, Any]:
    tc = TaskCenter(db_file)
    tc.init_schema()
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    base_time = now()
    change_lines = summarize_change_lines(changes, limit=120)
    open_fps = collect_open_fingerprints(tc)
    context_gate: dict[str, Any] = {
        "required": bool(require_project_context),
        "ready": not bool(require_project_context),
        "blocked": False,
        "created_task_id": "",
        "existing_task_id": "",
        "status": "not_required" if not bool(require_project_context) else "unknown",
    }

    try:
        if bool(require_project_context):
            gate = query_context_gate(tc, fingerprint)
            context_gate["existing_task_id"] = str(gate.get("task_id", ""))
            context_gate["status"] = str(gate.get("status", "")) or "missing"
            if bool(gate.get("ready", False)):
                context_gate["ready"] = True
                context_gate["status"] = "ready"
            elif bool(gate.get("blocked", False)):
                context_gate["blocked"] = True
                skipped.append({"fingerprint": fingerprint, "reason": "project_context_pending", "task_id": gate.get("task_id", "")})
                return {"created": created, "skipped": skipped, "context_gate": context_gate}
            else:
                ctx_task = create_context_preflight_task(
                    tc=tc,
                    repo_path=repo_path,
                    fingerprint=fingerprint,
                    scan_head=scan_head,
                    diff_base=diff_base,
                    change_lines=change_lines,
                    assignee=project_context_assignee,
                    base_time=base_time,
                )
                task_id = str(ctx_task.get("task_id", "")).strip()
                context_gate["blocked"] = True
                context_gate["created_task_id"] = task_id
                context_gate["status"] = "created"
                created.append(
                    {
                        "task_id": task_id,
                        "assignee": str(project_context_assignee or "project-agent").strip() or "project-agent",
                        "type": "governance_evolution_context_preflight",
                    }
                )
                skipped.append({"fingerprint": fingerprint, "reason": "project_context_required", "task_id": task_id})
                return {"created": created, "skipped": skipped, "context_gate": context_gate}

        if fingerprint in open_fps:
            skipped.append({"fingerprint": fingerprint, "reason": "already_open"})
            return {"created": created, "skipped": skipped, "context_gate": context_gate}

        optimize_requirement = "\n".join(
            [
                f"[fingerprint:{fingerprint}]",
                f"目标仓库: {repo_path}",
                f"增量窗口: {diff_base or '-'} -> {scan_head or '-'}",
                "增量变更文件:",
                *[f"- {line}" for line in change_lines],
                "",
                "执行要求:",
                "- 仅允许修改工作流代码路径: scripts/openclaw-ops/ / hooks/ / openclaw/ / setup.py",
                "- 严禁修改记忆与会话文件: openclaw-memory/ / memory/ / .workflow/experience/ / .workflow/sessions/ / MEMORY.md",
                "- 完成后创建分支: auto/evolution-<YYYYMMDD-HHMM>-<fingerprint前6位>",
                "- 提交后 push 并创建 PR 到 main，标题前缀: chore: governance evolution",
                "- 在 PR 描述写清: 问题、变更点、风险、回滚方式、验证命令",
            ]
        )
        optimize_constraint_fields = build_task_constraint_fields("optimization-agent")
        optimize_task = tc.create_task(
            {
                "task_id": f"todo-governance-evolution-{base_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
                "pool": "todo",
                "task_type": "governance_evolution_optimize",
                "reason": f"[GOVERNANCE_EVOLUTION] incremental changes detected ({len(changes)} files)",
                "source": "governance-evolution-agent",
                "request_source": "ai",
                "priority": "medium",
                "risk_level": "high",
                "assignee": "optimization-agent",
                **optimize_constraint_fields,
                "status": "pending",
                "need_human_confirm": False,
                "human_confirmed": False,
                "requirement": optimize_requirement,
                "result_output": "提交分支与PR链接，附验证结果与回滚说明。",
                "acceptance": "PR创建成功；变更范围受限；验证命令可复现。",
                "observable_outputs": "git branch/commit, PR URL, review notes",
                "acceptance_thresholds": "包含PR URL；至少1条验证命令通过；风险与回滚明确",
                "scheduled_at": (base_time + timedelta(minutes=2)).replace(microsecond=0).isoformat(),
                "context_payload": {
                    "repo_path": str(repo_path),
                    "fingerprint": fingerprint,
                    "scan_head": scan_head,
                    "diff_base": diff_base,
                    "changes": changes[:120],
                    "context_gate": context_gate,
                },
            },
            actor="governance-evolution-agent",
        )
        created.append(
            {
                "task_id": optimize_task.get("task_id", ""),
                "assignee": "optimization-agent",
                "type": "governance_evolution_optimize",
            }
        )

        if create_review_task:
            review_requirement = "\n".join(
                [
                    f"[fingerprint:{fingerprint}]",
                    f"目标仓库: {repo_path}",
                    "审查目标:",
                    "- 审核 optimization-agent 最新 governance evolution PR",
                    "- 核查边界: 不得改动记忆/会话文件",
                    "- 检查回滚与验证命令是否完整",
                    "",
                    "交付要求:",
                    "- 通过: 记录 approve 结论",
                    "- 不通过: 输出明确修复项并回流给 optimization-agent",
                ]
            )
            review_constraint_fields = build_task_constraint_fields("reviewer")
            review_task = tc.create_task(
                {
                    "task_id": f"todo-governance-review-{base_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
                    "pool": "todo",
                    "task_type": "governance_evolution_review",
                    "reason": "[GOVERNANCE_EVOLUTION] review optimization PR",
                    "source": "governance-evolution-agent",
                    "request_source": "ai",
                    "priority": "medium",
                    "risk_level": "high",
                    "assignee": "reviewer",
                    **review_constraint_fields,
                    "status": "pending",
                    "need_human_confirm": False,
                    "human_confirmed": False,
                    "requirement": review_requirement,
                    "result_output": "给出审查结论与关键问题清单。",
                    "acceptance": "审查结论明确，问题有定位信息。",
                    "observable_outputs": "review summary, blocking issues",
                    "acceptance_thresholds": "至少给出通过/不通过结论与证据",
                    "scheduled_at": (base_time + timedelta(minutes=90)).replace(microsecond=0).isoformat(),
                    "context_payload": {
                        "repo_path": str(repo_path),
                        "fingerprint": fingerprint,
                        "context_gate": context_gate,
                    },
                },
                actor="governance-evolution-agent",
            )
            created.append(
                {
                    "task_id": review_task.get("task_id", ""),
                    "assignee": "reviewer",
                    "type": "governance_evolution_review",
                }
            )
    finally:
        tc.close()
    return {"created": created, "skipped": skipped, "context_gate": context_gate}


def ensure_gh_ready() -> tuple[bool, str]:
    if not has_command("gh"):
        return False, "gh_not_found"
    rc, out, err = run_cmd(["gh", "auth", "status"], timeout=20, shell=False)
    if rc != 0:
        return False, err or out or "gh_auth_failed"
    return True, "ok"


def parse_existing_pr(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    if isinstance(payload, list) and payload:
        first = payload[0]
        return first if isinstance(first, dict) else {}
    return payload if isinstance(payload, dict) else {}


def attach_auto_pr_context(task_packaging: dict[str, Any], auto_pr_result: dict[str, Any]) -> dict[str, Any]:
    packaging = dict(task_packaging or {})
    created_items = packaging.get("created")
    created_list = list(created_items) if isinstance(created_items, list) else []
    auto_pr_payload = {
        "attempted": bool(auto_pr_result.get("attempted", False)),
        "ok": bool(auto_pr_result.get("ok", False)),
        "reason": str(auto_pr_result.get("reason", "")).strip(),
        "branch": str(auto_pr_result.get("branch", "")).strip(),
        "pr_url": str(auto_pr_result.get("pr_url", "")).strip(),
        "pr_number": int(auto_pr_result.get("pr_number", 0) or 0),
    }
    packaging["auto_pr"] = auto_pr_payload

    review_targets: list[dict[str, Any]] = []
    if auto_pr_payload["ok"] and auto_pr_payload["pr_number"] > 0 and auto_pr_payload["pr_url"]:
        for item in created_list:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).strip() != "governance_evolution_review":
                continue
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            review_targets.append(
                {
                    "task_id": task_id,
                    "pr_url": auto_pr_payload["pr_url"],
                    "pr_number": auto_pr_payload["pr_number"],
                    "branch": auto_pr_payload["branch"],
                }
            )
    packaging["review_targets"] = review_targets
    return packaging


def resolve_auto_pr_result(
    *,
    auto_pr_enabled: bool,
    context_blocked: bool,
    changes_scoped_count: int,
    attempt_auto_pr_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if not auto_pr_enabled:
        return {"attempted": False, "ok": False, "reason": "not_run", "pr_url": "", "pr_number": 0, "branch": ""}
    if int(changes_scoped_count) <= 0:
        return {"attempted": False, "ok": False, "reason": "no_scoped_changes", "pr_url": "", "pr_number": 0, "branch": ""}
    if context_blocked:
        return {
            "attempted": True,
            "ok": False,
            "reason": "blocked_by_project_context_gate",
            "pr_url": "",
            "pr_number": 0,
            "branch": "",
        }
    return attempt_auto_pr_fn()


def attempt_auto_pr(
    *,
    repo: Path,
    pr_base: str,
    pr_title_prefix: str,
    reviewer_gh_user: str,
    push_before_pr: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": True,
        "ok": False,
        "reason": "",
        "pr_url": "",
        "pr_number": 0,
        "branch": "",
    }
    ready, note = ensure_gh_ready()
    if not ready:
        result["reason"] = note
        return result

    rc, branch, err = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20)
    if rc != 0 or not branch:
        result["reason"] = f"branch_detect_failed:{err or rc}"
        return result
    branch = branch.strip()
    result["branch"] = branch
    if branch in {"HEAD", "", str(pr_base).strip()}:
        result["reason"] = "invalid_branch_for_pr"
        return result

    rc, out, err = run_git(repo, ["rev-list", "--count", f"{pr_base}..{branch}"], timeout=20)
    ahead = int(out.strip()) if rc == 0 and str(out).strip().isdigit() else 0
    if ahead <= 0:
        result["reason"] = "no_commits_ahead_base"
        return result

    rc, dirty_out, _err = run_git(repo, ["status", "--porcelain"], timeout=20)
    if rc != 0:
        result["reason"] = "git_status_failed"
        return result
    if str(dirty_out or "").strip():
        result["reason"] = "worktree_dirty"
        return result

    if push_before_pr:
        rc, _out, err = run_git(repo, ["push", "-u", "origin", branch], timeout=180)
        if rc != 0:
            result["reason"] = f"git_push_failed:{err or rc}"
            return result

    rc, out, err = run_cmd(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,url,title"],
        cwd=repo,
        timeout=40,
        shell=False,
    )
    existing = parse_existing_pr(out) if rc == 0 else {}

    pr_number = int(existing.get("number", 0) or 0) if isinstance(existing, dict) else 0
    pr_url = str(existing.get("url", "")).strip() if isinstance(existing, dict) else ""
    if pr_number <= 0:
        title = f"{pr_title_prefix} {now().strftime('%Y-%m-%d %H:%M UTC')}"
        body = "\n".join(
            [
                "## Governance Evolution",
                "- source: scheduled governance evolution loop",
                "- scope: workflow repository improvement only",
                "- reviewer: reviewer",
            ]
        )
        rc, out, err = run_cmd(
            [
                "gh",
                "pr",
                "create",
                "--base",
                str(pr_base),
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ],
            cwd=repo,
            timeout=60,
            shell=False,
        )
        if rc != 0:
            result["reason"] = f"gh_pr_create_failed:{err or out or rc}"
            return result
        pr_url = str(out).strip().splitlines()[-1].strip() if str(out).strip() else ""
        rc2, out2, _err2 = run_cmd(
            ["gh", "pr", "view", "--json", "number,url", "--jq", ".number"],
            cwd=repo,
            timeout=20,
            shell=False,
        )
        if rc2 == 0 and str(out2).strip().isdigit():
            pr_number = int(str(out2).strip())

    if reviewer_gh_user and pr_number > 0:
        run_cmd(
            ["gh", "pr", "edit", str(pr_number), "--add-reviewer", reviewer_gh_user],
            cwd=repo,
            timeout=40,
            shell=False,
        )

    result["ok"] = True
    result["reason"] = "ok"
    result["pr_url"] = pr_url
    result["pr_number"] = pr_number
    return result


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Governance evolution incremental runner")
    parser.add_argument("--repo-path", default="", help="target workflow git repository path")
    parser.add_argument("--openclaw-config", default=str(home / ".openclaw" / "openclaw.json"))
    parser.add_argument("--project-registry", default="")
    parser.add_argument("--repo-id", default="")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--auto-git-update", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--git-update-strategy", default="fetch", choices=sorted(GIT_UPDATE_STRATEGIES))
    parser.add_argument("--git-fetch-timeout", type=int, default=120)
    parser.add_argument("--db", default=str(home / ".openclaw" / "ops" / "task-center" / "task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw" / "ops" / "governance-evolution" / "state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw" / "ops" / "governance-evolution" / "reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--mode", default="incremental", choices=["incremental", "full"])
    parser.add_argument("--watch-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--min-interval-minutes", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--create-review-task", action="store_true", default=False)
    parser.add_argument("--task-clarity", default="auto", choices=sorted(TASK_CLARITY_MODES))
    parser.add_argument("--clarity-max-files", type=int, default=2)
    parser.add_argument("--project-context-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project-context-assignee", default="project-agent")
    parser.add_argument("--auto-pr", action="store_true")
    parser.add_argument("--pr-base", default="main")
    parser.add_argument("--pr-title-prefix", default="chore: governance evolution")
    parser.add_argument("--reviewer-gh-user", default="")
    parser.add_argument("--push-before-pr", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()
    sender_identity = normalize_sender_identity(args.sender_identity)
    task_id = str(args.task_id or "").strip()

    openclaw_config = Path(args.openclaw_config).expanduser()
    resolved_repo, repo_resolve = resolve_repo_from_inputs(
        repo_path_arg=str(args.repo_path or ""),
        openclaw_config=openclaw_config,
        registry_path_arg=str(args.project_registry or ""),
        repo_id=str(args.repo_id or ""),
        repo_name=str(args.repo_name or ""),
    )
    if resolved_repo is None:
        print_startup_failure(
            emit_json=bool(args.emit_json),
            sender_identity=sender_identity,
            task_id=task_id,
            error=str(repo_resolve.get("error", "repo resolve failed")),
            detail=compact_text(repo_resolve, 320),
            extra={"repo_resolve": repo_resolve},
        )
        return 2
    repo = resolved_repo
    db_file = Path(args.db).expanduser()
    state_file = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    git_update_strategy = normalize_git_update_strategy(args.git_update_strategy, default="fetch")

    state = load_json(state_file, None)
    if not isinstance(state, dict):
        state = state_default()

    if not repo.exists() or not repo.is_dir():
        print_startup_failure(
            emit_json=bool(args.emit_json),
            sender_identity=sender_identity,
            task_id=task_id,
            error=f"repo path invalid: {repo}",
        )
        return 2
    rc, out, err = run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=20)
    if rc != 0 or str(out).strip().lower() != "true":
        print_startup_failure(
            emit_json=bool(args.emit_json),
            sender_identity=sender_identity,
            task_id=task_id,
            error=f"not git repo: {repo}",
            detail=(err or out),
        )
        return 2

    git_update_result = update_local_git(
        repo,
        enabled=bool(args.auto_git_update),
        strategy=git_update_strategy,
        fetch_timeout=max(30, int(args.git_fetch_timeout)),
    )
    last_scan_at = str(state.get("last_scan_at", "")).strip()
    last_scan_head = str(state.get("last_scan_head", "")).strip()
    min_interval = max(1, int(args.min_interval_minutes))
    run_allowed = True
    if last_scan_at and (not bool(args.force)):
        try:
            ts = datetime.fromisoformat(last_scan_at.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            run_allowed = (now() - ts) >= timedelta(minutes=min_interval)
        except Exception:
            run_allowed = True
    if (not run_allowed) and bool(git_update_result.get("head_changed", False)):
        run_allowed = True

    changes_all: list[dict[str, str]] = []
    changes_scoped: list[dict[str, str]] = []
    change_stats_all: dict[str, int] = {"added": 0, "modified": 0, "deleted": 0, "renamed": 0, "other": 0}
    change_stats_scoped: dict[str, int] = {"added": 0, "modified": 0, "deleted": 0, "renamed": 0, "other": 0}
    scan_meta: dict[str, Any] = {}
    fingerprint = ""
    task_packaging: dict[str, Any] = {"created": [], "skipped": []}
    auto_pr_result: dict[str, Any] = {"attempted": bool(args.auto_pr), "ok": False, "reason": "not_run"}
    notify = False
    run_errors: list[str] = []
    task_clarity = str(args.task_clarity or "auto").strip().lower()
    require_project_context = False

    watch_prefixes = [normalize_rel(x) for x in args.watch_prefix if str(x).strip()]
    if not watch_prefixes:
        watch_prefixes = list(DEFAULT_WATCH_PREFIXES)
    exclude_prefixes = [normalize_rel(x) for x in args.exclude_prefix if str(x).strip()]
    if not exclude_prefixes:
        exclude_prefixes = list(DEFAULT_EXCLUDE_PREFIXES)
    exclude_filenames = set(DEFAULT_EXCLUDE_FILENAMES)

    try:
        if run_allowed or bool(args.force):
            changes_all, scan_meta = collect_incremental_changes(
                repo,
                mode=str(args.mode).strip().lower(),
                last_head=last_scan_head,
                max_files=max(1, int(args.max_files)),
                force=bool(args.force),
            )
            for item in changes_all:
                rel = str(item.get("path", "")).strip()
                if should_include_file(
                    rel=rel,
                    watch_prefixes=watch_prefixes,
                    exclude_prefixes=exclude_prefixes,
                    exclude_filenames=exclude_filenames,
                ):
                    changes_scoped.append(item)

            change_stats_all = summarize_change_stats(changes_all)
            change_stats_scoped = summarize_change_stats(changes_scoped)
            fingerprint = to_fingerprint(changes_scoped, scan_meta.get("head", "")) if changes_scoped else ""
            require_project_context = bool(args.project_context_gate) and infer_need_project_context(
                task_clarity=task_clarity,
                changes_count=len(changes_scoped),
                clarity_max_files=max(1, int(args.clarity_max_files)),
            )

            if changes_scoped and fingerprint:
                task_packaging = create_task_packages(
                    db_file=db_file,
                    repo_path=repo,
                    fingerprint=fingerprint,
                    scan_head=str(scan_meta.get("head", "")),
                    diff_base=str(scan_meta.get("diff_base", "")),
                    changes=changes_scoped,
                    create_review_task=bool(args.create_review_task),
                    require_project_context=require_project_context,
                    project_context_assignee=str(args.project_context_assignee or "project-agent").strip() or "project-agent",
                )
                if task_packaging.get("created"):
                    notify = True
            context_gate = task_packaging.get("context_gate", {}) if isinstance(task_packaging, dict) else {}
            context_blocked = bool(context_gate.get("blocked", False)) if isinstance(context_gate, dict) else False
            if bool(args.auto_pr):
                auto_pr_result = resolve_auto_pr_result(
                    auto_pr_enabled=bool(args.auto_pr),
                    context_blocked=context_blocked,
                    changes_scoped_count=len(changes_scoped),
                    attempt_auto_pr_fn=lambda: attempt_auto_pr(
                        repo=repo,
                        pr_base=str(args.pr_base).strip() or "main",
                        pr_title_prefix=str(args.pr_title_prefix).strip() or "chore: governance evolution",
                        reviewer_gh_user=str(args.reviewer_gh_user).strip(),
                        push_before_pr=bool(args.push_before_pr),
                    ),
                )
                if bool(auto_pr_result.get("ok", False)):
                    notify = True
                task_packaging = attach_auto_pr_context(task_packaging, auto_pr_result)
        else:
            scan_meta = {"mode": args.mode, "head": "", "diff_base": "", "skip_reason": "min_interval"}
    except Exception as exc:
        run_errors.append(f"governance_evolution_run_failed:{exc}")

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "normal_log_mode": log_mode,
        "repo_resolve": repo_resolve,
        "git_update": git_update_result,
        "repo_path": str(repo),
        "run_allowed": run_allowed,
        "mode": str(args.mode),
        "watch_prefixes": watch_prefixes,
        "exclude_prefixes": exclude_prefixes,
        "task_clarity": task_clarity,
        "require_project_context": require_project_context,
        "scan_meta": scan_meta,
        "changes_all_count": len(changes_all),
        "changes_all_stats": change_stats_all,
        "changes_scoped_count": len(changes_scoped),
        "changes_scoped_stats": change_stats_scoped,
        "changes_scoped": changes_scoped[:200],
        "fingerprint": fingerprint,
        "task_packaging": task_packaging,
        "auto_pr": auto_pr_result,
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms

    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    if db_file.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_file)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_file,
                raw_task_id,
                "governance-evolution-agent",
                "optimization-agent/governance-evolution",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        created_items = task_packaging.get("created", []) if isinstance(task_packaging.get("created"), list) else []
        module_args = [
            "log-module",
            "--module-name",
            "optimization-agent/governance-evolution",
            "--phase",
            "incremental_scan",
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            (
                "governance evolution run finished: "
                + f"changes_scoped={len(changes_scoped)} created={len(created_items)} auto_pr_ok={bool(auto_pr_result.get('ok', False))}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "run_allowed": bool(run_allowed),
                    "changes_scoped_count": len(changes_scoped),
                    "created_task_count": len(created_items),
                    "auto_pr_result": auto_pr_result,
                    "run_error_count": len(run_errors),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "governance-evolution-agent",
        ]
        if bound_task_id:
            module_args.extend(["--task-id", bound_task_id])
        ok_module, _payload_module, err_module = invoke_policy_enforcer(db_file, module_args, timeout=30)
        policy_observability["log_module_ok"] = ok_module
        if not ok_module and err_module:
            policy_observability["errors"].append(err_module)

        comm_args = [
            "log-communication",
            "--from-module",
            "optimization-agent/governance-evolution",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "governance_evolution_result",
            "--status",
            ("failed" if run_errors else "acked"),
            "--latency-ms",
            str(run_duration_ms),
            "--correlation-id",
            str(report.get("run_id", "")),
            "--payload-ref",
            str(report_file),
            "--details-json",
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "created_task_count": len(created_items),
                    "context_gate": task_packaging.get("context_gate", {}),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "governance-evolution-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_file, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        report_count = 0
        base_steps = "collect_incremental_changes,build_task_packages,optional_auto_pr"
        if bound_task_id:
            success = not run_errors
            quality_score = 92.0 if success else 55.0
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "governance-evolution-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("passed" if success else "partial"),
                "--solved",
                ("true" if success else "false"),
                "--resolved-issues",
                "governance_evolution_runtime_recorded",
                "--resolution-summary",
                (
                    "governance evolution runtime recorded"
                    if success
                    else "governance evolution runtime recorded with partial errors"
                ),
                "--resolution-steps",
                base_steps + ",record_runtime_observability",
                "--failed-items",
                ",".join(run_errors[:20]),
                "--failure-count",
                str(len(run_errors)),
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
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "created_count": len(created_items),
                        "created_task_ids": [str(item.get("task_id", "")).strip() for item in created_items[:20]],
                        "task_types": [
                            str(item.get("type", "")).strip()
                            for item in created_items[:20]
                            if str(item.get("type", "")).strip()
                        ],
                        "assignees": [
                            str(item.get("assignee", "")).strip()
                            for item in created_items[:20]
                            if str(item.get("assignee", "")).strip()
                        ],
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "governance-evolution-agent",
            ]
            ok_report, _payload_report, err_report = invoke_policy_enforcer(db_file, report_args, timeout=35)
            if ok_report:
                report_count += 1
            elif err_report:
                policy_observability["errors"].append(err_report)
        policy_observability["report_agent_result_count"] = report_count

        since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
        ok_summary, payload_summary, err_summary = invoke_policy_enforcer(
            db_file,
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

    report["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        report["planner_summary"] = planner_summary_snapshot
    save_json(report_file, report)

    state["runs"] = int(state.get("runs", 0)) + 1
    state["updated_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    if scan_meta.get("head"):
        state["last_scan_head"] = str(scan_meta.get("head"))
        state["last_scan_at"] = now_iso()
    if fingerprint:
        fps = state.get("fingerprints")
        if not isinstance(fps, dict):
            fps = {}
        fps[fingerprint] = {
            "time": now_iso(),
            "changes_count": len(changes_scoped),
            "report_file": str(report_file),
        }
        state["fingerprints"] = fps
    if auto_pr_result.get("ok"):
        state["last_pr_url"] = str(auto_pr_result.get("pr_url", ""))
        state["last_pr_number"] = int(auto_pr_result.get("pr_number", 0) or 0)
    save_json(state_file, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    auto_pr_reason = str(auto_pr_result.get("reason", "")).strip()
    if bool(auto_pr_result.get("attempted", False)) and (not bool(auto_pr_result.get("ok", False))):
        non_error_reasons = {"not_run", "no_commits_ahead_base", "invalid_branch_for_pr", "blocked_by_project_context_gate"}
        if auto_pr_reason and auto_pr_reason not in non_error_reasons:
            exception_reasons.append(f"auto_pr_failed:{auto_pr_reason}")
    if bool(git_update_result.get("enabled", False)) and not bool(git_update_result.get("fetch_ok", True)):
        exception_reasons.append(f"git_update_failed:{git_update_result.get('error', git_update_result.get('skipped_reason', 'unknown'))}")
    notify = bool(exception_reasons)

    output = "NO_REPLY"
    if notify:
        extra_lines = [
            f"目标仓库：{short_location_label(repo)}",
            f"扫描模式：{args.mode}",
            f"任务清晰度：{task_clarity}",
            f"允许执行：{'是' if run_allowed else '否'}",
            f"上下文门禁：{'开启' if require_project_context else '关闭'}",
            f"范围内变更：{len(changes_scoped)} 项",
            (
                "变更统计："
                f"新增 {int(change_stats_scoped.get('added', 0) or 0)} 项，"
                f"修改 {int(change_stats_scoped.get('modified', 0) or 0)} 项，"
                f"删除 {int(change_stats_scoped.get('deleted', 0) or 0)} 项，"
                f"重命名 {int(change_stats_scoped.get('renamed', 0) or 0)} 项。"
            ),
            f"新建任务：{len(task_packaging.get('created', []))} 项",
            f"异常数量：{len(exception_reasons)} 项",
            (
                "Git 更新："
                f"{'成功' if git_update_result.get('fetch_ok', True) else '失败'}，"
                f"策略 {git_update_result.get('strategy', '-') or '-'}，"
                f"落后提交 {int(git_update_result.get('behind', 0) or 0)} 个。"
            ),
        ]
        context_gate = task_packaging.get("context_gate", {}) if isinstance(task_packaging, dict) else {}
        if isinstance(context_gate, dict) and context_gate:
            extra_lines.append(
                "上下文门禁状态："
                f"就绪 {int(context_gate.get('ready', 0) or 0)} 个，"
                f"阻塞 {int(context_gate.get('blocked', 0) or 0)} 个，"
                f"状态 {context_gate.get('status', '-') or '-'}。"
            )
        if auto_pr_result.get("attempted"):
            extra_lines.append(
                "自动合并请求："
                f"{'成功' if auto_pr_result.get('ok') else '未成功'}，"
                f"原因 {auto_pr_result.get('reason', '-') or '-'}。"
            )
        detail_lines = []
        for idx, item in enumerate(changes_scoped[:6], start=1):
            detail_lines.append(
                f"变更样例{idx}：{item.get('status', 'M')} {short_location_label(str(item.get('path', '')))}"
            )
        output = render_chat_notice(
            "治理巡检异常",
            status="需处理",
            task_id=str(args.task_id or ""),
            sender_identity=sender_identity,
            run_time=now_iso(),
            trace_id=build_trace_id(report_file=report_file),
            summary=f"治理巡检发现 {len(exception_reasons)} 个异常，已生成 {len(task_packaging.get('created', []))} 项后续任务。",
            extra_lines=extra_lines,
            details=detail_lines,
            next_step="请按留痕编号查看内部报告，并确认是否需要人工接管。",
        )

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(output)
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

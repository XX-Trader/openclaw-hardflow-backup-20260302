#!/usr/bin/env python3
"""Conversation evolution incremental runner.

Purpose:
1) Scan recent conversation/session/memory files.
2) Detect potential bugs / workflow gaps / unresolved items / optimization points.
3) Package high-quality suggestions as TODO tasks for human-reviewed follow-up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from utf8_runtime import configure_process_utf8_stdio
from task_center import TaskCenter  # type: ignore
from task_capability_binding import build_task_constraint_fields  # type: ignore
from io_write_gateway import FileWriteError, write_json_atomic  # type: ignore
from chat_output import build_trace_id, render_chat_notice

configure_process_utf8_stdio()

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "conversation-evolution-agent/dialog-review"
DEFAULT_MAX_EVIDENCE_PER_CANDIDATE = 24
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
}
SCAN_SUFFIXES = {".md", ".txt", ".log", ".json", ".jsonl"}
DEFAULT_INCLUDE_PATH_HINTS = [
    "/.workflow/sessions/",
    "/.workflow/experience/",
    "/memory/",
    "/reports/",
]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "bug": [
        "bug",
        "error",
        "failed",
        "failure",
        "exception",
        "traceback",
        "报错",
        "失败",
        "异常",
        "不生效",
        "不下单",
        "卡住",
        "问题",
    ],
    "workflow_gap": [
        "workflow",
        "route",
        "routing",
        "cron",
        "scheduler",
        "project-agent",
        "reviewer",
        "context gate",
        "上下文",
        "路由",
        "流程",
        "调度",
        "任务分配",
    ],
    "unresolved": [
        "todo",
        "pending",
        "blocked",
        "later",
        "follow up",
        "workaround",
        "未解决",
        "待处理",
        "待确认",
        "后续",
        "临时方案",
        "绕过",
    ],
    "optimize": [
        "optimize",
        "optimization",
        "improve",
        "refactor",
        "performance",
        "token",
        "cost",
        "优化",
        "改进",
        "重构",
        "性能",
        "稳定",
        "节省",
    ],
}

CATEGORY_TITLES = {
    "bug": "近期对话缺陷与失败信号梳理",
    "workflow_gap": "近期对话流程与路由问题梳理",
    "unresolved": "近期对话未闭环事项梳理",
    "optimize": "近期对话优化建议梳理",
}


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


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

    actor_name = str(actor or "conversation-evolution-agent").strip() or "conversation-evolution-agent"
    assignee = actor_name.split("/", 1)[0].strip() or "conversation-evolution-agent"
    source_name = (
        str(source_module or "conversation-evolution-agent/dialog-review").strip()
        or "conversation-evolution-agent/dialog-review"
    )
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


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-03",
        "runs": 0,
        "updated_at": "",
        "last_scan_at": "",
        "last_report_file": "",
        "last_latest_mtime": 0.0,
        "fingerprints": {},
    }


def collect_workspace_roots(openclaw_home: Path, extra_roots: list[Path]) -> list[Path]:
    roots: list[Path] = []
    if openclaw_home.exists() and openclaw_home.is_dir():
        for child in sorted(openclaw_home.iterdir(), key=lambda p: str(p)):
            if child.is_dir() and child.name.startswith("workspace"):
                roots.append(child)
    for root in extra_roots:
        if root.exists() and root.is_dir() and root not in roots:
            roots.append(root)
    return roots


def should_include_path(path: Path, root: Path, include_hints: list[str]) -> bool:
    rel = str(path.relative_to(root)).replace("\\", "/").lower()
    if not include_hints:
        return True
    rel_with_slash = "/" + rel
    for hint in include_hints:
        if hint.lower() in rel_with_slash:
            return True
    return False


def collect_recent_files(
    *,
    roots: list[Path],
    lookback_hours: int,
    include_hints: list[str],
    max_files: int,
) -> list[dict[str, Any]]:
    cutoff = now() - timedelta(hours=max(1, int(lookback_hours)))
    cutoff_ts = cutoff.timestamp()
    found: list[dict[str, Any]] = []

    for root in roots:
        for cur, dirs, files in os.walk(root):
            cur_path = Path(cur)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                p = cur_path / name
                suffix = p.suffix.lower()
                if suffix not in SCAN_SUFFIXES:
                    continue
                if not should_include_path(p, root, include_hints):
                    continue
                try:
                    stat = p.stat()
                except Exception:
                    continue
                if stat.st_mtime < cutoff_ts:
                    continue
                found.append(
                    {
                        "path": str(p),
                        "root": str(root),
                        "mtime": float(stat.st_mtime),
                        "size": int(stat.st_size),
                    }
                )

    found.sort(key=lambda x: float(x.get("mtime", 0.0)), reverse=True)
    return found[: max(1, int(max_files))]


def extract_strings_from_json(obj: Any, out: list[str], limit: int) -> None:
    if len(out) >= limit:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if len(out) >= limit:
                break
            key_low = str(key).strip().lower()
            if key_low in {
                "text",
                "content",
                "message",
                "requirement",
                "result",
                "result_output",
                "summary",
                "note",
            } and isinstance(value, str):
                out.append(value)
            extract_strings_from_json(value, out, limit)
        return
    if isinstance(obj, list):
        for item in obj:
            if len(out) >= limit:
                break
            extract_strings_from_json(item, out, limit)


def read_text_lines(path: Path, max_bytes: int, max_lines: int) -> list[str]:
    suffix = path.suffix.lower()
    try:
        raw = path.read_bytes()[: max(1024, int(max_bytes))]
    except Exception:
        return []
    text = raw.decode("utf-8", errors="ignore")

    if suffix == ".json":
        try:
            payload = json.loads(text)
        except Exception:
            payload = {}
        out: list[str] = []
        extract_strings_from_json(payload, out, limit=max(10, int(max_lines)))
        if out:
            return out[: max(10, int(max_lines))]

    if suffix == ".jsonl":
        out_jsonl: list[str] = []
        for line in text.splitlines():
            if len(out_jsonl) >= max(10, int(max_lines)):
                break
            line_text = line.strip()
            if not line_text:
                continue
            try:
                payload = json.loads(line_text)
            except Exception:
                out_jsonl.append(line_text)
                continue
            extract_strings_from_json(payload, out_jsonl, limit=max(10, int(max_lines)))
        if out_jsonl:
            return out_jsonl[: max(10, int(max_lines))]

    lines = [x.strip() for x in text.splitlines() if str(x).strip()]
    return lines[: max(10, int(max_lines))]


def normalize_text_line(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    return compact[:220]


def normalize_for_dedupe(text: str) -> str:
    compact = normalize_text_line(text).lower()
    compact = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?\b",
        "<ts>",
        compact,
    )
    compact = re.sub(r"\b[0-9a-f]{8,64}\b", "<hex>", compact)
    compact = re.sub(r"\d+", "<num>", compact)
    return compact[:180]


def match_categories(line: str) -> set[str]:
    out: set[str] = set()
    low = str(line or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            kw_low = str(kw).lower()
            if not kw_low:
                continue
            if kw_low in low:
                out.add(cat)
                break
    return out


def collect_findings(
    *,
    files: list[dict[str, Any]],
    max_bytes_per_file: int,
    max_lines_per_file: int,
    max_findings: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    per_category: dict[str, int] = {k: 0 for k in CATEGORY_KEYWORDS.keys()}
    per_file_hits: list[dict[str, Any]] = []

    for item in files:
        path = Path(str(item.get("path", "")))
        lines = read_text_lines(path, max_bytes=max_bytes_per_file, max_lines=max_lines_per_file)
        file_hit_count = 0
        for idx, line in enumerate(lines, start=1):
            cats = match_categories(line)
            if not cats:
                continue
            norm = normalize_text_line(line)
            for cat in sorted(cats):
                per_category[cat] = int(per_category.get(cat, 0)) + 1
                findings.append(
                    {
                        "category": cat,
                        "path": str(path),
                        "line": idx,
                        "text": norm,
                        "mtime": float(item.get("mtime", 0.0)),
                    }
                )
                file_hit_count += 1
                if len(findings) >= max(10, int(max_findings)):
                    break
            if len(findings) >= max(10, int(max_findings)):
                break
        if file_hit_count > 0:
            per_file_hits.append(
                {
                    "path": str(path),
                    "hits": file_hit_count,
                    "mtime": float(item.get("mtime", 0.0)),
                }
            )
        if len(findings) >= max(10, int(max_findings)):
            break

    per_file_hits.sort(key=lambda x: int(x.get("hits", 0)), reverse=True)
    summary = {
        "total_findings": len(findings),
        "per_category": per_category,
        "top_files": per_file_hits[:20],
    }
    return findings, summary


def candidate_quality_metrics(items: list[dict[str, Any]]) -> dict[str, int]:
    evidence_count = len(items)
    unique_files = len({str(x.get("path", "")).strip().lower() for x in items if str(x.get("path", "")).strip()})
    unique_texts = len({normalize_for_dedupe(str(x.get("text", ""))) for x in items if str(x.get("text", "")).strip()})
    return {
        "evidence_count": int(evidence_count),
        "unique_files": int(unique_files),
        "unique_texts": int(unique_texts),
    }


def candidate_quality_score(metrics: dict[str, int]) -> int:
    evidence_count = max(0, int(metrics.get("evidence_count", 0)))
    unique_files = max(0, int(metrics.get("unique_files", 0)))
    unique_texts = max(0, int(metrics.get("unique_texts", 0)))
    evidence_score = min(60, evidence_count * 12)
    file_score = min(25, unique_files * 8)
    diversity_score = 0
    if evidence_count > 0:
        diversity_score = int(round(min(15.0, (unique_texts / evidence_count) * 15.0)))
    return int(max(0, evidence_score + file_score + diversity_score))


def candidate_dedupe_key(category: str, items: list[dict[str, Any]]) -> str:
    stable_items = sorted(
        items,
        key=lambda x: (
            str(x.get("path", "")).strip().lower(),
            int(x.get("line", 0) or 0),
            normalize_for_dedupe(str(x.get("text", ""))),
        ),
    )
    tokens: list[str] = []
    seen: set[str] = set()
    for item in stable_items:
        token = (
            f"{str(item.get('path', '')).strip().lower()}:"
            f"{normalize_for_dedupe(str(item.get('text', '')))}"
        )
        if (not token) or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= 16:
            break
    raw = f"{str(category).strip().lower()}|{'|'.join(tokens)}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def build_candidates(
    *,
    findings: list[dict[str, Any]],
    lookback_hours: int,
    min_evidence_lines: int,
    min_unique_files: int,
    min_quality_score: int,
    max_evidence_per_candidate: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in CATEGORY_KEYWORDS.keys()}
    for item in findings:
        cat = str(item.get("category", "")).strip()
        if cat in grouped:
            grouped[cat].append(item)

    ordered_categories = ["bug", "unresolved", "workflow_gap", "optimize"]
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    min_evidence = max(1, int(min_evidence_lines))
    min_files = max(1, int(min_unique_files))
    min_score = max(1, int(min_quality_score))
    evidence_cap = max(1, int(max_evidence_per_candidate))

    for cat in ordered_categories:
        items = grouped.get(cat, [])
        if not items:
            continue

        metrics = candidate_quality_metrics(items)
        score = candidate_quality_score(metrics)
        fail_reasons: list[str] = []
        if int(metrics.get("evidence_count", 0)) < min_evidence:
            fail_reasons.append("low_evidence")
        if int(metrics.get("unique_files", 0)) < min_files:
            fail_reasons.append("low_file_coverage")
        if score < min_score:
            fail_reasons.append("low_quality_score")
        if fail_reasons:
            rejected.append(
                {
                    "category": cat,
                    "quality_score": score,
                    "metrics": metrics,
                    "reasons": fail_reasons,
                }
            )
            continue

        evidence_lines = []
        for it in items[:evidence_cap]:
            evidence_lines.append(f"- {it.get('path')}:{int(it.get('line', 0))} | {it.get('text', '')}")

        dedupe_key = candidate_dedupe_key(cat, items)
        requirement = "\n".join(
            [
                f"复盘窗口: 最近 {int(lookback_hours)} 小时对话/会话/记忆记录",
                f"主题: {CATEGORY_TITLES.get(cat, cat)}",
                (
                    "质量评估: "
                    f"score={score}, evidence={int(metrics.get('evidence_count', 0))}, "
                    f"files={int(metrics.get('unique_files', 0))}, unique_text={int(metrics.get('unique_texts', 0))}"
                ),
                "",
                "观察到的问题与线索:",
                *evidence_lines,
                "",
                "输出要求:",
                "- 归纳根因与影响范围",
                "- 给出可执行修复/优化项（按优先级）",
                "- 标注哪些项需求不明确，需先走 project-agent 上下文复核",
                "- 输出需包含自我进化改进点（策略/路由/技能）",
                "- 输出最小验证步骤与回滚方式",
            ]
        )
        candidates.append(
            {
                "category": cat,
                "dedupe_key": dedupe_key,
                "quality": {"score": score, **metrics},
                "title": CATEGORY_TITLES.get(cat, cat),
                "reason": f"近期对话复盘识别到 {cat} 信号 {len(items)} 条，质量分 {score}",
                "requirement": requirement,
            }
        )

    return candidates, rejected


def parse_marker(text: str, marker: str) -> str:
    pattern = rf"\[{re.escape(str(marker or '').strip())}:([a-f0-9]{{8,64}})\]"
    m = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    return str(m.group(1)).lower() if m else ""


def parse_fingerprint(text: str) -> str:
    return parse_marker(text, "fingerprint")


def parse_dedupe_key(text: str) -> str:
    return parse_marker(text, "dedupe_key")


def candidate_fingerprint(title: str, requirement: str) -> str:
    raw = f"{title}\n{requirement}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def collect_open_fingerprints(tc: TaskCenter) -> set[str]:
    rows = tc.conn.execute(
        """
        SELECT requirement
        FROM tasks
        WHERE source = 'conversation-evolution-agent'
          AND pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        fp = parse_fingerprint(str(row["requirement"] or ""))
        if fp:
            out.add(fp)
    return out


def collect_recent_dedupe_keys(tc: TaskCenter, recent_days: int) -> set[str]:
    days = max(0, int(recent_days))
    if days <= 0:
        return set()
    cutoff = now() - timedelta(days=days)
    rows = tc.conn.execute(
        """
        SELECT requirement, created_at
        FROM tasks
        WHERE source = 'conversation-evolution-agent'
          AND pool = 'todo'
        ORDER BY created_at DESC
        LIMIT 5000
        """
    ).fetchall()
    out: set[str] = set()
    for row in rows:
        created_at = parse_iso(str(row["created_at"] or ""))
        if created_at and created_at < cutoff:
            continue
        key = parse_dedupe_key(str(row["requirement"] or ""))
        if key:
            out.add(key)
    return out


def infer_next_schedule_base(tc: TaskCenter) -> datetime:
    row = tc.conn.execute(
        """
        SELECT scheduled_at, created_at
        FROM tasks
        WHERE pool = 'todo'
          AND status IN ('pending', 'running', 'failed')
        ORDER BY COALESCE(scheduled_at, created_at) DESC, created_at DESC
        LIMIT 1
        """
    ).fetchone()
    base = now()
    if row:
        chosen = parse_iso(str(row["scheduled_at"] or row["created_at"] or ""))
        if chosen and chosen > base:
            base = chosen
    return base


def create_todo_tasks(
    tc: TaskCenter,
    *,
    candidates: list[dict[str, Any]],
    assignee: str,
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
    recent_dedupe_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_fingerprints = collect_open_fingerprints(tc)
    recent_dedupe_keys = collect_recent_dedupe_keys(tc, recent_days=recent_dedupe_days)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    base = infer_next_schedule_base(tc)
    limit = max(1, int(max_tasks_per_run))
    gap = max(1, int(schedule_gap_minutes))
    who = str(assignee or "").strip() or "optimization-agent"
    constraint_fields = build_task_constraint_fields(who)

    for candidate in candidates:
        title = str(candidate.get("title", "")).strip()
        reason = str(candidate.get("reason", "")).strip()
        requirement_raw = str(candidate.get("requirement", "")).strip()
        dedupe_key = str(candidate.get("dedupe_key", "")).strip().lower()
        quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
        if not title or not requirement_raw:
            continue

        fp = candidate_fingerprint(title=title, requirement=requirement_raw)
        if fp in open_fingerprints:
            skipped.append({"fingerprint": fp, "dedupe_key": dedupe_key, "reason": "already_open"})
            continue
        if dedupe_key and dedupe_key in recent_dedupe_keys:
            skipped.append({"fingerprint": fp, "dedupe_key": dedupe_key, "reason": "duplicate_recent"})
            continue
        if len(created) >= limit:
            skipped.append({"fingerprint": fp, "dedupe_key": dedupe_key, "reason": "run_limit_reached"})
            continue

        schedule_at = (base + timedelta(minutes=gap * (len(created) + 1))).replace(microsecond=0).isoformat()
        markers = [f"[fingerprint:{fp}]"]
        if dedupe_key:
            markers.append(f"[dedupe_key:{dedupe_key}]")
        requirement = "\n".join([*markers, requirement_raw])

        payload = {
            "task_id": f"todo-conversation-evolution-{now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            "pool": "todo",
            "task_type": "conversation_evolution",
            "reason": f"[CONVERSATION_EVOLUTION] {reason}",
            "source": "conversation-evolution-agent",
            "request_source": "ai",
            "priority": "low",
            "risk_level": "high",
            "assignee": who,
            **constraint_fields,
            "status": "pending",
            "need_human_confirm": True,
            "human_confirmed": False,
            "requirement": requirement,
            "result_output": "输出结构化优化建议与后续任务包，不直接执行高风险改动",
            "acceptance": "建议项可执行、证据可追溯、包含验证与回滚方案",
            "observable_outputs": "task_center记录、优化清单、验证步骤",
            "acceptance_thresholds": "至少1项可执行建议，且包含证据与风险说明",
            "scheduled_at": schedule_at,
        }
        task = tc.create_task(payload, actor="conversation-evolution-agent")
        tc.add_event(
            task_id=task["task_id"],
            actor="conversation-evolution-agent",
            event_type="conversation_evolution_task_packaged",
            stage="dialog_review",
            details={
                "fingerprint": fp,
                "dedupe_key": dedupe_key,
                "quality_score": int(quality.get("score", 0) or 0),
                "scheduled_at": schedule_at,
            },
        )

        created.append(
            {
                "task_id": task["task_id"],
                "fingerprint": fp,
                "dedupe_key": dedupe_key,
                "quality_score": int(quality.get("score", 0) or 0),
                "scheduled_at": schedule_at,
                "title": title,
                "assignee": who,
            }
        )
        open_fingerprints.add(fp)
        if dedupe_key:
            recent_dedupe_keys.add(dedupe_key)

    return created, skipped


def should_run(
    *,
    last_scan_at: str,
    min_interval_minutes: int,
    force: bool,
    latest_mtime: float,
    last_latest_mtime: float,
) -> bool:
    if force:
        return True
    if latest_mtime > float(last_latest_mtime or 0.0):
        return True
    dt = parse_iso(last_scan_at)
    if dt is None:
        return True
    return (now() - dt) >= timedelta(minutes=max(1, int(min_interval_minutes)))


def main() -> int:
    run_started_at = now()
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Conversation evolution incremental runner")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--scan-root", action="append", default=[])
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/conversation-evolution/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/conversation-evolution/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--lookback-hours", type=int, default=72)
    parser.add_argument("--min-interval-minutes", type=int, default=180)
    parser.add_argument("--max-files", type=int, default=120)
    parser.add_argument("--max-bytes-per-file", type=int, default=400000)
    parser.add_argument("--max-lines-per-file", type=int, default=1000)
    parser.add_argument("--max-findings", type=int, default=240)
    parser.add_argument("--max-evidence-per-candidate", type=int, default=DEFAULT_MAX_EVIDENCE_PER_CANDIDATE)
    parser.add_argument("--min-evidence-lines", type=int, default=3)
    parser.add_argument("--min-unique-files", type=int, default=1)
    parser.add_argument("--min-quality-score", type=int, default=55)
    parser.add_argument("--max-tasks-per-run", type=int, default=3)
    parser.add_argument("--schedule-gap-minutes", type=int, default=90)
    parser.add_argument("--recent-dedupe-days", type=int, default=14)
    parser.add_argument("--assignee", default="optimization-agent")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    state_path = Path(args.state_file).expanduser()
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)

    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = state_default()

    openclaw_home = Path(args.openclaw_home).expanduser()
    extra_roots = [Path(x).expanduser() for x in args.scan_root if str(x).strip()]
    roots = collect_workspace_roots(openclaw_home=openclaw_home, extra_roots=extra_roots)

    files = collect_recent_files(
        roots=roots,
        lookback_hours=max(1, int(args.lookback_hours)),
        include_hints=list(DEFAULT_INCLUDE_PATH_HINTS),
        max_files=max(1, int(args.max_files)),
    )
    latest_mtime = max([float(x.get("mtime", 0.0)) for x in files], default=0.0)
    run_allowed = should_run(
        last_scan_at=str(state.get("last_scan_at", "")),
        min_interval_minutes=max(1, int(args.min_interval_minutes)),
        force=bool(args.force),
        latest_mtime=latest_mtime,
        last_latest_mtime=float(state.get("last_latest_mtime", 0.0) or 0.0),
    )

    findings: list[dict[str, Any]] = []
    finding_summary: dict[str, Any] = {"total_findings": 0, "per_category": {}, "top_files": []}
    candidates: list[dict[str, Any]] = []
    candidate_rejected: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    run_errors: list[str] = []

    try:
        if run_allowed and files:
            findings, finding_summary = collect_findings(
                files=files,
                max_bytes_per_file=max(1024, int(args.max_bytes_per_file)),
                max_lines_per_file=max(50, int(args.max_lines_per_file)),
                max_findings=max(10, int(args.max_findings)),
            )
            candidates, candidate_rejected = build_candidates(
                findings=findings,
                lookback_hours=int(args.lookback_hours),
                min_evidence_lines=max(1, int(args.min_evidence_lines)),
                min_unique_files=max(1, int(args.min_unique_files)),
                min_quality_score=max(1, int(args.min_quality_score)),
                max_evidence_per_candidate=max(1, int(args.max_evidence_per_candidate)),
            )
            if candidates:
                tc = TaskCenter(Path(args.db).expanduser())
                try:
                    tc.init_schema()
                    created, skipped = create_todo_tasks(
                        tc,
                        candidates=candidates,
                        assignee=str(args.assignee or "optimization-agent").strip() or "optimization-agent",
                        max_tasks_per_run=max(1, int(args.max_tasks_per_run)),
                        schedule_gap_minutes=max(1, int(args.schedule_gap_minutes)),
                        recent_dedupe_days=max(0, int(args.recent_dedupe_days)),
                    )
                finally:
                    tc.close()
    except Exception as exc:
        run_errors.append(f"conversation_evolution_run_failed:{exc}")

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "normal_log_mode": log_mode,
        "openclaw_home": str(openclaw_home),
        "scan_roots": [str(x) for x in roots],
        "run_allowed": run_allowed,
        "lookback_hours": int(args.lookback_hours),
        "files_scanned_count": len(files),
        "files_scanned": files[:200],
        "finding_summary": finding_summary,
        "findings": findings[:400],
        "quality_policy": {
            "min_evidence_lines": max(1, int(args.min_evidence_lines)),
            "min_unique_files": max(1, int(args.min_unique_files)),
            "min_quality_score": max(1, int(args.min_quality_score)),
            "max_evidence_per_candidate": max(1, int(args.max_evidence_per_candidate)),
            "recent_dedupe_days": max(0, int(args.recent_dedupe_days)),
        },
        "candidates_count": len(candidates),
        "candidates_rejected_count": len(candidate_rejected),
        "candidates_rejected": candidate_rejected[:200],
        "created_count": len(created),
        "created": created,
        "skipped": skipped,
        "run_errors": run_errors,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"

    run_duration_ms = max(0, int((now() - run_started_at).total_seconds() * 1000))
    report["run_duration_ms"] = run_duration_ms

    policy_observability: dict[str, Any] = {"enabled": False, "db": "", "task_bound": False, "errors": []}
    planner_summary_snapshot: dict[str, Any] = {}
    db_path = Path(args.db).expanduser()
    if db_path.exists():
        policy_observability["enabled"] = True
        policy_observability["db"] = str(db_path)
        bound_task_id = ""
        raw_task_id = str(args.task_id or "").strip()
        if raw_task_id:
            bound_task_id, bind_err = ensure_task_binding(
                db_path,
                raw_task_id,
                "conversation-evolution-agent",
                "conversation-evolution-agent/dialog-review",
            )
            if bound_task_id:
                policy_observability["task_bound"] = True
            elif bind_err:
                policy_observability["errors"].append(bind_err)

        module_args = [
            "log-module",
            "--module-name",
            "conversation-evolution-agent/dialog-review",
            "--phase",
            "dialog_review",
            "--level",
            ("error" if run_errors else "info"),
            "--status",
            ("failed" if run_errors else "passed"),
            "--message",
            (
                "conversation evolution run finished: "
                + f"created={len(created)} candidates={len(candidates)} findings={int(finding_summary.get('total_findings', 0) or 0)}"
            ),
            "--duration-ms",
            str(run_duration_ms),
            "--details-json",
            json.dumps(
                {
                    "run_allowed": bool(run_allowed),
                    "files_scanned_count": len(files),
                    "created_count": len(created),
                    "run_error_count": len(run_errors),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "conversation-evolution-agent",
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
            "conversation-evolution-agent/dialog-review",
            "--to-module",
            "coordinator",
            "--protocol",
            "policy-enforcer",
            "--message-type",
            "todo_task_packaged",
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
                    "created_count": len(created),
                    "candidate_count": len(candidates),
                    "run_error_count": len(run_errors),
                },
                ensure_ascii=False,
            ),
            "--actor",
            "conversation-evolution-agent",
        ]
        if bound_task_id:
            comm_args.extend(["--task-id", bound_task_id])
        ok_comm, _payload_comm, err_comm = invoke_policy_enforcer(db_path, comm_args, timeout=30)
        policy_observability["log_communication_ok"] = ok_comm
        if not ok_comm and err_comm:
            policy_observability["errors"].append(err_comm)

        reported_count = 0
        if bound_task_id:
            success = not run_errors
            quality_score = (
                sum(float(item.get("quality_score", 0) or 0) for item in created) / len(created)
                if created
                else (55.0 if run_errors else 90.0)
            )
            report_args = [
                "report-agent-result",
                "--task-id",
                bound_task_id,
                "--agent-id",
                "conversation-evolution-agent",
                "--planner-id",
                "coordinator",
                "--status",
                ("partial" if run_errors else "passed"),
                "--solved",
                ("false" if run_errors else "true"),
                "--resolved-issues",
                "conversation_evolution_runtime_recorded",
                "--resolution-summary",
                (
                    "conversation evolution runtime recorded"
                    if success
                    else "conversation evolution runtime recorded with errors"
                ),
                "--resolution-steps",
                "scan_recent_files,collect_findings,build_candidates,create_todo_task,record_runtime_observability",
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
                str(round(quality_score, 2)),
                "--quality-grade",
                quality_grade_from_score(quality_score),
                "--notify-chat",
                ("true" if run_errors else "false"),
                "--details-json",
                json.dumps(
                    {
                        "run_id": report.get("run_id"),
                        "created_count": len(created),
                        "created_task_ids": [str(item.get("task_id", "")).strip() for item in created[:20]],
                        "fingerprints": [
                            str(item.get("fingerprint", "")).strip()
                            for item in created[:20]
                            if str(item.get("fingerprint", "")).strip()
                        ],
                    },
                    ensure_ascii=False,
                ),
                "--actor",
                "conversation-evolution-agent",
            ]
            ok_report, _payload_report, err_report = invoke_policy_enforcer(db_path, report_args, timeout=35)
            if ok_report:
                reported_count += 1
            elif err_report:
                policy_observability["errors"].append(err_report)
        policy_observability["report_agent_result_count"] = reported_count

        since_24h = (now() - timedelta(hours=24)).replace(microsecond=0).isoformat()
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

    report["policy_observability"] = policy_observability
    if planner_summary_snapshot:
        report["planner_summary"] = planner_summary_snapshot
    save_json(report_file, report)

    state["runs"] = int(state.get("runs", 0)) + 1
    state["updated_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    state["last_latest_mtime"] = float(latest_mtime)
    if run_allowed:
        state["last_scan_at"] = now_iso()

    fps = state.get("fingerprints")
    if not isinstance(fps, dict):
        fps = {}
    for item in created:
        fps[str(item.get("fingerprint", ""))] = str(item.get("task_id", ""))
    state["fingerprints"] = fps
    save_json(state_path, state)

    exception_reasons: list[str] = []
    exception_reasons.extend(run_errors)
    if isinstance(policy_observability.get("errors"), list):
        exception_reasons.extend(str(x) for x in policy_observability.get("errors", []) if str(x).strip())
    notify = bool(exception_reasons)

    output = "NO_REPLY"
    if notify:
        detail_lines = [
            f"建议任务{idx}：{item.get('task_id')}，质量分 {item.get('quality_score', 0)}，计划时间 {item.get('scheduled_at')}"
            for idx, item in enumerate(created[:8], start=1)
        ]
        per_cat = finding_summary.get("per_category", {})
        extra_lines = [
            f"允许执行：{'是' if run_allowed else '否'}",
            f"扫描文件：{len(files)} 个",
            f"发现问题：{int(finding_summary.get('total_findings', 0) or 0)} 项",
            f"候选建议：{len(candidates)} 项",
            f"已过滤：{len(candidate_rejected)} 项",
            f"新建建议任务：{len(created)} 项",
            f"跳过项：{len(skipped)} 项",
            f"默认负责人：{str(args.assignee or 'optimization-agent')}",
            f"异常数量：{len(exception_reasons)} 项",
            (
                "质量门槛："
                f"分数不少于 {max(1, int(args.min_quality_score))}，"
                f"证据不少于 {max(1, int(args.min_evidence_lines))} 行，"
                f"文件不少于 {max(1, int(args.min_unique_files))} 个，"
                f"去重窗口 {max(0, int(args.recent_dedupe_days))} 天。"
            ),
        ]
        if isinstance(per_cat, dict) and per_cat:
            extra_lines.append(
                "分类分布："
                + "，".join(f"{k} {int(v)} 项" for k, v in sorted(per_cat.items(), key=lambda kv: str(kv[0])))
            )
        output = render_chat_notice(
            "对话复盘异常",
            status="需关注",
            task_id=str(args.task_id or ""),
            sender_identity=sender_identity,
            run_time=now_iso(),
            trace_id=build_trace_id(report_file=report_file),
            summary=f"对话复盘发现 {len(exception_reasons)} 个异常，并生成 {len(created)} 条建议任务。",
            extra_lines=extra_lines,
            details=detail_lines,
            next_step="请按留痕编号查看详细复盘结果，并确认是否进入后续排期。",
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

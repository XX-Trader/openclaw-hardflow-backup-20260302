#!/usr/bin/env python3
"""Conversation evolution runner.

Purpose:
1) Scan recent conversation/session/memory files.
2) Detect potential bugs / workflow gaps / unresolved items / optimization points.
3) Package suggestions as TODO tasks for human-reviewed follow-up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from task_center import TaskCenter  # type: ignore

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
DEFAULT_SENDER_IDENTITY = "conversation-evolution-agent/dialog-review"
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
        "稳定性",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


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


def build_candidates(
    *,
    findings: list[dict[str, Any]],
    lookback_hours: int,
) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in CATEGORY_KEYWORDS.keys()}
    for item in findings:
        cat = str(item.get("category", "")).strip()
        if cat in grouped:
            grouped[cat].append(item)

    ordered_categories = ["bug", "unresolved", "workflow_gap", "optimize"]
    candidates: list[dict[str, str]] = []
    for cat in ordered_categories:
        items = grouped.get(cat, [])
        if not items:
            continue
        evidence_lines = []
        for it in items[:24]:
            evidence_lines.append(
                f"- {it.get('path')}:{int(it.get('line', 0))} | {it.get('text', '')}"
            )
        requirement = "\n".join(
            [
                f"复盘窗口: 最近 {int(lookback_hours)} 小时对话/会话记录",
                f"主题: {CATEGORY_TITLES.get(cat, cat)}",
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
                "title": CATEGORY_TITLES.get(cat, cat),
                "reason": f"近期对话复盘识别到 {cat} 信号 {len(items)} 条",
                "requirement": requirement,
            }
        )
    return candidates


def parse_fingerprint(text: str) -> str:
    m = re.search(r"\[fingerprint:([a-f0-9]{8,40})\]", str(text or ""), flags=re.IGNORECASE)
    return str(m.group(1)).lower() if m else ""


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
    candidates: list[dict[str, str]],
    assignee: str,
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_fingerprints = collect_open_fingerprints(tc)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    base = infer_next_schedule_base(tc)
    limit = max(1, int(max_tasks_per_run))
    gap = max(1, int(schedule_gap_minutes))
    who = str(assignee or "").strip() or "optimization-agent"

    for candidate in candidates:
        title = str(candidate.get("title", "")).strip()
        reason = str(candidate.get("reason", "")).strip()
        requirement_raw = str(candidate.get("requirement", "")).strip()
        if not title or not requirement_raw:
            continue

        fp = candidate_fingerprint(title=title, requirement=requirement_raw)
        if fp in open_fingerprints:
            skipped.append({"fingerprint": fp, "reason": "already_open"})
            continue
        if len(created) >= limit:
            skipped.append({"fingerprint": fp, "reason": "run_limit_reached"})
            continue

        schedule_at = (base + timedelta(minutes=gap * (len(created) + 1))).replace(microsecond=0).isoformat()
        requirement = f"[fingerprint:{fp}]\n{requirement_raw}"
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
            "status": "pending",
            "need_human_confirm": True,
            "human_confirmed": False,
            "requirement": requirement,
            "result_output": "输出结构化优化建议与后续任务包，不直接执行高风险改动",
            "acceptance": "建议项可执行、证据可追溯、包含验证与回滚方案",
            "observable_outputs": "task_center记录、优化清单、验证步骤",
            "acceptance_thresholds": "至少1项可执行建议，且含证据与风险说明",
            "scheduled_at": schedule_at,
        }
        task = tc.create_task(payload, actor="conversation-evolution-agent")
        tc.add_event(
            task_id=task["task_id"],
            actor="conversation-evolution-agent",
            event_type="conversation_evolution_task_packaged",
            stage="dialog_review",
            details={"fingerprint": fp, "scheduled_at": schedule_at},
        )
        created.append(
            {
                "task_id": task["task_id"],
                "fingerprint": fp,
                "scheduled_at": schedule_at,
                "title": title,
                "assignee": who,
            }
        )
        open_fingerprints.add(fp)
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
    parser.add_argument("--max-tasks-per-run", type=int, default=3)
    parser.add_argument("--schedule-gap-minutes", type=int, default=90)
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
    candidates: list[dict[str, str]] = []
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if run_allowed and files:
        findings, finding_summary = collect_findings(
            files=files,
            max_bytes_per_file=max(1024, int(args.max_bytes_per_file)),
            max_lines_per_file=max(50, int(args.max_lines_per_file)),
            max_findings=max(10, int(args.max_findings)),
        )
        candidates = build_candidates(findings=findings, lookback_hours=int(args.lookback_hours))
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
                )
            finally:
                tc.close()

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
        "candidates_count": len(candidates),
        "created_count": len(created),
        "created": created,
        "skipped": skipped,
    }
    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
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

    notify = bool(created)
    if not notify and log_mode == "chat":
        notify = True

    output = "NO_REPLY"
    if notify:
        lines = [
            "# conversation-evolution",
            f"- sender_identity: {sender_identity}",
            f"- task: {args.task_id or '-'}",
            f"- time: {now_iso()}",
            f"- run_allowed: {run_allowed}",
            f"- files_scanned: {len(files)}",
            f"- findings: {int(finding_summary.get('total_findings', 0) or 0)}",
            f"- candidates: {len(candidates)}",
            f"- created_todo: {len(created)}",
            f"- assignee: {str(args.assignee or 'optimization-agent')}",
        ]
        per_cat = finding_summary.get("per_category", {})
        if isinstance(per_cat, dict) and per_cat:
            lines.append(
                "- findings_by_category: "
                + ", ".join(f"{k}={int(v)}" for k, v in sorted(per_cat.items(), key=lambda kv: str(kv[0])))
            )
        for item in created[:8]:
            lines.append(f"- todo[{item.get('task_id')}]: scheduled_at={item.get('scheduled_at')}")
        output = "\n".join(lines)

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "report": str(report_file)}, ensure_ascii=False))
    else:
        if notify:
            print(f"{output}\n- evidence: {report_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

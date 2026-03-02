#!/usr/bin/env python3
"""Weekly self-evolution reviewer.

Hard boundary:
- Only outputs suggestions and task packages.
- Does NOT modify workflow or skills automatically.
- Pushes low-priority, high-risk tasks into TODO queue for human confirmation.
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
DEFAULT_SENDER_IDENTITY = "self-evolution-agent/weekly-review"


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


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


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-02",
        "runs": 0,
        "updated_at": "",
        "last_full_review_at": "",
        "last_report_file": "",
        "fingerprints": {},
    }


def should_run_weekly(last_review_at: str, min_days: int, force: bool) -> bool:
    if force:
        return True
    if not str(last_review_at or "").strip():
        return True
    dt = parse_iso(last_review_at)
    if dt is None:
        return True
    return (now() - dt) >= timedelta(days=max(1, int(min_days)))


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


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
        WHERE source = 'self-evolution-agent'
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


def collect_metrics(tc: TaskCenter, lookback_days: int) -> dict[str, Any]:
    since = (now() - timedelta(days=max(1, int(lookback_days)))).isoformat()
    metrics: dict[str, Any] = {"since": since}

    agent_rows = tc.conn.execute(
        """
        SELECT
          COALESCE(NULLIF(assignee, ''), 'unassigned') AS assignee,
          COUNT(*) AS total,
          SUM(CASE WHEN status IN ('failed', 'escalated') THEN 1 ELSE 0 END) AS failed
        FROM tasks
        WHERE created_at >= ?
        GROUP BY COALESCE(NULLIF(assignee, ''), 'unassigned')
        HAVING COUNT(*) >= 3
        ORDER BY failed DESC, total DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    agent_health: list[dict[str, Any]] = []
    for row in agent_rows:
        total = int(row["total"] or 0)
        failed = int(row["failed"] or 0)
        agent_health.append(
            {
                "assignee": str(row["assignee"] or ""),
                "total": total,
                "failed": failed,
                "failure_ratio": round(safe_ratio(failed, total), 4),
            }
        )
    metrics["agent_health"] = agent_health

    stage_rows = tc.conn.execute(
        """
        SELECT
          stage,
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
          AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms
        FROM stage_runs
        WHERE started_at >= ?
        GROUP BY stage
        HAVING COUNT(*) >= 3
        ORDER BY failed DESC, total DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    stage_health: list[dict[str, Any]] = []
    for row in stage_rows:
        total = int(row["total"] or 0)
        failed = int(row["failed"] or 0)
        stage_health.append(
            {
                "stage": str(row["stage"] or ""),
                "total": total,
                "failed": failed,
                "failure_ratio": round(safe_ratio(failed, total), 4),
                "avg_duration_ms": int(float(row["avg_duration_ms"] or 0.0)),
            }
        )
    metrics["stage_health"] = stage_health

    token_rows = tc.conn.execute(
        """
        SELECT
          task_id,
          SUM(total_tokens) AS total_tokens,
          SUM(cost_estimate) AS total_cost
        FROM token_usage
        WHERE ts >= ?
        GROUP BY task_id
        ORDER BY total_tokens DESC
        LIMIT 8
        """,
        (since,),
    ).fetchall()
    heavy_tasks: list[dict[str, Any]] = []
    for row in token_rows:
        heavy_tasks.append(
            {
                "task_id": str(row["task_id"] or ""),
                "total_tokens": int(row["total_tokens"] or 0),
                "total_tokens_m": round(int(row["total_tokens"] or 0) / 1_000_000.0, 6),
                "total_cost": round(float(row["total_cost"] or 0.0), 6),
            }
        )
    metrics["heavy_tasks"] = heavy_tasks

    return metrics


def build_candidates(metrics: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    since = str(metrics.get("since", ""))
    agent_health = metrics.get("agent_health", []) if isinstance(metrics.get("agent_health"), list) else []
    stage_health = metrics.get("stage_health", []) if isinstance(metrics.get("stage_health"), list) else []
    heavy_tasks = metrics.get("heavy_tasks", []) if isinstance(metrics.get("heavy_tasks"), list) else []

    unstable_agents = [x for x in agent_health if float(x.get("failure_ratio", 0)) >= 0.30]
    if unstable_agents:
        top = ", ".join(
            f"{x.get('assignee')}({x.get('failed')}/{x.get('total')})" for x in unstable_agents[:5]
        )
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"识别到执行稳定性偏低的agent: {top}\n"
            "请输出优化任务包（修改/升级/删除建议），但禁止自动执行变更；仅允许提交给 TODO 并等待人工确认。"
        )
        candidates.append(
            {
                "title": "周度Agent稳定性优化建议包",
                "reason": "自我进化复盘发现部分agent失败率偏高，需要人工确认后优化",
                "requirement": requirement,
            }
        )

    bad_stages = [x for x in stage_health if int(x.get("failed", 0)) > 0]
    if bad_stages:
        top = ", ".join(
            f"{x.get('stage')}({x.get('failed')}/{x.get('total')},avg={x.get('avg_duration_ms')}ms)"
            for x in bad_stages[:5]
        )
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"识别到流程热点: {top}\n"
            "请拆解成可执行任务包交给规划者分发，不允许直接修改工作流主配置。"
        )
        candidates.append(
            {
                "title": "周度工作流瓶颈与错误热点建议包",
                "reason": "自我进化复盘发现流程阶段异常，需要先任务化再优化",
                "requirement": requirement,
            }
        )

    if heavy_tasks:
        top = ", ".join(f"{x.get('task_id')}({x.get('total_tokens_m')}M)" for x in heavy_tasks[:6])
        requirement = (
            f"周度复盘窗口: {since}\n"
            f"高token任务: {top}\n"
            "请输出成本优化建议与路由优化建议，涉及技能增删改必须人工确认后执行。"
        )
        candidates.append(
            {
                "title": "周度成本与路由优化建议包",
                "reason": "自我进化复盘发现token成本偏高，需要人工确认后推进",
                "requirement": requirement,
            }
        )

    if not candidates:
        candidates.append(
            {
                "title": "周度经验沉淀建议包",
                "reason": "自我进化常规复盘，沉淀可复用经验并任务化",
                "requirement": (
                    f"周度复盘窗口: {since}\n"
                    "总结可复用经验、流程改进点、技能治理建议；仅产出任务包到 TODO，不自动改配置。"
                ),
            }
        )
    return candidates


def create_todo_tasks(
    tc: TaskCenter,
    *,
    candidates: list[dict[str, str]],
    max_tasks_per_run: int,
    schedule_gap_minutes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_fingerprints = collect_open_fingerprints(tc)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    base = infer_next_schedule_base(tc)
    limit = max(1, int(max_tasks_per_run))
    gap = max(1, int(schedule_gap_minutes))

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
            "task_id": f"todo-self-evolution-{now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            "pool": "todo",
            "task_type": "self_evolution",
            "reason": f"[SELF_EVOLUTION] {reason}",
            "source": "self-evolution-agent",
            "priority": "low",
            "risk_level": "high",
            "assignee": "coordinator",
            "status": "pending",
            "need_human_confirm": True,
            "human_confirmed": False,
            "requirement": requirement,
            "result_output": "输出建议与任务包，提交给规划者；不得自动改工作流",
            "acceptance": "任务包字段完整、可追溯、可人工审批",
            "observable_outputs": "task_center记录/建议包json/周报摘要",
            "acceptance_thresholds": "建议>=1条；包含风险与回滚说明；人工确认后才执行",
            "scheduled_at": schedule_at,
        }
        task = tc.create_task(payload, actor="self-evolution-agent")
        tc.add_event(
            task_id=task["task_id"],
            actor="self-evolution-agent",
            event_type="self_evolution_task_packaged",
            stage="weekly_review",
            details={"fingerprint": fp, "scheduled_at": schedule_at},
        )
        created.append({"task_id": task["task_id"], "fingerprint": fp, "scheduled_at": schedule_at, "title": title})
        open_fingerprints.add(fp)
    return created, skipped


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Weekly self-evolution TODO packager")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/self-evolution/state.json"))
    parser.add_argument("--report-dir", default=str(home / ".openclaw/ops/self-evolution/reports"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--min-review-interval-days", type=int, default=7)
    parser.add_argument("--max-tasks-per-run", type=int, default=3)
    parser.add_argument("--schedule-gap-minutes", type=int, default=120)
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

    run_allowed = should_run_weekly(
        last_review_at=str(state.get("last_full_review_at", "")),
        min_days=int(args.min_review_interval_days),
        force=bool(args.force),
    )

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    if run_allowed:
        tc = TaskCenter(Path(args.db).expanduser())
        try:
            tc.init_schema()
            metrics = collect_metrics(tc, lookback_days=int(args.lookback_days))
            candidates = build_candidates(metrics)
            created, skipped = create_todo_tasks(
                tc,
                candidates=candidates,
                max_tasks_per_run=int(args.max_tasks_per_run),
                schedule_gap_minutes=int(args.schedule_gap_minutes),
            )
        finally:
            tc.close()

    report = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "run_allowed": run_allowed,
        "normal_log_mode": log_mode,
        "lookback_days": int(args.lookback_days),
        "min_review_interval_days": int(args.min_review_interval_days),
        "max_tasks_per_run": int(args.max_tasks_per_run),
        "candidates_count": len(candidates),
        "created_count": len(created),
        "created": created,
        "skipped": skipped,
        "metrics": metrics,
    }

    report_file = report_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{report['run_id']}.json"
    save_json(report_file, report)

    state["runs"] = int(state.get("runs", 0)) + 1
    state["updated_at"] = now_iso()
    if run_allowed:
        state["last_full_review_at"] = now_iso()
    state["last_report_file"] = str(report_file)
    state_fps = state.get("fingerprints")
    if not isinstance(state_fps, dict):
        state_fps = {}
    for item in created:
        state_fps[str(item.get("fingerprint", ""))] = str(item.get("task_id", ""))
    state["fingerprints"] = state_fps
    save_json(state_path, state)

    notify = bool(created)
    if not notify and log_mode == "chat":
        notify = True

    output = "NO_REPLY"
    if notify:
        lines: list[str] = []
        lines.append("# self-evolution-weekly")
        lines.append(f"- sender_identity: {sender_identity}")
        lines.append(f"- task: {args.task_id or '-'}")
        lines.append(f"- time: {now_iso()}")
        lines.append(f"- run_allowed: {run_allowed}")
        lines.append(f"- candidates: {len(candidates)}")
        lines.append(f"- created_todo: {len(created)}")
        lines.append(f"- max_tasks_per_run: {int(args.max_tasks_per_run)}")
        lines.append("- policy: suggestions_only=true, auto_workflow_change=false, human_confirm_required=true")
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

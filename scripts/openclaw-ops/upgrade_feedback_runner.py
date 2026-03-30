#!/usr/bin/env python3
"""Generate upgrade feedback bundles from executor-run reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from skill_evolution_review import build_skill_evolution_review
from workflow_promotion_controller import apply_workflow_promotion
from upgrade_analysis import average_score
from workflow_upgrade_scoring import build_workflow_upgrade_scorecard

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from task_capability_binding import build_task_constraint_fields  # type: ignore
from task_center import TaskCenter  # type: ignore


JSONDict = dict[str, Any]
DEFAULT_BENCHMARK_SUITE_REGISTRY: JSONDict = {
    "schema_version": "2026-03-22",
    "default_suite_id": "coding-default-core",
    "suites": [
        {
            "suite_id": "coding-default-core",
            "display_name": "默认编码工作流核心基准集",
            "workflow_profile_id": "coding-default",
            "baseline_channel": "stable",
            "candidate_channel": "candidate",
            "workflow_target": "task_executor_10m",
            "skill_name": "openclaw-evolution-upgrader",
            "skill_assignee": "optimization-agent",
            "baseline_count": 3,
            "candidate_count": 3,
            "target_kind": "workflow",
            "target_id": "coding-default",
        },
        {
            "suite_id": "research-default-core",
            "display_name": "默认研究工作流核心基准集",
            "workflow_profile_id": "research-default",
            "baseline_channel": "stable",
            "candidate_channel": "candidate",
            "workflow_target": "task_executor_10m",
            "skill_name": "openclaw-evolution-upgrader",
            "skill_assignee": "optimization-agent",
            "baseline_count": 3,
            "candidate_count": 3,
            "target_kind": "workflow",
            "target_id": "research-default",
        },
        {
            "suite_id": "docs-default-core",
            "display_name": "默认文档工作流核心基准集",
            "workflow_profile_id": "docs-default",
            "baseline_channel": "stable",
            "candidate_channel": "candidate",
            "workflow_target": "task_executor_10m",
            "skill_name": "openclaw-evolution-upgrader",
            "skill_assignee": "optimization-agent",
            "baseline_count": 3,
            "candidate_count": 3,
            "target_kind": "workflow",
            "target_id": "docs-default",
        },
        {
            "suite_id": "ops-default-core",
            "display_name": "默认运维工作流核心基准集",
            "workflow_profile_id": "ops-default",
            "baseline_channel": "stable",
            "candidate_channel": "candidate",
            "workflow_target": "task_executor_10m",
            "skill_name": "openclaw-evolution-upgrader",
            "skill_assignee": "optimization-agent",
            "baseline_count": 3,
            "candidate_count": 3,
            "target_kind": "workflow",
            "target_id": "ops-default",
        }
    ],
}


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> JSONDict:
    """Load a UTF-8 JSON object from disk."""

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    payload["__report_path"] = str(path)
    return payload


def _timestamp_sort_key(report: JSONDict) -> tuple[str, str]:
    """Build a stable sort key from report timestamps and run ids."""

    finished_at = str(report.get("finished_at", "")).strip()
    started_at = str(report.get("started_at", "")).strip()
    run_id = str(report.get("run_id", "")).strip()
    return (finished_at or started_at or "", run_id)


def collect_executor_reports(executor_run_dir: Path) -> list[JSONDict]:
    """Load and sort executor-run reports from a directory."""

    if not executor_run_dir.exists():
        raise FileNotFoundError(f"Executor run dir does not exist: {executor_run_dir}")
    reports = [_load_json(path) for path in sorted(executor_run_dir.glob("*.json"))]
    return sorted(reports, key=_timestamp_sort_key)


def select_report_windows(
    reports: list[JSONDict],
    *,
    baseline_count: int,
    candidate_count: int,
) -> tuple[list[JSONDict], list[JSONDict]]:
    """Select baseline and candidate windows from sorted reports."""

    required = max(1, int(baseline_count)) + max(1, int(candidate_count))
    if len(reports) < required:
        raise ValueError(f"Need at least {required} reports, got {len(reports)}.")
    candidate = reports[-max(1, int(candidate_count)) :]
    baseline_end = len(reports) - len(candidate)
    baseline = reports[max(0, baseline_end - max(1, int(baseline_count))) : baseline_end]
    return baseline, candidate


def _load_state(path: Path) -> JSONDict:
    """Load the runner state file when it exists."""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: JSONDict) -> None:
    """Write a JSON object using UTF-8 without BOM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    """Write plain text using UTF-8 without BOM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text), encoding="utf-8")


def load_benchmark_suite_registry(path: Path | None = None) -> JSONDict:
    """Load the benchmark suite registry or fall back to the built-in default."""
    if path is None:
        return json.loads(json.dumps(DEFAULT_BENCHMARK_SUITE_REGISTRY, ensure_ascii=False))
    payload = _load_json(path)
    suites = payload.get("suites", [])
    if not isinstance(suites, list):
        raise ValueError("benchmark suite registry suites must be a list")
    return payload


def resolve_benchmark_suite(
    *,
    registry: JSONDict,
    suite_id: str = "",
) -> JSONDict:
    """Resolve one benchmark suite entry from the registry."""
    wanted_suite_id = str(suite_id or registry.get("default_suite_id", "")).strip()
    if not wanted_suite_id:
        raise ValueError("benchmark suite registry default_suite_id is empty")
    for item in registry.get("suites", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("suite_id", "")).strip() == wanted_suite_id:
            return dict(item)
    raise ValueError(f"benchmark suite not found: {wanted_suite_id}")


def build_inline_benchmark_suite(
    *,
    workflow_target: str,
    skill_name: str,
    skill_assignee: str,
    baseline_count: int,
    candidate_count: int,
) -> JSONDict:
    """Build a temporary benchmark suite from direct CLI arguments."""
    return {
        "suite_id": "ad-hoc-upgrade-feedback",
        "display_name": "临时升级反馈基准集",
        "workflow_profile_id": "coding-default",
        "baseline_channel": "stable",
        "candidate_channel": "candidate",
        "workflow_target": str(workflow_target).strip(),
        "skill_name": str(skill_name).strip(),
        "skill_assignee": str(skill_assignee).strip(),
        "baseline_count": max(1, int(baseline_count)),
        "candidate_count": max(1, int(candidate_count)),
        "target_kind": "workflow",
        "target_id": "coding-default",
    }


def _safe_stamp(candidate_reports: list[JSONDict]) -> str:
    """Build a file-safe timestamp for bundle outputs."""

    tail = candidate_reports[-1] if candidate_reports else {}
    raw = str(tail.get("finished_at") or tail.get("started_at") or _now_iso()).strip()
    cleaned = raw.replace(":", "").replace("-", "").replace("+", "_plus_")
    cleaned = cleaned.replace("T", "_").replace("Z", "_z").replace(".", "_")
    return cleaned or datetime.now().strftime("%Y%m%d_%H%M%S")


def _report_paths(reports: list[JSONDict]) -> list[Path]:
    """Extract source paths from annotated reports."""

    return [Path(str(report["__report_path"])) for report in reports if str(report.get("__report_path", "")).strip()]


def _feedback_fingerprint(*parts: str) -> str:
    """Build a stable fingerprint for one upgrade-feedback task candidate."""

    raw = "\n".join(str(part or "").strip() for part in parts).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def _collect_open_change_ids(task_center: TaskCenter) -> set[str]:
    """Collect open change ids already owned by the upgrade-feedback runner."""

    rows = task_center.conn.execute(
        """
        SELECT change_id
        FROM tasks
        WHERE source = 'upgrade-feedback-runner'
          AND status IN ('pending', 'running', 'failed')
        """
    ).fetchall()
    return {str(row["change_id"] or "").strip() for row in rows if str(row["change_id"] or "").strip()}


def _infer_task_assignee(root_cause_type: str, *, upgrade_kind: str, default_skill_assignee: str) -> str:
    """Map upgrade candidates to a concrete assignee."""

    if root_cause_type == "architecture_gap":
        return "project-agent"
    if root_cause_type == "runtime_gap":
        return "ops-agent"
    if upgrade_kind == "skill":
        return str(default_skill_assignee or "optimization-agent").strip() or "optimization-agent"
    return "optimization-agent"


def _infer_priority(score_average: float) -> str:
    """Map score averages into task priority buckets."""

    if score_average < 60:
        return "high"
    if score_average < 80:
        return "medium"
    return "low"


def _infer_risk_level(root_cause_type: str, score_average: float) -> str:
    """Map upgrade tasks to a risk level."""

    if root_cause_type in {"architecture_gap", "runtime_gap"} or score_average < 60:
        return "high"
    return "low"


def _should_create_task(score: JSONDict, decision: JSONDict, threshold: float) -> bool:
    """Decide whether an upgrade candidate should become a task-center item."""

    score_average = average_score(score)
    low_dimensions = [key for key, value in score.items() if float(value) < float(threshold)]
    return (score_average < float(threshold)) or (not bool(decision.get("promote_to_new_baseline"))) or bool(low_dimensions)


def _build_upgrade_task_payload(
    *,
    candidate_kind: str,
    score: JSONDict,
    classification: JSONDict,
    decision: JSONDict,
    candidate_run_ids: list[str],
    workflow_target: str,
    skill_name: str,
    output_files: JSONDict,
    default_skill_assignee: str,
    schedule_at: str,
) -> JSONDict:
    """Build one task-center payload from an upgrade candidate."""

    if candidate_kind not in {"workflow", "skill"}:
        raise ValueError(f"Unsupported candidate kind: {candidate_kind}")
    target_name = workflow_target if candidate_kind == "workflow" else skill_name
    score_average = average_score(score)
    weak_dimensions = [key for key, value in score.items() if float(value) < 80]
    root_cause_type = str(classification["root_cause_type"]).strip()
    assignee = _infer_task_assignee(
        root_cause_type,
        upgrade_kind=candidate_kind,
        default_skill_assignee=default_skill_assignee,
    )
    fingerprint = _feedback_fingerprint(candidate_kind, target_name, root_cause_type, *candidate_run_ids)
    change_id = f"upgrade-feedback:{candidate_kind}:{fingerprint}"
    constraint_fields = build_task_constraint_fields(assignee)
    title = f"{candidate_kind} 升级跟进：{target_name}"
    requirement_lines = [
        f"[fingerprint:{fingerprint}]",
        f"[change_id:{change_id}]",
        title,
        f"- 根因分类：{root_cause_type}",
        f"- 当前平均分：{score_average:.2f}",
        f"- 弱维度：{', '.join(weak_dimensions) if weak_dimensions else '无'}",
        f"- 候选 run：{', '.join(candidate_run_ids)}",
        f"- 最小可写面：{', '.join(classification['minimal_writable_surface'])}",
        f"- 暂不优先改：{', '.join(classification['avoid_first_changes'])}",
        f"- 参考产物：{output_files['latest_summary']}",
    ]
    result_output = (
        "输出升级实施结果，并回写新的 baseline/candidate 对比证据；"
        "如果只完成部分内容，必须说明剩余风险和下一步。"
    )
    acceptance = (
        "至少完成一个最小可写面改动；"
        "补充验证证据；"
        "再次运行 upgrade feedback 后分数提升或根因收敛。"
    )
    observable_outputs = "task_center记录,workflow scorecard,skill review,upgrade feedback summary"
    acceptance_thresholds = "至少1个弱维度得到提升；不得破坏现有安装链与调度链"
    return {
        "task_id": f"todo-upgrade-feedback-{candidate_kind}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "pool": "todo",
        "task_type": f"{candidate_kind}_upgrade",
        "reason": f"[UPGRADE_FEEDBACK] {title}",
        "source": "upgrade-feedback-runner",
        "request_source": "ai",
        "priority": _infer_priority(score_average),
        "risk_level": _infer_risk_level(root_cause_type, score_average),
        "assignee": assignee,
        **constraint_fields,
        "status": "pending",
        "need_human_confirm": False,
        "human_confirmed": True,
        "change_id": change_id,
        "requirement": "\n".join(requirement_lines),
        "result_output": result_output,
        "acceptance": acceptance,
        "observable_outputs": observable_outputs,
        "acceptance_thresholds": acceptance_thresholds,
        "context_payload": {
            "upgrade_kind": candidate_kind,
            "target_name": target_name,
            "candidate_run_ids": candidate_run_ids,
            "classification": classification,
            "decision": decision,
            "output_files": output_files,
        },
        "scheduled_at": schedule_at,
    }


def create_upgrade_tasks(
    *,
    task_db: Path,
    workflow_scorecard: JSONDict,
    skill_review: JSONDict,
    workflow_target: str,
    skill_name: str,
    skill_assignee: str,
    candidate_run_ids: list[str],
    output_files: JSONDict,
    score_threshold: float,
    schedule_gap_minutes: int,
) -> dict[str, Any]:
    """Create task-center items for workflow/skill upgrade follow-ups when needed."""

    task_center = TaskCenter(task_db)
    task_center.init_schema()
    open_change_ids = _collect_open_change_ids(task_center)
    created: list[JSONDict] = []
    skipped: list[JSONDict] = []
    base_schedule = datetime.now(timezone.utc)

    candidates = [
        ("workflow", workflow_scorecard["candidate_score"], workflow_scorecard["classification"], workflow_scorecard["decision"]),
        ("skill", skill_review["candidate_score"], skill_review["classification"], skill_review["decision"]),
    ]
    try:
        for index, (candidate_kind, score, classification, decision) in enumerate(candidates):
            if not _should_create_task(score, decision, score_threshold):
                skipped.append({"kind": candidate_kind, "reason": "score_above_threshold"})
                continue
            payload = _build_upgrade_task_payload(
                candidate_kind=candidate_kind,
                score=score,
                classification=classification,
                decision=decision,
                candidate_run_ids=candidate_run_ids,
                workflow_target=workflow_target,
                skill_name=skill_name,
                output_files=output_files,
                default_skill_assignee=skill_assignee,
                schedule_at=(base_schedule + timedelta(minutes=int(schedule_gap_minutes) * index)).replace(microsecond=0).isoformat(),
            )
            if str(payload["change_id"]) in open_change_ids:
                skipped.append({"kind": candidate_kind, "reason": "already_open", "change_id": payload["change_id"]})
                continue
            task = task_center.create_task(payload, actor="upgrade-feedback-runner")
            task_center.add_event(
                task_id=task["task_id"],
                actor="upgrade-feedback-runner",
                event_type="upgrade_feedback_task_packaged",
                stage="feedback",
                details={
                    "change_id": payload["change_id"],
                    "candidate_run_ids": candidate_run_ids,
                    "kind": candidate_kind,
                },
            )
            created.append(
                {
                    "task_id": task["task_id"],
                    "task_type": task["task_type"],
                    "assignee": task["assignee"],
                    "change_id": task["change_id"],
                }
            )
            open_change_ids.add(str(payload["change_id"]))
    finally:
        task_center.close()

    return {"created": created, "skipped": skipped}


def _build_summary(
    *,
    baseline_reports: list[JSONDict],
    candidate_reports: list[JSONDict],
    benchmark_suite: JSONDict,
    promotion_bundle: JSONDict,
    workflow_scorecard: JSONDict,
    skill_review: JSONDict,
    output_files: JSONDict,
    created_tasks: list[JSONDict] | None = None,
    skipped_tasks: list[JSONDict] | None = None,
) -> JSONDict:
    """Build the bundle summary payload."""

    return {
        "status": "ok",
        "generated_at": _now_iso(),
        "baseline_run_ids": [str(report.get("run_id", "")).strip() for report in baseline_reports],
        "candidate_run_ids": [str(report.get("run_id", "")).strip() for report in candidate_reports],
        "workflow_root_cause": workflow_scorecard["classification"]["root_cause_type"],
        "skill_root_cause": skill_review["classification"]["root_cause_type"],
        "workflow_promoted": bool(workflow_scorecard["decision"]["promote_to_new_baseline"]),
        "skill_promoted": bool(skill_review["decision"]["promote_to_new_baseline"]),
        "benchmark_suite": benchmark_suite,
        "promotion_bundle": promotion_bundle,
        "output_files": output_files,
        "workflow_scorecard": workflow_scorecard,
        "skill_review": skill_review,
        "created_tasks": list(created_tasks or []),
        "skipped_tasks": list(skipped_tasks or []),
    }


def build_upgrade_feedback_bundle(
    *,
    executor_run_dir: str | Path,
    output_dir: str | Path,
    state_file: str | Path,
    workflow_target: str,
    skill_name: str,
    skill_assignee: str,
    baseline_count: int = 3,
    candidate_count: int = 3,
    task_db: str | Path | None = None,
    auto_create_tasks: bool = False,
    task_score_threshold: float = 80.0,
    task_schedule_gap_minutes: int = 120,
    benchmark_suite_file: str | Path | None = None,
    benchmark_suite_id: str = "",
    workflow_profile_registry: str | Path | None = None,
    auto_apply_workflow_promotion: bool = False,
    promotion_operator: str = "upgrade-feedback-runner",
) -> JSONDict:
    """Build a persisted feedback bundle from executor-run reports.

    Args:
        executor_run_dir: Directory containing executor-run JSON reports.
        output_dir: Directory where summary and rendered outputs will be written.
        state_file: State file used to dedupe repeated candidate windows.
        workflow_target: Workflow target name for the workflow scorecard.
        skill_name: Skill name for the skill review.
        skill_assignee: Assignee filter for the skill review.
        baseline_count: Number of earlier reports used as the baseline window.
        candidate_count: Number of latest reports used as the candidate window.
        task_db: Optional task-center database path used to create follow-up tasks.
        auto_create_tasks: Whether low-score results should create task-center items automatically.
        task_score_threshold: Score threshold below which follow-up tasks should be created.
        task_schedule_gap_minutes: Minutes between generated follow-up tasks.
        benchmark_suite_file: Optional benchmark suite registry JSON file.
        benchmark_suite_id: Optional benchmark suite id. Defaults to registry default.
        workflow_profile_registry: Optional workflow registry file used for auto promotion.
        auto_apply_workflow_promotion: Whether to auto-apply workflow promotion into the registry.
        promotion_operator: Operator name recorded in promotion history.

    Returns:
        A summary dictionary describing the generated bundle or a skipped status.

    Raises:
        FileNotFoundError: If the executor-run directory does not exist.
        ValueError: If there are not enough reports to build both windows.
    """

    run_dir = Path(executor_run_dir).expanduser()
    out_dir = Path(output_dir).expanduser()
    state_path = Path(state_file).expanduser()
    explicit_benchmark_suite = bool(benchmark_suite_file) or bool(str(benchmark_suite_id).strip())
    if explicit_benchmark_suite:
        benchmark_registry = load_benchmark_suite_registry(
            Path(benchmark_suite_file).expanduser() if benchmark_suite_file is not None else None
        )
        benchmark_suite = resolve_benchmark_suite(
            registry=benchmark_registry,
            suite_id=str(benchmark_suite_id).strip(),
        )
        workflow_target = str(benchmark_suite.get("workflow_target", workflow_target) or workflow_target).strip()
        skill_name = str(benchmark_suite.get("skill_name", skill_name) or skill_name).strip()
        skill_assignee = str(benchmark_suite.get("skill_assignee", skill_assignee) or skill_assignee).strip()
        baseline_count = max(1, int(benchmark_suite.get("baseline_count", baseline_count) or baseline_count))
        candidate_count = max(1, int(benchmark_suite.get("candidate_count", candidate_count) or candidate_count))
    else:
        benchmark_suite = build_inline_benchmark_suite(
            workflow_target=workflow_target,
            skill_name=skill_name,
            skill_assignee=skill_assignee,
            baseline_count=baseline_count,
            candidate_count=candidate_count,
        )
    reports = collect_executor_reports(run_dir)
    baseline_reports, candidate_reports = select_report_windows(
        reports,
        baseline_count=baseline_count,
        candidate_count=candidate_count,
    )
    candidate_run_ids = [str(report.get("run_id", "")).strip() for report in candidate_reports]
    existing_state = _load_state(state_path)
    if candidate_run_ids and existing_state.get("last_candidate_run_ids") == candidate_run_ids:
        return {
            "status": "skipped_no_new_candidate_runs",
            "generated_at": _now_iso(),
            "candidate_run_ids": candidate_run_ids,
            "baseline_run_ids": [str(report.get("run_id", "")).strip() for report in baseline_reports],
        }

    workflow_scorecard = build_workflow_upgrade_scorecard(
        baseline_inputs=_report_paths(baseline_reports),
        candidate_inputs=_report_paths(candidate_reports),
        target_name=workflow_target,
    )
    skill_review = build_skill_evolution_review(
        baseline_inputs=_report_paths(baseline_reports),
        candidate_inputs=_report_paths(candidate_reports),
        skill_name=skill_name,
        assignee=skill_assignee,
    )

    stamp = _safe_stamp(candidate_reports)
    out_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = out_dir / f"workflow-scorecard-{stamp}.json"
    skill_file = out_dir / f"skill-review-{stamp}.md"
    summary_file = out_dir / f"upgrade-feedback-{stamp}.json"
    latest_workflow_file = out_dir / "latest-workflow-scorecard.json"
    latest_skill_file = out_dir / "latest-skill-review.md"
    latest_summary_file = out_dir / "latest-summary.json"

    _write_json(workflow_file, workflow_scorecard)
    _write_json(latest_workflow_file, workflow_scorecard)
    _write_text(skill_file, skill_review["markdown"])
    _write_text(latest_skill_file, skill_review["markdown"])

    output_files = {
        "workflow_scorecard": str(workflow_file),
        "skill_review": str(skill_file),
        "summary": str(summary_file),
        "latest_workflow_scorecard": str(latest_workflow_file),
        "latest_skill_review": str(latest_skill_file),
        "latest_summary": str(latest_summary_file),
    }
    promotion_bundle = {
        "bundle_id": f"promotion-bundle-{stamp}",
        "target_kind": str(benchmark_suite.get("target_kind", "workflow") or "workflow").strip(),
        "target_id": str(benchmark_suite.get("target_id", benchmark_suite.get("workflow_profile_id", workflow_target)) or workflow_target).strip(),
        "baseline_version": f"{benchmark_suite.get('workflow_profile_id', 'coding-default')}@{benchmark_suite.get('baseline_channel', 'stable')}",
        "candidate_version": f"{benchmark_suite.get('workflow_profile_id', 'coding-default')}@{benchmark_suite.get('candidate_channel', 'candidate')}",
        "benchmark_suite_id": str(benchmark_suite.get("suite_id", "")).strip(),
        "baseline_score": dict(workflow_scorecard["baseline_score"]),
        "candidate_score": dict(workflow_scorecard["candidate_score"]),
        "delta": dict(workflow_scorecard["delta"]),
        "top_regressions": list(workflow_scorecard.get("top_regressions", [])),
        "top_improvements": list(workflow_scorecard.get("top_improvements", [])),
        "promotion_decision": dict(workflow_scorecard.get("decision", {})),
        "rollback_plan": {
            "registry_channel": str(benchmark_suite.get("baseline_channel", "stable")).strip() or "stable",
            "candidate_channel": str(benchmark_suite.get("candidate_channel", "candidate")).strip() or "candidate",
        },
        "baseline_run_ids": list(str(report.get("run_id", "")).strip() for report in baseline_reports if str(report.get("run_id", "")).strip()),
        "candidate_run_ids": candidate_run_ids,
    }
    task_summary = {"created": [], "skipped": []}
    if auto_create_tasks:
        if task_db is None:
            task_summary["skipped"].append({"kind": "all", "reason": "task_db_missing"})
        else:
            task_summary = create_upgrade_tasks(
                task_db=Path(task_db).expanduser(),
                workflow_scorecard=workflow_scorecard,
                skill_review=skill_review,
                workflow_target=workflow_target,
                skill_name=skill_name,
                skill_assignee=skill_assignee,
                candidate_run_ids=candidate_run_ids,
                output_files=output_files,
                score_threshold=float(task_score_threshold),
                schedule_gap_minutes=max(1, int(task_schedule_gap_minutes)),
            )
    summary = _build_summary(
        baseline_reports=baseline_reports,
        candidate_reports=candidate_reports,
        benchmark_suite=benchmark_suite,
        promotion_bundle=promotion_bundle,
        workflow_scorecard=workflow_scorecard,
        skill_review=skill_review,
        output_files=output_files,
        created_tasks=task_summary["created"],
        skipped_tasks=task_summary["skipped"],
    )
    workflow_registry_promotion: JSONDict = {
        "status": "skipped_auto_apply_disabled",
        "profile_id": str(benchmark_suite.get("workflow_profile_id", "coding-default")).strip() or "coding-default",
    }
    benchmark_run_record: JSONDict = {"status": "skipped_task_db_missing"}
    if task_db is not None:
        task_center = TaskCenter(Path(task_db).expanduser())
        try:
            task_center.init_schema()
            benchmark_run_record = task_center.record_benchmark_run(
                benchmark_run_id=f"benchmark-run-{stamp}",
                task_id="",
                benchmark_suite_id=str(benchmark_suite.get("suite_id", "")).strip(),
                workflow_profile_id=str(benchmark_suite.get("workflow_profile_id", "")).strip(),
                workflow_channel=str(benchmark_suite.get("candidate_channel", "")).strip(),
                target_kind=str(promotion_bundle["target_kind"]).strip(),
                target_id=str(promotion_bundle["target_id"]).strip(),
                baseline_run_ids=promotion_bundle["baseline_run_ids"],
                candidate_run_ids=promotion_bundle["candidate_run_ids"],
                summary_file=str(summary_file),
                scorecard_file=str(workflow_file),
                decision=dict(promotion_bundle["promotion_decision"]),
                details={
                    "workflow_target": workflow_target,
                    "skill_name": skill_name,
                    "output_files": output_files,
                },
                actor="upgrade-feedback-runner",
            )
        finally:
            task_center.close()
    summary["benchmark_run"] = benchmark_run_record
    _write_json(summary_file, summary)
    _write_json(latest_summary_file, summary)
    if auto_apply_workflow_promotion:
        if workflow_profile_registry is None:
            workflow_registry_promotion = {
                "status": "skipped_registry_missing",
                "profile_id": str(benchmark_suite.get("workflow_profile_id", "coding-default")).strip() or "coding-default",
            }
        elif not bool(workflow_scorecard.get("decision", {}).get("promote_to_new_baseline")):
            workflow_registry_promotion = {
                "status": "skipped_not_promoted",
                "profile_id": str(benchmark_suite.get("workflow_profile_id", "coding-default")).strip() or "coding-default",
            }
        else:
            workflow_registry_promotion = apply_workflow_promotion(
                registry_file=Path(workflow_profile_registry).expanduser(),
                summary_file=latest_summary_file,
                profile_id=str(benchmark_suite.get("workflow_profile_id", "coding-default")).strip() or "coding-default",
                stable_channel=str(benchmark_suite.get("baseline_channel", "stable")).strip() or "stable",
                candidate_channel=str(benchmark_suite.get("candidate_channel", "candidate")).strip() or "candidate",
                operator=str(promotion_operator or "").strip() or "upgrade-feedback-runner",
            )
    summary["workflow_registry_promotion"] = workflow_registry_promotion
    _write_json(summary_file, summary)
    _write_json(latest_summary_file, summary)
    _write_json(
        state_path,
        {
            "last_generated_at": summary["generated_at"],
            "last_candidate_run_ids": candidate_run_ids,
            "latest_summary_file": str(summary_file),
            "last_created_task_ids": [str(item.get("task_id", "")).strip() for item in task_summary["created"]],
            "last_workflow_registry_promotion_status": str(workflow_registry_promotion.get("status", "")).strip(),
            "last_benchmark_suite_id": str(benchmark_suite.get("suite_id", "")).strip(),
            "last_benchmark_run_id": str(benchmark_run_record.get("benchmark_run_id", "")).strip(),
        },
    )
    return summary


def main() -> int:
    """Run the upgrade feedback bundle builder as a CLI tool."""

    home = Path.home()
    parser = argparse.ArgumentParser(description="Build upgrade feedback bundles from executor reports.")
    parser.add_argument("--executor-run-dir", default=str(home / ".openclaw/ops/task-center/executor-runs"))
    parser.add_argument("--output-dir", default=str(home / ".openclaw/ops/upgrade-feedback/reports"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/upgrade-feedback/state.json"))
    parser.add_argument("--workflow-target", default="task_executor_10m")
    parser.add_argument("--skill-name", default="openclaw-evolution-upgrader")
    parser.add_argument("--skill-assignee", default="optimization-agent")
    parser.add_argument("--baseline-count", type=int, default=3)
    parser.add_argument("--candidate-count", type=int, default=3)
    parser.add_argument("--task-db", default="")
    parser.add_argument("--auto-create-tasks", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--task-score-threshold", type=float, default=80.0)
    parser.add_argument("--task-schedule-gap-minutes", type=int, default=120)
    parser.add_argument("--benchmark-suite-file", default="")
    parser.add_argument("--benchmark-suite-id", default="")
    parser.add_argument("--workflow-profile-registry", default="")
    parser.add_argument("--auto-apply-workflow-promotion", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--promotion-operator", default="upgrade-feedback-runner")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    result = build_upgrade_feedback_bundle(
        executor_run_dir=args.executor_run_dir,
        output_dir=args.output_dir,
        state_file=args.state_file,
        workflow_target=str(args.workflow_target).strip(),
        skill_name=str(args.skill_name).strip(),
        skill_assignee=str(args.skill_assignee).strip(),
        baseline_count=max(1, int(args.baseline_count)),
        candidate_count=max(1, int(args.candidate_count)),
        task_db=(str(args.task_db).strip() or None),
        auto_create_tasks=bool(args.auto_create_tasks),
        task_score_threshold=float(args.task_score_threshold),
        task_schedule_gap_minutes=max(1, int(args.task_schedule_gap_minutes)),
        benchmark_suite_file=(str(args.benchmark_suite_file).strip() or None),
        benchmark_suite_id=str(args.benchmark_suite_id).strip(),
        workflow_profile_registry=(str(args.workflow_profile_registry).strip() or None),
        auto_apply_workflow_promotion=bool(args.auto_apply_workflow_promotion),
        promotion_operator=str(args.promotion_operator).strip() or "upgrade-feedback-runner",
    )
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 精简人类可读摘要（用于 Telegram 通知）
        status = str(result.get("status", "unknown"))
        promo = result.get("promotion_bundle", {})
        decision = promo.get("promotion_decision", {}) if isinstance(promo, dict) else {}
        baseline_avg = decision.get("baseline_average", 0) if isinstance(decision, dict) else 0
        candidate_avg = decision.get("candidate_average", 0) if isinstance(decision, dict) else 0
        promoted = bool(decision.get("promote_to_new_baseline", False)) if isinstance(decision, dict) else False
        veto = decision.get("veto_reasons", []) if isinstance(decision, dict) else []
        lines = [
            f"升级反馈：{status}",
            f"基线均分：{baseline_avg:.1f} | 候选均分：{candidate_avg:.1f}",
            f"晋升决策：{'✅ 已晋升' if promoted else '❌ 未晋升'}",
        ]
        if veto and isinstance(veto, list):
            lines.append(f"否决原因：{', '.join(str(v) for v in veto[:3])}")
        reg_status = str(result.get("workflow_registry_promotion", {}).get("status", "")).strip()
        if reg_status:
            lines.append(f"注册表：{reg_status}")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

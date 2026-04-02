#!/usr/bin/env python3
"""Shared helpers for workflow and skill upgrade analysis."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


JSONDict = dict[str, Any]
RUNTIME_KEYWORDS = (
    "call_agent_exception",
    "gateway",
    "timeout",
    "preflight_strict_blocked",
    "manifest",
    "auth",
    "oauth",
    "report_failed",
    "pre_stage_failed",
    "connect failed",
    "handshake",
    "refresh_token",
)
CLARIFICATION_KEYWORDS = ("waiting_human_confirm", "need_human_confirm", "clarify", "confirm")
VERIFICATION_KEYWORDS = ("验证", "验收", "复跑", "测试", "对比", "check", "verify", "evidence", "proof")
BOUNDARY_KEYWORDS = ("边界", "越界", "boundary")
INCOMPLETE_KEYWORDS = ("缺少", "不足", "不完整", "incomplete", "missing")

ROOT_CAUSE_SURFACES: dict[str, list[str]] = {
    "runtime_gap": [
        "scripts/openclaw-ops/install_workflow_profile.py",
        "scripts/openclaw-ops/install_task_executor_job.py",
        "scripts/openclaw-ops/policy/task_executor_runner.py",
        "cron/jobs.json",
    ],
    "workflow_gap": [
        "cron/jobs.json",
        "scripts/openclaw-ops/cron_setup.py",
        "scripts/openclaw-ops/governance_evolution_runner.py",
        "scripts/openclaw-ops/policy/task_executor_runner.py",
    ],
    "skill_gap": [
        "skills/library/{skill_name}/SKILL.md",
        "skills/library/{skill_name}/references/internal-feedback-upgrade.md",
        "skills/index/skill_to_agents.json",
    ],
    "architecture_gap": [
        "docs/plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md",
        "skills/library/openclaw-workflow-manager/references/workflow-map.md",
        "scripts/openclaw-ops/generate_runtime_binding_manifests.py",
        "agents/agent_capability_manifest.json",
    ],
}
ROOT_CAUSE_AVOID_FIRST: dict[str, list[str]] = {
    "runtime_gap": [
        "~/.openclaw/* 运行态现值",
        "单次任务 prompt 的临时补丁",
    ],
    "workflow_gap": [
        "只改某个 agent 的临时提示词",
        "跳过 task-center / executor 现有链路",
    ],
    "skill_gap": [
        "直接手改 runtime 结果文件",
        "把规范留在一次性对话里而不写回 skill",
    ],
    "architecture_gap": [
        "先堆更多 runner",
        "先把复杂逻辑塞进 runtime overlay",
    ],
}


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Return a safe division result in the range [0, 1] when possible."""

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _clamp_score(value: float) -> int:
    """Clamp a floating-point score to an integer between 0 and 100."""

    return max(0, min(100, int(round(value))))


def _normalize_text(value: Any) -> str:
    """Normalize arbitrary values into trimmed lowercase text."""

    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    """Check whether any keyword appears in the normalized text."""

    return any(keyword in text for keyword in keywords)


def _normalize_result_status(result: JSONDict) -> str:
    """Derive a stable terminal status for an executor result record."""

    reason_text = " ".join(
        [
            _normalize_text(result.get("reason")),
            _normalize_text(result.get("resolution_summary")),
        ]
    )
    if "preflight_strict_blocked" in reason_text:
        return "blocked"

    if bool(result.get("solved")):
        return "passed"

    for key in ("task_status_after", "report_status", "status"):
        text = _normalize_text(result.get(key))
        if text in {"passed", "solved", "completed"}:
            return "passed"
        if text in {"partial"}:
            return "partial"
        if text in {"failed", "error"}:
            return "failed"
        if text in {"waiting_human_confirm", "waiting_human"}:
            return "waiting_human"
    return "unknown"


def read_json_file(path: Path) -> JSONDict:
    """Read a UTF-8 JSON file and annotate the payload with its source path."""

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    payload["__report_path"] = str(path)
    return payload


def expand_report_inputs(inputs: Sequence[str | Path]) -> list[Path]:
    """Expand report inputs from files or directories into a sorted file list."""

    report_paths: list[Path] = []
    for raw_item in inputs:
        path = Path(raw_item).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Report input does not exist: {path}")
        if path.is_dir():
            report_paths.extend(sorted(item for item in path.rglob("*.json") if item.is_file()))
            continue
        report_paths.append(path)

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in report_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    if not unique_paths:
        raise ValueError("At least one JSON report input is required.")
    return sorted(unique_paths, key=lambda item: str(item))


def load_reports(inputs: Sequence[str | Path]) -> list[JSONDict]:
    """Load and validate executor-style JSON reports from the given inputs."""

    return [read_json_file(path) for path in expand_report_inputs(inputs)]


def build_window(reports: Sequence[JSONDict]) -> JSONDict:
    """Build a time window summary from the earliest and latest report timestamps."""

    timestamps: list[datetime] = []
    for report in reports:
        for key in ("started_at", "finished_at"):
            raw_value = str(report.get(key, "")).strip()
            if not raw_value:
                continue
            normalized = raw_value.replace("Z", "+00:00")
            try:
                timestamps.append(datetime.fromisoformat(normalized))
            except ValueError:
                continue

    if not timestamps:
        return {"start": "", "end": ""}
    timestamps.sort()
    return {
        "start": timestamps[0].replace(microsecond=0).isoformat(),
        "end": timestamps[-1].replace(microsecond=0).isoformat(),
    }


def _extract_filtered_results(reports: Sequence[JSONDict], *, assignee: str) -> tuple[list[JSONDict], JSONDict]:
    """Collect report-level counters and filtered result rows."""

    filtered_results: list[JSONDict] = []
    preflight_warning_tasks = 0
    preflight_blocked_tasks = 0
    tasks_selected = 0
    tasks_executed = 0
    tasks_skipped = 0
    tasks_failed = 0
    assignee_filter = assignee.strip()

    for report in reports:
        if not assignee_filter:
            tasks_selected += int(report.get("tasks_selected", 0) or 0)
            tasks_executed += int(report.get("tasks_executed", 0) or 0)
            tasks_skipped += int(report.get("tasks_skipped", 0) or 0)
            tasks_failed += int(report.get("tasks_failed", 0) or 0)
            preflight_warning_tasks += int(report.get("preflight_warning_tasks", 0) or 0)
            preflight_blocked_tasks += int(report.get("preflight_blocked_tasks", 0) or 0)

        for item in report.get("results", []):
            if not isinstance(item, dict):
                continue
            if assignee_filter and str(item.get("assignee", "")).strip() != assignee_filter:
                continue
            filtered_results.append(item)
            if assignee_filter:
                tasks_selected += 1
                status_text = " ".join(
                    [
                        _normalize_text(item.get("status")),
                        _normalize_text(item.get("task_status_after")),
                        _normalize_text(item.get("report_status")),
                    ]
                )
                reason_text = _normalize_text(item.get("reason"))
                if "skipped" in status_text:
                    tasks_skipped += 1
                else:
                    tasks_executed += 1
                if any(marker in status_text for marker in ("failed", "partial")):
                    tasks_failed += 1
                if "preflight" in reason_text:
                    preflight_warning_tasks += 1
                if "preflight_strict_blocked" in reason_text:
                    preflight_blocked_tasks += 1

    return filtered_results, {
        "tasks_selected": tasks_selected,
        "tasks_executed": tasks_executed,
        "tasks_skipped": tasks_skipped,
        "tasks_failed": tasks_failed,
        "preflight_warning_tasks": preflight_warning_tasks,
        "preflight_blocked_tasks": preflight_blocked_tasks,
    }


def _record_result_metrics(result: JSONDict, counters: JSONDict) -> None:
    """Update aggregation counters with one normalized result record."""

    status = _normalize_result_status(result)
    counters["status_counter"][status] += 1
    counters["assignee_counter"][str(result.get("assignee", "")).strip()] += 1
    counters["task_type_counter"][str(result.get("task_type", "")).strip()] += 1

    reason = _normalize_text(result.get("reason"))
    summary = str(result.get("resolution_summary", "")).strip()
    summary_normalized = _normalize_text(summary)
    reason_text = " ".join([reason, summary_normalized, _normalize_text(status)])
    stage_contract = result.get("stage_contract", {})
    stage_contract_failed = isinstance(stage_contract, dict) and (not bool(stage_contract.get("contract_passed", True)))
    standard_output = result.get("standard_output", {})
    if not isinstance(standard_output, dict):
        standard_output = {}
    human_gate = result.get("human_gate", {})
    if not isinstance(human_gate, dict):
        human_gate = standard_output.get("human_gate", {}) if isinstance(standard_output.get("human_gate", {}), dict) else {}
    incident = result.get("incident", {})
    if not isinstance(incident, dict):
        incident = {}

    quality = float(result.get("quality_score", 0) or 0)
    counters["quality_scores"].append(quality)
    if summary and (
        int(result.get("duration_ms", 0) or 0) > 0
        or int(result.get("input_tokens", 0) or 0) > 0
        or int(result.get("output_tokens", 0) or 0) > 0
    ):
        counters["documented_result_count"] += 1
    clarification_signal = status == "waiting_human" or _contains_any(reason_text, CLARIFICATION_KEYWORDS) or bool(human_gate.get("needs_clarification", False))
    waiting_human_signal = status == "waiting_human" or (
        bool(human_gate.get("need_human_confirm", False)) and (not bool(human_gate.get("human_confirmed", False)))
    )
    if clarification_signal:
        counters["clarification_count"] += 1
    if waiting_human_signal:
        counters["waiting_human_count"] += 1
    if bool(human_gate.get("requires_human_assistance", False)):
        counters["human_assistance_count"] += 1
    if _contains_any(reason_text, RUNTIME_KEYWORDS):
        counters["runtime_failure_count"] += 1
    if _contains_any(reason_text, BOUNDARY_KEYWORDS):
        counters["boundary_issue_count"] += 1
    if _contains_any(reason_text, INCOMPLETE_KEYWORDS):
        counters["incomplete_output_count"] += 1
    if incident:
        counters["incident_count"] += 1
        incident_status = _normalize_text(incident.get("status"))
        if incident_status not in {"resolved", "suppressed"}:
            counters["open_incident_count"] += 1
            if _normalize_text(incident.get("severity")) == "critical":
                counters["critical_incident_count"] += 1
    if stage_contract_failed or "stage_contract_failed" in reason_text:
        counters["stage_contract_failure_count"] += 1
        if not _contains_any(reason_text, INCOMPLETE_KEYWORDS):
            counters["incomplete_output_count"] += 1
    if status == "passed" and (_contains_any(summary_normalized, VERIFICATION_KEYWORDS) or bool(result.get("solved"))):
        counters["verification_success_count"] += 1
    if status in {"failed", "partial", "blocked", "waiting_human"}:
        reason_key = reason or status
        if stage_contract_failed and reason_key == status:
            reason_key = "stage_contract_failed"
        counters["failure_reason_counter"][reason_key] += 1


def _build_empty_result_counters() -> JSONDict:
    """Create mutable counters used during result aggregation."""

    return {
        "status_counter": Counter(),
        "failure_reason_counter": Counter(),
        "assignee_counter": Counter(),
        "task_type_counter": Counter(),
        "documented_result_count": 0,
        "verification_success_count": 0,
        "boundary_issue_count": 0,
        "incomplete_output_count": 0,
        "runtime_failure_count": 0,
        "stage_contract_failure_count": 0,
        "clarification_count": 0,
        "waiting_human_count": 0,
        "human_assistance_count": 0,
        "incident_count": 0,
        "open_incident_count": 0,
        "critical_incident_count": 0,
        "quality_scores": [],
    }


def analyze_reports(reports: Sequence[JSONDict], *, assignee: str = "") -> JSONDict:
    """Aggregate executor reports into upgrade-focused metrics."""

    report_paths = [str(report.get("__report_path", "")) for report in reports]
    filtered_results, report_totals = _extract_filtered_results(reports, assignee=assignee)
    counters = _build_empty_result_counters()
    for result in filtered_results:
        _record_result_metrics(result, counters)

    result_count = len(filtered_results)
    status_counter: Counter[str] = Counter()
    status_counter.update(counters["status_counter"])
    repeated_failure_count = sum(max(count - 1, 0) for count in counters["failure_reason_counter"].values())
    passed_count = status_counter.get("passed", 0)
    partial_count = status_counter.get("partial", 0)
    failed_count = status_counter.get("failed", 0)
    blocked_count = status_counter.get("blocked", 0)
    solved_count = sum(1 for item in filtered_results if bool(item.get("solved")))
    quality_scores = counters["quality_scores"]
    avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    failure_density = _safe_ratio(
        failed_count + partial_count + blocked_count + counters["waiting_human_count"],
        result_count,
    )

    return {
        "report_count": len(reports),
        "report_paths": report_paths,
        "run_ids": [str(report.get("run_id", "")).strip() for report in reports if str(report.get("run_id", "")).strip()],
        "result_count": result_count,
        "tasks_selected": report_totals["tasks_selected"],
        "tasks_executed": report_totals["tasks_executed"],
        "tasks_skipped": report_totals["tasks_skipped"],
        "tasks_failed": report_totals["tasks_failed"],
        "preflight_warning_tasks": report_totals["preflight_warning_tasks"],
        "preflight_blocked_tasks": report_totals["preflight_blocked_tasks"],
        "passed_count": passed_count,
        "partial_count": partial_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "solved_count": solved_count,
        "clarification_count": counters["clarification_count"],
        "waiting_human_count": counters["waiting_human_count"],
        "human_assistance_count": counters["human_assistance_count"],
        "incident_count": counters["incident_count"],
        "open_incident_count": counters["open_incident_count"],
        "critical_incident_count": counters["critical_incident_count"],
        "runtime_failure_count": counters["runtime_failure_count"],
        "stage_contract_failure_count": counters["stage_contract_failure_count"],
        "documented_result_count": counters["documented_result_count"],
        "verification_success_count": counters["verification_success_count"],
        "boundary_issue_count": counters["boundary_issue_count"],
        "incomplete_output_count": counters["incomplete_output_count"],
        "repeated_failure_count": repeated_failure_count,
        "avg_quality_score": avg_quality_score,
        "status_counter": dict(status_counter),
        "failure_reason_counter": dict(counters["failure_reason_counter"]),
        "assignee_counter": dict(counters["assignee_counter"]),
        "task_type_counter": dict(counters["task_type_counter"]),
        "failing_assignee_count": sum(
            1 for _, count in counters["assignee_counter"].items() if count > 0 and failure_density > 0
        ),
        "failing_task_type_count": sum(
            1 for _, count in counters["task_type_counter"].items() if count > 0 and failure_density > 0
        ),
        "pass_rate": _safe_ratio(passed_count, result_count),
        "solved_rate": _safe_ratio(solved_count, result_count),
        "failure_density": failure_density,
        "documentation_ratio": _safe_ratio(counters["documented_result_count"], result_count),
        "runtime_failure_rate": _safe_ratio(
            counters["runtime_failure_count"] + report_totals["preflight_blocked_tasks"],
            max(result_count, report_totals["tasks_selected"]),
        ),
        "preflight_warning_rate": _safe_ratio(
            report_totals["preflight_warning_tasks"],
            max(result_count, report_totals["tasks_selected"]),
        ),
        "preflight_blocked_rate": _safe_ratio(
            report_totals["preflight_blocked_tasks"],
            max(result_count, report_totals["tasks_selected"]),
        ),
        "verification_success_rate": _safe_ratio(counters["verification_success_count"], result_count),
        "boundary_issue_rate": _safe_ratio(counters["boundary_issue_count"], result_count),
        "incomplete_output_rate": _safe_ratio(counters["incomplete_output_count"], result_count),
        "human_assistance_rate": _safe_ratio(counters["human_assistance_count"], result_count),
        "incident_rate": _safe_ratio(counters["incident_count"], result_count),
        "open_incident_rate": _safe_ratio(counters["open_incident_count"], result_count),
        "critical_incident_rate": _safe_ratio(counters["critical_incident_count"], result_count),
        "clarification_rate": _safe_ratio(
            counters["clarification_count"] + counters["waiting_human_count"],
            result_count,
        ),
    }


def score_workflow_metrics(metrics: JSONDict) -> JSONDict:
    """Convert aggregated workflow metrics into a stable scorecard."""

    avg_quality = float(metrics["avg_quality_score"])
    pass_rate = float(metrics["pass_rate"])
    solved_rate = float(metrics["solved_rate"])
    failure_density = float(metrics["failure_density"])
    documentation_ratio = float(metrics["documentation_ratio"])
    runtime_failure_rate = float(metrics["runtime_failure_rate"])
    clarification_rate = float(metrics["clarification_rate"])
    human_assistance_rate = float(metrics.get("human_assistance_rate", 0.0) or 0.0)
    open_incident_rate = float(metrics.get("open_incident_rate", 0.0) or 0.0)
    critical_incident_rate = float(metrics.get("critical_incident_rate", 0.0) or 0.0)
    assignee_sprawl = max(0, len(metrics["assignee_counter"]) - 1)
    task_type_sprawl = max(0, len(metrics["task_type_counter"]) - 1)
    locality_penalty = min(1.0, (assignee_sprawl + task_type_sprawl) / 8.0)

    return {
        "structure_clarity": _clamp_score(
            avg_quality * 0.4
            + documentation_ratio * 20
            + (1 - clarification_rate) * 15
            + (1 - human_assistance_rate) * 10
            + (1 - locality_penalty) * 15
        ),
        "change_locality": _clamp_score(
            avg_quality * 0.2
            + (1 - locality_penalty) * 55
            + documentation_ratio * 15
            + (1 - runtime_failure_rate) * 10
        ),
        "execution_stability": _clamp_score(
            (1 - failure_density) * 45
            + pass_rate * 20
            + (1 - runtime_failure_rate) * 15
            + (1 - open_incident_rate) * 10
            + (1 - critical_incident_rate) * 10
        ),
        "closure_rate": _clamp_score(solved_rate * 70 + pass_rate * 30),
        "evidence_quality": _clamp_score(
            avg_quality * 0.5
            + documentation_ratio * 25
            + float(metrics["verification_success_rate"]) * 20
            + (1 - open_incident_rate) * 5
        ),
        "runtime_drift_control": _clamp_score(
            (1 - runtime_failure_rate) * 50
            + (1 - float(metrics["preflight_blocked_rate"])) * 15
            + documentation_ratio * 10
            + (1 - open_incident_rate) * 15
            + (1 - human_assistance_rate) * 10
        ),
        "reuse_value": _clamp_score(
            avg_quality * 0.35 + solved_rate * 25 + documentation_ratio * 20 + (1 - failure_density) * 20
        ),
    }


def score_skill_metrics(metrics: JSONDict) -> JSONDict:
    """Convert aggregated skill-oriented metrics into a stable scorecard."""

    avg_quality = float(metrics["avg_quality_score"])
    pass_rate = float(metrics["pass_rate"])
    solved_rate = float(metrics["solved_rate"])
    failure_density = float(metrics["failure_density"])
    clarification_rate = float(metrics["clarification_rate"])
    verification_success_rate = float(metrics["verification_success_rate"])
    boundary_issue_rate = float(metrics["boundary_issue_rate"])
    incomplete_output_rate = float(metrics["incomplete_output_rate"])
    documentation_ratio = float(metrics["documentation_ratio"])

    return {
        "trigger_precision": _clamp_score(
            avg_quality * 0.3 + (1 - clarification_rate) * 35 + pass_rate * 20 + solved_rate * 15
        ),
        "instruction_clarity": _clamp_score(
            avg_quality * 0.45 + pass_rate * 25 + (1 - incomplete_output_rate) * 15 + (1 - failure_density) * 15
        ),
        "boundary_clarity": _clamp_score(
            avg_quality * 0.35 + pass_rate * 20 + (1 - boundary_issue_rate) * 25 + (1 - failure_density) * 20
        ),
        "verification_discipline": _clamp_score(
            documentation_ratio * 30 + verification_success_rate * 35 + pass_rate * 20 + avg_quality * 0.15
        ),
        "failure_reduction": _clamp_score((1 - failure_density) * 60 + solved_rate * 25 + pass_rate * 15),
        "operational_reuse": _clamp_score(
            avg_quality * 0.4 + solved_rate * 25 + documentation_ratio * 20 + (1 - clarification_rate) * 15
        ),
    }


def compute_delta(baseline_score: JSONDict, candidate_score: JSONDict) -> JSONDict:
    """Compute score deltas between a candidate and its baseline."""

    return {
        key: int(candidate_score.get(key, 0)) - int(baseline_score.get(key, 0))
        for key in baseline_score
    }


def average_score(score: JSONDict) -> float:
    """Return the arithmetic mean of a score dictionary."""

    values = [float(value) for value in score.values()]
    if not values:
        return 0.0
    return sum(values) / len(values)


def classify_root_cause(
    metrics: JSONDict,
    *,
    preferred_kind: str,
    skill_name: str = "",
) -> JSONDict:
    """Classify the dominant upgrade surface from baseline metrics."""

    if metrics["runtime_failure_count"] > 0 or metrics["preflight_blocked_tasks"] > 0:
        root_cause_type = "runtime_gap"
    elif preferred_kind == "skill" and (
        metrics["repeated_failure_count"] > 0 or metrics["avg_quality_score"] < 75 or metrics["incomplete_output_count"] > 0
    ):
        root_cause_type = "skill_gap"
    elif metrics["clarification_count"] > 0 or metrics["tasks_skipped"] > 0:
        root_cause_type = "workflow_gap"
    elif len(metrics["task_type_counter"]) >= 4 and len(metrics["assignee_counter"]) >= 3:
        root_cause_type = "architecture_gap"
    elif preferred_kind == "skill":
        root_cause_type = "skill_gap"
    else:
        root_cause_type = "workflow_gap"

    root_cause_summary = build_root_cause_summary(root_cause_type, metrics, skill_name=skill_name)
    minimal_writable_surface = [
        item.format(skill_name=skill_name or "target-skill")
        for item in ROOT_CAUSE_SURFACES[root_cause_type]
    ]
    return {
        "root_cause_type": root_cause_type,
        "root_cause_summary": root_cause_summary,
        "minimal_writable_surface": minimal_writable_surface,
        "avoid_first_changes": ROOT_CAUSE_AVOID_FIRST[root_cause_type],
    }


def build_root_cause_summary(root_cause_type: str, metrics: JSONDict, *, skill_name: str = "") -> str:
    """Render a concise Chinese summary for the detected root cause."""

    if root_cause_type == "runtime_gap":
        return (
            f"基线样本出现 {metrics['runtime_failure_count']} 次 runtime/preflight 异常，"
            f"并伴随 {metrics['preflight_blocked_tasks']} 次 preflight block，优先修安装态、manifest 与执行链路。"
        )
    if root_cause_type == "skill_gap":
        target = skill_name or "目标技能"
        if int(metrics.get("stage_contract_failure_count", 0) or 0) > 0:
            return (
                f"{target} 在基线样本里出现 {metrics['stage_contract_failure_count']} 次 stage contract 失败，"
                f"并伴随平均质量分 {metrics['avg_quality_score']:.1f}，优先补交付物与验证证据。"
            )
        return (
            f"{target} 对同类任务的指引仍不稳定，基线样本存在 {metrics['repeated_failure_count']} 次重复失败，"
            f"且平均质量分只有 {metrics['avg_quality_score']:.1f}。"
        )
    if root_cause_type == "workflow_gap":
        return (
            f"基线样本存在 {metrics['tasks_skipped']} 个 skipped / {metrics['clarification_count']} 个 clarification 信号，"
            "说明 job 触发、依赖顺序或回写流程仍需收口。"
        )
    return (
        "问题已跨越多个 agent、task type 与安装边界，说明需要先收口 SSOT、manifest 和装配关系，再调整局部 runner。"
    )


def build_dimension_insights(
    baseline_score: JSONDict,
    candidate_score: JSONDict,
    delta: JSONDict,
) -> tuple[list[JSONDict], list[JSONDict]]:
    """Generate top improvements and regressions from score deltas."""

    ranking = sorted(delta.items(), key=lambda item: item[1], reverse=True)
    top_improvements = [
        {
            "dimension": key,
            "baseline": int(baseline_score[key]),
            "candidate": int(candidate_score[key]),
            "delta": int(value),
            "summary": f"{key} 从 {baseline_score[key]} 提升到 {candidate_score[key]}。",
        }
        for key, value in ranking[:3]
    ]
    weakest = sorted(delta.items(), key=lambda item: item[1])[:2]
    top_regressions = [
        {
            "dimension": key,
            "baseline": int(baseline_score[key]),
            "candidate": int(candidate_score[key]),
            "delta": int(value),
            "summary": (
                f"{key} 下降 {abs(int(value))} 分，需要继续观察。"
                if int(value) < 0
                else f"{key} 仅提升 {int(value)} 分，仍是本轮最弱维度之一。"
            ),
        }
        for key, value in weakest
    ]
    return top_improvements, top_regressions


def build_promotion_decision(
    *,
    baseline_score: JSONDict,
    candidate_score: JSONDict,
    delta: JSONDict,
    classification: JSONDict,
    baseline_metrics: JSONDict | None = None,
    candidate_metrics: JSONDict | None = None,
) -> JSONDict:
    """Decide whether the candidate should become the new baseline."""

    baseline_average = average_score(baseline_score)
    candidate_average = average_score(candidate_score)
    positive_deltas = sum(1 for value in delta.values() if int(value) > 0)
    hard_regressions = [key for key, value in delta.items() if int(value) <= -8]
    veto_reasons: list[str] = []
    baseline_metrics = baseline_metrics if isinstance(baseline_metrics, dict) else {}
    candidate_metrics = candidate_metrics if isinstance(candidate_metrics, dict) else {}
    if int(candidate_metrics.get("critical_incident_count", 0) or 0) > 0:
        veto_reasons.append("critical_incidents_present")
    if int(candidate_metrics.get("open_incident_count", 0) or 0) > int(baseline_metrics.get("open_incident_count", 0) or 0):
        veto_reasons.append("open_incidents_not_improved")
    if int(candidate_metrics.get("human_assistance_count", 0) or 0) > int(baseline_metrics.get("human_assistance_count", 0) or 0):
        veto_reasons.append("human_assistance_not_reduced")
    promote = (
        candidate_average > baseline_average
        and positive_deltas >= max(1, len(delta) // 2)
        and not hard_regressions
        and not veto_reasons
    )

    next_actions = [
        f"先按 `{classification['root_cause_type']}` 的最小可写面落改动。",
        "保留 baseline 与 candidate 对比产物，避免下一轮失去比较基线。",
    ]
    if hard_regressions:
        next_actions.append(f"优先处理回退维度：{', '.join(hard_regressions)}。")
    if veto_reasons:
        next_actions.append(f"候选方案暂不允许晋升，先处理门禁信号：{', '.join(veto_reasons)}。")
    elif promote:
        next_actions.append("候选方案可以晋升为新基线，并继续观察下一轮日志。")
    else:
        next_actions.append("继续保留为候选方案，再补充更多运行证据后决定是否晋升。")

    return {
        "promote_to_new_baseline": promote,
        "baseline_average": round(baseline_average, 2),
        "candidate_average": round(candidate_average, 2),
        "veto_reasons": veto_reasons,
        "next_actions": next_actions,
    }

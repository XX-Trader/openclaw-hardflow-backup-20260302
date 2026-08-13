#!/usr/bin/env python3
"""Generate control-plane optimization recommendations from recent runtime signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from control_plane_dashboard import build_control_plane_roi_snapshot, collect_control_plane_roi_breakdown
from control_plane_summary_runner import collect_control_plane_summary
from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import TaskCenter, utc_now_iso  # type: ignore

# Source checkouts keep each script under its owning Skill; installed runtimes
# flatten the same dependencies into the ops directory. Bootstrap only when
# the repository marker is present so both layouts share one implementation.
for _candidate_root in Path(__file__).resolve().parents:
    _shared_dir = _candidate_root / "scripts" / "openclaw-ops" / "shared"
    if _shared_dir.is_dir():
        _shared_value = str(_shared_dir)
        if _shared_value not in sys.path:
            sys.path.insert(0, _shared_value)
        from repo_imports import bootstrap_repository_imports

        bootstrap_repository_imports(__file__)
        break

from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


def _stage_label(stage_id: str) -> str:
    """Return a readable Chinese label for one workflow stage."""

    mapping = {
        "clarify": "需求澄清",
        "plan": "任务拆分",
        "implement": "实现",
        "review": "评审",
        "draft": "文档草拟",
        "investigate": "研究调查",
        "stabilize": "稳定化处理",
        "verify": "验证",
        "test": "验证",
    }
    normalized = str(stage_id or "").strip().lower()
    return mapping.get(normalized, normalized or "未知阶段")


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(value or "").strip().lower(), 9)


def _stage_key(metric: dict[str, Any]) -> tuple[str, str]:
    return (
        str(metric.get("workflow_profile_id", "")).strip(),
        str(metric.get("stage_id", "")).strip(),
    )


def _new_stage_metric(workflow_profile_id: str, stage_id: str) -> dict[str, Any]:
    return {
        "workflow_profile_id": workflow_profile_id,
        "stage_id": stage_id,
        "stage_label": _stage_label(stage_id),
        "task_count": 0,
        "open_incident_task_count": 0,
        "critical_incident_task_count": 0,
        "human_assistance_task_count": 0,
        "waiting_human_confirm_task_count": 0,
        "needs_clarification_task_count": 0,
        "benchmark_blocked_count": 0,
        "benchmark_promoted_count": 0,
    }


def _collect_stage_metrics(
    *,
    db_file: str | Path,
    lookback_hours: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Collect per-stage runtime metrics from recent task control-plane reports."""

    db_path = Path(db_file).expanduser()
    since = (
        datetime.now(tz=timezone.utc) - timedelta(hours=max(1, int(lookback_hours or 24)))
    ).replace(microsecond=0).isoformat()

    task_center = TaskCenter(db_path)
    try:
        task_center.init_schema()
        candidates = task_center.recent_control_plane_task_ids(
            since=since,
            limit=max(1, int(limit or 20)),
            display_safe=False,
        )
        metrics_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in candidates:
            task_id = str(candidate.get("task_id", "")).strip()
            if not task_id:
                continue
            report = task_center.task_report(task_id, event_limit=200, display_safe=False)
            task = report.get("task", {}) if isinstance(report.get("task", {}), dict) else {}
            control = report.get("control_plane", {}) if isinstance(report.get("control_plane", {}), dict) else {}
            latest_benchmark = control.get("latest_benchmark_run", {}) if isinstance(control.get("latest_benchmark_run", {}), dict) else {}
            decision = latest_benchmark.get("decision", {}) if isinstance(latest_benchmark.get("decision", {}), dict) else {}

            workflow_profile_id = str(task.get("workflow_profile_id", "")).strip() or "unbound"
            stage_id = str(task.get("stage_id", "")).strip() or "unknown"
            key = (workflow_profile_id, stage_id)
            metric = metrics_by_key.get(key)
            if metric is None:
                metric = _new_stage_metric(workflow_profile_id, stage_id)
                metrics_by_key[key] = metric

            metric["task_count"] += 1
            if int(control.get("open_incident_count", 0) or 0) > 0:
                metric["open_incident_task_count"] += 1
            if int(control.get("critical_open_incident_count", 0) or 0) > 0:
                metric["critical_incident_task_count"] += 1
            if bool(control.get("requires_human_assistance", False)):
                metric["human_assistance_task_count"] += 1
            if bool(control.get("waiting_human_confirm", False)):
                metric["waiting_human_confirm_task_count"] += 1
            if bool(control.get("needs_clarification", False)):
                metric["needs_clarification_task_count"] += 1
            if latest_benchmark:
                if bool(decision.get("promote_to_new_baseline", False)):
                    metric["benchmark_promoted_count"] += 1
                else:
                    metric["benchmark_blocked_count"] += 1
    finally:
        task_center.close()

    return sorted(metrics_by_key.values(), key=_stage_key)


def _append_recommendation(
    recommendations: list[dict[str, Any]],
    *,
    rec_type: str,
    severity: str,
    workflow_profile_id: str,
    stage_id: str,
    stage_label: str,
    reason: str,
    action: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    recommendations.append(
        {
            "type": rec_type,
            "severity": severity,
            "workflow_profile_id": workflow_profile_id,
            "stage_id": stage_id,
            "stage_label": stage_label,
            "reason": reason,
            "action": action,
            "evidence": deepcopy(evidence) if isinstance(evidence, dict) else {},
        }
    )


def _build_recommendations(stage_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build optimization recommendations from per-stage metrics."""

    recommendations: list[dict[str, Any]] = []
    strategy_candidate_stages = {"implement", "draft", "investigate", "stabilize"}

    for metric in stage_metrics:
        workflow_profile_id = str(metric["workflow_profile_id"])
        stage_id = str(metric["stage_id"])
        stage_label = str(metric["stage_label"])
        task_count = int(metric["task_count"])
        open_incident_task_count = int(metric["open_incident_task_count"])
        critical_incident_task_count = int(metric["critical_incident_task_count"])
        human_assistance_task_count = int(metric["human_assistance_task_count"])
        waiting_human_confirm_task_count = int(metric["waiting_human_confirm_task_count"])
        needs_clarification_task_count = int(metric["needs_clarification_task_count"])
        benchmark_blocked_count = int(metric["benchmark_blocked_count"])
        benchmark_promoted_count = int(metric["benchmark_promoted_count"])

        if critical_incident_task_count > 0 or benchmark_blocked_count > 0:
            _append_recommendation(
                recommendations,
                rec_type="strengthen_stage_gate",
                severity="high",
                workflow_profile_id=workflow_profile_id,
                stage_id=stage_id,
                stage_label=stage_label,
                reason=(
                    f"?? {task_count} ? task ??critical incident={critical_incident_task_count}?"
                    f"benchmark ??={benchmark_blocked_count}"
                ),
                action="???????????????????????????????",
            )

        if stage_id in {"clarify", "plan"} and (
            human_assistance_task_count > 0 or needs_clarification_task_count > 0
        ):
            _append_recommendation(
                recommendations,
                rec_type="clarification_upgrade_needed",
                severity="high",
                workflow_profile_id=workflow_profile_id,
                stage_id=stage_id,
                stage_label=stage_label,
                reason=(
                    f"?? {task_count} ? task ??????={human_assistance_task_count}?"
                    f"???={needs_clarification_task_count}?????={waiting_human_confirm_task_count}"
                ),
                action="?????????????????????????????????",
            )

        strategy_candidate_ready = (
            stage_id in strategy_candidate_stages
            and task_count >= 3
            and open_incident_task_count == 0
            and human_assistance_task_count == 0
            and benchmark_blocked_count == 0
            and benchmark_promoted_count >= 2
        )
        if strategy_candidate_ready:
            _append_recommendation(
                recommendations,
                rec_type="parallelize_stage_candidate",
                severity="medium",
                workflow_profile_id=workflow_profile_id,
                stage_id=stage_id,
                stage_label=stage_label,
                reason=(
                    f"?? {task_count} ? task ?????? incident???????? benchmark ???"
                    f"?????={benchmark_promoted_count}"
                ),
                action="????????????????????????????",
            )

        if (
            task_count >= 2
            and open_incident_task_count == 0
            and human_assistance_task_count == 0
            and benchmark_blocked_count == 0
            and benchmark_promoted_count >= 1
        ):
            _append_recommendation(
                recommendations,
                rec_type="stage_simplification_candidate",
                severity="low",
                workflow_profile_id=workflow_profile_id,
                stage_id=stage_id,
                stage_label=stage_label,
                reason=f"?? {task_count} ? task ??????????????={benchmark_promoted_count}",
                action="???????????????????????????????????",
                evidence={
                    "policy": "workflow_evolution.stage_simplification.v1",
                    "task_count": task_count,
                    "open_incident_task_count": open_incident_task_count,
                    "critical_incident_task_count": critical_incident_task_count,
                    "human_assistance_task_count": human_assistance_task_count,
                    "waiting_human_confirm_task_count": waiting_human_confirm_task_count,
                    "needs_clarification_task_count": needs_clarification_task_count,
                    "benchmark_blocked_count": benchmark_blocked_count,
                    "benchmark_promoted_count": benchmark_promoted_count,
                },
            )

    recommendations.sort(
        key=lambda item: (
            _severity_rank(str(item.get("severity", ""))),
            str(item.get("workflow_profile_id", "")),
            str(item.get("stage_id", "")),
            str(item.get("type", "")),
        )
    )
    return recommendations


def render_control_plane_optimization_markdown(report: dict[str, Any]) -> str:
    """Render one Markdown optimization report."""

    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    recommendations = report.get("recommendations", [])
    roi_snapshot = report.get("roi_snapshot", {}) if isinstance(report.get("roi_snapshot", {}), dict) else {}
    stage_roi_breakdown = report.get("stage_roi_breakdown", [])
    if not isinstance(recommendations, list):
        recommendations = []
    lines = [
        "# OpenClaw Control Plane Optimization Advisor",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- 时间窗口：最近 {report.get('lookback_hours', 24)} 小时",
        f"- 扫描 task：{summary.get('scanned_task_count', 0)}",
        f"- 未闭环 incident：{summary.get('open_incident_count', 0)}（critical {summary.get('critical_open_incident_count', 0)}）",
        f"- 人工协助：{summary.get('human_assistance_task_count', 0)}，benchmark 阻断：{summary.get('benchmark_blocked_count', 0)}",
        "",
        "## 优化建议",
    ]
    if not recommendations:
        lines.append("- 当前无新增优化建议")
    else:
        for item in recommendations:
            lines.append(
                f"- [{item.get('severity', 'low')}] {item.get('type', '')}: "
                f"{item.get('workflow_profile_id', '')} / {item.get('stage_label', '')}"
            )
            lines.append(f"  - 原因：{item.get('reason', '')}")
            lines.append(f"  - 动作：{item.get('action', '')}")
            roi_context = item.get("roi_context", {}) if isinstance(item.get("roi_context", {}), dict) else {}
            if roi_context:
                lines.append(
                    "  - ROI：task {task_count} / benchmark {benchmark_count} / 阻断 {blocked_count} / "
                    "incident_task {incident_count} / 人工协助 {human_count} / 单 task 成本 {avg_cost}".format(
                        task_count=int(roi_context.get("task_count", 0) or 0),
                        benchmark_count=int(roi_context.get("benchmark_run_count", 0) or 0),
                        blocked_count=int(roi_context.get("benchmark_blocked_count", 0) or 0),
                        incident_count=int(roi_context.get("open_incident_task_count", 0) or 0),
                        human_count=int(roi_context.get("human_assistance_task_count", 0) or 0),
                        avg_cost="-" if roi_context.get("avg_cost_per_task") is None else str(roi_context.get("avg_cost_per_task")),
                    )
                )

    def ratio_text(value: float | None) -> str:
        return "-" if value is None else f"{round(value * 100, 2)}%"

    def scalar_text(value: float | None) -> str:
        return "-" if value is None else str(value)

    lines.extend(
        [
            "",
            "## ROI 摘要",
            f"- benchmark 样本数：{int(roi_snapshot.get('benchmark_sample_size', 0) or 0)}",
            f"- 晋升率：{ratio_text(roi_snapshot.get('benchmark_promote_rate'))}",
            f"- 阻断率：{ratio_text(roi_snapshot.get('benchmark_block_rate'))}",
            f"- 每 100 次 benchmark 的 incident：{scalar_text(roi_snapshot.get('incident_per_100_benchmark_runs'))}",
            f"- 每 100 次 benchmark 的人工协助：{scalar_text(roi_snapshot.get('human_assistance_per_100_benchmark_runs'))}",
        ]
    )
    lines.extend(["", "## Stage ROI"])
    if isinstance(stage_roi_breakdown, list) and stage_roi_breakdown:
        for item in stage_roi_breakdown[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- {workflow} / {stage}: task {task_count} / benchmark {benchmark_count} / 晋升率 {promote_rate} / "
                "阻断 {blocked_count} / incident_task {incident_count} / 人工协助 {human_count} / 单 task 成本 {avg_cost}".format(
                    workflow=str(item.get("workflow_profile_id", "")).strip() or "unbound",
                    stage=str(item.get("stage_label", "")).strip() or "未知阶段",
                    task_count=int(item.get("task_count", 0) or 0),
                    benchmark_count=int(item.get("benchmark_run_count", 0) or 0),
                    promote_rate="-"
                    if item.get("benchmark_promote_rate") is None
                    else f"{round(float(item.get('benchmark_promote_rate')) * 100, 2)}%",
                    blocked_count=int(item.get("benchmark_blocked_count", 0) or 0),
                    incident_count=int(item.get("open_incident_task_count", 0) or 0),
                    human_count=int(item.get("human_assistance_task_count", 0) or 0),
                    avg_cost="-" if item.get("avg_cost_per_task") is None else str(item.get("avg_cost_per_task")),
                )
            )
    else:
        lines.append("- 当前窗口内暂无 stage ROI 样本")
    return "\n".join(lines).rstrip() + "\n"


def build_control_plane_optimization_report(
    *,
    db_file: str | Path,
    lookback_hours: int = 24,
    limit: int = 20,
) -> dict[str, Any]:
    """Build one optimization report from recent control-plane activity."""

    summary = collect_control_plane_summary(
        db_file=db_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    stage_metrics = _collect_stage_metrics(
        db_file=db_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    roi_breakdown = collect_control_plane_roi_breakdown(
        db_file=db_file,
        lookback_hours=max(1, int(lookback_hours or 24)),
        limit=max(1, int(limit or 20)),
    )
    stage_roi_breakdown = roi_breakdown.get("stage_breakdown", [])
    workflow_roi_breakdown = roi_breakdown.get("workflow_breakdown", [])
    roi_snapshot = build_control_plane_roi_snapshot(
        summary=summary,
        trend_overview={"totals": {
            "benchmark_run_count": int(summary.get("benchmark_run_task_count", 0) or 0),
            "benchmark_promoted_count": int(summary.get("benchmark_promoted_count", 0) or 0),
            "benchmark_blocked_count": int(summary.get("benchmark_blocked_count", 0) or 0),
            "incident_count": int(summary.get("open_incident_count", 0) or 0),
            "critical_incident_count": int(summary.get("critical_open_incident_count", 0) or 0),
            "human_assistance_count": int(summary.get("human_assistance_task_count", 0) or 0),
        }},
        benchmark_overview={},
    )
    stage_roi_map = {
        (
            str(item.get("workflow_profile_id", "")).strip(),
            str(item.get("stage_id", "")).strip(),
        ): item
        for item in stage_roi_breakdown
        if isinstance(item, dict)
    }
    recommendations = _build_recommendations(stage_metrics)
    for item in recommendations:
        key = (
            str(item.get("workflow_profile_id", "")).strip(),
            str(item.get("stage_id", "")).strip(),
        )
        roi_context = stage_roi_map.get(key)
        if isinstance(roi_context, dict):
            item["roi_context"] = roi_context
    report = {
        "generated_at": utc_now_iso(),
        "lookback_hours": max(1, int(lookback_hours or 24)),
        "summary": summary,
        "stage_metrics": stage_metrics,
        "recommendations": recommendations,
        "roi_snapshot": roi_snapshot,
        "workflow_roi_breakdown": workflow_roi_breakdown,
        "stage_roi_breakdown": stage_roi_breakdown,
    }
    report["markdown"] = render_control_plane_optimization_markdown(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="Generate control-plane optimization recommendations.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--lookback-hours", default="24")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--todo-file", default="", help="将建议自动追加到 TODO.md（含去重+风险标记）")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the CLI and return the optimization report payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_control_plane_optimization_report(
        db_file=str(args.db).strip(),
        lookback_hours=max(1, int(args.lookback_hours or 24)),
        limit=max(1, int(args.limit or 20)),
    )
    payload = {"report": report}
    if str(args.json_output or "").strip():
        write_json_atomic(
            Path(str(args.json_output).strip()).expanduser(),
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o644,
            dir_mode=0o755,
        )
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            report["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    # advisor→TODO 自动写入
    todo_file = str(args.todo_file or "").strip()
    if todo_file and report.get("recommendations"):
        appended = append_recommendations_to_todo(
            Path(todo_file).expanduser(),
            report["recommendations"],
        )
        payload["todo_appended"] = appended
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(report["markdown"])
    return payload


def append_recommendations_to_todo(
    todo_path: Path,
    recommendations: list[dict[str, Any]],
) -> int:
    """将优化建议自动追加到 TODO.md，含指纹去重 + 风险标记。

    Args:
        todo_path: TODO.md 文件路径。
        recommendations: advisor 生成的建议列表。

    Returns:
        int: 实际追加的新建议数量。
    """
    existing_content = ""
    if todo_path.exists():
        existing_content = todo_path.read_text(encoding="utf-8", errors="replace")
    # 提取已有指纹进行去重
    existing_fingerprints: set[str] = set()
    for line in existing_content.splitlines():
        # 匹配 [advisor:xxxx] 格式的指纹
        if "[advisor:" in line:
            start = line.index("[advisor:") + 9
            end = line.index("]", start) if "]" in line[start:] else len(line)
            existing_fingerprints.add(line[start:start + (end - start)].strip())
    new_lines: list[str] = []
    severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    for rec in recommendations:
        rec_type = str(rec.get("rec_type", "")).strip()
        severity = str(rec.get("severity", "low")).strip().lower()
        reason = str(rec.get("reason", "")).strip()[:120]
        action = str(rec.get("action", "")).strip()[:120]
        # 生成指纹
        fp_raw = f"{rec_type}:{rec.get('workflow_profile_id','')}:{rec.get('stage_id','')}"
        fingerprint = hashlib.md5(fp_raw.encode()).hexdigest()[:8]
        if fingerprint in existing_fingerprints:
            continue
        icon = severity_icon.get(severity, "⚪")
        risk_tag = "🚨需人工审核" if severity == "high" else ""
        line = f"- [ ] {icon} [{date_str}] {reason} — {action} {risk_tag} [advisor:{fingerprint}]"
        new_lines.append(line)
    if not new_lines:
        return 0
    # 追加到文件末尾
    separator = "\n## 🤖 Advisor 自动建议\n\n" if "Advisor 自动建议" not in existing_content else "\n"
    todo_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(todo_path), "a", encoding="utf-8") as fh:
        fh.write(separator + "\n".join(new_lines) + "\n")
    return len(new_lines)


if __name__ == "__main__":
    main()

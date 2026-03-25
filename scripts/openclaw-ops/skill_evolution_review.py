#!/usr/bin/env python3
"""Build skill evolution reviews from baseline/candidate executor reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from upgrade_analysis import (
    build_promotion_decision,
    build_root_cause_summary,
    build_window,
    classify_root_cause,
    compute_delta,
    load_reports,
    score_skill_metrics,
)


JSONDict = dict[str, Any]


def build_skill_update_recommendations(
    *,
    baseline_metrics: JSONDict,
    baseline_score: JSONDict,
    skill_name: str,
) -> list[str]:
    """Generate concrete follow-up updates for the target skill."""

    updates: list[str] = []
    if int(baseline_score["instruction_clarity"]) < 80 or baseline_metrics["incomplete_output_count"] > 0:
        updates.append("补强触发条件与输入前置校验，明确资料不足时先补证据而不是直接下结论。")
    if int(baseline_score["boundary_clarity"]) < 80 or baseline_metrics["boundary_issue_count"] > 0:
        updates.append("补强边界说明，写清楚 workflow、skill、runtime 三层里哪些位置可以先改、哪些不要先动。")
    if int(baseline_score["verification_discipline"]) < 80 or baseline_metrics["verification_success_count"] == 0:
        updates.append("补强验证动作，要求输出最少一条运行结果、日志摘录或 baseline/candidate 对比证据。")
    if baseline_metrics["repeated_failure_count"] > 0:
        updates.append("补强失败回流规则，让 agent 在重复失败时先写归因和最小可写面，再进入下一轮修改。")
    if not updates:
        updates.append(f"继续精简 {skill_name} 的说明结构，保持触发、边界、验证三段稳定。")
    return updates


def render_skill_review_markdown(
    *,
    skill_name: str,
    assignee: str,
    classification: JSONDict,
    baseline_score: JSONDict,
    candidate_score: JSONDict,
    delta: JSONDict,
    baseline_metrics: JSONDict,
    candidate_metrics: JSONDict,
    recommended_updates: Sequence[str],
    decision: JSONDict,
) -> str:
    """Render a human-readable markdown review for a skill upgrade."""

    lines = [
        "# Skill Evolution Review",
        "",
        "## 1. 背景",
        f"- skill 名称：{skill_name}",
        f"- 关联执行人：{assignee or '未指定'}",
        f"- 关联 run：{', '.join(baseline_metrics['run_ids'] + candidate_metrics['run_ids']) or '未记录'}",
        "",
        "## 2. 上一轮问题",
        f"- 重复失败：{baseline_metrics['repeated_failure_count']}",
        f"- 低分维度：instruction_clarity={baseline_score['instruction_clarity']}，verification_discipline={baseline_score['verification_discipline']}",
        f"- 证据不足点：{baseline_metrics['incomplete_output_count']}",
        f"- 越界修改点：{baseline_metrics['boundary_issue_count']}",
        "",
        "## 3. 归因",
        f"- 问题分类：`{classification['root_cause_type']}`",
        f"- 归因摘要：{classification['root_cause_summary']}",
        f"- 最小可写面：{', '.join(classification['minimal_writable_surface'])}",
        "",
        "## 4. 本轮升级点",
    ]
    lines.extend(f"- {item}" for item in recommended_updates)
    lines.extend(
        [
            "",
            "## 5. 验证方式",
            f"- baseline：passed={baseline_metrics['passed_count']} / failed={baseline_metrics['failed_count']} / partial={baseline_metrics['partial_count']}",
            f"- candidate：passed={candidate_metrics['passed_count']} / failed={candidate_metrics['failed_count']} / partial={candidate_metrics['partial_count']}",
            "- 观察点：质量分、验证证据、边界控制、重复失败是否下降。",
            "",
            "## 6. 分数比较",
            f"- baseline：{json.dumps(baseline_score, ensure_ascii=False)}",
            f"- candidate：{json.dumps(candidate_score, ensure_ascii=False)}",
            f"- delta：{json.dumps(delta, ensure_ascii=False)}",
            "",
            "## 7. 结论",
            f"- 是否晋升为新基线：{'是' if decision['promote_to_new_baseline'] else '否'}",
            f"- 后续仍需补哪一层：{build_root_cause_summary(classification['root_cause_type'], baseline_metrics, skill_name=skill_name)}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_skill_evolution_review(
    *,
    baseline_inputs: Sequence[str | Path],
    candidate_inputs: Sequence[str | Path],
    skill_name: str,
    assignee: str,
) -> JSONDict:
    """Build a skill evolution review from baseline and candidate report inputs.

    Args:
        baseline_inputs: Baseline report files or directories. Must contain JSON files.
        candidate_inputs: Candidate report files or directories. Must contain JSON files.
        skill_name: Target skill name. Used for output and writable-surface hints.
        assignee: Optional assignee filter. Only matching result records are analyzed.

    Returns:
        A JSON object containing baseline/candidate scores, recommendations, and markdown.

    Raises:
        FileNotFoundError: If any report input path does not exist.
        ValueError: If the report payloads are invalid.
    """

    from upgrade_analysis import analyze_reports  # Local import keeps script entry lightweight.

    baseline_reports = load_reports(baseline_inputs)
    candidate_reports = load_reports(candidate_inputs)
    baseline_metrics = analyze_reports(baseline_reports, assignee=assignee)
    candidate_metrics = analyze_reports(candidate_reports, assignee=assignee)
    baseline_score = score_skill_metrics(baseline_metrics)
    candidate_score = score_skill_metrics(candidate_metrics)
    delta = compute_delta(baseline_score, candidate_score)
    classification = classify_root_cause(
        baseline_metrics,
        preferred_kind="skill",
        skill_name=skill_name,
    )
    recommended_updates = build_skill_update_recommendations(
        baseline_metrics=baseline_metrics,
        baseline_score=baseline_score,
        skill_name=skill_name,
    )
    decision = build_promotion_decision(
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        delta=delta,
        classification=classification,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
    )
    markdown = render_skill_review_markdown(
        skill_name=skill_name,
        assignee=assignee,
        classification=classification,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        delta=delta,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        recommended_updates=recommended_updates,
        decision=decision,
    )
    return {
        "upgrade_type": "skill",
        "skill_name": skill_name,
        "assignee": assignee,
        "baseline_window": build_window(baseline_reports),
        "candidate_window": build_window(candidate_reports),
        "classification": classification,
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "delta": delta,
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "recommended_updates": recommended_updates,
        "decision": decision,
        "markdown": markdown,
    }


def main() -> int:
    """Run the skill evolution review builder as a CLI tool."""

    parser = argparse.ArgumentParser(description="Build skill evolution reviews from executor reports.")
    parser.add_argument("--baseline-report", action="append", dest="baseline_reports", required=True)
    parser.add_argument("--candidate-report", action="append", dest="candidate_reports", required=True)
    parser.add_argument("--skill-name", required=True)
    parser.add_argument("--assignee", default="")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    review = build_skill_evolution_review(
        baseline_inputs=args.baseline_reports,
        candidate_inputs=args.candidate_reports,
        skill_name=str(args.skill_name).strip(),
        assignee=str(args.assignee).strip(),
    )

    if str(args.output_file).strip():
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(review["markdown"], encoding="utf-8")

    if args.emit_json:
        print(json.dumps(review, ensure_ascii=False, indent=2))
    elif not str(args.output_file).strip():
        print(review["markdown"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

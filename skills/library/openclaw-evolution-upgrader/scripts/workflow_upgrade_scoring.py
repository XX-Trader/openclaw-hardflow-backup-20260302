#!/usr/bin/env python3
"""Build baseline/candidate workflow upgrade scorecards from executor reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from upgrade_analysis import (
    build_dimension_insights,
    build_promotion_decision,
    build_window,
    classify_root_cause,
    compute_delta,
    load_reports,
    score_workflow_metrics,
)


JSONDict = dict[str, Any]


def _load_template(path: Path) -> JSONDict:
    """Load a JSON template file when it exists."""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Workflow scorecard template must be a JSON object: {path}")
    return payload


def _collect_inputs(reports: Sequence[JSONDict]) -> list[str]:
    """Collect source file paths from annotated report payloads."""

    return [str(report.get("__report_path", "")).strip() for report in reports if str(report.get("__report_path", "")).strip()]


def build_workflow_upgrade_scorecard(
    *,
    baseline_inputs: Sequence[str | Path],
    candidate_inputs: Sequence[str | Path],
    target_name: str,
    template_file: str | Path | None = None,
) -> JSONDict:
    """Build a workflow scorecard from baseline and candidate report inputs.

    Args:
        baseline_inputs: Baseline report files or directories. Must contain JSON files.
        candidate_inputs: Candidate report files or directories. Must contain JSON files.
        target_name: Workflow target name, such as a cron job id or runner identifier.
        template_file: Optional JSON template path. When present, the output keeps template keys.

    Returns:
        A workflow upgrade scorecard JSON object with baseline/candidate/delta scores.

    Raises:
        FileNotFoundError: If any report input path does not exist.
        ValueError: If the report or template structure is invalid.
    """

    baseline_reports = load_reports(baseline_inputs)
    candidate_reports = load_reports(candidate_inputs)

    from upgrade_analysis import analyze_reports  # Local import keeps module boundary simple.

    baseline_metrics = analyze_reports(baseline_reports)
    candidate_metrics = analyze_reports(candidate_reports)
    baseline_score = score_workflow_metrics(baseline_metrics)
    candidate_score = score_workflow_metrics(candidate_metrics)
    delta = compute_delta(baseline_score, candidate_score)
    classification = classify_root_cause(baseline_metrics, preferred_kind="workflow")
    top_improvements, top_regressions = build_dimension_insights(baseline_score, candidate_score, delta)
    decision = build_promotion_decision(
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        delta=delta,
        classification=classification,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
    )

    scorecard = _load_template(Path(template_file).expanduser()) if template_file else {}
    scorecard.update(
        {
            "template_version": scorecard.get("template_version", "2026-03-22"),
            "upgrade_type": "workflow",
            "target_name": target_name,
            "baseline_window": build_window(baseline_reports),
            "candidate_window": build_window(candidate_reports),
            "inputs": {
                "runs": sorted(set(baseline_metrics["run_ids"] + candidate_metrics["run_ids"])),
                "reports": {
                    "baseline": _collect_inputs(baseline_reports),
                    "candidate": _collect_inputs(candidate_reports),
                },
                "external_sources": [],
            },
            "classification": classification,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "delta": delta,
            "baseline_metrics": baseline_metrics,
            "candidate_metrics": candidate_metrics,
            "top_regressions": top_regressions,
            "top_improvements": top_improvements,
            "decision": decision,
        }
    )
    return scorecard


def main() -> int:
    """Run the workflow scorecard builder as a CLI tool."""

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build workflow upgrade scorecards from executor reports.")
    parser.add_argument("--baseline-report", action="append", dest="baseline_reports", required=True)
    parser.add_argument("--candidate-report", action="append", dest="candidate_reports", required=True)
    parser.add_argument("--target-name", required=True)
    parser.add_argument(
        "--template-file",
        default=str(
            root
            / "skills"
            / "library"
            / "openclaw-evolution-upgrader"
            / "assets"
            / "workflow-upgrade-scorecard-template.json"
        ),
    )
    parser.add_argument("--output-file", default="")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    scorecard = build_workflow_upgrade_scorecard(
        baseline_inputs=args.baseline_reports,
        candidate_inputs=args.candidate_reports,
        target_name=str(args.target_name).strip(),
        template_file=args.template_file,
    )
    payload = json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n"

    if str(args.output_file).strip():
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")

    if args.emit_json or not str(args.output_file).strip():
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

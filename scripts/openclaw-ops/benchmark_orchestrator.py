#!/usr/bin/env python3
"""Benchmark suite orchestration entrypoint for OpenClaw workflow profiles."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from upgrade_feedback_runner import (
    build_upgrade_feedback_bundle,
    load_benchmark_suite_registry,
    resolve_benchmark_suite,
)
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


JSONDict = dict[str, Any]


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_registry_path(registry_file: str | Path | None) -> Path | None:
    """Normalize an optional benchmark suite registry path."""

    if registry_file is None:
        return None
    raw = str(registry_file).strip()
    return Path(raw).expanduser() if raw else None


def _safe_stamp() -> str:
    """Build a filesystem-safe UTC timestamp."""

    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: JSONDict) -> None:
    """Persist one JSON document using UTF-8 without BOM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_suite_item(item: JSONDict, *, default_suite_id: str) -> JSONDict:
    """Return one display-friendly benchmark suite record."""

    suite_id = str(item.get("suite_id", "")).strip()
    return {
        "suite_id": suite_id,
        "display_name": str(item.get("display_name", "")).strip(),
        "workflow_profile_id": str(item.get("workflow_profile_id", "")).strip(),
        "baseline_channel": str(item.get("baseline_channel", "")).strip(),
        "candidate_channel": str(item.get("candidate_channel", "")).strip(),
        "workflow_target": str(item.get("workflow_target", "")).strip(),
        "skill_name": str(item.get("skill_name", "")).strip(),
        "skill_assignee": str(item.get("skill_assignee", "")).strip(),
        "baseline_count": int(item.get("baseline_count", 0) or 0),
        "candidate_count": int(item.get("candidate_count", 0) or 0),
        "target_kind": str(item.get("target_kind", "")).strip(),
        "target_id": str(item.get("target_id", "")).strip(),
        "is_default": suite_id == default_suite_id,
    }


def list_benchmark_suites(*, registry_file: str | Path | None = None) -> JSONDict:
    """List benchmark suites from the runtime registry."""

    registry_path = _resolve_registry_path(registry_file)
    registry = load_benchmark_suite_registry(registry_path)
    default_suite_id = str(registry.get("default_suite_id", "")).strip()
    suites = [
        _normalize_suite_item(item, default_suite_id=default_suite_id)
        for item in registry.get("suites", [])
        if isinstance(item, dict)
    ]
    return {
        "generated_at": _now_iso(),
        "registry_file": str(registry_path) if registry_path is not None else "",
        "default_suite_id": default_suite_id,
        "suite_count": len(suites),
        "suites": suites,
    }


def _build_suite_paths(*, output_root: Path, state_root: Path, suite_id: str) -> tuple[Path, Path]:
    """Derive one suite-scoped output directory and state file path."""

    return output_root / "suites" / suite_id, state_root / f"{suite_id}.json"


def _persist_sweep_summary(*, output_root: Path, summary: JSONDict) -> tuple[Path, Path]:
    """Write timestamped and latest sweep summary files."""

    sweep_dir = output_root / "sweeps"
    stamp = _safe_stamp()
    summary_file = sweep_dir / f"benchmark-sweep-{stamp}.json"
    latest_summary_file = sweep_dir / "latest-summary.json"
    _write_json(summary_file, summary)
    _write_json(latest_summary_file, summary)
    return summary_file, latest_summary_file


def _execute_suite_batch(
    *,
    selected_suite_ids: list[str],
    executor_run_dir: str | Path,
    output_root: str | Path,
    state_root: str | Path,
    registry_file: str | Path | None,
    task_db: str | Path | None,
    auto_create_tasks: bool,
    task_score_threshold: float,
    task_schedule_gap_minutes: int,
    workflow_profile_registry: str | Path | None,
    auto_apply_workflow_promotion: bool,
    promotion_operator: str,
    continue_on_error: bool,
) -> tuple[list[JSONDict], list[JSONDict]]:
    """Execute multiple suites and capture per-suite failures."""

    results: list[JSONDict] = []
    failures: list[JSONDict] = []
    for wanted_suite_id in selected_suite_ids:
        try:
            results.append(
                run_benchmark_suite(
                    executor_run_dir=executor_run_dir,
                    output_root=output_root,
                    state_root=state_root,
                    registry_file=registry_file,
                    suite_id=wanted_suite_id,
                    task_db=task_db,
                    auto_create_tasks=auto_create_tasks,
                    task_score_threshold=task_score_threshold,
                    task_schedule_gap_minutes=task_schedule_gap_minutes,
                    workflow_profile_registry=workflow_profile_registry,
                    auto_apply_workflow_promotion=auto_apply_workflow_promotion,
                    promotion_operator=promotion_operator,
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "suite_id": wanted_suite_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            if not continue_on_error:
                break
    return results, failures


def run_benchmark_suite(
    *,
    executor_run_dir: str | Path,
    output_root: str | Path,
    state_root: str | Path,
    registry_file: str | Path | None = None,
    suite_id: str = "",
    task_db: str | Path | None = None,
    auto_create_tasks: bool = False,
    task_score_threshold: float = 80.0,
    task_schedule_gap_minutes: int = 120,
    workflow_profile_registry: str | Path | None = None,
    auto_apply_workflow_promotion: bool = False,
    promotion_operator: str = "benchmark-orchestrator",
) -> JSONDict:
    """Run one benchmark suite and return the persisted result bundle."""

    registry_path = _resolve_registry_path(registry_file)
    registry = load_benchmark_suite_registry(registry_path)
    suite = resolve_benchmark_suite(registry=registry, suite_id=str(suite_id).strip())
    resolved_suite_id = str(suite.get("suite_id", "")).strip()
    suite_output_dir, suite_state_file = _build_suite_paths(
        output_root=Path(output_root).expanduser(),
        state_root=Path(state_root).expanduser(),
        suite_id=resolved_suite_id,
    )
    summary = build_upgrade_feedback_bundle(
        executor_run_dir=executor_run_dir,
        output_dir=suite_output_dir,
        state_file=suite_state_file,
        workflow_target=str(suite.get("workflow_target", "")).strip() or "task_executor_10m",
        skill_name=str(suite.get("skill_name", "")).strip() or "openclaw-evolution-upgrader",
        skill_assignee=str(suite.get("skill_assignee", "")).strip() or "optimization-agent",
        baseline_count=max(1, int(suite.get("baseline_count", 1) or 1)),
        candidate_count=max(1, int(suite.get("candidate_count", 1) or 1)),
        task_db=task_db,
        auto_create_tasks=bool(auto_create_tasks),
        task_score_threshold=float(task_score_threshold),
        task_schedule_gap_minutes=max(1, int(task_schedule_gap_minutes)),
        benchmark_suite_file=registry_path,
        benchmark_suite_id=resolved_suite_id,
        workflow_profile_registry=workflow_profile_registry,
        auto_apply_workflow_promotion=bool(auto_apply_workflow_promotion),
        promotion_operator=str(promotion_operator or "").strip() or "benchmark-orchestrator",
    )
    return {
        "status": str(summary.get("status", "")).strip() or "unknown",
        "generated_at": _now_iso(),
        "suite_id": resolved_suite_id,
        "suite": _normalize_suite_item(suite, default_suite_id=str(registry.get("default_suite_id", "")).strip()),
        "output_dir": str(suite_output_dir),
        "state_file": str(suite_state_file),
        "summary": summary,
    }


def run_benchmark_sweep(
    *,
    executor_run_dir: str | Path,
    output_root: str | Path,
    state_root: str | Path,
    registry_file: str | Path | None = None,
    suite_ids: list[str] | tuple[str, ...] | None = None,
    task_db: str | Path | None = None,
    auto_create_tasks: bool = False,
    task_score_threshold: float = 80.0,
    task_schedule_gap_minutes: int = 120,
    workflow_profile_registry: str | Path | None = None,
    auto_apply_workflow_promotion: bool = False,
    promotion_operator: str = "benchmark-orchestrator",
    continue_on_error: bool = False,
) -> JSONDict:
    """Run a batch benchmark sweep across multiple suites."""

    listing = list_benchmark_suites(registry_file=registry_file)
    requested_suite_ids = [str(item).strip() for item in (suite_ids or []) if str(item).strip()]
    selected_suite_ids = requested_suite_ids or [str(item.get("suite_id", "")).strip() for item in listing["suites"]]
    results, failures = _execute_suite_batch(
        selected_suite_ids=selected_suite_ids,
        executor_run_dir=executor_run_dir,
        output_root=output_root,
        state_root=state_root,
        registry_file=registry_file,
        task_db=task_db,
        auto_create_tasks=auto_create_tasks,
        task_score_threshold=task_score_threshold,
        task_schedule_gap_minutes=task_schedule_gap_minutes,
        workflow_profile_registry=workflow_profile_registry,
        auto_apply_workflow_promotion=auto_apply_workflow_promotion,
        promotion_operator=promotion_operator,
        continue_on_error=continue_on_error,
    )
    status = "ok" if not failures else ("partial_failure" if results else "failed")
    summary = {
        "status": status,
        "generated_at": _now_iso(),
        "registry_file": listing["registry_file"],
        "default_suite_id": listing["default_suite_id"],
        "requested_suite_ids": selected_suite_ids,
        "suite_count": len(selected_suite_ids),
        "success_count": len(results),
        "failure_count": len(failures),
        "results": results,
        "failures": failures,
    }
    summary_file, latest_summary_file = _persist_sweep_summary(
        output_root=Path(output_root).expanduser(),
        summary=summary,
    )
    summary["summary_file"] = str(summary_file)
    summary["latest_summary_file"] = str(latest_summary_file)
    _write_json(summary_file, summary)
    _write_json(latest_summary_file, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark orchestration CLI parser."""

    home = Path.home()
    parser = argparse.ArgumentParser(description="Orchestrate benchmark suites for workflow profiles.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list-suites", help="list available benchmark suites")
    list_cmd.add_argument("--benchmark-suite-file", default="")
    list_cmd.add_argument("--emit-json", action="store_true")

    def add_common_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--executor-run-dir", default=str(home / ".openclaw/ops/task-center/executor-runs"))
        target.add_argument("--output-root", default=str(home / ".openclaw/ops/benchmark-orchestrator"))
        target.add_argument("--state-root", default=str(home / ".openclaw/ops/benchmark-orchestrator/state"))
        target.add_argument("--benchmark-suite-file", default="")
        target.add_argument("--task-db", default="")
        target.add_argument("--auto-create-tasks", action=argparse.BooleanOptionalAction, default=False)
        target.add_argument("--task-score-threshold", type=float, default=80.0)
        target.add_argument("--task-schedule-gap-minutes", type=int, default=120)
        target.add_argument("--workflow-profile-registry", default="")
        target.add_argument("--auto-apply-workflow-promotion", action=argparse.BooleanOptionalAction, default=False)
        target.add_argument("--promotion-operator", default="benchmark-orchestrator")
        target.add_argument("--emit-json", action="store_true")

    run_suite = sub.add_parser("run-suite", help="run one benchmark suite")
    add_common_arguments(run_suite)
    run_suite.add_argument("--suite-id", default="")

    run_all = sub.add_parser("run-all", help="run all benchmark suites or a selected subset")
    add_common_arguments(run_all)
    run_all.add_argument("--suite-id", action="append", default=[])
    run_all.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=False)
    return parser


def main() -> int:
    """Run the benchmark orchestration CLI."""

    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list-suites":
        payload = list_benchmark_suites(registry_file=(str(args.benchmark_suite_file).strip() or None))
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"default_suite_id": payload["default_suite_id"], "suite_count": payload["suite_count"]}, ensure_ascii=False))
        return 0

    if args.command == "run-suite":
        payload = run_benchmark_suite(
            executor_run_dir=args.executor_run_dir,
            output_root=args.output_root,
            state_root=args.state_root,
            registry_file=(str(args.benchmark_suite_file).strip() or None),
            suite_id=str(args.suite_id).strip(),
            task_db=(str(args.task_db).strip() or None),
            auto_create_tasks=bool(args.auto_create_tasks),
            task_score_threshold=float(args.task_score_threshold),
            task_schedule_gap_minutes=max(1, int(args.task_schedule_gap_minutes)),
            workflow_profile_registry=(str(args.workflow_profile_registry).strip() or None),
            auto_apply_workflow_promotion=bool(args.auto_apply_workflow_promotion),
            promotion_operator=str(args.promotion_operator).strip() or "benchmark-orchestrator",
        )
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"suite_id": payload["suite_id"], "status": payload["status"]}, ensure_ascii=False))
        return 0

    payload = run_benchmark_sweep(
        executor_run_dir=args.executor_run_dir,
        output_root=args.output_root,
        state_root=args.state_root,
        registry_file=(str(args.benchmark_suite_file).strip() or None),
        suite_ids=[str(item).strip() for item in args.suite_id if str(item).strip()],
        task_db=(str(args.task_db).strip() or None),
        auto_create_tasks=bool(args.auto_create_tasks),
        task_score_threshold=float(args.task_score_threshold),
        task_schedule_gap_minutes=max(1, int(args.task_schedule_gap_minutes)),
        workflow_profile_registry=(str(args.workflow_profile_registry).strip() or None),
        auto_apply_workflow_promotion=bool(args.auto_apply_workflow_promotion),
        promotion_operator=str(args.promotion_operator).strip() or "benchmark-orchestrator",
        continue_on_error=bool(args.continue_on_error),
    )
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": payload["status"], "success_count": payload["success_count"], "failure_count": payload["failure_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

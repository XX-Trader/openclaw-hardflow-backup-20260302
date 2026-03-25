#!/usr/bin/env python3
"""Run targeted benchmark validation after workflow profile updates are applied."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

POLICY_DIR = Path(__file__).resolve().parent / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from benchmark_orchestrator import run_benchmark_suite
from io_write_gateway import atomic_write_text, write_json_atomic  # type: ignore
from task_center import utc_now_iso  # type: ignore
from upgrade_feedback_runner import load_benchmark_suite_registry
from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()


JSONDict = dict[str, Any]
SuiteRunner = Callable[..., JSONDict]


def _write_json(path: Path, payload: JSONDict) -> None:
    """Write one JSON object using UTF-8 without BOM."""

    write_json_atomic(
        path,
        payload,
        ensure_ascii=False,
        indent=2,
        file_mode=0o644,
        dir_mode=0o755,
    )


def _normalize_apply_payload(apply_raw: Any) -> JSONDict:
    """Normalize one apply payload into the result body."""

    if not isinstance(apply_raw, dict):
        raise ValueError("profile update apply payload must be a JSON object")
    nested_result = apply_raw.get("result")
    if isinstance(nested_result, dict):
        return nested_result
    return apply_raw


def load_control_plane_profile_update_apply_report(apply_file: str | Path) -> JSONDict:
    """Load one profile-update apply report from disk."""

    path = Path(apply_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"profile update apply file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    report = _normalize_apply_payload(payload)
    applied = report.get("applied", [])
    skipped = report.get("skipped", [])
    if not isinstance(applied, list):
        raise ValueError("profile update apply report applied must be a list")
    if not isinstance(skipped, list):
        raise ValueError("profile update apply report skipped must be a list")
    normalized = dict(report)
    normalized["applied"] = [item for item in applied if isinstance(item, dict)]
    normalized["skipped"] = [item for item in skipped if isinstance(item, dict)]
    return normalized


def _load_validation_state(state_file: Path) -> JSONDict:
    """Load one validation state file or return the default state."""

    if not state_file.exists():
        return {
            "validated_change_ids": [],
            "updated_at": "",
        }
    payload = json.loads(state_file.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("profile update validation state must be a JSON object")
    validated_change_ids = payload.get("validated_change_ids", [])
    if not isinstance(validated_change_ids, list):
        raise ValueError("profile update validation state validated_change_ids must be a list")
    return {
        "validated_change_ids": [
            str(item).strip()
            for item in validated_change_ids
            if str(item).strip()
        ],
        "updated_at": str(payload.get("updated_at", "")).strip(),
    }


def _resolve_matching_suite_ids(*, registry: JSONDict, target_profile_id: str) -> list[str]:
    """Resolve benchmark suite ids for one workflow profile id."""

    normalized_target = str(target_profile_id or "").strip().lower()
    matched_suite_ids: list[str] = []
    suites = registry.get("suites", [])
    if not isinstance(suites, list):
        raise ValueError("benchmark suite registry suites must be a list")
    for item in suites:
        if not isinstance(item, dict):
            continue
        workflow_profile_id = str(item.get("workflow_profile_id", "")).strip().lower()
        target_kind = str(item.get("target_kind", "")).strip().lower()
        target_id = str(item.get("target_id", "")).strip().lower()
        suite_id = str(item.get("suite_id", "")).strip()
        if not suite_id:
            continue
        if workflow_profile_id == normalized_target or (
            target_kind == "workflow" and target_id == normalized_target
        ):
            if suite_id not in matched_suite_ids:
                matched_suite_ids.append(suite_id)
    return matched_suite_ids


def render_control_plane_profile_update_validation_markdown(result: JSONDict) -> str:
    """Render one Markdown summary for targeted benchmark validation."""

    lines = [
        "# OpenClaw Control Plane Profile Update Validation",
        "",
        f"- 生成时间：{result.get('generated_at', '')}",
        f"- apply 报告：{result.get('apply_file', '')}",
        f"- benchmark registry：{result.get('benchmark_suite_file', '')}",
        f"- 已执行 suite：{result.get('executed_suite_count', 0)}",
        f"- 已验证 change_id：{result.get('validated_change_count', 0)}",
        f"- 跳过项：{result.get('skipped_count', 0)}",
        f"- 失败项：{result.get('failed_count', 0)}",
        "",
        "## 已验证变更",
    ]
    validated = result.get("validated", [])
    if isinstance(validated, list) and validated:
        for item in validated:
            if not isinstance(item, dict):
                continue
            suite_ids = ", ".join(str(part) for part in item.get("suite_ids", []) if str(part).strip()) or "unknown-suite"
            lines.append(
                f"- {item.get('change_id', '')}: {item.get('target_profile_id', '')}/"
                f"{item.get('target_stage_id', '')} -> {suite_ids}"
            )
    else:
        lines.append("- 本次没有新增验证通过的 profile update 变更")

    lines.extend(["", "## 跳过项"])
    skipped = result.get("skipped", [])
    if isinstance(skipped, list) and skipped:
        for item in skipped:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('change_id', '')}: {item.get('target_profile_id', '')}/"
                f"{item.get('target_stage_id', '')} / {item.get('reason', '')}"
            )
    else:
        lines.append("- 本次没有跳过项")

    lines.extend(["", "## 失败项"])
    failed = result.get("failed", [])
    if isinstance(failed, list) and failed:
        for item in failed:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('change_id', '')}: {item.get('target_profile_id', '')}/"
                f"{item.get('target_stage_id', '')} / {item.get('reason', '')}"
            )
    else:
        lines.append("- 本次没有失败项")
    return "\n".join(lines).rstrip() + "\n"


def run_control_plane_profile_update_validation(
    *,
    apply_file: str | Path,
    benchmark_suite_file: str | Path,
    executor_run_dir: str | Path,
    output_root: str | Path,
    state_file: str | Path,
    workflow_profile_registry: str | Path | None = None,
    task_db: str | Path | None = None,
    auto_create_tasks: bool = False,
    task_score_threshold: float = 80.0,
    task_schedule_gap_minutes: int = 120,
    auto_apply_workflow_promotion: bool = False,
    promotion_operator: str = "control-plane-profile-update-validation",
    suite_runner: SuiteRunner | None = None,
) -> JSONDict:
    """Run targeted benchmark validation for newly applied profile-update changes."""

    resolved_apply_file = Path(apply_file).expanduser()
    resolved_benchmark_suite_file = Path(benchmark_suite_file).expanduser()
    resolved_output_root = Path(output_root).expanduser()
    resolved_state_file = Path(state_file).expanduser()
    resolved_state_root = resolved_output_root / "state"

    apply_report = load_control_plane_profile_update_apply_report(resolved_apply_file)
    benchmark_registry = load_benchmark_suite_registry(resolved_benchmark_suite_file)
    state = _load_validation_state(resolved_state_file)
    validated_change_ids = {
        str(item).strip()
        for item in state.get("validated_change_ids", [])
        if str(item).strip()
    }
    suite_runner_impl = suite_runner or run_benchmark_suite

    grouped_items: dict[str, list[JSONDict]] = {}
    skipped: list[JSONDict] = []
    failed: list[JSONDict] = []
    validated: list[JSONDict] = []
    executed_suites: list[JSONDict] = []

    for raw_item in apply_report.get("applied", []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        change_id = str(item.get("change_id", "")).strip()
        target_profile_id = str(item.get("target_profile_id", "")).strip()
        target_stage_id = str(item.get("target_stage_id", "")).strip()
        if not change_id:
            skipped.append(
                {
                    "task_id": str(item.get("task_id", "")).strip(),
                    "change_id": "",
                    "target_profile_id": target_profile_id,
                    "target_stage_id": target_stage_id,
                    "reason": "missing_change_id",
                }
            )
            continue
        if change_id in validated_change_ids:
            skipped.append(
                {
                    "task_id": str(item.get("task_id", "")).strip(),
                    "change_id": change_id,
                    "target_profile_id": target_profile_id,
                    "target_stage_id": target_stage_id,
                    "reason": "already_validated_change_id",
                }
            )
            continue
        if not target_profile_id:
            skipped.append(
                {
                    "task_id": str(item.get("task_id", "")).strip(),
                    "change_id": change_id,
                    "target_profile_id": "",
                    "target_stage_id": target_stage_id,
                    "reason": "missing_target_profile_id",
                }
            )
            continue
        grouped_items.setdefault(target_profile_id, []).append(item)

    for target_profile_id, items in grouped_items.items():
        suite_ids = _resolve_matching_suite_ids(
            registry=benchmark_registry,
            target_profile_id=target_profile_id,
        )
        if not suite_ids:
            for item in items:
                skipped.append(
                    {
                        "task_id": str(item.get("task_id", "")).strip(),
                        "change_id": str(item.get("change_id", "")).strip(),
                        "target_profile_id": target_profile_id,
                        "target_stage_id": str(item.get("target_stage_id", "")).strip(),
                        "reason": "no_matching_benchmark_suite",
                    }
                )
            continue

        profile_suite_results: list[JSONDict] = []
        try:
            for suite_id in suite_ids:
                suite_result = suite_runner_impl(
                    executor_run_dir=str(resolved_executor_run_dir := Path(executor_run_dir).expanduser()),
                    output_root=str(resolved_output_root),
                    state_root=str(resolved_state_root),
                    registry_file=str(resolved_benchmark_suite_file),
                    suite_id=str(suite_id).strip(),
                    task_db=(str(Path(task_db).expanduser()) if str(task_db or "").strip() else None),
                    auto_create_tasks=bool(auto_create_tasks),
                    task_score_threshold=float(task_score_threshold),
                    task_schedule_gap_minutes=max(1, int(task_schedule_gap_minutes)),
                    workflow_profile_registry=(
                        str(Path(workflow_profile_registry).expanduser())
                        if str(workflow_profile_registry or "").strip()
                        else None
                    ),
                    auto_apply_workflow_promotion=bool(auto_apply_workflow_promotion),
                    promotion_operator=str(promotion_operator or "").strip() or "control-plane-profile-update-validation",
                )
                normalized_suite_result = (
                    dict(suite_result) if isinstance(suite_result, dict) else {"suite_id": str(suite_id).strip()}
                )
                normalized_suite_result["suite_id"] = str(
                    normalized_suite_result.get("suite_id", suite_id)
                ).strip() or str(suite_id).strip()
                normalized_suite_result["target_profile_id"] = target_profile_id
                profile_suite_results.append(normalized_suite_result)
                executed_suites.append(normalized_suite_result)
        except Exception as exc:
            for item in items:
                failed.append(
                    {
                        "task_id": str(item.get("task_id", "")).strip(),
                        "change_id": str(item.get("change_id", "")).strip(),
                        "target_profile_id": target_profile_id,
                        "target_stage_id": str(item.get("target_stage_id", "")).strip(),
                        "reason": "benchmark_validation_failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
            continue

        executed_suite_ids = [
            str(item.get("suite_id", "")).strip()
            for item in profile_suite_results
            if str(item.get("suite_id", "")).strip()
        ]
        for item in items:
            change_id = str(item.get("change_id", "")).strip()
            validated_change_ids.add(change_id)
            validated.append(
                {
                    "task_id": str(item.get("task_id", "")).strip(),
                    "change_id": change_id,
                    "target_profile_id": target_profile_id,
                    "target_stage_id": str(item.get("target_stage_id", "")).strip(),
                    "target_stage_label": str(item.get("target_stage_label", "")).strip(),
                    "target_channel": str(item.get("target_channel", "")).strip(),
                    "recommendation_type": str(item.get("recommendation_type", "")).strip(),
                    "suite_ids": executed_suite_ids,
                }
            )

    next_state = {
        "validated_change_ids": sorted(validated_change_ids),
        "updated_at": utc_now_iso(),
    }
    _write_json(resolved_state_file, next_state)

    result = {
        "generated_at": utc_now_iso(),
        "apply_file": str(resolved_apply_file),
        "benchmark_suite_file": str(resolved_benchmark_suite_file),
        "executor_run_dir": str(Path(executor_run_dir).expanduser()),
        "output_root": str(resolved_output_root),
        "state_file": str(resolved_state_file),
        "workflow_profile_registry": (
            str(Path(workflow_profile_registry).expanduser())
            if str(workflow_profile_registry or "").strip()
            else ""
        ),
        "task_db": str(Path(task_db).expanduser()) if str(task_db or "").strip() else "",
        "executed_suite_count": len(executed_suites),
        "validated_change_count": len(validated),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "validated": validated,
        "skipped": skipped,
        "failed": failed,
        "executed_suites": executed_suites,
        "state": next_state,
    }
    result["markdown"] = render_control_plane_profile_update_validation_markdown(result)
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="Validate applied workflow profile updates by running targeted benchmark suites."
    )
    parser.add_argument("--apply-file", required=True)
    parser.add_argument("--benchmark-suite-file", required=True)
    parser.add_argument("--executor-run-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--task-db", default="")
    parser.add_argument("--workflow-profile-registry", default="")
    parser.add_argument("--auto-create-tasks", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--task-score-threshold", type=float, default=80.0)
    parser.add_argument("--task-schedule-gap-minutes", type=int, default=120)
    parser.add_argument("--auto-apply-workflow-promotion", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--promotion-operator", default="control-plane-profile-update-validation")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, suite_runner: SuiteRunner | None = None) -> JSONDict:
    """Run the CLI and return the validation payload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_control_plane_profile_update_validation(
        apply_file=str(args.apply_file).strip(),
        benchmark_suite_file=str(args.benchmark_suite_file).strip(),
        executor_run_dir=str(args.executor_run_dir).strip(),
        output_root=str(args.output_root).strip(),
        state_file=str(args.state_file).strip(),
        workflow_profile_registry=(str(args.workflow_profile_registry).strip() or None),
        task_db=(str(args.task_db).strip() or None),
        auto_create_tasks=bool(args.auto_create_tasks),
        task_score_threshold=float(args.task_score_threshold),
        task_schedule_gap_minutes=max(1, int(args.task_schedule_gap_minutes)),
        auto_apply_workflow_promotion=bool(args.auto_apply_workflow_promotion),
        promotion_operator=str(args.promotion_operator).strip() or "control-plane-profile-update-validation",
        suite_runner=suite_runner,
    )
    payload = {"result": result}
    if str(args.json_output or "").strip():
        _write_json(Path(str(args.json_output).strip()).expanduser(), payload)
    if str(args.markdown_output or "").strip():
        atomic_write_text(
            Path(str(args.markdown_output).strip()).expanduser(),
            result["markdown"],
            encoding="utf-8",
            newline="\n",
            file_mode=0o644,
            dir_mode=0o755,
        )
    if bool(args.emit_json):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(result["markdown"])
    return payload


if __name__ == "__main__":
    main()
